"""선택적 로컬 Ollama 보조 훅. 실패 시 규칙 결과를 보존한다."""
from __future__ import annotations

import json
from urllib.error import URLError
from urllib.request import Request, urlopen

from certocr import config
from certocr.schema import ExtractionResult


def refine(result: ExtractionResult, timeout: float = 1.0) -> ExtractionResult:
    try:
        with urlopen(config.OLLAMA_URL + "/api/tags", timeout=timeout) as response:
            if response.status != 200:
                return result
    except (OSError, URLError, TimeoutError):
        return result
    # 개인정보를 포함한 원문을 자동 전송하지 않는다. 현재 훅은 설치 여부만 확인하며
    # 명시적인 로컬 보조 프롬프트 설계 전까지 규칙 결과를 그대로 반환한다.
    return result
