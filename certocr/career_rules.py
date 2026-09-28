"""현행 법령에 근거한 교육공무원 경력환산율 추천 규칙.

이 모듈은 생성형 모델의 판단을 사용하지 않는다. OCR로 확인된 기관·직종·
근무시간과 명시된 환산율만으로 후보를 만들며, 법령상 추가 사실이 필요한
경우에는 자동 확정 대신 필수 확인사항을 반환한다.

법령 자료 확인일: 2026-09-26 (확인 범위는 LEGAL_SNAPSHOT.review_scope 참조)
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re

from certocr.school_registry import lookup_school


LEGAL_SNAPSHOT = {
    "as_of": "2026-09-26",
    "review_scope": "8개 법령 현행 메타데이터·경력분류 관련 조문·교육부 예규97호 및 인사혁신처 예규220호. 개별 경력의 과거 시점·특례 적용은 담당자 확인 필요.",
    "primary_rule": "교육공무원 호봉획정시 경력환산율표의 적용 등에 관한 예규",
    "primary_rule_number": "교육부 예규 제97호",
    "primary_rule_effective": "2025-04-23",
    "primary_rule_url": "https://law.go.kr/flDownload.do?flSeq=151251813",
    "salary_guideline": "공무원보수 등의 업무지침",
    "salary_guideline_number": "인사혁신처 예규 제220호",
    "salary_guideline_effective": "2026-08-01",
    "salary_guideline_url": "https://www.law.go.kr/admRulLsInfoP.do?admRulSeq=2100000283466",
    "laws": [
        {
            "name": "국가공무원법",
            "kind": "법률",
            "promulgated": "2026-06-02",
            "effective": "2026-06-02",
            "mst": "286457",
            "articles": "제46조·제47조",
            "url": "https://www.law.go.kr/법령/국가공무원법",
        },
        {
            "name": "교육공무원법",
            "kind": "법률",
            "promulgated": "2025-08-14",
            "effective": "2026-02-15",
            "mst": "273345",
            "articles": "제2조·제32조·제34조",
            "url": "https://www.law.go.kr/법령/교육공무원법",
        },
        {
            "name": "공무원보수규정",
            "kind": "대통령령",
            "promulgated": "2026-07-30",
            "effective": "2026-08-01",
            "mst": "288433",
            "articles": "제8조·별표 15·별표 22~26",
            "url": "https://www.law.go.kr/법령/공무원보수규정",
        },
        {
            "name": "초·중등교육법",
            "kind": "법률",
            "promulgated": "2026-03-10",
            "effective": "2026-09-11",
            "mst": "283903",
            "articles": "제21조·제22조·제39조·제42조·제46조",
            "url": "https://www.law.go.kr/법령/초중등교육법",
        },
        {
            "name": "초·중등교육법 시행령",
            "kind": "대통령령",
            "promulgated": "2026-09-08",
            "effective": "2026-09-11",
            "mst": "289439",
            "articles": "산학겸임교사 등의 자격·임용 및 학력 동등자격",
            "url": "https://www.law.go.kr/법령/초중등교육법시행령",
        },
        {
            "name": "초·중등교육법 시행규칙",
            "kind": "교육부령",
            "promulgated": "2026-03-11",
            "effective": "2026-03-11",
            "mst": "284493",
            "articles": "학교·학력 확인 보조",
            "url": "https://www.law.go.kr/법령/초중등교육법시행규칙",
        },
        {
            "name": "교원자격검정령",
            "kind": "대통령령",
            "promulgated": "2024-10-02",
            "effective": "2024-10-02",
            "mst": "265627",
            "articles": "교원자격 검정·수여",
            "url": "https://www.law.go.kr/법령/교원자격검정령",
        },
        {
            "name": "교원자격검정령 시행규칙",
            "kind": "교육부령",
            "promulgated": "2026-03-27",
            "effective": "2026-03-27",
            "mst": "285245",
            "articles": "자격종별·표시과목 확인",
            "url": "https://www.law.go.kr/법령/교원자격검정령시행규칙",
        },
    ],
    "pending_changes": [
        {"name": "교육공무원법", "effective": "2026-11-20", "mst": "286055"},
        {"name": "국가공무원법", "effective": "2026-10-02·2026-10-22·2026-12-03"},
        {"name": "초·중등교육법", "effective": "2026-10-29·2026-11-20"},
        {"name": "공무원보수규정", "effective": "2026-12-03", "articles": "제28조·제47조 난임휴직 보수"},
    ],
}


TYPE_BASIS = {
    "tutoringPending": "교육부 예규 제97호 별표 1 제3호라목 9)(교습소 5할 후보·신고 및 교습자 경력 확인 필요)",
    "teacher10": "기존 호봉획정표 명시 100%·공무원보수규정 별표 22 제1호(공·사립 세부구분 확인)",
    "pub10": "공무원보수규정 별표 22 제1호가목·교육부 예규 제97호 별표 1 제1호가목",
    "priv10": "공무원보수규정 별표 22 제1호나목·사립학교법 제54조",
    "mis8": "공무원보수규정 별표 22 제1호 단서(자격종류와 근무학교 불일치)",
    "unrep5": "공무원보수규정 별표 22 제1호 단서(관할청 미보고 사립학교 교원)",
    "dc10": "공무원보수규정 별표 22 제1호마목",
    "dis8": "공무원보수규정 별표 22 제1호바목",
    "life10": "공무원보수규정 별표 22 제1호다목",
    "kor10": "공무원보수규정 별표 22 제1호라목",
    "gov10": "공무원보수규정 별표 22 제2호가목",
    "emp8": "공무원보수규정 별표 22 제2호나목",
    "sf10": "교육부 예규 제97호 별표 1 제3호가목(전일제·종일제 강사)",
    "stAuto": "교육부 예규 제97호 별표 1 제3호가목(시간제 강사 시기별 주당시간 비례)",
    "st3": "교육부 예규 제97호 별표 1 제3호가목(주 12시간 이하 또는 시수 불명 3할)",
    "u5": "교육부 예규 제97호 별표 1 제3호가목(대학 시간강사 주 5시간 이하)",
    "u6": "교육부 예규 제97호 별표 1 제3호가목(대학 시간강사 주 6시간)",
    "u7": "교육부 예규 제97호 별표 1 제3호가목(대학 시간강사 주 7시간)",
    "u8": "교육부 예규 제97호 별표 1 제3호가목(대학 시간강사 주 8시간)",
    "u9": "교육부 예규 제97호 별표 1 제3호가목(대학 시간강사 주 9시간)",
    "u10": "교육부 예규 제97호 별표 1 제3호가목(대학 시간강사 주 10시간 이상)",
    "res10": "공무원보수규정 별표 22 제3호나목 1)·2)",
    "ta10": "공무원보수규정 별표 22 제3호나목 3)",
    "ms10": "공무원보수규정 별표 22 제3호나목 4)(석사 최저 수업연한)",
    "ph10": "공무원보수규정 별표 22 제3호나목 4)(박사 최대 3년)",
    "sameDegree8": "공무원보수규정 별표 22 비고 2",
    "jab8": "공무원보수규정 별표 22 제3호다목 1)",
    "tmp8": "공무원보수규정 별표 22 제3호다목 1)",
    "tmp5": "공무원보수규정 별표 22 제3호다목 2)",
    "sch5": "교육부 예규 제97호 별표 1 제3호다목 2)(학교회계직원)",
    "sch8": "교육부 예규 제97호 별표 1 제3호다목 2)(동일업무 교원자격 취득 후)",
    "mil10": "공무원보수규정 별표 22 제3호라목 1)",
    "rehab8": "공무원보수규정 별표 22 제3호라목 2)",
    "law7": "공무원보수규정 별표 22 제3호라목 3)",
    "union7": "공무원보수규정 별표 22 제3호라목 4)",
    "alt7": "공무원보수규정 별표 22 제3호라목 5)",
    "relig6": "공무원보수규정 별표 22 제3호라목 6)",
    "pub5": "공무원보수규정 별표 22 제3호라목 7)",
    "overseas5": "공무원보수규정 별표 22 제3호라목 8)",
    "ac5": "공무원보수규정 별표 22 제3호라목 9)(등록 학원·신고 교습소)",
    "ac3": "공무원보수규정 별표 22 제3호라목 9) 단서(미등록·미신고)",
    "corp4": "공무원보수규정 별표 22 제3호라목 10)(상법상 회사)",
    "oth3": "공무원보수규정 별표 22 제3호라목 11)",
}


@dataclass
class CareerRecommendation:
    suggested_type: str = ""
    confidence: str = "low"
    candidate_types: list[str] = field(default_factory=list)
    legal_basis: list[str] = field(default_factory=list)
    required_checks: list[str] = field(default_factory=list)
    reason: str = ""
    law_snapshot_date: str = LEGAL_SNAPSHOT["as_of"]
    source: str = "statutory-rule-engine"
    decision_status: str = "review"
    evidence: list[dict] = field(default_factory=list)
    auto_apply: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def legal_snapshot() -> dict:
    """JSON 직렬화용 복사본."""
    return {
        **LEGAL_SNAPSHOT,
        "laws": [dict(item) for item in LEGAL_SNAPSHOT["laws"]],
        "pending_changes": [dict(item) for item in LEGAL_SNAPSHOT["pending_changes"]],
    }


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value or "")


def _hours(value: str | int | None) -> int | None:
    match = re.search(r"\d{1,2}", str(value or ""))
    if not match:
        return None
    number = int(match.group())
    return number if 0 < number <= 60 else None


def _result(
    suggested: str = "",
    *,
    confidence: str = "low",
    candidates: list[str] | None = None,
    checks: list[str] | None = None,
    reason: str = "",
    evidence: list[dict] | None = None,
    decision_status: str | None = None,
    auto_apply: bool | None = None,
) -> CareerRecommendation:
    candidate_types = list(dict.fromkeys(([suggested] if suggested else []) + (candidates or [])))
    return CareerRecommendation(
        suggested_type=suggested,
        confidence=confidence,
        candidate_types=candidate_types,
        legal_basis=[TYPE_BASIS[item] for item in candidate_types if item in TYPE_BASIS],
        required_checks=list(dict.fromkeys(checks or [])),
        reason=reason,
        evidence=evidence or [],
        decision_status=decision_status or ("candidate" if suggested else "review"),
        auto_apply=bool(suggested) if auto_apply is None else auto_apply,
    )


def _university_hourly(hours: int | None) -> str:
    if hours is None or hours <= 5:
        return "u5"
    return "u10" if hours >= 10 else f"u{hours}"


def _tutoring_pending() -> CareerRecommendation:
    return _result(
        "tutoringPending",
        confidence="low",
        candidates=["ac5", "ac3"],
        checks=[
            "근무 당시 관할 교육지원청에 신고된 교습소였는지 확인",
            "신청자가 실제 교습자로 근무했는지 확인",
            "사업자등록, 소득세·부가세 신고내역 등 객관적 증빙 확인",
        ],
        reason="교습소 경력은 50% 후보로 계산하되 신고·교습자 경력 확인이 필요합니다. 확인 필요 배지를 눌러 상세 안내를 확인하세요.",
        decision_status="provisional",
    )


def recommend_career(
    organization: str = "",
    position: str = "",
    weekly_hours: str | int | None = None,
    raw_text: str = "",
    approved_rate_percent: int | None = None,
    verified_facts: dict | None = None,
) -> CareerRecommendation:
    """기관·직종·시수에서 법령상 경력유형 후보를 추천한다.

    `approved_rate_percent`는 기존 획정표에 명시된 값으로, 새 법적 판단을
    대신하지 않고 동일 문서의 후보 순위를 보조하는 데만 사용한다.
    """
    org = _compact(organization)
    pos = _compact(position)
    raw = _compact(raw_text)
    text = org + pos + raw
    hours = _hours(weekly_hours)

    # 명시적인 기관·직종이 교습소이면 OCR 본문에 학위나 다른 경력이 섞여도 우선한다.
    if "교습소" in org + pos:
        if re.search(r"청소|경비|운전|조리|접수|수납", pos) and not re.search(r"교습|강사|교사", pos):
            return _result(candidates=["corp4", "oth3"], reason="교습소의 비교습 업무는 교습자 50% 잠정 경력으로 자동 처리하지 않습니다.", checks=["실제 직무와 고용형태·근로계약·정기보수 확인"])
        return _tutoring_pending()

    from certocr.career_evidence import classify_organization_career
    organization_decision = classify_organization_career(organization, position, raw_text, verified_facts)
    if organization_decision is not None:
        return _result(**organization_decision)

    if any(word in text for word in ("예술체육요원", "산업기능요원", "전문연구요원", "승선근무예비역")):
        return _result("mil10", confidence="high", reason="병역법상 별도 복무경력 문구 확인")
    if any(word in text for word in ("현역", "군복무", "상근예비역", "대체역", "국가공무원", "지방공무원")):
        return _result("gov10", confidence="high", reason="공무원 또는 현역병에 준하는 복무경력 문구 확인")
    if "고용직공무원" in text:
        return _result("emp8", confidence="high", reason="고용직공무원 경력 문구 확인")

    if "박사" in pos or ("대학원" in org and "박사" in raw):
        return _result("ph10", confidence="high", checks=["실제 등록·수학기간 및 3년 상한 확인"], reason="대학원 박사 수학경력")
    if "대학원" in org and any(word in pos + raw for word in ("수학", "석사")):
        return _result("ms10", confidence="high", checks=["실제 등록·수학기간과 학칙상 최저 수업연한 확인"], reason="대학원 석사 수학경력")
    if "연구전담조교" in text:
        return _result("ta10", confidence="high", checks=["근로계약·정기보수 지급 확인"], reason="대학(원) 연구전담 조교")
    if "연구원" in pos or "연구기관" in org:
        return _result("res10", confidence="mid", checks=["임용권자 임명, 정원 내 유급 또는 법정 연구기관 여부 확인"], reason="연구원 경력 후보")

    is_university = any(word in org for word in ("대학교", "대학", "전문대학", "대학원"))
    is_hourly = any(word in pos + raw for word in ("시간강사", "시간제강사"))
    if is_hourly and is_university:
        selected = _university_hourly(hours)
        return _result(selected, confidence="high" if hours else "mid", checks=[] if hours else ["주당 수업시수 확인"], reason="대학 시간강사 수업시수 기준")
    if is_hourly and org.endswith(("유치원", "초등학교", "중학교", "고등학교", "학교")):
        selected = "stAuto" if hours and hours > 12 else "st3"
        checks = [] if hours else ["계약서상 주당 수업시수 확인"]
        return _result(selected, confidence="high" if hours else "mid", checks=checks, reason="유·초·중등 시간제 강사 기준")
    if org.endswith(("유치원", "학교")) and "강사" in pos and any(word in raw for word in ("전일제", "종일제", "1일8시간", "일8시간")):
        return _result("sf10", confidence="high", checks=["교원자격과 근무 학교급 일치 확인"], reason="1일 8시간 이상 전일제·종일제 강사")

    school_suffix = ("유치원", "초등학교", "중학교", "고등학교", "학교")
    is_school = org.endswith(school_suffix)
    is_teacher = any(word in pos for word in ("기간제교원", "기간제교사", "교사", "교원"))
    if is_school and is_teacher:
        common_checks = ["소지 교원자격증 종류와 근무 학교급 일치 여부 확인"]
        if any(word in text for word in ("자격불일치", "학교급불일치")):
            return _result("mis8", confidence="high", reason="자격종류와 근무 학교 불일치 표시")
        school = lookup_school(organization)
        explicit_foundation = next((kind for kind in ("국립", "공립", "사립") if kind in org), "")
        if school.status == "matched":
            if explicit_foundation and explicit_foundation != school.foundation:
                return _result(
                    "", candidates=["pub10", "priv10", "mis8", "unrep5"],
                    checks=["입력 자료의 설립구분과 학교알리미 조회 결과가 다름: 원본 확인", *common_checks],
                    reason=f"{school.school_name}: 입력 자료와 학교알리미 {school.year} 설립구분 충돌",
                )
            historical_check = f"근무 당시 설립구분 확인(학교알리미 {school.year}년 스냅샷은 현재 정보)"
            if school.foundation == "사립":
                if any(word in text for word in ("미보고", "임면미보고", "보고되지않")):
                    return _result("unrep5", confidence="mid", checks=[*common_checks, historical_check], reason=f"{school.school_name}: 학교알리미 {school.year} 사립학교·임면 미보고 표시")
                return _result("priv10", confidence="mid", checks=[*common_checks, "관할청 임면 보고 여부 확인", historical_check], reason=f"{school.school_name}: 학교알리미 {school.year} 사립학교")
            return _result("pub10", confidence="mid", checks=[*common_checks, historical_check], reason=f"{school.school_name}: 학교알리미 {school.year} {school.foundation}학교")
        if school.status in ("ambiguous", "inactive"):
            return _result(
                "", candidates=["pub10", "priv10", "mis8", "unrep5"],
                checks=["동명 학교 또는 폐교 여부와 근무 당시 설립구분 확인", *common_checks],
                reason=f"학교알리미 {school.year} 자료만으로 해당 학교를 단정할 수 없음",
            )
        if "사립" in text:
            if any(word in text for word in ("미보고", "임면미보고", "보고되지않")):
                return _result("unrep5", confidence="high", checks=common_checks, reason="사립학교 관할청 임면 미보고 표시")
            return _result("priv10", confidence="mid", checks=common_checks + ["관할청 임면 보고 여부 확인"], reason="사립학교 교원 경력")
        if any(word in text for word in ("국립", "공립", "교육청")):
            return _result("pub10", confidence="mid", checks=common_checks, reason="국·공립 교육기관 교원 경력")
        if approved_rate_percent == 100:
            return _result(
                "teacher10",
                confidence="high",
                checks=["기존 획정표의 100% 승인값 원본 대조", "공·사립 및 관할청 임면보고 여부 확인", *common_checks],
                reason="기존 호봉획정표에 교원경력 100%가 명시됨",
            )
        return _result(
            "",
            candidates=["pub10", "priv10", "mis8", "unrep5"],
            confidence="low",
            checks=["국·공립/사립 구분 확인", "사립은 관할청 임면 보고 여부 확인", *common_checks],
            reason="학교 교원 경력은 확인정보에 따라 10할·8할·5할이 갈림",
        )

    if "평생교육시설" in text:
        return _result("life10", confidence="mid", checks=["학력인정 학교형태 시설 및 교원자격 확인"], reason="학교형태 평생교육시설 교원")
    if "한국학교" in text:
        return _result("kor10", confidence="mid", checks=["재외국민교육지원법상 설립·임면 여부 확인"], reason="재외 한국학교 교원")
    if "장애영유아" in text and "어린이집" in text:
        return _result("dis8", confidence="mid", checks=["특수학교 교원자격 및 지자체 임면보고 확인"], reason="장애영유아 어린이집 경력")
    if "어린이집" in text:
        return _result("dc10", confidence="mid", checks=["유치원 또는 해당 특수학교 교원자격, 지자체 임면보고 확인"], reason="어린이집 보육교직원 경력")

    if "학교회계" in text or (is_school and any(word in pos for word in ("영양사", "전산보조", "과학실험보조", "사서보조", "교육보조", "전임코치", "특수교육보조원", "상담사"))):
        return _result(
            "",
            candidates=["sch8", "sch5"],
            confidence="mid",
            checks=["업무분야와 동일한 교원자격 취득일 및 취득 후 근무기간 확인", "방학 중 무보수 기간 제외"],
            reason="학교회계직원은 동일업무 자격 취득 전후로 5할·8할 구분",
        )
    if "교습소" in raw:
        return _tutoring_pending()
    if "학원" in org or "학원강사" in pos:
        if any(word in text for word in ("미등록", "미신고")):
            return _result("ac3", confidence="high", checks=["근로소득세 납입증명 등 객관적 증빙 확인"], reason="미등록·미신고 학원/교습소")
        return _result("ac5", confidence="mid", candidates=["ac3"], checks=["교육감 등록 학원 또는 신고 교습소 및 강사 등록 여부 확인"], reason="학원·교습소 강사 경력")
    if any(word in text for word in ("변호사", "법무사")):
        return _result("law7", confidence="high", checks=["자격 취득 후 법률사무 종사기간 확인"], reason="변호사·법무사 경력")
    if any(word in text for word in ("교원단체", "교원노조", "교원의노동조합")):
        return _result("union7", confidence="high", reason="법정 교원단체·교원노조 근무경력")
    if "대안교육" in text and "위탁" in text:
        return _result("alt7", confidence="mid", checks=["교육감 지정기관 및 자격과 동일 분야 학생교육 전담 여부 확인"], reason="대안교육 위탁교육기관")
    if "종교법인" in text:
        return _result("relig6", confidence="mid", checks=["민법상 비영리 종교법인 및 교육활동 관련 직무 확인"], reason="종교법인 교육활동 경력")
    if any(word in text for word in ("공공기관", "공공법인", "공사", "공단")):
        return _result("pub5", confidence="mid", checks=["법정 인정법인 및 행정·경영·연구·과학기술 분야 여부 확인"], reason="공공기관·공공법인 경력")
    if "재외교육" in text:
        return _result("overseas5", confidence="mid", checks=["법정 등록기관 여부 및 한국학교·교육원 제외 확인"], reason="재외교육기관·단체 경력")
    if any(word in text for word in ("장애인복지관", "지역사회재활시설")):
        return _result("rehab8", confidence="mid", checks=["특수학교 교원자격 및 법정 시설 여부 확인"], reason="장애인 지역사회재활시설 경력")

    is_company = org.endswith(("회사", "아카데미")) or any(word in text for word in ("주식회사", "유한회사", "합명회사", "합자회사", "(주)"))
    if is_company or pos in ("사원", "계약직"):
        if approved_rate_percent == 40 or is_company:
            return _result("corp4", confidence="mid", checks=["상법 제169조·제170조상 회사 및 직원 근무 여부 확인"], reason="상법상 회사 근무경력")
        return _result("", candidates=["corp4", "oth3"], checks=["법인등기·사업자등록으로 상법상 회사 여부 확인"], reason="회사 형태에 따라 4할·3할 구분")

    if approved_rate_percent == 100:
        return _result("", candidates=["pub10", "priv10", "gov10", "res10"], checks=["기존 획정표의 100% 근거 경력구분 확인"], reason="기존 자료에 100%가 있으나 경력구분 판독 필요")
    if approved_rate_percent == 80:
        return _result("", candidates=["mis8", "emp8", "sch8", "rehab8"], checks=["기존 획정표의 80% 근거 경력구분 확인"], reason="기존 자료에 80%가 있으나 경력구분 판독 필요")
    if approved_rate_percent == 50:
        return _result("", candidates=["unrep5", "sch5", "pub5", "ac5", "overseas5"], checks=["기존 획정표의 50% 근거 경력구분 확인"], reason="기존 자료에 50%가 있으나 경력구분 판독 필요")
    if approved_rate_percent == 40:
        return _result("corp4", confidence="mid", checks=["상법상 회사 여부 확인"], reason="기존 획정표 40% 및 회사 경력 후보")
    if approved_rate_percent == 30:
        return _result("", candidates=["ac3", "oth3", "st3"], checks=["기존 획정표의 30% 근거 경력구분 확인"], reason="기존 자료에 30%가 있으나 경력구분 판독 필요")

    return _result("", candidates=["oth3"], checks=["근로계약·정기보수 및 법정 경력구분 확인", "유사경력은 전력조회와 필요 시 호봉경력 평가심의회 실시"], reason="그 밖의 직업경력 가능성")


def part_time_rule(type_id: str, weekly_hours: str | int | None) -> dict:
    """일반 단시간 유사경력의 법정 비례환산 보조정보.

    유·초·중등 시간제 강사(`stAuto`, `st3`)와 공무원 경력은 각자의 별도
    규칙을 적용하므로 여기서 제외한다.
    """
    hours = _hours(weekly_hours)
    excluded = {"gov10", "emp8", "sf10", "stAuto", "st3", "u5", "u6", "u7", "u8", "u9", "u10"}
    if not hours or type_id in excluded:
        return {"applies": False, "weekly_hours": hours, "factor": 1.0, "excluded": False}
    if hours < 15:
        return {
            "applies": True,
            "weekly_hours": hours,
            "factor": 0.0,
            "excluded": True,
            "basis": "공무원보수규정 별표 22 비고 4·인사혁신처 예규 제220호",
            "message": "주 15시간 미만 단시간 경력은 산입 대상에서 제외",
        }
    factor = min(1.0, hours / 40.0)
    return {
        "applies": hours < 40,
        "weekly_hours": hours,
        "factor": factor,
        "excluded": False,
        "basis": "공무원보수규정 별표 22 비고 4·인사혁신처 예규 제220호",
        "message": f"주 {hours}시간/주 40시간 비례환산" if hours < 40 else "통상근무시간 이상",
    }
