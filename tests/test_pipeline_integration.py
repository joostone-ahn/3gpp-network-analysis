"""
Preprocessing Pipeline Integration Test (Task 10: Checkpoint)

전처리 파이프라인의 통합 테스트:
- Title Filter (Stage 2) → Membership Extraction (Stage 3) → 
  WI Explode (Stage 4) → Temporal Enrich (Stage 5)

테스트 목표:
1. 각 전처리 단계가 올바르게 체이닝되는지 검증
2. 데이터 변환의 일관성 확인
3. Parquet 저장/로드의 round-trip 동등성 검증
"""

import pytest
import pandas as pd
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Tuple, List, Dict, Any

from src.preprocessor.title_filter import TitleFilter, FilterStats
from src.preprocessor.wi_exploder import WIExploder, ExplodeStats
from src.preprocessor.temporal_enricher import (
    TemporalEnricher, 
    EnrichStats,
    PreprocessingMetadata,
    build_preprocessing_metadata,
)
from src.preprocessor.membership_extractor import (
    SourceCleaner,
    SourceCleaningConfig,
    MembershipNormalizer,
    NormalizationConfig,
)
from src.utils.parquet_utils import (
    save_to_parquet, 
    load_from_parquet, 
    verify_round_trip,
)


class TestPreprocessingPipelineIntegration:
    """전처리 파이프라인 통합 테스트."""
    
    @pytest.fixture
    def sample_tdoc_data(self) -> pd.DataFrame:
        """파이프라인 테스트용 샘플 TDoc 데이터.
        
        실제 3GPP 데이터와 유사한 구조의 테스트 데이터.
        """
        return pd.DataFrame({
            "TDoc": [
                "RP-123456", "RP-123457", "RP-123458", "RP-123459", 
                "RP-123460", "RP-123461", "RP-123462", "RP-123463",
                "SP-234567", "SP-234568",
            ],
            "Title": [
                "5G NR Carrier Aggregation Enhancement",      # 유지 대상
                "LS on 5G NR Security Requirements",          # LS - 제외 대상
                "CR pack for Release 18 updates",             # CR pack - 제외 대상
                "Physical Layer Performance Improvements",    # 유지 대상
                "Reply LS regarding SA5 interface",           # Reply LS - 제외 대상
                "New Radio Enhancements for IoT",             # 유지 대상
                "LS to CT4 on SEPP Security",                 # LS to - 제외 대상
                "Beam Management Optimization",               # 유지 대상
                "SA2 Architecture Enhancement",               # 유지 대상
                "LS answer on QoS Parameters",                # LS answer - 제외 대상
            ],
            "Source": [
                "Samsung Electronics Co., Ltd., Nokia",
                "Huawei Technologies Co., Ltd.",
                "Ericsson, Qualcomm",
                "Intel Corporation, CMCC",
                "ZTE Corporation",
                "OPPO, vivo, Xiaomi",
                "Deutsche Telekom AG",
                "Apple Inc., Google",
                "NTT Docomo, Inc.",
                "Vodafone",
            ],
            "Related WIs": [
                "5G_BASIC, 5G_PERF",           # 복수 WI
                "TEI, 5G_SEC",                  # TEI 포함
                "DUMMY, 5G_CR",                 # DUMMY 포함
                "5G_PHY",                       # 단일 WI
                "5G_ARCH",                      # 단일 WI
                "5G_IOT, 5G_NR",               # 복수 WI
                "5G_SEPP",                      # 단일 WI
                "5G_BEAM, 5G_MIMO, 5G_PERF",   # 복수 WI
                "5G_ARCH",                      # 단일 WI
                "5G_QOS",                       # 단일 WI
            ],
            "Uploaded": [
                "2023-03-15", "2023-04-20", "2023-06-10", "2023-07-25",
                "2023-08-30", "2023-09-15", "2023-10-05", "2023-11-20",
                "2024-01-15", "2024-02-28",
            ],
            "Release": [
                "Rel-18", "Rel-17", "Rel-18", "Release 17",
                "R18", "rel-18", "Rel-17", "Rel-18",
                "Rel-19", "Rel-18",
            ],
            "TSG": ["RAN", "RAN", "RAN", "RAN", "RAN", "RAN", "RAN", "RAN", "SA", "SA"],
            "WG": ["WG1", "WG2", "WG3", "WG1", "WG2", "WG1", "WG4", "WG1", "WG2", "WG5"],
            "MTG": [100, 100, 101, 101, 102, 102, 103, 103, 104, 104],
        })
    
    @pytest.fixture
    def title_filter(self) -> TitleFilter:
        """Title Filter 인스턴스."""
        patterns = [
            "LS on", "LS to", "LS Reply", "Reply LS", "LS in relation to",
            "LS for", "LS regarding", "LS response", "LS out", "LS answer",
            "LS about", "LS-Replay", "CR pack"
        ]
        return TitleFilter(exclude_patterns=patterns)
    
    @pytest.fixture
    def wi_exploder(self) -> WIExploder:
        """WI Exploder 인스턴스."""
        return WIExploder(
            delimiters=[","],
            exclude_patterns=["TEI", "DUMMY"]
        )
    
    @pytest.fixture
    def temporal_enricher(self) -> TemporalEnricher:
        """Temporal Enricher 인스턴스."""
        return TemporalEnricher(min_year=2015)
    
    @pytest.fixture
    def source_cleaner(self) -> SourceCleaner:
        """Source Cleaner 인스턴스."""
        config = SourceCleaningConfig(
            special_replacements={"CMCC": "China Mobile"},
            remove_characters=["[", "]", "."],
            add_word_boundary_spaces=True
        )
        return SourceCleaner(config)
    
    def test_title_filter_stage(self, sample_tdoc_data, title_filter):
        """Stage 2: Title Filter가 올바르게 동작하는지 테스트."""
        filtered_df, stats = title_filter.filter(sample_tdoc_data)
        
        # 기대 결과: LS 관련 및 CR pack 제외
        # 제외 대상: RP-123457 (LS on), RP-123458 (CR pack), 
        #           RP-123460 (Reply LS), RP-123462 (LS to), SP-234568 (LS answer)
        assert stats.total_before == 10
        assert stats.excluded_count == 5
        assert stats.total_after == 5
        
        # 남은 레코드 확인
        remaining_tdocs = filtered_df["TDoc"].tolist()
        assert "RP-123456" in remaining_tdocs  # 5G NR Carrier Aggregation Enhancement
        assert "RP-123459" in remaining_tdocs  # Physical Layer Performance Improvements
        assert "RP-123461" in remaining_tdocs  # New Radio Enhancements for IoT
        assert "RP-123463" in remaining_tdocs  # Beam Management Optimization
        assert "SP-234567" in remaining_tdocs  # SA2 Architecture Enhancement
        
        # 제외된 레코드가 없는지 확인
        assert "RP-123457" not in remaining_tdocs  # LS on
        assert "RP-123458" not in remaining_tdocs  # CR pack
    
    def test_wi_exploder_stage(self, wi_exploder):
        """Stage 4: WI Exploder가 올바르게 동작하는지 테스트."""
        # Title Filter 후 데이터 (5개 레코드)
        test_df = pd.DataFrame({
            "TDoc": ["RP-123456", "RP-123460", "RP-123462", "SP-234567", "RP-123459"],
            "Related WIs": [
                "5G_BASIC, 5G_PERF",           # 2개 WI
                "5G_IOT, 5G_NR",               # 2개 WI
                "5G_BEAM, 5G_MIMO, 5G_PERF",   # 3개 WI
                "5G_ARCH",                      # 1개 WI
                "TEI, 5G_PHY",                  # TEI 제외, 1개 유지
            ],
        })
        
        exploded_df, stats = wi_exploder.explode(test_df)
        
        # 기대 결과:
        # RP-123456: 2행 (5G_BASIC, 5G_PERF)
        # RP-123460: 2행 (5G_IOT, 5G_NR)
        # RP-123462: 3행 (5G_BEAM, 5G_MIMO, 5G_PERF)
        # SP-234567: 1행 (5G_ARCH)
        # RP-123459: 1행 (5G_PHY) - TEI 제외됨
        # 총 9행
        assert stats.total_after == 9
        
        # TEI와 DUMMY가 제외되었는지 확인
        # WI Exploder는 Related WIs 컬럼에 Work Item을 저장함
        work_items = exploded_df["Related WIs"].tolist()
        assert not any("TEI" in str(wi) for wi in work_items)
        assert not any("DUMMY" in str(wi) for wi in work_items)
        
        # 유효한 WI가 포함되었는지 확인
        assert "5G_BASIC" in work_items
        assert "5G_PERF" in work_items
        assert "5G_PHY" in work_items
    
    def test_temporal_enricher_stage(self, temporal_enricher):
        """Stage 5: Temporal Enricher가 올바르게 동작하는지 테스트."""
        test_df = pd.DataFrame({
            "TDoc": ["RP-1", "RP-2", "RP-3", "RP-4", "RP-5"],
            "Uploaded": [
                "2023-03-15",  # Q1
                "2023-06-20",  # Q2
                "2023-09-10",  # Q3
                "2023-12-25",  # Q4
                "2014-01-01",  # 제외 (2015년 이전)
            ],
        })
        
        enriched_df, stats = temporal_enricher.enrich(test_df)
        
        # 2015년 이전 데이터 제외 확인
        assert stats.excluded_by_date_range == 1
        assert len(enriched_df) == 4
        
        # Year 컬럼 추가 확인
        assert "Year" in enriched_df.columns
        years = enriched_df["Year"].tolist()
        assert all(y == 2023 for y in years)
        
        # Quarter 컬럼 추가 확인
        assert "Quarter" in enriched_df.columns
        quarters = enriched_df["Quarter"].tolist()
        assert "2023Q1" in quarters
        assert "2023Q2" in quarters
        assert "2023Q3" in quarters
        assert "2023Q4" in quarters
    
    def test_source_cleaner_integration(self, source_cleaner):
        """Stage 3 전처리: Source Cleaner가 올바르게 동작하는지 테스트."""
        # Source 문자열 정제 테스트
        source = "Samsung Electronics Co., Ltd., [CMCC], Chair"
        cleaned = source_cleaner.clean(source)
        
        # CMCC → China Mobile 치환 확인
        assert "China Mobile" in cleaned
        assert "CMCC" not in cleaned
        
        # 대괄호 제거 확인
        assert "[" not in cleaned
        assert "]" not in cleaned
        
        # 마침표 제거 확인 (문자열 내 마침표)
        # 단, 단어 경계 공백이 추가되므로 앞뒤 공백 존재
        assert cleaned.startswith(" ")
        assert cleaned.endswith(" ")
    
    def test_full_pipeline_integration(
        self, 
        sample_tdoc_data, 
        title_filter, 
        wi_exploder, 
        temporal_enricher
    ):
        """전체 파이프라인 통합 테스트: Title Filter → WI Explode → Temporal Enrich."""
        # Stage 2: Title Filter
        filtered_df, filter_stats = title_filter.filter(sample_tdoc_data)
        assert filter_stats.total_after > 0
        
        # Stage 4: WI Explode (Stage 3 Membership Extraction은 별도 테스트)
        exploded_df, explode_stats = wi_exploder.explode(filtered_df)
        assert explode_stats.total_after > 0
        
        # Stage 5: Temporal Enrichment
        enriched_df, enrich_stats = temporal_enricher.enrich(exploded_df)
        assert len(enriched_df) > 0
        
        # 최종 DataFrame 스키마 확인 (WI Exploder는 Related WIs 컬럼 유지)
        expected_columns = {"TDoc", "Title", "Related WIs", "Year", "Quarter"}
        assert expected_columns.issubset(set(enriched_df.columns))
        
        # Year, Quarter가 올바르게 추가되었는지 확인
        assert enriched_df["Year"].notna().all()
        assert enriched_df["Quarter"].notna().all()
    
    def test_pipeline_metadata_recording(
        self, 
        sample_tdoc_data, 
        title_filter, 
        wi_exploder, 
        temporal_enricher
    ):
        """파이프라인 메타데이터 기록 테스트."""
        # Stage 2: Title Filter
        filtered_df, filter_stats = title_filter.filter(sample_tdoc_data)
        
        # Stage 4: WI Explode
        exploded_df, explode_stats = wi_exploder.explode(filtered_df)
        
        # Stage 5: Temporal Enrichment
        enriched_df, enrich_stats = temporal_enricher.enrich(exploded_df)
        
        # 메타데이터 구축 - build_preprocessing_metadata API 사용
        stages_stats: List[Tuple[str, Dict[str, Any]]] = [
            ("title_filter", filter_stats.to_dict()),
            ("wi_exploder", explode_stats.to_dict()),
            ("temporal_enricher", enrich_stats.to_dict()),
        ]
        
        metadata = build_preprocessing_metadata(stages_stats)
        
        # 메타데이터 요약 확인 - get_summary는 요약 정보를 반환
        summary = metadata.get_summary()
        assert "stages_count" in summary
        assert summary["stages_count"] == 3
        
        # to_dict()를 사용해서 상세 정보 확인
        full_metadata = metadata.to_dict()
        assert "stages" in full_metadata
        assert len(full_metadata["stages"]) == 3


class TestParquetSerializationIntegration:
    """Parquet 직렬화 통합 테스트."""
    
    @pytest.fixture
    def sample_preprocessed_data(self) -> pd.DataFrame:
        """전처리된 데이터 샘플."""
        return pd.DataFrame({
            "TDoc": ["RP-123456", "RP-123456", "RP-123457"],
            "Title": ["Enhancement A", "Enhancement A", "Feature B"],
            "company": ["Samsung", "Nokia", "Huawei"],
            "Work_Item": ["5G_BASIC", "5G_PERF", "5G_PHY"],
            "Release": [18, 18, 17],
            "Year": [2023, 2023, 2023],
            "Quarter": ["2023Q1", "2023Q1", "2023Q2"],
            "TSG": ["RAN", "RAN", "RAN"],
            "WG": ["WG1", "WG1", "WG2"],
        })
    
    def test_parquet_round_trip_equality(self, sample_preprocessed_data):
        """Parquet round-trip 동등성 테스트 (요구사항 2.6)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "test_data.parquet"
            
            # 저장 → 로드 → 비교
            is_equal = verify_round_trip(sample_preprocessed_data, output_path)
            assert is_equal, "Parquet round-trip 동등성 실패"
    
    def test_save_and_load_preprocessed_data(self, sample_preprocessed_data):
        """전처리 데이터 저장/로드 테스트 (요구사항 7.1)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 저장
            output_path = save_to_parquet(
                sample_preprocessed_data, 
                Path(tmpdir) / "preprocessed.parquet",
                metadata={"stage": "test", "version": "1.0"}
            )
            
            assert output_path.exists()
            
            # 로드
            loaded_df = load_from_parquet(output_path)
            
            # 동등성 확인
            pd.testing.assert_frame_equal(
                sample_preprocessed_data.reset_index(drop=True),
                loaded_df.reset_index(drop=True),
            )
    
    def test_save_preprocessed_stage_data(self, sample_preprocessed_data):
        """단계별 전처리 데이터 저장 테스트."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 단계별 저장
            stage_names = ["title_filtered", "membership_extracted", 
                          "wi_exploded", "temporal_enriched"]
            
            for stage_name in stage_names:
                output_path = Path(tmpdir) / f"{stage_name}.parquet"
                save_to_parquet(
                    sample_preprocessed_data, 
                    output_path,
                    metadata={"stage": stage_name}
                )
                
                assert output_path.exists(), f"{stage_name} 저장 실패"
                
                # 로드 검증
                loaded = load_from_parquet(output_path)
                assert len(loaded) == len(sample_preprocessed_data)


class TestMembershipNormalizerPipelineIntegration:
    """Membership Normalizer 파이프라인 통합 테스트."""
    
    @pytest.fixture
    def normalization_config(self) -> NormalizationConfig:
        """테스트용 정규화 설정."""
        return NormalizationConfig(
            stopwords=[" Co.", " Ltd.", " Inc.", " Corporation", " Corp."],
            countries=[" Korea", " Germany", " Japan"],
            removes=["Beijing", "Shanghai"],
            replaces={"HuaWei": "Huawei", "DOCOMO": "NTT Docomo"},
            brackets_pattern=r"\s\(",
            startswith_exceptions=["BTL"],
            suffix=[" Software", " Electronics"],
            prefix=["Shanghai "]
        )
    
    @pytest.fixture
    def membership_normalizer(self, normalization_config) -> MembershipNormalizer:
        """Membership Normalizer 인스턴스."""
        return MembershipNormalizer(normalization_config)
    
    def test_normalizer_basic_normalization(self, membership_normalizer):
        """기본 정규화 테스트."""
        # 법인격 제거
        result = membership_normalizer.normalize("Samsung Electronics Co., Ltd.")
        assert "Co." not in result
        assert "Ltd." not in result
        
    def test_normalizer_replaces_mapping(self, membership_normalizer):
        """특수 매핑 테스트."""
        result = membership_normalizer.normalize("HuaWei Technologies")
        assert "Huawei" in result
        assert "HuaWei" not in result
    
    def test_normalizer_brackets_removal(self, membership_normalizer):
        """괄호 제거 테스트."""
        result = membership_normalizer.normalize("Samsung (Korea)")
        assert "(Korea)" not in result
        assert "Samsung" in result
    
    def test_normalizer_normalize_with_trace(self, membership_normalizer):
        """단계별 추적 테스트."""
        result, steps = membership_normalizer.normalize_with_trace(
            "Samsung Electronics Co., Ltd. (Korea)"
        )
        
        # 추적 단계 확인
        assert len(steps) > 0
        
        # 변경된 단계가 있는지 확인
        changed_steps = [s for s in steps if s.changed]
        assert len(changed_steps) > 0
    
    def test_normalizer_build_lookup_table(self, membership_normalizer):
        """검색 테이블 구축 테스트."""
        membership_df = pd.DataFrame({
            "Company": [
                "Samsung Electronics Co., Ltd.",
                "Huawei Technologies Co., Ltd.",
                "Nokia Corporation",
            ]
        })
        
        lookup = membership_normalizer.build_lookup_table(membership_df)
        
        # 테이블이 비어있지 않은지 확인
        assert len(lookup) > 0
        
        # 소문자 키로 접근 가능한지 확인 (case-insensitive)
        # 정규화된 이름이 키로 존재해야 함
        assert any("samsung" in k for k in lookup.keys())
    
    def test_normalizer_stage_statistics(self, membership_normalizer):
        """단계별 통계 테스트."""
        membership_df = pd.DataFrame({
            "Company": [
                "Samsung Electronics Co., Ltd.",
                "Samsung Electronics Co., Ltd. Korea",  # 중복
                "Huawei Technologies Co., Ltd.",
                "Nokia Corporation Germany",
            ]
        })
        
        stats = membership_normalizer.get_stage_statistics(membership_df)
        
        # 통계 DataFrame 확인
        assert not stats.empty
        assert "stage" in stats.columns
        assert "unique_companies" in stats.columns


class TestPreprocessingMetadataIntegration:
    """전처리 메타데이터 통합 테스트."""
    
    def test_build_preprocessing_metadata(self):
        """메타데이터 생성 테스트."""
        stages_stats: List[Tuple[str, Dict[str, Any]]] = [
            ("test_stage", {"total_before": 100, "total_after": 90}),
        ]
        metadata = build_preprocessing_metadata(stages_stats, pipeline_version="1.0")
        
        # 기본 속성 확인
        assert metadata.pipeline_version == "1.0"
        assert metadata.processed_at is not None
        assert len(metadata.stages) == 1
    
    def test_metadata_add_multiple_stages(self):
        """복수 단계 추가 테스트."""
        # 각 단계별 통계 생성
        filter_stats = FilterStats(
            total_before=1000, total_after=800, excluded_count=200,
            pattern_counts={"LS on": 100, "CR pack": 100}
        )
        
        explode_stats = ExplodeStats(
            total_before=800, total_after=1500, total_exploded=1550,
            total_excluded=50, wi_counts_before=100, wi_counts_after=150,
            pattern_counts={"TEI": 30, "DUMMY": 20}
        )
        
        enrich_stats = EnrichStats(
            total_before=1500, total_after=1450, 
            excluded_by_date_range=50, excluded_by_invalid_date=0,
            year_distribution={2023: 1000, 2024: 450},
            quarter_distribution={"2023Q1": 300, "2023Q2": 350, "2023Q3": 350}
        )
        
        # 메타데이터 구축
        stages_stats: List[Tuple[str, Dict[str, Any]]] = [
            ("title_filter", filter_stats.to_dict()),
            ("wi_exploder", explode_stats.to_dict()),
            ("temporal_enricher", enrich_stats.to_dict()),
        ]
        
        metadata = build_preprocessing_metadata(stages_stats)
        
        # get_summary()는 요약 정보 반환
        summary = metadata.get_summary()
        assert summary["stages_count"] == 3
        
        # to_dict()로 상세 정보 확인
        full_metadata = metadata.to_dict()
        assert len(full_metadata["stages"]) == 3


# Entry point for running tests directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
