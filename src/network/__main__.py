"""
Network Module CLI Entry Point

`python -m src.network` 형식으로 실행 가능하도록 하는 진입점.

Usage:
    python -m src.network
    python -m src.network --threshold 0 --tsg RAN --tsg SA
"""

import sys
from pathlib import Path

# 프로젝트 루트 경로 추가
PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    """Network 모듈 메인 함수.
    
    Returns:
        종료 코드 (0: 성공, 1: 실패)
    """
    import argparse
    from src.scheduler.entry_points import run_build
    
    parser = argparse.ArgumentParser(
        prog="3gpp-network",
        description="네트워크 Edge list를 생성합니다 (Stage 6).",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="상세 로그 출력",
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="입력 파일 경로 (기본값: data/interim/preprocessed_tdocs.parquet)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="출력 디렉토리 (기본값: data/processed/)",
    )
    parser.add_argument(
        "--tsg",
        action="append",
        dest="tsg_groups",
        help="분석할 TSG 그룹 (복수 지정 가능, 예: --tsg RAN --tsg SA)",
    )
    parser.add_argument(
        "--time-unit",
        action="append",
        dest="time_units",
        choices=["year", "release", "quarter"],
        help="시간 단위 (복수 지정 가능)",
    )
    parser.add_argument(
        "--threshold",
        action="append",
        type=int,
        dest="thresholds",
        help="Weight 임계값 (복수 지정 가능)",
    )
    
    args = parser.parse_args()
    
    result = run_build(
        input_path=args.input,
        output_dir=args.output_dir,
        tsg_groups=args.tsg_groups,
        time_units=args.time_units,
        thresholds=args.thresholds,
        verbose=args.verbose,
    )
    
    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
