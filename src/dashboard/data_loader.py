"""
Dashboard Data Loader Module

분석 결과 데이터를 로드하는 유틸리티 모듈.

요구사항:
- 13.1: 분석 결과 데이터 로드 기능 제공
- 16.3: 사전 계산된 분석 결과(Parquet)를 로드하여 5초 이내 로딩 보장

데이터 소스:
- data/processed/: 네트워크 Edge list (Parquet)
- data/results/: 네트워크 통계, 중심성, 커뮤니티 분석 결과

파일 네이밍 패턴:
- Edge list: company_{tsg}_{time_unit}_{time_value}_{threshold}.parquet
- WI Edge list: wi_{tsg}_{time_unit}_{time_value}_{threshold}.parquet
- Statistics: statistics_{tsg}_{time_unit}.parquet 또는 statistics_{tsg}_{time_unit}.csv
- Centrality: centrality_{tsg}_{time_unit}_{time_value}.parquet
- Community: community_{tsg}_{time_unit}_{time_value}.parquet
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import pandas as pd

from src.utils.config_loader import NetworkConfig, PROJECT_ROOT, load_config
from src.utils.logger import get_logger

# FilterSelection은 components.filter_panel에서 임포트
# 순환 임포트 방지를 위해 TYPE_CHECKING 내부에서 임포트
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.dashboard.components.filter_panel import FilterSelection

# 모듈 로거
logger = get_logger("dashboard", default_stage="data_loader")

# 기본 데이터 디렉토리 경로
DEFAULT_PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
DEFAULT_RESULTS_DIR = PROJECT_ROOT / "data" / "results"


def get_edge_filename_from_selection(
    tsg_group: str,
    time_unit: str,
    time_value: Union[int, str],
    threshold: int,
    network_type: str = "company",
) -> str:
    """Edge list 파일명 생성.
    
    Args:
        tsg_group: TSG 그룹
        time_unit: 시간 단위
        time_value: 시간 값
        threshold: Weight 임계값
        network_type: 네트워크 유형
        
    Returns:
        파일명 문자열
    """
    return f"{network_type}_{tsg_group}_{time_unit}_{time_value}_{threshold}.parquet"


def get_centrality_filename_from_selection(
    tsg_group: str,
    time_unit: str,
    time_value: Union[int, str],
) -> str:
    """Centrality 파일명 생성."""
    return f"centrality_{tsg_group}_{time_unit}_{time_value}.parquet"


def get_community_filename_from_selection(
    tsg_group: str,
    time_unit: str,
    time_value: Union[int, str],
) -> str:
    """Community 파일명 생성."""
    return f"community_{tsg_group}_{time_unit}_{time_value}.parquet"


@dataclass
class EdgeListData:
    """Edge List 데이터 컨테이너.
    
    Attributes:
        df: Edge list DataFrame (Source, Target, Weight 컬럼 포함)
        tsg_group: TSG 그룹
        time_unit: 시간 단위
        time_value: 시간 값
        threshold: Weight 임계값
        network_type: 네트워크 유형
    """
    df: pd.DataFrame
    tsg_group: str
    time_unit: str
    time_value: Union[int, str]
    threshold: int
    network_type: str
    
    @property
    def edge_count(self) -> int:
        """Edge 수 반환."""
        return len(self.df)
    
    @property
    def total_weight(self) -> int:
        """전체 Weight 합계."""
        if "Weight" in self.df.columns:
            return int(self.df["Weight"].sum())
        return 0
    
    @property
    def node_count(self) -> int:
        """고유 노드 수 반환."""
        if self.df.empty:
            return 0
        nodes = set(self.df["Source"].unique()) | set(self.df["Target"].unique())
        return len(nodes)


@dataclass
class CentralityData:
    """중심성 데이터 컨테이너.
    
    Attributes:
        df: 중심성 DataFrame (node, degree_centrality, betweenness_centrality, 
            closeness_centrality, eigenvector_centrality 컬럼 포함)
        tsg_group: TSG 그룹
        time_unit: 시간 단위
        time_value: 시간 값
    """
    df: pd.DataFrame
    tsg_group: str
    time_unit: str
    time_value: Union[int, str]
    
    def get_top_n(self, metric: str = "degree_centrality", n: int = 10) -> pd.DataFrame:
        """특정 중심성 지표 기준 상위 N개 노드 반환.
        
        Args:
            metric: 중심성 지표 컬럼명
            n: 반환할 노드 수
            
        Returns:
            상위 N개 노드 DataFrame
        """
        if self.df.empty or metric not in self.df.columns:
            return pd.DataFrame()
        return self.df.nlargest(n, metric)
    
    def search_node(self, query: str) -> pd.DataFrame:
        """노드 이름으로 검색.
        
        Args:
            query: 검색 쿼리 (대소문자 무시)
            
        Returns:
            검색 결과 DataFrame
        """
        if self.df.empty or "node" not in self.df.columns:
            return pd.DataFrame()
        mask = self.df["node"].str.lower().str.contains(query.lower(), na=False)
        return self.df[mask]


@dataclass
class CommunityData:
    """커뮤니티 데이터 컨테이너.
    
    Attributes:
        df: 커뮤니티 DataFrame (node, community_id 컬럼 포함)
        tsg_group: TSG 그룹
        time_unit: 시간 단위
        time_value: 시간 값
        modularity: 모듈성 값 (선택적)
    """
    df: pd.DataFrame
    tsg_group: str
    time_unit: str
    time_value: Union[int, str]
    modularity: Optional[float] = None
    
    @property
    def community_count(self) -> int:
        """커뮤니티 수 반환."""
        if self.df.empty or "community_id" not in self.df.columns:
            return 0
        return self.df["community_id"].nunique()
    
    def get_community_sizes(self) -> Dict[int, int]:
        """커뮤니티별 크기 반환."""
        if self.df.empty or "community_id" not in self.df.columns:
            return {}
        return self.df["community_id"].value_counts().to_dict()
    
    def get_community_members(self, community_id: int) -> List[str]:
        """특정 커뮤니티의 멤버 목록 반환."""
        if self.df.empty or "community_id" not in self.df.columns:
            return []
        mask = self.df["community_id"] == community_id
        if "node" in self.df.columns:
            return self.df[mask]["node"].tolist()
        return []
    
    def get_largest_communities(self, top_n: int = 5) -> List[Tuple[int, int]]:
        """가장 큰 N개 커뮤니티 반환.
        
        Returns:
            [(community_id, size), ...] 리스트
        """
        sizes = self.get_community_sizes()
        sorted_communities = sorted(sizes.items(), key=lambda x: x[1], reverse=True)
        return sorted_communities[:top_n]


@dataclass
class StatisticsData:
    """네트워크 통계 데이터 컨테이너.
    
    Attributes:
        df: 통계 DataFrame (시간 값별 통계 지표 포함)
        tsg_group: TSG 그룹
        time_unit: 시간 단위
    """
    df: pd.DataFrame
    tsg_group: str
    time_unit: str
    
    def get_time_series(self, metric: str) -> pd.DataFrame:
        """특정 지표의 시계열 데이터 반환.
        
        Args:
            metric: 통계 지표명
            
        Returns:
            시간 값과 지표 값 DataFrame
        """
        if self.df.empty or metric not in self.df.columns:
            return pd.DataFrame()
        
        time_col = "time_value" if "time_value" in self.df.columns else self.df.columns[0]
        return self.df[[time_col, metric]].copy()


class DashboardDataLoader:
    """대시보드 데이터 로더 클래스.
    
    분석 결과 데이터를 로드하여 대시보드 컴포넌트에 제공한다.
    Parquet 형식의 사전 계산된 결과를 로드하여 빠른 응답 시간을 보장한다.
    
    Attributes:
        processed_dir: Edge list 저장 디렉토리
        results_dir: 분석 결과 저장 디렉토리
        network_config: 네트워크 설정 (threshold, time_unit 등 유효값 목록)
    
    Example:
        >>> loader = DashboardDataLoader()
        >>> edge_data = loader.load_edge_list(
        ...     FilterSelection("RAN", "year", 2023, 3, "company")
        ... )
        >>> if edge_data:
        ...     print(f"Edge 수: {edge_data.edge_count}")
    """
    
    def __init__(
        self,
        processed_dir: Optional[Path] = None,
        results_dir: Optional[Path] = None,
        network_config: Optional[NetworkConfig] = None,
    ):
        """DashboardDataLoader 초기화.
        
        Args:
            processed_dir: Edge list 디렉토리. None이면 기본 경로 사용.
            results_dir: 분석 결과 디렉토리. None이면 기본 경로 사용.
            network_config: 네트워크 설정. None이면 config 파일에서 로드.
        """
        self.processed_dir = processed_dir or DEFAULT_PROCESSED_DIR
        self.results_dir = results_dir or DEFAULT_RESULTS_DIR
        
        # 네트워크 설정 로드
        if network_config is None:
            try:
                self.network_config = load_config("network")
            except FileNotFoundError:
                logger.warning(
                    "network.yaml 설정 파일을 찾을 수 없습니다. 기본값을 사용합니다."
                )
                self.network_config = NetworkConfig(
                    thresholds=list(range(10)),
                    time_units=["year", "release", "quarter"],
                    tsg_groups=["ALL", "RAN", "SA", "CT"],
                )
        else:
            self.network_config = network_config
        
        logger.info(
            f"DashboardDataLoader 초기화 완료: processed_dir={self.processed_dir}, results_dir={self.results_dir}"
        )
    
    # =========================================================================
    # 유효값 목록 조회 메서드
    # =========================================================================
    
    def get_available_tsg_groups(self) -> List[str]:
        """사용 가능한 TSG 그룹 목록 반환."""
        return self.network_config.tsg_groups
    
    def get_available_time_units(self) -> List[str]:
        """사용 가능한 시간 단위 목록 반환."""
        return self.network_config.time_units
    
    def get_available_thresholds(self) -> List[int]:
        """사용 가능한 threshold 목록 반환."""
        return self.network_config.thresholds
    
    def get_available_network_types(self) -> List[str]:
        """사용 가능한 네트워크 유형 목록 반환."""
        return ["company", "wi"]
    
    def get_available_time_values(
        self,
        time_unit: str,
        tsg_group: str = "ALL",
        network_type: str = "company",
    ) -> List[Union[int, str]]:
        """특정 조건에서 사용 가능한 시간 값 목록 반환.
        
        실제 저장된 파일을 스캔하여 사용 가능한 시간 값을 반환한다.
        
        Args:
            time_unit: 시간 단위
            tsg_group: TSG 그룹
            network_type: 네트워크 유형
            
        Returns:
            사용 가능한 시간 값 리스트 (정렬됨)
        """
        time_values: Set[Union[int, str]] = set()
        
        # 파일 패턴: {network_type}_{tsg}_{time_unit}_{time_value}_{threshold}.parquet
        pattern = f"{network_type}_{tsg_group}_{time_unit}_*.parquet"
        
        for file_path in self.processed_dir.glob(pattern):
            # 파일명에서 time_value 추출
            filename = file_path.stem  # 확장자 제외
            parts = filename.split("_")
            
            # 예: company_ALL_year_2023_0 -> parts = [company, ALL, year, 2023, 0]
            if len(parts) >= 5:
                time_value_str = parts[3]
                
                # 숫자면 int로 변환, 아니면 문자열 유지
                try:
                    time_values.add(int(time_value_str))
                except ValueError:
                    time_values.add(time_value_str)
        
        # 정렬하여 반환
        return sorted(time_values, key=lambda x: (isinstance(x, str), x))
    
    # =========================================================================
    # Edge List 로드 메서드
    # =========================================================================
    
    def load_edge_list(
        self,
        tsg_group: str,
        time_unit: str,
        time_value: Union[int, str],
        threshold: int,
        network_type: str = "company",
    ) -> Optional[EdgeListData]:
        """Edge list 파일 로드.
        
        Args:
            tsg_group: TSG 그룹
            time_unit: 시간 단위
            time_value: 시간 값
            threshold: Weight 임계값
            network_type: 네트워크 유형
            
        Returns:
            EdgeListData 또는 None (파일이 없거나 로드 실패 시)
        """
        filename = get_edge_filename_from_selection(
            tsg_group, time_unit, time_value, threshold, network_type
        )
        file_path = self.processed_dir / filename
        
        if not file_path.exists():
            logger.warning(
                f"Edge list 파일을 찾을 수 없습니다: {filename}. "
                f"분석 파이프라인을 먼저 실행하세요."
            )
            return None
        
        try:
            df = pd.read_parquet(file_path)
            logger.info(f"Edge list 로드 완료: {filename}, edge_count={len(df)}")
            return EdgeListData(
                df=df,
                tsg_group=tsg_group,
                time_unit=time_unit,
                time_value=time_value,
                threshold=threshold,
                network_type=network_type,
            )
        except PermissionError as e:
            logger.error(
                f"Edge list 파일 접근 권한 오류: {filename}. "
                f"파일 권한을 확인하세요. error={e}"
            )
            return None
        except Exception as e:
            logger.error(
                f"Edge list 로드 실패: {filename}. "
                f"파일이 손상되었거나 형식이 올바르지 않습니다. error={e}"
            )
            return None
    
    def load_edge_list_from_selection(
        self,
        selection: "FilterSelection",
    ) -> Optional[EdgeListData]:
        """FilterSelection 객체에서 Edge list 로드.
        
        Args:
            selection: 필터 선택 값 (components.filter_panel.FilterSelection)
            
        Returns:
            EdgeListData 또는 None
        """
        return self.load_edge_list(
            tsg_group=selection.tsg_group,
            time_unit=selection.time_unit,
            time_value=selection.time_value,
            threshold=selection.threshold,
            network_type=selection.network_type,
        )
    
    def load_all_edge_lists_for_time_unit(
        self,
        tsg_group: str,
        time_unit: str,
        threshold: int = 0,
        network_type: str = "company",
    ) -> Dict[Union[int, str], EdgeListData]:
        """특정 시간 단위의 모든 Edge list 로드.
        
        시계열 분석을 위해 특정 TSG 그룹과 시간 단위에 대해
        모든 시간 값의 Edge list를 로드한다.
        
        Args:
            tsg_group: TSG 그룹
            time_unit: 시간 단위
            threshold: Weight 임계값
            network_type: 네트워크 유형
            
        Returns:
            {time_value: EdgeListData} 딕셔너리
        """
        result = {}
        
        time_values = self.get_available_time_values(time_unit, tsg_group, network_type)
        
        for time_value in time_values:
            edge_data = self.load_edge_list(
                tsg_group=tsg_group,
                time_unit=time_unit,
                time_value=time_value,
                threshold=threshold,
                network_type=network_type,
            )
            if edge_data:
                result[time_value] = edge_data
        
        logger.info(
            f"시간 단위별 Edge list 로드 완료: tsg_group={tsg_group}, time_unit={time_unit}, loaded_count={len(result)}"
        )
        return result
    
    # =========================================================================
    # 통계 데이터 로드 메서드
    # =========================================================================
    
    def load_statistics(
        self,
        tsg_group: str,
        time_unit: str,
    ) -> Optional[StatisticsData]:
        """네트워크 통계 데이터 로드.
        
        Args:
            tsg_group: TSG 그룹
            time_unit: 시간 단위
            
        Returns:
            StatisticsData 또는 None (파일이 없거나 로드 실패 시)
        """
        # Parquet 파일 우선 시도
        parquet_filename = f"statistics_{tsg_group}_{time_unit}.parquet"
        parquet_path = self.results_dir / parquet_filename
        
        if parquet_path.exists():
            try:
                df = pd.read_parquet(parquet_path)
                logger.info(f"통계 데이터 로드 완료 (Parquet): {parquet_filename}")
                return StatisticsData(
                    df=df,
                    tsg_group=tsg_group,
                    time_unit=time_unit,
                )
            except PermissionError as e:
                logger.error(
                    f"통계 파일 접근 권한 오류: {parquet_filename}. "
                    f"파일 권한을 확인하세요. error={e}"
                )
            except Exception as e:
                logger.warning(
                    f"Parquet 통계 로드 실패: {parquet_filename}. "
                    f"CSV 형식으로 재시도합니다. error={e}"
                )
        
        # CSV 파일 fallback
        csv_filename = f"statistics_{tsg_group}_{time_unit}.csv"
        csv_path = self.results_dir / csv_filename
        
        if csv_path.exists():
            try:
                df = pd.read_csv(csv_path)
                logger.info(f"통계 데이터 로드 완료 (CSV): {csv_filename}")
                return StatisticsData(
                    df=df,
                    tsg_group=tsg_group,
                    time_unit=time_unit,
                )
            except PermissionError as e:
                logger.error(
                    f"CSV 통계 파일 접근 권한 오류: {csv_filename}. error={e}"
                )
            except Exception as e:
                logger.error(
                    f"CSV 통계 로드 실패: {csv_filename}. "
                    f"파일이 손상되었을 수 있습니다. error={e}"
                )
        
        logger.warning(
            f"통계 파일을 찾을 수 없습니다: {tsg_group}, {time_unit}. "
            f"분석 파이프라인을 실행하여 결과를 생성하세요."
        )
        return None
    
    def load_all_statistics(self) -> Dict[str, StatisticsData]:
        """모든 TSG 그룹 × 시간 단위의 통계 로드.
        
        Returns:
            {"{tsg_group}_{time_unit}": StatisticsData} 딕셔너리
        """
        result = {}
        
        for tsg_group in self.network_config.tsg_groups:
            for time_unit in self.network_config.time_units:
                stats_data = self.load_statistics(tsg_group, time_unit)
                if stats_data:
                    key = f"{tsg_group}_{time_unit}"
                    result[key] = stats_data
        
        logger.info(f"전체 통계 데이터 로드 완료: {len(result)}개")
        return result
    
    # =========================================================================
    # 중심성 데이터 로드 메서드
    # =========================================================================
    
    def load_centrality(
        self,
        tsg_group: str,
        time_unit: str,
        time_value: Union[int, str],
    ) -> Optional[CentralityData]:
        """중심성 데이터 로드.
        
        Args:
            tsg_group: TSG 그룹
            time_unit: 시간 단위
            time_value: 시간 값
            
        Returns:
            CentralityData 또는 None (파일이 없거나 로드 실패 시)
        """
        filename = f"centrality_{tsg_group}_{time_unit}_{time_value}.parquet"
        file_path = self.results_dir / filename
        
        if not file_path.exists():
            # CSV fallback 시도
            csv_filename = f"centrality_{tsg_group}_{time_unit}_{time_value}.csv"
            csv_path = self.results_dir / csv_filename
            
            if csv_path.exists():
                try:
                    df = pd.read_csv(csv_path)
                    logger.info(f"중심성 데이터 로드 완료 (CSV): {csv_filename}")
                    return CentralityData(
                        df=df,
                        tsg_group=tsg_group,
                        time_unit=time_unit,
                        time_value=time_value,
                    )
                except PermissionError as e:
                    logger.error(
                        f"CSV 중심성 파일 접근 권한 오류: {csv_filename}. error={e}"
                    )
                    return None
                except Exception as e:
                    logger.error(
                        f"CSV 중심성 로드 실패: {csv_filename}. "
                        f"파일이 손상되었을 수 있습니다. error={e}"
                    )
                    return None
            
            logger.warning(
                f"중심성 파일을 찾을 수 없습니다: {filename}. "
                f"분석 파이프라인을 실행하여 결과를 생성하세요."
            )
            return None
        
        try:
            df = pd.read_parquet(file_path)
            logger.info(f"중심성 데이터 로드 완료: {filename}")
            return CentralityData(
                df=df,
                tsg_group=tsg_group,
                time_unit=time_unit,
                time_value=time_value,
            )
        except PermissionError as e:
            logger.error(
                f"중심성 파일 접근 권한 오류: {filename}. "
                f"파일 권한을 확인하세요. error={e}"
            )
            return None
        except Exception as e:
            logger.error(
                f"중심성 데이터 로드 실패: {filename}. "
                f"파일이 손상되었거나 형식이 올바르지 않습니다. error={e}"
            )
            return None
    
    def load_centrality_from_selection(
        self,
        selection: "FilterSelection",
    ) -> Optional[CentralityData]:
        """FilterSelection에서 중심성 데이터 로드."""
        return self.load_centrality(
            selection.tsg_group,
            selection.time_unit,
            selection.time_value,
        )
    
    # =========================================================================
    # 커뮤니티 데이터 로드 메서드
    # =========================================================================
    
    def load_community(
        self,
        tsg_group: str,
        time_unit: str,
        time_value: Union[int, str],
    ) -> Optional[CommunityData]:
        """커뮤니티 데이터 로드.
        
        Args:
            tsg_group: TSG 그룹
            time_unit: 시간 단위
            time_value: 시간 값
            
        Returns:
            CommunityData 또는 None (파일이 없거나 로드 실패 시)
        """
        filename = f"community_{tsg_group}_{time_unit}_{time_value}.parquet"
        file_path = self.results_dir / filename
        
        if not file_path.exists():
            # CSV fallback 시도
            csv_filename = f"community_{tsg_group}_{time_unit}_{time_value}.csv"
            csv_path = self.results_dir / csv_filename
            
            if csv_path.exists():
                try:
                    df = pd.read_csv(csv_path)
                    logger.info(f"커뮤니티 데이터 로드 완료 (CSV): {csv_filename}")
                    return CommunityData(
                        df=df,
                        tsg_group=tsg_group,
                        time_unit=time_unit,
                        time_value=time_value,
                    )
                except PermissionError as e:
                    logger.error(
                        f"CSV 커뮤니티 파일 접근 권한 오류: {csv_filename}. error={e}"
                    )
                    return None
                except Exception as e:
                    logger.error(
                        f"CSV 커뮤니티 로드 실패: {csv_filename}. "
                        f"파일이 손상되었을 수 있습니다. error={e}"
                    )
                    return None
            
            logger.warning(
                f"커뮤니티 파일을 찾을 수 없습니다: {filename}. "
                f"분석 파이프라인을 실행하여 결과를 생성하세요."
            )
            return None
        
        try:
            df = pd.read_parquet(file_path)
            
            # modularity 값 추출 (메타데이터에서 또는 별도 컬럼에서)
            modularity = None
            if "modularity" in df.columns:
                modularity = df["modularity"].iloc[0] if len(df) > 0 else None
            
            logger.info(f"커뮤니티 데이터 로드 완료: {filename}")
            return CommunityData(
                df=df,
                tsg_group=tsg_group,
                time_unit=time_unit,
                time_value=time_value,
                modularity=modularity,
            )
        except PermissionError as e:
            logger.error(
                f"커뮤니티 파일 접근 권한 오류: {filename}. "
                f"파일 권한을 확인하세요. error={e}"
            )
            return None
        except Exception as e:
            logger.error(
                f"커뮤니티 데이터 로드 실패: {filename}. "
                f"파일이 손상되었거나 형식이 올바르지 않습니다. error={e}"
            )
            return None
    
    def load_community_from_selection(
        self,
        selection: "FilterSelection",
    ) -> Optional[CommunityData]:
        """FilterSelection에서 커뮤니티 데이터 로드."""
        return self.load_community(
            selection.tsg_group,
            selection.time_unit,
            selection.time_value,
        )
    
    # =========================================================================
    # 복합 로드 메서드
    # =========================================================================
    
    def load_all_for_selection(
        self,
        selection: "FilterSelection",
    ) -> Dict[str, Any]:
        """FilterSelection에 대한 모든 관련 데이터 로드.
        
        Args:
            selection: 필터 선택 값
            
        Returns:
            {
                "edge_list": EdgeListData 또는 None,
                "centrality": CentralityData 또는 None,
                "community": CommunityData 또는 None,
            }
        """
        return {
            "edge_list": self.load_edge_list_from_selection(selection),
            "centrality": self.load_centrality_from_selection(selection),
            "community": self.load_community_from_selection(selection),
        }
    
    # =========================================================================
    # 데이터 가용성 확인 메서드
    # =========================================================================
    
    def has_data(
        self,
        tsg_group: str,
        time_unit: str,
        time_value: Union[int, str],
        threshold: int,
        network_type: str = "company",
    ) -> bool:
        """특정 조건에 대한 데이터 존재 여부 확인.
        
        Args:
            tsg_group: TSG 그룹
            time_unit: 시간 단위
            time_value: 시간 값
            threshold: Weight 임계값
            network_type: 네트워크 유형
            
        Returns:
            데이터 존재 여부
        """
        filename = get_edge_filename_from_selection(
            tsg_group, time_unit, time_value, threshold, network_type
        )
        file_path = self.processed_dir / filename
        return file_path.exists()
    
    def has_data_from_selection(self, selection: "FilterSelection") -> bool:
        """FilterSelection으로 데이터 존재 여부 확인."""
        return self.has_data(
            selection.tsg_group,
            selection.time_unit,
            selection.time_value,
            selection.threshold,
            selection.network_type,
        )
    
    def get_data_summary(self) -> Dict[str, Any]:
        """데이터 가용성 요약 정보 반환.
        
        Returns:
            {
                "processed_files": 파일 수,
                "results_files": 파일 수,
                "tsg_groups": 사용 가능한 TSG 그룹,
                "time_units": 사용 가능한 시간 단위,
                "thresholds": 사용 가능한 threshold,
            }
        """
        processed_files = list(self.processed_dir.glob("*.parquet"))
        results_files = list(self.results_dir.glob("*.parquet")) + list(
            self.results_dir.glob("*.csv")
        )
        
        return {
            "processed_files": len(processed_files),
            "results_files": len(results_files),
            "tsg_groups": self.get_available_tsg_groups(),
            "time_units": self.get_available_time_units(),
            "thresholds": self.get_available_thresholds(),
            "network_types": self.get_available_network_types(),
        }
    
    def scan_available_data(self) -> Dict[str, List[Dict[str, Any]]]:
        """저장된 데이터를 스캔하여 사용 가능한 조합 반환.
        
        Returns:
            {
                "company": [{"tsg_group": ..., "time_unit": ..., "time_value": ..., "threshold": ...}, ...],
                "wi": [...],
            }
        """
        result = {"company": [], "wi": []}
        
        # 파일 패턴: {network_type}_{tsg}_{time_unit}_{time_value}_{threshold}.parquet
        pattern = re.compile(
            r"^(company|wi)_([A-Z]+)_(\w+)_(.+?)_(\d+)\.parquet$"
        )
        
        for file_path in self.processed_dir.glob("*.parquet"):
            match = pattern.match(file_path.name)
            if match:
                network_type = match.group(1)
                tsg_group = match.group(2)
                time_unit = match.group(3)
                time_value_str = match.group(4)
                threshold = int(match.group(5))
                
                # time_value 타입 변환
                try:
                    time_value = int(time_value_str)
                except ValueError:
                    time_value = time_value_str
                
                result[network_type].append({
                    "tsg_group": tsg_group,
                    "time_unit": time_unit,
                    "time_value": time_value,
                    "threshold": threshold,
                })
        
        logger.info(
            f"데이터 스캔 완료: company_count={len(result['company'])}, wi_count={len(result['wi'])}"
        )
        return result


# =============================================================================
# 편의 함수
# =============================================================================


_default_loader: Optional[DashboardDataLoader] = None


def get_data_loader() -> DashboardDataLoader:
    """기본 DashboardDataLoader 인스턴스 반환 (싱글톤 패턴).
    
    Returns:
        DashboardDataLoader 인스턴스
    """
    global _default_loader
    if _default_loader is None:
        _default_loader = DashboardDataLoader()
    return _default_loader


__all__ = [
    # 데이터 컨테이너 클래스
    "EdgeListData",
    "CentralityData",
    "CommunityData",
    "StatisticsData",
    # 데이터 로더
    "DashboardDataLoader",
    "get_data_loader",
    # 유틸리티 함수
    "get_edge_filename_from_selection",
    "get_centrality_filename_from_selection",
    "get_community_filename_from_selection",
]
