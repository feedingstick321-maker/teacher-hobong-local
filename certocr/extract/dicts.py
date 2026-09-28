"""UTF-8 줄 단위 사전 로더."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from certocr import config


@lru_cache
def load(name: str) -> tuple[str, ...]:
    path = config.DICTS / name
    if not path.is_file():
        return ()
    return tuple(x.strip() for x in path.read_text(encoding="utf-8").splitlines() if x.strip() and not x.startswith("#"))


@lru_cache
def hanja_map() -> dict[str, str]:
    out = {}
    for line in load("hanja_map.txt"):
        if "\t" in line:
            a, b = line.split("\t", 1)
            out[a] = b
    return out
