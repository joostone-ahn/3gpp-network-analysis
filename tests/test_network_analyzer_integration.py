"""
Network Builder + Analyzer Integration Test (Task 13: Checkpoint)

네트워크 분석 파이프라인의 통합 테스트:
- Network Builder (Stage 6): CompanyNetworkBuilder, WINetworkBuilder
- Network Analyzer (Stage 7): NetworkStatistics, CentralityAnalyzer, 
                              CommunityDetector, AdvancedAnalyzer

테스트 목표:
1. Network Builder에서 생성된 Edge list가 Analyzer에 올바르게 전달되는지 검증
2. 샘플 데이터로 전체 분석 파이프라인 실행 확인
3. 분석 결과의 일관성 및 정확성 검증
"""

import pytest
import pandas as pd
import numpy as np
import networkx as nx
import tempfile
from pathlib import Path
from typing import Dict, List, Any
from dataclasses import dataclass

from src.network.company_network import CompanyNetworkBuilder, CompanyEdgeSchema
from src.network.wi_network import WINetworkBuilder, WIEdgeSchema
from src.analyzer.statistics import NetworkStatistics, NetworkStats
from src.analyzer.centrality import CentralityAnalyzer, CentralityResult
from src.analyzer.community import CommunityDetector, CommunityResult
from src.analyzer.advanced import AdvancedAnalyzer
from src.utils.config_loader import NetworkConfig


class TestNetworkBuilderIntegration:
    """Network Builder 통합 테스트."""
    
    @pytest.fixture
    def sample_preprocessed_data(self) -> pd.DataFrame:
        """Network Builder 테스트용 전처리된 샘플 데이터.
        
        기업 간 협력 네트워크를 구성할 수 있는 데이터:
        - 동일 Work Item에 복수 기업이 참여
        - 다양한 TSG, 연도, 분기 포함
        """
        return pd.DataFrame({
            "TDoc": [
                # WI_A에 Samsung, Nokia, Huawei 참여
                "RP-001", "RP-001", "RP-001",
                # WI_A에 Samsung, Ericsson 참여 (Samsung 중복)
                "RP-002", "RP-002",
                # WI_B에 Nokia, Qualcomm 참여
                "RP-003", "RP-003",
                # WI_C에 Huawei, Intel, Apple 참여
                "RP-004", "RP-004", "RP-004",
                # SA TSG 데이터 - WI_D
                "SP-001", "SP-001",
            ],
            "company": [
                "Samsung", "Nokia", "Huawei",
                "Samsung", "Ericsson",
                "Nokia", "Qualcomm",
                "Huawei", "Intel", "Apple",
                "NTT Docomo", "SK Telecom",
            ],
            "Work_Item": [
                "WI_A", "WI_A", "WI_A",
                "WI_A", "WI_A",
                "WI_B", "WI_B",
                "WI_C", "WI_C", "WI_C",
                "WI_D", "WI_D",
            ],
            "Year": [2023, 2023, 2023, 2023, 2023, 2023, 2023, 2024, 2024, 2024, 2024, 2024],
            "Quarter": ["2023Q1", "2023Q1", "2023Q1", "2023Q2", "2023Q2", 
                       "2023Q3", "2023Q3", "2024Q1", "2024Q1", "2024Q1", "2024Q2", "2024Q2"],
            "Release": [18, 18, 18, 18, 18, 17, 17, 19, 19, 19, 18, 18],
            "TSG": ["RAN", "RAN", "RAN", "RAN", "RAN", "RAN", "RAN", 
                   "RAN", "RAN", "RAN", "SA", "SA"],
        })
    
    @pytest.fixture
    def network_config(self) -> NetworkConfig:
        """Network 설정 객체."""
        return NetworkConfig(
            thresholds=[0],  # 모든 Edge 포함
            time_units=["year"],
            tsg_groups=["ALL", "RAN", "SA"]
        )
    
    @pytest.fixture
    def company_network_builder(self, network_config) -> CompanyNetworkBuilder:
        """Company Network Builder 인스턴스."""
        with tempfile.TemporaryDirectory() as tmpdir:
            return CompanyNetworkBuilder(
                config=network_config,
                output_dir=Path(tmpdir)
            )
    
    @pytest.fixture
    def wi_network_builder(self, network_config) -> WINetworkBuilder:
        """WI Network Builder 인스턴스."""
        with tempfile.TemporaryDirectory() as tmpdir:
            return WINetworkBuilder(
                config=network_config,
                output_dir=Path(tmpdir)
            )
    
    def test_company_edge_generation(self, sample_preprocessed_data, network_config):
        """Company Edge 생성 테스트."""
        with tempfile.TemporaryDirectory() as tmpdir:
            builder = CompanyNetworkBuilder(config=network_config, output_dir=Path(tmpdir))
            
            # 전체 데이터에서 Edge 생성
            edges_df, stats = builder.build_edges(
                sample_preprocessed_data,
                tsg_group="ALL",
                time_unit="year",
                time_value=2023,
                threshold=0
            )
            
            # Edge가 생성되었는지 확인
            assert len(edges_df) > 0, "Edge가 생성되지 않음"
            
            # 필수 컬럼 확인
            assert "Source" in edges_df.columns
            assert "Target" in edges_df.columns
            assert "Weight" in edges_df.columns
            
            # Edge 정규화 확인 (Source < Target)
            for _, row in edges_df.iterrows():
                assert row["Source"] < row["Target"], f"Edge 정규화 실패: {row['Source']} >= {row['Target']}"
    
    def test_wi_edge_generation(self, sample_preprocessed_data, network_config):
        """WI Network Edge 생성 테스트."""
        with tempfile.TemporaryDirectory() as tmpdir:
            builder = WINetworkBuilder(config=network_config, output_dir=Path(tmpdir))
            
            edges_df, stats = builder.build_edges(
                sample_preprocessed_data,
                tsg_group="ALL",
                time_unit="year",
                time_value=2023,
                threshold=0
            )
            
            # Edge가 생성되었는지 확인
            assert len(edges_df) > 0, "WI Edge가 생성되지 않음"
            
            # 필수 컬럼 확인
            assert "Source" in edges_df.columns
            assert "Target" in edges_df.columns
            assert "Weight" in edges_df.columns
            
            # Edge 정규화 확인 (Source < Target)
            for _, row in edges_df.iterrows():
                assert row["Source"] < row["Target"], f"WI Edge 정규화 실패"
    
    def test_tsg_filtering(self, sample_preprocessed_data, network_config):
        """TSG 필터링 테스트."""
        with tempfile.TemporaryDirectory() as tmpdir:
            builder = CompanyNetworkBuilder(config=network_config, output_dir=Path(tmpdir))
            
            # RAN만 필터링
            ran_edges, _ = builder.build_edges(
                sample_preprocessed_data,
                tsg_group="RAN",
                time_unit="year",
                time_value=2024,
                threshold=0
            )
            
            # SA만 필터링
            sa_edges, _ = builder.build_edges(
                sample_preprocessed_data,
                tsg_group="SA",
                time_unit="year",
                time_value=2024,
                threshold=0
            )
            
            # RAN과 SA의 Edge가 다른지 확인 (SA는 NTT Docomo, SK Telecom만)
            if len(ran_edges) > 0 and len(sa_edges) > 0:
                ran_sources = set(ran_edges["Source"].tolist() + ran_edges["Target"].tolist())
                sa_sources = set(sa_edges["Source"].tolist() + sa_edges["Target"].tolist())
                
                # SA에 NTT Docomo나 SK Telecom이 있는지 확인
                assert "NTT Docomo" in sa_sources or "SK Telecom" in sa_sources
    
    def test_threshold_filtering(self, sample_preprocessed_data, network_config):
        """Threshold 필터링 테스트."""
        with tempfile.TemporaryDirectory() as tmpdir:
            builder = CompanyNetworkBuilder(config=network_config, output_dir=Path(tmpdir))
            
            # threshold=0으로 모든 Edge 가져오기
            all_edges, _ = builder.build_edges(
                sample_preprocessed_data,
                tsg_group="ALL",
                time_unit="year",
                time_value=2023,
                threshold=0
            )
            
            # threshold=2로 필터링 (Weight >= 2인 Edge만)
            filtered_edges, _ = builder.build_edges(
                sample_preprocessed_data,
                tsg_group="ALL",
                time_unit="year",
                time_value=2023,
                threshold=2
            )
            
            # 필터링된 Edge 수가 같거나 적어야 함
            assert len(filtered_edges) <= len(all_edges)
            
            # 필터링된 Edge의 Weight가 모두 2 이상인지 확인
            if len(filtered_edges) > 0:
                assert all(filtered_edges["Weight"] >= 2), "threshold 필터링 실패"


class TestNetworkAnalyzerIntegration:
    """Network Analyzer 통합 테스트."""
    
    @pytest.fixture
    def sample_edge_list(self) -> pd.DataFrame:
        """Analyzer 테스트용 샘플 Edge list.
        
        간단하지만 분석 가능한 네트워크 구조:
        - 6개 노드, 9개 Edge
        - 연결된 단일 컴포넌트
        """
        return pd.DataFrame({
            "Source": ["A", "A", "A", "B", "B", "C", "C", "D", "E"],
            "Target": ["B", "C", "D", "C", "E", "D", "F", "E", "F"],
            "Weight": [3, 2, 1, 4, 2, 3, 1, 2, 1],
        })
    
    @pytest.fixture
    def network_statistics(self) -> NetworkStatistics:
        """Network Statistics 인스턴스."""
        return NetworkStatistics()
    
    @pytest.fixture
    def centrality_analyzer(self) -> CentralityAnalyzer:
        """Centrality Analyzer 인스턴스."""
        return CentralityAnalyzer(eigenvector_max_iter=1000)
    
    @pytest.fixture
    def community_detector(self) -> CommunityDetector:
        """Community Detector 인스턴스."""
        return CommunityDetector(random_seed=42)
    
    @pytest.fixture
    def advanced_analyzer(self) -> AdvancedAnalyzer:
        """Advanced Analyzer 인스턴스."""
        return AdvancedAnalyzer(random_network_samples=10)  # 테스트용으로 작은 값
    
    def test_network_statistics_computation(self, sample_edge_list, network_statistics):
        """기본 네트워크 통계 계산 테스트."""
        # NetworkX 그래프 생성
        G = network_statistics.build_graph(sample_edge_list)
        
        # 통계 계산
        stats = network_statistics.compute(G)
        
        # 기본 통계 확인
        assert stats.nodes == 6, f"노드 수 불일치: {stats.nodes}"
        assert stats.edges == 9, f"Edge 수 불일치: {stats.edges}"
        assert stats.density > 0
        assert stats.connected_components >= 1
        assert stats.avg_degree > 0
        
        # 가중 통계 확인
        assert stats.weighted_edges == sum(sample_edge_list["Weight"])
        
        # LCC 기반 경로 통계 (단일 컴포넌트이므로 계산 가능)
        assert stats.diameter is not None or stats.diameter >= 1
        assert stats.avg_path_length is not None or stats.avg_path_length > 0
    
    def test_centrality_computation(self, sample_edge_list, centrality_analyzer):
        """중심성 계산 테스트."""
        # NetworkX 그래프 생성
        G = centrality_analyzer.build_graph(sample_edge_list)
        
        # 중심성 계산
        centrality_df = centrality_analyzer.compute_all(G)
        
        # 결과 확인
        assert len(centrality_df) == 6, "노드 수와 결과 행 수 불일치"
        
        # 필수 중심성 컬럼 확인
        expected_columns = {
            "node", "degree_centrality", "betweenness_centrality",
            "closeness_centrality", "eigenvector_centrality"
        }
        assert expected_columns.issubset(set(centrality_df.columns))
        
        # 정규화 확인 (0~1 범위)
        for col in ["degree_centrality", "betweenness_centrality", 
                    "closeness_centrality", "eigenvector_centrality"]:
            values = centrality_df[col].dropna()
            if len(values) > 0:
                assert values.min() >= 0, f"{col} 최소값이 0 미만"
                assert values.max() <= 1, f"{col} 최대값이 1 초과"
    
    def test_community_detection(self, sample_edge_list, community_detector):
        """커뮤니티 탐지 테스트."""
        # NetworkX 그래프 생성
        G = community_detector.build_graph(sample_edge_list)
        
        # 커뮤니티 탐지
        result = community_detector.detect(G)
        
        # 결과 확인
        assert result.modularity is not None
        assert len(result.node_community_map) == 6
        assert result.num_communities > 0
        
        # 모든 노드가 커뮤니티에 할당되었는지 확인
        for node, community_id in result.node_community_map.items():
            assert community_id is not None
    
    def test_community_reproducibility(self, sample_edge_list, community_detector):
        """커뮤니티 탐지 재현성 테스트 (seed 고정)."""
        G = community_detector.build_graph(sample_edge_list)
        
        # 두 번 실행
        result1 = community_detector.detect(G)
        result2 = community_detector.detect(G)
        
        # 동일한 결과 확인 (seed 고정)
        assert result1.modularity == result2.modularity
        assert result1.node_community_map == result2.node_community_map
    
    def test_statistics_with_community(self, sample_edge_list, network_statistics, community_detector):
        """통계 계산과 커뮤니티 통합 테스트."""
        G = network_statistics.build_graph(sample_edge_list)
        
        # 커뮤니티 먼저 탐지 (modularity 재사용)
        community_result = community_detector.detect(G)
        
        # 통계 계산 시 modularity 전달
        stats = network_statistics.compute(G, modularity=community_result.modularity)
        
        # modularity가 일치하는지 확인
        assert stats.modularity == community_result.modularity


class TestAdvancedAnalyzerIntegration:
    """Advanced Analyzer 통합 테스트."""
    
    @pytest.fixture
    def larger_edge_list(self) -> pd.DataFrame:
        """고급 분석용 더 큰 Edge list (Power-law 등 테스트용)."""
        # 허브 노드를 포함한 스케일프리 유사 구조
        np.random.seed(42)
        edges = []
        
        # 허브 노드 A에 많은 연결
        for i in range(15):
            edges.append({"Source": "A", "Target": f"N{i}", "Weight": np.random.randint(1, 5)})
        
        # 허브 노드 B에 중간 연결
        for i in range(10):
            edges.append({"Source": "B", "Target": f"M{i}", "Weight": np.random.randint(1, 3)})
        
        # A-B 연결
        edges.append({"Source": "A", "Target": "B", "Weight": 5})
        
        # 일부 추가 연결로 클러스터링 형성
        for i in range(5):
            edges.append({"Source": f"N{i}", "Target": f"N{i+1}", "Weight": 1})
        
        df = pd.DataFrame(edges)
        
        # Edge 정규화 (Source < Target)
        df["pair"] = df.apply(
            lambda r: tuple(sorted([r["Source"], r["Target"]])), axis=1
        )
        df["Source"] = df["pair"].apply(lambda x: x[0])
        df["Target"] = df["pair"].apply(lambda x: x[1])
        df = df.drop(columns=["pair"]).drop_duplicates(subset=["Source", "Target"])
        
        return df
    
    @pytest.fixture
    def advanced_analyzer(self) -> AdvancedAnalyzer:
        """Advanced Analyzer 인스턴스."""
        return AdvancedAnalyzer(random_network_samples=5)  # 빠른 테스트
    
    def test_power_law_analysis(self, larger_edge_list, advanced_analyzer):
        """Power-law 분석 테스트."""
        G = advanced_analyzer.build_graph(larger_edge_list)
        
        # 최소 노드 수 확인
        if G.number_of_nodes() < 10:
            pytest.skip("Power-law 분석에는 충분한 노드가 필요")
        
        result = advanced_analyzer.analyze_power_law(G)
        
        # 결과 확인 (alpha가 실제 속성명)
        assert result.alpha is not None
        assert result.xmin is not None
    
    def test_small_world_computation(self, larger_edge_list, advanced_analyzer):
        """Small-world 지수 계산 테스트."""
        G = advanced_analyzer.build_graph(larger_edge_list)
        
        # 연결된 컴포넌트가 충분히 큰지 확인
        if G.number_of_nodes() < 5:
            pytest.skip("Small-world 분석에는 충분한 노드가 필요")
        
        result = advanced_analyzer.compute_small_world(G)
        
        # 결과 확인 (실제 속성명 사용)
        if result.sigma is not None:
            assert result.clustering_coefficient > 0
            assert result.avg_path_length > 0
            assert result.clustering_random >= 0
            assert result.avg_path_length_random > 0
    
    def test_mst_extraction(self, larger_edge_list, advanced_analyzer):
        """Maximum Spanning Tree 추출 테스트."""
        G = advanced_analyzer.build_graph(larger_edge_list)
        
        mst = advanced_analyzer.extract_mst(G)
        
        # MST 속성 확인
        # MST는 n-1개의 Edge를 가짐 (n = 노드 수)
        assert mst.number_of_edges() == mst.number_of_nodes() - 1
        
        # MST는 트리이므로 연결됨
        assert nx.is_connected(mst)


class TestFullPipelineIntegration:
    """Network Builder → Analyzer 전체 파이프라인 통합 테스트."""
    
    @pytest.fixture
    def full_preprocessed_data(self) -> pd.DataFrame:
        """전체 파이프라인 테스트용 데이터."""
        # 더 현실적인 협력 네트워크 데이터
        import random
        random.seed(42)
        
        data = []
        
        companies = ["Samsung", "Nokia", "Huawei", "Ericsson", "Qualcomm",
                    "Intel", "Apple", "Google", "OPPO", "vivo"]
        work_items = ["5G_NR", "5G_PERF", "5G_IOT", "5G_SEC", "5G_ARCH"]
        
        # 각 WI에 2-5개 기업 참여
        for wi in work_items:
            num_companies = random.randint(2, 5)
            participating = random.sample(companies, num_companies)
            
            for company in participating:
                data.append({
                    "TDoc": f"RP-{random.randint(100000, 999999)}",
                    "company": company,
                    "Work_Item": wi,
                    "Year": 2023,
                    "Quarter": f"2023Q{random.randint(1, 4)}",
                    "Release": 18,
                    "TSG": "RAN"
                })
        
        return pd.DataFrame(data)
    
    @pytest.fixture
    def network_config(self) -> NetworkConfig:
        """Network 설정 객체."""
        return NetworkConfig(
            thresholds=[0],
            time_units=["year"],
            tsg_groups=["ALL"]
        )
    
    def test_full_pipeline_company_network(self, full_preprocessed_data, network_config):
        """Company Network: Builder → Statistics → Centrality → Community."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 1. Network Builder
            builder = CompanyNetworkBuilder(
                config=network_config,
                output_dir=Path(tmpdir)
            )
            
            edges_df, build_stats = builder.build_edges(
                full_preprocessed_data,
                tsg_group="ALL",
                time_unit="year",
                time_value=2023,
                threshold=0
            )
            
            assert len(edges_df) > 0, "Edge 생성 실패"
            
            # 2. Network Statistics
            stats_analyzer = NetworkStatistics()
            G = stats_analyzer.build_graph(edges_df)
            
            # 3. Community Detection (먼저 실행 - modularity 재사용)
            community_detector = CommunityDetector(random_seed=42)
            community_result = community_detector.detect(G)
            
            assert community_result.modularity is not None
            
            # 4. Statistics Computation (modularity 재사용)
            stats = stats_analyzer.compute(G, modularity=community_result.modularity)
            
            assert stats.nodes > 0
            assert stats.edges > 0
            assert stats.modularity == community_result.modularity
            
            # 5. Centrality Analysis
            centrality_analyzer = CentralityAnalyzer()
            centrality_df = centrality_analyzer.compute_all(G)
            
            assert len(centrality_df) == stats.nodes
            
            # 결과 일관성 확인
            assert set(centrality_df["node"].tolist()) == set(G.nodes())
    
    def test_full_pipeline_wi_network(self, full_preprocessed_data, network_config):
        """WI Network: Builder → Statistics → Centrality → Community."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 1. Network Builder
            builder = WINetworkBuilder(
                config=network_config,
                output_dir=Path(tmpdir)
            )
            
            edges_df, build_stats = builder.build_edges(
                full_preprocessed_data,
                tsg_group="ALL",
                time_unit="year",
                time_value=2023,
                threshold=0
            )
            
            assert len(edges_df) > 0, "WI Edge 생성 실패"
            
            # 2. Network Statistics
            stats_analyzer = NetworkStatistics()
            G = stats_analyzer.build_graph(edges_df)
            
            # 3. Community Detection
            community_detector = CommunityDetector(random_seed=42)
            community_result = community_detector.detect(G)
            
            # 4. Statistics Computation
            stats = stats_analyzer.compute(G, modularity=community_result.modularity)
            
            assert stats.nodes > 0
            assert stats.edges > 0
            
            # 5. Centrality Analysis
            centrality_analyzer = CentralityAnalyzer()
            centrality_df = centrality_analyzer.compute_all(G)
            
            assert len(centrality_df) == stats.nodes
    
    def test_pipeline_result_saving(self, full_preprocessed_data, network_config):
        """파이프라인 결과 저장 테스트."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            # 1. Edge list 생성 및 저장
            builder = CompanyNetworkBuilder(
                config=network_config,
                output_dir=tmpdir_path
            )
            
            edges_df, _ = builder.build_edges(
                full_preprocessed_data,
                tsg_group="ALL",
                time_unit="year",
                time_value=2023,
                threshold=0
            )
            
            edge_path = tmpdir_path / "edges.parquet"
            edges_df.to_parquet(edge_path)
            assert edge_path.exists()
            
            # 2. 통계 결과 저장
            stats_analyzer = NetworkStatistics()
            G = stats_analyzer.build_graph(edges_df)
            stats = stats_analyzer.compute(G)
            
            stats_path = tmpdir_path / "stats.csv"
            stats_df = pd.DataFrame([stats.to_dict()])
            stats_df.to_csv(stats_path, index=False)
            assert stats_path.exists()
            
            # 3. 중심성 결과 저장
            centrality_analyzer = CentralityAnalyzer()
            centrality_df = centrality_analyzer.compute_all(G)
            
            centrality_path = tmpdir_path / "centrality.parquet"
            centrality_df.to_parquet(centrality_path)
            assert centrality_path.exists()
            
            # 4. 커뮤니티 결과 저장
            community_detector = CommunityDetector(random_seed=42)
            community_result = community_detector.detect(G)
            
            community_path = tmpdir_path / "community.parquet"
            community_df = community_result.to_node_dataframe()
            community_df.to_parquet(community_path)
            assert community_path.exists()
            
            # 5. 저장된 파일 로드 검증
            loaded_edges = pd.read_parquet(edge_path)
            loaded_centrality = pd.read_parquet(centrality_path)
            loaded_community = pd.read_parquet(community_path)
            
            assert len(loaded_edges) == len(edges_df)
            assert len(loaded_centrality) == len(centrality_df)
            assert len(loaded_community) == len(community_df)


class TestEdgeCasesAndErrorHandling:
    """Edge case 및 에러 처리 테스트."""
    
    @pytest.fixture
    def network_config(self) -> NetworkConfig:
        """Network 설정 객체."""
        return NetworkConfig(
            thresholds=[0],
            time_units=["year"],
            tsg_groups=["ALL"]
        )
    
    def test_empty_dataframe(self, network_config):
        """빈 DataFrame 처리 테스트."""
        empty_df = pd.DataFrame(columns=["company", "Work_Item", "Year", "TSG"])
        
        with tempfile.TemporaryDirectory() as tmpdir:
            builder = CompanyNetworkBuilder(
                config=network_config,
                output_dir=Path(tmpdir)
            )
            
            edges_df, stats = builder.build_edges(
                empty_df,
                tsg_group="ALL",
                time_unit="year",
                time_value=2023,
                threshold=0
            )
            
            assert len(edges_df) == 0
    
    def test_single_company_work_item(self, network_config):
        """단일 기업만 참여한 WI 처리 테스트."""
        single_df = pd.DataFrame({
            "TDoc": ["RP-001"],
            "company": ["Samsung"],
            "Work_Item": ["WI_A"],
            "Year": [2023],
            "TSG": ["RAN"]
        })
        
        with tempfile.TemporaryDirectory() as tmpdir:
            builder = CompanyNetworkBuilder(
                config=network_config,
                output_dir=Path(tmpdir)
            )
            
            edges_df, stats = builder.build_edges(
                single_df,
                tsg_group="ALL",
                time_unit="year",
                time_value=2023,
                threshold=0
            )
            
            # 단일 기업은 Edge를 형성할 수 없음
            assert len(edges_df) == 0
    
    def test_small_graph_statistics(self):
        """작은 그래프의 통계 계산 테스트."""
        # 2개 노드, 1개 Edge
        small_edges = pd.DataFrame({
            "Source": ["A"],
            "Target": ["B"],
            "Weight": [1]
        })
        
        stats_analyzer = NetworkStatistics()
        G = stats_analyzer.build_graph(small_edges)
        stats = stats_analyzer.compute(G)
        
        assert stats.nodes == 2
        assert stats.edges == 1
        assert stats.diameter is not None  # 2개 노드면 diameter = 1
    
    def test_disconnected_graph(self):
        """비연결 그래프 처리 테스트."""
        disconnected_edges = pd.DataFrame({
            "Source": ["A", "C"],
            "Target": ["B", "D"],
            "Weight": [1, 1]
        })
        
        stats_analyzer = NetworkStatistics()
        G = stats_analyzer.build_graph(disconnected_edges)
        stats = stats_analyzer.compute(G)
        
        assert stats.connected_components == 2
        # diameter와 avg_path_length는 LCC 기준으로 계산
        assert stats.diameter is not None
    
    def test_eigenvector_convergence_handling(self):
        """Eigenvector 중심성 미수렴 처리 테스트."""
        # 매우 단순한 그래프에서는 수렴
        simple_edges = pd.DataFrame({
            "Source": ["A", "B"],
            "Target": ["B", "C"],
            "Weight": [1, 1]
        })
        
        analyzer = CentralityAnalyzer(eigenvector_max_iter=1000)
        G = analyzer.build_graph(simple_edges)
        
        result = analyzer.compute_all(G)
        
        # eigenvector_centrality가 계산되었는지 확인 (또는 null)
        assert "eigenvector_centrality" in result.columns


# Entry point for running tests directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
