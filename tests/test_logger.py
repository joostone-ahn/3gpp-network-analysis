"""
Logger 모듈 단위 테스트.

Task 1.4: Logger 유틸리티 구현 검증
- JsonFormatter JSON 형식 출력 검증
- get_logger 캐싱 및 모듈별 로거 생성 검증
- setup_logging 핸들러 설정 검증
- 구조화된 로깅 (stage, details) 검증
- 수집 이력 로깅 (요구사항 1.5, 1.7) 검증
"""

import json
import logging
import tempfile
from pathlib import Path

import pytest

from src.utils.logger import (
    JsonFormatter,
    StructuredLoggerAdapter,
    create_collection_history_logger,
    get_logger,
    setup_logging,
)


class TestJsonFormatter:
    """JsonFormatter 클래스 테스트."""

    def test_format_basic_message(self) -> None:
        """기본 로그 메시지가 JSON 형식으로 포맷되는지 확인."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test_module",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="테스트 메시지",
            args=(),
            exc_info=None,
        )
        
        output = formatter.format(record)
        data = json.loads(output)
        
        assert "timestamp" in data
        assert data["level"] == "INFO"
        assert data["module"] == "test_module"
        assert data["message"] == "테스트 메시지"

    def test_format_with_stage(self) -> None:
        """stage 필드가 포함된 로그가 올바르게 포맷되는지 확인."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="collector",
            level=logging.ERROR,
            pathname="test.py",
            lineno=10,
            msg="다운로드 실패",
            args=(),
            exc_info=None,
        )
        record.stage = "download"
        
        output = formatter.format(record)
        data = json.loads(output)
        
        assert data["stage"] == "download"
        assert data["level"] == "ERROR"
        assert data["module"] == "collector"

    def test_format_with_details(self) -> None:
        """details 필드가 포함된 로그가 올바르게 포맷되는지 확인."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="collector",
            level=logging.ERROR,
            pathname="test.py",
            lineno=10,
            msg="파일 다운로드 실패",
            args=(),
            exc_info=None,
        )
        record.stage = "download"
        record.details = {
            "file": "TDoc_List_Meeting_RAN#100.xlsx",
            "error_type": "ConnectionError",
            "retry_count": 3,
        }
        
        output = formatter.format(record)
        data = json.loads(output)
        
        assert data["details"]["file"] == "TDoc_List_Meeting_RAN#100.xlsx"
        assert data["details"]["error_type"] == "ConnectionError"
        assert data["details"]["retry_count"] == 3

    def test_format_timestamp_is_iso8601(self) -> None:
        """타임스탬프가 ISO 8601 형식인지 확인."""
        formatter = JsonFormatter(include_timestamp=True)
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="test",
            args=(),
            exc_info=None,
        )
        
        output = formatter.format(record)
        data = json.loads(output)
        
        # ISO 8601 형식: YYYY-MM-DDTHH:MM:SSZ
        timestamp = data["timestamp"]
        assert len(timestamp) == 20
        assert timestamp[4] == "-"
        assert timestamp[7] == "-"
        assert timestamp[10] == "T"
        assert timestamp[13] == ":"
        assert timestamp[16] == ":"
        assert timestamp[19] == "Z"

    def test_format_without_timestamp(self) -> None:
        """타임스탬프 비활성화 시 타임스탬프가 포함되지 않는지 확인."""
        formatter = JsonFormatter(include_timestamp=False)
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="test",
            args=(),
            exc_info=None,
        )
        
        output = formatter.format(record)
        data = json.loads(output)
        
        assert "timestamp" not in data

    def test_format_korean_message(self) -> None:
        """한글 메시지가 올바르게 인코딩되는지 확인."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="파일 다운로드 완료: 한글파일명.xlsx",
            args=(),
            exc_info=None,
        )
        
        output = formatter.format(record)
        data = json.loads(output)
        
        assert "파일 다운로드 완료" in data["message"]
        assert "한글파일명.xlsx" in data["message"]


class TestGetLogger:
    """get_logger 함수 테스트."""

    def test_returns_logger_adapter(self) -> None:
        """StructuredLoggerAdapter 인스턴스를 반환하는지 확인."""
        logger = get_logger("test_module")
        assert isinstance(logger, StructuredLoggerAdapter)

    def test_caches_same_logger(self) -> None:
        """동일 모듈명으로 호출 시 동일 로거를 반환하는지 확인."""
        logger1 = get_logger("cache_test_module", default_stage="stage1")
        logger2 = get_logger("cache_test_module", default_stage="stage1")
        
        assert logger1 is logger2

    def test_different_stage_creates_different_logger(self) -> None:
        """다른 stage로 호출 시 다른 로거를 반환하는지 확인."""
        logger1 = get_logger("multi_stage_module", default_stage="download")
        logger2 = get_logger("multi_stage_module", default_stage="parse")
        
        assert logger1 is not logger2

    def test_default_stage_in_extra(self) -> None:
        """default_stage가 extra에 설정되는지 확인."""
        logger = get_logger("stage_test_module", default_stage="collect")
        
        assert logger.extra.get("stage") == "collect"


class TestStructuredLoggerAdapter:
    """StructuredLoggerAdapter 클래스 테스트."""

    def setup_method(self) -> None:
        """각 테스트 전에 실행되는 설정."""
        self.logger = logging.getLogger("adapter_test")
        self.logger.setLevel(logging.DEBUG)
        self.adapter = StructuredLoggerAdapter(self.logger, {"stage": "test"})

    def test_log_with_details(self, caplog: pytest.LogCaptureFixture) -> None:
        """log_with_details가 stage와 details를 올바르게 추가하는지 확인."""
        with caplog.at_level(logging.INFO):
            self.adapter.log_with_details(
                logging.INFO,
                "테스트 메시지",
                stage="download",
                details={"file": "test.xlsx"},
            )
        
        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert record.stage == "download"  # type: ignore
        assert record.details == {"file": "test.xlsx"}  # type: ignore

    def test_info_with_details(self, caplog: pytest.LogCaptureFixture) -> None:
        """info_with_details가 INFO 레벨로 로깅하는지 확인."""
        with caplog.at_level(logging.INFO):
            self.adapter.info_with_details(
                "정보 메시지",
                stage="parse",
                details={"count": 100},
            )
        
        assert len(caplog.records) == 1
        assert caplog.records[0].levelno == logging.INFO

    def test_error_with_details(self, caplog: pytest.LogCaptureFixture) -> None:
        """error_with_details가 ERROR 레벨로 로깅하는지 확인."""
        with caplog.at_level(logging.ERROR):
            self.adapter.error_with_details(
                "에러 메시지",
                stage="download",
                details={"error_type": "ConnectionError"},
            )
        
        assert len(caplog.records) == 1
        assert caplog.records[0].levelno == logging.ERROR

    def test_log_collection_result_success(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """수집 성공 결과가 올바르게 로깅되는지 확인 (요구사항 1.7)."""
        with caplog.at_level(logging.INFO):
            self.adapter.log_collection_result(
                file_name="TDoc_List_Meeting_RAN#100.xlsx",
                success=True,
            )
        
        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert record.levelno == logging.INFO
        assert "RAN#100" in record.message
        assert record.details["success"] is True  # type: ignore
        assert "collected_at" in record.details  # type: ignore

    def test_log_collection_result_failure(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """수집 실패 결과가 올바르게 로깅되는지 확인 (요구사항 1.5, 1.7)."""
        with caplog.at_level(logging.ERROR):
            self.adapter.log_collection_result(
                file_name="TDoc_List_Meeting_SA#120.xlsx",
                success=False,
                error_message="Connection refused",
                error_type="ConnectionError",
                retry_count=3,
            )
        
        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert record.levelno == logging.ERROR
        assert "SA#120" in record.message
        details = record.details  # type: ignore
        assert details["success"] is False
        assert details["error_message"] == "Connection refused"
        assert details["error_type"] == "ConnectionError"
        assert details["retry_count"] == 3


class TestSetupLogging:
    """setup_logging 함수 테스트."""

    def teardown_method(self) -> None:
        """각 테스트 후 루트 로거 핸들러 정리."""
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

    def test_sets_log_level(self) -> None:
        """로그 레벨이 올바르게 설정되는지 확인."""
        setup_logging(level=logging.DEBUG, console_output=True)
        
        root_logger = logging.getLogger()
        assert root_logger.level == logging.DEBUG

    def test_sets_log_level_from_string(self) -> None:
        """문자열 로그 레벨이 올바르게 변환되는지 확인."""
        setup_logging(level="WARNING", console_output=True)
        
        root_logger = logging.getLogger()
        assert root_logger.level == logging.WARNING

    def test_creates_console_handler(self) -> None:
        """콘솔 핸들러가 생성되는지 확인."""
        setup_logging(level=logging.INFO, console_output=True)
        
        root_logger = logging.getLogger()
        console_handlers = [
            h for h in root_logger.handlers
            if isinstance(h, logging.StreamHandler)
            and not isinstance(h, logging.FileHandler)
        ]
        assert len(console_handlers) == 1

    def test_skips_console_handler_when_disabled(self) -> None:
        """console_output=False일 때 콘솔 핸들러가 생성되지 않는지 확인."""
        setup_logging(level=logging.INFO, console_output=False)
        
        root_logger = logging.getLogger()
        console_handlers = [
            h for h in root_logger.handlers
            if isinstance(h, logging.StreamHandler)
            and not isinstance(h, logging.FileHandler)
        ]
        assert len(console_handlers) == 0

    def test_creates_file_handler(self) -> None:
        """파일 핸들러가 생성되는지 확인."""
        with tempfile.TemporaryDirectory() as tmpdir:
            setup_logging(
                level=logging.INFO,
                log_dir=tmpdir,
                log_file="test.log",
                console_output=False,
            )
            
            root_logger = logging.getLogger()
            file_handlers = [
                h for h in root_logger.handlers
                if isinstance(h, logging.FileHandler)
            ]
            assert len(file_handlers) == 1
            
            # 로그 파일이 생성되었는지 확인
            log_file = Path(tmpdir) / "test.log"
            assert log_file.exists()

    def test_uses_json_formatter_by_default(self) -> None:
        """기본값으로 JSON 포맷터가 사용되는지 확인."""
        setup_logging(level=logging.INFO, console_output=True, json_format=True)
        
        root_logger = logging.getLogger()
        for handler in root_logger.handlers:
            assert isinstance(handler.formatter, JsonFormatter)

    def test_uses_simple_formatter_when_json_disabled(self) -> None:
        """json_format=False일 때 기본 포맷터가 사용되는지 확인."""
        setup_logging(level=logging.INFO, console_output=True, json_format=False)
        
        root_logger = logging.getLogger()
        for handler in root_logger.handlers:
            assert not isinstance(handler.formatter, JsonFormatter)


class TestCollectionHistoryLogger:
    """create_collection_history_logger 함수 테스트."""

    def setup_method(self) -> None:
        """각 테스트 전 collection_history 로거 정리."""
        logger = logging.getLogger("collection_history")
        for handler in logger.handlers[:]:
            handler.close()
            logger.removeHandler(handler)

    def teardown_method(self) -> None:
        """각 테스트 후 collection_history 로거 정리."""
        logger = logging.getLogger("collection_history")
        for handler in logger.handlers[:]:
            handler.close()
            logger.removeHandler(handler)

    def test_creates_logger_with_file_handler(self) -> None:
        """수집 이력 전용 로거가 파일 핸들러와 함께 생성되는지 확인."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = create_collection_history_logger(log_dir=tmpdir)
            
            assert isinstance(logger, StructuredLoggerAdapter)
            
            # 파일 핸들러 확인
            base_logger = logger.logger
            file_handlers = [
                h for h in base_logger.handlers
                if isinstance(h, logging.FileHandler)
            ]
            assert len(file_handlers) == 1
            
            # 이력 파일이 생성되었는지 확인
            history_file = Path(tmpdir) / "collection_history.jsonl"
            assert history_file.exists()

    def test_logger_uses_json_formatter(self) -> None:
        """수집 이력 로거가 JSON 포맷터를 사용하는지 확인."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = create_collection_history_logger(log_dir=tmpdir)
            
            base_logger = logger.logger
            for handler in base_logger.handlers:
                if isinstance(handler, logging.FileHandler):
                    assert isinstance(handler.formatter, JsonFormatter)

    def test_default_stage_is_collect(self) -> None:
        """기본 stage가 'collect'인지 확인."""
        with tempfile.TemporaryDirectory() as tmpdir:
            logger = create_collection_history_logger(log_dir=tmpdir)
            
            assert logger.extra.get("stage") == "collect"


class TestEndToEndLogging:
    """로깅 시스템 통합 테스트."""

    def teardown_method(self) -> None:
        """각 테스트 후 루트 로거 핸들러 정리."""
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

    def test_full_logging_flow(self) -> None:
        """전체 로깅 흐름이 올바르게 동작하는지 확인."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 로깅 시스템 초기화
            setup_logging(
                level=logging.DEBUG,
                log_dir=tmpdir,
                log_file="test_pipeline.log",
                console_output=False,
                json_format=True,
            )
            
            # 모듈별 로거 생성
            collector_logger = get_logger("collector", default_stage="collect")
            
            # 로그 기록
            collector_logger.info_with_details(
                "수집 시작",
                details={"target_tsg": "RAN"},
            )
            
            collector_logger.error_with_details(
                "파일 다운로드 실패",
                stage="download",
                details={
                    "file": "TDoc_List_Meeting_RAN#100.xlsx",
                    "error_type": "ConnectionError",
                    "retry_count": 3,
                },
            )
            
            collector_logger.log_collection_result(
                file_name="TDoc_List_Meeting_RAN#100.xlsx",
                success=False,
                error_message="Connection refused",
                error_type="ConnectionError",
                retry_count=3,
            )
            
            # 로그 파일 검증
            log_file = Path(tmpdir) / "test_pipeline.log"
            with open(log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            assert len(lines) >= 3
            
            # 각 라인이 유효한 JSON인지 확인
            for line in lines:
                data = json.loads(line)
                assert "timestamp" in data
                assert "level" in data
                assert "module" in data
                assert "message" in data
