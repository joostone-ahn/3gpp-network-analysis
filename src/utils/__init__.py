"""
Utils Module

공통 유틸리티 함수 및 클래스를 포함하는 모듈.
"""

from .config_loader import (
    # Dataclasses
    CollectorTarget,
    CollectorConfig,
    SourceCleaningConfig,
    NormalizationConfig,
    DateRange,
    PreprocessingConfig,
    NetworkConfig,
    AnalysisConfig,
    PipelineConfig,
    # Loader
    ConfigLoader,
    # 편의 함수
    get_config_loader,
    load_config,
    load_raw_yaml,
    # 경로 상수
    PROJECT_ROOT,
    CONFIG_DIR,
)

from .logger import (
    JsonFormatter,
    StructuredLoggerAdapter,
    get_logger,
    setup_logging,
    create_collection_history_logger,
)

from .parquet_utils import (
    # 범용 Parquet I/O 함수
    save_to_parquet,
    load_from_parquet,
    get_parquet_metadata,
    verify_round_trip,
    # 파이프라인별 특화 함수
    save_parsed_tdocs,
    load_parsed_tdocs,
    save_preprocessed_data,
    load_preprocessed_data,
    save_network_edges,
    save_analysis_results,
    # 경로 상수
    DEFAULT_INTERIM_DIR,
    DEFAULT_PROCESSED_DIR,
    DEFAULT_RESULTS_DIR,
)

from .cache_manager import (
    CacheManager,
    CacheInfo,
    CacheMetadata,
    get_cache_manager,
)

__all__ = [
    # Config Dataclasses
    "CollectorTarget",
    "CollectorConfig",
    "SourceCleaningConfig",
    "NormalizationConfig",
    "DateRange",
    "PreprocessingConfig",
    "NetworkConfig",
    "AnalysisConfig",
    "PipelineConfig",
    # Config Loader
    "ConfigLoader",
    "get_config_loader",
    "load_config",
    "load_raw_yaml",
    "PROJECT_ROOT",
    "CONFIG_DIR",
    # Logger
    "JsonFormatter",
    "StructuredLoggerAdapter",
    "get_logger",
    "setup_logging",
    "create_collection_history_logger",
    # Parquet I/O (범용)
    "save_to_parquet",
    "load_from_parquet",
    "get_parquet_metadata",
    "verify_round_trip",
    # Parquet I/O (파이프라인별)
    "save_parsed_tdocs",
    "load_parsed_tdocs",
    "save_preprocessed_data",
    "load_preprocessed_data",
    "save_network_edges",
    "save_analysis_results",
    # Parquet 경로 상수
    "DEFAULT_INTERIM_DIR",
    "DEFAULT_PROCESSED_DIR",
    "DEFAULT_RESULTS_DIR",
    # Cache Manager
    "CacheManager",
    "CacheInfo",
    "CacheMetadata",
    "get_cache_manager",
]
