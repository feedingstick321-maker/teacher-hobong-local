"""별지 제17호서식 호봉획정표 출력. PDF/Excel 모두 같은 표 구조를 쓴다."""
from __future__ import annotations

from html import escape
from io import BytesIO
from pathlib import Path

import xlsxwriter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Table, TableStyle

from certocr import config


TITLE = "호봉획정표"
CAPTION = "■ 교육공무원 인사기록 및 인사사무 처리 규칙 [별지 제17호서식]"
DETAIL_ROWS = 13
LEGAL_BASIS = (
    "법령 자료 확인 2026-09-26 · 공무원보수규정 제8조·별표 15·22~26 · "
    "교육부 예규 제97호 · 인사혁신처 예규 제220호"
)


def value(data: dict, key: str) -> str:
    item = data.get(key, "")
    return str(item if item is not None else "").strip()


def career_values(career: dict) -> tuple[str, ...]:
    def date(prefix: str) -> str:
        parts = [value(career, prefix + x) for x in ("Y", "M", "D")]
        return ".".join(part for part in parts if part)

    def period(prefix: str) -> str:
        return " ".join(f"{value(career, prefix + k)}{unit}" for k, unit in
                        (("Y", "년"), ("M", "월"), ("D", "일")) if value(career, prefix + k))

    rate = value(career, "rate")
    if rate and rate.replace(".", "", 1).isdigit():
        rate += "%"
    return (value(career, "start") or date("s"), value(career, "end") or date("e"),
            value(career, "content"), value(career, "rawPeriod"), rate,
            value(career, "convertedPeriod") or period("c"), value(career, "note"))


def summary_values(payload: dict) -> tuple[str, ...]:
    total = payload.get("total") or {}
    total_text = value(payload, "careerTotal") or " ".join(
        f"{value(total, key)}{unit}" for key, unit in (("Y", "년"), ("M", "월"), ("D", "일"))
        if value(total, key)
    )
    return (total_text, value(payload, "deductYears"), value(payload, "remain"),
            value(payload, "finalGrade"), value(payload, "requiredYears"))


def pages(payload: dict) -> list[list[dict]]:
    careers = payload.get("careers") or []
    if not isinstance(careers, list):
        raise ValueError("careers는 목록이어야 합니다.")
    return [careers[i:i + DETAIL_ROWS] for i in range(0, len(careers), DETAIL_ROWS)] or [[]]


def page_grid(payload: dict, careers: list[dict], last: bool):
    cells = [[""] * 12 for _ in range(26)]
    spans: list[tuple[int, int, int, int]] = []
    kinds: dict[tuple[int, int], str] = {}

    def put(r: int, c: int, r2: int, c2: int, text: str, kind: str = "cell") -> None:
        cells[r][c] = text
        kinds[r, c] = kind
        if (r, c) != (r2, c2):
            spans.append((r, c, r2, c2))

    put(0, 0, 0, 11, CAPTION, "caption")
    put(1, 0, 1, 11, TITLE, "title")
    put(2, 0, 2, 1, "소속", "header")
    put(2, 2, 2, 7, value(payload, "affiliation"))
    put(2, 8, 2, 9, "제청(내신) 직위(직급)", "header")
    put(2, 10, 2, 11, "현 직위(직급)", "header")
    put(3, 0, 3, 1, "성명", "header")
    put(3, 2, 3, 7, value(payload, "name"))
    put(3, 8, 3, 9, value(payload, "proposedPosition"))
    put(3, 10, 3, 11, value(payload, "position"))
    put(4, 0, 4, 1, "학력", "header")
    put(4, 2, 4, 4, value(payload, "edu"))
    put(4, 5, 4, 7, "현 호봉", "header")
    put(4, 8, 4, 11, value(payload, "grade"))
    put(5, 0, 5, 3, "경력기간", "header")
    put(5, 4, 6, 5, "경력 내용", "header")
    put(5, 6, 6, 7, "경력 연수", "header")
    put(5, 8, 6, 8, "환산율", "header")
    put(5, 9, 6, 10, "환산 연수", "header")
    put(5, 11, 6, 11, "비고", "header")
    put(6, 0, 6, 0, "부터", "header")
    put(6, 1, 6, 3, "까지", "header")
    for offset in range(DETAIL_ROWS):
        r = 7 + offset
        vals = career_values(careers[offset]) if offset < len(careers) else ("",) * 7
        for c, c2, text in ((0, 0, vals[0]), (1, 3, vals[1]), (4, 5, vals[2]),
                            (6, 7, vals[3]), (8, 8, vals[4]), (9, 10, vals[5]),
                            (11, 11, vals[6])):
            put(r, c, r, c2, text, "left" if c == 4 else "cell")
    put(20, 0, 20, 3, "")
    put(20, 4, 20, 5, "계", "header")
    put(20, 6, 20, 7, "")
    put(20, 8, 20, 8, "")
    put(20, 9, 20, 10, summary_values(payload)[0] if last else "", "header")
    put(20, 11, 20, 11, "")
    summary = summary_values(payload) if last else ("",) * 5
    for i, (c, c2, label) in enumerate((
        (0, 2, "환산 총경력 연수"), (3, 5, "공제 연수"), (6, 7, "남은 연수"),
        (8, 9, "사정 호봉"), (10, 11, "사정 호봉에 필요한 경력 연수"),
    )):
        put(21, c, 21, c2, label, "header")
        put(22, c, 22, c2, summary[i])
    signer = (f"작성자  직위(직급)  {value(payload, 'authorRank')}     "
              f"성명  {value(payload, 'author')}  (인)") if last else ""
    put(23, 0, 23, 7, signer, "left")
    put(23, 8, 24, 11, "")
    put(24, 0, 24, 7, "적용 근거: " + (value(payload, "legalBasis") or LEGAL_BASIS) if last else "", "note")
    put(25, 0, 25, 6, "")
    put(25, 7, 25, 11, "190mm×268mm (백상지 80g/㎡)", "note")
    return cells, spans, kinds


def build_xlsx(payload: dict) -> bytes:
    output = BytesIO()
    # OCR and user fields are document text, never executable spreadsheet input.
    workbook = xlsxwriter.Workbook(output, {"in_memory": True,
        "strings_to_formulas": False, "strings_to_urls": False})
    base = {"font_name": "맑은 고딕", "font_size": 8, "border": 1,
            "align": "center", "valign": "vcenter", "text_wrap": True}
    fmt = {
        "cell": workbook.add_format(base),
        "header": workbook.add_format({**base, "bold": True}),
        "left": workbook.add_format({**base, "align": "left"}),
        "caption": workbook.add_format({"font_name": "맑은 고딕", "font_size": 8, "align": "left"}),
        "title": workbook.add_format({"font_name": "맑은 고딕", "font_size": 18, "bold": True, "align": "center"}),
        "note": workbook.add_format({"font_name": "맑은 고딕", "font_size": 6,
                                     "font_color": "#555555", "align": "left", "text_wrap": True}),
    }
    page_list = pages(payload)
    for index, career_page in enumerate(page_list):
        sheet = workbook.add_worksheet(TITLE if index == 0 else f"{TITLE} {index + 1}")
        sheet.hide_gridlines(2)
        sheet.set_portrait()
        sheet.set_paper(9)
        sheet.fit_to_pages(1, 1)
        sheet.center_horizontally()
        sheet.set_margins(0.35, 0.35, 0.4, 0.4)
        sheet.print_area(0, 0, 25, 11)
        for col, width in enumerate((12, 4.5, 4.5, 4.5, 8.5, 8.5, 8, 8, 12, 8, 8, 12)):
            sheet.set_column(col, col, width)
        for row, height in enumerate((17, 30, 24, 24, 24, 23, 20) + (32,) * 13 + (22, 27, 31, 27, 24, 18)):
            sheet.set_row(row, height)
        cells, spans, kinds = page_grid(payload, career_page, index == len(page_list) - 1)
        covered = {(rr, cc) for r, c, r2, c2 in spans for rr in range(r, r2 + 1)
                   for cc in range(c, c2 + 1) if (rr, cc) != (r, c)}
        span_lookup = {(r, c): (r2, c2) for r, c, r2, c2 in spans}
        for r in range(26):
            for c in range(12):
                if (r, c) in covered:
                    continue
                style = fmt[kinds.get((r, c), "cell")]
                if (r, c) in span_lookup:
                    r2, c2 = span_lookup[r, c]
                    sheet.merge_range(r, c, r2, c2, cells[r][c], style)
                else:
                    sheet.write(r, c, cells[r][c], style)
    workbook.close()
    return output.getvalue()


def _register_fonts() -> tuple[str, str]:
    regular = Path(config.FONTS["malgun"])
    bold = Path(config.FONTS["malgun_bold"])
    if not regular.is_file() or not bold.is_file():
        raise RuntimeError("Windows 한글 글꼴(맑은 고딕)을 찾을 수 없습니다.")
    if "HobongKorean" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("HobongKorean", str(regular)))
    if "HobongKoreanBold" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("HobongKoreanBold", str(bold)))
    return "HobongKorean", "HobongKoreanBold"


def build_pdf(payload: dict) -> bytes:
    regular, bold = _register_fonts()
    styles = {
        "cell": ParagraphStyle("cell", fontName=regular, fontSize=7.2, leading=8.6, alignment=TA_CENTER),
        "header": ParagraphStyle("header", fontName=bold, fontSize=7.2, leading=8.6, alignment=TA_CENTER),
        "left": ParagraphStyle("left", fontName=regular, fontSize=7.2, leading=8.6, alignment=TA_LEFT),
        "caption": ParagraphStyle("caption", fontName=regular, fontSize=8, leading=9, alignment=TA_LEFT),
        "title": ParagraphStyle("title", fontName=bold, fontSize=17, leading=20, alignment=TA_CENTER),
        "note": ParagraphStyle("note", fontName=regular, fontSize=6, leading=7.5, alignment=TA_LEFT),
    }
    output = BytesIO()
    document = SimpleDocTemplate(output, pagesize=A4, leftMargin=10 * mm, rightMargin=10 * mm,
                                 topMargin=10 * mm, bottomMargin=10 * mm, title=TITLE)
    page_list = pages(payload)
    story = []
    for index, career_page in enumerate(page_list):
        if index:
            story.append(PageBreak())
        cells, spans, kinds = page_grid(payload, career_page, index == len(page_list) - 1)
        rows = [[Paragraph(escape(cells[r][c]), styles[kinds.get((r, c), "cell")])
                 for c in range(12)] for r in range(26)]
        table = Table(rows, colWidths=[x * mm for x in (25, 9, 8, 9, 15, 15, 15, 14, 26, 14, 14, 26)],
                      rowHeights=[x * mm for x in ((7, 12, 9, 9, 9, 9, 8) + (10,) * 13 + (9, 9, 10, 9, 8, 7))])
        table.setStyle(TableStyle([
            *(("SPAN", (c, r), (c2, r2)) for r, c, r2, c2 in spans),
            ("GRID", (0, 2), (-1, -1), 0.5, colors.black),
            ("BOX", (0, 2), (-1, -1), 1, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ]))
        story.append(table)
    document.build(story)
    return output.getvalue()
