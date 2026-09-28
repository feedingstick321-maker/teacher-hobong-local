"""팩스 열화 시뮬레이터 (INTERFACES.md 계약 2번).

degrade_fax(img, profile, rng) -> 입력과 같은 크기의 열화 이미지 (mode "L", 값 {0,255}).

처리 순서 (프로파일당 passes 회 반복):
  그레이스케일 -> 광학 블러 -> 팩스 dpi 비율로 비대칭 다운샘플
  -> 이진화(오차확산 디더링 / 지터 임계값, 문서별 혼합)
  -> 노이즈(점, 가로 줄무늬, 세로 밴드 탈락, 가장자리 얼룩)
  -> 미세 회전(±0.7°)·평행이동 -> 원래 크기로 업샘플(최근접/바이리니어+재이진화)

모든 강도는 rng로 문서마다 달라진다. 파라미터는 profiles.PROFILES 참조.
"""
from __future__ import annotations

import random

import cv2
import numpy as np
from PIL import Image

from certocr.degrade.profiles import PROFILES, SOURCE_DPI

__all__ = ["degrade_fax", "PROFILES"]


def degrade_fax(img: Image.Image, profile: str, rng: random.Random) -> Image.Image:
    """img를 팩스 프로파일(fine/standard/dirty/refax)로 열화시켜 반환한다.

    반환 이미지는 입력과 같은 (width, height), mode "L", 픽셀값은 0 또는 255.
    """
    if profile not in PROFILES:
        raise ValueError(
            f"unknown fax profile: {profile!r} (choose from {sorted(PROFILES)})"
        )
    params = PROFILES[profile]

    arr = np.asarray(img.convert("L"), dtype=np.uint8)
    for _ in range(int(params["passes"])):
        arr = _single_pass(arr, params, rng)
    return Image.fromarray(arr, mode="L")


# ---------------------------------------------------------------- 내부 구현

def _u(rng: random.Random, lohi: tuple[float, float]) -> float:
    return rng.uniform(float(lohi[0]), float(lohi[1]))


def _ri(rng: random.Random, lohi: tuple[int, int]) -> int:
    return rng.randint(int(lohi[0]), int(lohi[1]))


def _single_pass(gray: np.ndarray, p: dict, rng: random.Random) -> np.ndarray:
    """그레이스케일(uint8, HxW) -> 같은 크기의 이진(0/255 uint8) 한 번 통과."""
    h, w = gray.shape
    # numpy 벡터 연산용 RNG — 문서 rng에서 시드를 뽑아 재현성 유지
    nrng = np.random.default_rng(rng.getrandbits(64))

    # 1) 광학 블러 (송신측 스캐너 흐림)
    sigma = _u(rng, p["blur_sigma"])
    if sigma > 0.05:
        gray = cv2.GaussianBlur(gray, (0, 0), sigmaX=sigma, sigmaY=sigma)

    # 2) 팩스 dpi 비율로 비대칭 다운샘플 (핵심: standard는 세로가 절반)
    dpi_x, dpi_y = p["fax_dpi"]
    fw = max(1, round(w * dpi_x / SOURCE_DPI))
    fh = max(1, round(h * dpi_y / SOURCE_DPI))
    small = cv2.resize(gray, (fw, fh), interpolation=cv2.INTER_AREA)

    # 3) 이진화 — 문서별로 오차확산 디더링 또는 고정 임계값, 임계값에 지터
    thr = p["threshold_mean"] + rng.uniform(-p["threshold_jitter"], p["threshold_jitter"])
    thr = float(np.clip(thr, 40.0, 215.0))
    if rng.random() < p["dither_prob"]:
        # PIL convert("1")은 Floyd-Steinberg 오차확산 (내부 임계값 128 고정)
        # -> 입력을 (128 - thr)만큼 밀어서 실질 임계값을 thr로 만든다.
        shifted = np.clip(small.astype(np.int16) + int(round(128 - thr)), 0, 255)
        dithered = Image.fromarray(shifted.astype(np.uint8), mode="L").convert("1")
        bw = np.where(np.asarray(dithered, dtype=bool), 255, 0).astype(np.uint8)
    else:
        bw = np.where(small > thr, 255, 0).astype(np.uint8)

    # 4) 노이즈
    bw = _salt_pepper(bw, p, rng, nrng)
    bw = _scanlines(bw, p, rng, nrng)
    bw = _vertical_band_dropout(bw, p, rng, nrng)
    bw = _edge_smudges(bw, p, rng, nrng)
    bw = _edge_bar(bw, p, rng, nrng)

    # 5) 미세 회전 + 평행이동 (배경은 흰색으로 채움)
    ang = rng.uniform(-p["max_rotation_deg"], p["max_rotation_deg"])
    ms = int(p["max_shift_px"])
    tx, ty = rng.uniform(-ms, ms), rng.uniform(-ms, ms)
    M = cv2.getRotationMatrix2D((fw / 2.0, fh / 2.0), ang, 1.0)
    M[0, 2] += tx
    M[1, 2] += ty
    bw = cv2.warpAffine(
        bw, M, (fw, fh), flags=cv2.INTER_NEAREST,
        borderMode=cv2.BORDER_CONSTANT, borderValue=255,
    )

    # 6) 원래 크기로 업샘플 — 이진 특성 유지
    if rng.random() < p["upsample_nearest_prob"]:
        up = cv2.resize(bw, (w, h), interpolation=cv2.INTER_NEAREST)
    else:
        up = cv2.resize(bw, (w, h), interpolation=cv2.INTER_LINEAR)
        up = np.where(up > 127, 255, 0).astype(np.uint8)
    return up


def _salt_pepper(bw: np.ndarray, p: dict, rng: random.Random,
                 nrng: np.random.Generator) -> np.ndarray:
    """검은 점(pepper: 배경 오염) + 흰 점(salt: 글자 뜯김)."""
    pepper = _u(rng, p["pepper"])
    salt = _u(rng, p["salt"])
    u = nrng.random(bw.shape)
    bw = bw.copy()
    bw[u < pepper] = 0
    bw[(u >= pepper) & (u < pepper + salt)] = 255
    return bw


def _scanlines(bw: np.ndarray, p: dict, rng: random.Random,
               nrng: np.random.Generator) -> np.ndarray:
    """가로 줄무늬 — 검은 스트릭 또는 흰 탈락 줄. 끊긴 줄로 표현."""
    n = _ri(rng, p["scanlines"])
    if n <= 0:
        return bw
    fh, fw = bw.shape
    bw = bw.copy()
    for _ in range(n):
        y = rng.randrange(fh)
        hgt = _ri(rng, p["scanline_height"])
        fill = _u(rng, p["scanline_fill"])
        rows = slice(y, min(y + hgt, fh))
        mask = nrng.random((rows.stop - rows.start, fw)) < fill
        if rng.random() < p["scanline_dark_prob"]:
            region = bw[rows]
            region[mask] = 0          # 검은 스트릭
        else:
            region = bw[rows]
            region[mask] = 255        # 흰 탈락 줄 (글자가 끊김)
        bw[rows] = region
    return bw


def _vertical_band_dropout(bw: np.ndarray, p: dict, rng: random.Random,
                           nrng: np.random.Generator) -> np.ndarray:
    """세로 밴드 탈락 — 용지 이송 불량으로 세로 띠의 내용이 사라짐."""
    if rng.random() >= p["vband_prob"]:
        return bw
    fh, fw = bw.shape
    bw = bw.copy()
    for _ in range(_ri(rng, p["vband_count"])):
        wdt = _ri(rng, p["vband_width"])
        x = rng.randrange(max(1, fw - wdt))
        drop = _u(rng, p["vband_drop"])
        band = bw[:, x:x + wdt]
        gone = (band == 0) & (nrng.random(band.shape) < drop)
        band[gone] = 255
        bw[:, x:x + wdt] = band
    return bw


def _edge_smudges(bw: np.ndarray, p: dict, rng: random.Random,
                  nrng: np.random.Generator) -> np.ndarray:
    """가장자리 얼룩 — 문서 테두리 근처의 거친 타원형 검은 얼룩."""
    if rng.random() >= p["smudge_prob"]:
        return bw
    fh, fw = bw.shape
    bw = bw.copy()
    margin = 0.08  # 가장자리에서 이 비율 안쪽까지만 중심을 둔다
    for _ in range(_ri(rng, p["smudge_count"])):
        side = rng.choice(("top", "bottom", "left", "right"))
        if side == "top":
            cx, cy = rng.uniform(0, fw), rng.uniform(0, fh * margin)
        elif side == "bottom":
            cx, cy = rng.uniform(0, fw), rng.uniform(fh * (1 - margin), fh)
        elif side == "left":
            cx, cy = rng.uniform(0, fw * margin), rng.uniform(0, fh)
        else:
            cx, cy = rng.uniform(fw * (1 - margin), fw), rng.uniform(0, fh)
        r = _u(rng, p["smudge_size"]) * min(fw, fh)
        axes = (max(1, int(r)), max(1, int(r * rng.uniform(0.5, 1.5))))
        blob = np.zeros_like(bw)
        cv2.ellipse(blob, (int(cx), int(cy)), axes,
                    rng.uniform(0, 180), 0, 360, 255, thickness=-1)
        density = _u(rng, p["smudge_density"])
        rough = nrng.random(bw.shape) < density
        bw[(blob == 255) & rough] = 0
    return bw


def _edge_bar(bw: np.ndarray, p: dict, rng: random.Random,
              nrng: np.random.Generator) -> np.ndarray:
    """좌/우 끝의 검은 세로 띠 (스캐너 헤드 오염·캘리브레이션 불량)."""
    if rng.random() >= p["edge_bar_prob"]:
        return bw
    fh, fw = bw.shape
    bw = bw.copy()
    wdt = _ri(rng, p["edge_bar_width"])
    cols = slice(0, wdt) if rng.random() < 0.5 else slice(fw - wdt, fw)
    mask = nrng.random((fh, wdt)) < rng.uniform(0.75, 1.0)
    region = bw[:, cols]
    region[mask] = 0
    bw[:, cols] = region
    return bw
