"""
Advanced Network Analyzer Module (Stage 7)

고급 네트워크 분석을 수행하는 모듈.

요구사항:
- 12.1: Power-law 적합성 검증 (exponent + p-value)
- 12.2: Small-world 지수 σ 계산 (직접 구현, nx.sigma() 사용 금지)
- 12.3: Maximum Spanning Tree 추출
- 12.4: TSG별 Degree Centrality 순위 간 Spearman 상관계수
- 12.5: Threshold 민감도 분석

적용 범위 (요구사항 12 참고):
- analyze_power_law/compute_small_world/extract_mst/analyze_centrality_correlation:
  TSG × 연도(time_unit=year) × threshold=0 조합에만 실행
- sensitivity_analysis: 대표 시간 값에서 threshold 0~9 스윕

Note:
    - nx.sigma()는 대규모 그래프에서 성능 이슈로 직접 사용 금지
    - 원본 노트북은 exponent만 계산, p-value는 신규 구현
    - 원본 노트북은 원본 값에 Pearson 적용 오류, 순위 기반 Spearman으로 정정
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import networkx as nx
import numpy as np
import pandas as pd
from scipy import stats

from src.utils.config_loader import PROJECT_ROOT, AnalysisConfig, load_config
from src.utils.logger import get_logger

# 모듈 로거
logger = get_logger("analyzer", default_stage="advanced")

# 기본 저장 경로
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "data" / "results"


@dataclass
class PowerLawResult:
    """Power-law 분석 결과 데이터 클래스.
    
    Attributes:
        alpha: Power-law 지수 (exponent)
        xmin: Power-law 적용 최소값
        p_value: 분포 비교 p-value (power_law vs lognormal)
        comparison_distribution: 비교 분포 이름
        loglikelihood_ratio: 로그 우도비 (R)
        is_power_law: Power-law 적합 여부 (R > 0 and p < 0.1)
    """
    alpha: float
    xmin: float
    p_value: float
    comparison_distribution: str
    loglikelihood_ratio: float
    is_power_law: bool
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환."""
        return {
            "alpha": self.alpha,
            "xmin": self.xmin,
            "p_value": self.p_value,
            "comparison_distribution": self.comparison_distribution,
            "loglikelihood_ratio": self.loglikelihood_ratio,
            "is_power_law": self.is_power_law,
        }


@dataclass
class SmallWorldResult:
    """Small-world 분석 결과 데이터 클래스.
    
    Attributes:
        clustering_coefficient: 실제 네트워크 군집 계수 (C)
        avg_path_length: 실제 네트워크 평균 경로 길이 (L)
        clustering_random: 무작위 네트워크 평균 군집 계수 (C_rand)
        avg_path_length_random: 무작위 네트워크 평균 경로 길이 (L_rand)
        sigma: Small-world 지수 σ = (C/C_rand)/(L/L_rand)
        num_samples: 무작위 네트워크 생성 횟수
        is_small_world: Small-world 특성 여부 (σ > 1)
    """
    clustering_coefficient: float
    avg_path_length: float
    clustering_random: float
    avg_path_length_random: float
    sigma: float
    num_samples: int
    is_small_world: bool
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환."""
        return {
            "clustering_coefficient": self.clustering_coefficient,
            "avg_path_length": self.avg_path_length,
            "clustering_random": self.clustering_random,
            "avg_path_length_random": self.avg_path_length_random,
            "sigma": self.sigma,
            "num_samples": self.num_samples,
            "is_small_world": self.is_small_world,
        }


@dataclass
class SensitivityResult:
    """민감도 분석 결과 데이터 클래스.
    
    Attributes:
        threshold: 적용된 threshold 값
        nodes: 노드 수
        edges: Edge 수
        density: 밀도
        avg_degree: 평균 degree
        avg_clustering: 평균 군집 계수
        connected_components: 연결 컴포넌트 수
        lcc_ratio: LCC 비율 (LCC 노드 수 / 전체 노드 수)
    """
    threshold: int
    nodes: int
    edges: int
    density: float
    avg_degree: float
    avg_clustering: float
    connected_components: int
    lcc_ratio: float
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환."""
        return {
            "threshold": self.threshold,
            "nodes": self.nodes,
            "edges": self.edges,
            "density": self.density,
            "avg_degree": self.avg_degree,
            "avg_clustering": self.avg_clustering,
            "connected_components": self.connected_components,
            "lcc_ratio": self.lcc_ratio,
        }


class AdvancedAnalyzer:
    """고급 네트워크 분석 클래스.
    
    Power-law 분석, Small-world 지수 계산, MST 추출, 중심성 상관분석 등
    고급 네트워크 분석 기능을 제공한다.
    
    적용 범위 (요구사항 12 참고):
        - analyze_power_law/compute_small_world/extract_mst/analyze_centrality_correlation:
          TSG × 연도(time_unit=year) × threshold=0 조합에만 실행
        - sensitivity_analysis: 대표 시간 값에서 threshold 0~9 스윕
    
    Note:
        - nx.sigma()는 대규모 그래프에서 성능 이슈로 직접 사용 금지
        - powerlaw 패키지를 사용하여 Power-law 분석 수행
        - 중심성 상관분석은 순위 기반 Spearman 사용 (원본 노트북 오류 정정)
    
    Attributes:
        config: AnalysisConfig 설정 객체
        random_network_samples: 무작위 네트워크 생성 횟수
        output_dir: 결과 저장 디렉토리
    
    Example:
        >>> analyzer = AdvancedAnalyzer()
        >>> G = nx.karate_club_graph()
        >>> result = analyzer.analyze_power_law(G)
        >>> print(f"Alpha: {result.alpha}, p-value: {result.p_value}")
    """
    
    def __init__(
        self,
        config: Optional[AnalysisConfig] = None,
        random_network_samples: int = 100,
        output_dir: Optional[Path] = None,
    ) -> None:
        """AdvancedAnalyzer 초기화.
        
        Args:
            config: AnalysisConfig 설정 객체. None이면 기본 설정 로드.
            random_network_samples: Small-world 분석 시 무작위 네트워크 생성 횟수.
                config/analysis.yaml의 random_network_samples.
            output_dir: 결과 저장 디렉토리. None이면 data/results/ 사용.
        """
        if config is not None:
            self.config = config
            if hasattr(config, 'random_network_samples') and config.random_network_samples:
                self.random_network_samples = config.random_network_samples
            else:
                self.random_network_samples = random_network_samples
        else:
            self.config = load_config("analysis")
            if hasattr(self.config, 'random_network_samples') and self.config.random_network_samples:
                self.random_network_samples = self.config.random_network_samples
            else:
                self.random_network_samples = random_network_samples
        
        self.output_dir = Path(output_dir) if output_dir else DEFAULT_RESULTS_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info_with_details(
            "AdvancedAnalyzer 초기화 완료",
            stage="advanced",
            details={
                "random_network_samples": self.random_network_samples,
                "output_dir": str(self.output_dir),
            },
        )
    
    def analyze_power_law(
        self,
        G: nx.Graph,
        comparison_distribution: str = "lognormal",
    ) -> Optional[PowerLawResult]:
        """Degree 분포의 Power-law 적합성 검증.
        
        powerlaw 패키지를 사용하여 Power-law 지수(alpha)와 p-value를 계산한다.
        p-value는 fit.distribution_compare()로 Power-law와 다른 분포(기본: lognormal)를
        비교하여 계산한다.
        
        Args:
            G: NetworkX 그래프
            comparison_distribution: 비교할 분포 (기본: "lognormal")
                가능한 값: "lognormal", "exponential", "truncated_power_law"
            
        Returns:
            PowerLawResult 객체 또는 None (분석 실패 시)
            
        Note:
            - 원본 노트북은 exponent만 계산, p-value는 신규 구현
            - R > 0이면 power_law가 더 적합, R < 0이면 비교 분포가 더 적합
            - is_power_law = (R > 0) and (p < 0.1)로 판단
        """
        try:
            import powerlaw
        except ImportError:
            logger.error_with_details(
                "powerlaw 패키지가 설치되지 않았습니다. pip install powerlaw 실행 필요",
                stage="advanced",
            )
            return None
        
        if len(G) == 0:
            logger.warning_with_details(
                "빈 그래프: Power-law 분석을 수행할 수 없습니다.",
                stage="advanced",
            )
            return None
        
        # Degree 시퀀스 추출
        degrees = [d for _, d in G.degree()]
        
        # Degree가 0인 노드 제외 (powerlaw 패키지 요구사항)
        degrees = [d for d in degrees if d > 0]
        
        if len(degrees) < 2:
            logger.warning_with_details(
                "유효한 degree가 2개 미만: Power-law 분석을 수행할 수 없습니다.",
                stage="advanced",
            )
            return None
        
        try:
            # Power-law 피팅
            fit = powerlaw.Fit(degrees, discrete=True, verbose=False)
            
            # 지수 및 xmin
            alpha = fit.power_law.alpha
            xmin = fit.power_law.xmin
            
            # 분포 비교 (power_law vs comparison_distribution)
            # R > 0이면 power_law가 더 적합
            R, p_value = fit.distribution_compare('power_law', comparison_distribution)
            
            # Power-law 적합 판단: R > 0 (power_law 선호) and p < 0.1 (통계적 유의)
            is_power_law = (R > 0) and (p_value < 0.1)
            
            result = PowerLawResult(
                alpha=round(alpha, 4),
                xmin=round(xmin, 4) if xmin is not None else 0.0,
                p_value=round(p_value, 4),
                comparison_distribution=comparison_distribution,
                loglikelihood_ratio=round(R, 4),
                is_power_law=is_power_law,
            )
            
            logger.info_with_details(
                f"Power-law 분석 완료: α={result.alpha}, p={result.p_value}",
                stage="advanced",
                details=result.to_dict(),
            )
            
            return result
            
        except Exception as e:
            logger.error_with_details(
                f"Power-law 분석 중 오류 발생: {e}",
                stage="advanced",
                details={"error": str(e)},
            )
            return None
    
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
        
        largest_cc = max(nx.connected_components(G), key=len)
        return G.subgraph(largest_cc).copy()
    
    def compute_small_world(
        self,
        G: nx.Graph,
        num_samples: Optional[int] = None,
        seed: int = 42,
    ) -> Optional[SmallWorldResult]:
        """Small-world 지수 σ = (C/C_rand)/(L/L_rand) 계산.
        
        num_samples개의 Erdős–Rényi 무작위 네트워크를 생성하여 평균 C_rand, L_rand를
        구한 뒤 σ를 계산한다.
        
        σ > 1이면 Small-world 특성을 가진다고 판단.
        
        Args:
            G: NetworkX 그래프
            num_samples: 무작위 네트워크 생성 횟수 (기본: config 값)
            seed: 랜덤 시드 (재현성)
            
        Returns:
            SmallWorldResult 객체 또는 None (계산 불가 시)
            
        Note:
            - nx.sigma()는 대규모 그래프에서 성능 이슈로 직접 사용 금지
            - 원본 노트북은 C_rand/L_rand를 출력만 했고 σ는 계산한 적 없음 (신규 구현)
            - LCC 기준으로 계산 (비연결 그래프 처리)
        """
        if num_samples is None:
            num_samples = self.random_network_samples
        
        if len(G) == 0:
            logger.warning_with_details(
                "빈 그래프: Small-world 분석을 수행할 수 없습니다.",
                stage="advanced",
            )
            return None
        
        # LCC 추출 (비연결 그래프 대비)
        lcc = self._get_largest_connected_component(G)
        n_nodes = lcc.number_of_nodes()
        n_edges = lcc.number_of_edges()
        
        if n_nodes < 4:
            logger.warning_with_details(
                f"LCC 노드 수가 4개 미만({n_nodes}): Small-world 분석을 수행할 수 없습니다.",
                stage="advanced",
            )
            return None
        
        try:
            # 실제 네트워크 지표
            C = nx.average_clustering(lcc)
            L = nx.average_shortest_path_length(lcc)
            
            # 무작위 네트워크 생성 및 지표 계산
            np.random.seed(seed)
            C_rand_list = []
            L_rand_list = []
            
            for i in range(num_samples):
                # Erdős–Rényi 무작위 그래프 (동일 노드/엣지 수)
                G_rand = nx.gnm_random_graph(n_nodes, n_edges, seed=seed + i)
                
                # 연결된 경우에만 계산
                if nx.is_connected(G_rand) and G_rand.number_of_nodes() >= 2:
                    C_rand_list.append(nx.average_clustering(G_rand))
                    L_rand_list.append(nx.average_shortest_path_length(G_rand))
                else:
                    # 비연결 시 LCC 사용
                    if len(G_rand) > 0:
                        largest_cc = max(nx.connected_components(G_rand), key=len)
                        G_rand_lcc = G_rand.subgraph(largest_cc).copy()
                        if G_rand_lcc.number_of_nodes() >= 2:
                            C_rand_list.append(nx.average_clustering(G_rand_lcc))
                            L_rand_list.append(nx.average_shortest_path_length(G_rand_lcc))
            
            if len(C_rand_list) == 0 or len(L_rand_list) == 0:
                logger.warning_with_details(
                    "유효한 무작위 네트워크를 생성할 수 없습니다.",
                    stage="advanced",
                )
                return None
            
            # 평균 계산
            C_rand = np.mean(C_rand_list)
            L_rand = np.mean(L_rand_list)
            
            # σ 계산 (0 나눗셈 방지)
            if C_rand == 0 or L_rand == 0:
                logger.warning_with_details(
                    f"C_rand({C_rand}) 또는 L_rand({L_rand})가 0: σ 계산 불가",
                    stage="advanced",
                )
                return None
            
            sigma = (C / C_rand) / (L / L_rand)
            is_small_world = sigma > 1
            
            result = SmallWorldResult(
                clustering_coefficient=round(C, 6),
                avg_path_length=round(L, 6),
                clustering_random=round(C_rand, 6),
                avg_path_length_random=round(L_rand, 6),
                sigma=round(sigma, 6),
                num_samples=len(C_rand_list),
                is_small_world=is_small_world,
            )
            
            logger.info_with_details(
                f"Small-world 분석 완료: σ={result.sigma}, is_small_world={is_small_world}",
                stage="advanced",
                details=result.to_dict(),
            )
            
            return result
            
        except Exception as e:
            logger.error_with_details(
                f"Small-world 분석 중 오류 발생: {e}",
                stage="advanced",
                details={"error": str(e)},
            )
            return None
    
    def extract_mst(
        self,
        G: nx.Graph,
        weight_column: str = "Weight",
    ) -> nx.Graph:
        """Maximum Spanning Tree 추출.
        
        Edge의 weight 기준으로 Maximum Spanning Tree를 추출한다.
        MST는 모든 노드를 연결하면서 weight 합계를 최대화하는 트리 구조이다.
        
        Args:
            G: NetworkX 그래프
            weight_column: 가중치 컬럼명 (기본: "Weight")
            
        Returns:
            Maximum Spanning Tree NetworkX 그래프
            
        Note:
            - nx.maximum_spanning_tree(G, weight='Weight') 사용
            - 비연결 그래프의 경우 Maximum Spanning Forest 반환
        """
        if len(G) == 0:
            logger.warning_with_details(
                "빈 그래프: MST를 추출할 수 없습니다.",
                stage="advanced",
            )
            return nx.Graph()
        
        try:
            # Maximum Spanning Tree 추출
            # weight 속성이 없는 경우 기본값으로 처리
            mst = nx.maximum_spanning_tree(G, weight=weight_column)
            
            logger.info_with_details(
                f"MST 추출 완료: 노드 {mst.number_of_nodes()}, Edge {mst.number_of_edges()}",
                stage="advanced",
                details={
                    "original_nodes": G.number_of_nodes(),
                    "original_edges": G.number_of_edges(),
                    "mst_nodes": mst.number_of_nodes(),
                    "mst_edges": mst.number_of_edges(),
                },
            )
            
            return mst
            
        except Exception as e:
            logger.error_with_details(
                f"MST 추출 중 오류 발생: {e}",
                stage="advanced",
                details={"error": str(e)},
            )
            return nx.Graph()
    
    def analyze_centrality_correlation(
        self,
        networks: Dict[str, nx.Graph],
    ) -> pd.DataFrame:
        """TSG 그룹별 Degree Centrality 순위 간 Spearman 상관계수 계산.
        
        각 네트워크의 Degree Centrality를 순위(rank)로 변환한 뒤,
        네트워크 쌍 간 Spearman 상관계수를 계산한다.
        
        Args:
            networks: {네트워크ID: NetworkX 그래프} 딕셔너리
                      (예: {"RAN": G_ran, "SA": G_sa, "CT": G_ct})
            
        Returns:
            상관계수 행렬 DataFrame (네트워크ID × 네트워크ID)
            
        Note:
            - 원본 노트북은 원본 값에 Pearson 적용 오류 있었음
            - 순위 기반 Spearman으로 정정 (요구사항 12.4)
            - 공통 노드만 대상으로 상관계수 계산
        """
        if len(networks) < 2:
            logger.warning_with_details(
                f"네트워크가 2개 미만({len(networks)}): 상관분석을 수행할 수 없습니다.",
                stage="advanced",
            )
            return pd.DataFrame()
        
        # 각 네트워크의 Degree Centrality 계산
        centrality_dict: Dict[str, pd.Series] = {}
        
        for network_id, G in networks.items():
            if len(G) == 0:
                continue
            
            # Degree Centrality 계산 (비가중)
            dc = nx.degree_centrality(G)
            # Series로 변환
            centrality_dict[network_id] = pd.Series(dc)
        
        if len(centrality_dict) < 2:
            logger.warning_with_details(
                f"유효한 네트워크가 2개 미만: 상관분석을 수행할 수 없습니다.",
                stage="advanced",
            )
            return pd.DataFrame()
        
        # DataFrame 생성 (노드 × 네트워크ID)
        centrality_df = pd.DataFrame(centrality_dict)
        
        # 공통 노드만 유지 (NaN 제거)
        common_nodes = centrality_df.dropna()
        
        if len(common_nodes) < 3:
            logger.warning_with_details(
                f"공통 노드가 3개 미만({len(common_nodes)}): 상관분석이 의미 없습니다.",
                stage="advanced",
            )
            return pd.DataFrame()
        
        # 순위(rank)로 변환
        ranked_df = common_nodes.rank()
        
        # Spearman 상관계수 계산
        # pandas .corr(method='spearman')도 가능하지만, 
        # 여기서는 이미 rank 변환했으므로 pearson으로 동일한 결과
        correlation_matrix = ranked_df.corr(method='spearman')
        
        logger.info_with_details(
            f"중심성 상관분석 완료: {len(networks)}개 네트워크, {len(common_nodes)}개 공통 노드",
            stage="advanced",
            details={
                "networks": list(networks.keys()),
                "common_nodes": len(common_nodes),
            },
        )
        
        return correlation_matrix
    
    def sensitivity_analysis(
        self,
        edge_df: pd.DataFrame,
        thresholds: Optional[List[int]] = None,
        weight_column: str = "Weight",
    ) -> pd.DataFrame:
        """Threshold별 네트워크 지표 민감도 분석.
        
        threshold 0~9 각 단계에서 네트워크 지표 값을 계산하여 민감도를 분석한다.
        
        Args:
            edge_df: Edge list DataFrame (Source, Target, Weight 컬럼 필수)
            thresholds: 분석할 threshold 목록 (기본: [0, 1, 2, ..., 9])
            weight_column: 가중치 컬럼명 (기본: "Weight")
            
        Returns:
            민감도 분석 결과 DataFrame
            
        Note:
            - 대표 시간 값에 한정 실행 권장 (요구사항 12 참고)
        """
        if thresholds is None:
            thresholds = list(range(10))  # 0~9
        
        required_columns = ["Source", "Target"]
        missing = [col for col in required_columns if col not in edge_df.columns]
        if missing:
            raise ValueError(f"필수 컬럼이 누락되었습니다: {missing}")
        
        results: List[SensitivityResult] = []
        
        for threshold in thresholds:
            # Threshold 적용 필터링
            if weight_column in edge_df.columns:
                filtered_df = edge_df[edge_df[weight_column] > threshold].copy()
            else:
                # weight 컬럼이 없으면 threshold=0일 때만 전체 데이터 사용
                if threshold == 0:
                    filtered_df = edge_df.copy()
                else:
                    filtered_df = pd.DataFrame(columns=edge_df.columns)
            
            # 그래프 생성
            if len(filtered_df) == 0:
                result = SensitivityResult(
                    threshold=threshold,
                    nodes=0,
                    edges=0,
                    density=0.0,
                    avg_degree=0.0,
                    avg_clustering=0.0,
                    connected_components=0,
                    lcc_ratio=0.0,
                )
            else:
                if weight_column in filtered_df.columns:
                    G = nx.from_pandas_edgelist(
                        filtered_df,
                        source="Source",
                        target="Target",
                        edge_attr=weight_column,
                    )
                else:
                    G = nx.from_pandas_edgelist(
                        filtered_df,
                        source="Source",
                        target="Target",
                    )
                
                n_nodes = G.number_of_nodes()
                n_edges = G.number_of_edges()
                
                # 지표 계산
                density = nx.density(G) if n_nodes > 0 else 0.0
                
                avg_degree = (2 * n_edges / n_nodes) if n_nodes > 0 else 0.0
                
                avg_clustering = nx.average_clustering(G) if n_nodes > 0 else 0.0
                
                connected_components = nx.number_connected_components(G) if n_nodes > 0 else 0
                
                # LCC 비율
                if n_nodes > 0:
                    largest_cc = max(nx.connected_components(G), key=len)
                    lcc_ratio = len(largest_cc) / n_nodes
                else:
                    lcc_ratio = 0.0
                
                result = SensitivityResult(
                    threshold=threshold,
                    nodes=n_nodes,
                    edges=n_edges,
                    density=round(density, 6),
                    avg_degree=round(avg_degree, 4),
                    avg_clustering=round(avg_clustering, 4),
                    connected_components=connected_components,
                    lcc_ratio=round(lcc_ratio, 4),
                )
            
            results.append(result)
        
        # DataFrame 생성
        df = pd.DataFrame([r.to_dict() for r in results])
        
        logger.info_with_details(
            f"민감도 분석 완료: {len(thresholds)}개 threshold 분석",
            stage="advanced",
            details={
                "thresholds": thresholds,
                "results_count": len(results),
            },
        )
        
        return df
    
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
        """
        required_columns = ["Source", "Target"]
        missing = [col for col in required_columns if col not in edge_df.columns]
        if missing:
            raise ValueError(f"필수 컬럼이 누락되었습니다: {missing}")
        
        if len(edge_df) == 0:
            return nx.Graph()
        
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
    
    def save_power_law_result(
        self,
        result: PowerLawResult,
        filename_prefix: str,
        include_csv: bool = True,
        include_parquet: bool = True,
    ) -> Dict[str, Path]:
        """Power-law 분석 결과 저장.
        
        Args:
            result: PowerLawResult 객체
            filename_prefix: 파일명 prefix
            include_csv: CSV 형식 저장 여부
            include_parquet: Parquet 형식 저장 여부
            
        Returns:
            저장된 파일 경로 딕셔너리
        """
        saved_files: Dict[str, Path] = {}
        df = pd.DataFrame([result.to_dict()])
        
        if include_csv:
            csv_path = self.output_dir / f"{filename_prefix}_powerlaw.csv"
            df.to_csv(csv_path, index=False)
            saved_files["csv"] = csv_path
        
        if include_parquet:
            parquet_path = self.output_dir / f"{filename_prefix}_powerlaw.parquet"
            df.to_parquet(parquet_path, index=False)
            saved_files["parquet"] = parquet_path
        
        return saved_files
    
    def save_small_world_result(
        self,
        result: SmallWorldResult,
        filename_prefix: str,
        include_csv: bool = True,
        include_parquet: bool = True,
    ) -> Dict[str, Path]:
        """Small-world 분석 결과 저장.
        
        Args:
            result: SmallWorldResult 객체
            filename_prefix: 파일명 prefix
            include_csv: CSV 형식 저장 여부
            include_parquet: Parquet 형식 저장 여부
            
        Returns:
            저장된 파일 경로 딕셔너리
        """
        saved_files: Dict[str, Path] = {}
        df = pd.DataFrame([result.to_dict()])
        
        if include_csv:
            csv_path = self.output_dir / f"{filename_prefix}_smallworld.csv"
            df.to_csv(csv_path, index=False)
            saved_files["csv"] = csv_path
        
        if include_parquet:
            parquet_path = self.output_dir / f"{filename_prefix}_smallworld.parquet"
            df.to_parquet(parquet_path, index=False)
            saved_files["parquet"] = parquet_path
        
        return saved_files
    
    def save_mst(
        self,
        mst: nx.Graph,
        filename_prefix: str,
        weight_column: str = "Weight",
    ) -> Dict[str, Path]:
        """MST를 Edge list로 저장.
        
        Args:
            mst: Maximum Spanning Tree NetworkX 그래프
            filename_prefix: 파일명 prefix
            weight_column: 가중치 컬럼명
            
        Returns:
            저장된 파일 경로 딕셔너리
        """
        saved_files: Dict[str, Path] = {}
        
        if len(mst) == 0:
            logger.warning_with_details(
                "빈 MST: 저장할 내용이 없습니다.",
                stage="advanced",
            )
            return saved_files
        
        # Edge list로 변환
        edges = []
        for u, v, data in mst.edges(data=True):
            edge = {
                "Source": u,
                "Target": v,
                weight_column: data.get(weight_column, 1),
            }
            edges.append(edge)
        
        df = pd.DataFrame(edges)
        
        csv_path = self.output_dir / f"{filename_prefix}_mst.csv"
        df.to_csv(csv_path, index=False)
        saved_files["csv"] = csv_path
        
        parquet_path = self.output_dir / f"{filename_prefix}_mst.parquet"
        df.to_parquet(parquet_path, index=False)
        saved_files["parquet"] = parquet_path
        
        return saved_files
    
    def save_sensitivity_analysis(
        self,
        df: pd.DataFrame,
        filename_prefix: str,
        include_csv: bool = True,
        include_parquet: bool = True,
    ) -> Dict[str, Path]:
        """민감도 분석 결과 저장.
        
        Args:
            df: 민감도 분석 결과 DataFrame
            filename_prefix: 파일명 prefix
            include_csv: CSV 형식 저장 여부
            include_parquet: Parquet 형식 저장 여부
            
        Returns:
            저장된 파일 경로 딕셔너리
        """
        saved_files: Dict[str, Path] = {}
        
        if include_csv:
            csv_path = self.output_dir / f"{filename_prefix}_sensitivity.csv"
            df.to_csv(csv_path, index=False)
            saved_files["csv"] = csv_path
        
        if include_parquet:
            parquet_path = self.output_dir / f"{filename_prefix}_sensitivity.parquet"
            df.to_parquet(parquet_path, index=False)
            saved_files["parquet"] = parquet_path
        
        return saved_files
    
    def save_correlation_matrix(
        self,
        correlation_df: pd.DataFrame,
        filename_prefix: str,
        include_csv: bool = True,
        include_parquet: bool = True,
    ) -> Dict[str, Path]:
        """상관계수 행렬 저장.
        
        Args:
            correlation_df: 상관계수 행렬 DataFrame
            filename_prefix: 파일명 prefix
            include_csv: CSV 형식 저장 여부
            include_parquet: Parquet 형식 저장 여부
            
        Returns:
            저장된 파일 경로 딕셔너리
        """
        saved_files: Dict[str, Path] = {}
        
        if include_csv:
            csv_path = self.output_dir / f"{filename_prefix}_correlation.csv"
            correlation_df.to_csv(csv_path, index=True)
            saved_files["csv"] = csv_path
        
        if include_parquet:
            # Parquet는 index를 컬럼으로 변환하여 저장
            parquet_df = correlation_df.reset_index()
            parquet_df = parquet_df.rename(columns={"index": "network_id"})
            parquet_path = self.output_dir / f"{filename_prefix}_correlation.parquet"
            parquet_df.to_parquet(parquet_path, index=False)
            saved_files["parquet"] = parquet_path
        
        return saved_files
    
    def analyze_all(
        self,
        G: nx.Graph,
        edge_df: Optional[pd.DataFrame] = None,
        tsg_networks: Optional[Dict[str, nx.Graph]] = None,
        filename_prefix: Optional[str] = None,
        save_results: bool = True,
    ) -> Dict[str, Any]:
        """모든 고급 분석 수행.
        
        Power-law, Small-world, MST, 상관분석, 민감도 분석을 모두 수행한다.
        
        Args:
            G: 분석 대상 메인 NetworkX 그래프
            edge_df: Edge list DataFrame (민감도 분석용, 선택)
            tsg_networks: TSG별 네트워크 딕셔너리 (상관분석용, 선택)
            filename_prefix: 결과 저장 파일명 prefix (선택)
            save_results: 결과 저장 여부 (기본: True)
            
        Returns:
            모든 분석 결과를 포함하는 딕셔너리
        """
        results: Dict[str, Any] = {}
        
        # Power-law 분석
        power_law_result = self.analyze_power_law(G)
        results["power_law"] = power_law_result
        
        # Small-world 분석
        small_world_result = self.compute_small_world(G)
        results["small_world"] = small_world_result
        
        # MST 추출
        mst = self.extract_mst(G)
        results["mst"] = mst
        results["mst_nodes"] = mst.number_of_nodes()
        results["mst_edges"] = mst.number_of_edges()
        
        # 중심성 상관분석 (TSG 네트워크 제공 시)
        if tsg_networks is not None and len(tsg_networks) >= 2:
            correlation_matrix = self.analyze_centrality_correlation(tsg_networks)
            results["centrality_correlation"] = correlation_matrix
        
        # 민감도 분석 (Edge DataFrame 제공 시)
        if edge_df is not None:
            sensitivity_df = self.sensitivity_analysis(edge_df)
            results["sensitivity"] = sensitivity_df
        
        # 결과 저장
        if save_results and filename_prefix:
            if power_law_result:
                self.save_power_law_result(power_law_result, filename_prefix)
            if small_world_result:
                self.save_small_world_result(small_world_result, filename_prefix)
            if mst.number_of_edges() > 0:
                self.save_mst(mst, filename_prefix)
            if "centrality_correlation" in results and len(results["centrality_correlation"]) > 0:
                self.save_correlation_matrix(results["centrality_correlation"], filename_prefix)
            if "sensitivity" in results:
                self.save_sensitivity_analysis(results["sensitivity"], filename_prefix)
        
        logger.info_with_details(
            "모든 고급 분석 완료",
            stage="advanced",
            details={
                "power_law": power_law_result is not None,
                "small_world": small_world_result is not None,
                "mst_edges": mst.number_of_edges() if mst else 0,
                "correlation": "centrality_correlation" in results,
                "sensitivity": "sensitivity" in results,
            },
        )
        
        return results
