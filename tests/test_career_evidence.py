from __future__ import annotations

import unittest

from certocr.career_rules import recommend_career
from certocr.career_evidence import extract_career_facts


class EvidenceClassificationTests(unittest.TestCase):
    def test_name_alone_does_not_supply_missing_evidence(self):
        for org, position in (("주식회사 가상물산", "사원"), ("가상공공기관", "행정직"), ("재단법인 가상문화", "직원"), ("가상보습학원", "강사")):
            with self.subTest(org=org):
                self.assertEqual(recommend_career(org, position).suggested_type, "")

    def test_paid_company_and_personal_business_are_separate(self):
        paid = "근로계약서를 체결하고 매월 급여를 지급받은 직원이다."
        self.assertEqual(recommend_career("주식회사 가상", "사무직", raw_text=paid).suggested_type, "corp4")
        self.assertEqual(recommend_career("가상기획", "직원", raw_text="법인격 없는 개인사업체. " + paid).suggested_type, "oth3")

    def test_negative_public_mention_does_not_override_civil_foundation(self):
        r = recommend_career("재단법인 가상공공", "행정직", raw_text="민법상 재단법인이다. 공공기관 지위는 없다. 근로계약·월급 지급 확인.")
        self.assertEqual(r.suggested_type, "oth3")

    def test_explicit_public_designation_and_role(self):
        self.assertEqual(recommend_career("가상개발원", "행정직", raw_text="공공기관운영법상 준정부기관으로 지정됐다. 근로계약 체결과 매월 급여 지급 확인.").suggested_type, "pub5")
        self.assertEqual(recommend_career("가상개발원", "청소원", raw_text="공공기관운영법상 준정부기관으로 지정됐다.").suggested_type, "")

    def test_official_institution_name_does_not_prove_employment(self):
        r = recommend_career("한국전력공사", "회계담당")
        self.assertEqual(r.suggested_type, "")
        self.assertIn("pub5", r.candidate_types)

    def test_business_registration_is_not_academy_registration(self):
        for raw in ("사업자등록증을 제출했습니다.", "학원 사업자등록증을 제출했습니다.", "강사등록증을 제출했습니다."):
            self.assertEqual(recommend_career("새봄학원", "강사", raw_text=raw).suggested_type, "")

    def test_regular_commission_payment_does_not_prove_employment(self):
        r = recommend_career("주식회사 한빛", "프리랜서 번역가", raw_text="위촉계약을 체결했습니다. 매월 정기보수를 지급받았습니다.")
        self.assertEqual(r.suggested_type, "")
        self.assertEqual(recommend_career("주식회사 한빛", "직원", raw_text="매월 급여를 지급받았습니다.").suggested_type, "")

    def test_other_organizations_legal_form_is_not_employer_evidence(self):
        for subject in ("거래처", "고객사", "발급기관", "이전 근무처", "참고 예시"):
            r = recommend_career("푸른마을센터", "행정직원", raw_text=f"{subject}는 주식회사 한빛입니다.\n근로계약서를 체결했습니다.\n매월 급여를 지급받았습니다.")
            self.assertEqual(r.suggested_type, "", subject)

    def test_negative_or_unverified_religious_corporation_abstains(self):
        for raw in ("종교법인이 아닌 비법인 단체입니다.", "종교법인 여부는 미확인입니다.", "종교법인 자료는 제출되지 않았습니다."):
            self.assertEqual(recommend_career("한빛교회", "전도사", raw_text=raw).suggested_type, "")

    def test_private_academy_hourly_instructor_is_not_school_hourly(self):
        self.assertEqual(recommend_career("가상보습학원", "시간강사", 20, "교육감에게 등록된 학원이다.").suggested_type, "ac5")

    def test_unregistered_academy_requires_objective_tax_evidence(self):
        self.assertEqual(recommend_career("가상학원", "강사", raw_text="미등록 학원, 소득세 자료가 없다.").suggested_type, "")
        self.assertEqual(recommend_career("가상학원", "강사", raw_text="학원 등록은 없지만 소득세 납입증명서를 제출했다.").suggested_type, "ac3")

    def test_visiting_student_exception_precedes_company(self):
        self.assertEqual(recommend_career("주식회사 가상교육", "방문 학습지 지도교사", raw_text="학생 가정 방문지도 목적 회사. 근로계약과 월급 기록이 있다.").suggested_type, "oth3")

    def test_seller_is_not_assumed_company_employee(self):
        self.assertEqual(recommend_career("주식회사 가상보험", "보험판매원", raw_text="월별 수수료만 지급받았다.").suggested_type, "")

    def test_missing_and_conflicting_documents_abstain(self):
        for raw in ("근로계약·정기보수 증빙은 미제출", "주식회사와 민법상 재단법인이라는 서로 다른 서류가 제출됐다. 월급 확인."):
            self.assertEqual(recommend_career("주식회사 가상", "사원", raw_text=raw).suggested_type, "")

    def test_structured_verification_supplies_missing_facts(self):
        r = recommend_career("가상서비스", "사무직", verified_facts={"legal_form": "individual_business", "employment_verified": "yes"})
        self.assertEqual(r.suggested_type, "oth3")
        self.assertTrue(any(e["source"] == "user_verified" for e in r.evidence))

    def test_structured_values_cannot_override_document_conflict(self):
        r = recommend_career("가상서비스", "사무직", raw_text="급여와 근로계약이 없다.", verified_facts={"legal_form": "commercial_company", "employment_verified": "yes"})
        self.assertEqual(r.suggested_type, "")

    def test_unknown_structured_values_preserve_school_registry(self):
        self.assertEqual(recommend_career("홍천고등학교", "기간제교원", verified_facts={"legal_form": "unknown", "employment_verified": "unknown"}).suggested_type, "pub10")

    def test_issuer_degree_does_not_change_company_career(self):
        r = recommend_career("주식회사 가상물산", "사무직", raw_text="근로계약과 정기보수 확인.\n발급자: 교육학 박사, 가상대학교 교수")
        self.assertEqual(r.suggested_type, "corp4")

    def test_registered_status_unknown_is_not_positive(self):
        facts = extract_career_facts("가상학원", "강사", "학원 등록 여부 미확인")
        self.assertEqual(facts["academy_registration"], "unknown")

    def test_religious_volunteer_is_not_eligible_role(self):
        self.assertEqual(recommend_career("가상종교법인", "주일학교 봉사교사", raw_text="종교법인 소속 봉사자").suggested_type, "")

    def test_tutoring_place_preserves_provisional_policy(self):
        r = recommend_career("가상수학교습소", "교습자", raw_text="소득세 자료 미제출")
        self.assertEqual(r.suggested_type, "tutoringPending")
        self.assertEqual(r.decision_status, "provisional")

    def test_registered_academy_does_not_imply_teaching_role(self):
        r = recommend_career("나래입시학원", "접수 직원", raw_text="교육감 등록 학원. 수업 강사가 아니라 접수만 담당했다.")
        self.assertEqual(r.suggested_type, "")

    def test_missing_public_status_is_not_rescued_by_legacy_keywords(self):
        r = recommend_career("가상한국공공미래원", "행정 직원", raw_text="공공기관 지정 이력이 제출되지 않았다.")
        self.assertEqual(r.suggested_type, "")

    def test_unrelated_example_cannot_trigger_legacy_tutoring_route(self):
        r = recommend_career("모르는상호", "미상", raw_text="참고 예시에는 교습소와 공공기관이 나온다. 실제 고용주는 알 수 없다.")
        self.assertEqual(r.suggested_type, "")

    def test_academy_registration_negative_history_with_tax(self):
        r = recommend_career("한빛입시학원", "수학 강사", raw_text="등록학원 명부 조회 결과 재직 당시 등록 이력이 없었다. 근로소득세 납입증명서를 제출했다.")
        self.assertEqual(r.suggested_type, "ac3")

    def test_public_recognition_negative_is_scoped_to_foundation(self):
        r = recommend_career("재단법인 문화원", "행정 직원", raw_text="인정 공공법인이나 교육부 인정기관에는 해당하지 않는다. 근로계약을 체결하고 정기 보수를 받았다.")
        self.assertEqual(r.suggested_type, "oth3")

    def test_conflicting_weekly_hours_require_review(self):
        r = recommend_career("주식회사 물류", "사무 직원", raw_text="근로계약서에는 주 40시간, 급여기록에는 주 10시간이다. 정정 자료는 없다. 매월 급여와 고용관계 확인.")
        self.assertEqual(r.suggested_type, "")

    def test_religious_missing_multiple_facts_is_not_split_into_positive(self):
        r = recommend_career("누리교회", "전도사", raw_text="종교법인 소속 여부, 정식 임명 여부, 전임 재직자료는 제출하지 않았다.")
        self.assertEqual(r.suggested_type, "")

    def test_known_non_teaching_job_at_tutoring_place_is_not_provisional_teacher(self):
        self.assertEqual(recommend_career("한빛교습소", "청소 보조").suggested_type, "")

    def test_document_candidate_does_not_authorize_auto_application(self):
        r = recommend_career("주식회사 가상", "사무직", raw_text="근로계약과 정기 급여 지급 확인.")
        self.assertEqual(r.suggested_type, "corp4")
        self.assertFalse(r.auto_apply)

    def test_verified_required_company_facts_authorize_candidate(self):
        r = recommend_career("주식회사 가상", "사무직", verified_facts={"legal_form": "commercial_company", "employment_verified": "yes", "visiting_education": "no"})
        self.assertTrue(r.auto_apply)
        self.assertEqual(r.suggested_type, "corp4")

    def test_public_auto_application_requires_verified_role_and_employment(self):
        r = recommend_career("한국전력공사", "회계담당", verified_facts={"legal_form": "public_recognized", "employment_verified": "yes", "public_role": "yes"})
        self.assertEqual(r.suggested_type, "pub5")
        self.assertTrue(r.auto_apply)
        self.assertFalse(recommend_career("한국전력공사", "회계담당", verified_facts={"employment_verified": "yes"}).auto_apply)

    def test_company_visiting_exception_must_be_explicitly_verified(self):
        verified = {"legal_form": "commercial_company", "employment_verified": "yes"}
        for position, raw in (("직원", ""), ("방문 학습지 지도교사", "학생 가정 방문지도 목적 회사")):
            self.assertFalse(recommend_career("주식회사 한빛교육", position, raw_text=raw, verified_facts=verified).auto_apply)

    def test_current_public_registry_does_not_verify_historical_status(self):
        self.assertFalse(recommend_career("한국전력공사", "회계담당", verified_facts={"employment_verified": "yes", "public_role": "yes"}).auto_apply)

    def test_school_and_provisional_tutoring_policy_still_auto_apply(self):
        self.assertTrue(recommend_career("홍천고등학교", "기간제교원").auto_apply)
        self.assertTrue(recommend_career("햇살교습소", "교습자").auto_apply)


if __name__ == "__main__":
    unittest.main()
