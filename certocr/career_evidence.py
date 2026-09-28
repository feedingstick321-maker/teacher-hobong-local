"""Local, evidence-gated classification of non-school employment.

Names identify questions to ask. Affirmative document facts or explicit user
verification identify a candidate; absent/negative/conflicting facts abstain.
No network, model, or probabilistic confidence is used here.
"""
from __future__ import annotations

import re
import unicodedata


FACT_VALUES = {
    "legal_form": {"unknown", "commercial_company", "civil_corporation", "individual_business", "public_recognized"},
    "employment_verified": {"unknown", "yes", "no"},
    "academy_registration": {"unknown", "registered", "unregistered"},
    "tax_evidence": {"unknown", "yes", "no"},
    "visiting_education": {"unknown", "yes", "no"},
    "public_role": {"unknown", "yes", "no"},
}
FORM = r"주식회사|유한(?:책임)?회사|합명회사|합자회사|\(주\)|\(유\)"
CIVIL = r"재단법인|사단법인|\(재\)|\(사\)"
PERSONAL = r"개인회사|개인기업|개인사업(?:자|체)|법인격(?:이)?없는|개인(?:병원|의원)|개인.{0,12}법인아닌사업장"
PUBLIC = r"공기업|준정부기관|공공법인|지방공사|지방공단|공공기관"
ROLE = r"행정|경영|연구|기술|과학|전산|회계|기획|사무"
EXCLUDED_JOB = r"보험(?:판매|설계|모집)|외판원|방문판매원|점원"
RELIGIOUS_JOB = r"목사|강도사|전도사|선교사|신부|수녀|수사|승려|주지|교무|도무|덕무"
OTHER_SUBJECT = r"거래처|고객사|원청|발급기관|발급자|이전근무처|전근무처|전직장|예시|인용"
UNKNOWN = r"미확인|불명|모르|알수없|확인(?:되지않|할수없|전|중|필요|불가)|검토중|미제출|제출되지않|제출하지않|자료(?:가|는|를)?없|증빙(?:이|은|을)?없"
NEGATIVE = r"미등록|무등록|미지정|미신고|취소|말소|아니|아닌|아님|없|않|해당하지"


def compact(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(value or "")))


def _has(pattern: str, value: str) -> bool:
    return bool(re.search(pattern, value))


def _segments(raw: str) -> list[str]:
    # Bound negations to a clause, so "공공기관은 아님, 월급 확인" retains pay evidence.
    return [compact(s) for s in re.split(r"[\n;.!?。]|,(?!\s*[^。.!?\n]*(?:여부|미제출|제출하지|제출되지))|(?<=없고)|(?<=없으며)|(?<=없지만)|(?<=아니고)|(?<=아니며)|(?<=아니지만)|(?<=아니라)|(?<=받았고)", unicodedata.normalize("NFKC", raw)) if compact(s)]


def _status(segments: list[str], anchor: str, *, positive: str = "", negative: str = NEGATIVE) -> str:
    states = set()
    for segment in segments:
        if not _has(anchor, segment):
            continue
        if _has(UNKNOWN, segment):
            states.add("unknown")
        elif negative and _has(negative, segment):
            states.add("no")
        elif not positive or _has(positive, segment):
            states.add("yes")
    if "yes" in states and "no" in states:
        return "conflict"
    if "unknown" in states:
        return "unknown"
    return "yes" if "yes" in states else "no" if "no" in states else "unknown"


def extract_career_facts(organization: str, position: str, raw_text: str = "", verified_facts: dict | None = None) -> dict:
    org, pos = compact(organization), compact(position)
    # Issuer titles, copied examples and academic biography are not employment facts.
    lines = [line for line in str(raw_text or "").splitlines()
             if not re.match(r"\s*(?:발급자|발급기관|발급담당|작성자|담당자|대표자학력|대표학력|참고예시|안내예시)\s*[:：]", line)]
    # Evidence about a counterparty, issuer or example must not describe this employer.
    segments = [s for s in _segments("\n".join(lines)) if not _has(OTHER_SUBJECT, s)]
    raw = "。".join(segments)
    conflict = _has(r"서류(?:마다|간)|서로(?:다르|상충)|상충|상반된|법적형태.{0,12}불일치|등록.{0,12}불일치|증빙.{0,12}모순|정정.{0,10}(?:없|미제출|안됐)|진위.{0,15}(?:미확인|확인하지못)", raw)
    reported_hours = set(re.findall(r"주(?:당)?(\d{1,2})시간", raw))
    if len(reported_hours) > 1:
        conflict = True  # One career row cannot reconcile different weekly hours on its own.

    commercial = _has(FORM, org)
    civil = _has(CIVIL, org)
    personal = False
    public_state = "unknown"
    public_positive, public_negative = False, False
    for s in segments:
        if _has(FORM, s) and not _has(r"(?:회사|상법).{0,8}(?:아니|아닌|아님)|" + UNKNOWN, s):
            commercial = True
        if _has(CIVIL, s) and not _has(r"(?:사단법인|재단법인|민법).{0,8}(?:아니|아닌|아님)|" + UNKNOWN, s):
            civil = True
        if _has(PERSONAL, s) and not _has(r"개인(?:사업자|회사|기업).{0,6}(?:아니|아닌|아님)|" + UNKNOWN, s):
            personal = True
        if _has(PUBLIC, s):
            uncertain = _has(UNKNOWN + r"|지정여부|설립근거.{0,8}(?:없|미제출)", s)
            negative = _has(r"없|아니|아닌|아님|취소|해제|해당하지|미지정", s)
            positive = _has(r"(?:공기업|준정부기관).{0,20}(?:지정|고시|확인)|지정된.{0,12}(?:공기업|준정부기관)|(?:공공기관운영법|공공기관의운영에관한법률).{0,12}(?:공기업|준정부기관)|지방공기업법.{0,22}(?:공사|공단)|(?:공공법인|개별법).{0,28}(?:인정|설립근거)|인정.{0,12}공공법인", s)
            if uncertain or negative:
                public_negative = True
            elif positive:
                public_positive = True
    public_state = "conflict" if public_positive and public_negative else "yes" if public_positive else "no" if public_negative else "unknown"

    relationship = _status(segments, r"근로계약|계약서.{0,12}소득자료|고용관계|고용보험|상근|정규직|유급.{0,8}직원", positive=r"확인|있|제출|기록|정규직|상근|체결|맺|유급|따라", negative=r"(?:근로계약|고용관계|계약서).{0,20}(?:없|않|미제출)|무급|봉사|수수료만")
    payment = _status(segments, r"정기보수|보수|급여|월급|임금|유급|소득자료|원천징수|근로소득|(?:계약서|근로계약).{0,18}소득세", positive=r"확인|있|제출|지급|받|매달|매월|월별|정기|명세|내역|기록|유급", negative=r"(?:보수|급여|월급|임금|소득자료|원천징수|근로소득).{0,20}(?:없|않|미제출)|무급|봉사|수수료만")
    employment = "yes" if relationship == payment == "yes" else "conflict" if "conflict" in (relationship, payment) else "no" if "no" in (relationship, payment) else "unknown"
    if _has(r"프리랜서|위촉|도급|용역계약|수수료", pos + raw) and relationship != "yes":
        employment = "unknown" if employment != "no" else "no"
    # Mere mention of a job title is not proof of regular paid employment.
    tax = _status(segments, r"소득세|부가세|세무|납세|원천징수|국세", positive=r"있|제출|확인|발급|납입|납부|내역|증빙", negative=r"(?:소득세|부가세|세무|납세|원천징수|국세).{0,20}(?:없|미제출|않)")
    academy = "unknown"
    acad_states = set()
    for original_segment in segments:
        s = re.sub(r"사업자등록증?|강사등록증?", "", original_segment)
        # Business registration is not an academy's registration with an education authority.
        if not _has(r"학원|교육청|교육감|교육지원청|미등록|무등록", s):
            continue
        if _has(r"미등록|무등록|등록(?:이력|사실|상태)?(?:이|을|은)?(?:되어있지않|되지않|하지않|없)|등록.{0,8}(?:취소|말소)|등록하지않", s):
            acad_states.add("unregistered")
        elif _has(r"등록.{0,15}(?:여부|미확인|불명|확인전|확인되지않|자료없|증빙없|미제출)|등록증.{0,8}(?:미제출|없)", s):
            acad_states.add("unknown")
        elif _has(r"학원등록증|등록(?:된|을마친|한)학원|등록학원|학원.{0,12}(?:정식등록|등록.{0,12}(?:확인|유효|마쳤|완료))|(?:교육청|교육감|교육지원청).{0,12}등록", s):
            acad_states.add("registered")
    if "registered" in acad_states and "unregistered" in acad_states:
        academy = "conflict"
    elif "unknown" not in acad_states and acad_states:
        academy = next(iter(acad_states))

    visiting = _status(segments, r"방문.{0,15}(?:지도|학습|교육)|학생.{0,12}방문|학습지", positive=r"학생|학습지|가정|지도", negative=r"아니|아닌|아님|하지않|없")
    if visiting == "unknown" and _has(r"방문.{0,10}(?:학습지|지도교사)|학습지.{0,10}방문", pos):
        visiting = "yes"
    role = "yes" if _has(ROLE, pos) else _status(segments, ROLE, positive=r"직원|직무|담당|근무|재직|업무|분야")
    if _has(r"청소|경비|운전|환경미화|배식|조리", pos) and not _has(ROLE, pos):
        role = "no"
    legal_form = "public_recognized" if public_state == "yes" else "individual_business" if personal else "civil_corporation" if civil else "commercial_company" if commercial else "unknown"
    if commercial and (civil or personal):
        conflict = True
    religious = _status(segments, r"종교법인", positive=r"소속|법인|등기|설립|확인", negative=NEGATIVE + r"|여부")
    if religious == "unknown" and "종교법인" in org and not any(_has(r"종교법인", s) for s in segments):
        religious = "yes"
    facts = {
        "legal_form": legal_form, "employment_verified": employment,
        "academy_registration": academy, "tax_evidence": tax,
        "visiting_education": visiting, "public_role": role,
        "public_designation": public_state,
        "religious_corporation": religious,
    }
    sources = {key: "document" for key, value in facts.items() if value not in ("unknown", "no")}
    for key, value in (verified_facts or {}).items():
        if key not in FACT_VALUES or value not in FACT_VALUES[key] or value == "unknown":
            continue
        previous = facts[key]
        if previous not in ("unknown", value) and not (key == "legal_form" and previous == "civil_corporation" and value == "public_recognized"):
            conflict = True
        facts[key] = value
        sources[key] = "user_verified"
    facts.update(conflict=conflict or any(v == "conflict" for v in facts.values()), sources=sources, clean_text=raw)
    return facts


def classify_organization_career(organization: str, position: str, raw_text: str = "", verified_facts: dict | None = None) -> dict | None:
    org, pos = compact(organization), compact(position)
    confirmed_facts = {key: value for key, value in (verified_facts or {}).items() if key in FACT_VALUES and value in FACT_VALUES[key] and value != "unknown"}
    if org.endswith(("학교", "유치원", "대학", "대학원")) and not confirmed_facts:
        return None
    f = extract_career_facts(organization, position, raw_text, verified_facts)
    raw = f["clean_text"]
    institution = {}
    try:
        from certocr.institution_registry import lookup_career_institution
        institution = lookup_career_institution(organization)
    except ImportError:
        pass
    known = institution.get("status") == "matched"
    institution_hint = _has(FORM + "|" + CIVIL + "|" + PERSONAL + r"|회사|기업|재단|협회|센터|공사|공단|공공기관|종교법인|교회|성당|사찰|학원|아카데미", org)
    fact_hint = f["legal_form"] != "unknown" or bool(confirmed_facts) or known
    if not institution_hint and not fact_hint and _has(r"공무원|군복무|현역|군인|병장|대체역|예술체육요원|산업기능요원|전문연구요원|승선근무|보육교사|어린이집|평생교육|장애인|변호사|노동조합", org + pos):
        return None

    evidence = [{"field": key, "value": f[key], "source": source} for key, source in f["sources"].items()]
    def result(selected="", candidates=None, reason="", checks=None):
        # Free-text extraction is an advisory layer, not proof. Only explicit
        # human-verified required facts may authorize automatic calculation.
        verified = confirmed_facts
        allowed = False
        if selected in ("corp4", "oth3"):
            allowed = verified.get("legal_form") in ("commercial_company", "civil_corporation", "individual_business") and verified.get("employment_verified") == "yes"
            if verified.get("legal_form") == "commercial_company":
                allowed = allowed and verified.get("visiting_education") in ("yes", "no")
                if not allowed:
                    checks = (checks or []) + ["상법회사 40%·방문지도 30% 구분을 위해 학생 가정 방문 교육 업무 여부도 증빙에서 확인"]
        elif selected == "pub5":
            # A current registry cannot prove an institution's historical status.
            allowed = verified.get("legal_form") == "public_recognized" and verified.get("employment_verified") == "yes" and verified.get("public_role") == "yes"
        elif selected == "ac5":
            allowed = verified.get("academy_registration") == "registered"
        elif selected == "ac3":
            allowed = verified.get("academy_registration") == "unregistered" and verified.get("tax_evidence") == "yes"
        return {"suggested": selected, "candidates": candidates or [], "confidence": "mid" if selected else "low", "reason": reason,
                "checks": checks or [], "evidence": evidence, "decision_status": "candidate" if selected else "review", "auto_apply": bool(allowed)}

    candidates = ["corp4", "oth3", "pub5"]
    if f["conflict"]:
        return result(candidates=candidates, reason="기관 유형 또는 증빙 내용이 서로 달라 확인이 필요합니다.", checks=["법인등기·등록·급여 자료의 서로 다른 기재를 원본과 대조"])
    if _has(EXCLUDED_JOB, pos):
        return result(candidates=["oth3"], reason="보험판매원·외판원·점원 등은 일반 회사 직원 4할 규정으로 자동 분류할 수 없습니다.", checks=["실제 직무, 근로계약·보수 형태와 별도 인정 근거 확인"])

    if ("학원" in org or "아카데미" in org or "학원강사" in pos) and "학교법인" not in org:
        if not _has(r"강사|교습|교사|수업|강의", pos) or _has(r"(?:강사|교습자|교사).{0,8}(?:아니|아닌)|(?:수업|강의|교습)(?:없이|을하지않|하지않)|접수만|수납만", raw):
            return result(candidates=["corp4", "oth3"], reason="학원 직원이라는 사실만으로 학원 강사 경력을 적용할 수 없습니다.", checks=["실제 강의·교습 업무와 법적 고용형태 확인"])
        if f["academy_registration"] == "registered":
            return result("ac5", ["ac3"], "등록 학원의 강사 경력으로 5할 이내 후보입니다.", ["근무 당시 학원·강사 등록과 재직기간 원본 대조"])
        if f["academy_registration"] == "unregistered" and f["tax_evidence"] == "yes":
            return result("ac3", reason="미등록 학원 강사이며 객관적 세무증빙이 확인되어 3할 이내 후보입니다.", checks=["세무증빙의 귀속기간과 실제 강의기간 대조"])
        return result(candidates=["ac5", "ac3"], reason="학원 등록 여부 또는 미등록 경력의 객관적 증빙 확인이 필요합니다.", checks=["근무 당시 교육감 등록 여부 확인", "미등록이면 근로소득세 납입증명 등 객관적 자료 확인"])

    if _has(r"종교법인|교회|성당|사찰", org + raw):
        if _has(r"주일학교|학생부선생|자원봉사|봉사교사", pos) or (_has(r"주일학교|학생부선생", raw) and not _has(RELIGIOUS_JOB, pos)):
            return result(reason="주일학교·학생부 봉사활동은 종교법인 인정 직무로 자동 분류할 수 없습니다.", checks=["법인 소속과 예규에서 인정한 실제 직무 확인"])
        if f["religious_corporation"] == "yes" and _has(RELIGIOUS_JOB, pos):
            return result("relig6", reason="종교법인 소속 인정 직무의 6할 이내 후보입니다.", checks=["비영리 종교법인 소속과 교육활동 관련 직무·재직기간 확인"])
        if f["legal_form"] != "civil_corporation":
            return result(candidates=["relig6", "oth3"], reason="종교시설 명칭만으로 법인 여부와 인정 직무를 확정할 수 없습니다.", checks=["종교법인 여부와 실제 담당 직무 확인"])

    if known:
        evidence.append({"field": "institution_registry", "value": institution.get("canonical_name", organization), "source": institution.get("source_url", "offline_registry")})
        if institution.get("suggested_type") == "pub5":
            if f["public_designation"] == "no":
                return result(candidates=["pub5", "oth3"], reason="공식 명부와 입력 증빙의 기관 지위가 다릅니다.", checks=["근무 당시의 지정·해제 이력 확인"])
            f["legal_form"] = "public_recognized"
        elif f["legal_form"] == "unknown":
            return result(candidates=["pub5", "oth3"], reason="공공기관 명부 등재만으로 이 경력의 5할 인정 근거가 확인되지는 않습니다.", checks=institution.get("required_checks", []) + ["예규에서 인정하는 기관 유형 또는 별도 인정 근거 확인"])

    if f["legal_form"] == "public_recognized":
        if f["public_role"] != "yes":
            return result(candidates=["pub5"], reason="기관 인정 근거는 있으나 행정·경영·연구·기술 업무 여부가 확인되지 않았습니다.", checks=["실제 담당업무·직무기술서 확인"])
        if f["employment_verified"] != "yes":
            return result(candidates=["pub5"], reason="공공기관 직원의 재직·보수 증빙 확인이 필요합니다.", checks=["근로관계와 재직기간을 객관적 증빙으로 대조"])
        return result("pub5", reason="인정 기관 유형과 행정·경영·연구·기술 직무에 따른 5할 이내 후보입니다.", checks=institution.get("required_checks", []) + ["근무 당시 기관 인정 지위·직무·재직기간 확인"])

    if f["legal_form"] in ("commercial_company", "civil_corporation", "individual_business"):
        if f["employment_verified"] != "yes":
            return result(candidates=["corp4", "oth3"] if f["legal_form"] == "commercial_company" else ["oth3"], reason="법적 유형은 파악했지만 근로관계·정기보수 증빙 확인이 필요합니다.", checks=["근로계약서, 급여명세서·소득세 등 객관적 고용·보수 자료 확인"])
        if f["visiting_education"] == "yes":
            return result("oth3", reason="학생 직접 방문지도 목적 회사의 학습지 지도 경력은 3할 이내 후보입니다.", checks=["학생 방문지도 사업목적·실제 직무·정기보수 확인"])
        if f["legal_form"] == "commercial_company":
            return result("corp4", reason="상법상 회사 직원의 고용·보수 근거에 따른 4할 이내 후보입니다.", checks=["상법상 회사 유형·예외 직무·근무기간 최종 대조"])
        return result("oth3", reason="민법상 일반 법인 또는 개인회사의 고용·정기보수 경력으로 3할 이내 후보입니다.", checks=["법적 설립형태·근로계약·정기보수와 실제 기간 대조"])

    return result(candidates=candidates, reason="기관명만으로 법적 유형을 판단할 수 없어 확인이 필요합니다.", checks=["법인등기·사업자등록 또는 근무 당시 기관 지정 근거 확인", "근로관계·정기보수·실제 담당업무 확인"])
