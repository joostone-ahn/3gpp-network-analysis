"""
Collector Module CLI Entry Point

`python -m src.collector` 형식으로 실행 가능하도록 하는 진입점.

Usage:
    python -m src.collector
    python -m src.collector --help
"""

import sys
from pathlib import Path

# 프로젝트 루트 경로 추가
PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.collector.ftp_collector import collect_tdoc_files
from src.utils.logger import get_logger

logger = get_logger(__name__)


def main() -> int:
    """Collector 모듈 메인 함수.
    
    Returns:
        종료 코드 (0: 성공, 1: 실패)
    """
    import argparse
    
    parser = argparse.ArgumentParser(
        prog="3gpp-collector",
        description="3GPP FTP 서버에서 TDoc List xlsx 파일을 수집합니다.",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="상세 로그 출력",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="collector.yaml 설정 파일 경로",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="다운로드 파일 저장 디렉토리 (기본값: data/raw/)",
    )
    
    args = parser.parse_args()
    
    try:
        logger.info("FTP Collector 시작")
        report = collect_tdoc_files()
        
        if report.failed_downloads:
            logger.warning(
                f"수집 완료 (일부 실패): "
                f"{report.successful_downloads}/{report.total_files} 파일 성공, "
                f"{report.failed_downloads} 파일 실패"
            )
            return 1
        else:
            logger.info(
                f"수집 완료: {report.successful_downloads}/{report.total_files} 파일 성공"
            )
            return 0
            
    except Exception as e:
        logger.error(f"수집 실패: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
