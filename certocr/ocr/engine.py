"""RapidOCR/PP-OCRv5 기반 CPU 기본 OCR 엔진."""
from __future__ import annotations

from pathlib import Path
import os
import sys

import numpy as np
from PIL import Image

from certocr import config
from certocr.schema import OcrLine

_DLL_HANDLES = []


def _configure_cuda_dlls() -> None:
    """pip으로 설치한 CUDA/cuDNN DLL의 지연 로딩 경로까지 등록한다."""
    root = Path(sys.prefix) / "Lib" / "site-packages" / "nvidia"
    dirs = [p / "bin" for p in root.iterdir()] if root.is_dir() else []
    valid = [str(p) for p in dirs if p.is_dir()]
    if valid:
        os.environ["PATH"] = os.pathsep.join(valid + [os.environ.get("PATH", "")])
        if hasattr(os, "add_dll_directory"):
            for path in valid:
                _DLL_HANDLES.append(os.add_dll_directory(path))


class OcrEngine:
    """로컬 모델만 사용한다. 기본은 CPU, CUDA는 개발 검증 옵션이다."""

    REQUIRED = (
        "ch_PP-OCRv5_det_mobile.onnx",
        "korean_PP-OCRv5_rec_mobile.onnx",
        "ppocrv5_korean_dict.txt",
    )

    def __init__(self, models_dir: Path = config.MODELS, device: str | None = None):
        self.models_dir = Path(models_dir)
        missing = [name for name in self.REQUIRED if not (self.models_dir / name).is_file()]
        if missing:
            raise FileNotFoundError(f"OCR 로컬 모델 누락: {', '.join(missing)} ({self.models_dir})")

        self.device = config.ocr_device(device)
        use_cuda = self.device == "cuda"
        if use_cuda:
            config.configure_gpu_environment()
            _configure_cuda_dlls()
        import onnxruntime as ort
        if use_cuda:
            ort.preload_dlls()
            if "CUDAExecutionProvider" not in ort.get_available_providers():
                raise RuntimeError("개발용 CUDA 모드를 사용할 수 없습니다. RTX 5060 Ti/CUDA 런타임을 확인하세요.")
        elif "CPUExecutionProvider" not in ort.get_available_providers():
            raise RuntimeError("CPUExecutionProvider를 사용할 수 없습니다. ONNX Runtime 설치를 확인하세요.")
        from rapidocr import RapidOCR
        params = {
            "Global.use_cls": False,
            "Global.log_level": "warning",
            "EngineConfig.onnxruntime.use_cuda": use_cuda,
            "EngineConfig.onnxruntime.intra_op_num_threads": max(1, min(4, os.cpu_count() or 1)),
            "Det.model_path": str(self.models_dir / self.REQUIRED[0]),
            "Rec.model_path": str(self.models_dir / self.REQUIRED[1]),
            "Rec.rec_keys_path": str(self.models_dir / self.REQUIRED[2]),
            "Det.ocr_version": _ocr_version("PP-OCRv5"),
            "Rec.ocr_version": _ocr_version("PP-OCRv5"),
            "Rec.lang_type": _rec_lang("korean"),
        }
        if use_cuda:
            params["EngineConfig.onnxruntime.cuda_ep_cfg.device_id"] = 0
        self._engine = RapidOCR(params=params)
        self.execution_provider = "CUDAExecutionProvider" if use_cuda else "CPUExecutionProvider"

    @property
    def metadata(self) -> dict:
        data = {
            "provider": "local-rapidocr",
            "execution_provider": self.execution_provider,
            "device": self.device,
            "external_api_used": False,
        }
        if self.device == "cuda":
            data["gpu"] = {"physical_index": config.GPU_INDEX, "name": config.GPU_NAME}
        return data

    def recognize(self, img: Image.Image) -> list[OcrLine]:
        arr = np.asarray(img.convert("RGB"))
        result = self._engine(arr, use_cls=False)
        if not result or result.boxes is None or result.txts is None:
            return []
        lines: list[OcrLine] = []
        for box, txt, score in zip(result.boxes, result.txts, result.scores):
            pts = np.asarray(box, dtype=float)
            lines.append(OcrLine(str(txt), (float(pts[:,0].min()), float(pts[:,1].min()), float(pts[:,0].max()), float(pts[:,1].max())), float(score)))
        return sorted(lines, key=lambda x: (((x.bbox[1]+x.bbox[3])/2)//12, x.bbox[0]))


def _ocr_version(value: str):
    from rapidocr.utils.typings import OCRVersion
    return OCRVersion(value)


def _rec_lang(value: str):
    from rapidocr.utils.typings import LangRec
    return LangRec(value)
