"""로컬 호봉 계산기 OCR API 실행. 기본 장치는 CPU."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from certocr import config


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    import uvicorn
    uvicorn.run("certocr.api:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
