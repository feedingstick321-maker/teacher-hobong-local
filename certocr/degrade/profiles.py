"""팩스 열화 프로파일 파라미터.

모든 수치는 문서 단위로 rng가 뽑는 (min, max) 범위이거나 확률(0.0~1.0)이다.
degrade_fax()는 여기 있는 dict만 읽으므로, 실물 팩스 수신본과 비교해
이 파일의 값만 고치면 보정(calibration)이 된다.

좌표·크기 단위: 별도 표기가 없으면 "팩스 해상도로 다운샘플한 뒤"의 픽셀.
"""
from __future__ import annotations

from certocr import config

# synth 모듈이 렌더하는 기준 dpi (config.A4_200DPI = A4 @ 200dpi).
# 비대칭 리사이즈 배율 = fax_dpi / SOURCE_DPI (가로·세로 각각).
SOURCE_DPI = 200

# 공통 기본값 — 각 프로파일은 이걸 덮어써서 정의한다.
_BASE: dict = {
    # ---- 해상도 ----
    "fax_dpi": config.FAX_FINE_DPI,   # (가로 dpi, 세로 dpi)
    "passes": 1,                      # 파이프라인 통과 횟수 (refax=2)

    # ---- 광학 블러 (다운샘플 전, 200dpi 픽셀 기준 sigma) ----
    "blur_sigma": (0.4, 0.9),

    # ---- 이진화 ----
    # 문서마다: rng < dither_prob 이면 오차확산 디더링, 아니면 고정 임계값.
    "dither_prob": 0.45,
    "threshold_mean": 145.0,          # 0(검정)~255(흰색) 그레이 기준
    "threshold_jitter": 22.0,         # 임계값 = mean + uniform(-j, +j)

    # ---- 점 노이즈 (salt & pepper) ----
    "pepper": (0.0002, 0.0015),       # 흰 배경에 생기는 검은 점 밀도
    "salt": (0.0005, 0.0030),         # 글자가 뜯겨 나가는 흰 점 밀도

    # ---- 가로 줄무늬 (스캔라인 밴딩) ----
    "scanlines": (0, 3),              # 줄 개수
    "scanline_dark_prob": 0.5,        # 검은 줄일 확률 (아니면 흰 탈락 줄)
    "scanline_height": (1, 2),        # 줄 두께 px
    "scanline_fill": (0.55, 0.95),    # 줄 안에서 픽셀이 뒤집힐 확률(끊긴 줄 표현)

    # ---- 세로 밴드 탈락 (용지 이송 불량) ----
    "vband_prob": 0.15,               # 문서당 발생 확률
    "vband_count": (1, 1),
    "vband_width": (2, 6),
    "vband_drop": (0.5, 0.9),         # 밴드 안 검은 픽셀이 사라질 확률

    # ---- 가장자리 얼룩 ----
    "smudge_prob": 0.35,
    "smudge_count": (1, 3),
    "smudge_size": (0.010, 0.040),    # min(폭,높이) 대비 반지름 비율
    "smudge_density": (0.35, 0.80),   # 얼룩 안 검은 픽셀 비율
    "edge_bar_prob": 0.15,            # 좌/우 끝 검은 세로 띠 (헤드 오염)
    "edge_bar_width": (1, 3),

    # ---- 기하 왜곡 ----
    "max_rotation_deg": 0.7,          # 미세 기울기 (계약: ±0.7° 이내)
    "max_shift_px": 3,                # 평행이동 (팩스 해상도 px)

    # ---- 원래 크기로 업샘플 ----
    "upsample_nearest_prob": 0.6,     # 아니면 바이리니어 후 재이진화
}

PROFILES: dict[str, dict] = {
    # 고품질 수신 (204x196dpi). 열화가 가장 약하다.
    "fine": {
        **_BASE,
        "fax_dpi": config.FAX_FINE_DPI,
    },

    # 표준 모드 (204x98dpi) — 세로 해상도가 절반으로 떨어지는 게 핵심.
    "standard": {
        **_BASE,
        "fax_dpi": config.FAX_STANDARD_DPI,
        "blur_sigma": (0.5, 1.1),
        "dither_prob": 0.35,
    },

    # standard + 강한 노이즈 (더러운 원고대, 노후 기기).
    "dirty": {
        **_BASE,
        "fax_dpi": config.FAX_STANDARD_DPI,
        "blur_sigma": (0.7, 1.4),
        "dither_prob": 0.35,
        "threshold_jitter": 32.0,
        "pepper": (0.0020, 0.0080),
        "salt": (0.0030, 0.0120),
        "scanlines": (2, 7),
        "scanline_height": (1, 3),
        "scanline_fill": (0.65, 1.0),
        "vband_prob": 0.55,
        "vband_count": (1, 2),
        "vband_width": (3, 10),
        "smudge_prob": 0.85,
        "smudge_count": (2, 5),
        "smudge_size": (0.015, 0.055),
        "edge_bar_prob": 0.45,
    },

    # 재팩스 — 이미 팩스로 받은 문서를 다시 팩스로 보낸 경우.
    # standard 파이프라인을 2회 통과시킨다.
    "refax": {
        **_BASE,
        "fax_dpi": config.FAX_STANDARD_DPI,
        "passes": 2,
        "blur_sigma": (0.5, 1.1),
        "dither_prob": 0.35,
        "pepper": (0.0005, 0.0030),
        "salt": (0.0010, 0.0050),
        "scanlines": (1, 4),
        "vband_prob": 0.25,
        "smudge_prob": 0.50,
    },
}
