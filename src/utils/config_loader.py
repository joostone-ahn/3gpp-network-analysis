"""
Config Loader 유틸리티

YAML 설정 파일을 로드하고 타입 안전한 dataclass로 변환하는 모듈.

Requirements: 15.3, 15.4
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, TypeVar, Union

import yaml

# 프로젝트 루트 및 config 디렉토리 경로
PROJECT_ROOT = Path(__file__).parent.parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"


# =============================================================================
# Collector 설정 Dataclasses
# =============================================================================


@dataclass
class CollectorTarget:
    """FTP 수집 대상 TSG 및 WG 설정.
    
    Attributes:
        tsg: TSG 그룹명 (RAN, SA, CT)
        min_meeting: 수집 시작 최소 회차 번호
        wg_list: 수집 대상 Working Group 목록 (예: ["TSG", "WG1", "WG2", ...])
    """
    tsg: str
    min_meeting: int
    wg_list: List[str]


@dataclass
class CollectorConfig:
    """FTP Collector 설정.
    
    Attributes:
        ftp_host: FTP 서버 호스트명
        ftp_base_path_template: FTP 경로 템플릿 (예: "/tsg_{tsg_lower}/TSG_{tsg}/TSGR_{mtg}/Docs/")
        targets: 수집 대상 TSG 목록
        max_retry: 최대 재시도 횟수
        retry_delay: 재시도 간 대기 시간 (초)
    """
    ftp_host: str
    ftp_base_path_template: str
    targets: List[CollectorTarget]
    max_retry: int
    retry_delay: int


# =============================================================================
# Preprocessing 설정 Dataclasses
# =============================================================================


@dataclass
class SourceCleaningConfig:
    """Source 문자열 정제 설정.
    
    매칭 전 Source 문자열에 적용되는 정제 규칙.
    
    Attributes:
        special_replacements: 특수 치환 매핑 (예: {"CMCC": "China Mobile"})
        remove_characters: 제거할 문자 목록 (예: ["[", "]", "."])
        add_word_boundary_spaces: 단어 경계 공백 추가 여부
    """
    special_replacements: Dict[str, str]
    remove_characters: List[str]
    add_word_boundary_spaces: bool


@dataclass
class NormalizationConfig:
    """멤버십 정규화 8단계 설정.
    
    ETSI 멤버십 기업명을 정규화하는 8단계 규칙.
    개수는 2026-09 원본 노트북 재검증 결과 반영.
    
    Attributes:
        stopwords: a) 법인격(47개) + 일반 단어(15개), 총 62개
        countries: b) 국가명 suffix (23개)
        removes: c) 특정 지명 (4개)
        replaces: d) 특수 매핑 (15개)
        brackets_pattern: e) 괄호 제거 패턴 (예: "\\s\\(")
        startswith_exceptions: f) 통합 예외 목록 (4개)
        suffix: g) 접미어 (54개)
        prefix: h) 접두어 (8개)
    """
    stopwords: List[str]
    countries: List[str]
    removes: List[str]
    replaces: Dict[str, str]
    brackets_pattern: str
    startswith_exceptions: List[str]
    suffix: List[str]
    prefix: List[str]


@dataclass
class DateRange:
    """날짜 범위 설정.
    
    Attributes:
        min_year: 분석 대상 최소 연도 (이전 연도는 제외)
    """
    min_year: int


@dataclass
class PreprocessingConfig:
    """전처리 설정.
    
    Stage 2~5 전처리 파이프라인의 모든 설정을 포함.
    
    Attributes:
        title_exclude_patterns: Title 기반 제외 패턴 (LS, CR pack 등)
        source_cleaning: Source 문자열 정제 설정
        membership_normalization: 멤버십 정규화 8단계 설정
        wi_delimiters: Work Item 구분자 목록
        wi_exclude_patterns: 제외할 Work Item 패턴 (TEI, DUMMY)
        date_range: 날짜 범위 설정
    """
    title_exclude_patterns: List[str]
    source_cleaning: SourceCleaningConfig
    membership_normalization: NormalizationConfig
    wi_delimiters: List[str]
    wi_exclude_patterns: List[str]
    date_range: DateRange


# =============================================================================
# Network 설정 Dataclasses
# =============================================================================


@dataclass
class NetworkConfig:
    """네트워크 구성 설정.
    
    Stage 6 Network Builder의 파라미터.
    
    Attributes:
        thresholds: Edge Weight 임계값 목록 (예: [0, 1, 2, ..., 9])
        time_units: 시간 단위 목록 (예: ["year", "release", "quarter"])
        tsg_groups: TSG 그룹 목록 (예: ["ALL", "RAN", "SA", "CT"])
    """
    thresholds: List[int]
    time_units: List[str]
    tsg_groups: List[str]


# =============================================================================
# Analysis 설정 Dataclasses
# =============================================================================


@dataclass
class AnalysisConfig:
    """네트워크 분석 설정.
    
    Stage 7 Network Analyzer의 파라미터.
    
    Attributes:
        louvain_seed: Louvain 커뮤니티 탐지 랜덤 시드 (재현성 보장)
        eigenvector_max_iter: Eigenvector Centrality 최대 반복 횟수
        random_network_samples: Small-world 분석용 무작위 네트워크 생성 횟수
    """
    louvain_seed: int
    eigenvector_max_iter: int
    random_network_samples: int


# =============================================================================
# Pipeline 설정 Dataclasses
# =============================================================================


@dataclass
class PipelineConfig:
    """파이프라인 스케줄러 설정.
    
    Attributes:
        schedule: cron 형식 스케줄 표현식 (예: "0 0 * * 0" - 매주 일요일 자정)
    """
    schedule: str


# =============================================================================
# Config Loader 클래스
# =============================================================================


T = TypeVar("T")


class ConfigLoader:
    """YAML 설정 파일 로드 및 dataclass 변환 클래스.
    
    설정 파일을 로드하고 타입 안전한 dataclass 객체로 변환한다.
    
    Usage:
        >>> loader = ConfigLoader()
        >>> collector_config = loader.load_collector_config()
        >>> preprocessing_config = loader.load_preprocessing_config()
    """
    
    def __init__(self, config_dir: Optional[Path] = None):
        """ConfigLoader 초기화.
        
        Args:
            config_dir: 설정 파일 디렉토리 경로. None이면 기본 config/ 디렉토리 사용.
        """
        self.config_dir = config_dir or CONFIG_DIR
    
    def _load_yaml(self, filename: str) -> Dict[str, Any]:
        """YAML 파일 로드.
        
        Args:
            filename: YAML 파일명 (확장자 포함)
            
        Returns:
            파싱된 YAML 딕셔너리
            
        Raises:
            FileNotFoundError: 파일이 존재하지 않는 경우
            yaml.YAMLError: YAML 파싱 에러
        """
        filepath = self.config_dir / filename
        if not filepath.exists():
            raise FileNotFoundError(f"설정 파일을 찾을 수 없습니다: {filepath}")
        
        with open(filepath, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    
    def load_collector_config(self) -> CollectorConfig:
        """collector.yaml 로드 및 CollectorConfig로 변환.
        
        Returns:
            CollectorConfig 객체
        """
        data = self._load_yaml("collector.yaml")
        
        # targets 리스트를 CollectorTarget 객체로 변환
        targets = [
            CollectorTarget(
                tsg=t["tsg"],
                min_meeting=t["min_meeting"],
                wg_list=t["wg_list"],
            )
            for t in data.get("targets", [])
        ]
        
        return CollectorConfig(
            ftp_host=data.get("ftp", {}).get("host", ""),
            ftp_base_path_template=data.get("ftp", {}).get("base_path_template", ""),
            targets=targets,
            max_retry=data.get("retry", {}).get("max_attempts", 3),
            retry_delay=data.get("retry", {}).get("delay_seconds", 5),
        )
    
    def load_preprocessing_config(self) -> PreprocessingConfig:
        """preprocessing.yaml 로드 및 PreprocessingConfig로 변환.
        
        Returns:
            PreprocessingConfig 객체
        """
        data = self._load_yaml("preprocessing.yaml")
        
        # source_cleaning 섹션
        source_cleaning_data = data.get("source_cleaning", {})
        source_cleaning = SourceCleaningConfig(
            special_replacements=source_cleaning_data.get("special_replacements", {}),
            remove_characters=source_cleaning_data.get("remove_characters", []),
            add_word_boundary_spaces=source_cleaning_data.get("add_word_boundary_spaces", True),
        )
        
        # membership_normalization 섹션
        normalization_data = data.get("membership_normalization", {})
        membership_normalization = NormalizationConfig(
            stopwords=normalization_data.get("stopwords", []),
            countries=normalization_data.get("countries", []),
            removes=normalization_data.get("removes", []),
            replaces=normalization_data.get("replaces", {}),
            brackets_pattern=normalization_data.get("brackets_pattern", r"\s\("),
            startswith_exceptions=normalization_data.get("startswith_exceptions", []),
            suffix=normalization_data.get("suffix", []),
            prefix=normalization_data.get("prefix", []),
        )
        
        # date_range 섹션
        date_range_data = data.get("date_range", {})
        date_range = DateRange(
            min_year=date_range_data.get("min_year", 2015),
        )
        
        return PreprocessingConfig(
            title_exclude_patterns=data.get("title_exclude_patterns", []),
            source_cleaning=source_cleaning,
            membership_normalization=membership_normalization,
            wi_delimiters=data.get("wi_delimiters", [","]),
            wi_exclude_patterns=data.get("wi_exclude_patterns", []),
            date_range=date_range,
        )
    
    def load_network_config(self) -> NetworkConfig:
        """network.yaml 로드 및 NetworkConfig로 변환.
        
        Returns:
            NetworkConfig 객체
        """
        data = self._load_yaml("network.yaml")
        
        return NetworkConfig(
            thresholds=data.get("thresholds", list(range(10))),
            time_units=data.get("time_units", ["year", "release", "quarter"]),
            tsg_groups=data.get("tsg_groups", ["ALL", "RAN", "SA", "CT"]),
        )
    
    def load_analysis_config(self) -> AnalysisConfig:
        """analysis.yaml 로드 및 AnalysisConfig로 변환.
        
        Returns:
            AnalysisConfig 객체
        """
        data = self._load_yaml("analysis.yaml")
        
        return AnalysisConfig(
            louvain_seed=data.get("louvain_seed", 42),
            eigenvector_max_iter=data.get("eigenvector_max_iter", 1000),
            random_network_samples=data.get("random_network_samples", 100),
        )
    
    def load_pipeline_config(self) -> PipelineConfig:
        """pipeline.yaml 로드 및 PipelineConfig로 변환.
        
        Returns:
            PipelineConfig 객체
        """
        data = self._load_yaml("pipeline.yaml")
        
        return PipelineConfig(
            schedule=data.get("schedule", "0 0 * * 0"),  # 기본값: 매주 일요일 자정
        )


# =============================================================================
# 편의 함수
# =============================================================================


_default_loader: Optional[ConfigLoader] = None


def get_config_loader() -> ConfigLoader:
    """기본 ConfigLoader 인스턴스 반환 (싱글톤 패턴).
    
    Returns:
        ConfigLoader 인스턴스
    """
    global _default_loader
    if _default_loader is None:
        _default_loader = ConfigLoader()
    return _default_loader


def load_config(config_name: str) -> Any:
    """YAML 설정 파일을 로드하여 적절한 dataclass로 변환.
    
    Args:
        config_name: 설정 파일명 (확장자 제외 또는 포함 가능)
                     지원: collector, preprocessing, network, analysis, pipeline
    
    Returns:
        해당 설정의 dataclass 객체
        
    Raises:
        ValueError: 지원하지 않는 설정 파일명인 경우
        FileNotFoundError: 파일이 존재하지 않는 경우
        
    Example:
        >>> collector_config = load_config("collector")
        >>> preprocessing_config = load_config("preprocessing")
    """
    loader = get_config_loader()
    
    # 확장자 제거
    config_name = config_name.replace(".yaml", "").replace(".yml", "")
    
    config_loaders = {
        "collector": loader.load_collector_config,
        "preprocessing": loader.load_preprocessing_config,
        "network": loader.load_network_config,
        "analysis": loader.load_analysis_config,
        "pipeline": loader.load_pipeline_config,
    }
    
    if config_name not in config_loaders:
        raise ValueError(
            f"지원하지 않는 설정 파일입니다: {config_name}. "
            f"지원 목록: {list(config_loaders.keys())}"
        )
    
    return config_loaders[config_name]()


def load_raw_yaml(config_name: str) -> Dict[str, Any]:
    """YAML 파일을 딕셔너리로 로드 (dataclass 변환 없이).
    
    dataclass로 변환하지 않고 원본 딕셔너리가 필요한 경우 사용.
    
    Args:
        config_name: 설정 파일명 (확장자 포함 또는 제외 가능)
    
    Returns:
        YAML 파일 내용의 딕셔너리
    """
    loader = get_config_loader()
    
    # 확장자 없으면 추가
    if not config_name.endswith((".yaml", ".yml")):
        config_name = f"{config_name}.yaml"
    
    return loader._load_yaml(config_name)


# =============================================================================
# 타입 별칭 (외부 모듈 사용 편의)
# =============================================================================


__all__ = [
    # Dataclasses
    "CollectorTarget",
    "CollectorConfig",
    "SourceCleaningConfig",
    "NormalizationConfig",
    "DateRange",
    "PreprocessingConfig",
    "NetworkConfig",
    "AnalysisConfig",
    "PipelineConfig",
    # Loader
    "ConfigLoader",
    # 편의 함수
    "get_config_loader",
    "load_config",
    "load_raw_yaml",
    # 경로 상수
    "PROJECT_ROOT",
    "CONFIG_DIR",
]
