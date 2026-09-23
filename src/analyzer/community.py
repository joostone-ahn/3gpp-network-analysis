"""
Community Detector Module (Stage 7)

네트워크 커뮤니티 탐지를 수행하는 모듈.

요구사항:
- 11.4: Louvain 알고리즘을 random_seed 고정하여 커뮤니티 탐지
- 11.5: 각 노드의 커뮤니티 ID와 커뮤니티별 노드 목록 기록
- 11.6: 중심성 및 커뮤니티 분석 결과를 Parquet 형식으로 저장

Note:
    - python-louvain 라이브러리 사용 (import community.community_louvain)
    - random_state=42로 재현성 보장 (요구사항 16.2)
    - 원본 노트북은 randomize=True로 비결정적이었음 (본 시스템에서 seed 고정으로 변경)
    - modularity는 NetworkStatistics가 재사용하도록 반환값에 포함 (Louvain 중복 실행 방지)
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import networkx as nx
import pandas as pd

# python-louvain 라이브러리 import
try:
    import community.community_louvain as community_louvain
except ImportError:
    raise ImportError(
        "python-louvain 라이브러리가 필요합니다. "
        "'pip install python-louvain' 명령으로 설치하세요."
    )

from src.utils.config_loader import PROJECT_ROOT, AnalysisConfig, load_config
from src.utils.logger import get_logger

# 모듈 로거
logger = get_logger("analyzer", default_stage="community")

# 기본 저장 경로
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "data" / "results"


@dataclass
class CommunityResult:
    """커뮤니티 탐지 결과 데이터 클래스.
    
    Attributes:
        node_community_map: {노드: 커뮤니티 ID} 딕셔너리
        community_nodes_list: {커뮤니티 ID: [노드 리스트]} 딕셔너리
        modularity: 모듈성 값 (0~1 범위, 높을수록 좋은 커뮤니티 구조)
        num_communities: 탐지된 커뮤니티 수
        
    Example:
        >>> result = CommunityResult(
        ...     node_community_map={"A": 0, "B": 0, "C": 1, "D": 1},
        ...     community_nodes_list={0: ["A", "B"], 1: ["C", "D"]},
        ...     modularity=0.65,
        ...     num_communities=2,
        ... )
    """
    node_community_map: Dict[str, int]
    community_nodes_list: Dict[int, List[str]]
    modularity: float
    num_communities: int
    
    def to_dict(self) -> Dict[str, Any]:
        """요약 정보를 딕셔너리로 변환.
        
        Returns:
            요약 통계 딕셔너리 (노드별 매핑은 제외)
        """
        return {
            "modularity": self.modularity,
            "num_communities": self.num_communities,
            "community_sizes": {
                cid: len(nodes) 
                for cid, nodes in self.community_nodes_list.items()
            },
        }
    
    def get_community_sizes(self) -> Dict[int, int]:
        """커뮤니티별 크기 반환.
        
        Returns:
            {커뮤니티 ID: 노드 수} 딕셔너리
        """
        return {
            cid: len(nodes) 
            for cid, nodes in self.community_nodes_list.items()
        }
    
    def get_largest_communities(self, top_n: int = 5) -> List[Tuple[int, int]]:
        """크기순 상위 N개 커뮤니티 반환.
        
        Args:
            top_n: 반환할 커뮤니티 수 (기본: 5)
            
        Returns:
            [(커뮤니티 ID, 노드 수), ...] 리스트 (크기 내림차순)
        """
        sizes = self.get_community_sizes()
        sorted_communities = sorted(
            sizes.items(), 
            key=lambda x: x[1], 
            reverse=True
        )
        return sorted_communities[:top_n]
    
    def to_node_dataframe(self) -> pd.DataFrame:
        """노드별 커뮤니티 매핑을 DataFrame으로 변환.
        
        Returns:
            DataFrame (node, community_id)
        """
        return pd.DataFrame([
            {"node": node, "community_id": cid}
            for node, cid in self.node_community_map.items()
        ])
    
    def to_community_dataframe(self) -> pd.DataFrame:
        """커뮤니티별 정보를 DataFrame으로 변환.
        
        Returns:
            DataFrame (community_id, size, nodes)
        """
        return pd.DataFrame([
            {
                "community_id": cid,
                "size": len(nodes),
                "nodes": ",".join(sorted(nodes)),
            }
            for cid, nodes in sorted(self.community_nodes_list.items())
        ])


class CommunityDetector:
    """커뮤니티 탐지 클래스.
    
    Louvain 알고리즘을 사용하여 네트워크 커뮤니티를 탐지한다.
    python-louvain 라이브러리(community_louvain.best_partition)를 사용하며,
    random_state를 고정하여 재현성을 보장한다 (요구사항 16.2).
    
    Note:
        - 원본 노트북은 randomize=True로 비결정적 실행을 했음
        - 본 시스템은 seed 고정으로 동일 입력에 동일 결과 보장
        - modularity는 networkx.algorithms.community.modularity()로 별도 계산
        - NetworkStatistics가 modularity를 재사용할 수 있도록 반환값에 포함
    
    Attributes:
        random_seed: Louvain 알고리즘 랜덤 시드 (기본: 42)
        config: AnalysisConfig 설정 객체
        output_dir: 결과 저장 디렉토리
    
    Example:
        >>> detector = CommunityDetector(random_seed=42)
        >>> G = nx.karate_club_graph()
        >>> result = detector.detect(G)
        >>> print(f"커뮤니티 수: {result.num_communities}, 모듈성: {result.modularity:.4f}")
    """
    
    def __init__(
        self,
        random_seed: int = 42,
        config: Optional[AnalysisConfig] = None,
        output_dir: Optional[Path] = None,
    ) -> None:
        """CommunityDetector 초기화.
        
        Args:
            random_seed: Louvain 알고리즘 랜덤 시드 (기본: 42).
                config/analysis.yaml의 louvain_seed 참조.
                요구사항 16.2(재현성)를 위한 신규 설계 결정.
            config: AnalysisConfig 설정 객체. None이면 기본 설정 로드.
            output_dir: 결과 저장 디렉토리. None이면 data/results/ 사용.
        """
        if config is not None:
            self.config = config
            # config에 louvain_seed가 있으면 사용
            if hasattr(config, 'louvain_seed') and config.louvain_seed is not None:
                self.random_seed = config.louvain_seed
            else:
                self.random_seed = random_seed
        else:
            self.config = load_config("analysis")
            # config에서 louvain_seed 로드 시도
            if hasattr(self.config, 'louvain_seed') and self.config.louvain_seed is not None:
                self.random_seed = self.config.louvain_seed
            else:
                self.random_seed = random_seed
        
        self.output_dir = Path(output_dir) if output_dir else DEFAULT_RESULTS_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info_with_details(
            "CommunityDetector 초기화 완료",
            stage="community",
            details={
                "random_seed": self.random_seed,
                "output_dir": str(self.output_dir),
            },
        )
    
    def detect(
        self,
        G: nx.Graph,
        weight: Optional[str] = None,
        resolution: float = 1.0,
    ) -> CommunityResult:
        """Louvain 알고리즘으로 커뮤니티 탐지.
        
        python-louvain 라이브러리의 best_partition()을 사용하여
        커뮤니티를 탐지한다. random_state를 고정하여 재현성을 보장한다.
        
        Args:
            G: NetworkX 무방향 그래프
            weight: Edge 가중치 컬럼명 (None이면 비가중)
            resolution: Louvain resolution 파라미터 (기본: 1.0).
                       값이 클수록 더 많은 커뮤니티 생성.
                       
        Returns:
            CommunityResult 데이터 클래스
            
        Example:
            >>> detector = CommunityDetector()
            >>> G = nx.karate_club_graph()
            >>> result = detector.detect(G)
            >>> print(f"커뮤니티 수: {result.num_communities}")
            >>> print(f"모듈성: {result.modularity:.4f}")
        """
        logger.info_with_details(
            f"커뮤니티 탐지 시작: 노드 {G.number_of_nodes()}, Edge {G.number_of_edges()}",
            stage="community",
            details={
                "random_seed": self.random_seed,
                "resolution": resolution,
                "weight": weight,
            },
        )
        
        # 빈 그래프 또는 노드가 없는 경우 처리
        if len(G) == 0:
            logger.warning_with_details(
                "빈 그래프: 커뮤니티를 탐지할 수 없습니다.",
                stage="community",
            )
            return CommunityResult(
                node_community_map={},
                community_nodes_list={},
                modularity=0.0,
                num_communities=0,
            )
        
        # 노드가 1개인 경우
        if len(G) == 1:
            node = list(G.nodes())[0]
            return CommunityResult(
                node_community_map={node: 0},
                community_nodes_list={0: [node]},
                modularity=0.0,
                num_communities=1,
            )
        
        # Edge가 없는 경우: 각 노드가 별도 커뮤니티
        if G.number_of_edges() == 0:
            nodes = list(G.nodes())
            node_community_map = {node: i for i, node in enumerate(nodes)}
            community_nodes_list = {i: [node] for i, node in enumerate(nodes)}
            return CommunityResult(
                node_community_map=node_community_map,
                community_nodes_list=community_nodes_list,
                modularity=0.0,
                num_communities=len(nodes),
            )
        
        # Louvain 커뮤니티 탐지 (python-louvain)
        # random_state로 재현성 보장 (요구사항 16.2)
        # Note: weight=None을 명시적으로 전달하면 python-louvain에서 오류 발생하므로
        #       weight가 None인 경우 인자를 제외하고 호출
        if weight is not None:
            partition = community_louvain.best_partition(
                G,
                weight=weight,
                resolution=resolution,
                random_state=self.random_seed,
            )
        else:
            partition = community_louvain.best_partition(
                G,
                resolution=resolution,
                random_state=self.random_seed,
            )
        
        # 노드별 커뮤니티 ID 매핑
        node_community_map: Dict[str, int] = partition
        
        # 커뮤니티별 노드 목록 생성
        community_nodes_list: Dict[int, List[str]] = defaultdict(list)
        for node, community_id in partition.items():
            community_nodes_list[community_id].append(node)
        
        # defaultdict를 일반 dict로 변환 및 노드 정렬
        community_nodes_list = {
            cid: sorted(nodes) 
            for cid, nodes in community_nodes_list.items()
        }
        
        # 커뮤니티 수
        num_communities = len(community_nodes_list)
        
        # Modularity 계산 (networkx.algorithms.community.modularity 사용)
        # partition을 set of sets 형태로 변환
        communities = [
            set(nodes) for nodes in community_nodes_list.values()
        ]
        # Note: weight=None을 명시적으로 전달하면 오류 발생 가능하므로
        #       weight가 None인 경우 인자를 제외하고 호출
        if weight is not None:
            modularity = nx.community.modularity(G, communities, weight=weight)
        else:
            modularity = nx.community.modularity(G, communities)
        
        result = CommunityResult(
            node_community_map=node_community_map,
            community_nodes_list=community_nodes_list,
            modularity=round(modularity, 6),
            num_communities=num_communities,
        )
        
        logger.info_with_details(
            f"커뮤니티 탐지 완료",
            stage="community",
            details={
                "num_communities": num_communities,
                "modularity": round(modularity, 4),
                "largest_community_size": max(len(n) for n in community_nodes_list.values()),
                "smallest_community_size": min(len(n) for n in community_nodes_list.values()),
            },
        )
        
        return result
    
    def build_graph(
        self,
        edge_df: pd.DataFrame,
        weight_column: str = "Weight",
    ) -> nx.Graph:
        """Edge DataFrame으로부터 NetworkX 그래프 생성.
        
        Args:
            edge_df: Edge list DataFrame (Source, Target 컬럼 필수)
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
    
    def detect_from_edge_list(
        self,
        edge_df: pd.DataFrame,
        weight_column: Optional[str] = None,
        resolution: float = 1.0,
    ) -> CommunityResult:
        """Edge DataFrame에서 직접 커뮤니티 탐지.
        
        편의 메서드로, 내부적으로 그래프를 생성한 후 커뮤니티를 탐지한다.
        
        Args:
            edge_df: Edge list DataFrame
            weight_column: Edge 가중치 컬럼명 (None이면 비가중)
            resolution: Louvain resolution 파라미터
            
        Returns:
            CommunityResult 데이터 클래스
        """
        G = self.build_graph(edge_df, weight_column or "Weight")
        return self.detect(G, weight=weight_column, resolution=resolution)
    
    def save_community_result(
        self,
        result: CommunityResult,
        filename_prefix: str,
        include_csv: bool = False,
        include_parquet: bool = True,
    ) -> Dict[str, Path]:
        """커뮤니티 탐지 결과 저장.
        
        노드별 커뮤니티 매핑과 커뮤니티별 정보를 각각 저장한다.
        
        Args:
            result: CommunityResult 객체
            filename_prefix: 파일명 prefix (예: "community_ALL_year_2023")
            include_csv: CSV 형식 저장 여부 (기본: False)
            include_parquet: Parquet 형식 저장 여부 (기본: True)
            
        Returns:
            저장된 파일 경로 딕셔너리
        """
        saved_files: Dict[str, Path] = {}
        
        # 노드별 커뮤니티 매핑 저장
        node_df = result.to_node_dataframe()
        
        if include_parquet:
            node_parquet_path = self.output_dir / f"{filename_prefix}_nodes.parquet"
            node_df.to_parquet(node_parquet_path, index=False)
            saved_files["node_parquet"] = node_parquet_path
            logger.debug_with_details(
                f"노드 커뮤니티 매핑 Parquet 저장 완료: {node_parquet_path}",
                stage="community",
            )
        
        if include_csv:
            node_csv_path = self.output_dir / f"{filename_prefix}_nodes.csv"
            node_df.to_csv(node_csv_path, index=False)
            saved_files["node_csv"] = node_csv_path
            logger.debug_with_details(
                f"노드 커뮤니티 매핑 CSV 저장 완료: {node_csv_path}",
                stage="community",
            )
        
        # 커뮤니티별 정보 저장
        community_df = result.to_community_dataframe()
        
        if include_parquet:
            comm_parquet_path = self.output_dir / f"{filename_prefix}_summary.parquet"
            community_df.to_parquet(comm_parquet_path, index=False)
            saved_files["community_parquet"] = comm_parquet_path
            logger.debug_with_details(
                f"커뮤니티 요약 Parquet 저장 완료: {comm_parquet_path}",
                stage="community",
            )
        
        if include_csv:
            comm_csv_path = self.output_dir / f"{filename_prefix}_summary.csv"
            community_df.to_csv(comm_csv_path, index=False)
            saved_files["community_csv"] = comm_csv_path
            logger.debug_with_details(
                f"커뮤니티 요약 CSV 저장 완료: {comm_csv_path}",
                stage="community",
            )
        
        return saved_files
    
    def compute_batch(
        self,
        edge_dfs: Dict[str, pd.DataFrame],
        weight_column: Optional[str] = None,
        resolution: float = 1.0,
    ) -> Dict[str, CommunityResult]:
        """여러 네트워크에 대해 일괄 커뮤니티 탐지.
        
        Args:
            edge_dfs: {식별자: Edge DataFrame} 딕셔너리
            weight_column: Edge 가중치 컬럼명 (None이면 비가중)
            resolution: Louvain resolution 파라미터
            
        Returns:
            {식별자: CommunityResult} 딕셔너리
        """
        results: Dict[str, CommunityResult] = {}
        
        for key, edge_df in edge_dfs.items():
            try:
                result = self.detect_from_edge_list(
                    edge_df, 
                    weight_column=weight_column,
                    resolution=resolution,
                )
                results[key] = result
            except Exception as e:
                logger.error_with_details(
                    f"커뮤니티 탐지 실패: {key}",
                    stage="community",
                    details={"error": str(e)},
                )
        
        return results
    
    def extract_modularity_values(
        self,
        results: Dict[str, CommunityResult],
    ) -> Dict[str, float]:
        """일괄 탐지 결과에서 modularity 값만 추출.
        
        NetworkStatistics가 modularity를 재사용할 수 있도록 추출.
        Louvain 중복 실행 방지를 위한 메서드.
        
        Args:
            results: {식별자: CommunityResult} 딕셔너리
            
        Returns:
            {식별자: modularity} 딕셔너리
        """
        return {key: result.modularity for key, result in results.items()}
    
    def to_summary_dataframe(
        self,
        results: Dict[str, CommunityResult],
    ) -> pd.DataFrame:
        """여러 CommunityResult를 요약 DataFrame으로 변환.
        
        Args:
            results: {식별자: CommunityResult} 딕셔너리
            
        Returns:
            요약 DataFrame (network_id, num_communities, modularity, largest_size, etc.)
        """
        rows = []
        for key, result in results.items():
            sizes = result.get_community_sizes()
            row = {
                "network_id": key,
                "num_communities": result.num_communities,
                "modularity": result.modularity,
                "largest_community_size": max(sizes.values()) if sizes else 0,
                "smallest_community_size": min(sizes.values()) if sizes else 0,
                "avg_community_size": (
                    sum(sizes.values()) / len(sizes) if sizes else 0.0
                ),
            }
            rows.append(row)
        
        return pd.DataFrame(rows)
