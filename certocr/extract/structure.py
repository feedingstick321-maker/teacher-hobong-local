"""좌표와 키워드 기반 경력증명서 구조화."""
from __future__ import annotations

import re
from datetime import date, timedelta
from rapidfuzz import fuzz

from certocr import config
from certocr.schema import CareerCertificate, CareerRecord, ExtractionResult, OcrLine, UNREADABLE
from .correct import find_organizations, is_empty_marker, normalize_date, normalize_position, parse_duration, replace_hanja

DATE_RE = re.compile(r"(?<!\d)(\d{2,4}\s*[.,\-/년]\s*\d{1,2}\s*[.,\-/월]\s*\d{1,2}\s*일?\.?)")
NOISE_RE = re.compile(r"(?:FAX|\d{2}/\d{2}\s+20\d{2}|0001/0001|교부\s*(?:번호|기관|기)|접수\s*(?:번호|기관)|담당자|전화번호|진위확인)", re.I)


def _value_after(text: str, labels: tuple[str, ...]) -> str:
    for label in labels:
        m = re.search(re.escape(label) + r"[ \t]*[:：]?[ \t]*([^\n|]{1,50})", text)
        if m:
            value = m.group(1).strip()
            value = re.split(r"\s{2,}|성명|생년월일|주소|용도|발급", value)[0].strip()
            if not is_empty_marker(value):
                return value
    return ""


def _cluster(lines: list[OcrLine], tolerance: float = 24) -> list[list[OcrLine]]:
    rows: list[list[OcrLine]] = []
    for line in sorted(lines, key=lambda x: ((x.bbox[1]+x.bbox[3])/2, x.bbox[0])):
        cy = (line.bbox[1]+line.bbox[3])/2
        if rows and abs(cy - sum((x.bbox[1]+x.bbox[3])/2 for x in rows[-1])/len(rows[-1])) <= tolerance:
            rows[-1].append(line)
        else:
            rows.append([line])
    return [sorted(r, key=lambda x: x.bbox[0]) for r in rows]


def structure_lines(lines: list[OcrLine]) -> ExtractionResult:
    usable = [x for x in lines if x.text.strip() and not NOISE_RE.search(x.text)]
    joined = "\n".join(replace_hanja(x.text) for x in usable)
    flags: list[str] = []
    conf: dict[str, float] = {}
    name = _value_after(joined, ("성명", "이름"))
    birth_raw = _value_after(joined, ("생년월일",))
    birth = normalize_date(birth_raw) or (UNREADABLE if birth_raw else "")
    doc = _value_after(joined, ("발급번호", "문서번호"))
    purpose = _value_after(joined, ("용도",))
    if "제출용" in joined:
        purpose = "학교제출용" if "학교제출용" in joined else ("교육기관 제출용" if "교육기관 제출용" in joined else "제출용")

    issuer = ""
    for text in reversed(joined.splitlines()):
        if "학교장" in text or "교장" in text or "교육장" in text or "교육감" in text:
            issuer = re.sub(r"\s*(학교교장인|학교장인|교장인|학교교장|학교장|교육장|교육감|장)\s*$", "학교", text).strip()
            break
    issue_date = ""
    issue_scope = joined.split("위와 같이")[-1] if "위와 같이" in joined else joined
    for raw in reversed(DATE_RE.findall(issue_scope)):
        val = normalize_date(raw)
        if val:
            issue_date = val
            break
    if not issue_date:
        for raw in reversed(DATE_RE.findall(joined)):
            val = normalize_date(raw)
            if val:
                issue_date = val; break

    records: list[CareerRecord] = []
    record_sources: list[dict[str, bool | float]] = []
    pending: list[CareerRecord] = []
    for row in _cluster(usable):
        text = " ".join(replace_hanja(x.text) for x in row)
        if records and "계약" in text and ("예정" in text or "~" in text):
            continue
        dates = DATE_RE.findall(text)
        organizations = find_organizations(text)
        org_value = organizations[-1] if organizations else ""
        if len(dates) < 2 and not ("현재" in text and org_value):
            continue
        start = normalize_date(dates[0]) or ""
        end = normalize_date(dates[1]) if len(dates) > 1 else ("재직중" if "현재" in text else "")
        position = normalize_position(text)
        subj_match = re.search(r"(?:국어|수학|영어|과학|사회|체육|음악|미술|특수)", text)
        duration = ""
        if parse_duration(text) and len(dates) < 2:
            duration = text
        emp = "기간제교원" if "기간제" in text else ""
        nums = [x.text.strip() for x in row if x.text.strip().isdigit() and 1 <= int(x.text.strip()) <= 60]
        rec = CareerRecord(org_value, position, start, end or "", subj_match.group(0) if subj_match else "", employment_type=emp, weekly_hours=nums[-1] if nums else "", duration=duration)
        records.append(rec)
        record_sources.append({"row_conf": sum(x.conf for x in row)/len(row), "org_in_row": bool(org_value), "position_in_row": bool(position)})
        if not rec.position:
            pending.append(rec)
        elif pending:
            for p in pending:
                p.position = rec.position
                p.subject = rec.subject
            pending.clear()

    # 표의 병합 셀 또는 표 밖 머리말에만 직위/기관이 있는 실물 서식 보완.
    doc_position = ""
    doc_position = normalize_position(joined)
    if not issuer:
        candidates = []
        for text in joined.splitlines():
            candidates += find_organizations(text)
        if candidates:
            issuer = candidates[-1]
    if not records:
        seen_dates = []
        for raw in DATE_RE.findall(joined):
            value = normalize_date(raw)
            if value and value not in seen_dates and value != birth:
                seen_dates.append(value)
        if len(seen_dates) >= 2 and (doc_position or "입사일자" in joined or "퇴사일자" in joined):
            records.append(CareerRecord(issuer if issuer.endswith(("학교", "학원", "아카데미", "회사", "법인")) else "", doc_position, seen_dates[0], seen_dates[1]))
            record_sources.append({"row_conf": base_conf if 'base_conf' in locals() else 0.7, "org_in_row": False, "position_in_row": False})
    # 표 머리글의 병합 셀 값은 OCR에서 별도 줄로 잡히므로 문서 수준에서 전달한다.
    subjects = re.findall(r"(?<![가-힣])(?:국어|수학|영어|과학|사회|체육|음악|미술|특수)(?![가-힣])", joined)
    hours = re.findall(r"(?:총\s*)?\d+\s*시간(?:\s*\d+\s*분)?|일\s*근무\s*\d+\s*분", joined)
    duration_match = re.search(r"근무(?:년|연)한[ \t]*\n?[ \t]*([^\n]{1,24})", joined)
    duration_value = duration_match.group(1).strip() if duration_match else ""
    if duration_value and not parse_duration(duration_value) and "시간" not in duration_value:
        duration_value = ""
    for rec in records:
        if not rec.position and doc_position:
            rec.position = doc_position
        elif rec.position == "교사" and doc_position not in ("", "교사"):
            rec.position = doc_position
        if not rec.org and issuer.endswith(("학교", "학원", "아카데미", "회사", "법인")):
            rec.org = issuer
        elif rec.org and issuer.endswith(("학교", "학원", "아카데미")):
            similarity = max(fuzz.WRatio(rec.org, issuer), fuzz.partial_ratio(rec.org, issuer))
            if similarity >= 75:
                rec.org = issuer
        if not rec.subject and subjects:
            rec.subject = subjects[-1]
        if not rec.employment_type and re.search(r"기간제\s*(?:교사|교원)", joined):
            rec.employment_type = "기간제교원"
        if not rec.weekly_hours and hours:
            rec.weekly_hours = re.sub(r"\s+", "", hours[-1])
        if not rec.duration and duration_value:
            rec.duration = re.sub(r"\s+", "", duration_value)
        if not rec.days and "일수" in joined:
            dm = re.search(r"(?<!\d)(\d+\s*일)(?!\s*근무)", joined)
            if dm:
                rec.days = re.sub(r"\s+", "", dm.group(1))

    # 동일 문서의 연속 계약이 겹치면 OCR 종료일 오류로 보고 다음 시작일 전날로 보정한다.
    chronological = sorted((r for r in records if r.start_date), key=lambda r: r.start_date)
    for current, following in zip(chronological, chronological[1:]):
        try:
            end = date.fromisoformat(current.end_date)
            next_start = date.fromisoformat(following.start_date)
        except ValueError:
            continue
        if end >= next_start:
            current.end_date = (next_start - timedelta(days=1)).isoformat()
            flags.append("기간 중첩 OCR 보정")

    layout = "neis" if "계약제" in joined and "주당근무" in joined else ("variant" if "일수" in joined or "입사일자" in joined else "legacy")
    cert = CareerCertificate(name=name, birth_date=birth, records=records, issue_date=issue_date, issuer=issuer, purpose=purpose, doc_no=doc, layout=layout)
    base_conf = sum(x.conf for x in usable)/len(usable) if usable else 0.0
    for field, value in (("name", name), ("birth_date", birth), ("issue_date", issue_date), ("issuer", issuer), ("doc_no", doc)):
        conf[field] = base_conf if value and value != UNREADABLE else 0.0
        if not value or value == UNREADABLE:
            flags.append(f"판독불가:{field}")
    for i, rec in enumerate(records):
        source = record_sources[i] if i < len(record_sources) else {"row_conf": base_conf, "org_in_row": False, "position_in_row": False}
        for fld in ("org", "position", "start_date", "end_date"):
            value = getattr(rec, fld)
            field_conf = float(source.get("row_conf", base_conf)) if value else 0.0
            if fld == "org" and value and not source.get("org_in_row"): field_conf *= 0.92
            if fld == "position" and value and not source.get("position_in_row"): field_conf *= 0.90
            conf[f"records[{i}].{fld}"] = field_conf
            if not value:
                flags.append(f"누락:records[{i}].{fld}")
    if not records:
        flags.append("경력사항 미검출")
    return ExtractionResult(cert=cert, field_conf=conf, flags=list(dict.fromkeys(flags)), raw_lines=lines)
