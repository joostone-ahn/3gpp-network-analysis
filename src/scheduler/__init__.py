"""
Scheduler Module

APScheduler 기반 파이프라인 자동 스케줄링 및 CLI 엔트리포인트를 담당하는 모듈.

Requirements: 14.1, 14.2, 14.3, 14.4, 15.2
"""

# CLI Entry Points (Task 15.2)
from .entry_points import (
    # 스테이지별 실행 함수
    run_parse,
    run_preprocess,
    run_build,
    run_analyze,
    run_all,
    # 결과 Dataclasses
    StageResult,
    PipelineResult,
    # CLI
    create_parser,
    main,
)

# PipelineScheduler는 apscheduler 의존성이 필요하므로 조건부 임포트
try:
    from .pipeline_scheduler import PipelineScheduler
    _HAS_SCHEDULER = True
except ImportError:
    PipelineScheduler = None  # type: ignore
    _HAS_SCHEDULER = False


__all__ = [
    # Entry Points
    "run_parse",
    "run_preprocess",
    "run_build",
    "run_analyze",
    "run_all",
    # Results
    "StageResult",
    "PipelineResult",
    # CLI
    "create_parser",
    "main",
]

# PipelineScheduler가 사용 가능한 경우에만 export
if _HAS_SCHEDULER:
    __all__.append("PipelineScheduler")
