"""
Temporal Enricher Module (Stage 5)

시간 정보(Year, Quarter) 추가 및 날짜 범위 필터링을 수행하는 모듈.

요구사항:
- 6.1: Uploaded 날짜 컬럼으로부터 Year, Quarter 컬럼을 생성
- 6.2: config의 date_range 설정에 정의된 범위를 벗어나는 날짜를 분석 대상에서 제외
- 6.3: 제외된 레코드 수와 제외 사유를 로그에 기록
- 7.3: Stage 2~5 전 단계의 통계를 통합 메타데이터로 기록 (PreprocessingMetadata)

Quarter 계산 규칙:
- Q1: 1-3월
- Q2: 4-6월
- Q3: 7-9월
- Q4: 10-12월

Quarter 포맷: 'YYYYQN' (예: '2023Q1')
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd

from src.utils.logger import get_logger

# 모듈 로거
logger = get_logger("preprocessor", default_stage="temporal_enricher")


@dataclass
class EnrichStats:
    """시간 정보 추가 통계.
    
    TemporalEnricher.enrich() 결과로 반환되는 통계 정보.
    
    Attributes:
        total_before: 처리 전 전체 레코드 수
        total_after: 처리 후 전체 레코드 수
        excluded_by_date_range: 날짜 범위 필터링으로 제외된 레코드 수
        excluded_by_invalid_date: 유효하지 않은 날짜로 제외된 레코드 수
        year_distribution: 연도별 레코드 수 분포 (필터링 후)
        quarter_distribution: 분기별 레코드 수 분포 (필터링 후)
    
    Example:
        >>> stats = EnrichStats(
        ...     total_before=10000,
        ...     total_after=9500,
        ...     excluded_by_date_range=300,
        ...     excluded_by_invalid_date=200,
        ...     year_distribution={2023: 5000, 2024: 4500},
        ...     quarter_distribution={"2023Q1": 1200, "2023Q2": 1300, ...}
        ... )
    """
    total_before: int
    total_after: int
    excluded_by_date_range: int
    excluded_by_invalid_date: int
    year_distribution: Dict[int, int] = field(default_factory=dict)
    quarter_distribution: Dict[str, int] = field(default_factory=dict)
    
    @property
    def total_excluded(self) -> int:
        """총 제외된 레코드 수."""
        return self.excluded_by_date_range + self.excluded_by_invalid_date
    
    @property
    def exclusion_rate(self) -> float:
        """제외 비율 (%)."""
        if self.total_before == 0:
            return 0.0
        return (self.total_excluded / self.total_before) * 100
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환."""
        return {
            "total_before": self.total_before,
            "total_after": self.total_after,
            "total_excluded": self.total_excluded,
            "exclusion_rate": round(self.exclusion_rate, 2),
            "excluded_by_date_range": self.excluded_by_date_range,
            "excluded_by_invalid_date": self.excluded_by_invalid_date,
            "year_distribution": self.year_distribution,
            "quarter_distribution": self.quarter_distribution,
        }


@dataclass
class PreprocessingMetadata:
    """전처리 전체 단계 메타데이터 (요구사항 7.3).
    
    Stage 2~5 전 단계의 통계를 통합하여 단계별 적용 규칙과 
    영향도(제거/변환 레코드 수)를 기록한다.
    
    Attributes:
        pipeline_version: 파이프라인 버전
        processed_at: 처리 일시 (ISO 8601)
        stages: 각 단계별 통계 딕셔너리 리스트
    
    Example:
        >>> metadata = PreprocessingMetadata(
        ...     pipeline_version="1.0.0",
        ...     stages=[
        ...         {"stage": "title_filter", "total_before": 10000, ...},
        ...         {"stage": "membership_extraction", "total_before": 8000, ...},
        ...         {"stage": "wi_explode", "total_before": 7500, ...},
        ...         {"stage": "temporal_enrich", "total_before": 15000, ...}
        ...     ]
        ... )
    """
    pipeline_version: str = "1.0.0"
    processed_at: str = field(
        default_factory=lambda: datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    stages: List[Dict[str, Any]] = field(default_factory=list)
    
    def add_stage(
        self, 
        stage_name: str, 
        stats: Union["EnrichStats", Dict[str, Any]],
        rules_applied: Optional[List[str]] = None
    ) -> None:
        """단계별 통계 추가.
        
        Args:
            stage_name: 단계 이름 (예: "title_filter", "temporal_enrich")
            stats: 해당 단계의 통계 (EnrichStats 또는 딕셔너리)
            rules_applied: 적용된 규칙 목록 (선택사항)
        """
        stage_data = {
            "stage": stage_name,
            "processed_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        
        # 통계 데이터 병합
        if isinstance(stats, dict):
            stage_data.update(stats)
        elif hasattr(stats, "to_dict"):
            stage_data.update(stats.to_dict())
        
        # 적용된 규칙 추가
        if rules_applied:
            stage_data["rules_applied"] = rules_applied
        
        self.stages.append(stage_data)
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환."""
        return {
            "pipeline_version": self.pipeline_version,
            "processed_at": self.processed_at,
            "stages": self.stages,
        }
    
    def get_summary(self) -> Dict[str, Any]:
        """전체 요약 정보 반환.
        
        Returns:
            요약 딕셔너리 (최초 레코드 수, 최종 레코드 수, 총 제외 수 등)
        """
        if not self.stages:
            return {"initial_records": 0, "final_records": 0, "total_excluded": 0}
        
        initial = self.stages[0].get("total_before", 0)
        final = self.stages[-1].get("total_after", 0)
        
        return {
            "initial_records": initial,
            "final_records": final,
            "total_excluded": initial - final,
            "exclusion_rate": round((initial - final) / initial * 100, 2) if initial > 0 else 0,
            "stages_count": len(self.stages),
        }


class TemporalEnricher:
    """시간 정보(Year, Quarter) 추가 및 필터링.
    
    Uploaded 날짜 컬럼으로부터 Year, Quarter 컬럼을 생성하고,
    설정된 날짜 범위를 벗어나는 레코드를 필터링한다.
    
    Quarter 계산 규칙:
        - Q1: 1-3월 (month 1, 2, 3)
        - Q2: 4-6월 (month 4, 5, 6)
        - Q3: 7-9월 (month 7, 8, 9)
        - Q4: 10-12월 (month 10, 11, 12)
    
    Quarter 포맷: 'YYYYQN' (예: '2023Q1', '2024Q4')
    
    Attributes:
        min_year: 최소 연도 (이전 연도는 제외)
        max_year: 최대 연도 (None이면 제한 없음)
    
    Example:
        >>> enricher = TemporalEnricher(min_year=2015, max_year=None)
        >>> enriched_df, stats = enricher.enrich(df)
        >>> print(f"제외된 레코드: {stats.total_excluded}")
        >>> print(f"연도 분포: {stats.year_distribution}")
    """
    
    # 월 → 분기 매핑 상수
    MONTH_TO_QUARTER = {
        1: 1, 2: 1, 3: 1,     # Q1
        4: 2, 5: 2, 6: 2,     # Q2
        7: 3, 8: 3, 9: 3,     # Q3
        10: 4, 11: 4, 12: 4,  # Q4
    }
    
    def __init__(
        self, 
        min_year: int = 2015, 
        max_year: Optional[int] = None
    ) -> None:
        """TemporalEnricher 초기화.
        
        Args:
            min_year: 최소 연도 (이전 연도는 제외). 기본값: 2015
                - 원본 노트북 분석: 2015년 이전 데이터 2건(1999년 등) 제외
            max_year: 최대 연도 (None이면 제한 없음)
        
        Raises:
            ValueError: min_year가 유효하지 않은 경우
        """
        if min_year < 1900 or min_year > 2100:
            raise ValueError(f"min_year가 유효하지 않습니다: {min_year}")
        
        if max_year is not None and max_year < min_year:
            raise ValueError(f"max_year({max_year})가 min_year({min_year})보다 작습니다.")
        
        self.min_year = min_year
        self.max_year = max_year
        
        logger.info_with_details(
            f"TemporalEnricher 초기화 완료: min_year={min_year}, max_year={max_year}",
            stage="temporal_enricher",
            details={"min_year": min_year, "max_year": max_year},
        )
    
    @staticmethod
    def _get_quarter(month: int) -> int:
        """월로부터 분기 계산.
        
        Args:
            month: 월 (1-12)
            
        Returns:
            분기 번호 (1-4)
            
        Example:
            >>> TemporalEnricher._get_quarter(1)
            1
            >>> TemporalEnricher._get_quarter(7)
            3
        """
        return TemporalEnricher.MONTH_TO_QUARTER.get(month, 0)
    
    @staticmethod
    def _format_quarter(year: int, quarter: int) -> str:
        """연도와 분기를 'YYYYQN' 형식 문자열로 변환.
        
        Args:
            year: 연도 (예: 2023)
            quarter: 분기 번호 (1-4)
            
        Returns:
            'YYYYQN' 형식 문자열 (예: '2023Q1')
        """
        return f"{year}Q{quarter}"
    
    def _convert_to_datetime(
        self, 
        df: pd.DataFrame, 
        date_column: str
    ) -> Tuple[pd.DataFrame, int]:
        """날짜 컬럼을 datetime으로 변환.
        
        Args:
            df: 입력 DataFrame
            date_column: 날짜 컬럼명
            
        Returns:
            (datetime 변환된 DataFrame, 유효하지 않은 날짜로 인한 제외 수)
        """
        result_df = df.copy()
        
        # 이미 datetime인 경우 스킵
        if pd.api.types.is_datetime64_any_dtype(result_df[date_column]):
            # NaT 값 체크
            invalid_count = result_df[date_column].isna().sum()
            return result_df, int(invalid_count)
        
        # datetime으로 변환 시도
        result_df[date_column] = pd.to_datetime(
            result_df[date_column], 
            errors="coerce",  # 변환 실패 시 NaT
            utc=True  # UTC로 파싱
        )
        
        # 타임존 정보 제거 (날짜만 필요)
        if result_df[date_column].dt.tz is not None:
            result_df[date_column] = result_df[date_column].dt.tz_localize(None)
        
        # NaT (변환 실패) 개수
        invalid_count = result_df[date_column].isna().sum()
        
        return result_df, int(invalid_count)
    
    def enrich(
        self, 
        df: pd.DataFrame,
        date_column: str = "Uploaded"
    ) -> Tuple[pd.DataFrame, EnrichStats]:
        """시간 정보 추가 및 범위 필터링.
        
        처리 흐름:
            1. Uploaded 컬럼을 datetime으로 변환
            2. Year 컬럼 추가
            3. Quarter 컬럼 추가 (Q1, Q2, Q3, Q4)
            4. 설정된 날짜 범위 필터링
            5. 통계 로깅
        
        Args:
            df: 입력 DataFrame (Uploaded 컬럼 필수)
            date_column: 날짜 컬럼명 (기본: "Uploaded")
            
        Returns:
            Tuple[시간 정보 추가된 DataFrame, 처리 통계]
            
        Raises:
            ValueError: 날짜 컬럼이 존재하지 않는 경우
            
        Example:
            >>> enricher = TemporalEnricher(min_year=2015)
            >>> enriched_df, stats = enricher.enrich(df)
            >>> print(enriched_df[['Year', 'Quarter']].head())
               Year  Quarter
            0  2023  2023Q1
            1  2023  2023Q2
            2  2024  2024Q1
        """
        # 입력 검증
        if date_column not in df.columns:
            raise ValueError(f"'{date_column}' 컬럼이 DataFrame에 존재하지 않습니다.")
        
        total_before = len(df)
        
        # 빈 DataFrame 처리
        if total_before == 0:
            stats = EnrichStats(
                total_before=0,
                total_after=0,
                excluded_by_date_range=0,
                excluded_by_invalid_date=0,
                year_distribution={},
                quarter_distribution={},
            )
            logger.info_with_details(
                "빈 DataFrame - 시간 정보 추가 스킵",
                stage="temporal_enricher",
                details=stats.to_dict(),
            )
            # Year, Quarter 컬럼 추가 (빈 DataFrame이어도 스키마 일관성 유지)
            result_df = df.copy()
            result_df["Year"] = pd.Series(dtype="Int64")
            result_df["Quarter"] = pd.Series(dtype="object")
            return result_df, stats
        
        # 1. datetime 변환
        result_df, excluded_by_invalid = self._convert_to_datetime(df, date_column)
        
        # 2. Year 컬럼 추가
        result_df["Year"] = result_df[date_column].dt.year
        
        # 3. Quarter 컬럼 추가 (YYYYQN 형식)
        result_df["Quarter"] = result_df.apply(
            lambda row: (
                self._format_quarter(
                    int(row["Year"]), 
                    self._get_quarter(row[date_column].month)
                )
                if pd.notna(row[date_column]) and pd.notna(row["Year"])
                else None
            ),
            axis=1,
        )
        
        # 4. 유효하지 않은 날짜 제외 (NaT)
        valid_mask = result_df[date_column].notna()
        result_df = result_df[valid_mask].copy()
        
        # 5. 날짜 범위 필터링
        records_before_range_filter = len(result_df)
        
        # min_year 필터링
        year_mask = result_df["Year"] >= self.min_year
        
        # max_year 필터링 (설정된 경우)
        if self.max_year is not None:
            year_mask = year_mask & (result_df["Year"] <= self.max_year)
        
        result_df = result_df[year_mask].copy()
        excluded_by_date_range = records_before_range_filter - len(result_df)
        
        # 6. Year 컬럼을 Int64로 변환 (nullable integer)
        result_df["Year"] = result_df["Year"].astype("Int64")
        
        total_after = len(result_df)
        
        # 7. 분포 통계 계산
        year_distribution: Dict[int, int] = {}
        quarter_distribution: Dict[str, int] = {}
        
        if total_after > 0:
            # 연도별 분포
            year_counts = result_df["Year"].value_counts().sort_index()
            year_distribution = {int(k): int(v) for k, v in year_counts.items()}
            
            # 분기별 분포
            quarter_counts = result_df["Quarter"].value_counts().sort_index()
            quarter_distribution = {str(k): int(v) for k, v in quarter_counts.items()}
        
        # 통계 생성
        stats = EnrichStats(
            total_before=total_before,
            total_after=total_after,
            excluded_by_date_range=excluded_by_date_range,
            excluded_by_invalid_date=excluded_by_invalid,
            year_distribution=year_distribution,
            quarter_distribution=quarter_distribution,
        )
        
        # 로그 기록 (요구사항 6.3)
        logger.info_with_details(
            f"시간 정보 추가 완료: {total_before:,}행 → {total_after:,}행 "
            f"({stats.total_excluded:,}행 제외, {stats.exclusion_rate:.2f}%)",
            stage="temporal_enricher",
            details=stats.to_dict(),
        )
        
        # 제외 사유별 상세 로그
        if excluded_by_invalid > 0:
            logger.warning_with_details(
                f"유효하지 않은 날짜: {excluded_by_invalid:,}건 제외",
                stage="temporal_enricher",
                details={"reason": "invalid_date", "count": excluded_by_invalid},
            )
        
        if excluded_by_date_range > 0:
            date_range_info = f"<{self.min_year}"
            if self.max_year is not None:
                date_range_info += f" 또는 >{self.max_year}"
            logger.info_with_details(
                f"날짜 범위 외({date_range_info}): {excluded_by_date_range:,}건 제외",
                stage="temporal_enricher",
                details={
                    "reason": "date_range",
                    "count": excluded_by_date_range,
                    "min_year": self.min_year,
                    "max_year": self.max_year,
                },
            )
        
        # 연도별 분포 요약 로그
        if year_distribution:
            min_yr = min(year_distribution.keys())
            max_yr = max(year_distribution.keys())
            logger.info_with_details(
                f"연도 범위: {min_yr}~{max_yr} ({len(year_distribution)}개 연도)",
                stage="temporal_enricher",
                details={"year_range": f"{min_yr}-{max_yr}", "year_count": len(year_distribution)},
            )
        
        return result_df, stats
    
    def get_year_from_date(self, date_value: Any) -> Optional[int]:
        """날짜 값에서 연도 추출.
        
        Args:
            date_value: 날짜 값 (datetime, str, 등)
            
        Returns:
            연도 (정수) 또는 None (변환 실패 시)
        """
        if pd.isna(date_value):
            return None
        
        try:
            if isinstance(date_value, datetime):
                return date_value.year
            
            parsed = pd.to_datetime(date_value, errors="coerce")
            if pd.isna(parsed):
                return None
            
            return parsed.year
        except Exception:
            return None
    
    def get_quarter_from_date(self, date_value: Any) -> Optional[str]:
        """날짜 값에서 분기 문자열 추출.
        
        Args:
            date_value: 날짜 값 (datetime, str, 등)
            
        Returns:
            'YYYYQN' 형식 문자열 또는 None (변환 실패 시)
        """
        if pd.isna(date_value):
            return None
        
        try:
            if isinstance(date_value, datetime):
                year = date_value.year
                quarter = self._get_quarter(date_value.month)
                return self._format_quarter(year, quarter)
            
            parsed = pd.to_datetime(date_value, errors="coerce")
            if pd.isna(parsed):
                return None
            
            year = parsed.year
            quarter = self._get_quarter(parsed.month)
            return self._format_quarter(year, quarter)
        except Exception:
            return None
    
    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "TemporalEnricher":
        """설정 딕셔너리로부터 TemporalEnricher 생성.
        
        Args:
            config: preprocessing.yaml의 설정 딕셔너리
                - date_range:
                    - min_year: int (기본: 2015)
                    - max_year: int 또는 None (기본: None)
        
        Returns:
            TemporalEnricher 인스턴스
            
        Example:
            >>> config = {
            ...     "date_range": {
            ...         "min_year": 2015,
            ...         "max_year": None
            ...     }
            ... }
            >>> enricher = TemporalEnricher.from_config(config)
        """
        date_range = config.get("date_range", {})
        
        min_year = date_range.get("min_year", 2015)
        max_year = date_range.get("max_year")  # None이면 제한 없음
        
        return cls(min_year=min_year, max_year=max_year)


def build_preprocessing_metadata(
    stages_stats: List[Tuple[str, Dict[str, Any]]],
    pipeline_version: str = "1.0.0",
) -> PreprocessingMetadata:
    """전처리 전체 단계 메타데이터 구축 (요구사항 7.3).
    
    Stage 2~5 전 단계의 통계를 통합하여 메타데이터를 생성한다.
    
    Args:
        stages_stats: (단계명, 통계딕셔너리) 튜플 리스트
            예: [("title_filter", {...}), ("membership_extraction", {...}), ...]
        pipeline_version: 파이프라인 버전
        
    Returns:
        PreprocessingMetadata 인스턴스
        
    Example:
        >>> from src.preprocessor.title_filter import FilterStats
        >>> from src.preprocessor.temporal_enricher import EnrichStats, build_preprocessing_metadata
        >>> 
        >>> stages = [
        ...     ("title_filter", filter_stats.to_dict()),
        ...     ("membership_extraction", extraction_stats),
        ...     ("wi_explode", explode_stats),
        ...     ("temporal_enrich", enrich_stats.to_dict()),
        ... ]
        >>> metadata = build_preprocessing_metadata(stages)
        >>> print(metadata.get_summary())
    """
    metadata = PreprocessingMetadata(pipeline_version=pipeline_version)
    
    for stage_name, stats in stages_stats:
        if isinstance(stats, dict):
            metadata.add_stage(stage_name, stats)
        elif hasattr(stats, "to_dict"):
            metadata.add_stage(stage_name, stats.to_dict())
        else:
            # 알 수 없는 형식의 경우 기본 정보만 기록
            metadata.add_stage(stage_name, {"raw_stats": str(stats)})
    
    return metadata
