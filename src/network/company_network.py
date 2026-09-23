"""
Company Network Builder Module (Stage 6)

기업 간 협력 네트워크 Edge list를 생성하는 모듈.

요구사항:
- 8.1: 동일 Work Item에 기고한 기업들의 모든 쌍(combination)을 Edge로 생성
- 8.2: 동일 WI 내에서 기업 중복 제거, (A,B)와 (B,A) 동일 Edge로 정규화
- 8.3: 두 기업이 함께 기고한 Work Item의 고유 개수를 Edge Weight로 계산
- 8.4: TSG 그룹(ALL/RAN/SA/CT) × 시간 단위(연도/Release/분기) × threshold 조합별 Edge list 생성
- 8.5: Weight threshold 이하인 Edge 제거
- 8.6: Parquet 형식으로 data/processed/ 디렉토리에 저장

Edge 생성 알고리즘:
- itertools.combinations 사용
- Source < Target 알파벳 순으로 정규화 (원본 노트북보다 견고한 명시적 정규화)

파일 저장 규칙:
- 네이밍 패턴: company_{tsg}_{time_unit}_{time_value}_{threshold}.parquet
- 예: company_ALL_year_2023_0.parquet, company_RAN_release_17_3.parquet
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import pandas as pd

from src.utils.config_loader import NetworkConfig, PROJECT_ROOT
from src.utils.logger import get_logger

# 모듈 로거
logger = get_logger("network", default_stage="company_network")

# 기본 저장 경로
DEFAULT_PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"


@dataclass
class CompanyEdgeSchema:
    """기업 간 네트워크 Edge 스키마.
    
    네트워크 Edge list DataFrame의 스키마를 정의한다.
    
    Attributes:
        Source: 기업명 A (알파벳 순으로 정렬, Source < Target)
        Target: 기업명 B (알파벳 순으로 정렬, Source < Target)
        Weight: 두 기업이 공동 기고한 Work Item의 고유 개수
        Work_Items: 공동 기고한 Work Item 목록 (선택적)
    
    Example:
        >>> edge = CompanyEdgeSchema(
        ...     Source="Ericsson",
        ...     Target="Samsung Electronics",
        ...     Weight=15,
        ...     Work_Items=["NR_eMIMO", "NR_FR2_enh", ...]
        ... )
    """
    Source: str
    Target: str
    Weight: int
    Work_Items: Optional[List[str]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환."""
        result = {
            "Source": self.Source,
            "Target": self.Target,
            "Weight": self.Weight,
        }
        if self.Work_Items is not None:
            result["Work_Items"] = self.Work_Items
        return result


@dataclass
class NetworkBuildStats:
    """네트워크 구축 통계.
    
    Attributes:
        tsg_group: TSG 그룹 (ALL, RAN, SA, CT)
        time_unit: 시간 단위 (year, release, quarter)
        time_value: 시간 값 (예: 2023, 17, "2023Q1")
        threshold: Edge Weight 임계값
        total_records: 필터링된 전체 레코드 수
        unique_companies: 고유 기업 수
        unique_work_items: 고유 Work Item 수
        edges_before_threshold: threshold 적용 전 Edge 수
        edges_after_threshold: threshold 적용 후 Edge 수
        total_weight: Edge Weight 총합
    """
    tsg_group: str
    time_unit: str
    time_value: Union[int, str]
    threshold: int
    total_records: int = 0
    unique_companies: int = 0
    unique_work_items: int = 0
    edges_before_threshold: int = 0
    edges_after_threshold: int = 0
    total_weight: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환."""
        return {
            "tsg_group": self.tsg_group,
            "time_unit": self.time_unit,
            "time_value": self.time_value,
            "threshold": self.threshold,
            "total_records": self.total_records,
            "unique_companies": self.unique_companies,
            "unique_work_items": self.unique_work_items,
            "edges_before_threshold": self.edges_before_threshold,
            "edges_after_threshold": self.edges_after_threshold,
            "total_weight": self.total_weight,
        }


class CompanyNetworkBuilder:
    """기업 간 협력 네트워크 Edge list 생성.
    
    Work Item을 매개로 한 기업 간 공동 기고 관계를 네트워크 Edge로 변환한다.
    
    Edge 생성 알고리즘:
        1. Work Item별로 그룹화
        2. 각 WI 내에서 기업 중복 제거 (drop_duplicates)
        3. 기업 쌍의 모든 조합(combinations) 생성
        4. (A,B)와 (B,A) 정규화: sorted([A,B]) → (Source, Target)
        5. 동일 기업 쌍의 WI 수를 Weight로 집계
        6. threshold 적용하여 낮은 Weight Edge 제거
    
    Attributes:
        config: NetworkConfig 설정 객체
        output_dir: Edge list 저장 디렉토리
    
    Example:
        >>> config = load_config("network")
        >>> builder = CompanyNetworkBuilder(config)
        >>> edge_df, stats = builder.build_edges(
        ...     df=preprocessed_df,
        ...     tsg_group="RAN",
        ...     time_unit="year",
        ...     time_value=2023,
        ...     threshold=3
        ... )
        >>> print(f"생성된 Edge 수: {len(edge_df)}")
    """
    
    # 필수 입력 컬럼
    REQUIRED_COLUMNS = ["company", "Work_Item", "TSG", "Year", "Quarter", "Release"]
    
    # 컬럼명 매핑 (유연한 컬럼명 처리)
    COLUMN_ALIASES = {
        "company": ["company", "Company", "source_company", "Source"],
        "Work_Item": ["Work_Item", "Work Item", "work_item", "Related_WIs", "Related WIs", "WI"],
        "TSG": ["TSG", "tsg"],
        "Year": ["Year", "year"],
        "Quarter": ["Quarter", "quarter"],
        "Release": ["Release", "release"],
    }
    
    def __init__(
        self,
        config: Optional[NetworkConfig] = None,
        output_dir: Optional[Path] = None,
    ) -> None:
        """CompanyNetworkBuilder 초기화.
        
        Args:
            config: NetworkConfig 설정 객체. None이면 기본 설정 사용.
            output_dir: Edge list 저장 디렉토리. None이면 data/processed/ 사용.
        """
        if config is not None:
            self.config = config
        else:
            # 기본 설정 사용
            from src.utils.config_loader import load_config
            self.config = load_config("network")
        
        self.output_dir = Path(output_dir) if output_dir else DEFAULT_PROCESSED_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info_with_details(
            f"CompanyNetworkBuilder 초기화 완료",
            stage="company_network",
            details={
                "thresholds": self.config.thresholds,
                "time_units": self.config.time_units,
                "tsg_groups": self.config.tsg_groups,
                "output_dir": str(self.output_dir),
            },
        )
    
    def _normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """컬럼명 정규화.
        
        다양한 형태의 컬럼명을 표준 컬럼명으로 변환한다.
        
        Args:
            df: 입력 DataFrame
            
        Returns:
            컬럼명이 정규화된 DataFrame
        """
        result_df = df.copy()
        
        for standard_name, aliases in self.COLUMN_ALIASES.items():
            # 표준 컬럼이 이미 있으면 건너뜀
            if standard_name in result_df.columns:
                continue
            for alias in aliases:
                if alias in result_df.columns and alias != standard_name:
                    result_df = result_df.rename(columns={alias: standard_name})
                    break
        
        return result_df
    
    def _validate_input(self, df: pd.DataFrame) -> None:
        """입력 DataFrame 검증.
        
        Args:
            df: 입력 DataFrame
            
        Raises:
            ValueError: 필수 컬럼이 누락된 경우
        """
        missing_columns = []
        
        for col in ["company", "Work_Item"]:  # 최소 필수 컬럼
            if col not in df.columns:
                # aliases에서 찾아보기
                found = False
                for alias in self.COLUMN_ALIASES.get(col, []):
                    if alias in df.columns:
                        found = True
                        break
                if not found:
                    missing_columns.append(col)
        
        if missing_columns:
            raise ValueError(
                f"필수 컬럼이 누락되었습니다: {missing_columns}. "
                f"DataFrame 컬럼: {list(df.columns)}"
            )
    
    def _filter_by_tsg(
        self, 
        df: pd.DataFrame, 
        tsg_group: str
    ) -> pd.DataFrame:
        """TSG 그룹으로 필터링.
        
        Args:
            df: 입력 DataFrame
            tsg_group: TSG 그룹 ('ALL', 'RAN', 'SA', 'CT')
            
        Returns:
            필터링된 DataFrame
        """
        if tsg_group.upper() == "ALL":
            return df.copy()
        
        if "TSG" not in df.columns:
            logger.warning_with_details(
                f"TSG 컬럼이 없어 TSG 필터링을 건너뜁니다.",
                stage="company_network",
                details={"tsg_group": tsg_group, "columns": list(df.columns)},
            )
            return df.copy()
        
        return df[df["TSG"].str.upper() == tsg_group.upper()].copy()
    
    def _filter_by_time(
        self,
        df: pd.DataFrame,
        time_unit: str,
        time_value: Union[int, str],
    ) -> pd.DataFrame:
        """시간 단위로 필터링.
        
        Args:
            df: 입력 DataFrame
            time_unit: 시간 단위 ('year', 'release', 'quarter')
            time_value: 시간 값 (예: 2023, 17, "2023Q1")
            
        Returns:
            필터링된 DataFrame
        """
        time_unit_lower = time_unit.lower()
        
        if time_unit_lower == "year":
            if "Year" not in df.columns:
                logger.warning_with_details(
                    "Year 컬럼이 없어 연도 필터링을 건너뜁니다.",
                    stage="company_network",
                )
                return df.copy()
            return df[df["Year"] == int(time_value)].copy()
        
        elif time_unit_lower == "release":
            if "Release" not in df.columns:
                logger.warning_with_details(
                    "Release 컬럼이 없어 릴리즈 필터링을 건너뜁니다.",
                    stage="company_network",
                )
                return df.copy()
            return df[df["Release"] == int(time_value)].copy()
        
        elif time_unit_lower == "quarter":
            if "Quarter" not in df.columns:
                logger.warning_with_details(
                    "Quarter 컬럼이 없어 분기 필터링을 건너뜁니다.",
                    stage="company_network",
                )
                return df.copy()
            return df[df["Quarter"] == str(time_value)].copy()
        
        else:
            raise ValueError(f"지원하지 않는 time_unit입니다: {time_unit}")
    
    def _create_edges_from_work_item(
        self,
        companies: List[str],
        work_item: str,
    ) -> List[Dict[str, Any]]:
        """단일 Work Item에서 기업 쌍 Edge 생성.
        
        Args:
            companies: WI에 기고한 기업 목록 (중복 제거됨)
            work_item: Work Item 코드
            
        Returns:
            Edge 정보 딕셔너리 리스트
        """
        if len(companies) < 2:
            return []
        
        edges = []
        
        # 정렬된 기업 목록에서 모든 쌍 조합 생성
        sorted_companies = sorted(companies)
        
        for pair in itertools.combinations(sorted_companies, 2):
            # Source < Target 이미 보장됨 (sorted 후 combinations)
            edges.append({
                "Source": pair[0],
                "Target": pair[1],
                "Work_Item": work_item,
            })
        
        return edges
    
    def build_edges(
        self,
        df: pd.DataFrame,
        tsg_group: str,
        time_unit: str,
        time_value: Union[int, str],
        threshold: int = 0,
        include_work_items: bool = False,
    ) -> Tuple[pd.DataFrame, NetworkBuildStats]:
        """특정 조건에 대한 Edge list 생성.
        
        처리 흐름:
            1. TSG 그룹 필터링
            2. 시간 단위 필터링
            3. Work Item별로 그룹화
            4. 각 WI 내 기업 중복 제거
            5. 기업 쌍 조합 생성 (itertools.combinations)
            6. Edge 정규화 (Source < Target)
            7. Weight 집계 (동일 기업 쌍의 WI 수)
            8. Threshold 적용
        
        Args:
            df: 전처리된 DataFrame (company, Work_Item 컬럼 필수)
            tsg_group: TSG 그룹 ('ALL', 'RAN', 'SA', 'CT')
            time_unit: 시간 단위 ('year', 'release', 'quarter')
            time_value: 시간 값 (예: 2023, 17, '2023Q1')
            threshold: Weight 임계값 (이하인 Edge 제거). 기본값: 0 (제거 없음)
            include_work_items: Edge별 Work Item 목록 포함 여부
            
        Returns:
            Tuple[Edge list DataFrame, 구축 통계]
            
        Example:
            >>> edge_df, stats = builder.build_edges(
            ...     df=preprocessed_df,
            ...     tsg_group="RAN",
            ...     time_unit="year",
            ...     time_value=2023,
            ...     threshold=3
            ... )
        """
        # 입력 검증 및 정규화
        self._validate_input(df)
        working_df = self._normalize_columns(df)
        
        # TSG 필터링
        filtered_df = self._filter_by_tsg(working_df, tsg_group)
        
        # 시간 필터링
        filtered_df = self._filter_by_time(filtered_df, time_unit, time_value)
        
        # 통계 초기화
        stats = NetworkBuildStats(
            tsg_group=tsg_group,
            time_unit=time_unit,
            time_value=time_value,
            threshold=threshold,
            total_records=len(filtered_df),
        )
        
        # 빈 DataFrame 처리
        if len(filtered_df) == 0:
            logger.info_with_details(
                f"필터링 후 데이터 없음: {tsg_group}/{time_unit}/{time_value}",
                stage="company_network",
                details=stats.to_dict(),
            )
            empty_df = pd.DataFrame(columns=["Source", "Target", "Weight"])
            if include_work_items:
                empty_df["Work_Items"] = pd.Series(dtype=object)
            return empty_df, stats
        
        # 고유 기업/WI 수
        stats.unique_companies = filtered_df["company"].nunique()
        stats.unique_work_items = filtered_df["Work_Item"].nunique()
        
        # Work Item별 Edge 생성
        all_edges: List[Dict[str, Any]] = []
        
        for work_item, group in filtered_df.groupby("Work_Item"):
            # WI 내 고유 기업 목록 (중복 제거, 요구사항 8.2)
            unique_companies = group["company"].unique().tolist()
            
            # 기업 쌍 Edge 생성
            edges = self._create_edges_from_work_item(unique_companies, str(work_item))
            all_edges.extend(edges)
        
        # 빈 Edge 리스트 처리
        if len(all_edges) == 0:
            logger.info_with_details(
                f"생성된 Edge 없음: {tsg_group}/{time_unit}/{time_value}",
                stage="company_network",
                details=stats.to_dict(),
            )
            empty_df = pd.DataFrame(columns=["Source", "Target", "Weight"])
            if include_work_items:
                empty_df["Work_Items"] = pd.Series(dtype=object)
            return empty_df, stats
        
        # Edge DataFrame 생성
        edge_df = pd.DataFrame(all_edges)
        
        # Weight 집계 (요구사항 8.3): 동일 기업 쌍의 고유 Work Item 수
        if include_work_items:
            # Work Item 목록 포함
            weight_df = (
                edge_df.groupby(["Source", "Target"])
                .agg(
                    Weight=("Work_Item", "nunique"),
                    Work_Items=("Work_Item", lambda x: list(x.unique())),
                )
                .reset_index()
            )
        else:
            # Weight만 집계
            weight_df = (
                edge_df.groupby(["Source", "Target"])
                .agg(Weight=("Work_Item", "nunique"))
                .reset_index()
            )
        
        stats.edges_before_threshold = len(weight_df)
        
        # Threshold 적용 (요구사항 8.5)
        if threshold > 0:
            weight_df = weight_df[weight_df["Weight"] > threshold].copy()
        
        stats.edges_after_threshold = len(weight_df)
        stats.total_weight = int(weight_df["Weight"].sum()) if len(weight_df) > 0 else 0
        
        # 로그 기록
        logger.info_with_details(
            f"Edge 생성 완료: {tsg_group}/{time_unit}/{time_value} (threshold={threshold}): "
            f"{stats.edges_before_threshold}→{stats.edges_after_threshold} edges",
            stage="company_network",
            details=stats.to_dict(),
        )
        
        return weight_df, stats
    
    def _get_time_values(
        self,
        df: pd.DataFrame,
        time_unit: str,
    ) -> List[Union[int, str]]:
        """시간 단위별 고유 값 목록 추출.
        
        Args:
            df: 입력 DataFrame
            time_unit: 시간 단위
            
        Returns:
            고유 시간 값 목록
        """
        time_unit_lower = time_unit.lower()
        
        if time_unit_lower == "year":
            if "Year" not in df.columns:
                return []
            return sorted(df["Year"].dropna().unique().tolist())
        
        elif time_unit_lower == "release":
            if "Release" not in df.columns:
                return []
            return sorted(df["Release"].dropna().unique().tolist())
        
        elif time_unit_lower == "quarter":
            if "Quarter" not in df.columns:
                return []
            return sorted(df["Quarter"].dropna().unique().tolist())
        
        return []
    
    def _generate_filename(
        self,
        tsg_group: str,
        time_unit: str,
        time_value: Union[int, str],
        threshold: int,
    ) -> str:
        """Edge list 파일명 생성.
        
        네이밍 패턴: company_{tsg}_{time_unit}_{time_value}_{threshold}.parquet
        
        Args:
            tsg_group: TSG 그룹
            time_unit: 시간 단위
            time_value: 시간 값
            threshold: 임계값
            
        Returns:
            파일명 문자열
        """
        return f"company_{tsg_group}_{time_unit}_{time_value}_{threshold}.parquet"
    
    def build_all(
        self,
        df: pd.DataFrame,
        save_to_disk: bool = True,
        include_work_items: bool = False,
    ) -> Dict[str, Tuple[pd.DataFrame, NetworkBuildStats]]:
        """모든 조합에 대한 Edge list 생성.
        
        TSG 그룹 × 시간 단위 × 시간 값 × threshold 전체 조합에 대해
        Edge list를 생성하고 Parquet 형식으로 저장한다.
        
        Args:
            df: 전처리된 DataFrame
            save_to_disk: 디스크 저장 여부 (기본: True)
            include_work_items: Edge별 Work Item 목록 포함 여부
            
        Returns:
            Dict[파일명, (Edge DataFrame, 통계)]
            
        Example:
            >>> results = builder.build_all(preprocessed_df)
            >>> print(f"생성된 네트워크 수: {len(results)}")
        """
        # 입력 검증 및 정규화
        self._validate_input(df)
        working_df = self._normalize_columns(df)
        
        results: Dict[str, Tuple[pd.DataFrame, NetworkBuildStats]] = {}
        total_combinations = 0
        successful = 0
        
        logger.info_with_details(
            f"전체 Edge list 생성 시작",
            stage="company_network",
            details={
                "tsg_groups": self.config.tsg_groups,
                "time_units": self.config.time_units,
                "thresholds": self.config.thresholds,
                "total_records": len(working_df),
            },
        )
        
        for tsg_group in self.config.tsg_groups:
            # TSG 필터링
            tsg_df = self._filter_by_tsg(working_df, tsg_group)
            
            if len(tsg_df) == 0:
                logger.warning_with_details(
                    f"TSG '{tsg_group}'에 데이터 없음, 스킵",
                    stage="company_network",
                )
                continue
            
            for time_unit in self.config.time_units:
                # 해당 시간 단위의 고유 값 목록
                time_values = self._get_time_values(tsg_df, time_unit)
                
                if not time_values:
                    logger.warning_with_details(
                        f"TSG '{tsg_group}', time_unit '{time_unit}'에 "
                        f"유효한 시간 값 없음, 스킵",
                        stage="company_network",
                    )
                    continue
                
                for time_value in time_values:
                    for threshold in self.config.thresholds:
                        total_combinations += 1
                        
                        try:
                            # Edge 생성
                            edge_df, stats = self.build_edges(
                                df=working_df,
                                tsg_group=tsg_group,
                                time_unit=time_unit,
                                time_value=time_value,
                                threshold=threshold,
                                include_work_items=include_work_items,
                            )
                            
                            # 파일명 생성
                            filename = self._generate_filename(
                                tsg_group, time_unit, time_value, threshold
                            )
                            
                            # 디스크 저장 (요구사항 8.6)
                            if save_to_disk and len(edge_df) > 0:
                                filepath = self.output_dir / filename
                                edge_df.to_parquet(filepath, index=False)
                                logger.debug_with_details(
                                    f"Edge list 저장: {filename}",
                                    stage="company_network",
                                    details={
                                        "filepath": str(filepath),
                                        "edges": len(edge_df),
                                    },
                                )
                            
                            results[filename] = (edge_df, stats)
                            successful += 1
                            
                        except Exception as e:
                            logger.error_with_details(
                                f"Edge 생성 실패: {tsg_group}/{time_unit}/{time_value}/{threshold}",
                                stage="company_network",
                                details={
                                    "error": str(e),
                                    "tsg_group": tsg_group,
                                    "time_unit": time_unit,
                                    "time_value": time_value,
                                    "threshold": threshold,
                                },
                            )
        
        logger.info_with_details(
            f"전체 Edge list 생성 완료: {successful}/{total_combinations} 성공",
            stage="company_network",
            details={
                "total_combinations": total_combinations,
                "successful": successful,
                "output_dir": str(self.output_dir),
            },
        )
        
        return results
    
    def load_edges(
        self,
        tsg_group: str,
        time_unit: str,
        time_value: Union[int, str],
        threshold: int,
    ) -> Optional[pd.DataFrame]:
        """저장된 Edge list 로드.
        
        Args:
            tsg_group: TSG 그룹
            time_unit: 시간 단위
            time_value: 시간 값
            threshold: 임계값
            
        Returns:
            Edge DataFrame 또는 None (파일 없는 경우)
        """
        filename = self._generate_filename(tsg_group, time_unit, time_value, threshold)
        filepath = self.output_dir / filename
        
        if not filepath.exists():
            logger.warning_with_details(
                f"Edge list 파일 없음: {filename}",
                stage="company_network",
            )
            return None
        
        return pd.read_parquet(filepath)
    
    @classmethod
    def from_config_file(cls, config_path: Optional[Path] = None) -> "CompanyNetworkBuilder":
        """설정 파일로부터 CompanyNetworkBuilder 생성.
        
        Args:
            config_path: network.yaml 파일 경로. None이면 기본 경로 사용.
            
        Returns:
            CompanyNetworkBuilder 인스턴스
        """
        from src.utils.config_loader import load_config
        config = load_config("network")
        return cls(config=config)
