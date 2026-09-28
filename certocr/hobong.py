"""호봉 계산기용 다문서 OCR 라우팅과 JSON 변환.

외부 생성형 API를 사용하지 않는다. OCR 결과에서 확인되는 값만 채우고,
근거가 부족한 학력/경력 유형은 빈 값과 검토 사유로 반환한다.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from io import BytesIO
from pathlib import Path
import re
from typing import Iterable

import fitz
from PIL import Image, ImageSequence, UnidentifiedImageError
from rapidfuzz import fuzz

from certocr.career_rules import legal_snapshot as current_legal_snapshot, recommend_career
from certocr.extract.correct import normalize_date
from certocr.extract.structure import structure_lines
from certocr.ocr import OcrEngine
from certocr.preprocess import fallback_variants
from certocr.schema import OcrLine


MAX_DOCUMENT_BYTES = 50 * 1024 * 1024
MAX_PAGES = 30
PDF_DPI = 250


@dataclass
class PageExtraction:
    page: int
    document_type: str
    confidence: float
    fields: dict = field(default_factory=dict)
    review_reasons: list[str] = field(default_factory=list)


@dataclass
class HobongExtraction:
    basic_info: dict
    careers: list[dict]
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


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value or "")


def _joined(lines: Iterable[OcrLine]) -> str:
    return "\n".join(x.text.strip() for x in lines if x.text.strip())


def _rows(lines: list[OcrLine]) -> list[list[OcrLine]]:
    if not lines:
        return []
    heights = sorted(max(1.0, x.bbox[3] - x.bbox[1]) for x in lines)
    tolerance = max(20.0, heights[len(heights) // 2] * 0.72)
    rows: list[list[OcrLine]] = []
    for line in sorted(lines, key=lambda x: ((x.bbox[1] + x.bbox[3]) / 2, x.bbox[0])):
        cy = (line.bbox[1] + line.bbox[3]) / 2
        if rows:
            previous = sum((x.bbox[1] + x.bbox[3]) / 2 for x in rows[-1]) / len(rows[-1])
            if abs(cy - previous) <= tolerance:
                rows[-1].append(line)
                continue
        rows.append([line])
    return [sorted(row, key=lambda x: x.bbox[0]) for row in rows]


def _row_texts(lines: list[OcrLine]) -> list[str]:
    return [" ".join(x.text for x in row) for row in _rows(lines)]


def classify_page(lines: list[OcrLine]) -> tuple[str, float]:
    text = _compact(_joined(lines))
    head = _compact(" ".join(x.text for x in lines[:12]))
    rules = (
        ("teacher_certificate", ("교원자격증", "교원자격층", "교원자격")),
        ("graduation_certificate", ("졸업증명서", "졸업증명")),
        ("degree_certificate", ("학위수여증명서", "학위증명서", "학위기")),
        ("career_certificate", ("경력증명서", "재직증명서", "경력사항")),
    )
    for kind, needles in rules:
        if any(n in text for n in needles):
            return kind, 0.99
    # 오래된 저화질 증명서는 제목 한두 글자가 흔히 틀린다.
    fuzzy_targets = {
        "teacher_certificate": "교원자격증",
        "graduation_certificate": "졸업증명서",
        "degree_certificate": "학위증명서",
        "career_certificate": "경력증명서",
    }
    best_kind, best_score = "unknown", 0
    for kind, target in fuzzy_targets.items():
        score = max((fuzz.partial_ratio(target, _compact(x.text)) for x in lines[:15]), default=0)
        if score > best_score:
            best_kind, best_score = kind, score
    if best_score >= 76:
        return best_kind, best_score / 100.0
    if "석사" in text or "박사" in text or ("학위" in head and "대학교" in text):
        return "degree_certificate", 0.82
    if len(re.findall(r"\d{4}[^\d]{0,6}\d{1,2}[^\d]{0,6}\d{1,2}", text)) >= 2 and re.search(r"교사|강사|근무", text):
        return "career_certificate", 0.72
    return "unknown", 0.35


def _date_from_labeled_row(lines: list[OcrLine], labels: tuple[str, ...]) -> str:
    compact_labels = tuple(_compact(x) for x in labels)
    rows = _row_texts(lines)
    for i, row in enumerate(rows):
        compact = _compact(row)
        if not any(label in compact for label in compact_labels):
            continue
        for candidate in (row, rows[i - 1] + " " + row if i else row, row + " " + rows[i + 1] if i + 1 < len(rows) else row):
            value = normalize_date(candidate)
            if value:
                return value
    return ""


def _institution(lines: list[OcrLine]) -> str:
    candidates: list[tuple[float, str]] = []
    for line in lines:
        compact = _compact(line.text)
        for match in re.finditer(r"([가-힣]{2,18}대학교)", compact):
            name = match.group(1)
            if name in ("본대학교", "대학교"):
                continue
            candidates.append((line.conf, name))
    if not candidates:
        return ""
    # 총장/직인이 붙은 하단 학교명은 반복되며 대체로 가장 정확하다.
    counts: dict[str, int] = {}
    for _, name in candidates:
        counts[name] = counts.get(name, 0) + 1
    return max(candidates, key=lambda item: (counts[item[1]], item[0], len(item[1])))[1]


def _clean_major(value: str) -> str:
    value = re.sub(r"^[\s:：/]+", "", value)
    value = re.split(r"(?:학위수여|학위등록|학위번호|위의사실|졸업년|수여학위)", value)[0]
    value = re.sub(r"\(심화과정\)$", "", value)
    return value.strip(" :-：")[:40]


def _major(lines: list[OcrLine], text: str) -> str:
    for row in _row_texts(lines):
        compact = _compact(row)
        match = re.search(r"(?:학과및전공|학과/전공|제1전공)[:：]?(.{2,45})", compact)
        if match:
            return _clean_major(match.group(1))
    compact = _compact(text)
    match = re.search(r"(?:교육학석사|문학석사|이학석사|공학석사|석사)\(([^()]{2,30})\)", compact)
    return _clean_major(match.group(1)) if match else ""


def _degree_name(text: str) -> tuple[str, str]:
    compact = _compact(text)
    # 학위기에는 발급자/대학원장의 기존 박사학위도 함께 적힌다. 본문에
    # 석사과정·석사학위가 명시되면 발급자 직함의 "박사"보다 우선한다.
    patterns = (
        ("master", r"([가-힣]{1,12}석사(?:\([^()]+\))?)"),
        ("doctor", r"([가-힣]{1,12}박사(?:\([^()]+\))?)"),
        ("bachelor", r"((?:문학|이학|공학|교육학|예술|체육학|의학|치의학|한의학|수의학|간호학|법학|행정학|경영학)사)"),
    )
    for level, pattern in patterns:
        match = re.search(pattern, compact)
        if match:
            return level, match.group(1)
    return "", ""


def extract_education_page(lines: list[OcrLine], page: int, kind: str, confidence: float) -> PageExtraction:
    text = _joined(lines)
    compact = _compact(text)
    institution = _institution(lines)
    division = ""
    if "교육대학원" in compact:
        division = "교육대학원"
    elif "사범대학" in compact or "사범대화" in compact:
        division = "사범대학"
    elif "교육대학" in compact and "교육대학원" not in compact:
        division = "교육대학"
    major = _major(lines, text)
    level, degree = _degree_name(text)
    admission = _date_from_labeled_row(lines, ("입학일자", "임학일자", "입학년월일"))
    graduation = _date_from_labeled_row(lines, ("졸업일자", "졸업년월일"))
    award = _date_from_labeled_row(lines, ("학위수여일자", "학위수여일", "학위를수여함"))

    edu_id = ""
    is_sabeom = False
    if level == "bachelor" or kind == "graduation_certificate":
        if division in ("사범대학", "교육대학"):
            edu_id, is_sabeom = "edu4", True
        elif re.search(r"의학사|치의학사|한의학사|수의학사", degree):
            edu_id = "uni6"
        elif "학점은행" in compact or "독학학위" in compact:
            edu_id = "credit4"
        elif "전문학사" in compact:
            edu_id = "col3" if re.search(r"3년|3년제", compact) else "col2"
        elif institution:
            edu_id = "uni4"
    display = " ".join(x for x in (institution, division, major) if x)
    fields = {
        "institution": institution,
        "division": division,
        "major": major,
        "degree_level": level,
        "degree": degree,
        "admission_date": admission,
        "graduation_date": graduation,
        "degree_award_date": award,
        "edu": edu_id,
        "eduText": display,
        "isSabeom": is_sabeom,
    }
    reasons: list[str] = []
    if not institution:
        reasons.append(f"{page}쪽 학교명 판독 필요")
    if kind == "graduation_certificate" and not edu_id:
        reasons.append(f"{page}쪽 학부 유형 판독 필요")
    if level in ("master", "doctor") and not admission:
        reasons.append(f"{page}쪽 대학원 입학일 미기재/판독불가: 수학경력 자동 생성 제외")
    return PageExtraction(page, kind, confidence, fields, reasons)


def extract_qualification_page(lines: list[OcrLine], page: int, confidence: float) -> PageExtraction:
    text = _joined(lines)
    compact = _compact(text)
    teacher_type = ""
    grade = ""
    match = re.search(r"(전문상담교사|사서교사|보건교사|영양교사|정교사)\(?([12])급", compact)
    if match:
        teacher_type, grade = match.groups()
    elif "준교사" in compact:
        teacher_type = "준교사"
    elif "실기교사" in compact:
        teacher_type = "실기교사"
    qual = teacher_type + grade + ("급" if grade else "") if teacher_type else ""
    subject = ""
    if match:
        tail = compact[match.end():]
        tail = tail.lstrip(")")
        known_subjects = (
            "국어", "수학", "영어", "사회", "과학", "체육", "음악", "미술",
            "도덕윤리", "윤리", "역사", "지리", "한문", "정보컴퓨터",
            "기술가정", "상업", "기계", "전자", "전기", "특수",
        )
        subject = next((name for name in known_subjects if tail.startswith(name)), "")
    is_special = "특수학교" in compact and bool(qual)
    reasons = [] if qual else [f"{page}쪽 교원자격 등급/종류 판독 필요"]
    return PageExtraction(page, "teacher_certificate", confidence, {
        "qual": qual,
        "subject": subject,
        "isSpecialCertificate": is_special,
    }, reasons)


def _career_type(org: str, position: str, weekly_hours: str, raw_text: str) -> tuple[str, str]:
    recommendation = recommend_career(org, position, weekly_hours, raw_text)
    return recommendation.suggested_type, recommendation.confidence


def extract_career_page(lines: list[OcrLine], page: int, confidence: float) -> tuple[PageExtraction, list[dict]]:
    result = structure_lines(lines)
    careers: list[dict] = []
    raw_text = _joined(lines)
    reasons: list[str] = []
    for i, record in enumerate(result.cert.records):
        context = raw_text if len(result.cert.records) == 1 else " ".join((record.org, record.position, record.employment_type))
        recommendation = recommend_career(record.org, record.position, record.weekly_hours, context)
        suggested, level = recommendation.suggested_type, recommendation.confidence
        required = [result.field_conf.get(f"records[{i}].{name}", 0.0) for name in ("org", "position", "start_date", "end_date")]
        if required and min(required) < 0.85:
            level = "low"
        careers.append({
            "content": " ".join(x for x in (record.org, record.position) if x),
            "organization": record.org,
            "position": record.position,
            "start": record.start_date,
            "end": record.end_date,
            "suggested_type": suggested,
            "auto_apply": recommendation.auto_apply,
            "weeklyHours": record.weekly_hours,
            "confidence": level,
            "source_page": page,
            "candidate_types": recommendation.candidate_types,
            "legal_basis": recommendation.legal_basis,
            "required_checks": recommendation.required_checks,
            "recommendation_reason": recommendation.reason,
            "recommendation_source": recommendation.source,
            "law_snapshot_date": recommendation.law_snapshot_date,
        })
        if not suggested or not recommendation.auto_apply:
            reasons.append(f"{page}쪽 경력 유형 확인 필요: {recommendation.reason or '법정 요건 근거 부족'}")
    if not careers:
        reasons.append(f"{page}쪽 경력행 판독 필요")
    fields = {"record_count": len(careers)}
    return PageExtraction(page, "career_certificate", confidence, fields, reasons), careers


def extract_page(lines: list[OcrLine], page: int) -> tuple[PageExtraction, list[dict]]:
    kind, confidence = classify_page(lines)
    if kind == "teacher_certificate":
        return extract_qualification_page(lines, page, confidence), []
    if kind in ("graduation_certificate", "degree_certificate"):
        return extract_education_page(lines, page, kind, confidence), []
    if kind == "career_certificate":
        return extract_career_page(lines, page, confidence)
    return PageExtraction(page, "unknown", confidence, {}, []), []


def _page_quality(page: PageExtraction) -> tuple[int, int, float]:
    populated = sum(bool(v) for v in page.fields.values())
    return (-len(page.review_reasons), populated, page.confidence)


def _extract_best(engine: OcrEngine, image: Image.Image, page_number: int) -> tuple[PageExtraction, list[dict]]:
    primary_lines = engine.recognize(image)
    best_page, best_careers = extract_page(primary_lines, page_number)
    needs_retry = (
        best_page.document_type == "unknown"
        or best_page.document_type == "teacher_certificate" and not best_page.fields.get("qual")
        or best_page.document_type == "graduation_certificate" and not best_page.fields.get("edu")
    )
    if needs_retry:
        for _, variant in fallback_variants(image):
            candidate, careers = extract_page(engine.recognize(variant), page_number)
            if _page_quality(candidate) > _page_quality(best_page):
                best_page, best_careers = candidate, careers
    return best_page, best_careers


def _iter_images(data: bytes, mime_type: str = ""):
    if len(data) > MAX_DOCUMENT_BYTES:
        raise ValueError("파일이 50MB 제한을 초과했습니다.")
    is_pdf = data.startswith(b"%PDF-") or "pdf" in (mime_type or "").lower()
    if is_pdf:
        try:
            document = fitz.open(stream=data, filetype="pdf")
        except Exception as exc:
            raise ValueError("PDF를 열 수 없습니다.") from exc
        if document.page_count > MAX_PAGES:
            document.close()
            raise ValueError(f"PDF는 최대 {MAX_PAGES}쪽까지 처리할 수 있습니다.")
        scale = PDF_DPI / 72.0
        try:
            for page in document:
                pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                yield Image.open(BytesIO(pixmap.tobytes("png"))).convert("RGB")
        finally:
            document.close()
        return
    try:
        source = Image.open(BytesIO(data))
        frames = list(ImageSequence.Iterator(source))
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("지원하지 않는 이미지 파일입니다.") from exc
    if len(frames) > MAX_PAGES:
        raise ValueError(f"이미지는 최대 {MAX_PAGES}프레임까지 처리할 수 있습니다.")
    for frame in frames:
        yield frame.convert("RGB")


def _qual_rank(value: str) -> int:
    if value.endswith("1급"):
        return 30
    if value.endswith("2급"):
        return 20
    if value:
        return 10
    return 0


def merge_pages(pages: list[PageExtraction], careers: list[dict]) -> HobongExtraction:
    qualifications = [p for p in pages if p.document_type == "teacher_certificate" and p.fields.get("qual")]
    qualification = max(qualifications, key=lambda p: _qual_rank(p.fields["qual"]), default=None)
    education = [p for p in pages if p.document_type in ("graduation_certificate", "degree_certificate")]
    # 같은 묶음의 자격증 교과가 명확하면 저화질 졸업증명서의 전공명 한 글자
    # 오인식만 제한적으로 보정한다(예: 카어교육과 -> 국어교육과).
    subject = qualification.fields.get("subject", "") if qualification else ""
    if subject:
        for page in education:
            major = page.fields.get("major", "")
            if major.endswith("교육과") and subject not in major and len(major) <= len(subject) + 4:
                page.fields["major"] = subject + "교육과"
            elif major and subject not in major and re.search(r"[가-힣]{2}교육$", major):
                page.fields["major"] = re.sub(r"[가-힣]{2}교육$", subject + "교육", major)
            page.fields["eduText"] = " ".join(x for x in (
                page.fields.get("institution"), page.fields.get("division"), page.fields.get("major")
            ) if x)
    undergraduate = [p for p in education if p.fields.get("edu")]
    undergrad = max(undergraduate, key=lambda p: (p.fields.get("edu") == "edu4", p.confidence), default=None)
    degree_rank = {"doctor": 3, "master": 2, "bachelor": 1, "": 0}
    display_page = max(
        (p for p in education if p.fields.get("eduText")),
        key=lambda p: (degree_rank.get(p.fields.get("degree_level", ""), 0), p.confidence),
        default=None,
    )
    review_reasons: list[str] = []
    for page in pages:
        review_reasons.extend(page.review_reasons)

    # 석·박사 학위가 있고 실제 입학일/학위수여일이 모두 확인된 경우만 수학경력을 만든다.
    for page in education:
        level = page.fields.get("degree_level")
        start = page.fields.get("admission_date")
        end = page.fields.get("degree_award_date") or page.fields.get("graduation_date")
        if level not in ("master", "doctor") or not (start and end):
            continue
        suggested = "ms10" if level == "master" else "ph10"
        content = " ".join(x for x in (page.fields.get("institution"), page.fields.get("division"), "수학") if x)
        recommendation = recommend_career(
            page.fields.get("institution", "") + " " + page.fields.get("division", ""),
            "수학" if level == "master" else "박사 수학",
            "",
            content,
        )
        careers.append({
            "content": content,
            "start": start,
            "end": end,
            "suggested_type": suggested,
            "weeklyHours": "",
            "confidence": "high" if page.confidence >= 0.9 else "mid",
            "source_page": page.page,
            "candidate_types": recommendation.candidate_types or [suggested],
            "legal_basis": recommendation.legal_basis,
            "required_checks": recommendation.required_checks,
            "recommendation_reason": recommendation.reason,
            "recommendation_source": recommendation.source,
            "law_snapshot_date": recommendation.law_snapshot_date,
        })
    if education and not undergrad:
        review_reasons.append("대학원 학위만 확인됨: 호봉 계산용 학부 최종학력 선택 필요")

    deduped: list[dict] = []
    seen = set()
    for career in careers:
        key = (career.get("content"), career.get("start"), career.get("end"), career.get("suggested_type"))
        if key not in seen:
            seen.add(key)
            deduped.append(career)
    review_reasons = list(dict.fromkeys(review_reasons))
    basic_info = {
        "qual": qualification.fields["qual"] if qualification else "",
        "edu": undergrad.fields["edu"] if undergrad else "",
        "eduText": display_page.fields["eduText"] if display_page else "",
        "isSabeom": bool(undergrad and undergrad.fields.get("isSabeom")),
        # 자격증 소지만으로 현재 특수교육 근무 대상 여부를 확정하지 않는다.
        "isSpecial": False,
    }
    return HobongExtraction(
        basic_info=basic_info,
        careers=deduped,
        documents=[asdict(page) for page in pages],
        review_required=bool(review_reasons),
        review_reasons=review_reasons,
    )


def analyze_bytes(data: bytes, mime_type: str = "", engine: OcrEngine | None = None) -> HobongExtraction:
    if not data:
        raise ValueError("빈 파일입니다.")
    ocr = engine or OcrEngine()
    pages: list[PageExtraction] = []
    careers: list[dict] = []
    for page_number, image in enumerate(_iter_images(data, mime_type), 1):
        page, page_careers = _extract_best(ocr, image, page_number)
        pages.append(page)
        careers.extend(page_careers)
    if not pages:
        raise ValueError("처리할 페이지가 없습니다.")
    result = merge_pages(pages, careers)
    result.engine = ocr.metadata
    return result


def analyze_file(path: str | Path, engine: OcrEngine | None = None) -> HobongExtraction:
    file_path = Path(path)
    mime = "application/pdf" if file_path.suffix.lower() == ".pdf" else "image/" + file_path.suffix.lower().lstrip(".")
    return analyze_bytes(file_path.read_bytes(), mime, engine)
