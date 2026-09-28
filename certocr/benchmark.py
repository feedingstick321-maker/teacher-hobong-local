"""평가 산출물 fingerprint와 재현성 유틸리티."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from certocr import config

SCHEMA_VERSION = 2


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def code_sha256() -> str:
    digest = hashlib.sha256()
    paths = sorted((config.ROOT / "certocr").rglob("*.py")) + sorted((config.ROOT / "scripts").glob("*.py"))
    for path in paths:
        rel = path.relative_to(config.ROOT).as_posix().encode("utf-8")
        digest.update(len(rel).to_bytes(4, "big")); digest.update(rel)
        data = path.read_bytes(); digest.update(len(data).to_bytes(8, "big")); digest.update(data)
    return digest.hexdigest()


def current_manifest(labels: Path, folds: Path, image_count: int) -> dict:
    models = {}
    for name in ("ch_PP-OCRv5_det_mobile.onnx", "korean_PP-OCRv5_rec_mobile.onnx", "ppocrv5_korean_dict.txt"):
        path = config.MODELS / name
        models[name] = sha256_file(path) if path.is_file() else "MISSING"
    return {
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "gt_sha256": sha256_file(labels),
        "folds_sha256": sha256_file(folds),
        "code_sha256": code_sha256(),
        "models": models,
        "image_count": image_count,
        "gpu": {"physical_index": config.GPU_INDEX, "name": config.GPU_NAME},
    }


def write_manifest(path: Path, manifest: dict) -> None:
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def verify_manifest(saved: dict, current: dict) -> list[str]:
    mismatches = []
    for key in ("schema_version", "gt_sha256", "folds_sha256", "code_sha256", "models", "image_count", "gpu"):
        if saved.get(key) != current.get(key):
            mismatches.append(key)
    return mismatches
