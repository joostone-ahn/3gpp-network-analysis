"""
WI Exploder Module (Stage 4)

복수 Work Item을 개별 행으로 분리하고 제외 패턴을 필터링하는 모듈.

요구사항:
- 5.1: Related WIs 컬럼을 분석하여 Work Item 구분자 패턴을 식별
- 5.2: config의 wi_delimiters 설정에 정의된 구분자로 Work Item을 개별 행으로 분리(explode)
- 5.3: config의 wi_exclude_patterns 설정에 정의된 패턴과 일치하는 Work Item을 분석 대상에서 제외
- 5.4: 분리 전후 레코드 수 변화와 제외된 Work Item 통계를 로그에 기록

제외 대상 패턴 (부분 문자열 매칭, case-insensitive):
- TEI, DUMMY
- 원본 노트북: str.contains(r'TEI|DUMMY', flags=re.IGNORECASE) 사용
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import pandas as pd

from src.utils.logger import get_logger

# 모듈 로거
logger = get_logger("preprocessor", default_stage="wi_exploder")


@dataclass
class ExplodeStats:
    """Work Item 분리 통계.
    
    Attributes:
        total_before: 분리 전 전체 레코드 수
        total_after: 분리 후 전체 레코드 수 (필터링 포함)
        total_exploded: explode 직후 레코드 수 (필터링 전)
        total_excluded: 제외된 Work Item 레코드 수
        pattern_counts: 패턴별 제외 건수 (TEI, DUMMY 등)
        wi_counts_before: 분리 전 고유 Work Item 수
        wi_counts_after: 분리 및 필터링 후 고유 Work Item 수
    """
    total_before: int
    total_after: int
    total_exploded: int
    total_excluded: int
    pattern_counts: Dict[str, int] = field(default_factory=dict)
    wi_counts_before: int = 0
    wi_counts_after: int = 0
    
    @property
    def expansion_ratio(self) -> float:
        """분리 확장 비율 (explode 후 / explode 전)."""
        if self.total_before == 0:
            return 0.0
        return self.total_exploded / self.total_before
    
    @property
    def exclusion_rate(self) -> float:
        """제외 비율 (explode 후 기준 %)."""
        if self.total_exploded == 0:
            return 0.0
        return (self.total_excluded / self.total_exploded) * 100
    
    def to_dict(self) -> Dict:
        """딕셔너리로 변환."""
        return {
            "total_before": self.total_before,
            "total_after": self.total_after,
            "total_exploded": self.total_exploded,
            "total_excluded": self.total_excluded,
            "expansion_ratio": round(self.expansion_ratio, 2),
            "exclusion_rate": round(self.exclusion_rate, 2),
            "pattern_counts": self.pattern_counts,
            "wi_counts_before": self.wi_counts_before,
            "wi_counts_after": self.wi_counts_after,
        }


class WIExploder:
    """복수 Work Item을 개별 행으로 분리.
    
    Related WIs 컬럼의 값을 구분자로 분리하고,
    TEI/DUMMY 등 제외 패턴에 해당하는 WI를 필터링한다.
    
    Attributes:
        delimiters: WI 구분자 목록 (예: [","])
        exclude_patterns: 제외할 패턴 목록 (예: ["TEI", "DUMMY"])
        _combined_exclude_pattern: 패턴들을 OR로 결합한 컴파일된 정규식
    
    Example:
        >>> exploder = WIExploder(
        ...     delimiters=[","],
        ...     exclude_patterns=["TEI", "DUMMY"]
        ... )
        >>> exploded_df, stats = exploder.explode(df)
        >>> print(f"분리 후 레코드: {stats.total_after}")
    """
    
    def __init__(
        self, 
        delimiters: List[str], 
        exclude_patterns: List[str]
    ) -> None:
        """
        Args:
            delimiters: WI 구분자 목록 (예: [","])
            exclude_patterns: 제외할 WI 패턴 목록 (예: ["TEI", "DUMMY"])
                - case-insensitive substring 매칭
        
        Raises:
            ValueError: delimiters가 비어있는 경우
        """
        if not delimiters:
            raise ValueError("delimiters는 비어있을 수 없습니다.")
        
        self.delimiters = delimiters
        self.exclude_patterns = exclude_patterns or []
        
        # 구분자를 정규식 패턴으로 결합 (여러 구분자 지원)
        # 예: [",", ";"] -> ",|;"
        escaped_delimiters = [re.escape(d) for d in delimiters]
        self._delimiter_pattern = "|".join(escaped_delimiters)
        
        # 제외 패턴을 OR로 결합하여 컴파일 (case-insensitive)
        # 원본 노트북 방식: str.contains(r'TEI|DUMMY', flags=re.IGNORECASE)
        self._combined_exclude_pattern: Optional[re.Pattern] = None
        if self.exclude_patterns:
            # 각 패턴을 이스케이프하여 OR로 결합
            escaped_patterns = [re.escape(p) for p in self.exclude_patterns]
            combined = "|".join(escaped_patterns)
            self._combined_exclude_pattern = re.compile(combined, re.IGNORECASE)
        
        logger.info_with_details(
            f"WIExploder 초기화 완료: 구분자 {len(delimiters)}개, "
            f"제외 패턴 {len(self.exclude_patterns)}개",
            stage="wi_exploder",
            details={
                "delimiters": delimiters,
                "exclude_patterns": self.exclude_patterns,
            },
        )
    
    def _split_work_items(self, wi_string: str) -> List[str]:
        """Work Item 문자열을 구분자로 분리.
        
        Args:
            wi_string: Work Item 문자열 (예: "WI-123, WI-456")
            
        Returns:
            분리된 Work Item 리스트 (예: ["WI-123", "WI-456"])
        """
        if pd.isna(wi_string) or not isinstance(wi_string, str):
            return [wi_string] if pd.notna(wi_string) else []
        
        if not wi_string.strip():
            return []
        
        # 구분자로 분리 후 각 항목 strip
        parts = re.split(self._delimiter_pattern, wi_string)
        return [part.strip() for part in parts if part.strip()]
    
    def _matches_exclude_pattern(self, wi_value: str) -> Tuple[bool, List[str]]:
        """Work Item이 제외 패턴에 매칭되는지 확인.
        
        Args:
            wi_value: Work Item 값
            
        Returns:
            (매칭 여부, 매칭된 패턴 리스트)
        """
        if pd.isna(wi_value) or not isinstance(wi_value, str):
            return False, []
        
        if self._combined_exclude_pattern is None:
            return False, []
        
        # 매칭되는 패턴 찾기
        matched_patterns = []
        for pattern in self.exclude_patterns:
            # 각 패턴에 대해 개별적으로 검사 (통계를 위해)
            if re.search(re.escape(pattern), wi_value, re.IGNORECASE):
                matched_patterns.append(pattern)
        
        return len(matched_patterns) > 0, matched_patterns
    
    def explode(
        self, 
        df: pd.DataFrame, 
        wi_column: str = "Related WIs"
    ) -> Tuple[pd.DataFrame, ExplodeStats]:
        """Work Item 분리 및 필터링.
        
        1. Related WIs 컬럼을 구분자로 분리
        2. 개별 행으로 분리 (explode)
        3. TEI/DUMMY 패턴 제외 (case-insensitive substring)
        4. 통계 로깅
        
        Args:
            df: 입력 DataFrame (Related WIs 컬럼 필수)
            wi_column: Work Item 컬럼명 (기본: "Related WIs")
        
        Returns:
            (분리/필터링된 DataFrame, 분리 통계)
            
        Raises:
            ValueError: wi_column이 존재하지 않는 경우
        """
        if wi_column not in df.columns:
            raise ValueError(f"'{wi_column}' 컬럼이 DataFrame에 존재하지 않습니다.")
        
        total_before = len(df)
        
        # 빈 DataFrame 처리
        if total_before == 0:
            stats = ExplodeStats(
                total_before=0,
                total_after=0,
                total_exploded=0,
                total_excluded=0,
                pattern_counts={p: 0 for p in self.exclude_patterns},
                wi_counts_before=0,
                wi_counts_after=0,
            )
            logger.info_with_details(
                "빈 DataFrame - 분리 스킵",
                stage="wi_exploder",
                details=stats.to_dict(),
            )
            return df.copy(), stats
        
        # 분리 전 고유 Work Item 수 계산
        # NaN이 아닌 값들만 대상으로 고유 값 계산
        non_null_wis = df[wi_column].dropna()
        wi_counts_before = non_null_wis.nunique()
        
        # Step 1: Work Item 문자열을 리스트로 분리
        df_work = df.copy()
        df_work["_wi_list"] = df_work[wi_column].apply(self._split_work_items)
        
        # Step 2: explode로 개별 행 분리
        df_exploded = df_work.explode("_wi_list", ignore_index=True)
        
        # explode된 WI 값을 원래 컬럼에 덮어쓰기
        df_exploded[wi_column] = df_exploded["_wi_list"]
        df_exploded = df_exploded.drop(columns=["_wi_list"])
        
        # 빈 문자열 또는 NaN 행 제거 (WI가 없는 레코드)
        df_exploded = df_exploded[
            df_exploded[wi_column].notna() & 
            (df_exploded[wi_column].astype(str).str.strip() != "")
        ].copy()
        
        total_exploded = len(df_exploded)
        
        # Step 3: 제외 패턴 필터링
        pattern_counts: Dict[str, int] = {p: 0 for p in self.exclude_patterns}
        
        if self._combined_exclude_pattern is not None and total_exploded > 0:
            # 제외 대상 마스크 생성 (case-insensitive substring matching)
            exclude_mask = df_exploded[wi_column].fillna("").str.contains(
                self._combined_exclude_pattern, regex=True, na=False
            )
            
            # 패턴별 제외 건수 계산
            for pattern in self.exclude_patterns:
                pattern_mask = df_exploded[wi_column].fillna("").str.contains(
                    pattern, case=False, regex=False, na=False
                )
                pattern_counts[pattern] = pattern_mask.sum()
            
            # 필터링 수행 (매칭되지 않은 행만 유지)
            df_filtered = df_exploded[~exclude_mask].copy()
        else:
            df_filtered = df_exploded.copy()
            exclude_mask = pd.Series([False] * len(df_exploded))
        
        total_excluded = exclude_mask.sum() if len(exclude_mask) > 0 else 0
        total_after = len(df_filtered)
        
        # 분리 후 고유 Work Item 수 계산
        wi_counts_after = df_filtered[wi_column].nunique() if total_after > 0 else 0
        
        # 통계 생성
        stats = ExplodeStats(
            total_before=total_before,
            total_after=total_after,
            total_exploded=total_exploded,
            total_excluded=total_excluded,
            pattern_counts=pattern_counts,
            wi_counts_before=wi_counts_before,
            wi_counts_after=wi_counts_after,
        )
        
        # 로그 기록 (요구사항 5.4)
        logger.info_with_details(
            f"WI Explode 완료: {total_before:,}행 → {total_exploded:,}행(분리) → "
            f"{total_after:,}행(필터링 후), 확장비율 {stats.expansion_ratio:.2f}x",
            stage="wi_exploder",
            details=stats.to_dict(),
        )
        
        # 패턴별 상세 통계 로그
        for pattern, count in sorted(
            pattern_counts.items(), key=lambda x: x[1], reverse=True
        ):
            if count > 0:
                logger.debug_with_details(
                    f"제외 패턴 '{pattern}': {count:,}건 제외",
                    stage="wi_exploder",
                    details={"pattern": pattern, "excluded_count": count},
                )
        
        return df_filtered, stats
    
    def get_excluded_records(
        self,
        df: pd.DataFrame,
        wi_column: str = "Related WIs",
    ) -> pd.DataFrame:
        """제외 대상 레코드만 반환.
        
        디버깅 또는 검증 목적으로 제외되는 레코드를 확인할 때 사용.
        explode 후 제외 패턴에 매칭되는 레코드를 반환한다.
        
        Args:
            df: 입력 DataFrame
            wi_column: Work Item 컬럼명
            
        Returns:
            제외 대상 레코드 DataFrame (matching_patterns 컬럼 추가)
        """
        if wi_column not in df.columns:
            raise ValueError(f"'{wi_column}' 컬럼이 DataFrame에 존재하지 않습니다.")
        
        if self._combined_exclude_pattern is None:
            return pd.DataFrame()
        
        # explode 수행
        df_work = df.copy()
        df_work["_wi_list"] = df_work[wi_column].apply(self._split_work_items)
        df_exploded = df_work.explode("_wi_list", ignore_index=True)
        df_exploded[wi_column] = df_exploded["_wi_list"]
        df_exploded = df_exploded.drop(columns=["_wi_list"])
        
        # 빈 행 제거
        df_exploded = df_exploded[
            df_exploded[wi_column].notna() & 
            (df_exploded[wi_column].astype(str).str.strip() != "")
        ].copy()
        
        # 제외 마스크 생성
        exclude_mask = df_exploded[wi_column].fillna("").str.contains(
            self._combined_exclude_pattern, regex=True, na=False
        )
        
        # 제외 대상 레코드
        excluded_df = df_exploded[exclude_mask].copy()
        
        # 매칭된 패턴 정보 추가
        def find_matching_patterns(wi_value):
            if pd.isna(wi_value) or not isinstance(wi_value, str):
                return []
            matched = []
            for pattern in self.exclude_patterns:
                if re.search(re.escape(pattern), wi_value, re.IGNORECASE):
                    matched.append(pattern)
            return matched
        
        excluded_df["matching_patterns"] = excluded_df[wi_column].apply(
            find_matching_patterns
        )
        
        return excluded_df
    
    @classmethod
    def from_config(cls, config: Dict) -> "WIExploder":
        """설정 딕셔너리로부터 WIExploder 생성.
        
        Args:
            config: preprocessing.yaml의 설정 딕셔너리
            
        Returns:
            WIExploder 인스턴스
            
        Raises:
            KeyError: wi_delimiters 키가 없는 경우
        """
        if "wi_delimiters" not in config:
            raise KeyError("설정에 'wi_delimiters' 키가 필요합니다.")
        
        delimiters = config["wi_delimiters"]
        exclude_patterns = config.get("wi_exclude_patterns", [])
        
        return cls(
            delimiters=delimiters,
            exclude_patterns=exclude_patterns,
        )
