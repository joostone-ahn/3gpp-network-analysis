"""
독립 모듈 실행 엔트리포인트

각 파이프라인 스테이지를 독립적으로 실행하기 위한 CLI 명령을 제공한다.

Requirements: 15.2, 14.3

CLI 명령:
- run_parse: Stage 1.5 - TDoc xlsx 파일 파싱
- run_preprocess: Stage 2-5 - 전처리 파이프라인 실행
- run_build: Stage 6 - 네트워크 Edge list 생성
- run_analyze: Stage 7 - 네트워크 분석 수행
- run_all: 전체 파이프라인 실행 (Collector 제외)

사용 예시:
    # 파싱 실행
    python -m src.scheduler.entry_points parse --config config/preprocessing.yaml
    
    # 전체 파이프라인 실행
    python -m src.scheduler.entry_points run-all --verbose
    
    # 특정 스테이지만 실행
    python -m src.scheduler.entry_points build --threshold 0
"""

import argparse
import logging
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# 프로젝트 루트 경로 추가 (패키지 임포트를 위함)
PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.config_loader import (
    PROJECT_ROOT as CONFIG_PROJECT_ROOT,
    load_config,
    ConfigLoader,
    PreprocessingConfig,
    NetworkConfig,
    AnalysisConfig,
    PipelineConfig,
)
from src.utils.logger import get_logger

# 로거 설정
logger = get_logger(__name__)


# =============================================================================
# 결과 Dataclasses
# =============================================================================


@dataclass
class StageResult:
    """파이프라인 스테이지 실행 결과.
    
    Attributes:
        stage_name: 스테이지 이름
        success: 성공 여부
        start_time: 시작 시각
        end_time: 종료 시각
        duration_seconds: 소요 시간 (초)
        records_processed: 처리된 레코드 수
        output_path: 출력 파일 경로
        error_message: 에러 메시지 (실패 시)
        metadata: 추가 메타데이터
    """
    stage_name: str
    success: bool
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    records_processed: int = 0
    output_path: Optional[Path] = None
    error_message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def __repr__(self) -> str:
        status = "✓" if self.success else "✗"
        return (
            f"StageResult({status} {self.stage_name}: "
            f"{self.duration_seconds:.2f}s, {self.records_processed} records)"
        )


@dataclass
class PipelineResult:
    """파이프라인 전체 실행 결과.
    
    Attributes:
        success: 전체 파이프라인 성공 여부
        start_time: 시작 시각
        end_time: 종료 시각
        total_duration_seconds: 총 소요 시간
        stage_results: 각 스테이지별 결과
        error_message: 에러 메시지 (실패 시)
    """
    success: bool
    start_time: datetime
    end_time: datetime
    total_duration_seconds: float
    stage_results: List[StageResult]
    error_message: Optional[str] = None
    
    @property
    def failed_stages(self) -> List[str]:
        """실패한 스테이지 목록."""
        return [r.stage_name for r in self.stage_results if not r.success]
    
    @property
    def successful_stages(self) -> List[str]:
        """성공한 스테이지 목록."""
        return [r.stage_name for r in self.stage_results if r.success]
    
    def __repr__(self) -> str:
        status = "✓ SUCCESS" if self.success else "✗ FAILED"
        return (
            f"PipelineResult({status})\n"
            f"  Duration: {self.total_duration_seconds:.2f}s\n"
            f"  Stages: {len(self.successful_stages)}/{len(self.stage_results)} succeeded"
        )


# =============================================================================
# 스테이지 실행 함수
# =============================================================================


def run_parse(
    raw_dir: Optional[Path] = None,
    output_path: Optional[Path] = None,
    config_path: Optional[Path] = None,
    verbose: bool = False,
) -> StageResult:
    """Stage 1.5: TDoc xlsx 파일 파싱.
    
    data/raw/ 디렉토리의 xlsx 파일을 파싱하여 표준화된 DataFrame으로 변환한다.
    
    Args:
        raw_dir: 원본 xlsx 파일 디렉토리 (기본값: data/raw/)
        output_path: 파싱 결과 저장 경로 (기본값: data/interim/parsed_tdocs.parquet)
        config_path: preprocessing.yaml 설정 파일 경로
        verbose: 상세 로그 출력 여부
        
    Returns:
        StageResult: 스테이지 실행 결과
    """
    stage_name = "parse"
    start_time = datetime.now()
    
    if verbose:
        logger.info(f"[{stage_name}] 스테이지 시작: TDoc 파싱")
    
    try:
        from src.parser import TDocParser, save_parsed_tdocs
        
        # 기본 경로 설정
        data_dir = CONFIG_PROJECT_ROOT / "data"
        raw_dir = raw_dir or data_dir / "raw"
        output_path = output_path or data_dir / "interim" / "parsed_tdocs.parquet"
        
        # 설정 로드
        config: Optional[PreprocessingConfig] = None
        if config_path:
            loader = ConfigLoader(config_path.parent)
            config = loader.load_preprocessing_config()
        else:
            try:
                config = load_config("preprocessing")
            except FileNotFoundError:
                logger.warning("preprocessing.yaml을 찾을 수 없어 기본 설정을 사용합니다.")
        
        # 파서 실행
        parser = TDocParser(config)
        df = parser.parse_all(raw_dir)
        
        # 결과 저장
        output_path.parent.mkdir(parents=True, exist_ok=True)
        save_parsed_tdocs(df, output_path)
        
        stats = parser.get_stats()
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        if verbose:
            logger.info(
                f"[{stage_name}] 완료: {stats.total_rows}행 파싱, "
                f"{stats.successful_files}/{stats.total_files} 파일 처리"
            )
        
        return StageResult(
            stage_name=stage_name,
            success=True,
            start_time=start_time,
            end_time=end_time,
            duration_seconds=duration,
            records_processed=stats.total_rows,
            output_path=output_path,
            metadata={
                "files_found": stats.total_files,
                "files_parsed": stats.successful_files,
                "files_skipped": stats.skipped_files,
                "columns": list(df.columns) if not df.empty else [],
            },
        )
        
    except Exception as e:
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        logger.error(f"[{stage_name}] 파싱 실패: {e}")
        
        return StageResult(
            stage_name=stage_name,
            success=False,
            start_time=start_time,
            end_time=end_time,
            duration_seconds=duration,
            error_message=str(e),
        )


def run_preprocess(
    input_path: Optional[Path] = None,
    output_path: Optional[Path] = None,
    config_path: Optional[Path] = None,
    membership_path: Optional[Path] = None,
    verbose: bool = False,
) -> StageResult:
    """Stage 2-5: 전처리 파이프라인 실행.
    
    Title Filter → Membership Extraction → WI Explode → Temporal Enrichment.
    
    Args:
        input_path: 파싱된 데이터 경로 (기본값: data/interim/parsed_tdocs.parquet)
        output_path: 전처리 결과 저장 경로 (기본값: data/interim/preprocessed_tdocs.parquet)
        config_path: preprocessing.yaml 설정 파일 경로
        membership_path: ETSI 멤버십 파일 경로
        verbose: 상세 로그 출력 여부
        
    Returns:
        StageResult: 스테이지 실행 결과
    """
    stage_name = "preprocess"
    start_time = datetime.now()
    
    if verbose:
        logger.info(f"[{stage_name}] 스테이지 시작: 전처리 파이프라인")
    
    try:
        import pandas as pd
        from src.preprocessor import (
            TitleFilter,
            WIExploder,
            TemporalEnricher,
            build_preprocessing_metadata,
        )
        
        # 기본 경로 설정
        data_dir = CONFIG_PROJECT_ROOT / "data"
        input_path = input_path or data_dir / "interim" / "parsed_tdocs.parquet"
        output_path = output_path or data_dir / "interim" / "preprocessed_tdocs.parquet"
        
        # 설정 로드
        config: PreprocessingConfig = load_config("preprocessing")
        
        # 입력 데이터 로드
        df = pd.read_parquet(input_path)
        initial_rows = len(df)
        
        if verbose:
            logger.info(f"[{stage_name}] 입력 데이터: {initial_rows}행 로드")
        
        # Stage 2: Title Filter
        title_filter = TitleFilter(config.title_exclude_patterns)
        df, filter_stats = title_filter.filter(df)
        
        if verbose:
            logger.info(
                f"[{stage_name}] Title Filter 완료: "
                f"{filter_stats.total_before}→{filter_stats.total_after}행 "
                f"({filter_stats.excluded_count}행 제외)"
            )
        
        # Stage 3: Membership-based Extraction
        # TODO: MembershipExtractor가 완전히 구현되면 활성화
        # from src.preprocessor import MembershipExtractor
        # extractor = MembershipExtractor(...)
        # df, extraction_stats = extractor.process(df)
        
        # Stage 4: WI Explode
        wi_exploder = WIExploder(
            delimiters=config.wi_delimiters,
            exclude_patterns=config.wi_exclude_patterns,
        )
        df, explode_stats = wi_exploder.explode(df)
        
        if verbose:
            logger.info(
                f"[{stage_name}] WI Explode 완료: "
                f"{explode_stats.total_before}→{explode_stats.total_after}행"
            )
        
        # Stage 5: Temporal Enrichment
        temporal_enricher = TemporalEnricher(min_year=config.date_range.min_year)
        df, enrich_stats = temporal_enricher.enrich(df)
        
        if verbose:
            logger.info(
                f"[{stage_name}] Temporal Enrich 완료: "
                f"{enrich_stats.total_before}→{enrich_stats.total_after}행"
            )
        
        # 결과 저장
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(output_path, index=False)
        
        # 메타데이터 구성
        stages_stats = [
            ("title_filter", filter_stats.to_dict()),
            ("wi_explode", explode_stats.to_dict() if hasattr(explode_stats, 'to_dict') else {}),
            ("temporal_enrich", enrich_stats.to_dict()),
        ]
        metadata = build_preprocessing_metadata(stages_stats=stages_stats)
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        if verbose:
            logger.info(
                f"[{stage_name}] 완료: {initial_rows}→{len(df)}행, "
                f"소요 시간: {duration:.2f}초"
            )
        
        return StageResult(
            stage_name=stage_name,
            success=True,
            start_time=start_time,
            end_time=end_time,
            duration_seconds=duration,
            records_processed=len(df),
            output_path=output_path,
            metadata=metadata.to_dict() if hasattr(metadata, 'to_dict') else None,
        )
        
    except Exception as e:
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        logger.error(f"[{stage_name}] 전처리 실패: {e}")
        
        return StageResult(
            stage_name=stage_name,
            success=False,
            start_time=start_time,
            end_time=end_time,
            duration_seconds=duration,
            error_message=str(e),
        )


def run_build(
    input_path: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    config_path: Optional[Path] = None,
    tsg_groups: Optional[List[str]] = None,
    time_units: Optional[List[str]] = None,
    thresholds: Optional[List[int]] = None,
    verbose: bool = False,
) -> StageResult:
    """Stage 6: 네트워크 Edge list 생성.
    
    전처리된 데이터로부터 기업 간/WI 간 협력 네트워크 Edge를 생성한다.
    
    Args:
        input_path: 전처리된 데이터 경로 (기본값: data/interim/preprocessed_tdocs.parquet)
        output_dir: Edge list 저장 디렉토리 (기본값: data/processed/)
        config_path: network.yaml 설정 파일 경로
        tsg_groups: 분석할 TSG 그룹 목록 (None이면 설정 파일에서 로드)
        time_units: 시간 단위 목록 (None이면 설정 파일에서 로드)
        thresholds: Weight 임계값 목록 (None이면 설정 파일에서 로드)
        verbose: 상세 로그 출력 여부
        
    Returns:
        StageResult: 스테이지 실행 결과
    """
    stage_name = "build"
    start_time = datetime.now()
    
    if verbose:
        logger.info(f"[{stage_name}] 스테이지 시작: 네트워크 Edge 생성")
    
    try:
        import pandas as pd
        from src.network import CompanyNetworkBuilder, WINetworkBuilder
        
        # 기본 경로 설정
        data_dir = CONFIG_PROJECT_ROOT / "data"
        input_path = input_path or data_dir / "interim" / "preprocessed_tdocs.parquet"
        output_dir = output_dir or data_dir / "processed"
        
        # 설정 로드
        config: NetworkConfig = load_config("network")
        
        # 파라미터 오버라이드
        tsg_groups = tsg_groups or config.tsg_groups
        time_units = time_units or config.time_units
        thresholds = thresholds if thresholds is not None else config.thresholds
        
        # 입력 데이터 로드
        df = pd.read_parquet(input_path)
        
        if verbose:
            logger.info(f"[{stage_name}] 입력 데이터: {len(df)}행 로드")
            logger.info(
                f"[{stage_name}] 설정: TSG={tsg_groups}, "
                f"time_units={time_units}, thresholds={thresholds}"
            )
        
        # Company Network Builder
        company_builder = CompanyNetworkBuilder(
            config=config,
            output_dir=output_dir / "company",
        )
        
        company_results = company_builder.build_all(df)
        
        if verbose:
            logger.info(f"[{stage_name}] Company Network: {len(company_results)} Edge list 생성")
        
        # WI Network Builder
        wi_builder = WINetworkBuilder(
            config=config,
            output_dir=output_dir / "wi",
        )
        
        wi_results = wi_builder.build_all(df)
        
        if verbose:
            logger.info(f"[{stage_name}] WI Network: {len(wi_results)} Edge list 생성")
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        # build_all returns Dict[str, Tuple[DataFrame, Stats]]
        total_edges = sum(
            stats.edges_after_threshold 
            for _, stats in list(company_results.values()) + list(wi_results.values())
        )
        
        if verbose:
            logger.info(
                f"[{stage_name}] 완료: 총 {total_edges:,} Edge 생성, "
                f"소요 시간: {duration:.2f}초"
            )
        
        return StageResult(
            stage_name=stage_name,
            success=True,
            start_time=start_time,
            end_time=end_time,
            duration_seconds=duration,
            records_processed=total_edges,
            output_path=output_dir,
            metadata={
                "company_networks": len(company_results),
                "wi_networks": len(wi_results),
                "tsg_groups": tsg_groups,
                "time_units": time_units,
                "thresholds": thresholds,
            },
        )
        
    except Exception as e:
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        logger.error(f"[{stage_name}] 네트워크 구성 실패: {e}")
        
        return StageResult(
            stage_name=stage_name,
            success=False,
            start_time=start_time,
            end_time=end_time,
            duration_seconds=duration,
            error_message=str(e),
        )


def run_analyze(
    input_dir: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    config_path: Optional[Path] = None,
    run_advanced: bool = True,
    verbose: bool = False,
) -> StageResult:
    """Stage 7: 네트워크 분석 수행.
    
    네트워크 통계, 중심성, 커뮤니티 분석을 수행한다.
    
    Args:
        input_dir: Edge list 디렉토리 (기본값: data/processed/)
        output_dir: 분석 결과 저장 디렉토리 (기본값: data/results/)
        config_path: analysis.yaml 설정 파일 경로
        run_advanced: 고급 분석(Power-law, Small-world 등) 실행 여부
        verbose: 상세 로그 출력 여부
        
    Returns:
        StageResult: 스테이지 실행 결과
    """
    stage_name = "analyze"
    start_time = datetime.now()
    
    if verbose:
        logger.info(f"[{stage_name}] 스테이지 시작: 네트워크 분석")
    
    try:
        import pandas as pd
        import networkx as nx
        from src.analyzer import (
            NetworkStatistics,
            CentralityAnalyzer,
            CommunityDetector,
            AdvancedAnalyzer,
        )
        
        # 기본 경로 설정
        data_dir = CONFIG_PROJECT_ROOT / "data"
        input_dir = input_dir or data_dir / "processed"
        output_dir = output_dir or data_dir / "results"
        
        # 설정 로드
        config: AnalysisConfig = load_config("analysis")
        
        # 분석기 초기화
        statistics = NetworkStatistics()
        centrality_analyzer = CentralityAnalyzer(
            eigenvector_max_iter=config.eigenvector_max_iter
        )
        community_detector = CommunityDetector(random_seed=config.louvain_seed)
        
        advanced_analyzer = None
        if run_advanced:
            advanced_analyzer = AdvancedAnalyzer(
                random_network_samples=config.random_network_samples
            )
        
        # Edge list 파일 탐색
        company_dir = input_dir / "company"
        edge_files = list(company_dir.glob("*.parquet")) if company_dir.exists() else []
        
        if verbose:
            logger.info(f"[{stage_name}] {len(edge_files)}개 Edge list 파일 발견")
        
        # 출력 디렉토리 생성
        (output_dir / "statistics").mkdir(parents=True, exist_ok=True)
        (output_dir / "centrality").mkdir(parents=True, exist_ok=True)
        (output_dir / "community").mkdir(parents=True, exist_ok=True)
        if run_advanced:
            (output_dir / "advanced").mkdir(parents=True, exist_ok=True)
        
        networks_analyzed = 0
        all_stats = []
        
        for edge_file in edge_files:
            try:
                # Edge list 로드 및 그래프 구성
                edges_df = pd.read_parquet(edge_file)
                
                if edges_df.empty:
                    continue
                
                G = nx.from_pandas_edgelist(
                    edges_df,
                    source='Source',
                    target='Target',
                    edge_attr='Weight',
                )
                
                # 통계 계산
                net_stats = statistics.compute(G)
                stats_dict = net_stats.to_dict() if hasattr(net_stats, 'to_dict') else {}
                all_stats.append({
                    'file': edge_file.stem,
                    **stats_dict,
                })
                
                # 커뮤니티 탐지 (modularity 계산을 위해 먼저 실행)
                community_result = community_detector.detect(G)
                
                # 중심성 분석
                centrality_result = centrality_analyzer.compute_all(G)
                
                # 결과 저장
                basename = edge_file.stem
                
                # 중심성 결과 저장
                if centrality_result.centrality_df is not None:
                    centrality_result.centrality_df.to_parquet(
                        output_dir / "centrality" / f"{basename}_centrality.parquet",
                        index=False,
                    )
                
                # 커뮤니티 결과 저장
                if community_result.node_communities:
                    community_df = pd.DataFrame([
                        {"node": node, "community": comm}
                        for node, comm in community_result.node_communities.items()
                    ])
                    community_df.to_parquet(
                        output_dir / "community" / f"{basename}_community.parquet",
                        index=False,
                    )
                
                networks_analyzed += 1
                
                if verbose and networks_analyzed % 10 == 0:
                    logger.info(f"[{stage_name}] {networks_analyzed}개 네트워크 분석 완료")
                    
            except Exception as e:
                logger.warning(f"[{stage_name}] {edge_file.name} 분석 실패: {e}")
                continue
        
        # 통계 결과 저장
        if all_stats:
            stats_df = pd.DataFrame(all_stats)
            stats_df.to_parquet(
                output_dir / "statistics" / "network_statistics.parquet",
                index=False,
            )
            stats_df.to_csv(
                output_dir / "statistics" / "network_statistics.csv",
                index=False,
            )
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        if verbose:
            logger.info(
                f"[{stage_name}] 완료: {networks_analyzed}개 네트워크 분석, "
                f"소요 시간: {duration:.2f}초"
            )
        
        return StageResult(
            stage_name=stage_name,
            success=True,
            start_time=start_time,
            end_time=end_time,
            duration_seconds=duration,
            records_processed=networks_analyzed,
            output_path=output_dir,
            metadata={
                "networks_analyzed": networks_analyzed,
                "run_advanced": run_advanced,
            },
        )
        
    except Exception as e:
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        logger.error(f"[{stage_name}] 분석 실패: {e}")
        
        return StageResult(
            stage_name=stage_name,
            success=False,
            start_time=start_time,
            end_time=end_time,
            duration_seconds=duration,
            error_message=str(e),
        )


def run_all(
    skip_collect: bool = True,
    skip_advanced: bool = False,
    config_dir: Optional[Path] = None,
    verbose: bool = False,
) -> PipelineResult:
    """전체 파이프라인 실행.
    
    Parser → Preprocessor → Network Builder → Analyzer 순서로 실행.
    Collector는 기본적으로 건너뛴다 (네트워크 I/O 필요).
    
    Args:
        skip_collect: FTP 수집 스킵 여부 (기본값: True)
        skip_advanced: 고급 분석 스킵 여부 (기본값: False)
        config_dir: 설정 파일 디렉토리 경로
        verbose: 상세 로그 출력 여부
        
    Returns:
        PipelineResult: 파이프라인 실행 결과
    """
    start_time = datetime.now()
    stage_results: List[StageResult] = []
    
    logger.info("=" * 60)
    logger.info("3GPP Network Analysis 파이프라인 시작")
    logger.info("=" * 60)
    
    try:
        # Stage 1.5: Parse
        logger.info("\n[1/4] Stage 1.5: Parse (TDoc 파싱)")
        parse_result = run_parse(verbose=verbose)
        stage_results.append(parse_result)
        
        if not parse_result.success:
            raise RuntimeError(f"Parse 실패: {parse_result.error_message}")
        
        # Stage 2-5: Preprocess
        logger.info("\n[2/4] Stage 2-5: Preprocess (전처리)")
        preprocess_result = run_preprocess(verbose=verbose)
        stage_results.append(preprocess_result)
        
        if not preprocess_result.success:
            raise RuntimeError(f"Preprocess 실패: {preprocess_result.error_message}")
        
        # Stage 6: Build
        logger.info("\n[3/4] Stage 6: Build (네트워크 구성)")
        build_result = run_build(verbose=verbose)
        stage_results.append(build_result)
        
        if not build_result.success:
            raise RuntimeError(f"Build 실패: {build_result.error_message}")
        
        # Stage 7: Analyze
        logger.info("\n[4/4] Stage 7: Analyze (네트워크 분석)")
        analyze_result = run_analyze(
            run_advanced=not skip_advanced,
            verbose=verbose,
        )
        stage_results.append(analyze_result)
        
        if not analyze_result.success:
            raise RuntimeError(f"Analyze 실패: {analyze_result.error_message}")
        
        end_time = datetime.now()
        total_duration = (end_time - start_time).total_seconds()
        
        logger.info("\n" + "=" * 60)
        logger.info("파이프라인 완료!")
        logger.info(f"총 소요 시간: {total_duration:.2f}초")
        for result in stage_results:
            status = "✓" if result.success else "✗"
            logger.info(f"  {status} {result.stage_name}: {result.duration_seconds:.2f}초")
        logger.info("=" * 60)
        
        return PipelineResult(
            success=True,
            start_time=start_time,
            end_time=end_time,
            total_duration_seconds=total_duration,
            stage_results=stage_results,
        )
        
    except Exception as e:
        end_time = datetime.now()
        total_duration = (end_time - start_time).total_seconds()
        
        logger.error("\n" + "=" * 60)
        logger.error(f"파이프라인 실패: {e}")
        logger.error("=" * 60)
        
        return PipelineResult(
            success=False,
            start_time=start_time,
            end_time=end_time,
            total_duration_seconds=total_duration,
            stage_results=stage_results,
            error_message=str(e),
        )


# =============================================================================
# CLI 인터페이스
# =============================================================================


def create_parser() -> argparse.ArgumentParser:
    """ArgumentParser 생성.
    
    Returns:
        ArgumentParser: 설정된 파서
    """
    parser = argparse.ArgumentParser(
        prog="3gpp-pipeline",
        description="3GPP Network Analysis 파이프라인 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예제:
  # 파싱 실행
  python -m src.scheduler.entry_points parse --verbose
  
  # 전처리 실행
  python -m src.scheduler.entry_points preprocess --verbose
  
  # 네트워크 구성 (특정 threshold만)
  python -m src.scheduler.entry_points build --threshold 0 --threshold 1
  
  # 분석 실행 (고급 분석 포함)
  python -m src.scheduler.entry_points analyze --advanced
  
  # 전체 파이프라인 실행
  python -m src.scheduler.entry_points run-all --verbose
        """,
    )
    
    # 전역 옵션
    parser.add_argument(
        "--config",
        type=Path,
        help="설정 파일 디렉토리 경로 (기본값: config/)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="상세 로그 출력",
    )
    
    # 서브커맨드 정의
    subparsers = parser.add_subparsers(
        dest="command",
        title="commands",
        description="실행할 스테이지",
    )
    
    # parse 커맨드
    parse_parser = subparsers.add_parser(
        "parse",
        help="Stage 1.5: TDoc xlsx 파일 파싱",
    )
    parse_parser.add_argument(
        "--raw-dir",
        type=Path,
        help="원본 xlsx 파일 디렉토리 (기본값: data/raw/)",
    )
    parse_parser.add_argument(
        "--output",
        type=Path,
        help="출력 파일 경로 (기본값: data/interim/parsed_tdocs.parquet)",
    )
    
    # preprocess 커맨드
    preprocess_parser = subparsers.add_parser(
        "preprocess",
        help="Stage 2-5: 전처리 파이프라인 실행",
    )
    preprocess_parser.add_argument(
        "--input",
        type=Path,
        help="입력 파일 경로 (기본값: data/interim/parsed_tdocs.parquet)",
    )
    preprocess_parser.add_argument(
        "--output",
        type=Path,
        help="출력 파일 경로 (기본값: data/interim/preprocessed_tdocs.parquet)",
    )
    preprocess_parser.add_argument(
        "--membership",
        type=Path,
        help="ETSI 멤버십 파일 경로",
    )
    
    # build 커맨드
    build_parser = subparsers.add_parser(
        "build",
        help="Stage 6: 네트워크 Edge list 생성",
    )
    build_parser.add_argument(
        "--input",
        type=Path,
        help="입력 파일 경로 (기본값: data/interim/preprocessed_tdocs.parquet)",
    )
    build_parser.add_argument(
        "--output-dir",
        type=Path,
        help="출력 디렉토리 (기본값: data/processed/)",
    )
    build_parser.add_argument(
        "--tsg",
        action="append",
        dest="tsg_groups",
        help="분석할 TSG 그룹 (복수 지정 가능, 예: --tsg RAN --tsg SA)",
    )
    build_parser.add_argument(
        "--time-unit",
        action="append",
        dest="time_units",
        choices=["year", "release", "quarter"],
        help="시간 단위 (복수 지정 가능)",
    )
    build_parser.add_argument(
        "--threshold",
        action="append",
        type=int,
        dest="thresholds",
        help="Weight 임계값 (복수 지정 가능)",
    )
    
    # analyze 커맨드
    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Stage 7: 네트워크 분석 수행",
    )
    analyze_parser.add_argument(
        "--input-dir",
        type=Path,
        help="Edge list 디렉토리 (기본값: data/processed/)",
    )
    analyze_parser.add_argument(
        "--output-dir",
        type=Path,
        help="분석 결과 디렉토리 (기본값: data/results/)",
    )
    analyze_parser.add_argument(
        "--advanced",
        action="store_true",
        dest="run_advanced",
        help="고급 분석 수행 (Power-law, Small-world 등)",
    )
    analyze_parser.add_argument(
        "--no-advanced",
        action="store_false",
        dest="run_advanced",
        help="고급 분석 건너뛰기",
    )
    analyze_parser.set_defaults(run_advanced=True)
    
    # run-all 커맨드
    run_all_parser = subparsers.add_parser(
        "run-all",
        help="전체 파이프라인 실행 (Collector 제외)",
    )
    run_all_parser.add_argument(
        "--include-collect",
        action="store_true",
        help="FTP 수집 포함 (기본값: 제외)",
    )
    run_all_parser.add_argument(
        "--skip-advanced",
        action="store_true",
        help="고급 분석 건너뛰기",
    )
    
    return parser


def main(args: Optional[List[str]] = None) -> int:
    """CLI 메인 함수.
    
    Args:
        args: 명령행 인자 리스트 (None이면 sys.argv 사용)
        
    Returns:
        종료 코드 (0: 성공, 1: 실패)
    """
    parser = create_parser()
    parsed_args = parser.parse_args(args)
    
    if parsed_args.command is None:
        parser.print_help()
        return 1
    
    verbose = parsed_args.verbose
    
    # 로그 레벨 설정
    if verbose:
        logging.getLogger().setLevel(logging.INFO)
    
    # 커맨드별 실행
    if parsed_args.command == "parse":
        result = run_parse(
            raw_dir=parsed_args.raw_dir,
            output_path=parsed_args.output,
            verbose=verbose,
        )
        return 0 if result.success else 1
        
    elif parsed_args.command == "preprocess":
        result = run_preprocess(
            input_path=parsed_args.input,
            output_path=parsed_args.output,
            membership_path=getattr(parsed_args, 'membership', None),
            verbose=verbose,
        )
        return 0 if result.success else 1
        
    elif parsed_args.command == "build":
        result = run_build(
            input_path=parsed_args.input,
            output_dir=parsed_args.output_dir,
            tsg_groups=parsed_args.tsg_groups,
            time_units=parsed_args.time_units,
            thresholds=parsed_args.thresholds,
            verbose=verbose,
        )
        return 0 if result.success else 1
        
    elif parsed_args.command == "analyze":
        result = run_analyze(
            input_dir=parsed_args.input_dir,
            output_dir=parsed_args.output_dir,
            run_advanced=parsed_args.run_advanced,
            verbose=verbose,
        )
        return 0 if result.success else 1
        
    elif parsed_args.command == "run-all":
        result = run_all(
            skip_collect=not getattr(parsed_args, 'include_collect', False),
            skip_advanced=getattr(parsed_args, 'skip_advanced', False),
            verbose=verbose,
        )
        return 0 if result.success else 1
    
    return 1


if __name__ == "__main__":
    sys.exit(main())
