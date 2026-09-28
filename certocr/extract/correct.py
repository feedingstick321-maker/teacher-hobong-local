"""퍼지 사전 교정, 날짜와 기간 표준화."""
from __future__ import annotations

import re
from datetime import date

from rapidfuzz import fuzz, process

from .dicts import hanja_map, load

CURRENT = {"현재", "재직중", "재직 중", "현 재"}
EMPTY_MARKERS = {"이하여백", "-이하여백-", "해당없음", "-해당없음-", "공란"}

POSITION_PATTERNS = (
    (r"기간제\s*(?:교사|교원)", "기간제교원"),
    (r"(?<![가-힣])기간제(?![가-힣])", "기간제교원"),
    (r"시간\s*강사", "시간강사"),
    (r"두드림학교\s*교과\s*학습\s*강사", "교과학습강사"),
    (r"교과\s*학습\s*강사", "교과학습강사"),
    (r"기초\s*학력\s*강사", "기초학력강사"),
    (r"학원\s*강사", "학원강사"),
    (r"무기\s*계약\s*근로자", "무기계약근로자"),
    (r"계약직", "계약직"),
    (r"보건\s*교사", "보건교사"),
    (r"사서\s*교사", "사서교사"),
    (r"전문\s*상담\s*교사", "전문상담교사"),
    (r"(?<![가-힣])교사(?![가-힣])", "교사"),
)

ORG_RE = re.compile(
    r"(?:\(주\)|주식회사\s*)?[가-힣A-Za-z0-9()]+(?:초등학교|중학교|고등학교|교육지원청|교육청|학교|학원|아카데미|회사|법인)"
)


def replace_hanja(text: str) -> str:
    for src, dst in sorted(hanja_map().items(), key=lambda x: -len(x[0])):
        text = text.replace(src, dst)
    return text


def fuzzy_correct(text: str, dictionary: str, score_cutoff: int = 82) -> tuple[str, float]:
    choices = load(dictionary)
    if not text or not choices:
        return text, 0.0
    hit = process.extractOne(text.strip(), choices, scorer=fuzz.WRatio, score_cutoff=score_cutoff)
    return (hit[0], hit[1]/100.0) if hit else (text, 0.0)


def normalize_date(value: str, pivot_year: int = 50) -> str | None:
    raw = value.strip().rstrip(".")
    if raw in CURRENT:
        return "재직중"
    raw = re.sub(r"[년/\-.]+", " ", raw)
    raw = re.sub(r"월", " ", raw)
    raw = re.sub(r"일", "", raw)
    nums = re.findall(r"\d+", raw)
    if len(nums) < 3:
        return None
    y, m, d = map(int, nums[:3])
    if y < 100:
        y += 2000 if y < pivot_year else 1900
    if y < 1900 or y > 2100:
        return None
    try:
        return date(y, m, d).isoformat()
    except ValueError:
        return None


def parse_duration(value: str) -> dict[str, int] | None:
    """'1년 6월 7일', '12개월(1년)', '월 4일'을 날짜와 분리해 파싱."""
    s = value.replace("개월", "월").replace(" ", "")
    if not re.search(r"(?:년|월|일)", s):
        return None
    years = re.search(r"(\d+)년", s)
    months = re.search(r"(\d+)월", s)
    days = re.search(r"(\d+)일", s)
    if not any((years, months, days)):
        return None
    return {"years": int(years.group(1)) if years else 0, "months": int(months.group(1)) if months else 0, "days": int(days.group(1)) if days else 0}


def is_empty_marker(value: str) -> bool:
    return re.sub(r"\s", "", value) in {re.sub(r"\s", "", x) for x in EMPTY_MARKERS}


def normalize_position(text: str) -> str:
    compact = re.sub(r"\s+", "", text)
    if "두드림학교" in compact and "교과학습" in compact and "강사" in compact:
        return "교과학습강사"
    for pattern, canonical in POSITION_PATTERNS:
        if re.search(pattern, text):
            return canonical
    return ""


def find_organizations(text: str) -> list[str]:
    found = [re.sub(r"\s+", " ", x).strip() for x in ORG_RE.findall(text)]
    for name, kind in re.findall(r"(?<![가-힣])([가-힣]{2,10})(초|중|고)(?![가-힣])", text):
        found.append(name + {"초": "초등학교", "중": "중학교", "고": "고등학교"}[kind])
    return [correct_organization(x) for x in found]


def correct_organization(value: str) -> str:
    value = re.sub(r"^\d+", "", value).strip()
    schools = load("schools_sample.txt")
    suffix = re.search(r"([가-힣A-Za-z0-9()]+(?:초등학교|중학교|고등학교|학교|학원|아카데미))$", value)
    target = suffix.group(1) if suffix else value
    if schools and target.endswith("학교"):
        ranked = sorted(((max(fuzz.WRatio(target, x), fuzz.partial_ratio(target, x)), x) for x in schools), reverse=True)
        if ranked and ranked[0][0] >= 80 and (len(ranked) == 1 or ranked[0][0] - ranked[1][0] >= 8):
            return value[: len(value)-len(target)] + ranked[0][1]
    return value
