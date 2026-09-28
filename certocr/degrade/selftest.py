"""degrade 모듈 자체 테스트.

실행: D:\\gge\\certocr> .venv\\Scripts\\python.exe -m certocr.degrade.selftest

테스트 이미지(한글 텍스트 + 1px 가로줄 교차 패턴 + 회색 그라데이션)를
4개 프로파일로 열화시켜 data/out/selftest_degrade/에 저장하고,
아래 항목을 수치로 검증한다:
  [A] 출력 크기 = 입력 크기, mode "L"
  [B] 이진화: 픽셀값이 {0, 255} 뿐인가 (중간톤 없음)
  [C] standard의 세로 해상도 저하: 1px 교차 줄 패턴의 행 전이 수가
      fine 대비 크게 감소하는가
  [D] 노이즈: dirty에서 빈 여백 영역에 검은 픽셀(점/줄무늬/얼룩)이 생기는가
  [E] 재현성: 같은 seed -> 완전히 같은 출력
  [F] refax: standard보다 더 뭉개지는가 (전경 픽셀 변화량 비교)
"""
from __future__ import annotations

import random
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from certocr import config
from certocr.degrade import degrade_fax, PROFILES

OUT_DIR = config.OUT / "selftest_degrade"

# 교차 줄 패턴 영역 (x0, y0, x1, y1) — 200dpi 기준 1px 검은 줄 / 1px 흰 줄
PATTERN_BOX = (200, 1500, 1100, 1600)
# 아무것도 그리지 않는 빈 여백 영역 (노이즈 검출용)
BLANK_BOX = (1200, 1700, 1550, 2200)


def make_test_image() -> Image.Image:
    w, h = config.A4_200DPI
    img = Image.new("L", (w, h), 255)
    d = ImageDraw.Draw(img)

    font_big = ImageFont.truetype(config.FONTS["malgun_bold"], 64)
    font_mid = ImageFont.truetype(config.FONTS["malgun"], 36)
    font_small = ImageFont.truetype(config.FONTS["malgun"], 20)

    d.text((560, 150), "경 력 증 명 서", font=font_big, fill=0)
    lines = [
        "성명: 홍길동          생년월일: 1975-03-02",
        "소속: 서울중앙초등학교     직위: 교사",
        "재직기간: 2003. 3. 1. ~ 2010. 2. 28.",
        "발급기관: 서울특별시교육청",
        "위 사실을 증명합니다. 2026년 7월 12일",
    ]
    y = 340
    for t in lines:
        d.text((220, y), t, font=font_mid, fill=0)
        y += 90

    # 표 테두리 흉내 (가로/세로 괘선)
    d.rectangle((200, 820, 1450, 1150), outline=0, width=2)
    for i in range(1, 4):
        d.line((200, 820 + i * 82, 1450, 820 + i * 82), fill=0, width=1)
    d.line((700, 820, 700, 1150), fill=0, width=1)
    d.text((230, 850), "국민학교  교사  담임  國民學校  敎師", font=font_mid, fill=0)
    d.text((230, 935), "작은 글씨 테스트: 문서번호 제2026-1234호 (팩스 열화 확인용)",
           font=font_small, fill=0)

    # [C]용: 1px 가로줄 교차 패턴 — 세로 해상도가 절반이 되면 뭉개져야 함
    x0, y0, x1, y1 = PATTERN_BOX
    for yy in range(y0, y1, 2):
        d.line((x0, yy, x1, yy), fill=0, width=1)
    d.text((x0, y1 + 10), "위: 1px 간격 가로줄 패턴 (세로 해상도 테스트)",
           font=font_small, fill=0)

    # [B]용: 회색 그라데이션 바 — 이진화 후 중간톤이 없어야 함
    gx0, gy0, gx1, gy1 = 200, 1950, 1100, 2020
    for xx in range(gx0, gx1):
        v = int(255 * (xx - gx0) / (gx1 - gx0))
        d.line((xx, gy0, xx, gy1), fill=v, width=1)
    d.text((gx0, gy1 + 10), "위: 그레이 그라데이션 (이진화 테스트)",
           font=font_small, fill=0)
    return img


def row_transitions(arr: np.ndarray, box: tuple[int, int, int, int]) -> int:
    """box 안에서 '어두운 행' 프로파일의 0<->1 전이 횟수 (세로 해상도 지표)."""
    x0, y0, x1, y1 = box
    region = arr[y0:y1, x0:x1]
    dark_rows = (region.mean(axis=1) < 128).astype(np.int8)
    return int(np.abs(np.diff(dark_rows)).sum())


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    src = make_test_image()
    src.save(OUT_DIR / "clean.png")
    src_arr = np.asarray(src)

    results: dict[str, np.ndarray] = {}
    ok = True

    def check(cond: bool, label: str, detail: str = "") -> None:
        nonlocal ok
        mark = "PASS" if cond else "FAIL"
        print(f"[{mark}] {label}" + (f" — {detail}" if detail else ""))
        ok = ok and cond

    for name in ("fine", "standard", "dirty", "refax"):
        out = degrade_fax(src, name, random.Random(42))
        out.save(OUT_DIR / f"{name}.png")
        arr = np.asarray(out)
        results[name] = arr

        check(out.size == src.size and out.mode == "L",
              f"[A] {name}: size/mode", f"{out.size} mode={out.mode}")
        vals = np.unique(arr)
        check(set(vals.tolist()) <= {0, 255},
              f"[B] {name}: 이진화(중간톤 없음)", f"unique={vals.tolist()[:8]}")

    # [C] 세로 해상도: 교차 줄 패턴의 행 전이 수
    t_clean = row_transitions(src_arr, PATTERN_BOX)
    t_fine = row_transitions(results["fine"], PATTERN_BOX)
    t_std = row_transitions(results["standard"], PATTERN_BOX)
    check(t_std < t_fine * 0.5,
          "[C] standard 세로 해상도 저하",
          f"행 전이 clean={t_clean} fine={t_fine} standard={t_std}")

    # [D] 노이즈: dirty의 빈 여백에 검은 픽셀 존재 (여러 seed 평균으로 확인)
    bx0, by0, bx1, by1 = BLANK_BOX
    dirty_black = int((results["dirty"][by0:by1, bx0:bx1] == 0).sum())
    clean_black = int((src_arr[by0:by1, bx0:bx1] == 0).sum())
    check(clean_black == 0 and dirty_black > 30,
          "[D] dirty 여백 노이즈(점/줄무늬/얼룩)",
          f"clean={clean_black}px -> dirty={dirty_black}px")

    # [E] 재현성
    a = np.asarray(degrade_fax(src, "dirty", random.Random(7)))
    b = np.asarray(degrade_fax(src, "dirty", random.Random(7)))
    c = np.asarray(degrade_fax(src, "dirty", random.Random(8)))
    check(np.array_equal(a, b), "[E] 같은 seed -> 같은 출력")
    check(not np.array_equal(a, c), "[E] 다른 seed -> 다른 출력")

    # [F] refax가 standard보다 원본에서 더 멀어지는가 (여러 seed 평균)
    def mean_diff(profile: str) -> float:
        diffs = []
        ref = np.asarray(src.convert("L")) < 128
        for s in (1, 2, 3):
            deg = np.asarray(degrade_fax(src, profile, random.Random(s))) < 128
            diffs.append(float(np.logical_xor(ref, deg).mean()))
        return sum(diffs) / len(diffs)

    d_std, d_refax = mean_diff("standard"), mean_diff("refax")
    check(d_refax > d_std, "[F] refax > standard 열화량",
          f"픽셀 불일치율 standard={d_std:.4f} refax={d_refax:.4f}")

    # 육안 확인용 크롭 저장 (텍스트 영역 + 패턴 영역)
    text_box = (200, 320, 1250, 760)
    for name in ("clean", "fine", "standard", "dirty", "refax"):
        arr = src_arr if name == "clean" else results[name]
        Image.fromarray(arr[text_box[1]:text_box[3], text_box[0]:text_box[2]]).save(
            OUT_DIR / f"crop_text_{name}.png")
        px0, py0, px1, py1 = PATTERN_BOX
        Image.fromarray(arr[py0 - 10:py1 + 60, px0:px0 + 700]).save(
            OUT_DIR / f"crop_pattern_{name}.png")

    print(f"\n출력 위치: {OUT_DIR}")
    print("전체 결과:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
