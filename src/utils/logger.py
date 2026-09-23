"""
Logger Module

구조화된 JSON 로깅 포맷을 제공하는 로거 유틸리티.

요구사항:
- 1.5: 실패 원인과 파일 경로를 로그에 기록
- 1.7: 수집 파일명, 수집 일시, 성공/실패 여부를 이력 로그에 기록
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Union

# 기본 로그 디렉토리
DEFAULT_LOG_DIR = Path("logs")


class JsonFormatter(logging.Formatter):
    """JSON 형식의 로그 포맷터.
    
    로그 레코드를 구조화된 JSON 형식으로 변환한다.
    
    출력 포맷 예시:
    {
        "timestamp": "2025-01-15T10:30:00Z",
        "level": "ERROR",
        "module": "collector",
        "stage": "download",
        "message": "파일 다운로드 실패",
        "details": {
            "file": "TDoc_List_Meeting_RAN#100.xlsx",
            "error_type": "ConnectionError",
            "retry_count": 3
        }
    }
    """

    def __init__(
        self,
        include_timestamp: bool = True,
        include_exc_info: bool = True,
    ) -> None:
        """
        Args:
            include_timestamp: 타임스탬프 포함 여부
            include_exc_info: 예외 정보 포함 여부
        """
        super().__init__()
        self.include_timestamp = include_timestamp
        self.include_exc_info = include_exc_info

    def format(self, record: logging.LogRecord) -> str:
        """로그 레코드를 JSON 문자열로 변환.
        
        Args:
            record: 로그 레코드
            
        Returns:
            JSON 형식의 로그 문자열
        """
        log_data: Dict[str, Any] = {}

        # 타임스탬프 (ISO 8601 형식, UTC)
        if self.include_timestamp:
            log_data["timestamp"] = datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )

        # 기본 필드
        log_data["level"] = record.levelname
        log_data["module"] = record.name
        log_data["message"] = record.getMessage()

        # 추가 컨텍스트 필드 (LogRecord에 동적으로 추가된 속성)
        # stage: 파이프라인 단계 (collector, parser, preprocessor 등)
        if hasattr(record, "stage"):
            log_data["stage"] = record.stage

        # details: 상세 정보 딕셔너리 (파일명, 에러 타입, 재시도 횟수 등)
        if hasattr(record, "details"):
            log_data["details"] = record.details

        # 예외 정보 (있는 경우)
        if self.include_exc_info and record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, ensure_ascii=False)


class StructuredLoggerAdapter(logging.LoggerAdapter):
    """구조화된 로깅을 위한 어댑터.
    
    stage와 details를 쉽게 로그에 추가할 수 있도록 한다.
    """

    def process(
        self, msg: str, kwargs: Dict[str, Any]
    ) -> tuple[str, Dict[str, Any]]:
        """로그 메시지와 kwargs를 처리.
        
        extra 딕셔너리의 stage와 details를 LogRecord에 추가한다.
        """
        extra = kwargs.get("extra", {})
        
        # 어댑터에 설정된 기본 extra 값 병합
        if self.extra:
            for key, value in self.extra.items():
                if key not in extra:
                    extra[key] = value
        
        kwargs["extra"] = extra
        return msg, kwargs

    def log_with_details(
        self,
        level: int,
        msg: str,
        stage: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """stage와 details를 포함하여 로그 기록.
        
        Args:
            level: 로그 레벨
            msg: 로그 메시지
            stage: 파이프라인 단계 (예: 'download', 'parse', 'filter')
            details: 상세 정보 딕셔너리
            **kwargs: 추가 로깅 인자
        """
        extra = kwargs.pop("extra", {})
        
        if stage is not None:
            extra["stage"] = stage
        if details is not None:
            extra["details"] = details
            
        self.log(level, msg, extra=extra, **kwargs)

    def debug_with_details(
        self,
        msg: str,
        stage: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """DEBUG 레벨로 stage와 details를 포함하여 로그 기록."""
        self.log_with_details(logging.DEBUG, msg, stage, details, **kwargs)

    def info_with_details(
        self,
        msg: str,
        stage: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """INFO 레벨로 stage와 details를 포함하여 로그 기록."""
        self.log_with_details(logging.INFO, msg, stage, details, **kwargs)

    def warning_with_details(
        self,
        msg: str,
        stage: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """WARNING 레벨로 stage와 details를 포함하여 로그 기록."""
        self.log_with_details(logging.WARNING, msg, stage, details, **kwargs)

    def error_with_details(
        self,
        msg: str,
        stage: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """ERROR 레벨로 stage와 details를 포함하여 로그 기록."""
        self.log_with_details(logging.ERROR, msg, stage, details, **kwargs)

    def critical_with_details(
        self,
        msg: str,
        stage: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """CRITICAL 레벨로 stage와 details를 포함하여 로그 기록."""
        self.log_with_details(logging.CRITICAL, msg, stage, details, **kwargs)

    # 수집 이력 로깅 (요구사항 1.7)
    def log_collection_result(
        self,
        file_name: str,
        success: bool,
        error_message: Optional[str] = None,
        error_type: Optional[str] = None,
        retry_count: Optional[int] = None,
    ) -> None:
        """수집 결과를 이력 로그에 기록 (요구사항 1.7).
        
        Args:
            file_name: 수집 파일명
            success: 성공/실패 여부
            error_message: 실패 시 에러 메시지
            error_type: 실패 시 에러 타입
            retry_count: 재시도 횟수
        """
        details: Dict[str, Any] = {
            "file": file_name,
            "success": success,
            "collected_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        
        if error_message:
            details["error_message"] = error_message
        if error_type:
            details["error_type"] = error_type
        if retry_count is not None:
            details["retry_count"] = retry_count
        
        if success:
            self.info_with_details(
                f"파일 수집 성공: {file_name}",
                stage="collect",
                details=details,
            )
        else:
            # 요구사항 1.5: 실패 원인과 파일 경로를 로그에 기록
            self.error_with_details(
                f"파일 수집 실패: {file_name}",
                stage="collect",
                details=details,
            )


# 모듈 레벨 로거 캐시
_loggers: Dict[str, StructuredLoggerAdapter] = {}


def get_logger(
    module_name: str,
    default_stage: Optional[str] = None,
) -> StructuredLoggerAdapter:
    """모듈별 로거 생성 및 반환.
    
    이미 생성된 로거는 캐시에서 반환한다.
    
    Args:
        module_name: 모듈 이름 (예: 'collector', 'parser', 'preprocessor')
        default_stage: 기본 파이프라인 단계 (모든 로그에 자동 추가)
        
    Returns:
        구조화된 로깅을 지원하는 로거 어댑터
        
    Example:
        >>> logger = get_logger("collector", default_stage="download")
        >>> logger.info("다운로드 시작")
        >>> logger.error_with_details(
        ...     "파일 다운로드 실패",
        ...     stage="download",
        ...     details={
        ...         "file": "TDoc_List_Meeting_RAN#100.xlsx",
        ...         "error_type": "ConnectionError",
        ...         "retry_count": 3
        ...     }
        ... )
    """
    cache_key = f"{module_name}:{default_stage}"
    
    if cache_key not in _loggers:
        logger = logging.getLogger(module_name)
        
        extra: Dict[str, Any] = {}
        if default_stage:
            extra["stage"] = default_stage
            
        adapter = StructuredLoggerAdapter(logger, extra)
        _loggers[cache_key] = adapter
        
    return _loggers[cache_key]


def setup_logging(
    level: Union[int, str] = logging.INFO,
    log_dir: Optional[Union[str, Path]] = None,
    log_file: Optional[str] = None,
    console_output: bool = True,
    json_format: bool = True,
) -> None:
    """로깅 시스템 초기화.
    
    콘솔과 파일 핸들러를 설정하고, 포맷터를 적용한다.
    
    Args:
        level: 로그 레벨 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: 로그 파일 저장 디렉토리 (None이면 logs/)
        log_file: 로그 파일명 (None이면 pipeline_{date}.log)
        console_output: 콘솔 출력 여부
        json_format: JSON 포맷 사용 여부 (False면 기본 포맷)
        
    Example:
        >>> setup_logging(level=logging.DEBUG, console_output=True)
        >>> setup_logging(
        ...     level="INFO",
        ...     log_dir="logs",
        ...     log_file="collector.log",
        ...     json_format=True
        ... )
    """
    # 로그 레벨 변환
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)

    # 루트 로거 설정
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # 기존 핸들러 제거 (중복 방지)
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # 포맷터 선택
    if json_format:
        formatter: logging.Formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    # 콘솔 핸들러
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    # 파일 핸들러
    if log_dir is not None or log_file is not None:
        log_path = Path(log_dir) if log_dir else DEFAULT_LOG_DIR
        log_path.mkdir(parents=True, exist_ok=True)
        
        if log_file is None:
            log_file = f"pipeline_{datetime.now().strftime('%Y%m%d')}.log"
            
        file_path = log_path / log_file
        file_handler = logging.FileHandler(file_path, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)


def create_collection_history_logger(
    log_dir: Optional[Union[str, Path]] = None,
) -> StructuredLoggerAdapter:
    """수집 이력 전용 로거 생성 (요구사항 1.7).
    
    수집 이력을 별도 파일에 기록하기 위한 전용 로거.
    
    Args:
        log_dir: 로그 디렉토리 (None이면 logs/)
        
    Returns:
        수집 이력 전용 로거
    """
    logger = logging.getLogger("collection_history")
    logger.setLevel(logging.INFO)
    
    # 중복 핸들러 방지
    if logger.handlers:
        return StructuredLoggerAdapter(logger, {"stage": "collect"})
    
    log_path = Path(log_dir) if log_dir else DEFAULT_LOG_DIR
    log_path.mkdir(parents=True, exist_ok=True)
    
    history_file = log_path / "collection_history.jsonl"
    file_handler = logging.FileHandler(history_file, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(JsonFormatter())
    logger.addHandler(file_handler)
    
    return StructuredLoggerAdapter(logger, {"stage": "collect"})
