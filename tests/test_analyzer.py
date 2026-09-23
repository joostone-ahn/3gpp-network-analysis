"""
Analyzer 모듈 Property 기반 테스트.

테스트 대상 Property:
- Property 16: 네트워크 통계 계산 정확성 테스트 (NetworkStatistics)
- Property 17: 중심성 정규화 테스트 (CentralityAnalyzer)
- Property 18: Maximum Spanning Tree 속성 테스트 (AdvancedAnalyzer)

요구사항:
- 10.1: 네트워크 기본 지표 계산 (nodes, edges, density, avg_degree 등)
- 10.2: diameter와 avg_path_length는 가장 큰 연결 컴포넌트(LCC) 기준으로 계산
- 10.3: LCC 노드 수가 2개 미만인 경우 diameter와 avg_path_length를 null 처리
- 11.1: 비가중(unweighted) 중심성 계산
- 11.2: 모든 Centrality 값을 0~1 사이로 정규화
- 12.3: Maximum Spanning Tree 추출
"""

import math
from typing import Any, Dict, List, Optional, Set, Tuple

import networkx as nx
import pandas as pd
import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

from src.analyzer.statistics import NetworkStatistics, NetworkStats
from src.analyzer.centrality import CentralityAnalyzer, CentralityResult
from src.analyzer.advanced import AdvancedAnalyzer, SmallWorldResult, PowerLawResult


# Suppress the function_scoped_fixture health check for all Hypothesis tests
# This is safe because our analyzer instances are stateless
HYPOTHESIS_SETTINGS = settings(
    max_examples=50,
    suppress_health_check=[
        HealthCheck.too_slow,
        HealthCheck.function_scoped_fixture,
    ],
)


# =============================================================================
# Hypothesis Strategies for Graph Generation
# =============================================================================


@st.composite
def simple_graph_strategy(
    draw,
    min_nodes: int = 1,
    max_nodes: int = 20,
    min_edge_prob: float = 0.1,
    max_edge_prob: float = 0.8,
) -> nx.Graph:
    """무작위 무방향 그래프 생성 전략.
    
    Erdős–Rényi G(n, p) 모델을 사용하여 그래프를 생성한다.
    
    Args:
        draw: Hypothesis draw 함수
        min_nodes: 최소 노드 수
        max_nodes: 최대 노드 수
        min_edge_prob: 최소 edge 생성 확률
        max_edge_prob: 최대 edge 생성 확률
        
    Returns:
        NetworkX 무방향 그래프
    """
    n_nodes = draw(st.integers(min_value=min_nodes, max_value=max_nodes))
    edge_prob = draw(st.floats(min_value=min_edge_prob, max_value=max_edge_prob))
    
    # 재현성을 위한 seed
    seed = draw(st.integers(min_value=0, max_value=10000))
    
    G = nx.gnp_random_graph(n_nodes, edge_prob, seed=seed)
    
    # 노드에 문자열 이름 부여 (실제 데이터와 유사하게)
    mapping = {i: f"Node_{i}" for i in G.nodes()}
    G = nx.relabel_nodes(G, mapping)
    
    return G


@st.composite
def connected_graph_strategy(
    draw,
    min_nodes: int = 3,
    max_nodes: int = 15,
) -> nx.Graph:
    """연결된 무방향 그래프 생성 전략.
    
    연결 그래프가 필요한 테스트 케이스를 위해 사용한다.
    
    Args:
        draw: Hypothesis draw 함수
        min_nodes: 최소 노드 수
        max_nodes: 최대 노드 수
        
    Returns:
        연결된 NetworkX 무방향 그래프
    """
    n_nodes = draw(st.integers(min_value=min_nodes, max_value=max_nodes))
    seed = draw(st.integers(min_value=0, max_value=10000))
    
    # 연결 그래프 생성 (random_labeled_tree 사용)
    G = nx.random_labeled_tree(n_nodes, seed=seed)
    
    # 추가 edge 생성 (선택적)
    extra_edges = draw(st.integers(min_value=0, max_value=n_nodes))
    nodes = list(G.nodes())
    for _ in range(extra_edges):
        u = draw(st.sampled_from(nodes))
        v = draw(st.sampled_from(nodes))
        if u != v and not G.has_edge(u, v):
            G.add_edge(u, v)
    
    # 노드에 문자열 이름 부여
    mapping = {i: f"Company_{i}" for i in G.nodes()}
    G = nx.relabel_nodes(G, mapping)
    
    return G


@st.composite
def weighted_graph_strategy(
    draw,
    min_nodes: int = 3,
    max_nodes: int = 15,
    min_weight: int = 1,
    max_weight: int = 10,
) -> nx.Graph:
    """가중치가 있는 연결 그래프 생성 전략.
    
    MST 테스트를 위해 edge에 Weight 속성을 추가한다.
    
    Args:
        draw: Hypothesis draw 함수
        min_nodes: 최소 노드 수
        max_nodes: 최대 노드 수
        min_weight: 최소 edge weight
        max_weight: 최대 edge weight
        
    Returns:
        가중치가 있는 연결된 NetworkX 무방향 그래프
    """
    n_nodes = draw(st.integers(min_value=min_nodes, max_value=max_nodes))
    seed = draw(st.integers(min_value=0, max_value=10000))
    
    # 연결 그래프 생성 (random_labeled_tree 사용)
    G = nx.random_labeled_tree(n_nodes, seed=seed)
    
    # 추가 edge 생성
    extra_edges = draw(st.integers(min_value=0, max_value=n_nodes * 2))
    nodes = list(G.nodes())
    for _ in range(extra_edges):
        u = draw(st.sampled_from(nodes))
        v = draw(st.sampled_from(nodes))
        if u != v and not G.has_edge(u, v):
            G.add_edge(u, v)
    
    # 각 edge에 가중치 부여
    for u, v in G.edges():
        weight = draw(st.integers(min_value=min_weight, max_value=max_weight))
        G[u][v]["Weight"] = weight
    
    # 노드에 문자열 이름 부여
    mapping = {i: f"Firm_{i}" for i in G.nodes()}
    G = nx.relabel_nodes(G, mapping)
    
    return G


@st.composite
def edge_df_strategy(
    draw,
    min_edges: int = 3,
    max_edges: int = 30,
    min_weight: int = 1,
    max_weight: int = 10,
) -> pd.DataFrame:
    """Edge list DataFrame 생성 전략.
    
    Args:
        draw: Hypothesis draw 함수
        min_edges: 최소 edge 수
        max_edges: 최대 edge 수
        min_weight: 최소 weight
        max_weight: 최대 weight
        
    Returns:
        Edge list DataFrame (Source, Target, Weight 컬럼)
    """
    n_edges = draw(st.integers(min_value=min_edges, max_value=max_edges))
    
    # 노드 풀 생성
    n_nodes = draw(st.integers(min_value=3, max_value=min(15, n_edges + 2)))
    nodes = [f"Entity_{i}" for i in range(n_nodes)]
    
    edges = []
    seen = set()
    
    for _ in range(n_edges):
        u = draw(st.sampled_from(nodes))
        v = draw(st.sampled_from(nodes))
        if u != v:
            # 정규화 (Source < Target)
            edge = tuple(sorted([u, v]))
            if edge not in seen:
                seen.add(edge)
                weight = draw(st.integers(min_value=min_weight, max_value=max_weight))
                edges.append({
                    "Source": edge[0],
                    "Target": edge[1],
                    "Weight": weight,
                })
    
    # 최소 1개 edge는 있어야 함
    if len(edges) == 0:
        u, v = nodes[0], nodes[1]
        edges.append({
            "Source": u,
            "Target": v,
            "Weight": draw(st.integers(min_value=min_weight, max_value=max_weight)),
        })
    
    return pd.DataFrame(edges)


# =============================================================================
# Property 16: NetworkStatistics 계산 정확성 테스트
# =============================================================================


class TestNetworkStatisticsProperty:
    """NetworkStatistics Property 테스트.
    
    **Validates: Requirements 10.1, 10.2, 10.3**
    
    Property 16: 네트워크 통계 계산 정확성 테스트
    - 노드 수, edge 수가 정확히 계산되어야 함
    - density = 2 * edges / (nodes * (nodes - 1))
    - LCC 노드 수 2개 미만 시 diameter, avg_path_length는 None
    """
    
    @pytest.fixture
    def statistics_analyzer(self) -> NetworkStatistics:
        """테스트용 NetworkStatistics 인스턴스."""
        return NetworkStatistics()
    
    @given(G=simple_graph_strategy(min_nodes=1, max_nodes=20))
    @HYPOTHESIS_SETTINGS
    def test_nodes_edges_accuracy(self, G: nx.Graph):
        """노드 수와 edge 수 정확성 테스트.
        
        **Validates: Requirements 10.1**
        
        Property: stats.nodes == G.number_of_nodes() and stats.edges == G.number_of_edges()
        """
        statistics_analyzer = NetworkStatistics()
        stats = statistics_analyzer.compute(G)
        
        assert stats.nodes == G.number_of_nodes(), \
            f"노드 수 불일치: expected {G.number_of_nodes()}, got {stats.nodes}"
        assert stats.edges == G.number_of_edges(), \
            f"Edge 수 불일치: expected {G.number_of_edges()}, got {stats.edges}"
    
    @given(G=simple_graph_strategy(min_nodes=2, max_nodes=20))
    @HYPOTHESIS_SETTINGS
    def test_density_accuracy(self, G: nx.Graph):
        """밀도 계산 정확성 테스트.
        
        **Validates: Requirements 10.1**
        
        Property: density = 2 * edges / (nodes * (nodes - 1)) for undirected graphs
        """
        statistics_analyzer = NetworkStatistics()
        stats = statistics_analyzer.compute(G)
        
        n = G.number_of_nodes()
        e = G.number_of_edges()
        
        if n <= 1:
            expected_density = 0.0
        else:
            expected_density = 2 * e / (n * (n - 1))
        
        assert abs(stats.density - expected_density) < 1e-5, \
            f"밀도 불일치: expected {expected_density}, got {stats.density}"
    
    @given(G=simple_graph_strategy(min_nodes=1, max_nodes=15))
    @HYPOTHESIS_SETTINGS
    def test_avg_degree_accuracy(self, G: nx.Graph):
        """평균 degree 계산 정확성 테스트.
        
        **Validates: Requirements 10.1**
        
        Property: avg_degree = 2 * edges / nodes (handshaking lemma)
        """
        statistics_analyzer = NetworkStatistics()
        stats = statistics_analyzer.compute(G)
        
        n = G.number_of_nodes()
        e = G.number_of_edges()
        
        if n == 0:
            expected_avg_degree = 0.0
        else:
            expected_avg_degree = 2 * e / n
        
        assert abs(stats.avg_degree - round(expected_avg_degree, 4)) < 1e-3, \
            f"평균 degree 불일치: expected {expected_avg_degree}, got {stats.avg_degree}"
    
    @given(G=simple_graph_strategy(min_nodes=1, max_nodes=15, min_edge_prob=0.0, max_edge_prob=0.3))
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_connected_components_accuracy(self, G: nx.Graph):
        """연결 컴포넌트 수 정확성 테스트.
        
        **Validates: Requirements 10.1**
        """
        statistics_analyzer = NetworkStatistics()
        stats = statistics_analyzer.compute(G)
        
        if G.number_of_nodes() == 0:
            expected_cc = 0
        else:
            expected_cc = nx.number_connected_components(G)
        
        assert stats.connected_components == expected_cc, \
            f"연결 컴포넌트 수 불일치: expected {expected_cc}, got {stats.connected_components}"
    
    def test_lcc_path_metrics_with_small_lcc(self):
        """LCC 노드 수 2개 미만 시 path metrics null 처리 테스트.
        
        **Validates: Requirements 10.3**
        
        Property: LCC < 2 => diameter is None and avg_path_length is None
        """
        statistics_analyzer = NetworkStatistics()
        
        # 단일 노드 그래프
        G1 = nx.Graph()
        G1.add_node("A")
        
        stats1 = statistics_analyzer.compute(G1)
        assert stats1.diameter is None, "단일 노드 그래프의 diameter는 None이어야 함"
        assert stats1.avg_path_length is None, "단일 노드 그래프의 avg_path_length는 None이어야 함"
        
        # 빈 그래프
        G2 = nx.Graph()
        
        stats2 = statistics_analyzer.compute(G2)
        assert stats2.diameter is None, "빈 그래프의 diameter는 None이어야 함"
        assert stats2.avg_path_length is None, "빈 그래프의 avg_path_length는 None이어야 함"
    
    @given(G=connected_graph_strategy(min_nodes=3, max_nodes=12))
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_path_metrics_on_connected_graph(self, G: nx.Graph):
        """연결 그래프에서 path metrics 정확성 테스트.
        
        **Validates: Requirements 10.2**
        
        Property: 연결 그래프에서 diameter >= 1 and avg_path_length >= 1
        """
        statistics_analyzer = NetworkStatistics()
        stats = statistics_analyzer.compute(G)
        
        # 연결 그래프이므로 LCC = 전체 그래프
        assert stats.lcc_nodes == G.number_of_nodes(), \
            "연결 그래프에서 LCC 노드 수는 전체 노드 수와 같아야 함"
        
        # diameter와 avg_path_length가 계산되어야 함
        assert stats.diameter is not None, \
            "연결 그래프에서 diameter는 None이 아니어야 함"
        assert stats.avg_path_length is not None, \
            "연결 그래프에서 avg_path_length는 None이 아니어야 함"
        
        # diameter >= 1 (노드가 3개 이상인 연결 그래프)
        assert stats.diameter >= 1, \
            f"diameter는 1 이상이어야 함: {stats.diameter}"
        assert stats.avg_path_length >= 1.0, \
            f"avg_path_length는 1.0 이상이어야 함: {stats.avg_path_length}"
    
    @given(G=simple_graph_strategy(min_nodes=2, max_nodes=15))
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_clustering_coefficient_range(self, G: nx.Graph):
        """클러스터링 계수 범위 테스트.
        
        **Validates: Requirements 10.1**
        
        Property: 0 <= avg_clustering_coefficient <= 1
        """
        statistics_analyzer = NetworkStatistics()
        stats = statistics_analyzer.compute(G)
        
        assert 0.0 <= stats.avg_clustering_coefficient <= 1.0, \
            f"클러스터링 계수 범위 오류: {stats.avg_clustering_coefficient}"


class TestNetworkStatisticsUnit:
    """NetworkStatistics 단위 테스트."""
    
    @pytest.fixture
    def statistics_analyzer(self) -> NetworkStatistics:
        """테스트용 NetworkStatistics 인스턴스."""
        return NetworkStatistics()
    
    def test_empty_graph(self, statistics_analyzer: NetworkStatistics):
        """빈 그래프 통계 테스트."""
        G = nx.Graph()
        stats = statistics_analyzer.compute(G)
        
        assert stats.nodes == 0
        assert stats.edges == 0
        assert stats.density == 0.0
        assert stats.avg_degree == 0.0
        assert stats.connected_components == 0
        assert stats.diameter is None
        assert stats.avg_path_length is None
    
    def test_single_edge_graph(self, statistics_analyzer: NetworkStatistics):
        """단일 edge 그래프 통계 테스트."""
        G = nx.Graph()
        G.add_edge("A", "B", Weight=5)
        
        stats = statistics_analyzer.compute(G)
        
        assert stats.nodes == 2
        assert stats.edges == 1
        assert stats.weighted_edges == 5
        assert stats.density == 1.0  # 완전 연결
        assert stats.avg_degree == 1.0  # 각 노드가 degree 1
        assert stats.diameter == 1
        assert stats.avg_path_length == 1.0
    
    def test_complete_graph(self, statistics_analyzer: NetworkStatistics):
        """완전 그래프 통계 테스트."""
        G = nx.complete_graph(5)
        
        # 노드 이름 변경
        mapping = {i: f"Node_{i}" for i in G.nodes()}
        G = nx.relabel_nodes(G, mapping)
        
        stats = statistics_analyzer.compute(G)
        
        assert stats.nodes == 5
        assert stats.edges == 10  # 5C2 = 10
        assert stats.density == 1.0  # 완전 그래프
        assert stats.diameter == 1
        assert stats.avg_path_length == 1.0
    
    def test_path_graph(self, statistics_analyzer: NetworkStatistics):
        """경로 그래프 통계 테스트."""
        G = nx.path_graph(5)
        
        # 노드 이름 변경
        mapping = {i: f"Node_{i}" for i in G.nodes()}
        G = nx.relabel_nodes(G, mapping)
        
        stats = statistics_analyzer.compute(G)
        
        assert stats.nodes == 5
        assert stats.edges == 4
        assert stats.diameter == 4  # 경로 그래프의 diameter = n - 1
        # 경로 그래프의 평균 경로 길이 = (n+1) / 3 for n > 1
        expected_avg_path = (5 + 1) / 3
        assert abs(stats.avg_path_length - expected_avg_path) < 1e-3
    
    def test_modularity_passthrough(self, statistics_analyzer: NetworkStatistics):
        """modularity 값 전달 테스트."""
        G = nx.Graph()
        G.add_edges_from([("A", "B"), ("B", "C"), ("C", "A")])
        
        # modularity 값을 외부에서 전달
        stats = statistics_analyzer.compute(G, modularity=0.75)
        
        assert stats.modularity == 0.75


# =============================================================================
# Property 17: CentralityAnalyzer 정규화 테스트
# =============================================================================


class TestCentralityAnalyzerProperty:
    """CentralityAnalyzer Property 테스트.
    
    **Validates: Requirements 11.1, 11.2**
    
    Property 17: 중심성 정규화 테스트
    - 모든 중심성 값은 0~1 범위 내에 있어야 함
    - 비가중(unweighted) 중심성 계산
    """
    
    @pytest.fixture
    def centrality_analyzer(self) -> CentralityAnalyzer:
        """테스트용 CentralityAnalyzer 인스턴스."""
        return CentralityAnalyzer(eigenvector_max_iter=1000)
    
    @given(G=connected_graph_strategy(min_nodes=3, max_nodes=15))
    @HYPOTHESIS_SETTINGS
    def test_centrality_normalized_range(self, G: nx.Graph):
        """모든 중심성 값이 0~1 범위 내에 있는지 테스트.
        
        **Validates: Requirements 11.2**
        
        Property: 0 <= centrality <= 1 for all centrality types
        """
        centrality_analyzer = CentralityAnalyzer(eigenvector_max_iter=1000)
        df = centrality_analyzer.compute_all(G)
        
        # Degree centrality
        assert df["degree_centrality"].min() >= 0.0, \
            "Degree centrality 최소값이 0 미만"
        assert df["degree_centrality"].max() <= 1.0, \
            "Degree centrality 최대값이 1 초과"
        
        # Betweenness centrality
        assert df["betweenness_centrality"].min() >= 0.0, \
            "Betweenness centrality 최소값이 0 미만"
        assert df["betweenness_centrality"].max() <= 1.0, \
            "Betweenness centrality 최대값이 1 초과"
        
        # Closeness centrality
        assert df["closeness_centrality"].min() >= 0.0, \
            "Closeness centrality 최소값이 0 미만"
        assert df["closeness_centrality"].max() <= 1.0, \
            "Closeness centrality 최대값이 1 초과"
        
        # Eigenvector centrality (None이 아닌 경우)
        eigenvector_values = df["eigenvector_centrality"].dropna()
        if len(eigenvector_values) > 0:
            assert eigenvector_values.min() >= 0.0, \
                "Eigenvector centrality 최소값이 0 미만"
            assert eigenvector_values.max() <= 1.0, \
                "Eigenvector centrality 최대값이 1 초과"
    
    @given(G=connected_graph_strategy(min_nodes=3, max_nodes=12))
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_centrality_has_max_one(self, G: nx.Graph):
        """정규화 후 각 중심성 유형에 최대값 1을 가진 노드가 존재하는지 테스트.
        
        **Validates: Requirements 11.2**
        
        Property: 정규화된 중심성에서 max == 1.0 (모든 값이 같으면 0.0 허용)
        
        Note:
            - 모든 노드의 degree가 동일한 경우(예: 완전 그래프), 
              Min-Max 정규화 후 모든 값이 0.0이 됨 (max - min == 0이므로).
            - 이 경우 max == 0.0이 정당함.
        """
        # 엣지가 있는 그래프에서만 의미가 있음
        assume(G.number_of_edges() > 0)
        
        centrality_analyzer = CentralityAnalyzer(eigenvector_max_iter=1000)
        df = centrality_analyzer.compute_all(G)
        
        # 노드가 2개 이상일 때만 정규화 의미가 있음
        if len(G) >= 2:
            # 모든 노드의 degree가 같으면 정규화 후 전부 0.0 (max == 0.0 허용)
            # 그렇지 않으면 max == 1.0
            degree_max = df["degree_centrality"].max()
            assert degree_max == 0.0 or abs(degree_max - 1.0) < 1e-5, \
                f"Degree centrality 최대값이 0.0 또는 1.0이 아님: {degree_max}"
            
            closeness_max = df["closeness_centrality"].max()
            assert closeness_max == 0.0 or abs(closeness_max - 1.0) < 1e-5, \
                f"Closeness centrality 최대값이 0.0 또는 1.0이 아님: {closeness_max}"
    
    @given(G=simple_graph_strategy(min_nodes=2, max_nodes=12))
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_centrality_node_count_matches(self, G: nx.Graph):
        """중심성 DataFrame의 행 수가 노드 수와 일치하는지 테스트.
        
        Property: len(df) == G.number_of_nodes()
        """
        centrality_analyzer = CentralityAnalyzer(eigenvector_max_iter=1000)
        df = centrality_analyzer.compute_all(G)
        
        assert len(df) == G.number_of_nodes(), \
            f"DataFrame 행 수({len(df)})가 노드 수({G.number_of_nodes()})와 불일치"


class TestCentralityAnalyzerUnit:
    """CentralityAnalyzer 단위 테스트."""
    
    @pytest.fixture
    def centrality_analyzer(self) -> CentralityAnalyzer:
        """테스트용 CentralityAnalyzer 인스턴스."""
        return CentralityAnalyzer(eigenvector_max_iter=1000)
    
    def test_empty_graph(self, centrality_analyzer: CentralityAnalyzer):
        """빈 그래프 중심성 테스트."""
        G = nx.Graph()
        df = centrality_analyzer.compute_all(G)
        
        assert len(df) == 0
        assert "node" in df.columns
        assert "degree_centrality" in df.columns
    
    def test_single_node_graph(self, centrality_analyzer: CentralityAnalyzer):
        """단일 노드 그래프 중심성 테스트."""
        G = nx.Graph()
        G.add_node("A")
        
        df = centrality_analyzer.compute_all(G)
        
        assert len(df) == 1
        assert df.iloc[0]["node"] == "A"
        # 단일 노드는 중심성이 의미가 제한적이지만, 정규화 후 1.0
        assert df.iloc[0]["degree_centrality"] == 1.0
    
    def test_star_graph_centrality(self, centrality_analyzer: CentralityAnalyzer):
        """스타 그래프 중심성 테스트."""
        # 스타 그래프: 중심 노드가 모든 주변 노드와 연결
        G = nx.star_graph(4)
        
        # 노드 이름 변경 (0이 중심)
        mapping = {i: f"Node_{i}" for i in G.nodes()}
        G = nx.relabel_nodes(G, mapping)
        
        df = centrality_analyzer.compute_all(G)
        
        # 중심 노드 (Node_0)가 가장 높은 degree centrality를 가져야 함
        center_row = df[df["node"] == "Node_0"]
        leaf_rows = df[df["node"] != "Node_0"]
        
        assert center_row["degree_centrality"].values[0] == 1.0, \
            "스타 그래프 중심 노드의 degree centrality는 1이어야 함"
        
        # 모든 leaf 노드는 동일한 degree centrality를 가져야 함
        assert leaf_rows["degree_centrality"].nunique() == 1, \
            "스타 그래프의 모든 leaf 노드는 동일한 degree centrality를 가져야 함"
    
    def test_eigenvector_convergence_handling(self, centrality_analyzer: CentralityAnalyzer):
        """Eigenvector centrality 수렴 실패 처리 테스트.
        
        **Validates: Requirements 11.3**
        """
        # 정상 그래프에서는 수렴해야 함
        G = nx.complete_graph(5)
        mapping = {i: f"Node_{i}" for i in G.nodes()}
        G = nx.relabel_nodes(G, mapping)
        
        df = centrality_analyzer.compute_all(G)
        
        # Eigenvector centrality가 계산되어야 함 (None이 아님)
        assert df["eigenvector_centrality"].notna().all(), \
            "완전 그래프에서 eigenvector centrality는 수렴해야 함"
    
    def test_unweighted_centrality(self, centrality_analyzer: CentralityAnalyzer):
        """비가중 중심성 계산 테스트.
        
        **Validates: Requirements 11.1**
        """
        # 가중치가 있는 그래프
        G = nx.Graph()
        G.add_edge("A", "B", Weight=10)
        G.add_edge("B", "C", Weight=1)
        G.add_edge("A", "C", Weight=5)
        
        df = centrality_analyzer.compute_all(G)
        
        # 비가중 중심성이므로 모든 노드가 동일한 degree centrality를 가져야 함
        # (모두 degree 2)
        assert df["degree_centrality"].nunique() == 1, \
            "동일 degree 노드는 동일한 degree centrality를 가져야 함"


# =============================================================================
# Property 18: Maximum Spanning Tree 속성 테스트
# =============================================================================


class TestAdvancedAnalyzerMSTProperty:
    """AdvancedAnalyzer MST Property 테스트.
    
    **Validates: Requirements 12.3**
    
    Property 18: Maximum Spanning Tree 속성 테스트
    - MST는 n-1개의 edge를 가짐 (n은 연결 컴포넌트의 노드 수)
    - MST는 사이클이 없어야 함
    - MST는 모든 노드를 연결해야 함 (연결 컴포넌트 내)
    """
    
    @pytest.fixture
    def advanced_analyzer(self) -> AdvancedAnalyzer:
        """테스트용 AdvancedAnalyzer 인스턴스."""
        return AdvancedAnalyzer(random_network_samples=10)
    
    @given(G=weighted_graph_strategy(min_nodes=3, max_nodes=15))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_mst_edge_count(self, G: nx.Graph):
        """MST의 edge 수가 n-1인지 테스트.
        
        **Validates: Requirements 12.3**
        
        Property: MST.number_of_edges() == MST.number_of_nodes() - 1
        """
        advanced_analyzer = AdvancedAnalyzer(random_network_samples=10)
        mst = advanced_analyzer.extract_mst(G)
        
        n = mst.number_of_nodes()
        e = mst.number_of_edges()
        
        # 트리 속성: edge 수 = 노드 수 - 1
        if n > 0:
            assert e == n - 1, \
                f"MST edge 수 오류: expected {n - 1}, got {e}"
    
    @given(G=weighted_graph_strategy(min_nodes=3, max_nodes=12))
    @settings(max_examples=40, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_mst_no_cycles(self, G: nx.Graph):
        """MST에 사이클이 없는지 테스트.
        
        **Validates: Requirements 12.3**
        
        Property: MST is acyclic (is_tree or is_forest)
        """
        advanced_analyzer = AdvancedAnalyzer(random_network_samples=10)
        mst = advanced_analyzer.extract_mst(G)
        
        # 빈 그래프 처리
        if mst.number_of_nodes() == 0:
            return
        
        # 트리 또는 포레스트인지 확인 (사이클 없음)
        assert nx.is_tree(mst) or nx.is_forest(mst), \
            "MST에 사이클이 있음"
    
    @given(G=connected_graph_strategy(min_nodes=3, max_nodes=12))
    @settings(max_examples=40, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_mst_connects_all_nodes(self, G: nx.Graph):
        """MST가 모든 노드를 연결하는지 테스트 (연결 그래프에서).
        
        **Validates: Requirements 12.3**
        
        Property: 연결 그래프의 MST는 연결됨
        """
        # 먼저 edge에 weight 추가
        import random
        random.seed(42)
        for u, v in G.edges():
            G[u][v]["Weight"] = random.randint(1, 10)
        
        advanced_analyzer = AdvancedAnalyzer(random_network_samples=10)
        mst = advanced_analyzer.extract_mst(G)
        
        # 원본 그래프가 연결되어 있으면 MST도 연결되어야 함
        assert nx.is_connected(mst), \
            "연결 그래프의 MST가 연결되지 않음"
        
        # MST 노드 수 == 원본 그래프 노드 수
        assert mst.number_of_nodes() == G.number_of_nodes(), \
            f"MST 노드 수({mst.number_of_nodes()})가 원본({G.number_of_nodes()})과 불일치"
    
    @given(G=weighted_graph_strategy(min_nodes=4, max_nodes=10))
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
    def test_mst_is_maximum(self, G: nx.Graph):
        """MST가 Maximum인지 테스트 (weight 합이 최대).
        
        **Validates: Requirements 12.3**
        
        Property: MST의 weight 합 >= 다른 spanning tree의 weight 합
        """
        advanced_analyzer = AdvancedAnalyzer(random_network_samples=10)
        mst = advanced_analyzer.extract_mst(G)
        
        # MST weight 합 계산
        mst_weight = sum(data.get("Weight", 1) for u, v, data in mst.edges(data=True))
        
        # Minimum spanning tree와 비교
        min_st = nx.minimum_spanning_tree(G, weight="Weight")
        min_st_weight = sum(data.get("Weight", 1) for u, v, data in min_st.edges(data=True))
        
        # Maximum >= Minimum
        assert mst_weight >= min_st_weight, \
            f"MST weight({mst_weight})가 MinST weight({min_st_weight})보다 작음"


class TestAdvancedAnalyzerMSTUnit:
    """AdvancedAnalyzer MST 단위 테스트."""
    
    @pytest.fixture
    def advanced_analyzer(self) -> AdvancedAnalyzer:
        """테스트용 AdvancedAnalyzer 인스턴스."""
        return AdvancedAnalyzer(random_network_samples=10)
    
    def test_empty_graph_mst(self, advanced_analyzer: AdvancedAnalyzer):
        """빈 그래프 MST 테스트."""
        G = nx.Graph()
        mst = advanced_analyzer.extract_mst(G)
        
        assert mst.number_of_nodes() == 0
        assert mst.number_of_edges() == 0
    
    def test_single_edge_mst(self, advanced_analyzer: AdvancedAnalyzer):
        """단일 edge MST 테스트."""
        G = nx.Graph()
        G.add_edge("A", "B", Weight=5)
        
        mst = advanced_analyzer.extract_mst(G)
        
        assert mst.number_of_nodes() == 2
        assert mst.number_of_edges() == 1
        assert mst.has_edge("A", "B")
    
    def test_complete_graph_mst(self, advanced_analyzer: AdvancedAnalyzer):
        """완전 그래프 MST 테스트."""
        G = nx.complete_graph(5)
        
        # 노드 이름 변경 및 weight 부여
        mapping = {i: f"Node_{i}" for i in G.nodes()}
        G = nx.relabel_nodes(G, mapping)
        
        # 가중치 부여 (다양한 값)
        weights = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        for i, (u, v) in enumerate(G.edges()):
            G[u][v]["Weight"] = weights[i % len(weights)]
        
        mst = advanced_analyzer.extract_mst(G)
        
        # 완전 그래프의 MST는 정확히 n-1 = 4개의 edge
        assert mst.number_of_nodes() == 5
        assert mst.number_of_edges() == 4
        assert nx.is_tree(mst)
    
    def test_disconnected_graph_mst(self, advanced_analyzer: AdvancedAnalyzer):
        """비연결 그래프 MST 테스트 (Forest 반환)."""
        G = nx.Graph()
        G.add_edge("A", "B", Weight=5)
        G.add_edge("C", "D", Weight=3)
        
        mst = advanced_analyzer.extract_mst(G)
        
        # 비연결 그래프의 MST는 Forest (여러 트리)
        assert mst.number_of_nodes() == 4
        assert mst.number_of_edges() == 2  # 각 컴포넌트가 1개 edge
        assert nx.is_forest(mst)
        assert nx.number_connected_components(mst) == 2


# =============================================================================
# 통합 테스트
# =============================================================================


class TestAnalyzerIntegration:
    """Analyzer 모듈 통합 테스트."""
    
    @pytest.fixture
    def statistics_analyzer(self) -> NetworkStatistics:
        """테스트용 NetworkStatistics 인스턴스."""
        return NetworkStatistics()
    
    @pytest.fixture
    def centrality_analyzer(self) -> CentralityAnalyzer:
        """테스트용 CentralityAnalyzer 인스턴스."""
        return CentralityAnalyzer()
    
    @pytest.fixture
    def advanced_analyzer(self) -> AdvancedAnalyzer:
        """테스트용 AdvancedAnalyzer 인스턴스."""
        return AdvancedAnalyzer(random_network_samples=10)
    
    def test_karate_club_graph(
        self,
        statistics_analyzer: NetworkStatistics,
        centrality_analyzer: CentralityAnalyzer,
        advanced_analyzer: AdvancedAnalyzer,
    ):
        """Karate Club 그래프 전체 분석 테스트."""
        G = nx.karate_club_graph()
        
        # 통계 분석
        stats = statistics_analyzer.compute(G)
        assert stats.nodes == 34
        assert stats.edges == 78
        assert stats.density > 0
        assert stats.diameter is not None
        
        # 중심성 분석
        centrality_df = centrality_analyzer.compute_all(G)
        assert len(centrality_df) == 34
        assert centrality_df["degree_centrality"].max() == 1.0
        
        # MST 추출
        # weight 추가
        for u, v in G.edges():
            G[u][v]["Weight"] = 1
        
        mst = advanced_analyzer.extract_mst(G)
        assert mst.number_of_nodes() == 34
        assert mst.number_of_edges() == 33  # n - 1
        assert nx.is_tree(mst)
    
    def test_from_edge_df(
        self,
        statistics_analyzer: NetworkStatistics,
        centrality_analyzer: CentralityAnalyzer,
    ):
        """Edge DataFrame에서 분석 수행 테스트."""
        edge_df = pd.DataFrame({
            "Source": ["A", "B", "A"],
            "Target": ["B", "C", "C"],
            "Weight": [5, 3, 2],
        })
        
        # 통계 분석
        stats = statistics_analyzer.compute_from_edge_list(edge_df)
        assert stats.nodes == 3
        assert stats.edges == 3
        assert stats.weighted_edges == 10  # 5 + 3 + 2
        
        # 중심성 분석
        centrality_df = centrality_analyzer.compute_from_edge_list(edge_df)
        assert len(centrality_df) == 3
