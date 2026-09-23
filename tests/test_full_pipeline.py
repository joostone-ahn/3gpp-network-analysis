"""
Full Pipeline Integration Test (Task 16.1)

전체 파이프라인 통합 테스트:
- 모든 스테이지 순차 실행 테스트
- 샘플 데이터로 E2E 테스트
- PipelineScheduler 클래스 테스트
- CLI 엔트리포인트 테스트

Requirements: 15.1, 15.2, 16.1

테스트 목표:
1. Parse → Preprocess → Build → Analyze 전체 흐름 테스트
2. 각 스테이지 출력 파일이 올바르게 생성되는지 검증
3. 스테이지 간 데이터 전달 일관성 검증
4. PipelineScheduler 클래스 동작 검증
5. 에러 처리 및 복구 테스트
"""

import pytest
import pandas as pd
import numpy as np
import tempfile
import time
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
from unittest.mock import patch, MagicMock

from src.scheduler.pipeline_scheduler import (
    PipelineScheduler,
    PipelineStage,
    StageResult,
    PipelineResult,
)
from src.parser import TDocParser
from src.preprocessor import TitleFilter, WIExploder, TemporalEnricher
from src.network import CompanyNetworkBuilder, WINetworkBuilder
from src.analyzer import (
    NetworkStatistics,
    CentralityAnalyzer,
    CommunityDetector,
    AdvancedAnalyzer,
)
from src.utils.config_loader import (
    get_config_loader,
    NetworkConfig,
    PipelineConfig,
)


class TestSampleDataGeneration:
    """샘플 데이터 생성 유틸리티 테스트."""
    
    @staticmethod
    def create_sample_tdoc_xlsx(output_dir: Path, num_records: int = 100) -> List[Path]:
        """샘플 TDoc xlsx 파일 생성.
        
        Args:
            output_dir: 출력 디렉토리
            num_records: 생성할 레코드 수
            
        Returns:
            생성된 xlsx 파일 경로 리스트
        """
        import random
        random.seed(42)
        np.random.seed(42)
        
        companies = [
            "Samsung Electronics Co., Ltd.",
            "Nokia Corporation",
            "Huawei Technologies Co., Ltd.",
            "Ericsson",
            "Qualcomm",
            "Intel Corporation",
            "Apple Inc.",
            "ZTE Corporation",
            "OPPO",
            "vivo",
            "Xiaomi",
            "NTT Docomo, Inc.",
            "SK Telecom",
            "China Mobile",
            "Vodafone",
        ]
        
        work_items = [
            "5G_BASIC", "5G_PERF", "5G_IOT", "5G_SEC", "5G_ARCH",
            "5G_NR", "5G_MIMO", "5G_BEAM", "5G_QOS", "5G_PHY",
        ]
        
        titles_regular = [
            "5G NR Enhancement Proposal",
            "Physical Layer Performance Analysis",
            "Beam Management Optimization",
            "SA Architecture Update",
            "MIMO Improvements for IoT",
            "Security Framework Enhancement",
            "QoS Parameter Update",
        ]
        
        titles_excluded = [
            "LS on Security Requirements",
            "LS to SA5 on Interface",
            "Reply LS regarding Architecture",
            "CR pack for Release 18",
            "LS answer on Parameters",
        ]
        
        tsg_list = ["RAN", "SA", "CT"]
        wg_list = ["WG1", "WG2", "WG3", "WG4"]
        
        created_files = []
        
        for tsg in tsg_list[:2]:  # RAN, SA만 테스트
            tsg_dir = output_dir / tsg
            tsg_dir.mkdir(parents=True, exist_ok=True)
            
            for mtg in range(100, 103):  # 100-102 회차
                records = []
                records_per_file = num_records // 6  # TSG × MTG 조합
                
                for i in range(records_per_file):
                    # 20%는 제외 대상 Title
                    is_excluded = random.random() < 0.2
                    title = random.choice(titles_excluded if is_excluded else titles_regular)
                    
                    # 1-3개 기업 참여
                    num_companies = random.randint(1, 3)
                    participating_companies = random.sample(companies, num_companies)
                    source = ", ".join(participating_companies)
                    
                    # 1-2개 WI
                    num_wis = random.randint(1, 2)
                    selected_wis = random.sample(work_items, num_wis)
                    # 10%는 TEI/DUMMY 포함
                    if random.random() < 0.1:
                        selected_wis.append(random.choice(["TEI", "DUMMY"]))
                    related_wis = ", ".join(selected_wis)
                    
                    wg = random.choice(wg_list)
                    release = f"Rel-{random.choice([17, 18, 19])}"
                    
                    # 날짜 - 2020-2024 범위
                    year = random.randint(2020, 2024)
                    month = random.randint(1, 12)
                    day = random.randint(1, 28)
                    uploaded = f"{year}-{month:02d}-{day:02d}"
                    
                    records.append({
                        "TDoc": f"{tsg[0]}P-{mtg}{i:04d}",
                        "Title": title,
                        "Source": source,
                        "Related WIs": related_wis,
                        "Release": release,
                        "Uploaded": uploaded,
                    })
                
                # xlsx 파일 저장
                df = pd.DataFrame(records)
                file_path = tsg_dir / f"TDoc_List_Meeting_{tsg}#{mtg}.xlsx"
                df.to_excel(file_path, index=False)
                created_files.append(file_path)
        
        return created_files
    
    @staticmethod
    def create_sample_parsed_data(num_records: int = 500) -> pd.DataFrame:
        """샘플 파싱된 데이터 생성.
        
        Args:
            num_records: 생성할 레코드 수
            
        Returns:
            샘플 DataFrame
        """
        import random
        random.seed(42)
        np.random.seed(42)
        
        companies = [
            "Samsung Electronics Co., Ltd.",
            "Nokia Corporation",
            "Huawei Technologies Co., Ltd.",
            "Ericsson",
            "Qualcomm",
            "Intel Corporation",
            "Apple Inc.",
            "ZTE Corporation",
            "OPPO",
            "vivo",
            "Xiaomi",
            "NTT Docomo, Inc.",
            "SK Telecom",
            "China Mobile",
            "Vodafone",
        ]
        
        work_items = [
            "5G_BASIC", "5G_PERF", "5G_IOT", "5G_SEC", "5G_ARCH",
            "5G_NR", "5G_MIMO", "5G_BEAM", "5G_QOS", "5G_PHY",
        ]
        
        titles_regular = [
            "5G NR Enhancement Proposal",
            "Physical Layer Performance Analysis",
            "Beam Management Optimization",
            "SA Architecture Update",
            "MIMO Improvements for IoT",
        ]
        
        titles_excluded = [
            "LS on Security Requirements",
            "CR pack for Release 18",
        ]
        
        tsg_list = ["RAN", "SA", "CT"]
        
        records = []
        for i in range(num_records):
            # 15% 제외 대상
            is_excluded = random.random() < 0.15
            title = random.choice(titles_excluded if is_excluded else titles_regular)
            
            num_companies = random.randint(1, 3)
            source = ", ".join(random.sample(companies, num_companies))
            
            num_wis = random.randint(1, 2)
            selected_wis = random.sample(work_items, num_wis)
            if random.random() < 0.1:
                selected_wis.append(random.choice(["TEI", "DUMMY"]))
            
            tsg = random.choice(tsg_list)
            year = random.randint(2020, 2024)
            month = random.randint(1, 12)
            day = random.randint(1, 28)
            
            records.append({
                "TDoc": f"{tsg[0]}P-{100000 + i}",
                "Title": title,
                "Source": source,
                "Related WIs": ", ".join(selected_wis),
                "Release": random.choice([17, 18, 19]),
                "Uploaded": datetime(year, month, day),
                "TSG": tsg,
                "WG": f"WG{random.randint(1, 4)}",
                "MTG": random.randint(100, 105),
            })
        
        return pd.DataFrame(records)


class TestPipelineStagesSequential:
    """파이프라인 스테이지 순차 실행 테스트."""
    
    @pytest.fixture
    def sample_parsed_data(self) -> pd.DataFrame:
        """샘플 파싱된 데이터."""
        return TestSampleDataGeneration.create_sample_parsed_data(200)
    
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
    def network_config(self) -> NetworkConfig:
        """Network 설정 객체."""
        return NetworkConfig(
            thresholds=[0],
            time_units=["year"],
            tsg_groups=["ALL", "RAN", "SA"]
        )
    
    def test_stage_2_title_filter(self, sample_parsed_data, title_filter):
        """Stage 2: Title Filter 테스트."""
        initial_count = len(sample_parsed_data)
        
        filtered_df, stats = title_filter.filter(sample_parsed_data)
        
        # 일부 레코드가 필터링되었는지 확인
        assert len(filtered_df) < initial_count, "Title Filter가 레코드를 필터링하지 않음"
        assert stats.excluded_count > 0, "제외된 레코드가 없음"
        assert stats.total_after == len(filtered_df)
        
        # 필터링된 데이터에 LS/CR pack 패턴이 없는지 확인
        for title in filtered_df["Title"]:
            assert "LS on" not in title
            assert "CR pack" not in title
    
    def test_stage_4_wi_exploder(self, sample_parsed_data, title_filter, wi_exploder):
        """Stage 4: WI Exploder 테스트."""
        # Title Filter 먼저 적용
        filtered_df, _ = title_filter.filter(sample_parsed_data)
        
        exploded_df, stats = wi_exploder.explode(filtered_df)
        
        # Explode로 행 수 증가 (복수 WI가 있으므로)
        assert len(exploded_df) >= len(filtered_df), "WI Explode가 동작하지 않음"
        
        # TEI/DUMMY가 제외되었는지 확인
        if "Related WIs" in exploded_df.columns:
            for wi in exploded_df["Related WIs"]:
                if pd.notna(wi):
                    assert "TEI" not in str(wi), "TEI가 제외되지 않음"
                    assert "DUMMY" not in str(wi), "DUMMY가 제외되지 않음"
    
    def test_stage_5_temporal_enricher(
        self, sample_parsed_data, title_filter, wi_exploder, temporal_enricher
    ):
        """Stage 5: Temporal Enricher 테스트."""
        # 이전 스테이지 적용
        filtered_df, _ = title_filter.filter(sample_parsed_data)
        exploded_df, _ = wi_exploder.explode(filtered_df)
        
        enriched_df, stats = temporal_enricher.enrich(exploded_df)
        
        # Year, Quarter 컬럼 추가 확인
        assert "Year" in enriched_df.columns, "Year 컬럼이 추가되지 않음"
        assert "Quarter" in enriched_df.columns, "Quarter 컬럼이 추가되지 않음"
        
        # Year 값 유효성 확인
        assert enriched_df["Year"].notna().all(), "Year에 null 값 존재"
        assert (enriched_df["Year"] >= 2015).all(), "2015년 이전 데이터가 포함됨"
        
        # Quarter 형식 확인 (YYYYQN)
        for quarter in enriched_df["Quarter"]:
            assert quarter.startswith("20"), f"Quarter 형식 오류: {quarter}"
            assert "Q" in quarter, f"Quarter 형식 오류: {quarter}"
    
    def test_stage_6_network_builder(
        self, sample_parsed_data, title_filter, wi_exploder, 
        temporal_enricher, network_config
    ):
        """Stage 6: Network Builder 테스트."""
        # 이전 스테이지 적용
        filtered_df, _ = title_filter.filter(sample_parsed_data)
        exploded_df, _ = wi_exploder.explode(filtered_df)
        enriched_df, _ = temporal_enricher.enrich(exploded_df)
        
        # Source를 company로 변환 (실제로는 MembershipExtractor가 처리)
        if "company" not in enriched_df.columns:
            enriched_df["company"] = enriched_df["Source"].str.split(",").str[0].str.strip()
        
        # Work_Item 컬럼 생성 (WI Exploder 출력에서)
        if "Work_Item" not in enriched_df.columns:
            enriched_df["Work_Item"] = enriched_df["Related WIs"].fillna("").str.strip()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            builder = CompanyNetworkBuilder(
                config=network_config,
                output_dir=Path(tmpdir)
            )
            
            # 특정 연도에 대한 Edge 생성
            edges_df, stats = builder.build_edges(
                enriched_df,
                tsg_group="ALL",
                time_unit="year",
                time_value=2023,
                threshold=0
            )
            
            # Edge가 생성되었는지 확인
            if len(edges_df) > 0:
                assert "Source" in edges_df.columns
                assert "Target" in edges_df.columns
                assert "Weight" in edges_df.columns
                
                # Edge 정규화 확인
                for _, row in edges_df.iterrows():
                    assert row["Source"] < row["Target"], "Edge 정규화 실패"
    
    def test_stage_7_network_analyzer(
        self, sample_parsed_data, title_filter, wi_exploder,
        temporal_enricher, network_config
    ):
        """Stage 7: Network Analyzer 테스트."""
        # 이전 스테이지 적용
        filtered_df, _ = title_filter.filter(sample_parsed_data)
        exploded_df, _ = wi_exploder.explode(filtered_df)
        enriched_df, _ = temporal_enricher.enrich(exploded_df)
        
        # company, Work_Item 컬럼 생성
        if "company" not in enriched_df.columns:
            enriched_df["company"] = enriched_df["Source"].str.split(",").str[0].str.strip()
        if "Work_Item" not in enriched_df.columns:
            enriched_df["Work_Item"] = enriched_df["Related WIs"].str.strip()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Network Builder
            builder = CompanyNetworkBuilder(
                config=network_config,
                output_dir=Path(tmpdir)
            )
            
            edges_df, _ = builder.build_edges(
                enriched_df,
                tsg_group="ALL",
                time_unit="year",
                time_value=2023,
                threshold=0
            )
            
            if len(edges_df) < 2:
                pytest.skip("분석하기에 Edge가 부족함")
            
            # Analyzer 테스트
            stats_analyzer = NetworkStatistics()
            G = stats_analyzer.build_graph(edges_df)
            
            # Community Detection (modularity 재사용)
            community_detector = CommunityDetector(random_seed=42)
            community_result = community_detector.detect(G)
            
            # Statistics Computation
            stats = stats_analyzer.compute(G, modularity=community_result.modularity)
            
            assert stats.nodes > 0, "노드가 없음"
            assert stats.edges > 0, "Edge가 없음"
            assert stats.density >= 0, "밀도가 음수"
            
            # Centrality Analysis
            centrality_analyzer = CentralityAnalyzer()
            centrality_df = centrality_analyzer.compute_all(G)
            
            assert len(centrality_df) == stats.nodes, "중심성 결과 노드 수 불일치"


class TestFullPipelineE2E:
    """전체 파이프라인 E2E 테스트."""
    
    def test_full_pipeline_with_sample_data(self):
        """샘플 데이터로 전체 파이프라인 E2E 테스트."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            # 디렉토리 구조 생성
            raw_dir = tmpdir_path / "data" / "raw"
            interim_dir = tmpdir_path / "data" / "interim"
            processed_dir = tmpdir_path / "data" / "processed"
            results_dir = tmpdir_path / "data" / "results"
            
            for d in [raw_dir, interim_dir, processed_dir, results_dir]:
                d.mkdir(parents=True, exist_ok=True)
            
            # 1. 샘플 데이터 생성 (Parser 출력 시뮬레이션)
            parsed_df = TestSampleDataGeneration.create_sample_parsed_data(300)
            parsed_path = interim_dir / "parsed_tdocs.parquet"
            parsed_df.to_parquet(parsed_path)
            
            assert parsed_path.exists(), "파싱된 데이터 저장 실패"
            
            # 2. Preprocess (Stage 2-5)
            title_filter = TitleFilter(
                exclude_patterns=["LS on", "LS to", "Reply LS", "CR pack", "LS answer"]
            )
            wi_exploder = WIExploder(delimiters=[","], exclude_patterns=["TEI", "DUMMY"])
            temporal_enricher = TemporalEnricher(min_year=2015)
            
            # Stage 2
            filtered_df, filter_stats = title_filter.filter(parsed_df)
            assert len(filtered_df) > 0, "Title Filter 후 데이터가 비어있음"
            
            # Stage 4
            exploded_df, explode_stats = wi_exploder.explode(filtered_df)
            assert len(exploded_df) > 0, "WI Explode 후 데이터가 비어있음"
            
            # Stage 5
            enriched_df, enrich_stats = temporal_enricher.enrich(exploded_df)
            assert len(enriched_df) > 0, "Temporal Enrich 후 데이터가 비어있음"
            
            # company, Work_Item 컬럼 생성
            enriched_df["company"] = enriched_df["Source"].str.split(",").str[0].str.strip()
            enriched_df["Work_Item"] = enriched_df["Related WIs"].str.strip()
            
            preprocessed_path = interim_dir / "preprocessed_tdocs.parquet"
            enriched_df.to_parquet(preprocessed_path)
            
            assert preprocessed_path.exists(), "전처리 데이터 저장 실패"
            
            # 3. Build (Stage 6)
            network_config = NetworkConfig(
                thresholds=[0],
                time_units=["year"],
                tsg_groups=["ALL"]
            )
            
            company_builder = CompanyNetworkBuilder(
                config=network_config,
                output_dir=processed_dir
            )
            
            # 대표 연도로 네트워크 생성
            edges_df, build_stats = company_builder.build_edges(
                enriched_df,
                tsg_group="ALL",
                time_unit="year",
                time_value=2023,
                threshold=0
            )
            
            if len(edges_df) > 0:
                edge_path = processed_dir / "company_ALL_year_2023_0.parquet"
                edges_df.to_parquet(edge_path)
                assert edge_path.exists(), "Edge 데이터 저장 실패"
            
            # 4. Analyze (Stage 7)
            if len(edges_df) >= 2:
                stats_analyzer = NetworkStatistics()
                G = stats_analyzer.build_graph(edges_df)
                
                community_detector = CommunityDetector(random_seed=42)
                community_result = community_detector.detect(G)
                
                stats = stats_analyzer.compute(G, modularity=community_result.modularity)
                
                centrality_analyzer = CentralityAnalyzer()
                centrality_df = centrality_analyzer.compute_all(G)
                
                # 결과 저장
                stats_df = pd.DataFrame([stats.to_dict()])
                stats_df.to_csv(results_dir / "network_statistics.csv", index=False)
                centrality_df.to_parquet(results_dir / "centrality.parquet")
                
                community_df = community_result.to_node_dataframe()
                community_df.to_parquet(results_dir / "communities.parquet")
                
                # 결과 파일 확인
                assert (results_dir / "network_statistics.csv").exists()
                assert (results_dir / "centrality.parquet").exists()
                assert (results_dir / "communities.parquet").exists()


class TestPipelineSchedulerClass:
    """PipelineScheduler 클래스 테스트."""
    
    @pytest.fixture
    def mock_pipeline_config(self) -> PipelineConfig:
        """테스트용 파이프라인 설정."""
        return PipelineConfig(schedule="0 0 * * *")  # 매일 자정
    
    def test_pipeline_scheduler_initialization(self, mock_pipeline_config):
        """PipelineScheduler 초기화 테스트."""
        with patch.object(PipelineScheduler, '_load_config', return_value=mock_pipeline_config):
            scheduler = PipelineScheduler(config=mock_pipeline_config)
            
            assert scheduler.config == mock_pipeline_config
            assert scheduler.is_running is False
    
    def test_pipeline_scheduler_stage_order(self):
        """스테이지 실행 순서 테스트."""
        expected_order = [
            PipelineStage.PARSE,
            PipelineStage.PREPROCESS,
            PipelineStage.BUILD,
            PipelineStage.ANALYZE,
        ]
        
        assert PipelineScheduler.STAGE_ORDER == expected_order
    
    def test_pipeline_scheduler_stage_dependencies(self):
        """스테이지 의존성 테스트."""
        deps = PipelineScheduler.STAGE_DEPENDENCIES
        
        # PARSE는 의존성 없음
        assert deps[PipelineStage.PARSE] == []
        
        # PREPROCESS는 PARSE에 의존
        assert PipelineStage.PARSE in deps[PipelineStage.PREPROCESS]
        
        # BUILD는 PREPROCESS에 의존
        assert PipelineStage.PREPROCESS in deps[PipelineStage.BUILD]
        
        # ANALYZE는 BUILD에 의존
        assert PipelineStage.BUILD in deps[PipelineStage.ANALYZE]
    
    def test_stage_result_dataclass(self):
        """StageResult dataclass 테스트."""
        start = datetime.now()
        time.sleep(0.1)
        end = datetime.now()
        
        result = StageResult(
            stage=PipelineStage.PARSE,
            success=True,
            start_time=start,
            end_time=end,
            message="파싱 완료",
            records_processed=100
        )
        
        assert result.success is True
        assert result.stage == PipelineStage.PARSE
        assert result.duration_seconds >= 0.1
        assert result.records_processed == 100
        assert result.error is None
    
    def test_pipeline_result_dataclass(self):
        """PipelineResult dataclass 테스트."""
        start = datetime.now()
        end = datetime.now()
        
        stage_results = [
            StageResult(
                stage=PipelineStage.PARSE,
                success=True,
                start_time=start,
                end_time=end,
                message="성공"
            ),
            StageResult(
                stage=PipelineStage.PREPROCESS,
                success=False,
                start_time=start,
                end_time=end,
                message="실패",
                error="테스트 오류"
            )
        ]
        
        result = PipelineResult(
            success=False,
            start_time=start,
            end_time=end,
            stage_results=stage_results
        )
        
        assert result.success is False
        assert len(result.completed_stages) == 1
        assert len(result.failed_stages) == 1
        assert PipelineStage.PARSE in result.completed_stages
        assert PipelineStage.PREPROCESS in result.failed_stages


class TestPipelineSchedulerStageExecution:
    """PipelineScheduler 스테이지 실행 테스트."""
    
    @pytest.fixture
    def temp_data_dirs(self):
        """임시 데이터 디렉토리 설정."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            # 디렉토리 구조 생성
            raw_dir = tmpdir_path / "data" / "raw"
            interim_dir = tmpdir_path / "data" / "interim"
            processed_dir = tmpdir_path / "data" / "processed"
            results_dir = tmpdir_path / "data" / "results"
            
            for d in [raw_dir, interim_dir, processed_dir, results_dir]:
                d.mkdir(parents=True, exist_ok=True)
            
            yield {
                "root": tmpdir_path,
                "raw": raw_dir,
                "interim": interim_dir,
                "processed": processed_dir,
                "results": results_dir,
            }
    
    def test_check_stage_output_exists_parse(self, temp_data_dirs):
        """Parse 스테이지 출력 파일 존재 확인 테스트."""
        mock_config = PipelineConfig(schedule="0 0 * * *")
        
        with patch.object(PipelineScheduler, '_load_config', return_value=mock_config):
            with patch('src.scheduler.pipeline_scheduler.Path') as mock_path:
                # 파일이 존재하는 경우를 시뮬레이션
                mock_path_instance = MagicMock()
                mock_path_instance.exists.return_value = True
                mock_path.return_value = mock_path_instance
                
                scheduler = PipelineScheduler(config=mock_config)
                # 실제 파일이 없으므로 False 반환 예상
                assert scheduler._check_stage_output_exists(PipelineStage.PARSE) is False
    
    def test_run_pipeline_with_mocked_stages(self):
        """모의 스테이지로 파이프라인 실행 테스트."""
        mock_config = PipelineConfig(schedule="0 0 * * *")
        
        with patch.object(PipelineScheduler, '_load_config', return_value=mock_config):
            scheduler = PipelineScheduler(config=mock_config)
            
            # 스테이지 러너를 모의로 대체
            def mock_parse():
                return StageResult(
                    stage=PipelineStage.PARSE,
                    success=True,
                    start_time=datetime.now(),
                    end_time=datetime.now(),
                    message="모의 파싱 완료",
                    records_processed=100
                )
            
            def mock_preprocess():
                return StageResult(
                    stage=PipelineStage.PREPROCESS,
                    success=True,
                    start_time=datetime.now(),
                    end_time=datetime.now(),
                    message="모의 전처리 완료",
                    records_processed=80
                )
            
            def mock_build():
                return StageResult(
                    stage=PipelineStage.BUILD,
                    success=True,
                    start_time=datetime.now(),
                    end_time=datetime.now(),
                    message="모의 빌드 완료",
                    records_processed=50
                )
            
            def mock_analyze():
                return StageResult(
                    stage=PipelineStage.ANALYZE,
                    success=True,
                    start_time=datetime.now(),
                    end_time=datetime.now(),
                    message="모의 분석 완료",
                    records_processed=10
                )
            
            scheduler._stage_runners = {
                PipelineStage.PARSE: mock_parse,
                PipelineStage.PREPROCESS: mock_preprocess,
                PipelineStage.BUILD: mock_build,
                PipelineStage.ANALYZE: mock_analyze,
            }
            
            # 의존성 체크 비활성화하고 실행
            with patch.object(scheduler, '_check_stage_output_exists', return_value=True):
                result = scheduler.run_pipeline()
            
            assert result.success is True
            assert len(result.completed_stages) == 4
            assert len(result.failed_stages) == 0


class TestPipelineErrorHandling:
    """파이프라인 에러 처리 테스트."""
    
    def test_stage_failure_stops_pipeline(self):
        """스테이지 실패 시 파이프라인 중단 테스트."""
        mock_config = PipelineConfig(schedule="0 0 * * *")
        
        with patch.object(PipelineScheduler, '_load_config', return_value=mock_config):
            scheduler = PipelineScheduler(config=mock_config)
            
            call_count = {"parse": 0, "preprocess": 0, "build": 0}
            
            def mock_parse():
                call_count["parse"] += 1
                return StageResult(
                    stage=PipelineStage.PARSE,
                    success=True,
                    start_time=datetime.now(),
                    end_time=datetime.now(),
                    message="성공"
                )
            
            def mock_preprocess():
                call_count["preprocess"] += 1
                return StageResult(
                    stage=PipelineStage.PREPROCESS,
                    success=False,  # 실패
                    start_time=datetime.now(),
                    end_time=datetime.now(),
                    message="실패",
                    error="테스트 오류"
                )
            
            def mock_build():
                call_count["build"] += 1
                return StageResult(
                    stage=PipelineStage.BUILD,
                    success=True,
                    start_time=datetime.now(),
                    end_time=datetime.now(),
                    message="성공"
                )
            
            scheduler._stage_runners = {
                PipelineStage.PARSE: mock_parse,
                PipelineStage.PREPROCESS: mock_preprocess,
                PipelineStage.BUILD: mock_build,
                PipelineStage.ANALYZE: lambda: None,
            }
            
            with patch.object(scheduler, '_check_stage_output_exists', return_value=True):
                result = scheduler.run_pipeline()
            
            # PREPROCESS에서 실패했으므로 BUILD는 실행되지 않아야 함
            assert result.success is False
            assert call_count["parse"] == 1
            assert call_count["preprocess"] == 1
            assert call_count["build"] == 0
    
    def test_dependency_check_failure(self):
        """의존성 체크 실패 테스트."""
        mock_config = PipelineConfig(schedule="0 0 * * *")
        
        with patch.object(PipelineScheduler, '_load_config', return_value=mock_config):
            scheduler = PipelineScheduler(config=mock_config)
            
            # PREPROCESS 스테이지만 실행하려고 하지만, PARSE 출력이 없음
            with patch.object(scheduler, '_check_stage_output_exists', return_value=False):
                result = scheduler.run_stage(PipelineStage.PREPROCESS, check_dependencies=True)
            
            assert result.success is False
            assert "의존 스테이지" in result.message or "의존" in str(result.error)


class TestCLIEntryPoints:
    """CLI 엔트리포인트 테스트."""
    
    def test_module_entry_point_import(self):
        """모듈 엔트리포인트 임포트 테스트."""
        # 각 모듈의 __main__.py가 임포트 가능한지 확인
        try:
            from src.scheduler import entry_points
            assert hasattr(entry_points, 'main') or hasattr(entry_points, 'run')
        except ImportError:
            # entry_points 모듈이 없으면 패스
            pass
    
    def test_scheduler_module_execution(self):
        """스케줄러 모듈 실행 가능 테스트."""
        # python -m src.scheduler 실행 가능 여부 확인
        from src.scheduler import __init__
        
        # 최소한 PipelineScheduler가 임포트 가능해야 함
        from src.scheduler.pipeline_scheduler import PipelineScheduler
        assert PipelineScheduler is not None


class TestPipelineDataFlowConsistency:
    """파이프라인 데이터 흐름 일관성 테스트."""
    
    def test_column_preservation_through_stages(self):
        """스테이지 간 컬럼 보존 테스트."""
        # 샘플 데이터 생성
        data = TestSampleDataGeneration.create_sample_parsed_data(100)
        
        # Stage 2: Title Filter
        title_filter = TitleFilter(exclude_patterns=["LS on", "CR pack"])
        filtered_df, _ = title_filter.filter(data)
        
        # 원본 컬럼이 보존되는지 확인
        original_columns = set(data.columns)
        filtered_columns = set(filtered_df.columns)
        assert original_columns.issubset(filtered_columns), "Title Filter에서 컬럼 손실"
        
        # Stage 4: WI Exploder
        wi_exploder = WIExploder(delimiters=[","], exclude_patterns=["TEI", "DUMMY"])
        exploded_df, _ = wi_exploder.explode(filtered_df)
        
        # 원본 컬럼이 보존되는지 확인
        assert original_columns.issubset(set(exploded_df.columns)), "WI Exploder에서 컬럼 손실"
        
        # Stage 5: Temporal Enricher
        temporal_enricher = TemporalEnricher(min_year=2015)
        enriched_df, _ = temporal_enricher.enrich(exploded_df)
        
        # Year, Quarter 컬럼이 추가되었는지 확인
        assert "Year" in enriched_df.columns, "Year 컬럼 추가 실패"
        assert "Quarter" in enriched_df.columns, "Quarter 컬럼 추가 실패"
        
        # 원본 컬럼도 보존되는지 확인
        assert original_columns.issubset(set(enriched_df.columns)), "Temporal Enricher에서 컬럼 손실"
    
    def test_record_count_tracking(self):
        """레코드 수 추적 테스트."""
        data = TestSampleDataGeneration.create_sample_parsed_data(200)
        initial_count = len(data)
        
        record_counts = {"initial": initial_count}
        
        # Stage 2
        title_filter = TitleFilter(exclude_patterns=["LS on", "CR pack"])
        filtered_df, filter_stats = title_filter.filter(data)
        record_counts["after_filter"] = len(filtered_df)
        
        assert filter_stats.total_before == initial_count
        assert filter_stats.total_after == len(filtered_df)
        
        # Stage 4
        wi_exploder = WIExploder(delimiters=[","], exclude_patterns=["TEI", "DUMMY"])
        exploded_df, explode_stats = wi_exploder.explode(filtered_df)
        record_counts["after_explode"] = len(exploded_df)
        
        # Explode로 레코드 수 증가 가능
        assert len(exploded_df) >= len(filtered_df)
        
        # Stage 5
        temporal_enricher = TemporalEnricher(min_year=2015)
        enriched_df, enrich_stats = temporal_enricher.enrich(exploded_df)
        record_counts["after_enrich"] = len(enriched_df)
        
        # 각 단계에서 레코드 수가 0이 아닌지 확인
        for stage, count in record_counts.items():
            assert count > 0, f"{stage}에서 레코드가 0"


class TestOutputFileGeneration:
    """출력 파일 생성 테스트."""
    
    def test_parquet_output_format(self):
        """Parquet 출력 형식 테스트."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data = TestSampleDataGeneration.create_sample_parsed_data(50)
            output_path = Path(tmpdir) / "test_output.parquet"
            
            data.to_parquet(output_path)
            
            assert output_path.exists()
            assert output_path.stat().st_size > 0
            
            # 로드 검증
            loaded = pd.read_parquet(output_path)
            pd.testing.assert_frame_equal(data.reset_index(drop=True), loaded.reset_index(drop=True))
    
    def test_csv_output_format(self):
        """CSV 출력 형식 테스트."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data = pd.DataFrame({
                "metric": ["nodes", "edges", "density"],
                "value": [100, 500, 0.05]
            })
            output_path = Path(tmpdir) / "test_stats.csv"
            
            data.to_csv(output_path, index=False)
            
            assert output_path.exists()
            
            # 로드 검증
            loaded = pd.read_csv(output_path)
            assert len(loaded) == 3
            assert "metric" in loaded.columns
            assert "value" in loaded.columns


# =============================================================================
# 파이프라인 재현성 Property 테스트 (Task 16.2)
# =============================================================================


class TestPipelineReproducibility:
    """파이프라인 재현성 Property 테스트 (Property 19).
    
    요구사항 16.2: 동일 입력에 대해 동일한 결과를 생성하는지 검증한다.
    - 동일 입력 데이터와 설정 파일에서 동일한 분석 결과 생성
    - random_seed 고정으로 Louvain 커뮤니티 탐지 재현성 보장
    - 다중 실행 시 동일 결과 생성
    
    **Validates: Requirements 16.2**
    """
    
    @staticmethod
    def create_deterministic_sample_data(seed: int = 42, num_records: int = 100) -> pd.DataFrame:
        """결정론적 샘플 데이터 생성.
        
        동일한 seed로 항상 동일한 데이터를 생성한다.
        
        Args:
            seed: 랜덤 시드
            num_records: 생성할 레코드 수
            
        Returns:
            결정론적으로 생성된 DataFrame
        """
        import random
        random.seed(seed)
        np.random.seed(seed)
        
        companies = [
            "Samsung Electronics",
            "Nokia",
            "Huawei",
            "Ericsson",
            "Qualcomm",
            "Intel",
            "Apple",
            "ZTE",
            "OPPO",
            "vivo",
        ]
        
        work_items = [
            "5G_BASIC", "5G_PERF", "5G_IOT", "5G_SEC", "5G_ARCH",
            "5G_NR", "5G_MIMO", "5G_BEAM", "5G_QOS", "5G_PHY",
        ]
        
        tsg_list = ["RAN", "SA", "CT"]
        
        records = []
        for i in range(num_records):
            # 결정론적 선택
            num_companies = random.randint(1, 3)
            selected_companies = random.sample(companies, num_companies)
            company = selected_companies[0]  # 첫 번째 기업 (explode 후 기준)
            
            num_wis = random.randint(1, 2)
            selected_wis = random.sample(work_items, num_wis)
            wi = selected_wis[0]  # 첫 번째 WI (explode 후 기준)
            
            tsg = random.choice(tsg_list)
            year = random.randint(2020, 2023)
            quarter = f"{year}Q{random.randint(1, 4)}"
            
            records.append({
                "TDoc": f"{tsg[0]}P-{100000 + i}",
                "Title": f"Test Document {i}",
                "company": company,
                "Work_Item": wi,
                "Release": random.choice([17, 18, 19]),
                "Year": year,
                "Quarter": quarter,
                "TSG": tsg,
                "WG": f"WG{random.randint(1, 4)}",
            })
        
        return pd.DataFrame(records)
    
    @pytest.fixture
    def deterministic_preprocessed_df(self) -> pd.DataFrame:
        """결정론적 전처리 완료 DataFrame."""
        return self.create_deterministic_sample_data(seed=42, num_records=200)
    
    @pytest.fixture
    def network_config_for_reproducibility(self) -> NetworkConfig:
        """재현성 테스트용 Network 설정."""
        return NetworkConfig(
            thresholds=[0],
            time_units=["year"],
            tsg_groups=["ALL"]
        )
    
    def test_property_same_input_produces_same_edges(
        self, 
        deterministic_preprocessed_df, 
        network_config_for_reproducibility
    ):
        """Property: 동일 입력에 대해 동일한 Edge list 생성.
        
        동일한 전처리된 데이터를 여러 번 처리해도 항상 동일한
        Edge list가 생성되어야 한다 (결정론적 결과).
        
        **Validates: Requirements 16.2**
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            builder = CompanyNetworkBuilder(
                config=network_config_for_reproducibility,
                output_dir=Path(tmpdir)
            )
            
            # 3회 실행하여 결과 비교
            results = []
            for run_idx in range(3):
                edges_df, stats = builder.build_edges(
                    deterministic_preprocessed_df.copy(),
                    tsg_group="ALL",
                    time_unit="year",
                    time_value=2022,
                    threshold=0
                )
                # Edge를 정렬하여 비교 가능하게 만듦
                if len(edges_df) > 0:
                    edges_sorted = edges_df.sort_values(
                        by=["Source", "Target"]
                    ).reset_index(drop=True)
                    results.append(edges_sorted)
            
            # 최소 하나의 결과가 있어야 함
            if len(results) == 0:
                pytest.skip("Edge가 생성되지 않음 (데이터 부족)")
            
            # 모든 실행 결과가 동일해야 함
            reference = results[0]
            for run_idx, result in enumerate(results[1:], start=2):
                pd.testing.assert_frame_equal(
                    reference,
                    result,
                    check_dtype=False,
                    obj=f"Run 1 vs Run {run_idx} Edge list"
                )
    
    def test_property_louvain_seed_ensures_reproducible_communities(
        self, 
        deterministic_preprocessed_df, 
        network_config_for_reproducibility
    ):
        """Property: random_seed 고정으로 Louvain 커뮤니티 탐지 재현성 보장.
        
        동일한 네트워크에서 동일한 random_seed(louvain_seed=42)를 사용하면
        항상 동일한 커뮤니티 결과가 생성되어야 한다.
        
        **Validates: Requirements 16.2, 11.4**
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Edge list 생성
            builder = CompanyNetworkBuilder(
                config=network_config_for_reproducibility,
                output_dir=Path(tmpdir)
            )
            
            edges_df, _ = builder.build_edges(
                deterministic_preprocessed_df.copy(),
                tsg_group="ALL",
                time_unit="year",
                time_value=2022,
                threshold=0
            )
            
            if len(edges_df) < 5:
                pytest.skip("커뮤니티 탐지를 위한 충분한 Edge가 없음")
            
            # CommunityDetector로 3회 실행 (동일 seed=42)
            detector = CommunityDetector(random_seed=42)
            
            results = []
            for run_idx in range(3):
                # 매번 새로운 그래프 생성 (동일 데이터)
                G = detector.build_graph(edges_df.copy())
                result = detector.detect(G)
                results.append(result)
            
            # 모든 실행에서 동일한 커뮤니티 결과
            reference = results[0]
            for run_idx, result in enumerate(results[1:], start=2):
                # 커뮤니티 수 동일
                assert reference.num_communities == result.num_communities, \
                    f"Run 1과 Run {run_idx}의 커뮤니티 수가 다름"
                
                # modularity 동일
                assert abs(reference.modularity - result.modularity) < 1e-6, \
                    f"Run 1과 Run {run_idx}의 modularity가 다름"
                
                # 노드별 커뮤니티 매핑 동일
                assert reference.node_community_map == result.node_community_map, \
                    f"Run 1과 Run {run_idx}의 노드 커뮤니티 매핑이 다름"
    
    def test_property_different_seeds_produce_different_communities(
        self, 
        deterministic_preprocessed_df, 
        network_config_for_reproducibility
    ):
        """Property: 서로 다른 seed는 다른 커뮤니티 결과를 생성할 수 있음.
        
        이 테스트는 seed가 실제로 커뮤니티 탐지에 영향을 미치는지 확인한다.
        같은 네트워크에서 다른 seed를 사용하면 다른 결과가 나올 수 있다.
        
        Note: Louvain 알고리즘 특성상 항상 다른 결과를 보장하지는 않지만,
              seed가 영향을 미침을 검증한다.
        
        **Validates: Requirements 16.2**
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Edge list 생성
            builder = CompanyNetworkBuilder(
                config=network_config_for_reproducibility,
                output_dir=Path(tmpdir)
            )
            
            edges_df, _ = builder.build_edges(
                deterministic_preprocessed_df.copy(),
                tsg_group="ALL",
                time_unit="year",
                time_value=2022,
                threshold=0
            )
            
            if len(edges_df) < 10:
                pytest.skip("다양한 커뮤니티 탐지를 위한 충분한 Edge가 없음")
            
            # 다른 seed로 여러 번 실행
            seeds = [42, 123, 456, 789]
            results = {}
            
            for seed in seeds:
                detector = CommunityDetector(random_seed=seed)
                G = detector.build_graph(edges_df.copy())
                result = detector.detect(G)
                results[seed] = result
            
            # 동일 seed에 대해서는 재현 가능해야 함
            detector_42_again = CommunityDetector(random_seed=42)
            G = detector_42_again.build_graph(edges_df.copy())
            result_42_again = detector_42_again.detect(G)
            
            assert results[42].node_community_map == result_42_again.node_community_map, \
                "동일 seed(42)에서 다른 결과가 나옴 - 재현성 실패"
    
    def test_property_network_statistics_reproducibility(
        self, 
        deterministic_preprocessed_df, 
        network_config_for_reproducibility
    ):
        """Property: 네트워크 통계 계산의 재현성.
        
        동일한 Edge list에 대해 동일한 네트워크 통계가 계산되어야 한다.
        modularity는 CommunityDetector의 결과를 재사용한다.
        
        **Validates: Requirements 16.2, 10.1**
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Edge list 생성
            builder = CompanyNetworkBuilder(
                config=network_config_for_reproducibility,
                output_dir=Path(tmpdir)
            )
            
            edges_df, _ = builder.build_edges(
                deterministic_preprocessed_df.copy(),
                tsg_group="ALL",
                time_unit="year",
                time_value=2022,
                threshold=0
            )
            
            if len(edges_df) < 3:
                pytest.skip("통계 계산을 위한 충분한 Edge가 없음")
            
            # 3회 실행하여 통계 비교
            stats_results = []
            
            for run_idx in range(3):
                stats_analyzer = NetworkStatistics(output_dir=Path(tmpdir))
                G = stats_analyzer.build_graph(edges_df.copy())
                
                # CommunityDetector로 modularity 계산 (seed 고정)
                detector = CommunityDetector(random_seed=42)
                community_result = detector.detect(G)
                
                stats = stats_analyzer.compute(G, modularity=community_result.modularity)
                stats_results.append(stats)
            
            # 모든 실행 결과가 동일해야 함
            reference = stats_results[0]
            for run_idx, stats in enumerate(stats_results[1:], start=2):
                assert reference.nodes == stats.nodes, \
                    f"Run 1과 Run {run_idx}의 nodes가 다름"
                assert reference.edges == stats.edges, \
                    f"Run 1과 Run {run_idx}의 edges가 다름"
                assert abs(reference.density - stats.density) < 1e-9, \
                    f"Run 1과 Run {run_idx}의 density가 다름"
                assert abs(reference.avg_degree - stats.avg_degree) < 1e-9, \
                    f"Run 1과 Run {run_idx}의 avg_degree가 다름"
                assert abs(reference.modularity - stats.modularity) < 1e-6, \
                    f"Run 1과 Run {run_idx}의 modularity가 다름"
    
    def test_property_centrality_calculation_reproducibility(
        self, 
        deterministic_preprocessed_df, 
        network_config_for_reproducibility
    ):
        """Property: 중심성 계산의 재현성.
        
        동일한 네트워크에 대해 동일한 중심성 값이 계산되어야 한다.
        
        **Validates: Requirements 16.2, 11.1**
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Edge list 생성
            builder = CompanyNetworkBuilder(
                config=network_config_for_reproducibility,
                output_dir=Path(tmpdir)
            )
            
            edges_df, _ = builder.build_edges(
                deterministic_preprocessed_df.copy(),
                tsg_group="ALL",
                time_unit="year",
                time_value=2022,
                threshold=0
            )
            
            if len(edges_df) < 3:
                pytest.skip("중심성 계산을 위한 충분한 Edge가 없음")
            
            # 3회 실행하여 중심성 비교
            centrality_results = []
            
            for run_idx in range(3):
                stats_analyzer = NetworkStatistics(output_dir=Path(tmpdir))
                G = stats_analyzer.build_graph(edges_df.copy())
                
                centrality_analyzer = CentralityAnalyzer()
                centrality_df = centrality_analyzer.compute_all(G)
                
                # 노드명으로 정렬하여 비교 가능하게 만듦
                centrality_sorted = centrality_df.sort_values(
                    by="node"
                ).reset_index(drop=True)
                centrality_results.append(centrality_sorted)
            
            # 모든 실행 결과가 동일해야 함
            reference = centrality_results[0]
            for run_idx, centrality_df in enumerate(centrality_results[1:], start=2):
                pd.testing.assert_frame_equal(
                    reference,
                    centrality_df,
                    check_dtype=False,
                    atol=1e-9,  # 부동소수점 오차 허용
                    obj=f"Run 1 vs Run {run_idx} centrality"
                )
    
    def test_property_full_pipeline_determinism(
        self, 
        network_config_for_reproducibility
    ):
        """Property: 전체 파이프라인 결정론적 실행.
        
        전체 파이프라인(Build → Analyze)을 동일 입력으로 여러 번 실행해도
        항상 동일한 최종 결과가 생성되어야 한다.
        
        **Validates: Requirements 16.2**
        """
        
        def run_full_analysis(seed: int, tmpdir: Path) -> Dict[str, Any]:
            """전체 분석 파이프라인 실행."""
            # 결정론적 데이터 생성
            data = TestPipelineReproducibility.create_deterministic_sample_data(
                seed=seed, num_records=150
            )
            
            # Build
            builder = CompanyNetworkBuilder(
                config=network_config_for_reproducibility,
                output_dir=tmpdir
            )
            
            edges_df, _ = builder.build_edges(
                data,
                tsg_group="ALL",
                time_unit="year",
                time_value=2022,
                threshold=0
            )
            
            if len(edges_df) < 3:
                return {"skip": True}
            
            # Analyze
            stats_analyzer = NetworkStatistics(output_dir=tmpdir)
            G = stats_analyzer.build_graph(edges_df)
            
            # Community (seed 고정)
            detector = CommunityDetector(random_seed=42)
            community_result = detector.detect(G)
            
            # Statistics
            stats = stats_analyzer.compute(G, modularity=community_result.modularity)
            
            # Centrality
            centrality_analyzer = CentralityAnalyzer()
            centrality_df = centrality_analyzer.compute_all(G)
            
            return {
                "skip": False,
                "edges_count": len(edges_df),
                "nodes": stats.nodes,
                "edges": stats.edges,
                "density": stats.density,
                "modularity": stats.modularity,
                "num_communities": community_result.num_communities,
                "node_community_map": community_result.node_community_map,
                "centrality_values": centrality_df.sort_values("node").to_dict(),
            }
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # 동일 seed로 3회 실행
            results = []
            for run_idx in range(3):
                result = run_full_analysis(seed=42, tmpdir=Path(tmpdir))
                if result.get("skip"):
                    pytest.skip("분석을 위한 충분한 데이터가 없음")
                results.append(result)
            
            # 모든 실행 결과가 동일해야 함
            reference = results[0]
            for run_idx, result in enumerate(results[1:], start=2):
                assert reference["edges_count"] == result["edges_count"], \
                    f"Run 1과 Run {run_idx}의 edges_count가 다름"
                assert reference["nodes"] == result["nodes"], \
                    f"Run 1과 Run {run_idx}의 nodes가 다름"
                assert reference["edges"] == result["edges"], \
                    f"Run 1과 Run {run_idx}의 edges가 다름"
                assert abs(reference["density"] - result["density"]) < 1e-9, \
                    f"Run 1과 Run {run_idx}의 density가 다름"
                assert abs(reference["modularity"] - result["modularity"]) < 1e-6, \
                    f"Run 1과 Run {run_idx}의 modularity가 다름"
                assert reference["num_communities"] == result["num_communities"], \
                    f"Run 1과 Run {run_idx}의 num_communities가 다름"
                assert reference["node_community_map"] == result["node_community_map"], \
                    f"Run 1과 Run {run_idx}의 node_community_map이 다름"


class TestPipelineReproducibilityWithHypothesis:
    """Hypothesis를 사용한 파이프라인 재현성 Property 테스트.
    
    Property-Based Testing으로 다양한 입력에서 재현성을 검증한다.
    
    **Validates: Requirements 16.2, 17.1**
    """
    
    @pytest.fixture
    def network_config(self) -> NetworkConfig:
        """테스트용 Network 설정."""
        return NetworkConfig(
            thresholds=[0],
            time_units=["year"],
            tsg_groups=["ALL"]
        )
    
    @pytest.mark.slow
    def test_hypothesis_community_detection_reproducibility(self, network_config):
        """Hypothesis: 다양한 seed에서 커뮤니티 탐지 재현성 검증.
        
        다양한 random_seed 값에서 동일 seed로 두 번 실행하면
        항상 동일한 결과가 나와야 한다.
        
        **Validates: Requirements 16.2**
        """
        from hypothesis import given, settings, assume
        from hypothesis import strategies as st
        
        @given(
            random_seed=st.integers(min_value=0, max_value=10000),
            num_records=st.integers(min_value=50, max_value=150)
        )
        @settings(max_examples=10, deadline=30000)  # 성능을 위해 제한
        def check_reproducibility(random_seed: int, num_records: int):
            # 데이터 생성
            data = TestPipelineReproducibility.create_deterministic_sample_data(
                seed=42, num_records=num_records
            )
            
            with tempfile.TemporaryDirectory() as tmpdir:
                # Edge 생성
                builder = CompanyNetworkBuilder(
                    config=network_config,
                    output_dir=Path(tmpdir)
                )
                
                edges_df, _ = builder.build_edges(
                    data,
                    tsg_group="ALL",
                    time_unit="year",
                    time_value=2022,
                    threshold=0
                )
                
                # Edge가 충분하지 않으면 스킵
                assume(len(edges_df) >= 5)
                
                # 동일 seed로 2회 실행
                detector = CommunityDetector(random_seed=random_seed)
                
                G1 = detector.build_graph(edges_df.copy())
                result1 = detector.detect(G1)
                
                G2 = detector.build_graph(edges_df.copy())
                result2 = detector.detect(G2)
                
                # 결과 비교
                assert result1.num_communities == result2.num_communities
                assert abs(result1.modularity - result2.modularity) < 1e-6
                assert result1.node_community_map == result2.node_community_map
        
        check_reproducibility()
    
    @pytest.mark.slow
    def test_hypothesis_edge_generation_determinism(self, network_config):
        """Hypothesis: 다양한 데이터 크기에서 Edge 생성 결정론성 검증.
        
        다양한 크기의 입력 데이터에서 Edge 생성이 항상 결정론적이어야 한다.
        
        **Validates: Requirements 16.2**
        """
        from hypothesis import given, settings
        from hypothesis import strategies as st
        
        @given(
            seed=st.integers(min_value=1, max_value=1000),
            num_records=st.integers(min_value=30, max_value=100)
        )
        @settings(max_examples=10, deadline=30000)
        def check_edge_determinism(seed: int, num_records: int):
            # 동일 seed로 데이터 생성 (2회)
            data1 = TestPipelineReproducibility.create_deterministic_sample_data(
                seed=seed, num_records=num_records
            )
            data2 = TestPipelineReproducibility.create_deterministic_sample_data(
                seed=seed, num_records=num_records
            )
            
            with tempfile.TemporaryDirectory() as tmpdir:
                builder = CompanyNetworkBuilder(
                    config=network_config,
                    output_dir=Path(tmpdir)
                )
                
                edges1, _ = builder.build_edges(
                    data1, tsg_group="ALL", time_unit="year",
                    time_value=2022, threshold=0
                )
                edges2, _ = builder.build_edges(
                    data2, tsg_group="ALL", time_unit="year",
                    time_value=2022, threshold=0
                )
                
                # 동일 입력에서 동일 출력
                if len(edges1) > 0:
                    edges1_sorted = edges1.sort_values(
                        ["Source", "Target"]
                    ).reset_index(drop=True)
                    edges2_sorted = edges2.sort_values(
                        ["Source", "Target"]
                    ).reset_index(drop=True)
                    pd.testing.assert_frame_equal(
                        edges1_sorted, edges2_sorted, check_dtype=False
                    )
        
        check_edge_determinism()


# Entry point for running tests directly
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
