"""
Preprocessor Module (Stage 2-5)

TDoc 데이터 전처리를 담당하는 모듈.
- Stage 2: Title Filter - 분석 대상 외 기고서 유형 제외
- Stage 3: Membership-based Extraction - Source에서 기업명 추출
- Stage 4: WI Explode - 복수 Work Item을 개별 행으로 분리
- Stage 5: Temporal Enrichment - 시간 정보 추가 및 필터링
"""

# Stage 2: Title Filter (구현 완료)
from .title_filter import TitleFilter, FilterStats

# Stage 3: Membership-based Extraction (구현 진행 중)
from .membership_extractor import (
    SourceCleaner,
    SourceCleaningConfig,
    MembershipNormalizer,
    NormalizationConfig,
    NormalizationStep,
    # MembershipExtractor,   # TODO: 구현 예정
    # ExtractionStats,       # TODO: 구현 예정
)

# Stage 4: WI Explode (구현 완료)
from .wi_exploder import WIExploder, ExplodeStats

# Stage 5: Temporal Enrichment (구현 완료)
from .temporal_enricher import (
    TemporalEnricher, 
    EnrichStats,
    PreprocessingMetadata,
    build_preprocessing_metadata,
)

__all__ = [
    # Stage 2
    "TitleFilter",
    "FilterStats",
    # Stage 3 (구현 진행 중)
    "SourceCleaner",
    "SourceCleaningConfig",
    "MembershipNormalizer",
    "NormalizationConfig",
    "NormalizationStep",
    # "MembershipExtractor",   # TODO
    # "ExtractionStats",       # TODO
    # Stage 4 (구현 완료)
    "WIExploder",
    "ExplodeStats",
    # Stage 5 (구현 완료)
    "TemporalEnricher",
    "EnrichStats",
    "PreprocessingMetadata",
    "build_preprocessing_metadata",
]
