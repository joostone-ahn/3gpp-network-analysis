"""
Dashboard Error Handler Component (Task 14.5)

에러 처리 및 빈 데이터 처리를 위한 컴포넌트.

Requirements: 13.6
- 데이터 없음 시 친절한 안내 메시지 표시
- 파일 로드 오류 처리
- 네트워크 빈 상태 (노드/엣지 없음) 처리
- 유용한 제안 메시지 제공 (예: '분석 파이프라인을 먼저 실행하세요')

Implementation Notes:
- 모든 에러 메시지는 한국어로 제공
- 사용자에게 친절하고 명확한 안내 제공
- 문제 해결을 위한 구체적인 제안 포함
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import streamlit as st

from src.utils.logger import get_logger

# 모듈 로거
logger = get_logger("dashboard", default_stage="error_handler")


class ErrorType(Enum):
    """에러 유형 열거형."""
    NO_DATA = "no_data"                      # 데이터 없음
    FILE_NOT_FOUND = "file_not_found"        # 파일을 찾을 수 없음
    FILE_LOAD_ERROR = "file_load_error"      # 파일 로드 실패
    EMPTY_NETWORK = "empty_network"          # 빈 네트워크
    EMPTY_DATAFRAME = "empty_dataframe"      # 빈 DataFrame
    INVALID_SELECTION = "invalid_selection"  # 잘못된 선택 조건
    CONFIG_ERROR = "config_error"            # 설정 오류
    PIPELINE_NOT_RUN = "pipeline_not_run"    # 파이프라인 미실행
    PERMISSION_ERROR = "permission_error"    # 권한 오류
    UNKNOWN_ERROR = "unknown_error"          # 알 수 없는 오류


@dataclass
class ErrorContext:
    """에러 컨텍스트 정보.
    
    Attributes:
        error_type: 에러 유형
        message: 사용자에게 표시할 메시지
        details: 상세 정보 (선택적)
        suggestions: 문제 해결을 위한 제안 목록
        technical_info: 기술적 정보 (디버깅용, 선택적)
    """
    error_type: ErrorType
    message: str
    details: Optional[str] = None
    suggestions: Optional[List[str]] = None
    technical_info: Optional[str] = None


# 에러 유형별 기본 메시지 및 제안
ERROR_MESSAGES = {
    ErrorType.NO_DATA: {
        "icon": "📭",
        "title": "데이터가 없습니다",
        "default_message": "선택한 조건에 해당하는 데이터가 없습니다.",
        "suggestions": [
            "분석 파이프라인을 먼저 실행하세요: `python -m src.scheduler`",
            "다른 필터 조건을 선택해 보세요.",
            "데이터 수집 상태를 확인하세요: `data/raw/` 폴더",
        ],
    },
    ErrorType.FILE_NOT_FOUND: {
        "icon": "📁",
        "title": "파일을 찾을 수 없습니다",
        "default_message": "요청한 데이터 파일이 존재하지 않습니다.",
        "suggestions": [
            "분석 파이프라인을 실행하여 결과 파일을 생성하세요.",
            "파일 경로가 올바른지 확인하세요.",
            "`data/processed/` 및 `data/results/` 폴더를 확인하세요.",
        ],
    },
    ErrorType.FILE_LOAD_ERROR: {
        "icon": "⚠️",
        "title": "파일 로드 오류",
        "default_message": "데이터 파일을 읽는 중 오류가 발생했습니다.",
        "suggestions": [
            "파일이 손상되지 않았는지 확인하세요.",
            "파이프라인을 다시 실행하여 파일을 재생성하세요.",
            "디스크 공간이 충분한지 확인하세요.",
        ],
    },
    ErrorType.EMPTY_NETWORK: {
        "icon": "🕸️",
        "title": "빈 네트워크",
        "default_message": "네트워크에 노드 또는 엣지가 없습니다.",
        "suggestions": [
            "Edge Weight 임계값(Threshold)을 낮춰 보세요.",
            "더 넓은 시간 범위를 선택해 보세요.",
            "다른 TSG 그룹을 선택해 보세요.",
        ],
    },
    ErrorType.EMPTY_DATAFRAME: {
        "icon": "📋",
        "title": "데이터 없음",
        "default_message": "표시할 데이터가 없습니다.",
        "suggestions": [
            "필터 조건을 변경해 보세요.",
            "데이터 범위를 확대해 보세요.",
        ],
    },
    ErrorType.INVALID_SELECTION: {
        "icon": "❌",
        "title": "잘못된 선택",
        "default_message": "선택한 조건이 유효하지 않습니다.",
        "suggestions": [
            "사이드바에서 유효한 조건을 선택하세요.",
            "모든 필수 항목이 선택되었는지 확인하세요.",
        ],
    },
    ErrorType.CONFIG_ERROR: {
        "icon": "⚙️",
        "title": "설정 오류",
        "default_message": "설정 파일을 로드하는 중 오류가 발생했습니다.",
        "suggestions": [
            "`config/` 폴더의 YAML 파일이 올바른지 확인하세요.",
            "설정 파일의 문법 오류를 확인하세요.",
        ],
    },
    ErrorType.PIPELINE_NOT_RUN: {
        "icon": "🔄",
        "title": "파이프라인 미실행",
        "default_message": "분석 결과가 아직 생성되지 않았습니다.",
        "suggestions": [
            "분석 파이프라인을 실행하세요: `python -m src.scheduler`",
            "개별 모듈을 실행하세요: `python -m src.analyzer`",
            "README.md의 실행 방법을 참고하세요.",
        ],
    },
    ErrorType.PERMISSION_ERROR: {
        "icon": "🔒",
        "title": "권한 오류",
        "default_message": "파일에 접근할 권한이 없습니다.",
        "suggestions": [
            "파일 권한을 확인하세요.",
            "관리자 권한으로 실행해 보세요.",
        ],
    },
    ErrorType.UNKNOWN_ERROR: {
        "icon": "❓",
        "title": "알 수 없는 오류",
        "default_message": "예상치 못한 오류가 발생했습니다.",
        "suggestions": [
            "애플리케이션을 새로고침 해보세요.",
            "문제가 지속되면 로그 파일을 확인하세요.",
        ],
    },
}


def render_error_message(
    error_context: ErrorContext,
    show_suggestions: bool = True,
    show_technical_info: bool = False,
) -> None:
    """에러 메시지를 Streamlit에 렌더링.
    
    Args:
        error_context: 에러 컨텍스트 정보
        show_suggestions: 제안 메시지 표시 여부
        show_technical_info: 기술적 정보 표시 여부 (디버깅용)
    """
    error_info = ERROR_MESSAGES.get(error_context.error_type, ERROR_MESSAGES[ErrorType.UNKNOWN_ERROR])
    icon = error_info["icon"]
    title = error_info["title"]
    
    # 메시지 구성
    message = error_context.message or error_info["default_message"]
    
    # 경고 메시지 표시
    st.warning(f"{icon} **{title}**\n\n{message}")
    
    # 상세 정보 표시
    if error_context.details:
        st.info(f"📝 **상세 정보:** {error_context.details}")
    
    # 제안 메시지 표시
    if show_suggestions:
        suggestions = error_context.suggestions or error_info["suggestions"]
        if suggestions:
            st.markdown("**💡 해결 방법:**")
            for suggestion in suggestions:
                st.markdown(f"- {suggestion}")
    
    # 기술적 정보 (접기 가능)
    if show_technical_info and error_context.technical_info:
        with st.expander("🔧 기술적 정보 (개발자용)"):
            st.code(error_context.technical_info)


def render_no_data_message(
    tsg_group: Optional[str] = None,
    time_unit: Optional[str] = None,
    time_value: Optional[Union[int, str]] = None,
    threshold: Optional[int] = None,
    network_type: Optional[str] = None,
    data_type: str = "데이터",
    custom_suggestions: Optional[List[str]] = None,
) -> None:
    """데이터 없음 메시지를 사용자 친화적으로 표시.
    
    Args:
        tsg_group: TSG 그룹
        time_unit: 시간 단위
        time_value: 시간 값
        threshold: Edge Weight 임계값
        network_type: 네트워크 유형
        data_type: 데이터 유형 설명 (예: "Edge list", "중심성", "커뮤니티")
        custom_suggestions: 추가 제안 메시지
    """
    # 조건 정보 문자열 구성
    conditions = []
    if network_type:
        network_label = "기업 간 네트워크" if network_type == "company" else "WI 간 네트워크"
        conditions.append(f"네트워크 유형: {network_label}")
    if tsg_group:
        conditions.append(f"TSG 그룹: {tsg_group}")
    if time_unit:
        time_unit_label = {"year": "연도", "release": "Release", "quarter": "분기"}.get(time_unit, time_unit)
        conditions.append(f"시간 단위: {time_unit_label}")
    if time_value:
        conditions.append(f"시간 값: {time_value}")
    if threshold is not None:
        conditions.append(f"Threshold: {threshold}")
    
    details = None
    if conditions:
        details = "선택한 조건: " + ", ".join(conditions)
    
    suggestions = [
        "분석 파이프라인을 먼저 실행하세요.",
        "다른 필터 조건을 선택해 보세요.",
    ]
    
    if threshold is not None and threshold > 0:
        suggestions.insert(0, f"Edge Weight 임계값을 낮춰 보세요. (현재: {threshold})")
    
    if custom_suggestions:
        suggestions.extend(custom_suggestions)
    
    error_context = ErrorContext(
        error_type=ErrorType.NO_DATA,
        message=f"선택한 조건에 해당하는 {data_type}가 없습니다.",
        details=details,
        suggestions=suggestions,
    )
    
    render_error_message(error_context)


def render_empty_network_message(
    node_count: int = 0,
    edge_count: int = 0,
    threshold: Optional[int] = None,
) -> None:
    """빈 네트워크 메시지 표시.
    
    Args:
        node_count: 노드 수
        edge_count: Edge 수
        threshold: 현재 임계값
    """
    suggestions = [
        "Edge Weight 임계값(Threshold)을 낮춰 보세요.",
        "더 넓은 시간 범위를 선택해 보세요.",
        "다른 TSG 그룹을 선택해 보세요.",
    ]
    
    if threshold is not None and threshold > 0:
        suggestions.insert(0, f"현재 Threshold가 {threshold}입니다. 0으로 설정하면 모든 Edge를 볼 수 있습니다.")
    
    details = f"노드 수: {node_count}, Edge 수: {edge_count}"
    
    error_context = ErrorContext(
        error_type=ErrorType.EMPTY_NETWORK,
        message="네트워크가 비어 있어 시각화할 수 없습니다.",
        details=details,
        suggestions=suggestions,
    )
    
    render_error_message(error_context)


def render_file_error_message(
    file_path: Optional[Union[str, Path]] = None,
    error_type: ErrorType = ErrorType.FILE_LOAD_ERROR,
    original_error: Optional[Exception] = None,
) -> None:
    """파일 관련 에러 메시지 표시.
    
    Args:
        file_path: 파일 경로
        error_type: 에러 유형 (FILE_NOT_FOUND 또는 FILE_LOAD_ERROR)
        original_error: 원본 예외 객체
    """
    details = None
    if file_path:
        details = f"파일 경로: {file_path}"
    
    technical_info = None
    if original_error:
        technical_info = f"오류 유형: {type(original_error).__name__}\n오류 메시지: {str(original_error)}"
    
    error_context = ErrorContext(
        error_type=error_type,
        message=None,  # 기본 메시지 사용
        details=details,
        technical_info=technical_info,
    )
    
    render_error_message(error_context, show_technical_info=True)


def render_pipeline_not_run_message(
    missing_files: Optional[List[str]] = None,
) -> None:
    """파이프라인 미실행 메시지 표시.
    
    Args:
        missing_files: 누락된 파일 목록
    """
    details = None
    if missing_files:
        details = "누락된 파일: " + ", ".join(missing_files[:5])
        if len(missing_files) > 5:
            details += f" 외 {len(missing_files) - 5}개"
    
    suggestions = [
        "분석 파이프라인을 실행하세요:",
        "  ```bash",
        "  python -m src.scheduler",
        "  ```",
        "또는 개별 모듈을 순서대로 실행하세요:",
        "  1. `python -m src.collector` (데이터 수집)",
        "  2. `python -m src.parser` (데이터 파싱)",
        "  3. `python -m src.preprocessor` (전처리)",
        "  4. `python -m src.network` (네트워크 구성)",
        "  5. `python -m src.analyzer` (분석 실행)",
    ]
    
    error_context = ErrorContext(
        error_type=ErrorType.PIPELINE_NOT_RUN,
        message="분석 결과 파일이 존재하지 않습니다. 파이프라인을 먼저 실행해 주세요.",
        details=details,
        suggestions=suggestions,
    )
    
    render_error_message(error_context)


def render_data_loading_spinner(
    message: str = "데이터를 로드하는 중...",
) -> st.spinner:
    """데이터 로딩 스피너 반환.
    
    Args:
        message: 표시할 메시지
        
    Returns:
        Streamlit 스피너 컨텍스트 매니저
    """
    return st.spinner(f"⏳ {message}")


def check_data_availability(
    processed_dir: Optional[Path] = None,
    results_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """데이터 가용성 확인.
    
    Args:
        processed_dir: processed 디렉토리 경로
        results_dir: results 디렉토리 경로
        
    Returns:
        데이터 가용성 정보 딕셔너리
    """
    from src.utils.config_loader import PROJECT_ROOT
    
    if processed_dir is None:
        processed_dir = PROJECT_ROOT / "data" / "processed"
    if results_dir is None:
        results_dir = PROJECT_ROOT / "data" / "results"
    
    result = {
        "has_processed_data": False,
        "has_results_data": False,
        "processed_file_count": 0,
        "results_file_count": 0,
        "missing_directories": [],
    }
    
    # Processed 디렉토리 확인
    if processed_dir.exists():
        parquet_files = list(processed_dir.glob("*.parquet"))
        result["processed_file_count"] = len(parquet_files)
        result["has_processed_data"] = len(parquet_files) > 0
    else:
        result["missing_directories"].append(str(processed_dir))
    
    # Results 디렉토리 확인
    if results_dir.exists():
        parquet_files = list(results_dir.glob("*.parquet"))
        csv_files = list(results_dir.glob("*.csv"))
        result["results_file_count"] = len(parquet_files) + len(csv_files)
        result["has_results_data"] = (len(parquet_files) + len(csv_files)) > 0
    else:
        result["missing_directories"].append(str(results_dir))
    
    return result


def render_data_status_banner() -> bool:
    """데이터 상태 배너 표시.
    
    분석 결과 데이터가 없는 경우 안내 배너를 표시합니다.
    
    Returns:
        데이터가 사용 가능한 경우 True, 아니면 False
    """
    availability = check_data_availability()
    
    if not availability["has_processed_data"] and not availability["has_results_data"]:
        st.error("🚨 **분석 결과 데이터가 없습니다**")
        st.markdown("""
분석 파이프라인을 먼저 실행하여 데이터를 생성해 주세요.

**실행 방법:**
```bash
# 전체 파이프라인 실행
python -m src.scheduler

# 또는 개별 모듈 실행
python -m src.collector    # 데이터 수집
python -m src.parser       # 데이터 파싱
python -m src.preprocessor # 전처리
python -m src.network      # 네트워크 구성
python -m src.analyzer     # 분석 실행
```
        """)
        return False
    
    elif not availability["has_results_data"]:
        st.warning("⚠️ **분석 결과가 아직 생성되지 않았습니다**")
        st.markdown("""
네트워크 Edge list는 있지만 분석 결과가 없습니다.
분석 모듈을 실행해 주세요:

```bash
python -m src.analyzer
```
        """)
        return True  # Edge list는 있으므로 일부 기능 사용 가능
    
    return True


class ErrorHandler:
    """대시보드 에러 핸들러 클래스.
    
    대시보드 전체에서 일관된 에러 처리를 제공합니다.
    
    Example:
        >>> handler = ErrorHandler()
        >>> try:
        ...     data = load_data()
        >>> except FileNotFoundError as e:
        ...     handler.handle_exception(e, file_path=path)
    """
    
    def __init__(self, show_technical_info: bool = False):
        """ErrorHandler 초기화.
        
        Args:
            show_technical_info: 기술적 정보 표시 여부
        """
        self.show_technical_info = show_technical_info
    
    def handle_exception(
        self,
        exception: Exception,
        context: str = "데이터 로드",
        file_path: Optional[Union[str, Path]] = None,
        custom_message: Optional[str] = None,
        custom_suggestions: Optional[List[str]] = None,
    ) -> None:
        """예외를 처리하고 사용자 친화적인 메시지 표시.
        
        Args:
            exception: 발생한 예외
            context: 에러가 발생한 컨텍스트 설명
            file_path: 관련 파일 경로
            custom_message: 커스텀 메시지
            custom_suggestions: 커스텀 제안 목록
        """
        # 로깅
        logger.error(f"대시보드 에러 발생: {context}", exc_info=exception)
        
        # 예외 유형에 따른 에러 타입 결정
        error_type = ErrorType.UNKNOWN_ERROR
        
        if isinstance(exception, FileNotFoundError):
            error_type = ErrorType.FILE_NOT_FOUND
        elif isinstance(exception, PermissionError):
            error_type = ErrorType.PERMISSION_ERROR
        elif isinstance(exception, (IOError, OSError)):
            error_type = ErrorType.FILE_LOAD_ERROR
        
        # 메시지 구성
        message = custom_message or f"{context} 중 오류가 발생했습니다."
        
        details = None
        if file_path:
            details = f"파일: {file_path}"
        
        technical_info = f"예외 유형: {type(exception).__name__}\n메시지: {str(exception)}"
        
        error_context = ErrorContext(
            error_type=error_type,
            message=message,
            details=details,
            suggestions=custom_suggestions,
            technical_info=technical_info,
        )
        
        render_error_message(
            error_context,
            show_technical_info=self.show_technical_info,
        )
    
    def no_data(
        self,
        data_type: str = "데이터",
        **filter_kwargs,
    ) -> None:
        """데이터 없음 메시지 표시 헬퍼.
        
        Args:
            data_type: 데이터 유형 설명
            **filter_kwargs: 필터 조건 (tsg_group, time_unit 등)
        """
        render_no_data_message(data_type=data_type, **filter_kwargs)
    
    def empty_network(
        self,
        node_count: int = 0,
        edge_count: int = 0,
        threshold: Optional[int] = None,
    ) -> None:
        """빈 네트워크 메시지 표시 헬퍼.
        
        Args:
            node_count: 노드 수
            edge_count: Edge 수
            threshold: 현재 임계값
        """
        render_empty_network_message(node_count, edge_count, threshold)
    
    def file_error(
        self,
        file_path: Optional[Union[str, Path]] = None,
        error_type: ErrorType = ErrorType.FILE_LOAD_ERROR,
        original_error: Optional[Exception] = None,
    ) -> None:
        """파일 에러 메시지 표시 헬퍼.
        
        Args:
            file_path: 파일 경로
            error_type: 에러 유형
            original_error: 원본 예외
        """
        render_file_error_message(file_path, error_type, original_error)
    
    def pipeline_not_run(
        self,
        missing_files: Optional[List[str]] = None,
    ) -> None:
        """파이프라인 미실행 메시지 표시 헬퍼.
        
        Args:
            missing_files: 누락된 파일 목록
        """
        render_pipeline_not_run_message(missing_files)


# 기본 에러 핸들러 인스턴스
_default_handler: Optional[ErrorHandler] = None


def get_error_handler() -> ErrorHandler:
    """기본 ErrorHandler 인스턴스 반환 (싱글톤 패턴).
    
    Returns:
        ErrorHandler 인스턴스
    """
    global _default_handler
    if _default_handler is None:
        _default_handler = ErrorHandler()
    return _default_handler


__all__ = [
    # 에러 유형
    "ErrorType",
    "ErrorContext",
    # 렌더링 함수
    "render_error_message",
    "render_no_data_message",
    "render_empty_network_message",
    "render_file_error_message",
    "render_pipeline_not_run_message",
    "render_data_loading_spinner",
    "render_data_status_banner",
    # 유틸리티
    "check_data_availability",
    # 클래스
    "ErrorHandler",
    "get_error_handler",
    # 상수
    "ERROR_MESSAGES",
]
