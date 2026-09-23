"""
Title Filter Module (Stage 2)

Title 기반으로 분석 대상 외 기고서를 필터링하는 모듈.

요구사항:
- 3.1: Title 컬럼을 분석하여 분석 대상에서 제외할 기고서 유형의 패턴을 식별
- 3.2: config의 title_exclude_patterns 설정에 정의된 패턴과 일치하는 기고서 제외
- 3.3: 패턴 매칭 시 대소문자를 무시 (case-insensitive)
- 3.4: 제외된 기고서 수와 제외 사유별 통계를 로그에 기록

제외 대상 패턴 (12개 LS + CR pack = 13개):
- LS on, LS to, LS Reply, Reply LS, LS in relation to, LS for, LS regarding,
  LS response, LS out, LS answer, LS about, LS-Replay, CR pack
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import pandas as pd

from src.utils.logger import get_logger

# 모듈 로거
logger = get_logger("preprocessor", default_stage="title_filter")


@dataclass
class FilterStats:
    """필터링 통계.
    
    Attributes:
        total_before: 필터링 전 전체 레코드 수
        total_after: 필터링 후 전체 레코드 수
        excluded_count: 제외된 레코드 수
        pattern_counts: 패턴별 제외 건수 (패턴 → 제외 건수)
    """
    total_before: int
    total_after: int
    excluded_count: int
    pattern_counts: Dict[str, int] = field(default_factory=dict)
    
    @property
    def exclusion_rate(self) -> float:
        """제외 비율 (%)."""
        if self.total_before == 0:
            return 0.0
        return (self.excluded_count / self.total_before) * 100
    
    def to_dict(self) -> Dict:
        """딕셔너리로 변환."""
        return {
            "total_before": self.total_before,
            "total_after": self.total_after,
            "excluded_count": self.excluded_count,
            "exclusion_rate": round(self.exclusion_rate, 2),
            "pattern_counts": self.pattern_counts,
        }


class TitleFilter:
    """Title 기반으로 분석 대상 외 기고서를 필터링.
    
    Liaison Statement(LS) 및 CR pack 등 네트워크 분석 대상이 아닌
    기고서를 Title 패턴 기반으로 제외한다.
    
    Attributes:
        exclude_patterns: 제외할 패턴 리스트
        _compiled_patterns: 컴파일된 정규식 패턴 딕셔너리 (원본 패턴 → 컴파일된 패턴)
    
    Example:
        >>> filter = TitleFilter(["LS on", "LS to", "CR pack"])
        >>> filtered_df, stats = filter.filter(df)
        >>> print(f"제외된 레코드: {stats.excluded_count}")
    """
    
    def __init__(self, exclude_patterns: List[str]) -> None:
        """
        Args:
            exclude_patterns: 제외할 패턴 리스트 (case-insensitive matching)
        
        Raises:
            ValueError: 패턴 리스트가 비어있는 경우
        """
        if not exclude_patterns:
            raise ValueError("exclude_patterns는 비어있을 수 없습니다.")
        
        self.exclude_patterns = exclude_patterns
        self._compiled_patterns: Dict[str, re.Pattern] = {}
        
        # 패턴 컴파일 (case-insensitive)
        for pattern in exclude_patterns:
            try:
                # 정규식 특수문자 이스케이프 후 컴파일
                escaped_pattern = re.escape(pattern)
                self._compiled_patterns[pattern] = re.compile(
                    escaped_pattern, re.IGNORECASE
                )
            except re.error as e:
                logger.warning_with_details(
                    f"패턴 컴파일 실패: {pattern}",
                    stage="title_filter",
                    details={"pattern": pattern, "error": str(e)},
                )
        
        logger.info_with_details(
            f"TitleFilter 초기화 완료: {len(self._compiled_patterns)}개 패턴 로드",
            stage="title_filter",
            details={"patterns": exclude_patterns},
        )
    
    def _match_pattern(self, title: str, pattern: str) -> bool:
        """단일 Title에 대해 패턴 매칭 수행.
        
        Args:
            title: Title 문자열
            pattern: 원본 패턴 문자열
            
        Returns:
            패턴이 매칭되면 True, 아니면 False
        """
        if pd.isna(title) or not isinstance(title, str):
            return False
        
        compiled = self._compiled_patterns.get(pattern)
        if compiled is None:
            return False
        
        return compiled.search(title) is not None
    
    def _find_matching_patterns(self, title: str) -> List[str]:
        """Title에 매칭되는 모든 패턴 반환.
        
        Args:
            title: Title 문자열
            
        Returns:
            매칭된 패턴 리스트
        """
        if pd.isna(title) or not isinstance(title, str):
            return []
        
        matching = []
        for pattern, compiled in self._compiled_patterns.items():
            if compiled.search(title) is not None:
                matching.append(pattern)
        
        return matching
    
    def filter(
        self, 
        df: pd.DataFrame, 
        title_column: str = "Title"
    ) -> Tuple[pd.DataFrame, FilterStats]:
        """Title 필터링 수행.
        
        DataFrame의 Title 컬럼을 검사하여 제외 패턴과 매칭되는
        행을 제거한다. 대소문자를 무시하고 매칭한다.
        
        Args:
            df: 입력 DataFrame (Title 컬럼 필수)
            title_column: Title 컬럼명 (기본: "Title")
            
        Returns:
            (필터링된 DataFrame, 필터링 통계)
            
        Raises:
            ValueError: Title 컬럼이 존재하지 않는 경우
        """
        if title_column not in df.columns:
            raise ValueError(f"'{title_column}' 컬럼이 DataFrame에 존재하지 않습니다.")
        
        total_before = len(df)
        
        # 빈 DataFrame 처리
        if total_before == 0:
            stats = FilterStats(
                total_before=0,
                total_after=0,
                excluded_count=0,
                pattern_counts={pattern: 0 for pattern in self._compiled_patterns},
            )
            logger.info_with_details(
                "빈 DataFrame - 필터링 스킵",
                stage="title_filter",
                details=stats.to_dict(),
            )
            return df.copy(), stats
        
        # 패턴별 제외 건수 계산
        pattern_counts: Dict[str, int] = {}
        exclude_mask = pd.Series([False] * len(df), index=df.index)
        
        for pattern, compiled in self._compiled_patterns.items():
            # 각 패턴에 매칭되는 행 찾기
            pattern_mask = df[title_column].fillna("").str.contains(
                compiled, regex=True
            )
            
            # 이 패턴에 의해 새로 제외되는 행 수 (이미 제외된 행은 제외)
            newly_excluded = pattern_mask & ~exclude_mask
            pattern_counts[pattern] = newly_excluded.sum()
            
            # 제외 마스크 업데이트
            exclude_mask = exclude_mask | pattern_mask
        
        # 필터링 수행 (매칭되지 않은 행만 유지)
        filtered_df = df[~exclude_mask].copy()
        
        total_after = len(filtered_df)
        excluded_count = total_before - total_after
        
        # 통계 생성
        stats = FilterStats(
            total_before=total_before,
            total_after=total_after,
            excluded_count=excluded_count,
            pattern_counts=pattern_counts,
        )
        
        # 로그 기록 (요구사항 3.4)
        logger.info_with_details(
            f"Title 필터링 완료: {total_before:,}행 → {total_after:,}행 "
            f"({excluded_count:,}행 제외, {stats.exclusion_rate:.2f}%)",
            stage="title_filter",
            details=stats.to_dict(),
        )
        
        # 패턴별 상세 통계 로그
        for pattern, count in sorted(
            pattern_counts.items(), key=lambda x: x[1], reverse=True
        ):
            if count > 0:
                logger.debug_with_details(
                    f"패턴 '{pattern}': {count:,}건 제외",
                    stage="title_filter",
                    details={"pattern": pattern, "excluded_count": count},
                )
        
        return filtered_df, stats
    
    def get_excluded_records(
        self,
        df: pd.DataFrame,
        title_column: str = "Title",
    ) -> pd.DataFrame:
        """제외 대상 레코드만 반환.
        
        디버깅 또는 검증 목적으로 제외되는 레코드를 확인할 때 사용.
        
        Args:
            df: 입력 DataFrame
            title_column: Title 컬럼명
            
        Returns:
            제외 대상 레코드 DataFrame (matching_patterns 컬럼 추가)
        """
        if title_column not in df.columns:
            raise ValueError(f"'{title_column}' 컬럼이 DataFrame에 존재하지 않습니다.")
        
        # 제외 마스크 생성
        exclude_mask = pd.Series([False] * len(df), index=df.index)
        
        for compiled in self._compiled_patterns.values():
            pattern_mask = df[title_column].fillna("").str.contains(
                compiled, regex=True
            )
            exclude_mask = exclude_mask | pattern_mask
        
        # 제외 대상 레코드
        excluded_df = df[exclude_mask].copy()
        
        # 매칭된 패턴 정보 추가
        excluded_df["matching_patterns"] = excluded_df[title_column].apply(
            self._find_matching_patterns
        )
        
        return excluded_df
    
    @classmethod
    def from_config(cls, config: Dict) -> "TitleFilter":
        """설정 딕셔너리로부터 TitleFilter 생성.
        
        Args:
            config: preprocessing.yaml의 설정 딕셔너리
            
        Returns:
            TitleFilter 인스턴스
            
        Raises:
            KeyError: title_exclude_patterns 키가 없는 경우
        """
        if "title_exclude_patterns" not in config:
            raise KeyError("설정에 'title_exclude_patterns' 키가 필요합니다.")
        
        return cls(exclude_patterns=config["title_exclude_patterns"])
