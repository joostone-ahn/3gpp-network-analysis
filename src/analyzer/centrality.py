"""
Centrality Analyzer Module (Stage 7)

네트워크 중심성 분석을 수행하는 모듈.

요구사항:
- 11.1: 비가중(unweighted) 중심성 계산 (Degree, Betweenness, Closeness, Eigenvector)
- 11.2: 모든 Centrality 값을 0~1 사이로 정규화
- 11.3: Eigenvector Centrality 미수렴 시 null 처리 및 경고 로그

Note:
    - Edge Weight는 네트워크 구성 단계의 threshold 필터링에만 사용
    - 중심성 계산 자체에는 weight를 반영하지 않음 (원본 노트북과 동일 방식)
    - Eigenvector max_iter=1000 설정, PowerIterationFailedConvergence 예외 처리
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import networkx as nx
import pandas as pd

from src.utils.config_loader import PROJECT_ROOT, AnalysisConfig, load_config
from src.utils.logger import get_logger

# 모듈 로거
logger = get_logger("analyzer", default_stage="centrality")

# 기본 저장 경로
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "data" / "results"


@dataclass
class CentralityResult:
    """중심성 계산 결과 데이터 클래스.
    
    Attributes:
        node: 노드 ID
        degree_centrality: Degree 중심성 (0~1 정규화됨)
        betweenness_centrality: Betweenness 중심성 (0~1 정규화됨)
        closeness_centrality: Closeness 중심성 (0~1 정규화됨)
        eigenvector_centrality: Eigenvector 중심성 (0~1 정규화됨, 미수렴 시 None)
    """
    node: str
    degree_centrality: float
    betweenness_centrality: float
    closeness_centrality: float
    eigenvector_centrality: Optional[float]
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환.
        
        Returns:
            모든 중심성 지표를 포함하는 딕셔너리
        """
        return {
            "node": self.node,
            "degree_centrality": self.degree_centrality,
            "betweenness_centrality": self.betweenness_centrality,
            "closeness_centrality": self.closeness_centrality,
            "eigenvector_centrality": self.eigenvector_centrality,
        }


class CentralityAnalyzer:
    """중심성 분석 클래스.
    
    NetworkX 그래프에 대해 다양한 중심성 지표를 계산한다.
    모든 중심성은 비가중(unweighted)으로 계산한다.
    
    계산 지표:
        - Degree Centrality: 노드의 연결 수 기반 중심성
        - Betweenness Centrality: 최단 경로에 포함되는 빈도 기반 중심성
        - Closeness Centrality: 다른 노드까지의 평균 거리 기반 중심성
        - Eigenvector Centrality: 중요한 노드와의 연결 기반 중심성
    
    Note:
        - 모든 중심성은 0~1 사이로 정규화됨
        - Eigenvector Centrality 미수렴 시 None 반환
        - weight 인자를 전달하지 않아 비가중 계산 (요구사항 11.1)
    
    Attributes:
        config: AnalysisConfig 설정 객체
        eigenvector_max_iter: Eigenvector Centrality 최대 반복 횟수
        output_dir: 결과 저장 디렉토리
    
    Example:
        >>> analyzer = CentralityAnalyzer()
        >>> G = nx.karate_club_graph()
        >>> df = analyzer.compute_all(G)
        >>> print(df.head())
    """
    
    def __init__(
        self,
        config: Optional[AnalysisConfig] = None,
        eigenvector_max_iter: int = 1000,
        output_dir: Optional[Path] = None,
    ) -> None:
        """CentralityAnalyzer 초기화.
        
        Args:
            config: AnalysisConfig 설정 객체. None이면 기본 설정 로드.
            eigenvector_max_iter: Eigenvector Centrality 최대 반복 횟수.
                config/analysis.yaml의 eigenvector_max_iter.
                원본 노트북은 NetworkX 기본값(100)을 사용했으나, 
                본 구현은 1000으로 완화 (요구사항 11.3).
            output_dir: 결과 저장 디렉토리. None이면 data/results/ 사용.
        """
        if config is not None:
            self.config = config
            # config에 eigenvector_max_iter가 있으면 사용
            if hasattr(config, 'eigenvector_max_iter') and config.eigenvector_max_iter:
                self.eigenvector_max_iter = config.eigenvector_max_iter
            else:
                self.eigenvector_max_iter = eigenvector_max_iter
        else:
            self.config = load_config("analysis")
            # config에서 eigenvector_max_iter 로드 시도
            if hasattr(self.config, 'eigenvector_max_iter') and self.config.eigenvector_max_iter:
                self.eigenvector_max_iter = self.config.eigenvector_max_iter
            else:
                self.eigenvector_max_iter = eigenvector_max_iter
        
        self.output_dir = Path(output_dir) if output_dir else DEFAULT_RESULTS_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info_with_details(
            "CentralityAnalyzer 초기화 완료",
            stage="centrality",
            details={
                "eigenvector_max_iter": self.eigenvector_max_iter,
                "output_dir": str(self.output_dir),
            },
        )
    
    def _normalize_centrality(
        self,
        centrality_dict: Dict[str, float],
    ) -> Dict[str, float]:
        """중심성 값을 0~1 범위로 정규화.
        
        Min-Max 정규화 적용: (value - min) / (max - min)
        모든 값이 동일한 경우 0.0 반환 (또는 단일 노드면 1.0)
        
        Args:
            centrality_dict: {노드: 중심성값} 딕셔너리
            
        Returns:
            정규화된 {노드: 중심성값} 딕셔너리
        """
        if not centrality_dict:
            return {}
        
        values = list(centrality_dict.values())
        min_val = min(values)
        max_val = max(values)
        
        # 모든 값이 동일한 경우
        if max_val == min_val:
            # 단일 노드인 경우 1.0, 아니면 모두 동일하므로 0.0
            if len(centrality_dict) == 1:
                return {node: 1.0 for node in centrality_dict}
            return {node: 0.0 for node in centrality_dict}
        
        # Min-Max 정규화
        return {
            node: (value - min_val) / (max_val - min_val)
            for node, value in centrality_dict.items()
        }
    
    def compute_degree_centrality(
        self,
        G: nx.Graph,
        normalize: bool = True,
    ) -> Dict[str, float]:
        """Degree Centrality 계산 (비가중).
        
        노드의 연결 수를 기반으로 중심성을 계산한다.
        NetworkX의 degree_centrality는 기본적으로 (n-1)로 정규화됨.
        
        Args:
            G: NetworkX 그래프
            normalize: 0~1 정규화 적용 여부 (기본: True)
            
        Returns:
            {노드: 중심성값} 딕셔너리
        """
        if len(G) == 0:
            return {}
        
        # 비가중 Degree Centrality (weight 인자 없음)
        centrality = nx.degree_centrality(G)
        
        if normalize:
            centrality = self._normalize_centrality(centrality)
        
        return centrality
    
    def compute_betweenness_centrality(
        self,
        G: nx.Graph,
        normalize: bool = True,
    ) -> Dict[str, float]:
        """Betweenness Centrality 계산 (비가중).
        
        노드가 다른 노드 쌍 사이의 최단 경로에 포함되는 빈도를 기반으로 
        중심성을 계산한다.
        
        Args:
            G: NetworkX 그래프
            normalize: 0~1 정규화 적용 여부 (기본: True)
            
        Returns:
            {노드: 중심성값} 딕셔너리
        """
        if len(G) == 0:
            return {}
        
        # 비가중 Betweenness Centrality (weight 인자 없음)
        # normalized=True는 NetworkX 내부 정규화 ((n-1)(n-2)/2로 나눔)
        centrality = nx.betweenness_centrality(G, normalized=True)
        
        if normalize:
            centrality = self._normalize_centrality(centrality)
        
        return centrality
    
    def compute_closeness_centrality(
        self,
        G: nx.Graph,
        normalize: bool = True,
    ) -> Dict[str, float]:
        """Closeness Centrality 계산 (비가중).
        
        노드에서 다른 모든 노드까지의 평균 최단 경로 길이의 역수를 기반으로
        중심성을 계산한다.
        
        Args:
            G: NetworkX 그래프
            normalize: 0~1 정규화 적용 여부 (기본: True)
            
        Returns:
            {노드: 중심성값} 딕셔너리
        """
        if len(G) == 0:
            return {}
        
        # 비가중 Closeness Centrality (distance 인자 없음)
        centrality = nx.closeness_centrality(G)
        
        if normalize:
            centrality = self._normalize_centrality(centrality)
        
        return centrality
    
    def compute_eigenvector_centrality(
        self,
        G: nx.Graph,
        normalize: bool = True,
    ) -> Optional[Dict[str, float]]:
        """Eigenvector Centrality 계산 (비가중).
        
        중요한 노드와 연결된 노드가 높은 중심성을 갖는 방식으로 계산한다.
        Power iteration 방법을 사용하며, max_iter 내에 수렴하지 않으면
        None을 반환하고 경고 로그를 남긴다 (요구사항 11.3).
        
        Args:
            G: NetworkX 그래프
            normalize: 0~1 정규화 적용 여부 (기본: True)
            
        Returns:
            {노드: 중심성값} 딕셔너리, 미수렴 시 None
        """
        if len(G) == 0:
            return {}
        
        # 노드가 1개인 경우 eigenvector centrality는 의미 없음
        if len(G) == 1:
            node = list(G.nodes())[0]
            return {node: 1.0}
        
        try:
            # 비가중 Eigenvector Centrality (weight 인자 없음)
            centrality = nx.eigenvector_centrality(
                G,
                max_iter=self.eigenvector_max_iter,
            )
            
            if normalize:
                centrality = self._normalize_centrality(centrality)
            
            return centrality
            
        except nx.PowerIterationFailedConvergence as e:
            # 미수렴 시 null 처리 및 경고 로그 (요구사항 11.3)
            logger.warning_with_details(
                f"Eigenvector Centrality 미수렴: {self.eigenvector_max_iter}회 반복 내 수렴하지 않음",
                stage="centrality",
                details={
                    "max_iter": self.eigenvector_max_iter,
                    "nodes": G.number_of_nodes(),
                    "edges": G.number_of_edges(),
                    "error": str(e),
                },
            )
            return None
        except Exception as e:
            logger.error_with_details(
                f"Eigenvector Centrality 계산 중 오류 발생: {e}",
                stage="centrality",
                details={"error": str(e)},
            )
            return None
    
    def compute_all(
        self,
        G: nx.Graph,
        normalize: bool = True,
    ) -> pd.DataFrame:
        """모든 중심성 지표 계산.
        
        Degree, Betweenness, Closeness, Eigenvector Centrality를 
        모두 계산하여 DataFrame으로 반환한다.
        모든 중심성은 비가중(unweighted)으로 계산한다 (요구사항 11.1).
        
        Args:
            G: NetworkX 그래프
            normalize: 0~1 정규화 적용 여부 (기본: True)
            
        Returns:
            중심성 DataFrame (node, degree_centrality, betweenness_centrality,
                            closeness_centrality, eigenvector_centrality)
                            
        Example:
            >>> analyzer = CentralityAnalyzer()
            >>> G = nx.karate_club_graph()
            >>> df = analyzer.compute_all(G)
            >>> print(df.columns.tolist())
            ['node', 'degree_centrality', 'betweenness_centrality', 
             'closeness_centrality', 'eigenvector_centrality']
        """
        logger.info_with_details(
            f"중심성 분석 시작: 노드 {G.number_of_nodes()}, Edge {G.number_of_edges()}",
            stage="centrality",
        )
        
        # 빈 그래프 처리
        if len(G) == 0:
            logger.warning_with_details(
                "빈 그래프: 중심성을 계산할 수 없습니다.",
                stage="centrality",
            )
            return pd.DataFrame(columns=[
                "node", "degree_centrality", "betweenness_centrality",
                "closeness_centrality", "eigenvector_centrality"
            ])
        
        # 각 중심성 계산
        degree = self.compute_degree_centrality(G, normalize)
        betweenness = self.compute_betweenness_centrality(G, normalize)
        closeness = self.compute_closeness_centrality(G, normalize)
        eigenvector = self.compute_eigenvector_centrality(G, normalize)
        
        # 결과 DataFrame 생성
        nodes = list(G.nodes())
        results = []
        
        for node in nodes:
            result = CentralityResult(
                node=node,
                degree_centrality=round(degree.get(node, 0.0), 6),
                betweenness_centrality=round(betweenness.get(node, 0.0), 6),
                closeness_centrality=round(closeness.get(node, 0.0), 6),
                eigenvector_centrality=(
                    round(eigenvector.get(node, 0.0), 6) 
                    if eigenvector is not None 
                    else None
                ),
            )
            results.append(result.to_dict())
        
        df = pd.DataFrame(results)
        
        # 로깅
        eigenvector_status = "계산 완료" if eigenvector is not None else "미수렴 (null)"
        logger.info_with_details(
            f"중심성 분석 완료: {len(nodes)}개 노드",
            stage="centrality",
            details={
                "nodes": len(nodes),
                "degree_centrality": "계산 완료",
                "betweenness_centrality": "계산 완료",
                "closeness_centrality": "계산 완료",
                "eigenvector_centrality": eigenvector_status,
            },
        )
        
        return df
    
    def build_graph(
        self,
        edge_df: pd.DataFrame,
        weight_column: str = "Weight",
    ) -> nx.Graph:
        """Edge DataFrame으로부터 NetworkX 그래프 생성.
        
        Note: 중심성 계산은 비가중으로 수행하지만, 그래프 생성 시에는
        weight 정보를 보존한다 (다른 분석에서 필요할 수 있음).
        
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
    
    def compute_from_edge_list(
        self,
        edge_df: pd.DataFrame,
        normalize: bool = True,
    ) -> pd.DataFrame:
        """Edge DataFrame에서 직접 중심성 계산.
        
        편의 메서드로, 내부적으로 그래프를 생성한 후 중심성을 계산한다.
        
        Args:
            edge_df: Edge list DataFrame
            normalize: 0~1 정규화 적용 여부
            
        Returns:
            중심성 DataFrame
        """
        G = self.build_graph(edge_df)
        return self.compute_all(G, normalize)
    
    def save_centrality(
        self,
        centrality_df: pd.DataFrame,
        filename_prefix: str,
        include_csv: bool = True,
        include_parquet: bool = True,
    ) -> Dict[str, Path]:
        """중심성 결과 저장.
        
        Args:
            centrality_df: 중심성 DataFrame
            filename_prefix: 파일명 prefix (예: "centrality_ALL_year_2023")
            include_csv: CSV 형식 저장 여부
            include_parquet: Parquet 형식 저장 여부
            
        Returns:
            저장된 파일 경로 딕셔너리
        """
        saved_files: Dict[str, Path] = {}
        
        if include_csv:
            csv_path = self.output_dir / f"{filename_prefix}.csv"
            centrality_df.to_csv(csv_path, index=False)
            saved_files["csv"] = csv_path
            logger.debug_with_details(
                f"CSV 저장 완료: {csv_path}",
                stage="centrality",
            )
        
        if include_parquet:
            parquet_path = self.output_dir / f"{filename_prefix}.parquet"
            centrality_df.to_parquet(parquet_path, index=False)
            saved_files["parquet"] = parquet_path
            logger.debug_with_details(
                f"Parquet 저장 완료: {parquet_path}",
                stage="centrality",
            )
        
        return saved_files
    
    def compute_batch(
        self,
        edge_dfs: Dict[str, pd.DataFrame],
        normalize: bool = True,
    ) -> Dict[str, pd.DataFrame]:
        """여러 네트워크에 대해 일괄 중심성 계산.
        
        Args:
            edge_dfs: {식별자: Edge DataFrame} 딕셔너리
            normalize: 0~1 정규화 적용 여부
            
        Returns:
            {식별자: 중심성 DataFrame} 딕셔너리
        """
        results: Dict[str, pd.DataFrame] = {}
        
        for key, edge_df in edge_dfs.items():
            try:
                centrality_df = self.compute_from_edge_list(edge_df, normalize)
                results[key] = centrality_df
            except Exception as e:
                logger.error_with_details(
                    f"중심성 계산 실패: {key}",
                    stage="centrality",
                    details={"error": str(e)},
                )
        
        return results
    
    def get_top_central_nodes(
        self,
        centrality_df: pd.DataFrame,
        centrality_type: str,
        top_n: int = 10,
    ) -> pd.DataFrame:
        """특정 중심성 기준 상위 N개 노드 반환.
        
        Args:
            centrality_df: 중심성 DataFrame
            centrality_type: 중심성 유형 ('degree', 'betweenness', 
                           'closeness', 'eigenvector')
            top_n: 상위 N개 (기본: 10)
            
        Returns:
            상위 N개 노드 DataFrame
            
        Raises:
            ValueError: 잘못된 중심성 유형인 경우
        """
        column_mapping = {
            "degree": "degree_centrality",
            "betweenness": "betweenness_centrality",
            "closeness": "closeness_centrality",
            "eigenvector": "eigenvector_centrality",
        }
        
        if centrality_type not in column_mapping:
            raise ValueError(
                f"잘못된 중심성 유형: {centrality_type}. "
                f"가능한 값: {list(column_mapping.keys())}"
            )
        
        column = column_mapping[centrality_type]
        
        if column not in centrality_df.columns:
            raise ValueError(f"컬럼이 존재하지 않습니다: {column}")
        
        # Eigenvector가 None인 경우 처리
        df = centrality_df.dropna(subset=[column])
        
        return df.nlargest(top_n, column)[["node", column]]
