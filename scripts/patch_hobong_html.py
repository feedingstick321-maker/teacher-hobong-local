"""기존 hobong.html을 로컬 OCR 응답까지 반영하도록 패치한다."""
from __future__ import annotations

import argparse
from pathlib import Path
import re


def patch_html(source: str) -> str:
    if "const OCR_API_BASE_URL" not in source:
        source = re.sub(
            r"(const API_BASE_URL\s*=\s*[^;]+;)",
            r"\1\nconst OCR_API_BASE_URL = window.location.protocol === 'file:' "
            r"? 'http://127.0.0.1:8765' : window.location.origin;",
            source,
            count=1,
        )
    source = source.replace(
        "fetch(API_BASE_URL + '/api/extract'",
        "fetch(OCR_API_BASE_URL + '/api/extract'",
    )
    marker = "if(data.basic_info.edu) state.edu = data.basic_info.edu;"
    addition = (
        marker
        + "\n           if(data.basic_info.eduText) "
        + "document.getElementById('eduText').value = data.basic_info.eduText;"
    )
    if addition not in source:
        source = source.replace(marker, addition, 1)
    source = source.replace(
        "AI 자동추출은 외부 API를 활용하므로",
        "자동추출은 이 PC의 CPU 로컬 엔진에서 처리됩니다. 따라서",
    )
    source = source.replace(
        "통합 문서를 파이썬 백엔드에서 정밀 분석 중입니다",
        "통합 문서를 CPU 로컬 엔진에서 정밀 분석 중입니다",
    )
    return source


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    target = args.out or args.source
    source = args.source.read_text(encoding="utf-8")
    patched = patch_html(source)
    if patched == source:
        print("변경할 항목이 없습니다.")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(patched, encoding="utf-8")
    print(target)


if __name__ == "__main__":
    main()
