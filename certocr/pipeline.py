"""경력증명서 이미지 OCR 통합 파이프라인."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from certocr.extract.llm import refine
from certocr.extract.structure import structure_lines
from certocr.ocr import OcrEngine
from certocr.preprocess import fallback_variants
from certocr.schema import ExtractionResult


@lru_cache(maxsize=1)
def _engine() -> OcrEngine:
    return OcrEngine()


def process(image_path: str | Path, use_llm: bool = False) -> ExtractionResult:
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(path)
    try:
        with Image.open(path) as source:
            img = source.convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError(f"지원하지 않거나 손상된 이미지: {path}") from exc
    engine = _engine()
    lines = engine.recognize(img)
    if not lines:
        result = structure_lines([])
        result.flags.insert(0, "OCR 텍스트 미검출")
    else:
        result = structure_lines(lines)
    # 날짜/직종 행 자체가 검출되지 않은 문서에만 비용이 큰 저화질 fallback 실행.
    if not result.cert.records or all(not r.start_date or not r.end_date for r in result.cert.records):
        candidates = [("primary", result)]
        for name, variant in fallback_variants(img):
            variant_lines = engine.recognize(variant)
            candidates.append((name, structure_lines(variant_lines)))
        name, result = max(candidates, key=lambda x: _record_score(x[1]))
        if name != "primary":
            result.flags.append(f"저화질 fallback 사용:{name}")
    return refine(result) if use_llm else result


def _record_score(result: ExtractionResult) -> tuple[int, int, float]:
    complete = sum(bool(r.start_date and r.end_date and r.position) for r in result.cert.records)
    populated = sum(bool(getattr(r, f)) for r in result.cert.records for f in ("start_date", "end_date", "org", "position"))
    confidence = sum(v for k, v in result.field_conf.items() if k.startswith("records["))
    return complete, populated, confidence
