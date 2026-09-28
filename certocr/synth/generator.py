"""실물 서식 특징을 반영한 합성 경력증명서 생성기."""
from __future__ import annotations

import random
from dataclasses import asdict
from datetime import date

from PIL import Image, ImageDraw, ImageFont

from certocr import config
from certocr.schema import CareerCertificate, CareerRecord, GroundTruth
from .corpus import OFFICES, make_records, person_name
from .stamp import draw_original_stamp, draw_seal

_ALIASES = {"gov24": "neis", "private": "variant", "legacy_hanja": "legacy"}
_LAYOUTS = {"neis", "legacy", "variant"}


def generate_certificate(rng: random.Random, layout: str | None = None) -> tuple[Image.Image, GroundTruth]:
    layout = _ALIASES.get(layout or "", layout) if layout else rng.choice(sorted(_LAYOUTS))
    if layout not in _LAYOUTS:
        raise ValueError(f"지원하지 않는 layout: {layout!r}; {sorted(_LAYOUTS | set(_ALIASES))}")
    w, h = config.A4_200DPI
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    regular = config.FONTS["malgun" if layout == "neis" else "batang"]
    bold = config.FONTS["malgun_bold"]
    fonts = {n: ImageFont.truetype(bold if n == "title" else regular, s) for n, s in {"title": 58, "head": 30, "body": 25, "small": 19}.items()}
    lines: list[tuple[str, tuple[float, float, float, float]]] = []

    def text(x: int, y: int, value: str, font: str = "body", anchor: str | None = None) -> None:
        d.text((x, y), value, font=fonts[font], fill="black", anchor=anchor)
        b = d.textbbox((x, y), value, font=fonts[font], anchor=anchor)
        lines.append((value, tuple(map(float, b))))

    name = person_name(rng)
    birth = date(rng.randint(1965, 1998), rng.randint(1, 12), rng.randint(1, 28)).isoformat()
    issuer = rng.choice(OFFICES) + " " + rng.choice(["가람초등학교", "푸른중학교", "한울고등학교"])
    raw_rows = make_records(rng, 1 if layout == "variant" else None)
    if layout == "variant":
        raw_rows[0].update(position="두드림학교 교과 학습 강사", days="4일 (일 근무 45분)", weekly_hours="45분")
    records = [CareerRecord(**r) for r in raw_rows]
    cert = CareerCertificate(name, birth, records, date.today().isoformat(), issuer, "경력 확인", f"J10000{rng.randint(1000,9999)}-{date.today().year}-{rng.randint(1,999999):06d}", layout)

    if rng.random() < .65:
        text(80, 35, f"{date.today():%m/%d %Y} 3:44 PM FAX 0310000000  0001/0001", "small")
    text(w//2, 150, "경 력 증 명 서", "title", "ma")
    text(150, 275, f"발급번호  {cert.doc_no}", "small")
    text(155, 345, f"성명  {name}")
    text(750, 345, f"생년월일  {birth.replace('-', '. ')}")
    text(155, 415, "주소  REDACTED", "body")

    x0, x1, y0 = 130, w-130, 520
    if layout == "neis":
        headers = ["근무기간(부터)", "근무기간(까지)", "계약제 구분", "정원임용 과목", "주당근무시간", "근무기관"]
        widths = [210, 210, 170, 175, 170, x1-x0-935]
    elif layout == "legacy":
        headers = ["근무기간(부터)", "근무기간(까지)", "직급", "직위", "근무부서"]
        widths = [220, 220, 210, 230, x1-x0-880]
    else:
        headers = ["근무기간", "일수", "직위", "근무기관"]
        widths = [300, 260, 430, x1-x0-990]
    row_h = 95
    d.rectangle((x0, y0, x1, y0 + row_h * (len(records)+1)), outline="black", width=2)
    xx = x0
    for i, (head, width) in enumerate(zip(headers, widths)):
        if i: d.line((xx, y0, xx, y0 + row_h*(len(records)+1)), fill="black", width=2)
        text(xx+8, y0+30, head, "small")
        xx += width
    for ri, rec in enumerate(records):
        yy = y0 + row_h*(ri+1)
        d.line((x0, yy, x1, yy), fill="black", width=1)
        if layout == "neis": vals = [rec.start_date, rec.end_date, rec.employment_type, rec.subject or "공란", rec.weekly_hours, rec.org]
        elif layout == "legacy": vals = [rec.start_date, rec.end_date, rec.employment_type, rec.position, "교무실"]
        else: vals = [f"{rec.start_date}~{rec.end_date}", rec.days, rec.position, rec.org]
        xx = x0
        for val, width in zip(vals, widths):
            text(xx+8, yy+30, val, "small")
            xx += width
    bottom = y0 + row_h*(len(records)+1)
    if layout == "legacy":
        text(150, bottom+65, f"근무연한  {records[-1].duration}     최종직위  {records[-1].position}")
        text(150, bottom+125, "상벌사항  해당없음     직위해제  해당없음")
    text(150, bottom+210, "용도  경력 확인")
    text(w//2, bottom+345, "위와 같이 증명합니다.", "head", "ma")
    text(w//2, bottom+430, cert.issue_date.replace("-", "년 ", 1).replace("-", "월 ") + "일", "body", "ma")
    text(w//2, bottom+515, issuer + "장", "head", "ma")
    draw_seal(img, (w//2+260, bottom+525), regular)
    if rng.random() < .55:
        draw_original_stamp(img, (rng.randint(80, 1100), rng.randint(900, 1700)), regular, rng.uniform(-8, 8))
    return img, GroundTruth(cert=cert, lines=lines, layout=layout)
