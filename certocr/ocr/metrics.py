"""OCR 및 구조화 정확도 지표."""
from __future__ import annotations

from dataclasses import asdict
from typing import Iterable

from certocr.schema import CareerCertificate, OcrLine


def _distance(a: str, b: str) -> int:
    prev = list(range(len(b)+1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(cur[-1]+1, prev[j]+1, prev[j-1]+(ca != cb)))
        prev = cur
    return prev[-1]


def cer(ref: str, hyp: str) -> float:
    if not ref:
        return 0.0 if not hyp else 1.0
    return _distance(ref, hyp) / len(ref)


def _norm(text: str) -> str:
    return "".join(text.split())


def doc_cer(gt_lines: Iterable, ocr_lines: Iterable[OcrLine]) -> float:
    refs = [x[0] if isinstance(x, (tuple, list)) else str(x) for x in gt_lines]
    hyps = [x.text for x in sorted(ocr_lines, key=lambda z: (z.bbox[1], z.bbox[0]))]
    return cer(_norm("".join(refs)), _norm("".join(hyps)))


def field_accuracy(gt: CareerCertificate, pred: CareerCertificate) -> dict[str, bool]:
    ga, pa = asdict(gt), asdict(pred)
    result = {k: ga[k] == pa.get(k) for k in ga if k != "records"}
    result["records"] = ga["records"] == pa.get("records")
    return result
