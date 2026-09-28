"""경로·폰트·상수 설정. 모든 모듈은 경로를 여기서만 가져온다."""
from __future__ import annotations

from pathlib import Path
import os
import sys

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
DATA = ROOT / "data"
DICTS = DATA / "dicts"
MODELS = DATA / "models"    # OCR ONNX 모델 캐시 (오프라인 동작용)
OUT = DATA / "out"

VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"

# Windows 기본 한글 폰트 — 레이아웃별로 섞어 쓴다
FONTS = {
    "malgun": r"C:\Windows\Fonts\malgun.ttf",        # 현대 서식 (나이스/정부24)
    "malgun_bold": r"C:\Windows\Fonts\malgunbd.ttf",
    "batang": r"C:\Windows\Fonts\batang.ttc",        # 구식 증명서
    "gulim": r"C:\Windows\Fonts\gulim.ttc",          # 90년대~2000년대 서식
    "hanbatang": r"C:\Windows\Fonts\HANBatang.TTF",  # 한자 포함 구식 문서
}

# 렌더링 기준: A4 @ 200dpi (팩스 수신 해상도에 맞춤, 픽셀 낭비 없음)
A4_200DPI = (1654, 2339)  # (width, height)

# 팩스 표준 해상도 (ITU-T T.4)
FAX_STANDARD_DPI = (204, 98)   # 가로 x 세로 — 세로가 절반인 게 표준 모드
FAX_FINE_DPI = (204, 196)

REVIEW_THRESHOLD = 0.85  # 필드 신뢰도가 이 미만이면 검토 큐로

OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen3.5:0.8b"  # 없으면 rule 기반으로 폴백

# GPU 0(RTX 3090)은 다른 작업이 사용 중이다. 이 프로젝트는 물리 GPU 1
# (RTX 5060 Ti)만 노출하고, 프로세스 안에서는 논리 device 0으로 사용한다.
GPU_INDEX = 1
GPU_NAME = "NVIDIA GeForce RTX 5060 Ti"
DEFAULT_OCR_DEVICE = "cpu"
OCR_DEVICE_ENV = "CERTOCR_DEVICE"


def ocr_device(value: str | None = None) -> str:
    """실행 장치. 학교 배포 기본값은 CPU이며 CUDA는 개발 검증용이다."""
    device = (value or os.environ.get(OCR_DEVICE_ENV, DEFAULT_OCR_DEVICE)).strip().lower()
    if device not in {"cpu", "cuda"}:
        raise ValueError(f"지원하지 않는 OCR 장치: {device} (cpu 또는 cuda)")
    return device


def configure_gpu_environment() -> None:
    """개발 검증용 CUDA 모드에서만 RTX 5060 Ti를 노출한다."""
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", str(GPU_INDEX))
