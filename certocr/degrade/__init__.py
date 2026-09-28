"""degrade — 팩스 열화 시뮬레이터. 공개 API: degrade_fax, PROFILES."""
from certocr.degrade.fax import degrade_fax
from certocr.degrade.profiles import PROFILES, SOURCE_DPI

__all__ = ["degrade_fax", "PROFILES", "SOURCE_DPI"]
