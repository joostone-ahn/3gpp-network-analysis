"""
Parser Module CLI Entry Point

`python -m src.parser` 형식으로 실행 가능하도록 하는 진입점.

Usage:
    python -m src.parser
    python -m src.parser --raw-dir data/raw --output data/interim/parsed.parquet
"""

import sys
from pathlib import Path

# 프로젝트 루트 경로 추가
PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    """Parser 모듈 메인 함수.
    
    Returns:
        종료 코드 (0: 성공, 1: 실패)
    """
    import argparse
    from src.scheduler.entry_points import run_parse
    
    parser = argparse.ArgumentParser(
        prog="3gpp-parser",
        description="TDoc List xlsx 파일을 파싱합니다.",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="상세 로그 출력",
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        help="원본 xlsx 파일 디렉토리 (기본값: data/raw/)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="출력 파일 경로 (기본값: data/interim/parsed_tdocs.parquet)",
    )
    
    args = parser.parse_args()
    
    result = run_parse(
        raw_dir=args.raw_dir,
        output_path=args.output,
        verbose=args.verbose,
    )
    
    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
