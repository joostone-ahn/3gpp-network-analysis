"""
Pipeline Scheduler (Stage 9)

APScheduler 기반 파이프라인 자동 스케줄링 모듈.

Requirements:
- 14.1: config/pipeline.yaml의 schedule 설정에 정의된 실행 주기에 따라 파이프라인 자동 실행
- 14.2: schedule 설정이 유효하지 않거나 누락된 경우 명확한 오류 메시지 출력
- 14.3: 파이프라인 실행 중 예외 발생 시 로깅 후 다음 예약 실행 유지
- 14.4: 정상 완료 시 완료 시각과 실행된 단계 목록 로그 기록
"""

from __future__ import annotations

import sys
import signal
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from src.utils.config_loader import (
    ConfigLoader,
    PipelineConfig,
    get_config_loader,
)
from src.utils.logger import get_logger


# =============================================================================
# 상수 정의
# =============================================================================

logger = get_logger(__name__)


# =============================================================================
# 데이터 클래스 정의
# =============================================================================


class PipelineStage(Enum):
    """파이프라인 스테이지 정의."""
    
    PARSE = auto()       # Stage 1.5: xlsx 파싱
    PREPROCESS = auto()  # Stage 2-5: 전처리 (Title Filter, Membership Extraction, WI Explode, Temporal Enrich)
    BUILD = auto()       # Stage 6: 네트워크 구성 (Company/WI Network)
    ANALYZE = auto()     # Stage 7: 네트워크 분석 (Statistics, Centrality, Community, Advanced)


@dataclass
class StageResult:
    """파이프라인 스테이지 실행 결과.
    
    Attributes:
        stage: 실행된 스테이지
        success: 성공 여부
        start_time: 시작 시각
        end_time: 종료 시각
        message: 결과 메시지
        records_processed: 처리된 레코드 수 (해당되는 경우)
        error: 오류 메시지 (실패 시)
    """
    stage: PipelineStage
    success: bool
    start_time: datetime
    end_time: datetime
    message: str = ""
    records_processed: Optional[int] = None
    error: Optional[str] = None
    
    @property
    def duration_seconds(self) -> float:
        """실행 시간(초)."""
        return (self.end_time - self.start_time).total_seconds()


@dataclass
class PipelineResult:
    """전체 파이프라인 실행 결과.
    
    Attributes:
        success: 전체 파이프라인 성공 여부
        start_time: 시작 시각
        end_time: 종료 시각
        stage_results: 각 스테이지별 실행 결과
        error: 오류 메시지 (실패 시)
    """
    success: bool
    start_time: datetime
    end_time: datetime
    stage_results: List[StageResult] = field(default_factory=list)
    error: Optional[str] = None
    
    @property
    def duration_seconds(self) -> float:
        """총 실행 시간(초)."""
        return (self.end_time - self.start_time).total_seconds()
    
    @property
    def completed_stages(self) -> List[PipelineStage]:
        """성공적으로 완료된 스테이지 목록."""
        return [r.stage for r in self.stage_results if r.success]
    
    @property
    def failed_stages(self) -> List[PipelineStage]:
        """실패한 스테이지 목록."""
        return [r.stage for r in self.stage_results if not r.success]


# =============================================================================
# PipelineScheduler 클래스
# =============================================================================


class PipelineScheduler:
    """APScheduler 기반 파이프라인 자동 스케줄링 클래스.
    
    파이프라인의 각 스테이지(parse, preprocess, build, analyze)를
    개별적으로 또는 전체적으로 실행하고, cron 스케줄에 따라
    자동으로 실행할 수 있다.
    
    Attributes:
        config: 파이프라인 설정
        scheduler: APScheduler 인스턴스
        
    Usage:
        >>> scheduler = PipelineScheduler()
        >>> # 전체 파이프라인 실행
        >>> result = scheduler.run_pipeline()
        >>> # 특정 스테이지만 실행
        >>> result = scheduler.run_stage(PipelineStage.PARSE)
        >>> # 자동 스케줄링 시작
        >>> scheduler.start()
    """
    
    # 스테이지 실행 순서
    STAGE_ORDER = [
        PipelineStage.PARSE,
        PipelineStage.PREPROCESS,
        PipelineStage.BUILD,
        PipelineStage.ANALYZE,
    ]
    
    # 스테이지 의존성 (각 스테이지가 실행되기 전에 완료되어야 하는 스테이지)
    STAGE_DEPENDENCIES: Dict[PipelineStage, List[PipelineStage]] = {
        PipelineStage.PARSE: [],
        PipelineStage.PREPROCESS: [PipelineStage.PARSE],
        PipelineStage.BUILD: [PipelineStage.PREPROCESS],
        PipelineStage.ANALYZE: [PipelineStage.BUILD],
    }
    
    def __init__(
        self,
        config: Optional[PipelineConfig] = None,
        config_loader: Optional[ConfigLoader] = None,
    ):
        """PipelineScheduler 초기화.
        
        Args:
            config: 파이프라인 설정. None이면 config/pipeline.yaml에서 로드.
            config_loader: 설정 로더. None이면 기본 로더 사용.
        """
        self._config_loader = config_loader or get_config_loader()
        self._config = config or self._load_config()
        self._scheduler: Optional[BlockingScheduler] = None
        self._running = False
        
        # 스테이지 실행 함수 매핑
        self._stage_runners: Dict[PipelineStage, Callable[[], StageResult]] = {
            PipelineStage.PARSE: self._run_parse_stage,
            PipelineStage.PREPROCESS: self._run_preprocess_stage,
            PipelineStage.BUILD: self._run_build_stage,
            PipelineStage.ANALYZE: self._run_analyze_stage,
        }
        
        logger.info(
            "PipelineScheduler 초기화 완료",
            extra={"schedule": self._config.schedule}
        )
    
    @property
    def config(self) -> PipelineConfig:
        """파이프라인 설정."""
        return self._config
    
    @property
    def is_running(self) -> bool:
        """스케줄러 실행 중 여부."""
        return self._running
    
    def _load_config(self) -> PipelineConfig:
        """파이프라인 설정 로드.
        
        Returns:
            PipelineConfig 객체
            
        Raises:
            ValueError: 설정이 유효하지 않은 경우
        """
        try:
            config = self._config_loader.load_pipeline_config()
            self._validate_schedule(config.schedule)
            return config
        except Exception as e:
            logger.error(
                "파이프라인 설정 로드 실패",
                extra={"error": str(e)}
            )
            raise ValueError(f"파이프라인 설정 로드 실패: {e}")
    
    def _validate_schedule(self, schedule: str) -> None:
        """cron 스케줄 표현식 유효성 검증.
        
        Args:
            schedule: cron 형식 스케줄 표현식
            
        Raises:
            ValueError: 스케줄 형식이 유효하지 않은 경우
        """
        if not schedule or not isinstance(schedule, str):
            raise ValueError("스케줄 설정이 누락되었거나 유효하지 않습니다.")
        
        try:
            # CronTrigger로 파싱하여 유효성 검증
            parts = schedule.split()
            if len(parts) != 5:
                raise ValueError(
                    f"cron 표현식은 5개의 필드(분 시 일 월 요일)가 필요합니다. "
                    f"현재: {len(parts)}개"
                )
            
            CronTrigger.from_crontab(schedule)
            logger.debug(
                "스케줄 표현식 검증 성공",
                extra={"schedule": schedule}
            )
        except Exception as e:
            raise ValueError(f"유효하지 않은 cron 스케줄 표현식: {schedule}. 오류: {e}")
    
    # =========================================================================
    # 스테이지 실행 메서드
    # =========================================================================
    
    def _run_parse_stage(self) -> StageResult:
        """Stage 1.5: Parser 스테이지 실행.
        
        xlsx 파일을 표준화된 DataFrame으로 파싱하고 Parquet으로 저장.
        
        Returns:
            StageResult 객체
        """
        start_time = datetime.now()
        stage = PipelineStage.PARSE
        
        try:
            from src.parser import TDocParser, save_parsed_tdocs
            from src.utils.config_loader import get_config_loader
            
            logger.info("Parse 스테이지 시작")
            
            # 설정 로드
            config_loader = get_config_loader()
            preprocessing_config = config_loader.load_preprocessing_config()
            
            # Parser 실행
            parser = TDocParser(config=preprocessing_config)
            
            # 기본 raw 데이터 경로
            raw_dir = Path("data/raw")
            if not raw_dir.exists():
                logger.warning(f"원본 데이터 디렉토리가 존재하지 않습니다: {raw_dir}")
                return StageResult(
                    stage=stage,
                    success=False,
                    start_time=start_time,
                    end_time=datetime.now(),
                    message="원본 데이터 디렉토리가 존재하지 않습니다",
                    error=f"디렉토리 없음: {raw_dir}"
                )
            
            # 모든 파일 파싱
            df, stats = parser.parse_all(raw_dir)
            
            # Parquet 저장
            output_path = Path("data/interim/parsed_tdocs.parquet")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            save_parsed_tdocs(df, output_path)
            
            end_time = datetime.now()
            message = (
                f"파싱 완료: {stats.total_files}개 파일, "
                f"{stats.total_records}개 레코드"
            )
            
            logger.info(
                message,
                extra={
                    "files_processed": stats.total_files,
                    "records_parsed": stats.total_records,
                    "duration_seconds": (end_time - start_time).total_seconds()
                }
            )
            
            return StageResult(
                stage=stage,
                success=True,
                start_time=start_time,
                end_time=end_time,
                message=message,
                records_processed=stats.total_records
            )
            
        except Exception as e:
            end_time = datetime.now()
            logger.error(
                "Parse 스테이지 실패",
                extra={"error": str(e)},
                exc_info=True
            )
            return StageResult(
                stage=stage,
                success=False,
                start_time=start_time,
                end_time=end_time,
                message="파싱 실패",
                error=str(e)
            )
    
    def _run_preprocess_stage(self) -> StageResult:
        """Stage 2-5: Preprocessor 스테이지 실행.
        
        Title Filter → Membership Extraction → WI Explode → Temporal Enrich
        
        Returns:
            StageResult 객체
        """
        start_time = datetime.now()
        stage = PipelineStage.PREPROCESS
        
        try:
            import pandas as pd
            from src.parser import load_parsed_tdocs
            from src.preprocessor import (
                TitleFilter,
                WIExploder,
                TemporalEnricher,
            )
            from src.utils.config_loader import get_config_loader
            
            logger.info("Preprocess 스테이지 시작")
            
            # 설정 로드
            config_loader = get_config_loader()
            preprocessing_config = config_loader.load_preprocessing_config()
            
            # 파싱된 데이터 로드
            input_path = Path("data/interim/parsed_tdocs.parquet")
            if not input_path.exists():
                return StageResult(
                    stage=stage,
                    success=False,
                    start_time=start_time,
                    end_time=datetime.now(),
                    message="파싱된 데이터 파일이 존재하지 않습니다",
                    error=f"파일 없음: {input_path}"
                )
            
            df = load_parsed_tdocs(input_path)
            initial_count = len(df)
            logger.info(f"입력 데이터 로드 완료: {initial_count}개 레코드")
            
            # Stage 2: Title Filter
            title_filter = TitleFilter(
                exclude_patterns=preprocessing_config.title_exclude_patterns
            )
            df, title_stats = title_filter.filter(df)
            logger.info(
                f"Title Filter 완료: {title_stats.records_excluded}개 제외",
                extra={"remaining_records": len(df)}
            )
            
            # Stage 3: Membership Extraction
            # 참고: MembershipExtractor가 완전히 구현되면 여기에 추가
            # 현재는 Source 컬럼을 그대로 company로 사용
            if 'Source' in df.columns:
                df['company'] = df['Source']
            
            # Stage 4: WI Explode
            wi_exploder = WIExploder(
                delimiters=preprocessing_config.wi_delimiters,
                exclude_patterns=preprocessing_config.wi_exclude_patterns
            )
            df, explode_stats = wi_exploder.explode(df)
            logger.info(
                f"WI Explode 완료: {explode_stats.records_after}개 레코드",
                extra={
                    "original_records": explode_stats.records_before,
                    "exploded_records": explode_stats.records_after
                }
            )
            
            # Stage 5: Temporal Enrichment
            temporal_enricher = TemporalEnricher(
                date_range=preprocessing_config.date_range
            )
            df, enrich_stats = temporal_enricher.enrich(df)
            logger.info(
                f"Temporal Enrich 완료: {enrich_stats.records_after}개 레코드",
                extra={
                    "records_excluded": enrich_stats.records_excluded
                }
            )
            
            # 전처리 결과 저장
            output_path = Path("data/interim/preprocessed_tdocs.parquet")
            df.to_parquet(output_path, index=False)
            
            end_time = datetime.now()
            message = (
                f"전처리 완료: {initial_count} → {len(df)}개 레코드 "
                f"({end_time - start_time})"
            )
            
            logger.info(
                message,
                extra={
                    "initial_records": initial_count,
                    "final_records": len(df),
                    "duration_seconds": (end_time - start_time).total_seconds()
                }
            )
            
            return StageResult(
                stage=stage,
                success=True,
                start_time=start_time,
                end_time=end_time,
                message=message,
                records_processed=len(df)
            )
            
        except Exception as e:
            end_time = datetime.now()
            logger.error(
                "Preprocess 스테이지 실패",
                extra={"error": str(e)},
                exc_info=True
            )
            return StageResult(
                stage=stage,
                success=False,
                start_time=start_time,
                end_time=end_time,
                message="전처리 실패",
                error=str(e)
            )
    
    def _run_build_stage(self) -> StageResult:
        """Stage 6: Network Builder 스테이지 실행.
        
        Company Network 및 WI Network Edge list 생성.
        
        Returns:
            StageResult 객체
        """
        start_time = datetime.now()
        stage = PipelineStage.BUILD
        
        try:
            import pandas as pd
            from src.network import CompanyNetworkBuilder, WINetworkBuilder
            from src.utils.config_loader import get_config_loader
            
            logger.info("Build 스테이지 시작")
            
            # 설정 로드
            config_loader = get_config_loader()
            network_config = config_loader.load_network_config()
            
            # 전처리된 데이터 로드
            input_path = Path("data/interim/preprocessed_tdocs.parquet")
            if not input_path.exists():
                return StageResult(
                    stage=stage,
                    success=False,
                    start_time=start_time,
                    end_time=datetime.now(),
                    message="전처리된 데이터 파일이 존재하지 않습니다",
                    error=f"파일 없음: {input_path}"
                )
            
            df = pd.read_parquet(input_path)
            logger.info(f"입력 데이터 로드 완료: {len(df)}개 레코드")
            
            # 출력 디렉토리 생성
            output_dir = Path("data/processed")
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Company Network 구성
            company_builder = CompanyNetworkBuilder(config=network_config)
            company_results = company_builder.build_all(df)
            
            company_network_count = len(company_results)
            logger.info(f"Company Network 생성 완료: {company_network_count}개 네트워크")
            
            # WI Network 구성
            wi_builder = WINetworkBuilder(config=network_config)
            wi_results = wi_builder.build_all(df)
            
            wi_network_count = len(wi_results)
            logger.info(f"WI Network 생성 완료: {wi_network_count}개 네트워크")
            
            end_time = datetime.now()
            total_networks = company_network_count + wi_network_count
            message = (
                f"네트워크 구성 완료: Company {company_network_count}개, "
                f"WI {wi_network_count}개 (총 {total_networks}개)"
            )
            
            logger.info(
                message,
                extra={
                    "company_networks": company_network_count,
                    "wi_networks": wi_network_count,
                    "duration_seconds": (end_time - start_time).total_seconds()
                }
            )
            
            return StageResult(
                stage=stage,
                success=True,
                start_time=start_time,
                end_time=end_time,
                message=message,
                records_processed=total_networks
            )
            
        except Exception as e:
            end_time = datetime.now()
            logger.error(
                "Build 스테이지 실패",
                extra={"error": str(e)},
                exc_info=True
            )
            return StageResult(
                stage=stage,
                success=False,
                start_time=start_time,
                end_time=end_time,
                message="네트워크 구성 실패",
                error=str(e)
            )
    
    def _run_analyze_stage(self) -> StageResult:
        """Stage 7: Network Analyzer 스테이지 실행.
        
        Statistics, Centrality, Community, Advanced 분석 실행.
        
        Returns:
            StageResult 객체
        """
        start_time = datetime.now()
        stage = PipelineStage.ANALYZE
        
        try:
            import networkx as nx
            import pandas as pd
            from pathlib import Path
            from src.analyzer import (
                NetworkStatistics,
                CentralityAnalyzer,
                CommunityDetector,
                AdvancedAnalyzer,
            )
            from src.utils.config_loader import get_config_loader
            
            logger.info("Analyze 스테이지 시작")
            
            # 설정 로드
            config_loader = get_config_loader()
            analysis_config = config_loader.load_analysis_config()
            
            # 네트워크 데이터 디렉토리
            network_dir = Path("data/processed")
            if not network_dir.exists():
                return StageResult(
                    stage=stage,
                    success=False,
                    start_time=start_time,
                    end_time=datetime.now(),
                    message="네트워크 데이터 디렉토리가 존재하지 않습니다",
                    error=f"디렉토리 없음: {network_dir}"
                )
            
            # 결과 디렉토리 생성
            results_dir = Path("data/results")
            results_dir.mkdir(parents=True, exist_ok=True)
            
            # 분석기 초기화
            stats_analyzer = NetworkStatistics()
            centrality_analyzer = CentralityAnalyzer(
                eigenvector_max_iter=analysis_config.eigenvector_max_iter
            )
            community_detector = CommunityDetector(
                random_seed=analysis_config.louvain_seed
            )
            advanced_analyzer = AdvancedAnalyzer(
                random_network_samples=analysis_config.random_network_samples
            )
            
            # Company Network 분석
            company_files = list(network_dir.glob("company_*.parquet"))
            analyzed_count = 0
            
            all_stats = []
            all_centrality = []
            all_communities = []
            
            for network_file in company_files:
                try:
                    # 네트워크 로드
                    edge_df = pd.read_parquet(network_file)
                    
                    if len(edge_df) == 0:
                        logger.debug(f"빈 네트워크 스킵: {network_file.name}")
                        continue
                    
                    # NetworkX 그래프 생성
                    G = nx.Graph()
                    for _, row in edge_df.iterrows():
                        G.add_edge(row['Source'], row['Target'], Weight=row['Weight'])
                    
                    if G.number_of_nodes() < 2:
                        logger.debug(f"노드가 부족한 네트워크 스킵: {network_file.name}")
                        continue
                    
                    # 파일명에서 메타데이터 추출
                    parts = network_file.stem.split('_')  # company_RAN_year_2020_0
                    if len(parts) >= 5:
                        tsg = parts[1]
                        time_unit = parts[2]
                        time_value = parts[3]
                        threshold = parts[4]
                    else:
                        tsg = time_unit = time_value = threshold = "unknown"
                    
                    # 커뮤니티 탐지 (modularity 포함)
                    community_result = community_detector.detect(G)
                    
                    # 기본 통계 (modularity는 커뮤니티 결과에서 재사용)
                    stats = stats_analyzer.compute(G, modularity=community_result.modularity)
                    stats_dict = {
                        'tsg': tsg,
                        'time_unit': time_unit,
                        'time_value': time_value,
                        'threshold': threshold,
                        **stats.__dict__
                    }
                    all_stats.append(stats_dict)
                    
                    # 중심성 분석
                    centrality_df = centrality_analyzer.compute_all(G)
                    centrality_df['tsg'] = tsg
                    centrality_df['time_unit'] = time_unit
                    centrality_df['time_value'] = time_value
                    centrality_df['threshold'] = threshold
                    all_centrality.append(centrality_df)
                    
                    # 커뮤니티 결과 저장
                    for node, comm_id in community_result.node_communities.items():
                        all_communities.append({
                            'tsg': tsg,
                            'time_unit': time_unit,
                            'time_value': time_value,
                            'threshold': threshold,
                            'node': node,
                            'community_id': comm_id
                        })
                    
                    analyzed_count += 1
                    
                except Exception as e:
                    logger.warning(
                        f"네트워크 분석 실패: {network_file.name}",
                        extra={"error": str(e)}
                    )
                    continue
            
            # 결과 저장
            if all_stats:
                stats_df = pd.DataFrame(all_stats)
                stats_df.to_parquet(results_dir / "network_statistics.parquet", index=False)
                stats_df.to_csv(results_dir / "network_statistics.csv", index=False)
            
            if all_centrality:
                centrality_df = pd.concat(all_centrality, ignore_index=True)
                centrality_df.to_parquet(results_dir / "centrality.parquet", index=False)
            
            if all_communities:
                community_df = pd.DataFrame(all_communities)
                community_df.to_parquet(results_dir / "communities.parquet", index=False)
            
            end_time = datetime.now()
            message = f"분석 완료: {analyzed_count}개 네트워크 분석"
            
            logger.info(
                message,
                extra={
                    "networks_analyzed": analyzed_count,
                    "duration_seconds": (end_time - start_time).total_seconds()
                }
            )
            
            return StageResult(
                stage=stage,
                success=True,
                start_time=start_time,
                end_time=end_time,
                message=message,
                records_processed=analyzed_count
            )
            
        except Exception as e:
            end_time = datetime.now()
            logger.error(
                "Analyze 스테이지 실패",
                extra={"error": str(e)},
                exc_info=True
            )
            return StageResult(
                stage=stage,
                success=False,
                start_time=start_time,
                end_time=end_time,
                message="분석 실패",
                error=str(e)
            )
    
    # =========================================================================
    # 퍼블릭 메서드
    # =========================================================================
    
    def run_stage(
        self,
        stage: PipelineStage,
        check_dependencies: bool = True
    ) -> StageResult:
        """단일 스테이지 실행.
        
        Args:
            stage: 실행할 스테이지
            check_dependencies: 의존성 확인 여부 (기본 True)
            
        Returns:
            StageResult 객체
        """
        logger.info(
            f"스테이지 실행 시작: {stage.name}",
            extra={"check_dependencies": check_dependencies}
        )
        
        # 의존성 확인 (필요한 입력 파일 존재 여부)
        if check_dependencies:
            dependencies = self.STAGE_DEPENDENCIES.get(stage, [])
            for dep_stage in dependencies:
                # 의존 스테이지의 출력 파일 존재 여부 확인
                if not self._check_stage_output_exists(dep_stage):
                    return StageResult(
                        stage=stage,
                        success=False,
                        start_time=datetime.now(),
                        end_time=datetime.now(),
                        message=f"의존 스테이지 출력 없음: {dep_stage.name}",
                        error=f"의존 스테이지 {dep_stage.name}의 출력 파일이 존재하지 않습니다"
                    )
        
        # 스테이지 실행
        runner = self._stage_runners.get(stage)
        if runner is None:
            return StageResult(
                stage=stage,
                success=False,
                start_time=datetime.now(),
                end_time=datetime.now(),
                message=f"알 수 없는 스테이지: {stage.name}",
                error=f"스테이지 {stage.name}에 대한 실행 함수가 없습니다"
            )
        
        return runner()
    
    def _check_stage_output_exists(self, stage: PipelineStage) -> bool:
        """스테이지 출력 파일 존재 여부 확인.
        
        Args:
            stage: 확인할 스테이지
            
        Returns:
            출력 파일 존재 여부
        """
        output_paths = {
            PipelineStage.PARSE: Path("data/interim/parsed_tdocs.parquet"),
            PipelineStage.PREPROCESS: Path("data/interim/preprocessed_tdocs.parquet"),
            PipelineStage.BUILD: Path("data/processed"),
            PipelineStage.ANALYZE: Path("data/results"),
        }
        
        path = output_paths.get(stage)
        if path is None:
            return True
        
        if path.is_dir():
            # 디렉토리인 경우 내부에 파일이 있는지 확인
            return path.exists() and any(path.iterdir())
        
        return path.exists()
    
    def run_pipeline(
        self,
        stages: Optional[List[PipelineStage]] = None,
        stop_on_failure: bool = True
    ) -> PipelineResult:
        """전체 또는 선택된 파이프라인 스테이지 실행.
        
        Args:
            stages: 실행할 스테이지 목록. None이면 전체 스테이지 실행.
            stop_on_failure: 실패 시 중단 여부 (기본 True)
            
        Returns:
            PipelineResult 객체
        """
        pipeline_start = datetime.now()
        stages_to_run = stages or self.STAGE_ORDER
        stage_results: List[StageResult] = []
        
        logger.info(
            "파이프라인 실행 시작",
            extra={
                "stages": [s.name for s in stages_to_run],
                "stop_on_failure": stop_on_failure
            }
        )
        
        try:
            for stage in stages_to_run:
                result = self.run_stage(stage, check_dependencies=True)
                stage_results.append(result)
                
                if not result.success:
                    logger.error(
                        f"스테이지 실패: {stage.name}",
                        extra={"error": result.error}
                    )
                    if stop_on_failure:
                        break
                else:
                    logger.info(f"스테이지 성공: {stage.name}")
            
            pipeline_end = datetime.now()
            all_success = all(r.success for r in stage_results)
            
            # 결과 요약 로깅
            completed_stages = [r.stage.name for r in stage_results if r.success]
            failed_stages = [r.stage.name for r in stage_results if not r.success]
            
            if all_success:
                logger.info(
                    "파이프라인 실행 완료",
                    extra={
                        "completed_stages": completed_stages,
                        "total_duration_seconds": (pipeline_end - pipeline_start).total_seconds()
                    }
                )
            else:
                logger.error(
                    "파이프라인 실행 실패",
                    extra={
                        "completed_stages": completed_stages,
                        "failed_stages": failed_stages
                    }
                )
            
            return PipelineResult(
                success=all_success,
                start_time=pipeline_start,
                end_time=pipeline_end,
                stage_results=stage_results
            )
            
        except Exception as e:
            pipeline_end = datetime.now()
            logger.error(
                "파이프라인 실행 중 예외 발생",
                extra={"error": str(e)},
                exc_info=True
            )
            return PipelineResult(
                success=False,
                start_time=pipeline_start,
                end_time=pipeline_end,
                stage_results=stage_results,
                error=str(e)
            )
    
    def _scheduled_run(self) -> None:
        """스케줄러에 의해 호출되는 파이프라인 실행 함수."""
        logger.info("스케줄된 파이프라인 실행 시작")
        try:
            result = self.run_pipeline()
            if result.success:
                logger.info(
                    "스케줄된 파이프라인 실행 성공",
                    extra={
                        "completed_stages": [s.name for s in result.completed_stages],
                        "duration_seconds": result.duration_seconds
                    }
                )
            else:
                logger.error(
                    "스케줄된 파이프라인 실행 실패",
                    extra={
                        "failed_stages": [s.name for s in result.failed_stages],
                        "error": result.error
                    }
                )
        except Exception as e:
            logger.error(
                "스케줄된 파이프라인 실행 중 예외 발생",
                extra={"error": str(e)},
                exc_info=True
            )
    
    def start(self) -> None:
        """스케줄러 시작.
        
        cron 스케줄에 따라 파이프라인을 자동으로 실행한다.
        이 메서드는 블로킹 모드로 실행되며, stop() 호출 또는
        SIGINT/SIGTERM 시그널로 종료된다.
        """
        if self._running:
            logger.warning("스케줄러가 이미 실행 중입니다")
            return
        
        logger.info(
            "파이프라인 스케줄러 시작",
            extra={"schedule": self._config.schedule}
        )
        
        # 스케줄러 초기화
        self._scheduler = BlockingScheduler()
        
        # Cron 트리거 설정
        trigger = CronTrigger.from_crontab(self._config.schedule)
        
        # 작업 추가
        self._scheduler.add_job(
            self._scheduled_run,
            trigger=trigger,
            id="pipeline_job",
            name="3GPP Network Analysis Pipeline",
            replace_existing=True
        )
        
        # 시그널 핸들러 설정
        def signal_handler(signum, frame):
            logger.info(f"시그널 수신: {signum}. 스케줄러 종료 중...")
            self.stop()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        self._running = True
        
        try:
            logger.info("스케줄러 실행 시작. Ctrl+C로 종료할 수 있습니다.")
            self._scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("스케줄러 종료 요청 수신")
        finally:
            self._running = False
    
    def stop(self) -> None:
        """스케줄러 중지."""
        if not self._running or self._scheduler is None:
            logger.warning("스케줄러가 실행 중이 아닙니다")
            return
        
        logger.info("파이프라인 스케줄러 중지")
        
        try:
            self._scheduler.shutdown(wait=False)
        except Exception as e:
            logger.error(
                "스케줄러 종료 중 오류 발생",
                extra={"error": str(e)}
            )
        finally:
            self._running = False
            self._scheduler = None


# =============================================================================
# CLI 엔트리포인트
# =============================================================================


def main():
    """CLI 엔트리포인트.
    
    Usage:
        # 스케줄러 시작 (기본 모드)
        python -m src.scheduler.pipeline_scheduler
        
        # 즉시 파이프라인 실행
        python -m src.scheduler.pipeline_scheduler --run-now
        
        # 특정 스테이지만 실행
        python -m src.scheduler.pipeline_scheduler --stage parse
        python -m src.scheduler.pipeline_scheduler --stage preprocess
        python -m src.scheduler.pipeline_scheduler --stage build
        python -m src.scheduler.pipeline_scheduler --stage analyze
    """
    import argparse
    
    parser = argparse.ArgumentParser(
        description="3GPP Network Analysis Pipeline Scheduler"
    )
    parser.add_argument(
        "--run-now",
        action="store_true",
        help="즉시 파이프라인 실행 (스케줄러 없이)"
    )
    parser.add_argument(
        "--stage",
        choices=["parse", "preprocess", "build", "analyze"],
        help="특정 스테이지만 실행"
    )
    parser.add_argument(
        "--no-stop-on-failure",
        action="store_true",
        help="실패 시 계속 진행"
    )
    
    args = parser.parse_args()
    
    # 스케줄러 초기화
    try:
        scheduler = PipelineScheduler()
    except ValueError as e:
        logger.error(f"스케줄러 초기화 실패: {e}")
        sys.exit(1)
    
    # 단일 스테이지 실행
    if args.stage:
        stage_map = {
            "parse": PipelineStage.PARSE,
            "preprocess": PipelineStage.PREPROCESS,
            "build": PipelineStage.BUILD,
            "analyze": PipelineStage.ANALYZE,
        }
        stage = stage_map[args.stage]
        
        logger.info(f"단일 스테이지 실행: {args.stage}")
        result = scheduler.run_stage(stage)
        
        if result.success:
            print(f"✓ {args.stage} 스테이지 성공: {result.message}")
            sys.exit(0)
        else:
            print(f"✗ {args.stage} 스테이지 실패: {result.error}")
            sys.exit(1)
    
    # 즉시 파이프라인 실행
    if args.run_now:
        logger.info("즉시 파이프라인 실행")
        result = scheduler.run_pipeline(
            stop_on_failure=not args.no_stop_on_failure
        )
        
        if result.success:
            completed = ", ".join(s.name for s in result.completed_stages)
            print(f"✓ 파이프라인 성공: {completed}")
            print(f"  총 소요 시간: {result.duration_seconds:.1f}초")
            sys.exit(0)
        else:
            failed = ", ".join(s.name for s in result.failed_stages)
            print(f"✗ 파이프라인 실패: {failed}")
            if result.error:
                print(f"  오류: {result.error}")
            sys.exit(1)
    
    # 스케줄러 시작 (기본 모드)
    logger.info("스케줄러 모드로 시작")
    print(f"파이프라인 스케줄: {scheduler.config.schedule}")
    print("스케줄러 실행 중... Ctrl+C로 종료할 수 있습니다.")
    scheduler.start()


if __name__ == "__main__":
    main()
