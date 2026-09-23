"""
Parser Module (Stage 1.5)

TDoc List xlsx 파일을 표준화된 DataFrame으로 파싱하는 모듈.

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6
"""

from .xlsx_parser import (
    ParseStats,
    TDocParser,
    load_parsed_tdocs,
    save_parsed_tdocs,
)

__all__ = [
    "TDocParser",
    "ParseStats",
    "save_parsed_tdocs",
    "load_parsed_tdocs",
]
