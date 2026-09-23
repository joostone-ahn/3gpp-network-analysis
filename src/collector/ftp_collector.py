"""
FTP Collector Module

3GPP FTP 서버에서 TDoc List xlsx 파일을 수집하는 모듈.

Requirements:
- 1.1: FTP 서버에서 TDoc List xlsx 파일을 탐색하고, 로컬에 존재하지 않는 파일 다운로드
- 1.2: 파일명 패턴에서 TSG, WG, MTG 정보 추출
- 1.4: 이미 로컬에 존재하는 파일은 재다운로드하지 않음
- 1.5: 다운로드 실패 시 실패 원인과 파일 경로를 로그에 기록하고 재시도
- 1.6: 최대 재시도 횟수 초과 시 실패 목록에 등록하고 다음 파일 수집 계속
- 1.7: 수집 파일명, 수집 일시, 성공/실패 여부를 이력 로그에 기록
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from ftplib import FTP, error_perm, error_temp
from pathlib import Path
from typing import List, Optional

from src.utils.config_loader import CollectorConfig, PROJECT_ROOT
from src.utils.logger import get_logger, create_collection_history_logger

# 로거 초기화
logger = get_logger("collector", default_stage="collect")


# =============================================================================
# Dataclasses
# =============================================================================


@dataclass
class TDocFileInfo:
    """TDoc List 파일 정보.
    
    Attributes:
        tsg: TSG 그룹명 (RAN, SA, CT)
        wg: Working Group (TSG, WG1, WG2, ..., WG6)
        mtg: 회차 번호
        filename: 원본 파일명 (예: TDoc_List_Meeting_RAN#100.xlsx)
        ftp_path: FTP 상의 전체 경로
    """
    tsg: str
    wg: str
    mtg: int
    filename: str
    ftp_path: str
    
    @property
    def local_subdir(self) -> str:
        """로컬 저장 하위 디렉토리 (예: RAN/WG1 또는 RAN/TSG)."""
        if self.wg == "TSG":
            return self.tsg
        return f"{self.tsg}/{self.wg}"
    
    def __repr__(self) -> str:
        return f"TDocFileInfo(tsg={self.tsg}, wg={self.wg}, mtg={self.mtg}, filename={self.filename})"


@dataclass
class DownloadResult:
    """단일 파일 다운로드 결과.
    
    Attributes:
        success: 다운로드 성공 여부
        file_info: 다운로드 대상 파일 정보
        local_path: 다운로드된 로컬 파일 경로 (성공 시)
        error_message: 실패 시 에러 메시지
        error_type: 실패 시 에러 타입
        retry_count: 재시도 횟수
        skipped: 로컬에 이미 존재하여 스킵된 경우 True
    """
    success: bool
    file_info: TDocFileInfo
    local_path: Optional[Path] = None
    error_message: Optional[str] = None
    error_type: Optional[str] = None
    retry_count: int = 0
    skipped: bool = False


@dataclass
class CollectionReport:
    """전체 수집 프로세스 결과 보고서.
    
    Attributes:
        total_files: 탐색된 총 파일 수
        downloaded: 성공적으로 다운로드된 파일 수
        skipped: 로컬에 이미 존재하여 스킵된 파일 수
        failed: 다운로드 실패한 파일 수
        failed_files: 실패한 파일 목록 (DownloadResult)
        started_at: 수집 시작 시각
        finished_at: 수집 완료 시각
    """
    total_files: int = 0
    downloaded: int = 0
    skipped: int = 0
    failed: int = 0
    failed_files: List[DownloadResult] = field(default_factory=list)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    
    @property
    def duration_seconds(self) -> Optional[float]:
        """수집 소요 시간 (초)."""
        if self.started_at and self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None
    
    def __repr__(self) -> str:
        return (
            f"CollectionReport(total={self.total_files}, downloaded={self.downloaded}, "
            f"skipped={self.skipped}, failed={self.failed})"
        )


# =============================================================================
# FTPCollector 클래스
# =============================================================================


class FTPCollector:
    """3GPP FTP 서버에서 TDoc List 파일을 수집하는 클래스.
    
    collector.yaml 설정에 따라 FTP 서버에서 TDoc List xlsx 파일을 탐색하고,
    로컬에 존재하지 않는 파일을 다운로드한다.
    
    Usage:
        >>> from src.utils.config_loader import load_config
        >>> config = load_config("collector")
        >>> collector = FTPCollector(config)
        >>> report = collector.collect_all()
        >>> print(f"Downloaded: {report.downloaded}, Failed: {report.failed}")
    """
    
    # 파일명 패턴: TDoc_List_Meeting_{TSG}#{MTG}.xlsx 또는 #{MTG}-e.xlsx (e-meeting)
    # MTG 추출: #(\d+) 정규식으로 숫자만 추출
    FILENAME_PATTERN = re.compile(r"TDoc_List.*#(\d+)", re.IGNORECASE)
    
    def __init__(
        self,
        config: CollectorConfig,
        data_dir: Optional[Path] = None,
    ):
        """FTPCollector 초기화.
        
        Args:
            config: collector.yaml에서 로드한 CollectorConfig 객체
            data_dir: 데이터 저장 루트 디렉토리. None이면 PROJECT_ROOT/data 사용.
        """
        self.config = config
        self.data_dir = data_dir or PROJECT_ROOT / "data"
        self.raw_dir = self.data_dir / "raw"
        self._ftp: Optional[FTP] = None
        self._history_logger = create_collection_history_logger()
    
    # -------------------------------------------------------------------------
    # FTP 연결 관리
    # -------------------------------------------------------------------------
    
    def _connect(self) -> FTP:
        """FTP 서버에 연결.
        
        Returns:
            FTP 연결 객체
            
        Raises:
            Exception: 연결 실패 시
        """
        if self._ftp is not None:
            try:
                self._ftp.voidcmd("NOOP")  # 연결 상태 확인
                return self._ftp
            except Exception:
                self._close()
        
        logger.info_with_details(
            f"FTP 서버 연결 중: {self.config.ftp_host}",
            stage="connect",
            details={"host": self.config.ftp_host},
        )
        
        self._ftp = FTP(self.config.ftp_host)
        self._ftp.login()  # Anonymous login
        return self._ftp
    
    def _close(self) -> None:
        """FTP 연결 종료."""
        if self._ftp is not None:
            try:
                self._ftp.quit()
            except Exception:
                pass
            finally:
                self._ftp = None
    
    # -------------------------------------------------------------------------
    # 파일명 파싱 (요구사항 1.2)
    # -------------------------------------------------------------------------
    
    @classmethod
    def parse_filename(cls, filename: str) -> Optional[int]:
        """파일명에서 MTG(회차) 번호를 추출.
        
        Args:
            filename: TDoc List 파일명 (예: TDoc_List_Meeting_RAN#100.xlsx)
            
        Returns:
            회차 번호 (int) 또는 None (패턴 불일치 시)
            
        Examples:
            >>> FTPCollector.parse_filename("TDoc_List_Meeting_RAN#100.xlsx")
            100
            >>> FTPCollector.parse_filename("TDoc_List_Meeting_RAN#100-e.xlsx")
            100
            >>> FTPCollector.parse_filename("some_other_file.xlsx")
            None
        """
        match = cls.FILENAME_PATTERN.search(filename)
        if match:
            return int(match.group(1))
        return None
    
    @classmethod
    def is_tdoc_list_file(cls, filename: str) -> bool:
        """파일이 TDoc List xlsx 파일인지 확인.
        
        파일명 패턴: 'TDoc_List' 포함 + '.xlsx' 확장자
        (원본 노트북의 느슨한 매칭 방식 유지)
        
        Args:
            filename: 확인할 파일명
            
        Returns:
            TDoc List xlsx 파일이면 True
        """
        return "TDoc_List" in filename and filename.endswith(".xlsx")
    
    # -------------------------------------------------------------------------
    # FTP 경로 생성
    # -------------------------------------------------------------------------
    
    def _build_ftp_path(self, tsg: str, wg: str, mtg: int) -> str:
        """FTP 경로 생성.
        
        Args:
            tsg: TSG 그룹명 (RAN, SA, CT)
            wg: Working Group (TSG, WG1, ..., WG6)
            mtg: 회차 번호
            
        Returns:
            FTP 경로 문자열
            
        Examples:
            >>> collector._build_ftp_path("RAN", "TSG", 100)
            '/tsg_ran/TSG_RAN/TSGR_100/Docs/'
            >>> collector._build_ftp_path("RAN", "WG1", 100)
            '/tsg_ran/WG1_RL1/TSGR1_100/Docs/'
        """
        # TSG 총회인 경우
        if wg == "TSG":
            return self.config.ftp_base_path_template.format(
                tsg_lower=tsg.lower(),
                tsg=tsg,
                mtg=mtg,
            )
        
        # WG의 경우 다른 경로 패턴 사용
        # 예: /tsg_ran/WG1_RL1/TSGR1_100/Docs/
        wg_num = wg.replace("WG", "")
        
        # TSG별 WG 접미사 매핑
        wg_suffix_map = {
            "RAN": {
                "1": "RL1", "2": "RL2", "3": "RL3", 
                "4": "RL4", "5": "RL5", "6": "RL6"
            },
            "SA": {
                "1": "S1", "2": "S2", "3": "S3", 
                "4": "S4", "5": "S5", "6": "S6"
            },
            "CT": {
                "1": "C1", "2": "C2", "3": "C3", 
                "4": "C4", "5": "C5", "6": "C6"
            },
        }
        
        suffix = wg_suffix_map.get(tsg, {}).get(wg_num, f"{tsg[0]}{wg_num}")
        
        # WG 경로 패턴: /tsg_{tsg_lower}/WG{num}_{suffix}/TSGR{num}_{mtg}/Docs/
        return f"/tsg_{tsg.lower()}/WG{wg_num}_{suffix}/TSGR{wg_num}_{mtg}/Docs/"
    
    # -------------------------------------------------------------------------
    # 로컬 파일 존재 확인 (요구사항 1.4)
    # -------------------------------------------------------------------------
    
    def _get_local_path(self, file_info: TDocFileInfo) -> Path:
        """파일의 로컬 저장 경로 반환.
        
        Args:
            file_info: TDoc 파일 정보
            
        Returns:
            로컬 파일 경로
        """
        return self.raw_dir / file_info.local_subdir / file_info.filename
    
    def _file_exists_locally(self, file_info: TDocFileInfo) -> bool:
        """파일이 로컬에 이미 존재하는지 확인 (요구사항 1.4).
        
        Args:
            file_info: 확인할 파일 정보
            
        Returns:
            로컬에 존재하면 True
        """
        return self._get_local_path(file_info).exists()
    
    # -------------------------------------------------------------------------
    # 파일 탐색 (요구사항 1.1)
    # -------------------------------------------------------------------------
    
    def discover_files(self) -> List[TDocFileInfo]:
        """FTP 서버에서 다운로드 대상 파일 목록을 탐색.
        
        config/collector.yaml에 설정된 targets(TSG, WG, min_meeting)에 따라
        FTP 서버를 순회하며 TDoc List xlsx 파일을 탐색한다.
        
        Returns:
            TDocFileInfo 객체 리스트 (tsg, wg, mtg, filename, ftp_path 포함)
        """
        discovered_files: List[TDocFileInfo] = []
        ftp = self._connect()
        
        for target in self.config.targets:
            tsg = target.tsg
            min_meeting = target.min_meeting
            
            for wg in target.wg_list:
                logger.info_with_details(
                    f"탐색 중: TSG={tsg}, WG={wg}",
                    stage="discover",
                    details={"tsg": tsg, "wg": wg, "min_meeting": min_meeting},
                )
                
                # 회차 번호를 min_meeting부터 시작하여 탐색
                # FTP 디렉토리가 존재하지 않을 때까지 순회
                mtg = min_meeting
                consecutive_failures = 0
                max_consecutive_failures = 5  # 연속 5회 실패 시 해당 WG 탐색 종료
                
                while consecutive_failures < max_consecutive_failures:
                    ftp_path = self._build_ftp_path(tsg, wg, mtg)
                    
                    try:
                        files = ftp.nlst(ftp_path)
                        consecutive_failures = 0  # 성공 시 리셋
                        
                        for file_path in files:
                            filename = Path(file_path).name
                            
                            if self.is_tdoc_list_file(filename):
                                # 파일명에서 MTG 추출 (파일명에 명시된 회차가 더 정확)
                                parsed_mtg = self.parse_filename(filename)
                                actual_mtg = parsed_mtg if parsed_mtg else mtg
                                
                                file_info = TDocFileInfo(
                                    tsg=tsg,
                                    wg=wg,
                                    mtg=actual_mtg,
                                    filename=filename,
                                    ftp_path=ftp_path + filename,
                                )
                                discovered_files.append(file_info)
                                
                                logger.debug_with_details(
                                    f"파일 발견: {filename}",
                                    stage="discover",
                                    details={
                                        "tsg": tsg,
                                        "wg": wg,
                                        "mtg": actual_mtg,
                                        "filename": filename,
                                    },
                                )
                        
                    except error_perm as e:
                        # 550: 디렉토리 없음 등의 권한 에러
                        consecutive_failures += 1
                        logger.debug_with_details(
                            f"FTP 경로 접근 불가: {ftp_path}",
                            stage="discover",
                            details={"ftp_path": ftp_path, "error": str(e)},
                        )
                    except error_temp as e:
                        # 임시 에러 (연결 문제 등)
                        consecutive_failures += 1
                        logger.warning_with_details(
                            f"FTP 임시 에러: {ftp_path}",
                            stage="discover",
                            details={"ftp_path": ftp_path, "error": str(e)},
                        )
                    
                    mtg += 1
        
        logger.info_with_details(
            f"총 {len(discovered_files)}개 파일 발견",
            stage="discover",
            details={"total_files": len(discovered_files)},
        )
        
        return discovered_files
    
    # -------------------------------------------------------------------------
    # 파일 다운로드 (요구사항 1.1, 1.5, 1.6)
    # -------------------------------------------------------------------------
    
    def download_file(self, file_info: TDocFileInfo) -> DownloadResult:
        """단일 파일을 다운로드.
        
        로컬에 이미 존재하는 경우 스킵하고 (요구사항 1.4),
        다운로드 실패 시 재시도한다 (요구사항 1.5, 1.6).
        
        Args:
            file_info: 다운로드할 파일 정보
            
        Returns:
            DownloadResult (success, local_path, error_message 등)
        """
        local_path = self._get_local_path(file_info)
        
        # 로컬 파일 존재 시 스킵 (요구사항 1.4)
        if local_path.exists():
            logger.debug_with_details(
                f"파일 이미 존재, 스킵: {file_info.filename}",
                stage="download",
                details={
                    "filename": file_info.filename,
                    "local_path": str(local_path),
                    "skipped": True,
                },
            )
            return DownloadResult(
                success=True,
                file_info=file_info,
                local_path=local_path,
                skipped=True,
            )
        
        # 로컬 디렉토리 생성
        local_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 재시도 로직 (요구사항 1.5, 1.6)
        last_error: Optional[Exception] = None
        retry_count = 0
        
        while retry_count <= self.config.max_retry:
            try:
                ftp = self._connect()
                
                # 바이너리 모드로 다운로드
                with open(local_path, "wb") as f:
                    ftp.retrbinary(f"RETR {file_info.ftp_path}", f.write)
                
                # 요구사항 1.7: 수집 이력 로깅
                self._history_logger.log_collection_result(
                    file_name=file_info.filename,
                    success=True,
                    retry_count=retry_count,
                )
                
                logger.info_with_details(
                    f"다운로드 완료: {file_info.filename}",
                    stage="download",
                    details={
                        "filename": file_info.filename,
                        "local_path": str(local_path),
                        "retry_count": retry_count,
                    },
                )
                
                return DownloadResult(
                    success=True,
                    file_info=file_info,
                    local_path=local_path,
                    retry_count=retry_count,
                )
                
            except Exception as e:
                last_error = e
                retry_count += 1
                
                # 요구사항 1.5: 실패 원인과 파일 경로를 로그에 기록
                logger.warning_with_details(
                    f"다운로드 실패, 재시도 {retry_count}/{self.config.max_retry}: {file_info.filename}",
                    stage="download",
                    details={
                        "filename": file_info.filename,
                        "ftp_path": file_info.ftp_path,
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                        "retry_count": retry_count,
                    },
                )
                
                # 연결 재설정
                self._close()
                
                if retry_count <= self.config.max_retry:
                    time.sleep(self.config.retry_delay)
        
        # 최대 재시도 초과 (요구사항 1.6)
        error_type = type(last_error).__name__ if last_error else "Unknown"
        error_message = str(last_error) if last_error else "Unknown error"
        
        # 요구사항 1.7: 수집 이력 로깅 (실패)
        self._history_logger.log_collection_result(
            file_name=file_info.filename,
            success=False,
            error_message=error_message,
            error_type=error_type,
            retry_count=retry_count - 1,
        )
        
        logger.error_with_details(
            f"다운로드 최종 실패: {file_info.filename}",
            stage="download",
            details={
                "filename": file_info.filename,
                "ftp_path": file_info.ftp_path,
                "error_type": error_type,
                "error_message": error_message,
                "retry_count": retry_count - 1,
            },
        )
        
        # 실패한 경우 임시 파일 삭제 (있다면)
        if local_path.exists():
            try:
                local_path.unlink()
            except Exception:
                pass
        
        return DownloadResult(
            success=False,
            file_info=file_info,
            error_message=error_message,
            error_type=error_type,
            retry_count=retry_count - 1,
        )
    
    # -------------------------------------------------------------------------
    # 전체 수집 프로세스
    # -------------------------------------------------------------------------
    
    def collect_all(self) -> CollectionReport:
        """전체 수집 프로세스 실행.
        
        1. FTP 서버에서 파일 목록 탐색
        2. 로컬에 존재하지 않는 파일만 다운로드
        3. 수집 결과 보고서 반환
        
        Returns:
            CollectionReport (총 파일 수, 성공/실패 수, 실패 목록)
        """
        report = CollectionReport(started_at=datetime.now(timezone.utc))
        
        logger.info_with_details(
            "FTP 수집 프로세스 시작",
            stage="collect",
            details={"host": self.config.ftp_host},
        )
        
        try:
            # 1. 파일 목록 탐색
            discovered_files = self.discover_files()
            report.total_files = len(discovered_files)
            
            # 2. 각 파일 다운로드
            for file_info in discovered_files:
                result = self.download_file(file_info)
                
                if result.success:
                    if result.skipped:
                        report.skipped += 1
                    else:
                        report.downloaded += 1
                else:
                    report.failed += 1
                    report.failed_files.append(result)
            
        finally:
            # FTP 연결 종료
            self._close()
            report.finished_at = datetime.now(timezone.utc)
        
        logger.info_with_details(
            f"FTP 수집 완료: downloaded={report.downloaded}, skipped={report.skipped}, failed={report.failed}",
            stage="collect",
            details={
                "total_files": report.total_files,
                "downloaded": report.downloaded,
                "skipped": report.skipped,
                "failed": report.failed,
                "duration_seconds": report.duration_seconds,
            },
        )
        
        return report


# =============================================================================
# 모듈 레벨 편의 함수
# =============================================================================


def collect_tdoc_files(config: Optional[CollectorConfig] = None) -> CollectionReport:
    """TDoc 파일 수집 편의 함수.
    
    Args:
        config: CollectorConfig 객체. None이면 collector.yaml에서 로드.
        
    Returns:
        CollectionReport
    """
    if config is None:
        from src.utils.config_loader import load_config
        config = load_config("collector")
    
    collector = FTPCollector(config)
    return collector.collect_all()


__all__ = [
    "TDocFileInfo",
    "DownloadResult",
    "CollectionReport",
    "FTPCollector",
    "collect_tdoc_files",
]
