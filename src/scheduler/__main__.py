"""
Scheduler Module CLI Entry Point

`python -m src.scheduler` 형식으로 실행 가능하도록 하는 진입점.

Usage:
    python -m src.scheduler parse --verbose
    python -m src.scheduler preprocess
    python -m src.scheduler build --threshold 0
    python -m src.scheduler analyze --advanced
    python -m src.scheduler run-all --verbose
"""

import sys
from .entry_points import main

if __name__ == "__main__":
    sys.exit(main())
