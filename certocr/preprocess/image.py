"""원본을 보존하는 저화질 OCR fallback 변형."""
from __future__ import annotations

import cv2
import numpy as np
from PIL import Image


def image_features(img: Image.Image) -> dict[str, float]:
    gray = np.asarray(img.convert("L"), dtype=np.uint8)
    return {
        "contrast": float(gray.std()),
        "laplacian_var": float(cv2.Laplacian(gray, cv2.CV_64F).var()),
        "dark_ratio": float((gray < 180).mean()),
        "black_ratio": float((gray < 80).mean()),
    }


def fallback_variants(img: Image.Image) -> list[tuple[str, Image.Image]]:
    gray = np.asarray(img.convert("L"), dtype=np.uint8)
    clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(12, 12)).apply(gray)
    blur = cv2.GaussianBlur(clahe, (0, 0), 0.8)
    sharp = cv2.addWeighted(clahe, 1.7, blur, -0.7, 0)
    _, otsu = cv2.threshold(sharp, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    adaptive = cv2.adaptiveThreshold(
        clahe, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 41, 13
    )
    adaptive = cv2.morphologyEx(adaptive, cv2.MORPH_OPEN, np.ones((1, 2), np.uint8))
    return [
        ("clahe_otsu", Image.fromarray(otsu, mode="L").convert("RGB")),
        ("clahe_adaptive", Image.fromarray(adaptive, mode="L").convert("RGB")),
    ]
