"""
Analyzer Module CLI Entry Point

`python -m src.analyzer` 형식으로 실행 가능하도록 하는 진입점.

Usage:
    python -m src.analyzer
    python -m src.analyzer --advanced
"""

import sys
from pathlib import Path

# 프로젝트 루트 경로 추가
PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    """Analyzer 모듈 메인 함수.
    
    Returns:
        종료 코드 (0: 성공, 1: 실패)
    """
    import argparse
    from src.scheduler.entry_points import run_analyze
    
    parser = argparse.ArgumentParser(
        prog="3gpp-analyzer",
        description="네트워크 분석을 수행합니다 (Stage 7).",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="상세 로그 출력",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        help="Edge list 디렉토리 (기본값: data/processed/)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="분석 결과 디렉토리 (기본값: data/results/)",
    )
    parser.add_argument(
        "--advanced",
        action="store_true",
        dest="run_advanced",
        help="고급 분석 수행 (Power-law, Small-world 등)",
    )
    parser.add_argument(
        "--no-advanced",
        action="store_false",
        dest="run_advanced",
        help="고급 분석 건너뛰기",
    )
    parser.set_defaults(run_advanced=True)
    
    args = parser.parse_args()
    
    result = run_analyze(
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        run_advanced=args.run_advanced,
        verbose=args.verbose,
    )
    
    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
