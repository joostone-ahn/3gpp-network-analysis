"""
Network Statistics Module (Stage 7)

네트워크 기본 통계를 계산하는 모듈.

요구사항:
- 10.1: 네트워크 기본 지표 계산 (nodes, edges, density, avg_degree 등)
- 10.2: diameter와 avg_path_length는 가장 큰 연결 컴포넌트(LCC) 기준으로 계산
- 10.3: LCC 노드 수가 2개 미만인 경우 diameter와 avg_path_length를 null 처리 (신규 방어 로직)
- 10.4: 계산된 통계를 CSV 및 Parquet 형식으로 저장

Note:
    - modularity는 CommunityDetector.detect() 결과를 재사용하여 Louvain 중복 실행 방지
    - 원본 노트북은 LCC 노드 수 2개 미만 상황에 대한 방어 로직이 없었음
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import networkx as nx
import pandas as pd

from src.utils.config_loader import PROJECT_ROOT, AnalysisConfig, load_config
from src.utils.logger import get_logger

# 모듈 로거
logger = get_logger("analyzer", default_stage="statistics")

# 기본 저장 경로
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "data" / "results"


@dataclass
class NetworkStats:
    """네트워크 통계 데이터 클래스.
    
    네트워크의 구조적 특성을 나타내는 지표들을 포함한다.
    
    Attributes:
        nodes: 노드 수
        edges: Edge 수 (비가중)
        weighted_edges: 가중 Edge 합계 (Weight의 총합)
        avg_degree: 평균 연결 수 (degree의 평균)
        avg_weighted_degree: 평균 가중 연결 수 (weighted degree의 평균)
        density: 밀도 (실제 edge 수 / 가능한 최대 edge 수)
        connected_components: 연결 컴포넌트 수
        lcc_nodes: 가장 큰 연결 컴포넌트(LCC)의 노드 수
        diameter: 최장 최단 경로 (LCC 기준, 노드 2개 미만 시 None)
        avg_path_length: 평균 경로 길이 (LCC 기준, 노드 2개 미만 시 None)
        modularity: 모듈성 (커뮤니티 탐지 결과에서 가져옴, None 가능)
        avg_clustering_coefficient: 평균 군집 계수
    
    Example:
        >>> stats = NetworkStats(
        ...     nodes=150,
        ...     edges=450,
        ...     weighted_edges=1200,
        ...     avg_degree=6.0,
        ...     avg_weighted_degree=16.0,
        ...     density=0.04,
        ...     connected_components=3,
        ...     lcc_nodes=145,
        ...     diameter=8,
        ...     avg_path_length=3.5,
        ...     modularity=0.65,
        ...     avg_clustering_coefficient=0.35,
        ... )
    """
    nodes: int
    edges: int
    weighted_edges: int
    avg_degree: float
    avg_weighted_degree: float
    density: float
    connected_components: int
    lcc_nodes: int
    diameter: Optional[int]
    avg_path_length: Optional[float]
    modularity: Optional[float]
    avg_clustering_coefficient: float
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환.
        
        Returns:
            모든 통계 지표를 포함하는 딕셔너리
        """
        return {
            "nodes": self.nodes,
            "edges": self.edges,
            "weighted_edges": self.weighted_edges,
            "avg_degree": self.avg_degree,
            "avg_weighted_degree": self.avg_weighted_degree,
            "density": self.density,
            "connected_components": self.connected_components,
            "lcc_nodes": self.lcc_nodes,
            "diameter": self.diameter,
            "avg_path_length": self.avg_path_length,
            "modularity": self.modularity,
            "avg_clustering_coefficient": self.avg_clustering_coefficient,
        }
    
    def to_series(self) -> pd.Series:
        """Pandas Series로 변환.
        
        Returns:
            모든 통계 지표를 포함하는 Series
        """
        return pd.Series(self.to_dict())


class NetworkStatistics:
    """네트워크 기본 통계 계산 클래스.
    
    NetworkX 그래프에 대해 다양한 통계 지표를 계산한다.
    
    계산 지표:
        - 기본 지표: nodes, edges, weighted_edges
        - 연결성 지표: avg_degree, avg_weighted_degree, density
        - 컴포넌트 지표: connected_components, lcc_nodes
        - 경로 지표: diameter, avg_path_length (LCC 기준)
        - 클러스터링 지표: modularity, avg_clustering_coefficient
    
    Note:
        - diameter와 avg_path_length는 LCC 기준으로 계산
        - LCC 노드 수가 2개 미만인 경우 None 반환 (요구사항 10.3)
        - modularity는 외부에서 전달받아 사용 (Louvain 중복 실행 방지)
    
    Attributes:
        config: AnalysisConfig 설정 객체
        output_dir: 결과 저장 디렉토리
    
    Example:
        >>> analyzer = NetworkStatistics()
        >>> edge_df = pd.read_parquet("data/processed/company_ALL_year_2023_0.parquet")
        >>> G = analyzer.build_graph(edge_df)
        >>> stats = analyzer.compute(G)
        >>> print(f"노드 수: {stats.nodes}, Edge 수: {stats.edges}")
    """
    
    def __init__(
        self,
        config: Optional[AnalysisConfig] = None,
        output_dir: Optional[Path] = None,
    ) -> None:
        """NetworkStatistics 초기화.
        
        Args:
            config: AnalysisConfig 설정 객체. None이면 기본 설정 사용.
            output_dir: 결과 저장 디렉토리. None이면 data/results/ 사용.
        """
        if config is not None:
            self.config = config
        else:
            self.config = load_config("analysis")
        
        self.output_dir = Path(output_dir) if output_dir else DEFAULT_RESULTS_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info_with_details(
            "NetworkStatistics 초기화 완료",
            stage="statistics",
            details={
                "output_dir": str(self.output_dir),
            },
        )
    
    def build_graph(
        self,
        edge_df: pd.DataFrame,
        weight_column: str = "Weight",
    ) -> nx.Graph:
        """Edge DataFrame으로부터 NetworkX 그래프 생성.
        
        Args:
            edge_df: Edge list DataFrame (Source, Target, Weight 컬럼 필수)
            weight_column: 가중치 컬럼명 (기본: "Weight")
            
        Returns:
            NetworkX 무방향 그래프
            
        Raises:
            ValueError: 필수 컬럼이 누락된 경우
        """
        required_columns = ["Source", "Target"]
        missing = [col for col in required_columns if col not in edge_df.columns]
        if missing:
            raise ValueError(f"필수 컬럼이 누락되었습니다: {missing}")
        
        # 빈 DataFrame 처리
        if len(edge_df) == 0:
            return nx.Graph()
        
        # 그래프 생성 (가중치 포함)
        if weight_column in edge_df.columns:
            G = nx.from_pandas_edgelist(
                edge_df,
                source="Source",
                target="Target",
                edge_attr=weight_column,
            )
        else:
            G = nx.from_pandas_edgelist(
                edge_df,
                source="Source",
                target="Target",
            )
        
        return G
    
    def _get_largest_connected_component(
        self,
        G: nx.Graph,
    ) -> nx.Graph:
        """가장 큰 연결 컴포넌트(LCC) 추출.
        
        Args:
            G: NetworkX 그래프
            
        Returns:
            LCC 서브그래프
        """
        if len(G) == 0:
            return G
        
        # 가장 큰 연결 컴포넌트 추출
        largest_cc = max(nx.connected_components(G), key=len)
        return G.subgraph(largest_cc).copy()
    
    def _compute_basic_stats(
        self,
        G: nx.Graph,
        weight_column: str = "Weight",
    ) -> Dict[str, Any]:
        """기본 통계 계산.
        
        Args:
            G: NetworkX 그래프
            weight_column: 가중치 컬럼명
            
        Returns:
            기본 통계 딕셔너리
        """
        nodes = G.number_of_nodes()
        edges = G.number_of_edges()
        
        # 가중 Edge 합계
        weighted_edges = 0
        if edges > 0:
            weights = nx.get_edge_attributes(G, weight_column)
            if weights:
                weighted_edges = sum(weights.values())
            else:
                weighted_edges = edges  # 가중치 없으면 edge 수와 동일
        
        return {
            "nodes": nodes,
            "edges": edges,
            "weighted_edges": weighted_edges,
        }
    
    def _compute_degree_stats(
        self,
        G: nx.Graph,
        weight_column: str = "Weight",
    ) -> Dict[str, Any]:
        """Degree 관련 통계 계산.
        
        Args:
            G: NetworkX 그래프
            weight_column: 가중치 컬럼명
            
        Returns:
            Degree 통계 딕셔너리
        """
        nodes = G.number_of_nodes()
        
        if nodes == 0:
            return {
                "avg_degree": 0.0,
                "avg_weighted_degree": 0.0,
            }
        
        # 평균 degree
        degrees = dict(G.degree())
        avg_degree = sum(degrees.values()) / nodes
        
        # 평균 가중 degree
        weighted_degrees = dict(G.degree(weight=weight_column))
        avg_weighted_degree = sum(weighted_degrees.values()) / nodes
        
        return {
            "avg_degree": round(avg_degree, 4),
            "avg_weighted_degree": round(avg_weighted_degree, 4),
        }
    
    def _compute_density(
        self,
        G: nx.Graph,
    ) -> float:
        """밀도 계산.
        
        밀도 = 실제 edge 수 / 가능한 최대 edge 수
        최대 edge 수 = n(n-1)/2 (무방향 그래프)
        
        Args:
            G: NetworkX 그래프
            
        Returns:
            밀도 값 (0~1)
        """
        return round(nx.density(G), 6)
    
    def _compute_component_stats(
        self,
        G: nx.Graph,
    ) -> Dict[str, Any]:
        """연결 컴포넌트 통계 계산.
        
        Args:
            G: NetworkX 그래프
            
        Returns:
            컴포넌트 통계 딕셔너리
        """
        if len(G) == 0:
            return {
                "connected_components": 0,
                "lcc_nodes": 0,
            }
        
        # 연결 컴포넌트 수
        connected_components = nx.number_connected_components(G)
        
        # LCC 노드 수
        lcc = self._get_largest_connected_component(G)
        lcc_nodes = lcc.number_of_nodes()
        
        return {
            "connected_components": connected_components,
            "lcc_nodes": lcc_nodes,
        }
    
    def _compute_path_stats(
        self,
        G: nx.Graph,
    ) -> Dict[str, Any]:
        """경로 관련 통계 계산 (LCC 기준).
        
        diameter와 avg_path_length는 LCC 기준으로 계산한다.
        LCC 노드 수가 2개 미만인 경우 None 반환 (요구사항 10.3).
        
        Args:
            G: NetworkX 그래프
            
        Returns:
            경로 통계 딕셔너리 (diameter, avg_path_length)
        """
        if len(G) == 0:
            logger.warning_with_details(
                "빈 그래프: diameter와 avg_path_length를 계산할 수 없습니다.",
                stage="statistics",
            )
            return {
                "diameter": None,
                "avg_path_length": None,
            }
        
        # LCC 추출
        lcc = self._get_largest_connected_component(G)
        lcc_nodes = lcc.number_of_nodes()
        
        # LCC 노드 수 2개 미만 시 null 처리 (요구사항 10.3)
        if lcc_nodes < 2:
            logger.warning_with_details(
                f"LCC 노드 수가 2개 미만({lcc_nodes}): "
                f"diameter와 avg_path_length를 null 처리합니다.",
                stage="statistics",
                details={"lcc_nodes": lcc_nodes},
            )
            return {
                "diameter": None,
                "avg_path_length": None,
            }
        
        try:
            # diameter 계산
            diameter = nx.diameter(lcc)
            
            # 평균 경로 길이 계산
            avg_path_length = nx.average_shortest_path_length(lcc)
            
            return {
                "diameter": diameter,
                "avg_path_length": round(avg_path_length, 4),
            }
            
        except nx.NetworkXError as e:
            logger.error_with_details(
                f"경로 통계 계산 중 오류 발생: {e}",
                stage="statistics",
                details={"error": str(e), "lcc_nodes": lcc_nodes},
            )
            return {
                "diameter": None,
                "avg_path_length": None,
            }
    
    def _compute_clustering_coefficient(
        self,
        G: nx.Graph,
    ) -> float:
        """평균 군집 계수 계산.
        
        Args:
            G: NetworkX 그래프
            
        Returns:
            평균 군집 계수 (0~1)
        """
        if len(G) == 0:
            return 0.0
        
        return round(nx.average_clustering(G), 4)
    
    def compute(
        self,
        G: nx.Graph,
        modularity: Optional[float] = None,
        weight_column: str = "Weight",
    ) -> NetworkStats:
        """모든 네트워크 통계 계산.
        
        NetworkX 그래프에 대해 모든 통계 지표를 계산한다.
        
        Args:
            G: NetworkX 그래프
            modularity: 모듈성 값 (CommunityDetector.detect() 결과에서 가져옴).
                       None이면 modularity 통계는 None으로 설정.
                       Louvain 중복 실행을 방지하기 위해 외부에서 전달.
            weight_column: 가중치 컬럼명
            
        Returns:
            NetworkStats 데이터 클래스 객체
            
        Example:
            >>> analyzer = NetworkStatistics()
            >>> G = nx.karate_club_graph()
            >>> stats = analyzer.compute(G)
            >>> print(f"노드: {stats.nodes}, Edge: {stats.edges}")
        """
        logger.info_with_details(
            f"네트워크 통계 계산 시작: 노드 {G.number_of_nodes()}, Edge {G.number_of_edges()}",
            stage="statistics",
        )
        
        # 기본 통계
        basic_stats = self._compute_basic_stats(G, weight_column)
        
        # Degree 통계
        degree_stats = self._compute_degree_stats(G, weight_column)
        
        # 밀도
        density = self._compute_density(G)
        
        # 컴포넌트 통계
        component_stats = self._compute_component_stats(G)
        
        # 경로 통계 (LCC 기준)
        path_stats = self._compute_path_stats(G)
        
        # 군집 계수
        avg_clustering_coefficient = self._compute_clustering_coefficient(G)
        
        # NetworkStats 객체 생성
        stats = NetworkStats(
            nodes=basic_stats["nodes"],
            edges=basic_stats["edges"],
            weighted_edges=basic_stats["weighted_edges"],
            avg_degree=degree_stats["avg_degree"],
            avg_weighted_degree=degree_stats["avg_weighted_degree"],
            density=density,
            connected_components=component_stats["connected_components"],
            lcc_nodes=component_stats["lcc_nodes"],
            diameter=path_stats["diameter"],
            avg_path_length=path_stats["avg_path_length"],
            modularity=modularity,
            avg_clustering_coefficient=avg_clustering_coefficient,
        )
        
        logger.info_with_details(
            f"네트워크 통계 계산 완료",
            stage="statistics",
            details=stats.to_dict(),
        )
        
        return stats
    
    def compute_from_edge_list(
        self,
        edge_df: pd.DataFrame,
        modularity: Optional[float] = None,
        weight_column: str = "Weight",
    ) -> NetworkStats:
        """Edge DataFrame에서 직접 통계 계산.
        
        편의 메서드로, 내부적으로 그래프를 생성한 후 통계를 계산한다.
        
        Args:
            edge_df: Edge list DataFrame
            modularity: 모듈성 값 (외부에서 전달)
            weight_column: 가중치 컬럼명
            
        Returns:
            NetworkStats 데이터 클래스 객체
        """
        G = self.build_graph(edge_df, weight_column)
        return self.compute(G, modularity, weight_column)
    
    def save_stats(
        self,
        stats: NetworkStats,
        filename_prefix: str,
        include_csv: bool = True,
        include_parquet: bool = True,
    ) -> Dict[str, Path]:
        """통계 결과 저장.
        
        Args:
            stats: NetworkStats 객체
            filename_prefix: 파일명 prefix (예: "stats_ALL_year_2023")
            include_csv: CSV 형식 저장 여부
            include_parquet: Parquet 형식 저장 여부
            
        Returns:
            저장된 파일 경로 딕셔너리
        """
        saved_files: Dict[str, Path] = {}
        
        # DataFrame으로 변환 (단일 행)
        df = pd.DataFrame([stats.to_dict()])
        
        if include_csv:
            csv_path = self.output_dir / f"{filename_prefix}.csv"
            df.to_csv(csv_path, index=False)
            saved_files["csv"] = csv_path
            logger.debug_with_details(
                f"CSV 저장 완료: {csv_path}",
                stage="statistics",
            )
        
        if include_parquet:
            parquet_path = self.output_dir / f"{filename_prefix}.parquet"
            df.to_parquet(parquet_path, index=False)
            saved_files["parquet"] = parquet_path
            logger.debug_with_details(
                f"Parquet 저장 완료: {parquet_path}",
                stage="statistics",
            )
        
        return saved_files
    
    def compute_batch(
        self,
        edge_dfs: Dict[str, pd.DataFrame],
        modularity_values: Optional[Dict[str, float]] = None,
        weight_column: str = "Weight",
    ) -> Dict[str, NetworkStats]:
        """여러 네트워크에 대해 일괄 통계 계산.
        
        Args:
            edge_dfs: {식별자: Edge DataFrame} 딕셔너리
            modularity_values: {식별자: modularity} 딕셔너리 (선택)
            weight_column: 가중치 컬럼명
            
        Returns:
            {식별자: NetworkStats} 딕셔너리
        """
        results: Dict[str, NetworkStats] = {}
        modularity_values = modularity_values or {}
        
        for key, edge_df in edge_dfs.items():
            try:
                modularity = modularity_values.get(key)
                stats = self.compute_from_edge_list(edge_df, modularity, weight_column)
                results[key] = stats
            except Exception as e:
                logger.error_with_details(
                    f"통계 계산 실패: {key}",
                    stage="statistics",
                    details={"error": str(e)},
                )
        
        return results
    
    def to_dataframe(
        self,
        stats_dict: Dict[str, NetworkStats],
    ) -> pd.DataFrame:
        """여러 NetworkStats를 DataFrame으로 변환.
        
        Args:
            stats_dict: {식별자: NetworkStats} 딕셔너리
            
        Returns:
            통합 DataFrame (각 행이 하나의 네트워크 통계)
        """
        rows = []
        for key, stats in stats_dict.items():
            row = stats.to_dict()
            row["network_id"] = key
            rows.append(row)
        
        df = pd.DataFrame(rows)
        
        # network_id를 첫 번째 컬럼으로 이동
        if "network_id" in df.columns:
            cols = ["network_id"] + [c for c in df.columns if c != "network_id"]
            df = df[cols]
        
        return df
