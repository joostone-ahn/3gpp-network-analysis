"""
Membership-based Extractor Module (Stage 3)

Source 문자열에서 ETSI 멤버십 기업명을 직접 추출하는 모듈.

요구사항:
- 4.1: Source 문자열에서 ETSI 멤버십 기업명을 직접 탐색하여 추출
- 4.2: Source 문자열 탐색 전에 Source 문자열 정제 규칙 적용
- 4.3: 멤버십 기업명 탐색 시 멤버십 정규화 규칙을 순차적으로 적용
- 4.4: 대소문자 무시 (case-insensitive) 탐색
- 4.5: 수작업 매핑 파일의 alias를 멤버십 목록에 포함
- 4.6: 추출된 기업이 0개인 경우 unmatched_sources.csv에 기록
- 4.7: 추출된 기업명 목록을 개별 행으로 분리(explode)
- 4.8: 추출/분리 전후 레코드 수 변화를 로그에 기록
- 4.9: 매핑 결과를 캐시로 저장, 입력 Source 목록 해시가 변경될 때 캐시 무효화

정제 순서:
1. CMCC → China Mobile 치환 (MCC 필터링 전 예외처리)
2. 대괄호 제거 ([, ])
3. 마침표 제거 (.)
4. 앞뒤 공백 추가 (단어 경계 매칭용)

정규화 순서 (8단계):
a) stopwords 제거 - 법인격(47개) + 일반 단어(15개), 총 62개
b) countries 제거 - 국가명 suffix (23개)
c) removes 제거 - 지명 (4개)
d) replaces 특수 매핑 - 특정 기업명 변환 (15개)
e) brackets 괄호 제거 - (...) 형태 제거
f) startswith 통합 - 정렬 후 prefix 기반 통합
g) suffix 제거 - 접미어 (54개)
h) prefix 제거 - 접두어 (8개)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import pandas as pd

from src.utils.logger import get_logger

# 모듈 로거
logger = get_logger("preprocessor", default_stage="membership_extractor")


@dataclass
class SourceCleaningConfig:
    """Source 문자열 정제 설정.
    
    Source 문자열에서 멤버십 기업명을 탐색하기 전에 적용할 정제 규칙을 정의한다.
    
    Attributes:
        special_replacements: 특수 치환 매핑 (예: {"CMCC": "China Mobile"})
            - MCC 필터링 전에 CMCC를 China Mobile로 치환하기 위한 예외처리
        remove_characters: 제거할 문자 목록 (예: ["[", "]", "."])
            - 대괄호와 마침표 제거
        add_word_boundary_spaces: 단어 경계 공백 추가 여부
            - True: 앞뒤 공백 추가하여 부분 문자열 오매칭 방지
    
    Example:
        >>> config = SourceCleaningConfig(
        ...     special_replacements={"CMCC": "China Mobile"},
        ...     remove_characters=["[", "]", "."],
        ...     add_word_boundary_spaces=True
        ... )
    """
    special_replacements: Dict[str, str] = field(default_factory=dict)
    remove_characters: List[str] = field(default_factory=list)
    add_word_boundary_spaces: bool = True
    
    @classmethod
    def from_dict(cls, config_dict: Dict) -> "SourceCleaningConfig":
        """딕셔너리로부터 SourceCleaningConfig 생성.
        
        Args:
            config_dict: source_cleaning 설정 딕셔너리
                - special_replacements: Dict[str, str]
                - remove_characters: List[str]
                - add_word_boundary_spaces: bool
        
        Returns:
            SourceCleaningConfig 인스턴스
        """
        return cls(
            special_replacements=config_dict.get("special_replacements", {}),
            remove_characters=config_dict.get("remove_characters", []),
            add_word_boundary_spaces=config_dict.get("add_word_boundary_spaces", True),
        )
    
    def to_dict(self) -> Dict:
        """딕셔너리로 변환."""
        return {
            "special_replacements": self.special_replacements,
            "remove_characters": self.remove_characters,
            "add_word_boundary_spaces": self.add_word_boundary_spaces,
        }


class SourceCleaner:
    """Source 문자열 정제 규칙 적용.
    
    Source 문자열에서 멤버십 기업명을 탐색하기 전에 다음 정제 규칙을 적용한다:
    1. 특수 치환 (CMCC → China Mobile) - MCC 필터링 전 예외처리
    2. 대괄호 제거 ([, ])
    3. 마침표 제거 (.)
    4. 앞뒤 공백 추가 (단어 경계 매칭용)
    
    Attributes:
        config: SourceCleaningConfig 설정 객체
    
    Example:
        >>> config = SourceCleaningConfig(
        ...     special_replacements={"CMCC": "China Mobile"},
        ...     remove_characters=["[", "]", "."],
        ...     add_word_boundary_spaces=True
        ... )
        >>> cleaner = SourceCleaner(config)
        >>> result = cleaner.clean("Samsung Electronics Co., Ltd., [CMCC], Chair")
        >>> print(result)
        " Samsung Electronics Co, Ltd, China Mobile, Chair "
    """
    
    def __init__(self, config: SourceCleaningConfig) -> None:
        """
        Args:
            config: source_cleaning 설정
        """
        self.config = config
        
        logger.info_with_details(
            f"SourceCleaner 초기화 완료: "
            f"{len(config.special_replacements)}개 특수 치환, "
            f"{len(config.remove_characters)}개 제거 문자",
            stage="source_cleaner",
            details=config.to_dict(),
        )
    
    def clean(self, source: str) -> str:
        """Source 문자열 정제.
        
        정제 순서:
        1. 특수 치환 (CMCC → China Mobile) - MCC 필터링 전 예외처리
        2. 대괄호 제거 ([, ])
        3. 마침표 제거 (.)
        4. 앞뒤 공백 추가 (단어 경계 매칭용)
        
        Args:
            source: 원본 Source 문자열
            
        Returns:
            정제된 Source 문자열
            
        Note:
            - None 또는 빈 문자열 입력 시 빈 문자열 반환
            - 정제 순서는 요구사항에 따라 고정됨
        """
        # None 또는 빈 문자열 처리
        if source is None:
            return ""
        
        if not isinstance(source, str):
            source = str(source)
        
        if not source.strip():
            return ""
        
        result = source
        
        # 1. 특수 치환 (CMCC → China Mobile)
        # MCC 필터링 전에 CMCC를 China Mobile로 치환하여 예외처리
        for old_value, new_value in self.config.special_replacements.items():
            result = result.replace(old_value, new_value)
        
        # 2. 대괄호 제거 ([, ])
        # 3. 마침표 제거 (.)
        # remove_characters 리스트의 모든 문자 제거
        for char in self.config.remove_characters:
            result = result.replace(char, "")
        
        # 4. 앞뒤 공백 추가 (단어 경계 매칭용)
        if self.config.add_word_boundary_spaces:
            result = f" {result} "
        
        return result
    
    def clean_batch(self, sources: List[str]) -> List[str]:
        """복수 Source 문자열 일괄 정제.
        
        Args:
            sources: 원본 Source 문자열 리스트
            
        Returns:
            정제된 Source 문자열 리스트
            
        Example:
            >>> sources = [
            ...     "Samsung, [CMCC]",
            ...     "Nokia Corp.",
            ...     "Huawei"
            ... ]
            >>> cleaned = cleaner.clean_batch(sources)
        """
        if not sources:
            return []
        
        return [self.clean(source) for source in sources]
    
    @classmethod
    def from_config(cls, config_dict: Dict) -> "SourceCleaner":
        """설정 딕셔너리로부터 SourceCleaner 생성.
        
        Args:
            config_dict: source_cleaning 설정 딕셔너리
            
        Returns:
            SourceCleaner 인스턴스
        """
        source_config = SourceCleaningConfig.from_dict(config_dict)
        return cls(source_config)


# =============================================================================
# NormalizationConfig & NormalizationStep dataclass (Task 7.3)
# =============================================================================


@dataclass
class NormalizationStep:
    """정규화 단계 정보.
    
    normalize_with_trace()가 반환하는 단계별 변환 추적 정보.
    
    Attributes:
        stage_name: 정규화 단계 이름 (예: "stopwords", "countries")
        before: 적용 전 기업명
        after: 적용 후 기업명
        changed: 변경 여부 (True: 변경됨, False: 변경 없음)
    
    Example:
        >>> step = NormalizationStep(
        ...     stage_name="stopwords",
        ...     before="Samsung Electronics Co., Ltd.",
        ...     after="Samsung Electronics",
        ...     changed=True
        ... )
    """
    stage_name: str
    before: str
    after: str
    changed: bool
    
    def to_dict(self) -> Dict:
        """딕셔너리로 변환."""
        return {
            "stage_name": self.stage_name,
            "before": self.before,
            "after": self.after,
            "changed": self.changed,
        }


@dataclass
class NormalizationConfig:
    """멤버십 정규화 설정.
    
    ETSI 멤버십 기업명 정규화에 필요한 8단계 규칙을 정의한다.
    
    Attributes:
        stopwords: 법인격(47개) + 일반 단어(15개), 총 62개
        countries: 국가명 suffix 제거 (23개)
        removes: 특정 지명 제거 (4개)
        replaces: 특수 매핑 (15개)
        brackets_pattern: 괄호 제거 패턴 (기본: r'\\s\\(')
        startswith_exceptions: prefix 기반 통합 예외 목록 (4개)
        suffix: 접미어 제거 (54개)
        prefix: 접두어 제거 (8개)
    
    Example:
        >>> config = NormalizationConfig(
        ...     stopwords=[" Co.", " Ltd."],
        ...     countries=[" Germany", " Korea"],
        ...     removes=["Beijing"],
        ...     replaces={"HuaWei": "Huawei"},
        ...     brackets_pattern=r"\\s\\(",
        ...     startswith_exceptions=["BTL"],
        ...     suffix=[" Software"],
        ...     prefix=["Shanghai "]
        ... )
    """
    stopwords: List[str] = field(default_factory=list)  # 62개
    countries: List[str] = field(default_factory=list)  # 23개
    removes: List[str] = field(default_factory=list)    # 4개
    replaces: Dict[str, str] = field(default_factory=dict)  # 15개
    brackets_pattern: str = r"\s\("  # 괄호 제거 패턴
    startswith_exceptions: List[str] = field(
        default_factory=lambda: ["BTL", "CISA ECD", "Intelsat", "IIIT Bangalore"]
    )  # 4개
    suffix: List[str] = field(default_factory=list)     # 54개
    prefix: List[str] = field(default_factory=list)     # 8개
    
    @classmethod
    def from_dict(cls, config_dict: Dict) -> "NormalizationConfig":
        """딕셔너리로부터 NormalizationConfig 생성.
        
        Args:
            config_dict: membership_normalization 설정 딕셔너리
        
        Returns:
            NormalizationConfig 인스턴스
        """
        return cls(
            stopwords=config_dict.get("stopwords", []),
            countries=config_dict.get("countries", []),
            removes=config_dict.get("removes", []),
            replaces=config_dict.get("replaces", {}),
            brackets_pattern=config_dict.get("brackets_pattern", r"\s\("),
            startswith_exceptions=config_dict.get("startswith_exceptions", []),
            suffix=config_dict.get("suffix", []),
            prefix=config_dict.get("prefix", []),
        )
    
    def to_dict(self) -> Dict:
        """딕셔너리로 변환."""
        return {
            "stopwords": self.stopwords,
            "countries": self.countries,
            "removes": self.removes,
            "replaces": self.replaces,
            "brackets_pattern": self.brackets_pattern,
            "startswith_exceptions": self.startswith_exceptions,
            "suffix": self.suffix,
            "prefix": self.prefix,
        }
    
    def validate(self) -> None:
        """설정 유효성 검증.
        
        Raises:
            ValueError: 필수 설정이 누락되거나 유효하지 않은 경우
        """
        # 필수 목록이 비어있지 않은지 검증
        if not self.stopwords:
            logger.warning("stopwords 목록이 비어있습니다.")
        if not self.countries:
            logger.warning("countries 목록이 비어있습니다.")
        if not self.suffix:
            logger.warning("suffix 목록이 비어있습니다.")
        if not self.prefix:
            logger.warning("prefix 목록이 비어있습니다.")
        
        # 개수 검증 (로그 레벨)
        expected_counts = {
            "stopwords": 62,
            "countries": 23,
            "removes": 4,
            "replaces": 15,
            "suffix": 54,
            "prefix": 8,
            "startswith_exceptions": 4,
        }
        
        actual_counts = {
            "stopwords": len(self.stopwords),
            "countries": len(self.countries),
            "removes": len(self.removes),
            "replaces": len(self.replaces),
            "suffix": len(self.suffix),
            "prefix": len(self.prefix),
            "startswith_exceptions": len(self.startswith_exceptions),
        }
        
        for key, expected in expected_counts.items():
            actual = actual_counts[key]
            if actual != expected:
                logger.info(
                    f"NormalizationConfig.{key}: 기대 {expected}개, 실제 {actual}개"
                )


# =============================================================================
# MembershipNormalizer 클래스 (Task 7.3)
# =============================================================================


class MembershipNormalizer:
    """ETSI 멤버십 기업명 정규화 (8단계 순차 적용).
    
    requirements.md의 정규화 규칙에 따라 ETSI 멤버십 기업명을 8단계로 정규화한다.
    각 단계는 순서대로 적용되며, 단계별 변환 추적이 가능하다.
    
    정규화 단계:
        a) stopwords 제거 - 법인격(47개) + 일반 단어(15개), 총 62개
        b) countries 제거 - 국가명 suffix (23개)
        c) removes 제거 - 지명 (4개)
        d) replaces 특수 매핑 - 특정 기업명 변환 (15개)
        e) brackets 괄호 제거 - (...) 형태 제거
        f) startswith 통합 - 정렬 후 prefix 기반 통합
        g) suffix 제거 - 접미어 (54개)
        h) prefix 제거 - 접두어 (8개)
    
    Attributes:
        config: NormalizationConfig 설정 객체
        _normalization_stages: 정규화 단계 목록 (이름, 메서드 쌍)
        _startswith_lookup: startswith 통합용 정렬된 기업명 목록 (build_lookup_table 호출 후 설정)
    
    Example:
        >>> config = NormalizationConfig.from_dict(yaml_config)
        >>> normalizer = MembershipNormalizer(config)
        >>> result = normalizer.normalize("Samsung Electronics Co., Ltd.")
        >>> print(result)
        "Samsung Electronics"
    """
    
    def __init__(self, config: NormalizationConfig) -> None:
        """MembershipNormalizer 초기화.
        
        Args:
            config: membership_normalization 설정 객체
        """
        self.config = config
        
        # 정규화 단계 정의 (순서 중요!)
        self._normalization_stages: List[Tuple[str, Callable[[str], str]]] = [
            ("stopwords", self._remove_stopwords),
            ("countries", self._remove_countries),
            ("removes", self._remove_specific),
            ("replaces", self._apply_replaces),
            ("brackets", self._remove_brackets),
            # startswith는 build_lookup_table에서 전체 목록 기준으로 처리
            ("suffix", self._remove_suffix),
            ("prefix", self._remove_prefix),
        ]
        
        # startswith 통합용 (build_lookup_table 호출 시 설정)
        self._startswith_lookup: List[str] = []
        
        # 설정 유효성 검증
        config.validate()
        
        logger.info_with_details(
            f"MembershipNormalizer 초기화 완료: "
            f"stopwords={len(config.stopwords)}, countries={len(config.countries)}, "
            f"removes={len(config.removes)}, replaces={len(config.replaces)}, "
            f"suffix={len(config.suffix)}, prefix={len(config.prefix)}",
            stage="membership_normalizer",
            details={"stages_count": len(self._normalization_stages) + 1},  # +1 for startswith
        )
    
    # =========================================================================
    # 8단계 정규화 내부 메서드
    # =========================================================================
    
    def _remove_stopwords(self, name: str) -> str:
        """a) 법인격 및 일반 단어 제거.
        
        법인격 표기(47개)와 일반 기업명 접미사(15개)를 제거한다.
        제거 순서는 config.stopwords 리스트 순서를 따른다.
        
        Args:
            name: 원본 기업명
            
        Returns:
            stopwords가 제거된 기업명
            
        Example:
            >>> self._remove_stopwords("Samsung Electronics Co., Ltd.")
            "Samsung Electronics"
        """
        result = name
        for stopword in self.config.stopwords:
            result = result.replace(stopword, "")
        # 여분의 쉼표와 공백 정리
        result = re.sub(r',\s*,', ',', result)  # 연속 쉼표 정리
        result = re.sub(r',\s*$', '', result)   # 끝의 쉼표 제거
        result = re.sub(r'^\s*,', '', result)   # 시작의 쉼표 제거
        result = re.sub(r'\s+', ' ', result)    # 연속 공백 정리
        return result.strip()
    
    def _remove_countries(self, name: str) -> str:
        """b) 국가명 suffix 제거.
        
        기업명 뒤에 붙는 국가명 접미사(23개)를 제거한다.
        
        Args:
            name: 원본 기업명
            
        Returns:
            국가명이 제거된 기업명
            
        Example:
            >>> self._remove_countries("Samsung Germany")
            "Samsung"
        """
        result = name
        for country in self.config.countries:
            result = result.replace(country, "")
        return result.strip()
    
    def _remove_specific(self, name: str) -> str:
        """c) 특정 지명 제거.
        
        기업명에 포함된 지명(4개)을 제거한다.
        
        Args:
            name: 원본 기업명
            
        Returns:
            지명이 제거된 기업명
            
        Example:
            >>> self._remove_specific("Beijing Samsung")
            "Samsung"
        """
        result = name
        for remove_word in self.config.removes:
            result = result.replace(remove_word, "")
        return result.strip()
    
    def _apply_replaces(self, name: str) -> str:
        """d) 특수 매핑 적용.
        
        특정 기업명을 표준화된 이름으로 변환한다(15개 매핑).
        
        Note:
            - 더 긴 패턴을 먼저 적용하여 더 구체적인 매핑이 우선 처리됨
            - 매핑 적용 후 연쇄 변환이 필요한 경우 2차 패스 실행
            - 플레이스홀더를 사용하여 같은 패스 내 중복 치환 방지
            - 변환 결과가 다른 source 패턴을 포함하는 경우 해당 패턴 스킵
        
        Args:
            name: 원본 기업명
            
        Returns:
            매핑이 적용된 기업명
            
        Example:
            >>> self._apply_replaces("HuaWei Device")
            "Huawei"
        """
        result = name
        
        # replaces를 길이가 긴 것부터 적용 (더 구체적인 매핑 우선)
        sorted_replaces = sorted(
            self.config.replaces.items(), 
            key=lambda x: len(x[0]), 
            reverse=True
        )
        
        # 변환 결과값들을 수집 (이 값들에 대해서는 다시 매핑하지 않음)
        target_values = set(v.lower() for v in self.config.replaces.values())
        
        # 2패스 실행 (연쇄 변환 지원: HuaWei → Huawei → Huawei Device → Huawei)
        for pass_num in range(2):
            # 플레이스홀더를 사용하여 변환된 부분이 같은 패스에서 다시 변환되지 않도록 함
            placeholders = {}
            placeholder_idx = 0
            
            for old_value, new_value in sorted_replaces:
                if old_value in result:
                    # 이미 변환된 값의 부분 문자열이면 스킵
                    # (예: "NTT Docomo"에서 "Docomo"가 DOCOMO 패턴에 매칭되는 것 방지)
                    # old_value가 이미 적용된 target의 부분 문자열이면 스킵
                    is_part_of_target = False
                    for target in target_values:
                        if old_value.lower() in target and old_value.lower() != target:
                            # old_value가 target에 포함되어 있고, 전체가 아닌 경우
                            # result에 해당 target이 있는지 확인
                            for existing_target in self.config.replaces.values():
                                if existing_target in result and old_value.lower() in existing_target.lower():
                                    is_part_of_target = True
                                    break
                        if is_part_of_target:
                            break
                    
                    if is_part_of_target:
                        continue
                    
                    # 플레이스홀더로 임시 치환
                    placeholder = f"\x00{pass_num}_{placeholder_idx}\x00"
                    placeholders[placeholder] = new_value
                    result = result.replace(old_value, placeholder)
                    placeholder_idx += 1
            
            # 플레이스홀더를 실제 값으로 복원
            for placeholder, value in placeholders.items():
                result = result.replace(placeholder, value)
        
        # 여분의 쉼표와 공백 정리
        result = re.sub(r',\s*,', ',', result)  # 연속 쉼표 정리
        result = re.sub(r',\s*$', '', result)   # 끝의 쉼표 제거
        result = re.sub(r'^\s*,', '', result)   # 시작의 쉼표 제거
        result = re.sub(r'\s+', ' ', result)    # 연속 공백 정리
        return result.strip()
    
    def _remove_brackets(self, name: str) -> str:
        """e) 괄호 및 내용 제거.
        
        (...)` 형태의 괄호와 그 이후 내용을 제거한다.
        re.split(r'\\s\\(', name)[0] 방식으로 여는 괄호 기준 분리.
        
        Args:
            name: 원본 기업명
            
        Returns:
            괄호가 제거된 기업명
            
        Example:
            >>> self._remove_brackets("Samsung (Korea)")
            "Samsung"
        """
        if not name:
            return ""
        
        # 공백+여는 괄호 패턴으로 분리
        parts = re.split(self.config.brackets_pattern, name)
        result = parts[0].strip()
        
        # 여분의 쉼표와 공백 정리 (괄호 앞 쉼표 처리)
        result = re.sub(r',\s*$', '', result)   # 끝의 쉼표 제거
        result = re.sub(r'^\s*,', '', result)   # 시작의 쉼표 제거
        
        return result.strip()
    
    def _merge_startswith(self, name: str, all_names: List[str]) -> str:
        """f) prefix 기반 통합.
        
        정렬 후 이전 기업명으로 시작하는 기업명을 이전 값으로 통합한다.
        예외 목록의 기업명은 통합하지 않는다.
        
        Note:
            이 메서드는 전체 기업명 목록이 필요하므로 build_lookup_table에서
            별도로 처리된다. normalize() 메서드에서는 호출되지 않는다.
        
        Args:
            name: 현재 기업명
            all_names: 정렬된 전체 기업명 목록
            
        Returns:
            통합된 기업명 (이전 기업명으로 시작하면 이전 값 반환)
        """
        # 예외 목록에 있으면 통합하지 않음
        if name in self.config.startswith_exceptions:
            return name
        
        # 정렬된 목록에서 현재 이름으로 시작하는 이전 항목 찾기
        for existing_name in all_names:
            if existing_name == name:
                break
            # 현재 이름이 기존 이름으로 시작하면 기존 이름으로 통합
            if name.startswith(existing_name) and existing_name not in self.config.startswith_exceptions:
                return existing_name
        
        return name
    
    def _remove_suffix(self, name: str) -> str:
        """g) 접미어 제거.
        
        기업명 뒤에 붙는 일반적인 접미어(54개)를 제거한다.
        
        Args:
            name: 원본 기업명
            
        Returns:
            접미어가 제거된 기업명
            
        Example:
            >>> self._remove_suffix("Samsung Software")
            "Samsung"
        """
        result = name
        # suffix를 길이가 긴 것부터 적용 (더 구체적인 접미어 우선)
        sorted_suffix = sorted(self.config.suffix, key=len, reverse=True)
        for suf in sorted_suffix:
            if result.endswith(suf):
                result = result[:-len(suf)]
                break  # 하나만 제거 (중복 제거 방지)
        return result.strip()
    
    def _remove_prefix(self, name: str) -> str:
        """h) 접두어 제거.
        
        기업명 앞에 붙는 지명 접두어(8개)를 제거한다.
        
        Args:
            name: 원본 기업명
            
        Returns:
            접두어가 제거된 기업명
            
        Example:
            >>> self._remove_prefix("Shanghai Samsung")
            "Samsung"
        """
        result = name
        # prefix를 길이가 긴 것부터 적용 (더 구체적인 접두어 우선)
        sorted_prefix = sorted(self.config.prefix, key=len, reverse=True)
        for pref in sorted_prefix:
            if result.startswith(pref):
                result = result[len(pref):]
                break  # 하나만 제거 (중복 제거 방지)
        return result.strip()
    
    # =========================================================================
    # 공개 API 메서드
    # =========================================================================
    
    def normalize(self, company_name: str) -> str:
        """단일 기업명 정규화 (8단계 순차 적용).
        
        8단계 규칙을 순서대로 적용하여 기업명을 정규화한다.
        단, startswith 단계는 전체 목록이 필요하므로 이 메서드에서는 스킵된다.
        startswith 통합은 build_lookup_table()에서 전체 목록 기준으로 처리된다.
        
        정규화 단계:
            a) stopwords 제거 - 법인격(47개) + 일반 단어(15개)
            b) countries 제거 - 국가명 suffix (23개)
            c) removes 제거 - 지명 (4개)
            d) replaces 특수 매핑 - 특정 기업명 변환 (15개)
            e) brackets 괄호 제거 - (...) 형태 제거
            f) (startswith - build_lookup_table에서 별도 처리)
            g) suffix 제거 - 접미어 (54개)
            h) prefix 제거 - 접두어 (8개)
        
        Args:
            company_name: 원본 기업명
            
        Returns:
            정규화된 기업명
            
        Example:
            >>> normalizer.normalize("Guangdong OPPO Mobile Communication Co., Ltd. (Shenzhen)")
            "OPPO"
        """
        if not company_name or not isinstance(company_name, str):
            return ""
        
        result = company_name.strip()
        
        # 각 단계 순차 적용 (startswith 제외)
        for stage_name, stage_func in self._normalization_stages:
            result = stage_func(result)
        
        return result.strip()
    
    def normalize_with_trace(
        self, company_name: str
    ) -> Tuple[str, List[NormalizationStep]]:
        """정규화 단계별 추적 정보 포함.
        
        8단계 정규화를 수행하면서 각 단계의 변환 내역을 추적한다.
        디버깅 및 검증 목적으로 사용한다.
        
        Args:
            company_name: 원본 기업명
            
        Returns:
            Tuple[정규화된_기업명, 단계별_변환_기록_리스트]
            
        Example:
            >>> result, steps = normalizer.normalize_with_trace(
            ...     "Guangdong OPPO Mobile Communication Co., Ltd. (Shenzhen)"
            ... )
            >>> print(result)
            "OPPO"
            >>> for step in steps:
            ...     if step.changed:
            ...         print(f"{step.stage_name}: {step.before} → {step.after}")
        """
        if not company_name or not isinstance(company_name, str):
            return "", []
        
        result = company_name.strip()
        trace: List[NormalizationStep] = []
        
        # 각 단계 순차 적용 및 추적 (startswith 제외)
        for stage_name, stage_func in self._normalization_stages:
            before = result
            result = stage_func(result)
            after = result
            
            trace.append(NormalizationStep(
                stage_name=stage_name,
                before=before,
                after=after,
                changed=(before != after),
            ))
        
        return result.strip(), trace
    
    def build_lookup_table(
        self, membership_df: pd.DataFrame, 
        company_column: str = "Company"
    ) -> Dict[str, str]:
        """멤버십 DataFrame을 정규화하여 검색 테이블 구축.
        
        ETSI 멤버십 목록을 정규화하고 검색 테이블을 구축한다.
        startswith 통합은 이 메서드에서 전체 목록 기준으로 처리된다.
        
        Returns:
            Dict[정규화된_기업명_소문자 → 표준_기업명]
            - 키: 정규화된 기업명 (소문자, case-insensitive 매칭용)
            - 값: 표준 기업명 (원본 정규화 결과)
        
        Args:
            membership_df: ETSI 멤버십 원본 DataFrame
            company_column: 기업명 컬럼명 (기본: "Company")
            
        Returns:
            검색 테이블 딕셔너리
            
        Example:
            >>> lookup = normalizer.build_lookup_table(membership_df)
            >>> company = lookup.get("samsung electronics")  # case-insensitive
            >>> print(company)
            "Samsung Electronics"
        """
        if membership_df.empty:
            logger.warning("멤버십 DataFrame이 비어있습니다.")
            return {}
        
        if company_column not in membership_df.columns:
            raise ValueError(f"컬럼 '{company_column}'이 DataFrame에 없습니다.")
        
        # 1. 원본 기업명 추출 및 중복 제거
        original_names = membership_df[company_column].dropna().unique().tolist()
        logger.info(f"원본 멤버십 기업 수: {len(original_names)}")
        
        # 2. 각 기업명을 a)~e) 단계까지 정규화
        # (startswith 전까지)
        intermediate_names: Dict[str, str] = {}  # 중간 결과 → 원본 대응
        for name in original_names:
            result = name.strip()
            
            # a) stopwords
            result = self._remove_stopwords(result)
            # b) countries
            result = self._remove_countries(result)
            # c) removes
            result = self._remove_specific(result)
            # d) replaces
            result = self._apply_replaces(result)
            # e) brackets
            result = self._remove_brackets(result)
            
            if result:
                # 중복 시 첫 번째 것 유지
                if result not in intermediate_names:
                    intermediate_names[result] = result
        
        # 3. f) startswith 통합
        # 정렬 후 prefix 기반 통합
        sorted_names = sorted(intermediate_names.keys())
        merged_names: Dict[str, str] = {}  # 통합 결과 → 표준명
        
        for name in sorted_names:
            # 예외 목록에 있으면 통합하지 않음
            if name in self.config.startswith_exceptions:
                merged_names[name] = name
                continue
            
            # 이미 등록된 이름으로 시작하는지 확인
            found_prefix = None
            for existing_name in merged_names.keys():
                if (name.startswith(existing_name) and 
                    existing_name not in self.config.startswith_exceptions and
                    name != existing_name):
                    found_prefix = existing_name
                    break
            
            if found_prefix:
                # 기존 이름으로 통합 (merged_names[name]은 설정하지 않음, 
                # 대신 나중에 검색 테이블에서 처리)
                merged_names[name] = found_prefix
            else:
                merged_names[name] = name
        
        # 4. g) suffix, h) prefix 제거 적용
        final_lookup: Dict[str, str] = {}  # 소문자 → 표준명
        
        for intermediate_name, merged_name in merged_names.items():
            # suffix 제거
            result = self._remove_suffix(merged_name)
            # prefix 제거
            result = self._remove_prefix(result)
            
            if result:
                # 소문자로 키 저장 (case-insensitive 매칭용)
                lower_key = result.lower()
                if lower_key not in final_lookup:
                    final_lookup[lower_key] = result
        
        logger.info(f"정규화 완료: {len(original_names)} → {len(final_lookup)}개 고유 기업")
        
        return final_lookup
    
    def get_stage_statistics(
        self, membership_df: pd.DataFrame,
        company_column: str = "Company"
    ) -> pd.DataFrame:
        """정규화 단계별 고유 기업 수 변화 통계.
        
        각 정규화 단계를 적용할 때마다 고유 기업 수가 어떻게 변하는지 추적한다.
        요구사항의 "단조 감소" 속성 검증에 사용한다.
        
        Args:
            membership_df: ETSI 멤버십 원본 DataFrame
            company_column: 기업명 컬럼명 (기본: "Company")
            
        Returns:
            DataFrame with columns: stage, unique_companies, reduction
            
        Example:
            >>> stats = normalizer.get_stage_statistics(membership_df)
            >>> print(stats)
               stage            unique_companies  reduction
            0  original         789              -
            1  unique_members   787              -2
            2  stopwords        737              -50
            ...
        """
        if membership_df.empty:
            logger.warning("멤버십 DataFrame이 비어있습니다.")
            return pd.DataFrame(columns=["stage", "unique_companies", "reduction"])
        
        if company_column not in membership_df.columns:
            raise ValueError(f"컬럼 '{company_column}'이 DataFrame에 없습니다.")
        
        # 원본 기업명 추출
        original_names = membership_df[company_column].dropna().tolist()
        
        # 통계 데이터 수집
        stats: List[Dict] = []
        
        # 0. 원본 (중복 포함)
        stats.append({
            "stage": "original",
            "unique_companies": len(original_names),
            "reduction": 0,
        })
        
        # 1. 중복 제거
        current_names = list(set([n.strip() for n in original_names if n]))
        stats.append({
            "stage": "unique_members",
            "unique_companies": len(current_names),
            "reduction": stats[-1]["unique_companies"] - len(current_names),
        })
        
        # 각 단계별 고유 기업 수 계산
        stage_sequence = [
            ("stopwords", self._remove_stopwords),
            ("countries", self._remove_countries),
            ("removes", self._remove_specific),
            ("replaces", self._apply_replaces),
            ("brackets", self._remove_brackets),
        ]
        
        for stage_name, stage_func in stage_sequence:
            # 해당 단계 적용
            current_names = [stage_func(name) for name in current_names]
            # 빈 문자열 제거 및 중복 제거
            current_names = list(set([n for n in current_names if n.strip()]))
            
            stats.append({
                "stage": stage_name,
                "unique_companies": len(current_names),
                "reduction": stats[-1]["unique_companies"] - len(current_names),
            })
        
        # f) startswith 통합
        sorted_names = sorted(current_names)
        merged_set = set()
        for name in sorted_names:
            if name in self.config.startswith_exceptions:
                merged_set.add(name)
                continue
            
            found_prefix = None
            for existing_name in sorted(merged_set):
                if (name.startswith(existing_name) and 
                    existing_name not in self.config.startswith_exceptions and
                    name != existing_name):
                    found_prefix = existing_name
                    break
            
            if found_prefix:
                # 통합됨 - 추가하지 않음
                pass
            else:
                merged_set.add(name)
        
        current_names = list(merged_set)
        stats.append({
            "stage": "startswith",
            "unique_companies": len(current_names),
            "reduction": stats[-1]["unique_companies"] - len(current_names),
        })
        
        # g) suffix 제거
        current_names = [self._remove_suffix(name) for name in current_names]
        current_names = list(set([n for n in current_names if n.strip()]))
        stats.append({
            "stage": "suffix",
            "unique_companies": len(current_names),
            "reduction": stats[-1]["unique_companies"] - len(current_names),
        })
        
        # h) prefix 제거
        current_names = [self._remove_prefix(name) for name in current_names]
        current_names = list(set([n for n in current_names if n.strip()]))
        stats.append({
            "stage": "prefix",
            "unique_companies": len(current_names),
            "reduction": stats[-1]["unique_companies"] - len(current_names),
        })
        
        # DataFrame 생성
        stats_df = pd.DataFrame(stats)
        
        logger.info_with_details(
            f"정규화 단계별 통계 산출 완료: {len(stats)}개 단계",
            stage="membership_normalizer",
            details=stats,
        )
        
        return stats_df
    
    @classmethod
    def from_config(cls, config_dict: Dict) -> "MembershipNormalizer":
        """설정 딕셔너리로부터 MembershipNormalizer 생성.
        
        Args:
            config_dict: membership_normalization 설정 딕셔너리
            
        Returns:
            MembershipNormalizer 인스턴스
        """
        norm_config = NormalizationConfig.from_dict(config_dict)
        return cls(norm_config)


# =============================================================================
# ExtractionStats dataclass & MembershipExtractor 클래스 (Task 7.5)
# =============================================================================

import hashlib
from pathlib import Path
from typing import Union


@dataclass
class ExtractionStats:
    """기업 추출 통계.
    
    MembershipExtractor.process()가 반환하는 추출/분리 전후 통계 정보.
    요구사항 4.8: 추출/분리 전후 레코드 수 변화를 로그에 기록
    
    Attributes:
        total_sources: 원본 Source 수 (고유 Source 문자열 수)
        matched_sources: 기업 추출 성공한 Source 수 (1개 이상 추출)
        unmatched_sources: 기업 추출 실패한 Source 수 (0개 추출)
        total_companies_extracted: 추출된 총 기업 수 (중복 포함)
        unique_companies: 추출된 고유 기업 수
        records_before_explode: explode 전 레코드 수 (원본 DataFrame 행 수)
        records_after_explode: explode 후 레코드 수 (분리된 DataFrame 행 수)
    
    Example:
        >>> stats = ExtractionStats(
        ...     total_sources=1000,
        ...     matched_sources=950,
        ...     unmatched_sources=50,
        ...     total_companies_extracted=2500,
        ...     unique_companies=400,
        ...     records_before_explode=1000,
        ...     records_after_explode=2500
        ... )
    """
    total_sources: int
    matched_sources: int
    unmatched_sources: int
    total_companies_extracted: int
    unique_companies: int
    records_before_explode: int
    records_after_explode: int
    
    def to_dict(self) -> Dict:
        """딕셔너리로 변환."""
        return {
            "total_sources": self.total_sources,
            "matched_sources": self.matched_sources,
            "unmatched_sources": self.unmatched_sources,
            "total_companies_extracted": self.total_companies_extracted,
            "unique_companies": self.unique_companies,
            "records_before_explode": self.records_before_explode,
            "records_after_explode": self.records_after_explode,
        }
    
    def __str__(self) -> str:
        """사람이 읽기 쉬운 문자열 표현."""
        return (
            f"ExtractionStats("
            f"sources={self.total_sources}, "
            f"matched={self.matched_sources}, "
            f"unmatched={self.unmatched_sources}, "
            f"companies={self.total_companies_extracted}, "
            f"unique={self.unique_companies}, "
            f"explode: {self.records_before_explode} → {self.records_after_explode})"
        )


class MembershipExtractor:
    """Source 문자열에서 ETSI 멤버십 기업명을 직접 추출.
    
    SourceCleaner로 Source를 정제한 후, MembershipNormalizer로 정규화된
    멤버십 기업명을 직접 탐색하여 추출한다.
    
    요구사항:
        - 4.1: Source 문자열에서 ETSI 멤버십 기업명을 직접 탐색하여 추출
        - 4.4: 대소문자 무시 (case-insensitive) 탐색
        - 4.5: 수작업 매핑 파일의 alias를 멤버십 목록에 포함
        - 4.6: 추출된 기업이 0개인 경우 unmatched_sources.csv에 기록
        - 4.7: 추출된 기업명 목록을 개별 행으로 분리(explode)
        - 4.8: 추출/분리 전후 레코드 수 변화를 로그에 기록
        - 4.9: 매핑 결과를 캐시로 저장, 입력 Source 목록 해시가 변경될 때 캐시 무효화
    
    Attributes:
        source_cleaner: Source 문자열 정제기 (SourceCleaner)
        normalizer: 멤버십 기업명 정규화기 (MembershipNormalizer)
        _lookup_table: 정규화된 기업명 검색 테이블 (소문자 키 → 표준 기업명)
        _lookup_keys_sorted: 검색 테이블 키 목록 (길이 내림차순 정렬, 긴 매치 우선)
        _unmatched_sources: 미매칭 Source 목록
        _cache_manager: 매핑 결과 캐시 관리자 (Optional)
    
    Example:
        >>> # 멤버십 DataFrame과 설정 준비
        >>> membership_df = pd.read_excel("data/reference/etsi_membership.xlsx")
        >>> source_config = SourceCleaningConfig(
        ...     special_replacements={"CMCC": "China Mobile"},
        ...     remove_characters=["[", "]", "."],
        ...     add_word_boundary_spaces=True
        ... )
        >>> norm_config = NormalizationConfig.from_dict(yaml_config)
        >>> 
        >>> # Extractor 생성
        >>> extractor = MembershipExtractor(
        ...     membership_df=membership_df,
        ...     source_cleaning_config=source_config,
        ...     normalization_config=norm_config
        ... )
        >>> 
        >>> # 단일 Source에서 기업명 추출
        >>> companies = extractor.extract_companies("Samsung, Nokia, Chair")
        >>> print(companies)
        ['Samsung', 'Nokia']
    """
    
    def __init__(
        self, 
        membership_df: pd.DataFrame,
        source_cleaning_config: SourceCleaningConfig,
        normalization_config: NormalizationConfig,
        manual_mapping: Optional[pd.DataFrame] = None,
        cache_manager: Optional["CacheManager"] = None,  # type: ignore
    ) -> None:
        """MembershipExtractor 초기화.
        
        Args:
            membership_df: ETSI 멤버십 DataFrame (Company 컬럼 필수)
            source_cleaning_config: Source 문자열 정제 설정
            normalization_config: 멤버십 정규화 설정
            manual_mapping: 수작업 매핑 DataFrame (optional)
                - alias 컬럼: 별칭 (검색 키)
                - standard_name 컬럼: 표준 기업명 (결과 값)
            cache_manager: 매핑 결과 캐시 관리자 (optional, 요구사항 4.9)
        
        Raises:
            ValueError: 멤버십 DataFrame에 필수 컬럼이 없는 경우
        """
        # Source 정제기 생성
        self.source_cleaner = SourceCleaner(source_cleaning_config)
        
        # 멤버십 정규화기 생성
        self.normalizer = MembershipNormalizer(normalization_config)
        
        # 캐시 매니저 (Optional)
        self._cache_manager = cache_manager
        
        # 미매칭 Source 목록
        self._unmatched_sources: List[str] = []
        
        # 검색 테이블 구축
        self._lookup_table: Dict[str, str] = {}
        self._lookup_keys_sorted: List[str] = []
        self._build_lookup_table(membership_df, manual_mapping)
        
        logger.info_with_details(
            f"MembershipExtractor 초기화 완료: "
            f"{len(self._lookup_table)}개 검색 항목, "
            f"cache_manager={'사용' if cache_manager else '미사용'}",
            stage="membership_extractor",
            details={
                "lookup_table_size": len(self._lookup_table),
                "has_manual_mapping": manual_mapping is not None,
                "has_cache_manager": cache_manager is not None,
            },
        )
    
    def _compute_source_hash(self, sources: List[str]) -> str:
        """입력 Source 목록의 해시 계산.
        
        요구사항 4.9: 입력 Source 목록의 해시가 변경될 때 캐시 무효화
        Source 목록을 정렬 후 결합하여 SHA-256 해시를 생성한다.
        
        Args:
            sources: Source 문자열 목록
            
        Returns:
            SHA-256 해시 문자열 (16진수)
            
        Example:
            >>> sources = ["Samsung, Nokia", "Huawei, Chair"]
            >>> hash_key = extractor._compute_source_hash(sources)
            >>> print(hash_key[:16])
            "a1b2c3d4e5f6g7h8"
        """
        if not sources:
            return hashlib.sha256(b"").hexdigest()
        
        # 정렬하여 순서에 무관하게 동일 해시 생성
        sorted_sources = sorted(sources)
        combined = "\n".join(sorted_sources)
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()
    
    def _build_lookup_table(
        self, 
        membership_df: pd.DataFrame, 
        manual_mapping: Optional[pd.DataFrame] = None,
        company_column: str = "Company"
    ) -> None:
        """멤버십 + 수작업 alias 검색 테이블 구축.
        
        1. MembershipNormalizer.build_lookup_table()로 멤버십 기업명 정규화
        2. 원본 기업명도 검색 테이블에 추가 (소문자 키 → 정규화된 표준명)
        3. 수작업 매핑의 alias를 테이블에 추가
        4. 검색 키를 길이 내림차순으로 정렬 (긴 매치 우선)
        
        Args:
            membership_df: ETSI 멤버십 DataFrame
            manual_mapping: 수작업 매핑 DataFrame (optional)
                - alias 컬럼: 별칭 (검색 키)
                - standard_name 컬럼: 표준 기업명 (결과 값)
            company_column: 멤버십 기업명 컬럼명 (기본: "Company")
        """
        # 1. 멤버십 기업명 정규화 및 검색 테이블 구축
        self._lookup_table = self.normalizer.build_lookup_table(
            membership_df, company_column
        )
        
        # 1-1. 원본 기업명도 검색 테이블에 추가 (대소문자 무시)
        # Source에 "Nokia Corporation"이라고 적혀 있어도 매칭되도록
        if company_column in membership_df.columns:
            original_names = membership_df[company_column].dropna().unique().tolist()
            for original_name in original_names:
                original_name = str(original_name).strip()
                if not original_name:
                    continue
                
                # 정규화된 기업명 구하기
                normalized = self.normalizer.normalize(original_name)
                if not normalized:
                    continue
                
                # 원본 기업명을 소문자 키로 등록 (정규화된 이름을 값으로)
                # 이미 존재하는 키는 덮어쓰지 않음 (정규화된 결과 우선)
                lower_original = original_name.lower()
                if lower_original not in self._lookup_table:
                    self._lookup_table[lower_original] = normalized
                
                # 정규화 결과도 키로 등록 (이미 build_lookup_table에서 됐지만 확인)
                lower_normalized = normalized.lower()
                if lower_normalized not in self._lookup_table:
                    self._lookup_table[lower_normalized] = normalized
        
        # 2. 수작업 매핑의 alias 추가 (요구사항 4.5)
        if manual_mapping is not None and not manual_mapping.empty:
            alias_column = "alias"
            standard_column = "standard_name"
            
            # 컬럼 존재 확인
            if alias_column not in manual_mapping.columns:
                logger.warning(
                    f"수작업 매핑에 '{alias_column}' 컬럼이 없습니다. "
                    "alias 추가를 건너뜁니다."
                )
            elif standard_column not in manual_mapping.columns:
                logger.warning(
                    f"수작업 매핑에 '{standard_column}' 컬럼이 없습니다. "
                    "alias 추가를 건너뜁니다."
                )
            else:
                # alias → standard_name 매핑 추가
                added_count = 0
                for _, row in manual_mapping.iterrows():
                    alias = row[alias_column]
                    standard_name = row[standard_column]
                    
                    if pd.isna(alias) or pd.isna(standard_name):
                        continue
                    
                    alias = str(alias).strip()
                    standard_name = str(standard_name).strip()
                    
                    if not alias or not standard_name:
                        continue
                    
                    # 소문자 키로 저장 (case-insensitive)
                    lower_key = alias.lower()
                    if lower_key not in self._lookup_table:
                        self._lookup_table[lower_key] = standard_name
                        added_count += 1
                
                logger.info(
                    f"수작업 매핑에서 {added_count}개 alias 추가됨 "
                    f"(총 {len(self._lookup_table)}개 검색 항목)"
                )
        
        # 3. 검색 키를 길이 내림차순으로 정렬 (긴 매치 우선)
        # "Samsung Electronics"가 "Samsung"보다 먼저 매칭되도록
        self._lookup_keys_sorted = sorted(
            self._lookup_table.keys(),
            key=len,
            reverse=True
        )
        
        logger.info_with_details(
            f"검색 테이블 구축 완료: {len(self._lookup_table)}개 항목",
            stage="membership_extractor",
            details={
                "total_entries": len(self._lookup_table),
                "sample_entries": dict(list(self._lookup_table.items())[:5]),
            },
        )
    
    def extract_companies(self, source: str) -> List[str]:
        """단일 Source 문자열에서 기업명 리스트 추출.
        
        처리 흐름:
        1. Source 정제 (SourceCleaner) - CMCC→China Mobile, 대괄호/마침표 제거
        2. 정규화된 멤버십 기업명으로 직접 탐색 (case-insensitive)
        3. 매칭된 기업명 리스트 반환 (중복 제거)
        
        Args:
            source: 원본 Source 문자열
                예: "Samsung Electronics Co., Ltd., Nokia, Chair"
            
        Returns:
            추출된 기업명 리스트 (중복 제거, 순서 유지)
                예: ["Samsung Electronics", "Nokia"]
            - Chair는 멤버십에 없으므로 자동 제외
            - Co., Ltd. 잘못 분리 문제 원천 해결
        
        Note:
            - 빈 문자열 또는 None 입력 시 빈 리스트 반환
            - 긴 기업명이 먼저 매칭됨 (부분 문자열 중복 방지)
            - 대소문자 무시 (요구사항 4.4)
        """
        if not source or not isinstance(source, str):
            return []
        
        # 1. Source 정제
        cleaned_source = self.source_cleaner.clean(source)
        
        if not cleaned_source.strip():
            return []
        
        # 소문자로 변환 (case-insensitive 매칭용)
        cleaned_source_lower = cleaned_source.lower()
        
        # 2. 정규화된 멤버십 기업명으로 직접 탐색
        extracted: List[str] = []
        matched_positions: List[Tuple[int, int]] = []  # (start, end) 튜플 리스트
        
        # 긴 기업명부터 매칭 (부분 문자열 중복 방지)
        for key in self._lookup_keys_sorted:
            # 키가 Source에 존재하는지 확인
            start = 0
            while True:
                pos = cleaned_source_lower.find(key, start)
                if pos == -1:
                    break
                
                end = pos + len(key)
                
                # 이미 매칭된 영역과 겹치는지 확인
                overlaps = False
                for matched_start, matched_end in matched_positions:
                    if not (end <= matched_start or pos >= matched_end):
                        # 겹침
                        overlaps = True
                        break
                
                if not overlaps:
                    # 매칭 위치 기록
                    matched_positions.append((pos, end))
                    
                    # 표준 기업명 추가 (중복 방지)
                    standard_name = self._lookup_table[key]
                    if standard_name not in extracted:
                        extracted.append(standard_name)
                
                # 다음 위치에서 계속 검색
                start = pos + 1
        
        return extracted
    
    def process(
        self, 
        df: pd.DataFrame, 
        source_column: str = "Source"
    ) -> Tuple[pd.DataFrame, ExtractionStats]:
        """전체 DataFrame 처리 (추출 + explode).
        
        요구사항:
        - 4.6: 추출된 기업이 0개인 경우 미매칭 목록에 기록
        - 4.7: 추출된 기업명 목록을 개별 행으로 분리(explode)
        - 4.8: 추출/분리 전후 레코드 수 변화를 로그에 기록
        - 4.9: 캐시 사용 시 Source 해시 기반 캐시 조회/저장
        
        Args:
            df: 원본 DataFrame (Source 컬럼 필수)
            source_column: Source 컬럼명 (기본: "Source")
            
        Returns:
            Tuple[결과 DataFrame, ExtractionStats]
            - 결과 DataFrame: 기업명별로 분리된 DataFrame
              - Company 컬럼 추가: 추출된 표준 기업명
            - ExtractionStats: 추출 통계 정보
        
        Raises:
            ValueError: Source 컬럼이 DataFrame에 없는 경우
        """
        if source_column not in df.columns:
            raise ValueError(f"컬럼 '{source_column}'이 DataFrame에 없습니다.")
        
        # 원본 레코드 수 기록
        records_before = len(df)
        
        # 고유 Source 목록 추출
        sources = df[source_column].dropna().unique().tolist()
        
        # 캐시 확인 (요구사항 4.9)
        cache_key = None
        if self._cache_manager is not None:
            cache_key = f"membership_extraction_{self._compute_source_hash(sources)}"
            cached_result = self._cache_manager.load(cache_key)
            if cached_result is not None:
                logger.info(f"캐시에서 매핑 결과 로드: {cache_key[:16]}...")
                # 캐시된 매핑 사용
                source_to_companies = cached_result.get("source_to_companies", {})
                self._unmatched_sources = cached_result.get("unmatched_sources", [])
                
                # DataFrame에 적용
                df = df.copy()
                df["_extracted_companies"] = df[source_column].apply(
                    lambda s: source_to_companies.get(s, []) if pd.notna(s) else []
                )
                
                # explode
                df = df.explode("_extracted_companies")
                df = df.rename(columns={"_extracted_companies": "Company"})
                df = df[df["Company"].notna() & (df["Company"] != "")]
                df = df.reset_index(drop=True)
                
                # 통계 계산
                stats = self._compute_stats(
                    sources, source_to_companies, records_before, len(df)
                )
                
                logger.info_with_details(
                    f"캐시 사용 완료: {stats}",
                    stage="membership_extractor",
                    details=stats.to_dict(),
                )
                
                return df, stats
        
        # 미매칭 목록 초기화
        self._unmatched_sources = []
        
        # Source → 기업명 리스트 매핑 생성
        source_to_companies: Dict[str, List[str]] = {}
        
        for source in sources:
            if pd.isna(source):
                continue
            
            companies = self.extract_companies(source)
            source_to_companies[source] = companies
            
            # 미매칭 Source 기록 (요구사항 4.6)
            if not companies:
                self._unmatched_sources.append(source)
        
        # 캐시 저장 (요구사항 4.9)
        if self._cache_manager is not None and cache_key is not None:
            cache_data = {
                "source_to_companies": source_to_companies,
                "unmatched_sources": self._unmatched_sources,
            }
            self._cache_manager.save(cache_key, cache_data)
            logger.info(f"매핑 결과 캐시 저장: {cache_key[:16]}...")
        
        # DataFrame에 추출된 기업명 리스트 추가
        df = df.copy()
        df["_extracted_companies"] = df[source_column].apply(
            lambda s: source_to_companies.get(s, []) if pd.notna(s) else []
        )
        
        # explode - 기업명 리스트를 개별 행으로 분리 (요구사항 4.7)
        df = df.explode("_extracted_companies")
        df = df.rename(columns={"_extracted_companies": "Company"})
        
        # 빈 기업명 제거 (미매칭 Source의 경우)
        df = df[df["Company"].notna() & (df["Company"] != "")]
        df = df.reset_index(drop=True)
        
        # 통계 계산 (요구사항 4.8)
        records_after = len(df)
        stats = self._compute_stats(
            sources, source_to_companies, records_before, records_after
        )
        
        # 로그 기록 (요구사항 4.8)
        logger.info_with_details(
            f"기업 추출 완료: {stats}",
            stage="membership_extractor",
            details=stats.to_dict(),
        )
        
        if self._unmatched_sources:
            logger.warning(
                f"미매칭 Source {len(self._unmatched_sources)}개 발생 "
                f"(요구사항 4.6: unmatched_sources.csv에 저장 필요)"
            )
        
        return df, stats
    
    def _compute_stats(
        self,
        sources: List[str],
        source_to_companies: Dict[str, List[str]],
        records_before: int,
        records_after: int,
    ) -> ExtractionStats:
        """추출 통계 계산.
        
        Args:
            sources: 고유 Source 목록
            source_to_companies: Source → 기업명 리스트 매핑
            records_before: explode 전 레코드 수
            records_after: explode 후 레코드 수
            
        Returns:
            ExtractionStats 객체
        """
        total_sources = len(sources)
        matched_sources = sum(1 for s in sources if source_to_companies.get(s))
        unmatched_sources = total_sources - matched_sources
        
        # 추출된 총 기업 수 (중복 포함)
        all_companies = []
        for companies in source_to_companies.values():
            all_companies.extend(companies)
        total_companies_extracted = len(all_companies)
        unique_companies = len(set(all_companies))
        
        return ExtractionStats(
            total_sources=total_sources,
            matched_sources=matched_sources,
            unmatched_sources=unmatched_sources,
            total_companies_extracted=total_companies_extracted,
            unique_companies=unique_companies,
            records_before_explode=records_before,
            records_after_explode=records_after,
        )
    
    def get_unmatched_sources(self) -> List[str]:
        """미매칭 Source 목록 반환.
        
        process() 호출 후 추출된 기업이 0개인 Source 목록을 반환한다.
        
        Returns:
            미매칭 Source 문자열 리스트
            
        Note:
            process()를 먼저 호출해야 미매칭 목록이 채워집니다.
        """
        return self._unmatched_sources.copy()
    
    def save_unmatched_sources(self, output_path: Union[str, Path]) -> None:
        """미매칭 Source를 CSV로 저장.
        
        요구사항 4.6: 추출된 기업이 0개인 Source를 
        data/reference/unmatched_sources.csv에 기록
        
        Args:
            output_path: 출력 CSV 파일 경로
                기본: data/reference/unmatched_sources.csv
        
        Note:
            - process()를 먼저 호출해야 미매칭 목록이 채워집니다.
            - 기존 파일이 있으면 덮어씁니다.
        """
        output_path = Path(output_path)
        
        # 디렉토리 생성
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # DataFrame 생성 및 저장
        unmatched_df = pd.DataFrame({
            "source": self._unmatched_sources
        })
        
        unmatched_df.to_csv(output_path, index=False, encoding="utf-8")
        
        logger.info(
            f"미매칭 Source {len(self._unmatched_sources)}개를 "
            f"'{output_path}'에 저장했습니다."
        )
    
    def get_lookup_table(self) -> Dict[str, str]:
        """검색 테이블 반환.
        
        디버깅 및 검증 목적으로 내부 검색 테이블을 반환한다.
        
        Returns:
            Dict[정규화된_기업명_소문자 → 표준_기업명]
        """
        return self._lookup_table.copy()
    
    @classmethod
    def from_config(
        cls,
        membership_df: pd.DataFrame,
        config_dict: Dict,
        manual_mapping: Optional[pd.DataFrame] = None,
        cache_manager: Optional["CacheManager"] = None,  # type: ignore
    ) -> "MembershipExtractor":
        """설정 딕셔너리로부터 MembershipExtractor 생성.
        
        config_dict는 다음 키를 포함해야 한다:
        - source_cleaning: SourceCleaningConfig 설정
        - membership_normalization: NormalizationConfig 설정
        
        Args:
            membership_df: ETSI 멤버십 DataFrame
            config_dict: 설정 딕셔너리 (preprocessing.yaml 내용)
            manual_mapping: 수작업 매핑 DataFrame (optional)
            cache_manager: 매핑 결과 캐시 관리자 (optional)
            
        Returns:
            MembershipExtractor 인스턴스
        """
        source_cleaning_config = SourceCleaningConfig.from_dict(
            config_dict.get("source_cleaning", {})
        )
        normalization_config = NormalizationConfig.from_dict(
            config_dict.get("membership_normalization", {})
        )
        
        return cls(
            membership_df=membership_df,
            source_cleaning_config=source_cleaning_config,
            normalization_config=normalization_config,
            manual_mapping=manual_mapping,
            cache_manager=cache_manager,
        )
