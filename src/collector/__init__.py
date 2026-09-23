"""
Collector Module (Stage 1)

3GPP FTP 서버에서 TDoc List xlsx 파일을 수집하는 모듈.

Requirements:
- 1.1: FTP 서버에서 TDoc List xlsx 파일을 탐색하고, 로컬에 존재하지 않는 파일 다운로드
- 1.2: 파일명 패턴에서 TSG, WG, MTG 정보 추출
- 1.4: 이미 로컬에 존재하는 파일은 재다운로드하지 않음
- 1.5: 다운로드 실패 시 실패 원인과 파일 경로를 로그에 기록하고 재시도
- 1.6: 최대 재시도 횟수 초과 시 실패 목록에 등록하고 다음 파일 수집 계속
- 1.7: 수집 파일명, 수집 일시, 성공/실패 여부를 이력 로그에 기록
"""

from .ftp_collector import (
    FTPCollector,
    TDocFileInfo,
    DownloadResult,
    CollectionReport,
    collect_tdoc_files,
)

__all__ = [
    "FTPCollector",
    "TDocFileInfo",
    "DownloadResult",
    "CollectionReport",
    "collect_tdoc_files",
]
