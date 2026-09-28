"""기존 호봉 획정 서식 전용 CPU OCR 구조화.

호봉획정표, 재획정표, 경력기간 합산신청서와 시간강사 경력 환산표는
같은 경력이 여러 쪽에 반복된다. 이 모듈은 페이지를 먼저 분류한 뒤
기간을 키로 병합하고, 사용자가 확인할 수 있는 검토용 행만 반환한다.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
import re
from typing import Iterable

from rapidfuzz import fuzz

from certocr.career_rules import legal_snapshot as current_legal_snapshot, recommend_career
from certocr.extract.correct import find_organizations, normalize_position
from certocr.hobong import _iter_images, _joined, _rows
from certocr.ocr import OcrEngine
from certocr.preprocess import fallback_variants
from certocr.schema import OcrLine


DOCUMENT_LABELS = {
    "salary_determination": "호봉획정표",
    "salary_redetermination": "호봉재획정표",
    "career_aggregation_application": "경력기간 합산신청서",
    "hourly_instructor_conversion": "시간강사 경력 환산표",
    "unknown_salary_form": "기존 호봉자료(서식 미확정)",
}

DATE_RE = re.compile(
    r"(?P<year>19\d{2}|20\d{2})\s*[.\-/년월|]+\s*"
    r"(?P<month>\d{1,2})\s*[.\-/년월|]+\s*(?P<day>\d{1,2})\s*일?"
)


@dataclass
class SalaryPage:
    page: int
    document_type: str
    label: str
    confidence: float
    row_count: int = 0
    fields: dict = field(default_factory=dict)
    review_reasons: list[str] = field(default_factory=list)


@dataclass
class SalaryExtraction:
    reference: dict
    rows: list[dict]
    documents: list[dict]
    review_required: bool
    review_reasons: list[str]
    legal_snapshot: dict = field(default_factory=current_legal_snapshot)
    engine: dict = field(default_factory=lambda: {
        "provider": "local-rapidocr",
        "execution_provider": "CPUExecutionProvider",
        "device": "cpu",
        "external_api_used": False,
    })

    def to_dict(self) -> dict:
        return asdict(self)


def _title_text(lines: Iterable[OcrLine]) -> str:
    return re.sub(r"[^가-힣A-Za-z0-9]", "", "".join(x.text for x in lines))


def classify_salary_page(lines: list[OcrLine]) -> tuple[str, float]:
    text = _title_text(lines)
    exact = (
        ("hourly_instructor_conversion", ("시간강사경력환산", "시간강사경력")),
        ("career_aggregation_application", ("호봉획정을위한경력기간합산신청서", "경력기간합산신청서", "경력기간합산")),
        ("salary_redetermination", ("호봉재획정표", "호봉재획정")),
        ("salary_determination", ("교육공무원호봉획정표", "호봉획정표", "호봉획정")),
    )
    for kind, needles in exact:
        if any(needle in text for needle in needles):
            return kind, 0.99

    targets = {
        "hourly_instructor_conversion": "시간강사경력환산",
        "career_aggregation_application": "경력기간합산신청서",
        "salary_redetermination": "호봉재획정표",
        "salary_determination": "호봉획정표",
    }
    title_candidates = [_title_text([line]) for line in lines[:20]] + [text[:120]]
    best_kind, best_score = "unknown_salary_form", 0.0
    for kind, target in targets.items():
        score = max((fuzz.partial_ratio(target, candidate) for candidate in title_candidates if candidate), default=0)
        if score > best_score:
            best_kind, best_score = kind, score
    if best_score >= 70:
        return best_kind, best_score / 100.0

    # 제목이 잘린 스캔도 표의 고유 열 이름으로 제한적으로 복구한다.
    if "기산호봉" in text and ("잔여" in text or "차기승급" in text):
        return "salary_determination", 0.76
    if "주당" in text and "인정" in text and "강사" in text:
        return "hourly_instructor_conversion", 0.74
    return "unknown_salary_form", 0.35


def extract_dates(text: str) -> list[tuple[str, int, int]]:
    """4자리 연도의 실제 날짜만 반환한다. 붙은 두 날짜도 각각 인식한다."""
    values: list[tuple[str, int, int]] = []
    for match in DATE_RE.finditer(text):
        try:
            value = date(
                int(match.group("year")),
                int(match.group("month")),
                int(match.group("day")),
            ).isoformat()
        except ValueError:
            continue
        values.append((value, match.start(), match.end()))
    return values


def _position(text: str) -> str:
    normalized = normalize_position(text)
    if normalized:
        return normalized
    compact = re.sub(r"\s+", "", text)
    for needle, value in (
        ("사원", "사원"),
        ("연구원", "연구원"),
        ("조교", "조교"),
        ("수학", "수학"),
    ):
        if needle in compact:
            return value
    return ""


def _organization(text: str) -> str:
    organizations = find_organizations(text)
    if organizations:
        # 날짜 앞의 신청서 행과 날짜 뒤의 획정표 행 모두 마지막 완성 기관명이 안정적이다.
        return max(organizations, key=lambda value: (len(value), value))
    compact = re.sub(r"\s+", "", text)
    match = re.search(r"([가-힣A-Za-z()]{2,24}(?:교육대학원|대학원))", compact)
    if match:
        return match.group(1)
    return ""


def _suggested_type(org: str, position: str, percent: int | None, weekly_hours: str) -> str:
    return recommend_career(org, position, weekly_hours, "", percent).suggested_type


def _row_candidate(row: list[OcrLine], page: int, kind: str) -> dict | None:
    text = " | ".join(line.text.strip() for line in row if line.text.strip())
    compact = re.sub(r"\s+", "", text)
    dates = extract_dates(compact)
    if len(dates) < 2:
        return None
    start, end = dates[0][0], dates[1][0]
    if start > end:
        return None
    if any(marker in compact for marker in ("차기승급", "잔여월수", "잔여기간", "경력총계", "인정경력총계")):
        return None

    org = _organization(text)
    position = _position(text)
    if kind == "hourly_instructor_conversion":
        position = "시간강사"
    if not position and org.endswith(("교육대학원", "대학원")):
        position = "수학"

    percent_match = re.search(r"(?<!\d)(\d{1,3})\s*%", text)
    percent = int(percent_match.group(1)) if percent_match else None
    weekly_hours = ""
    recognized_standard_hours = ""
    if kind == "hourly_instructor_conversion":
        tail = compact[dates[1][2]:]
        numbers = [int(value) for value in re.findall(r"(?<!\d)(\d{1,2})(?!\d)", tail)]
        standards = [value for value in numbers if value in (40, 42, 43, 44)]
        recognized_standard_hours = str(standards[0]) if standards else ""
        hours = [value for value in numbers if 1 <= value <= 39]
        weekly_hours = str(hours[0]) if hours else ""

    recommendation = recommend_career(org, position, weekly_hours, text, percent)
    suggested = recommendation.suggested_type
    row_conf = sum(line.conf for line in row) / len(row)
    reasons: list[str] = []
    if not org:
        reasons.append("근무기관 확인 필요")
    if not position:
        reasons.append("직종 확인 필요")
    if position == "시간강사" and not weekly_hours:
        reasons.append("주당 수업시수 확인 필요")
    if not suggested:
        reasons.append("경력 환산유형 확인 필요")
    if row_conf < 0.82:
        reasons.append("저신뢰도 OCR 행")
    return {
        "content": " ".join(value for value in (org, position) if value),
        "organization": org,
        "position": position,
        "start": start,
        "end": end,
        "suggested_type": suggested,
        "auto_apply": recommendation.auto_apply,
        "weeklyHours": weekly_hours,
        "recognized_standard_hours": recognized_standard_hours,
        "approved_rate_percent": percent,
        "confidence": "high" if row_conf >= 0.9 and not reasons else ("mid" if row_conf >= 0.78 else "low"),
        "source_page": page,
        "source_document_type": kind,
        "source_label": DOCUMENT_LABELS[kind],
        "status": "review" if reasons else "new",
        "review_reasons": reasons,
        "raw_text": text[:500],
        "candidate_types": recommendation.candidate_types,
        "legal_basis": recommendation.legal_basis,
        "required_checks": recommendation.required_checks,
        "recommendation_reason": recommendation.reason,
        "recommendation_source": recommendation.source,
        "law_snapshot_date": recommendation.law_snapshot_date,
    }


def extract_salary_rows(lines: list[OcrLine], page: int, kind: str) -> list[dict]:
    candidates: list[dict] = []
    for row in _rows(lines):
        candidate = _row_candidate(row, page, kind)
        if candidate:
            candidates.append(candidate)
    return candidates


def _duration_after(text: str, labels: tuple[str, ...]) -> str:
    compact = re.sub(r"\s+", "", text)
    for label in labels:
        match = re.search(re.escape(label) + r"[:：]?((?:\d+년)?(?:\d+월)?(?:\d+일)?)", compact)
        if match and match.group(1):
            return match.group(1)
    return ""


def extract_reference(lines: list[OcrLine], kind: str) -> dict:
    text = _joined(lines)
    compact = re.sub(r"\s+", "", text)
    reference: dict[str, str | int] = {}
    for row in _rows(lines):
        row_text = " ".join(line.text for line in row)
        row_compact = re.sub(r"\s+", "", row_text)
        if "소속" in row_compact:
            organizations = find_organizations(row_text)
            if organizations:
                reference["affiliation"] = organizations[0]
        if "직위" in row_compact or "직급" in row_compact:
            position = _position(row_text)
            if position:
                reference["position"] = position
        if "획정일" in row_compact or "재획정일" in row_compact:
            row_dates = extract_dates(row_compact)
            if row_dates:
                reference["determination_date"] = row_dates[0][0]
    qual = re.search(r"((?:정교사|전문상담교사|보건교사|사서교사)\(?[12]\)?급|준교사|실기교사)", compact)
    if qual:
        reference["qualification"] = qual.group(1).replace("(", "").replace(")", "")
    for key, labels in (
        ("career_total", ("경력합계", "경력총계")),
        ("converted_total", ("환산경력", "환산합계")),
        ("remaining_period", ("잔여월수", "잔여기간")),
    ):
        value = _duration_after(text, labels)
        if value:
            reference[key] = value
    step_patterns = (
        ("determined_step", ("획정호봉", "계산된호봉", "확정호봉")),
        ("base_step", ("기산호봉",)),
        ("prior_step", ("종전호봉", "재획정전호봉")),
    )
    for key, labels in step_patterns:
        for label in labels:
            match = re.search(re.escape(label) + r"[^0-9]{0,8}(\d{1,2})\s*호봉", compact)
            if match:
                reference[key] = int(match.group(1))
                break
    next_date = re.search(r"차기승급(?:일|예정일)?[^0-9]{0,10}((?:19|20)\d{2}[^가-힣]{1,8}\d{1,2}[^가-힣]{1,8}\d{1,2})", compact)
    if next_date:
        parsed = extract_dates(next_date.group(1))
        if parsed:
            reference["next_increment_date"] = parsed[0][0]
    reference["source_document_type"] = kind
    return reference


def _merge_row_values(target: dict, candidate: dict) -> None:
    for key in ("organization", "position", "weeklyHours", "recognized_standard_hours", "approved_rate_percent"):
        value = candidate.get(key)
        if value not in (None, "") and target.get(key) in (None, ""):
            target[key] = value
    # 시간강사 환산표의 시수는 유형 결정에 가장 직접적인 근거다.
    if candidate.get("source_document_type") == "hourly_instructor_conversion" and candidate.get("weeklyHours"):
        target["weeklyHours"] = candidate["weeklyHours"]
        recommendation = recommend_career(
            target.get("organization", ""), "시간강사", candidate["weeklyHours"], candidate.get("raw_text", "")
        )
        target["suggested_type"] = recommendation.suggested_type
        target["auto_apply"] = recommendation.auto_apply
        target["position"] = target.get("position") or "시간강사"
    if not target.get("suggested_type") and candidate.get("suggested_type"):
        target["suggested_type"] = candidate["suggested_type"]
        target["auto_apply"] = candidate.get("auto_apply", False)
    target.setdefault("source_pages", [target.get("source_page")])
    if candidate.get("source_page") not in target["source_pages"]:
        target["source_pages"].append(candidate.get("source_page"))
    target.setdefault("source_labels", [target.get("source_label")])
    if candidate.get("source_label") not in target["source_labels"]:
        target["source_labels"].append(candidate.get("source_label"))
    target["review_reasons"] = list(dict.fromkeys(target.get("review_reasons", []) + candidate.get("review_reasons", [])))


def merge_salary_rows(rows: list[dict]) -> list[dict]:
    merged: dict[tuple[str, str], dict] = {}
    for row in rows:
        key = (row["start"], row["end"])
        if key not in merged:
            merged[key] = dict(row)
            merged[key]["source_pages"] = [row["source_page"]]
            merged[key]["source_labels"] = [row["source_label"]]
            continue
        target = merged[key]
        old_org, new_org = target.get("organization", ""), row.get("organization", "")
        if old_org and new_org and old_org != new_org:
            target["review_reasons"] = list(dict.fromkeys(target.get("review_reasons", []) + ["같은 기간의 기관명이 문서마다 다름"]))
        _merge_row_values(target, row)

    result = []
    for row in sorted(merged.values(), key=lambda item: (item["start"], item["end"])):
        row["content"] = " ".join(value for value in (row.get("organization"), row.get("position")) if value)
        recommendation = recommend_career(
            row.get("organization", ""),
            row.get("position", ""),
            row.get("weeklyHours", ""),
            row.get("raw_text", ""),
            row.get("approved_rate_percent"),
        )
        row.update({
            "suggested_type": recommendation.suggested_type,
            "auto_apply": recommendation.auto_apply,
            "candidate_types": recommendation.candidate_types,
            "legal_basis": recommendation.legal_basis,
            "required_checks": recommendation.required_checks,
            "recommendation_reason": recommendation.reason,
            "recommendation_source": recommendation.source,
            "law_snapshot_date": recommendation.law_snapshot_date,
        })
        reasons = list(dict.fromkeys(row.get("review_reasons", [])))
        # 다른 쪽에서 보완된 누락 사유는 제거한다.
        if row.get("organization"):
            reasons = [value for value in reasons if value != "근무기관 확인 필요"]
        if row.get("position"):
            reasons = [value for value in reasons if value != "직종 확인 필요"]
        if row.get("position") == "시간강사" and row.get("weeklyHours"):
            reasons = [value for value in reasons if value != "주당 수업시수 확인 필요"]
        if row.get("suggested_type"):
            reasons = [value for value in reasons if value != "경력 환산유형 확인 필요"]
        row["review_reasons"] = reasons
        row["status"] = "review" if reasons else "new"
        result.append(row)
    return result


def merge_references(references: list[dict]) -> dict:
    if not references:
        return {}
    priority = {
        "salary_redetermination": 4,
        "salary_determination": 3,
        "career_aggregation_application": 2,
        "hourly_instructor_conversion": 1,
        "unknown_salary_form": 0,
    }
    result: dict = {}
    for reference in sorted(references, key=lambda value: priority.get(str(value.get("source_document_type")), 0), reverse=True):
        for key, value in reference.items():
            if value not in (None, "") and key not in result:
                result[key] = value
    return result


def _page_quality(page: SalaryPage, rows: list[dict]) -> tuple[int, int, float]:
    usable = sum(bool(row.get("organization") or row.get("weeklyHours")) for row in rows)
    return (page.document_type != "unknown_salary_form", usable, page.confidence)


def _extract_best(engine: OcrEngine, image, page_number: int) -> tuple[SalaryPage, list[dict], dict]:
    def build(lines: list[OcrLine]) -> tuple[SalaryPage, list[dict], dict]:
        kind, confidence = classify_salary_page(lines)
        rows = extract_salary_rows(lines, page_number, kind)
        reasons = []
        if kind == "unknown_salary_form":
            reasons.append(f"{page_number}쪽 서식 종류 확인 필요")
        if not rows and kind != "unknown_salary_form":
            reasons.append(f"{page_number}쪽 경력행 판독 필요")
        page = SalaryPage(
            page=page_number,
            document_type=kind,
            label=DOCUMENT_LABELS[kind],
            confidence=confidence,
            row_count=len(rows),
            fields={"detected_dates": len(extract_dates(re.sub(r"\s+", "", _joined(lines))))},
            review_reasons=reasons,
        )
        return page, rows, extract_reference(lines, kind)

    best = build(engine.recognize(image))
    if best[0].document_type == "unknown_salary_form" or not best[1]:
        for _, variant in fallback_variants(image):
            candidate = build(engine.recognize(variant))
            if _page_quality(candidate[0], candidate[1]) > _page_quality(best[0], best[1]):
                best = candidate
    return best


def analyze_salary_bytes(data: bytes, mime_type: str = "", engine: OcrEngine | None = None) -> SalaryExtraction:
    if not data:
        raise ValueError("빈 파일입니다.")
    ocr = engine or OcrEngine(device="cpu")
    pages: list[SalaryPage] = []
    rows: list[dict] = []
    references: list[dict] = []
    for page_number, image in enumerate(_iter_images(data, mime_type), 1):
        page, page_rows, reference = _extract_best(ocr, image, page_number)
        pages.append(page)
        rows.extend(page_rows)
        references.append(reference)
    if not pages:
        raise ValueError("처리할 페이지가 없습니다.")
    merged_rows = merge_salary_rows(rows)
    review_reasons = [reason for page in pages for reason in page.review_reasons]
    for row in merged_rows:
        review_reasons.extend(f"{row['start']}~{row['end']}: {reason}" for reason in row.get("review_reasons", []))
    if not merged_rows:
        review_reasons.append("가져올 수 있는 경력행을 찾지 못했습니다.")
    result = SalaryExtraction(
        reference=merge_references(references),
        rows=merged_rows,
        documents=[asdict(page) for page in pages],
        review_required=bool(review_reasons),
        review_reasons=list(dict.fromkeys(review_reasons)),
    )
    result.engine = ocr.metadata
    return result
