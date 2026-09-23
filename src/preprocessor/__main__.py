"""
Preprocessor Module CLI Entry Point

`python -m src.preprocessor` 형식으로 실행 가능하도록 하는 진입점.

Usage:
    python -m src.preprocessor
    python -m src.preprocessor --input data/interim/parsed.parquet --output data/interim/preprocessed.parquet
"""

import sys
from pathlib import Path

# 프로젝트 루트 경로 추가
PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    """Preprocessor 모듈 메인 함수.
    
    Returns:
        종료 코드 (0: 성공, 1: 실패)
    """
    import argparse
    from src.scheduler.entry_points import run_preprocess
    
    parser = argparse.ArgumentParser(
        prog="3gpp-preprocessor",
        description="TDoc 데이터 전처리 파이프라인을 실행합니다 (Stage 2-5).",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="상세 로그 출력",
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="입력 파일 경로 (기본값: data/interim/parsed_tdocs.parquet)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="출력 파일 경로 (기본값: data/interim/preprocessed_tdocs.parquet)",
    )
    parser.add_argument(
        "--membership",
        type=Path,
        help="ETSI 멤버십 파일 경로",
    )
    
    args = parser.parse_args()
    
    result = run_preprocess(
        input_path=args.input,
        output_path=args.output,
        membership_path=args.membership,
        verbose=args.verbose,
    )
    
    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
