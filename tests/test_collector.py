"""
FTP Collector 모듈 단위 테스트.

Task 3.2: FTPCollector 단위 테스트 작성
- 파일명 패턴 파싱 테스트 (Property 1)
- 로컬 파일 존재 시 스킵 테스트 (Property 2)
- Mock FTP 서버를 사용한 다운로드 테스트

Requirements: 17.1, 17.2
"""

import io
import tempfile
from dataclasses import dataclass
from ftplib import FTP, error_perm, error_temp
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, Mock, patch

import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

from src.collector.ftp_collector import (
    FTPCollector,
    TDocFileInfo,
    DownloadResult,
    CollectionReport,
)
from src.utils.config_loader import (
    CollectorConfig,
    CollectorTarget,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_collector_config() -> CollectorConfig:
    """테스트용 Collector 설정."""
    return CollectorConfig(
        ftp_host="ftp.test.org",
        ftp_base_path_template="/tsg_{tsg_lower}/TSG_{tsg}/TSGR_{mtg}/Docs/",
        targets=[
            CollectorTarget(tsg="RAN", min_meeting=69, wg_list=["TSG", "WG1"]),
            CollectorTarget(tsg="SA", min_meeting=69, wg_list=["TSG"]),
        ],
        max_retry=2,
        retry_delay=0,  # 테스트에서는 지연 없음
    )


@pytest.fixture
def mock_ftp():
    """Mock FTP 객체."""
    ftp = MagicMock(spec=FTP)
    ftp.login.return_value = "230 Login successful."
    ftp.voidcmd.return_value = "200 NOOP ok."
    return ftp


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    """임시 데이터 디렉토리."""
    data_dir = tmp_path / "data"
    raw_dir = data_dir / "raw"
    raw_dir.mkdir(parents=True)
    return data_dir


# =============================================================================
# Property 1: 파일명 패턴 파싱 정확성 테스트
# =============================================================================


class TestFilenamePatternParsing:
    """Property 1: 파일명 패턴 파싱 정확성.
    
    **Validates: Requirements 1.2**
    
    For any 유효한 TDoc List 파일명 형식 `TDoc_List_Meeting_{TSG}#{MTG}.xlsx`에 대해,
    파싱 결과는 정확한 MTG 값을 추출해야 한다.
    """
    
    @given(
        tsg=st.sampled_from(["RAN", "SA", "CT"]),
        mtg=st.integers(min_value=69, max_value=200),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_standard_filename_parsing(self, tsg: str, mtg: int) -> None:
        """표준 형식 파일명에서 MTG 추출 테스트.
        
        **Validates: Requirements 1.2**
        """
        filename = f"TDoc_List_Meeting_{tsg}#{mtg}.xlsx"
        result = FTPCollector.parse_filename(filename)
        
        assert result is not None, f"파일명 {filename}에서 MTG 추출 실패"
        assert result == mtg, f"추출된 MTG({result})가 예상값({mtg})과 불일치"
    
    @given(
        tsg=st.sampled_from(["RAN", "SA", "CT"]),
        mtg=st.integers(min_value=69, max_value=200),
        suffix=st.sampled_from(["-e", "_e", "-e2", ""]),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_emeeting_filename_parsing(self, tsg: str, mtg: int, suffix: str) -> None:
        """e-meeting 형식 파일명에서 MTG 추출 테스트.
        
        e-meeting(코로나 시기 등)은 #{MTG}-e.xlsx처럼 접미사가 붙을 수 있으므로,
        MTG 추출은 #(\\d+) 정규식으로 접미사와 무관하게 숫자만 취득해야 한다.
        
        **Validates: Requirements 1.2**
        """
        filename = f"TDoc_List_Meeting_{tsg}#{mtg}{suffix}.xlsx"
        result = FTPCollector.parse_filename(filename)
        
        assert result is not None, f"e-meeting 파일명 {filename}에서 MTG 추출 실패"
        assert result == mtg, f"추출된 MTG({result})가 예상값({mtg})과 불일치"
    
    @given(
        tsg=st.sampled_from(["RAN", "SA", "CT", "ran", "sa", "ct", "Ran", "Sa", "Ct"]),
        mtg=st.integers(min_value=1, max_value=300),
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_case_insensitive_parsing(self, tsg: str, mtg: int) -> None:
        """대소문자 무관하게 파일명 파싱 테스트.
        
        **Validates: Requirements 1.2**
        """
        filename = f"TDoc_List_Meeting_{tsg}#{mtg}.xlsx"
        result = FTPCollector.parse_filename(filename)
        
        # 파싱은 대소문자 무관하게 동작해야 함
        assert result is not None
        assert result == mtg
    
    def test_invalid_filename_returns_none(self) -> None:
        """유효하지 않은 파일명에 대해 None 반환 테스트."""
        invalid_filenames = [
            "some_other_file.xlsx",
            "TDoc_List_no_hash.xlsx",
            "Meeting_RAN#100.xlsx",
            "TDoc_List_Meeting_RAN.xlsx",
            "TDoc_List_Meeting_RAN#abc.xlsx",
            "",
        ]
        
        for filename in invalid_filenames:
            result = FTPCollector.parse_filename(filename)
            assert result is None, f"잘못된 파일명 {filename}이 None을 반환하지 않음"
    
    def test_is_tdoc_list_file(self) -> None:
        """TDoc List 파일 식별 테스트.
        
        파일 판별은 'TDoc_List' in filename and filename.endswith('.xlsx')
        형태의 느슨한 매칭이어야 함.
        """
        valid_files = [
            "TDoc_List_Meeting_RAN#100.xlsx",
            "TDoc_List_Meeting_SA#75-e.xlsx",
            "TDoc_List_something.xlsx",
        ]
        
        for filename in valid_files:
            assert FTPCollector.is_tdoc_list_file(filename) is True, \
                f"{filename}이 TDoc List 파일로 인식되지 않음"
        
        invalid_files = [
            "TDoc_List_Meeting_RAN#100.xls",  # 확장자 다름
            "Meeting_RAN#100.xlsx",  # TDoc_List 없음
            "TDoc_List.csv",  # 확장자 다름
            "tdoc_list_meeting.xlsx",  # 소문자 (원본 노트북의 느슨한 매칭은 대소문자 구분)
        ]
        
        for filename in invalid_files:
            # Note: 현재 구현에서 "TDoc_List" 검사는 대소문자 구분함
            result = FTPCollector.is_tdoc_list_file(filename)
            if "TDoc_List" in filename and filename.endswith(".xlsx"):
                assert result is True
            else:
                assert result is False


# =============================================================================
# Property 2: 로컬 파일 존재 시 스킵 테스트
# =============================================================================


class TestLocalFileSkip:
    """Property 2: 로컬 파일 존재 시 다운로드 스킵.
    
    **Validates: Requirements 1.4**
    
    For any 로컬에 이미 존재하는 파일에 대해, Collector는 해당 파일을
    재다운로드하지 않아야 한다.
    """
    
    def test_skip_existing_file(
        self,
        sample_collector_config: CollectorConfig,
        tmp_data_dir: Path,
    ) -> None:
        """로컬에 이미 존재하는 파일은 스킵해야 함.
        
        **Validates: Requirements 1.4**
        """
        # 로컬에 파일 생성
        raw_dir = tmp_data_dir / "raw" / "RAN"
        raw_dir.mkdir(parents=True, exist_ok=True)
        existing_file = raw_dir / "TDoc_List_Meeting_RAN#100.xlsx"
        existing_file.write_text("test content")
        
        # Collector 생성
        collector = FTPCollector(sample_collector_config, data_dir=tmp_data_dir)
        
        # 파일 정보 생성
        file_info = TDocFileInfo(
            tsg="RAN",
            wg="TSG",
            mtg=100,
            filename="TDoc_List_Meeting_RAN#100.xlsx",
            ftp_path="/tsg_ran/TSG_RAN/TSGR_100/Docs/TDoc_List_Meeting_RAN#100.xlsx",
        )
        
        # 다운로드 시도 - FTP 연결 없이 스킵되어야 함
        result = collector.download_file(file_info)
        
        assert result.success is True, "로컬 파일 존재 시 성공으로 처리되어야 함"
        assert result.skipped is True, "로컬 파일 존재 시 skipped=True이어야 함"
        assert result.local_path == existing_file, "로컬 경로가 올바르게 반환되어야 함"
    
    @given(
        tsg=st.sampled_from(["RAN", "SA", "CT"]),
        mtg=st.integers(min_value=69, max_value=150),
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow])
    def test_skip_logic_with_various_files(self, tsg: str, mtg: int) -> None:
        """다양한 파일에 대한 스킵 로직 Property 테스트.
        
        **Validates: Requirements 1.4**
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_data_dir = Path(tmp_dir) / "data"
            raw_dir = tmp_data_dir / "raw" / tsg
            raw_dir.mkdir(parents=True, exist_ok=True)
            
            filename = f"TDoc_List_Meeting_{tsg}#{mtg}.xlsx"
            existing_file = raw_dir / filename
            existing_file.write_text("existing content")
            
            config = CollectorConfig(
                ftp_host="ftp.test.org",
                ftp_base_path_template="/tsg_{tsg_lower}/TSG_{tsg}/TSGR_{mtg}/Docs/",
                targets=[CollectorTarget(tsg=tsg, min_meeting=69, wg_list=["TSG"])],
                max_retry=1,
                retry_delay=0,
            )
            
            collector = FTPCollector(config, data_dir=tmp_data_dir)
            
            file_info = TDocFileInfo(
                tsg=tsg,
                wg="TSG",
                mtg=mtg,
                filename=filename,
                ftp_path=f"/tsg_{tsg.lower()}/TSG_{tsg}/TSGR_{mtg}/Docs/{filename}",
            )
            
            result = collector.download_file(file_info)
            
            assert result.success is True
            assert result.skipped is True
    
    def test_download_new_file(
        self,
        sample_collector_config: CollectorConfig,
        tmp_data_dir: Path,
        mock_ftp: MagicMock,
    ) -> None:
        """로컬에 없는 파일은 다운로드 시도해야 함."""
        collector = FTPCollector(sample_collector_config, data_dir=tmp_data_dir)
        
        file_info = TDocFileInfo(
            tsg="RAN",
            wg="TSG",
            mtg=100,
            filename="TDoc_List_Meeting_RAN#100.xlsx",
            ftp_path="/tsg_ran/TSG_RAN/TSGR_100/Docs/TDoc_List_Meeting_RAN#100.xlsx",
        )
        
        # 로컬에 파일이 없음을 확인
        local_path = collector._get_local_path(file_info)
        assert not local_path.exists()
        
        # Mock FTP 설정
        file_content = b"test xlsx content"
        
        def mock_retrbinary(cmd: str, callback):
            callback(file_content)
        
        mock_ftp.retrbinary.side_effect = mock_retrbinary
        
        with patch.object(collector, "_connect", return_value=mock_ftp):
            result = collector.download_file(file_info)
        
        assert result.success is True
        assert result.skipped is False
        assert result.local_path.exists()
        assert result.local_path.read_bytes() == file_content


# =============================================================================
# Mock FTP 서버를 사용한 다운로드 테스트
# =============================================================================


class TestFTPDownload:
    """Mock FTP 서버를 사용한 다운로드 테스트.
    
    **Validates: Requirements 1.1, 1.5, 1.6, 1.7**
    """
    
    def test_successful_download(
        self,
        sample_collector_config: CollectorConfig,
        tmp_data_dir: Path,
        mock_ftp: MagicMock,
    ) -> None:
        """정상적인 파일 다운로드 테스트.
        
        **Validates: Requirements 1.1**
        """
        collector = FTPCollector(sample_collector_config, data_dir=tmp_data_dir)
        
        file_info = TDocFileInfo(
            tsg="RAN",
            wg="TSG",
            mtg=100,
            filename="TDoc_List_Meeting_RAN#100.xlsx",
            ftp_path="/tsg_ran/TSG_RAN/TSGR_100/Docs/TDoc_List_Meeting_RAN#100.xlsx",
        )
        
        file_content = b"test xlsx binary content"
        
        def mock_retrbinary(cmd: str, callback):
            callback(file_content)
        
        mock_ftp.retrbinary.side_effect = mock_retrbinary
        
        with patch.object(collector, "_connect", return_value=mock_ftp):
            result = collector.download_file(file_info)
        
        assert result.success is True
        assert result.error_message is None
        assert result.local_path is not None
        assert result.local_path.exists()
        assert result.local_path.read_bytes() == file_content
        assert result.retry_count == 0
    
    def test_retry_on_failure(
        self,
        sample_collector_config: CollectorConfig,
        tmp_data_dir: Path,
        mock_ftp: MagicMock,
    ) -> None:
        """다운로드 실패 시 재시도 테스트.
        
        **Validates: Requirements 1.5**
        """
        collector = FTPCollector(sample_collector_config, data_dir=tmp_data_dir)
        
        file_info = TDocFileInfo(
            tsg="RAN",
            wg="TSG",
            mtg=100,
            filename="TDoc_List_Meeting_RAN#100.xlsx",
            ftp_path="/tsg_ran/TSG_RAN/TSGR_100/Docs/TDoc_List_Meeting_RAN#100.xlsx",
        )
        
        # 첫 번째 시도 실패, 두 번째 시도 성공
        call_count = 0
        file_content = b"test content"
        
        def mock_retrbinary(cmd: str, callback):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise error_temp("Connection reset")
            callback(file_content)
        
        mock_ftp.retrbinary.side_effect = mock_retrbinary
        
        with patch.object(collector, "_connect", return_value=mock_ftp):
            result = collector.download_file(file_info)
        
        assert result.success is True
        assert result.retry_count == 1  # 1회 재시도 후 성공
        assert call_count == 2
    
    def test_max_retry_exceeded(
        self,
        sample_collector_config: CollectorConfig,
        tmp_data_dir: Path,
        mock_ftp: MagicMock,
    ) -> None:
        """최대 재시도 횟수 초과 테스트.
        
        **Validates: Requirements 1.6**
        """
        collector = FTPCollector(sample_collector_config, data_dir=tmp_data_dir)
        
        file_info = TDocFileInfo(
            tsg="RAN",
            wg="TSG",
            mtg=100,
            filename="TDoc_List_Meeting_RAN#100.xlsx",
            ftp_path="/tsg_ran/TSG_RAN/TSGR_100/Docs/TDoc_List_Meeting_RAN#100.xlsx",
        )
        
        # 모든 시도 실패
        mock_ftp.retrbinary.side_effect = error_temp("Connection failed")
        
        with patch.object(collector, "_connect", return_value=mock_ftp):
            result = collector.download_file(file_info)
        
        assert result.success is False
        assert result.error_message is not None
        assert "Connection failed" in result.error_message
        assert result.error_type == "error_temp"
        # max_retry=2이므로 총 3회 시도 (초기 1회 + 재시도 2회)
        assert result.retry_count == sample_collector_config.max_retry
        
        # 실패한 임시 파일이 삭제되었는지 확인
        local_path = collector._get_local_path(file_info)
        assert not local_path.exists()
    
    def test_failed_file_cleanup(
        self,
        sample_collector_config: CollectorConfig,
        tmp_data_dir: Path,
        mock_ftp: MagicMock,
    ) -> None:
        """다운로드 실패 시 부분 파일 정리 테스트."""
        collector = FTPCollector(sample_collector_config, data_dir=tmp_data_dir)
        
        file_info = TDocFileInfo(
            tsg="RAN",
            wg="TSG",
            mtg=100,
            filename="TDoc_List_Meeting_RAN#100.xlsx",
            ftp_path="/tsg_ran/TSG_RAN/TSGR_100/Docs/TDoc_List_Meeting_RAN#100.xlsx",
        )
        
        # 파일 일부 쓰기 후 실패 시뮬레이션
        partial_content = b"partial"
        
        def mock_retrbinary(cmd: str, callback):
            callback(partial_content)
            raise error_temp("Connection interrupted")
        
        mock_ftp.retrbinary.side_effect = mock_retrbinary
        
        with patch.object(collector, "_connect", return_value=mock_ftp):
            result = collector.download_file(file_info)
        
        assert result.success is False
        # 부분 파일이 정리되었는지 확인
        local_path = collector._get_local_path(file_info)
        assert not local_path.exists()


class TestFTPDiscovery:
    """FTP 파일 탐색 테스트.
    
    **Validates: Requirements 1.1, 1.2**
    """
    
    def test_discover_files_single_target(
        self,
        sample_collector_config: CollectorConfig,
        tmp_data_dir: Path,
        mock_ftp: MagicMock,
    ) -> None:
        """단일 대상에서 파일 탐색 테스트."""
        # config 수정: 단일 TSG만 탐색
        config = CollectorConfig(
            ftp_host="ftp.test.org",
            ftp_base_path_template="/tsg_{tsg_lower}/TSG_{tsg}/TSGR_{mtg}/Docs/",
            targets=[CollectorTarget(tsg="RAN", min_meeting=100, wg_list=["TSG"])],
            max_retry=1,
            retry_delay=0,
        )
        
        collector = FTPCollector(config, data_dir=tmp_data_dir)
        
        # Mock FTP 응답 설정
        def mock_nlst(path: str) -> List[str]:
            if "TSGR_100" in path:
                return [
                    f"{path}TDoc_List_Meeting_RAN#100.xlsx",
                    f"{path}other_file.txt",
                ]
            elif "TSGR_101" in path:
                return [f"{path}TDoc_List_Meeting_RAN#101.xlsx"]
            else:
                raise error_perm("550 Directory not found")
        
        mock_ftp.nlst.side_effect = mock_nlst
        
        with patch.object(collector, "_connect", return_value=mock_ftp):
            files = collector.discover_files()
        
        assert len(files) == 2
        
        filenames = [f.filename for f in files]
        assert "TDoc_List_Meeting_RAN#100.xlsx" in filenames
        assert "TDoc_List_Meeting_RAN#101.xlsx" in filenames
        
        # 비 TDoc 파일은 제외되어야 함
        assert "other_file.txt" not in filenames
    
    def test_discover_files_extracts_correct_metadata(
        self,
        tmp_data_dir: Path,
        mock_ftp: MagicMock,
    ) -> None:
        """파일 탐색 시 메타데이터 추출 테스트."""
        config = CollectorConfig(
            ftp_host="ftp.test.org",
            ftp_base_path_template="/tsg_{tsg_lower}/TSG_{tsg}/TSGR_{mtg}/Docs/",
            targets=[CollectorTarget(tsg="SA", min_meeting=75, wg_list=["TSG"])],
            max_retry=1,
            retry_delay=0,
        )
        
        collector = FTPCollector(config, data_dir=tmp_data_dir)
        
        def mock_nlst(path: str) -> List[str]:
            if "TSGR_75" in path:
                return [f"{path}TDoc_List_Meeting_SA#75.xlsx"]
            else:
                raise error_perm("550 Directory not found")
        
        mock_ftp.nlst.side_effect = mock_nlst
        
        with patch.object(collector, "_connect", return_value=mock_ftp):
            files = collector.discover_files()
        
        assert len(files) == 1
        
        file_info = files[0]
        assert file_info.tsg == "SA"
        assert file_info.wg == "TSG"
        assert file_info.mtg == 75
        assert file_info.filename == "TDoc_List_Meeting_SA#75.xlsx"


class TestCollectionReport:
    """수집 보고서 테스트.
    
    **Validates: Requirements 1.7**
    """
    
    def test_collect_all_report_counts(
        self,
        tmp_data_dir: Path,
        mock_ftp: MagicMock,
    ) -> None:
        """collect_all 보고서의 통계 정확성 테스트."""
        config = CollectorConfig(
            ftp_host="ftp.test.org",
            ftp_base_path_template="/tsg_{tsg_lower}/TSG_{tsg}/TSGR_{mtg}/Docs/",
            targets=[CollectorTarget(tsg="RAN", min_meeting=100, wg_list=["TSG"])],
            max_retry=1,
            retry_delay=0,
        )
        
        # 기존 파일 생성 (스킵될 파일)
        raw_dir = tmp_data_dir / "raw" / "RAN"
        raw_dir.mkdir(parents=True, exist_ok=True)
        existing_file = raw_dir / "TDoc_List_Meeting_RAN#100.xlsx"
        existing_file.write_text("existing")
        
        collector = FTPCollector(config, data_dir=tmp_data_dir)
        
        # Mock 설정: 2개 파일 발견 (1개는 기존, 1개는 새로 다운로드)
        def mock_nlst(path: str) -> List[str]:
            if "TSGR_100" in path:
                return [
                    f"{path}TDoc_List_Meeting_RAN#100.xlsx",
                    f"{path}TDoc_List_Meeting_RAN#100-e.xlsx",
                ]
            else:
                raise error_perm("550")
        
        mock_ftp.nlst.side_effect = mock_nlst
        
        def mock_retrbinary(cmd: str, callback):
            callback(b"new content")
        
        mock_ftp.retrbinary.side_effect = mock_retrbinary
        
        with patch.object(collector, "_connect", return_value=mock_ftp):
            report = collector.collect_all()
        
        assert report.total_files == 2
        assert report.skipped == 1  # 기존 파일
        assert report.downloaded == 1  # 새 파일
        assert report.failed == 0
        assert report.started_at is not None
        assert report.finished_at is not None
        assert report.duration_seconds >= 0
    
    def test_collect_all_with_failures(
        self,
        tmp_data_dir: Path,
        mock_ftp: MagicMock,
    ) -> None:
        """다운로드 실패 포함한 보고서 테스트."""
        config = CollectorConfig(
            ftp_host="ftp.test.org",
            ftp_base_path_template="/tsg_{tsg_lower}/TSG_{tsg}/TSGR_{mtg}/Docs/",
            targets=[CollectorTarget(tsg="RAN", min_meeting=100, wg_list=["TSG"])],
            max_retry=0,  # 재시도 없음
            retry_delay=0,
        )
        
        collector = FTPCollector(config, data_dir=tmp_data_dir)
        
        def mock_nlst(path: str) -> List[str]:
            if "TSGR_100" in path:
                return [f"{path}TDoc_List_Meeting_RAN#100.xlsx"]
            else:
                raise error_perm("550")
        
        mock_ftp.nlst.side_effect = mock_nlst
        mock_ftp.retrbinary.side_effect = error_temp("Download failed")
        
        with patch.object(collector, "_connect", return_value=mock_ftp):
            report = collector.collect_all()
        
        assert report.total_files == 1
        assert report.downloaded == 0
        assert report.failed == 1
        assert len(report.failed_files) == 1
        assert report.failed_files[0].error_message is not None


class TestTDocFileInfo:
    """TDocFileInfo 데이터클래스 테스트."""
    
    def test_local_subdir_tsg_plenary(self) -> None:
        """TSG 총회 파일의 로컬 하위 디렉토리."""
        file_info = TDocFileInfo(
            tsg="RAN",
            wg="TSG",
            mtg=100,
            filename="test.xlsx",
            ftp_path="/path/to/file",
        )
        
        assert file_info.local_subdir == "RAN"
    
    def test_local_subdir_wg(self) -> None:
        """WG 파일의 로컬 하위 디렉토리."""
        file_info = TDocFileInfo(
            tsg="RAN",
            wg="WG1",
            mtg=100,
            filename="test.xlsx",
            ftp_path="/path/to/file",
        )
        
        assert file_info.local_subdir == "RAN/WG1"
    
    def test_repr(self) -> None:
        """__repr__ 메서드 테스트."""
        file_info = TDocFileInfo(
            tsg="SA",
            wg="WG2",
            mtg=80,
            filename="TDoc_List.xlsx",
            ftp_path="/path",
        )
        
        repr_str = repr(file_info)
        assert "SA" in repr_str
        assert "WG2" in repr_str
        assert "80" in repr_str


class TestFTPPathBuilding:
    """FTP 경로 생성 테스트."""
    
    def test_tsg_plenary_path(
        self,
        sample_collector_config: CollectorConfig,
        tmp_data_dir: Path,
    ) -> None:
        """TSG 총회 경로 생성 테스트."""
        collector = FTPCollector(sample_collector_config, data_dir=tmp_data_dir)
        
        path = collector._build_ftp_path("RAN", "TSG", 100)
        
        assert path == "/tsg_ran/TSG_RAN/TSGR_100/Docs/"
    
    def test_wg_path_ran(
        self,
        sample_collector_config: CollectorConfig,
        tmp_data_dir: Path,
    ) -> None:
        """RAN WG 경로 생성 테스트."""
        collector = FTPCollector(sample_collector_config, data_dir=tmp_data_dir)
        
        path = collector._build_ftp_path("RAN", "WG1", 100)
        
        # WG 경로 패턴: /tsg_{tsg_lower}/WG{num}_{suffix}/TSGR{num}_{mtg}/Docs/
        assert path == "/tsg_ran/WG1_RL1/TSGR1_100/Docs/"
    
    def test_wg_path_sa(
        self,
        sample_collector_config: CollectorConfig,
        tmp_data_dir: Path,
    ) -> None:
        """SA WG 경로 생성 테스트."""
        collector = FTPCollector(sample_collector_config, data_dir=tmp_data_dir)
        
        path = collector._build_ftp_path("SA", "WG2", 80)
        
        assert path == "/tsg_sa/WG2_S2/TSGR2_80/Docs/"
    
    def test_wg_path_ct(
        self,
        sample_collector_config: CollectorConfig,
        tmp_data_dir: Path,
    ) -> None:
        """CT WG 경로 생성 테스트."""
        collector = FTPCollector(sample_collector_config, data_dir=tmp_data_dir)
        
        path = collector._build_ftp_path("CT", "WG3", 90)
        
        assert path == "/tsg_ct/WG3_C3/TSGR3_90/Docs/"


class TestDownloadResult:
    """DownloadResult 데이터클래스 테스트."""
    
    def test_success_result(self) -> None:
        """성공 결과 생성."""
        file_info = TDocFileInfo(
            tsg="RAN",
            wg="TSG",
            mtg=100,
            filename="test.xlsx",
            ftp_path="/path",
        )
        
        result = DownloadResult(
            success=True,
            file_info=file_info,
            local_path=Path("/data/raw/RAN/test.xlsx"),
        )
        
        assert result.success is True
        assert result.skipped is False
        assert result.error_message is None
    
    def test_skipped_result(self) -> None:
        """스킵 결과 생성."""
        file_info = TDocFileInfo(
            tsg="RAN",
            wg="TSG",
            mtg=100,
            filename="test.xlsx",
            ftp_path="/path",
        )
        
        result = DownloadResult(
            success=True,
            file_info=file_info,
            local_path=Path("/data/raw/RAN/test.xlsx"),
            skipped=True,
        )
        
        assert result.success is True
        assert result.skipped is True
    
    def test_failure_result(self) -> None:
        """실패 결과 생성."""
        file_info = TDocFileInfo(
            tsg="RAN",
            wg="TSG",
            mtg=100,
            filename="test.xlsx",
            ftp_path="/path",
        )
        
        result = DownloadResult(
            success=False,
            file_info=file_info,
            error_message="Connection failed",
            error_type="ConnectionError",
            retry_count=3,
        )
        
        assert result.success is False
        assert result.error_message == "Connection failed"
        assert result.retry_count == 3


class TestCollectionReportDataclass:
    """CollectionReport 데이터클래스 테스트."""
    
    def test_duration_seconds(self) -> None:
        """소요 시간 계산 테스트."""
        from datetime import datetime, timedelta, timezone
        
        started = datetime.now(timezone.utc)
        finished = started + timedelta(seconds=120)
        
        report = CollectionReport(
            total_files=10,
            downloaded=5,
            skipped=3,
            failed=2,
            started_at=started,
            finished_at=finished,
        )
        
        assert report.duration_seconds == 120.0
    
    def test_duration_seconds_none(self) -> None:
        """시작/종료 시간 없을 때 duration_seconds는 None."""
        report = CollectionReport(total_files=5)
        
        assert report.duration_seconds is None
    
    def test_repr(self) -> None:
        """__repr__ 메서드 테스트."""
        report = CollectionReport(
            total_files=10,
            downloaded=5,
            skipped=3,
            failed=2,
        )
        
        repr_str = repr(report)
        assert "total=10" in repr_str
        assert "downloaded=5" in repr_str
        assert "skipped=3" in repr_str
        assert "failed=2" in repr_str
