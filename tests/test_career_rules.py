from __future__ import annotations

import unittest

from certocr.career_rules import legal_snapshot, part_time_rule, recommend_career


class LegalSnapshotTests(unittest.TestCase):
    def test_snapshot_records_verified_metadata_as_of_2026_09_26(self):
        snapshot = legal_snapshot()
        self.assertEqual(snapshot["as_of"], "2026-09-26")
        laws = {item["name"]: item for item in snapshot["laws"]}
        self.assertEqual(laws["공무원보수규정"]["effective"], "2026-08-01")
        self.assertEqual(laws["교육공무원법"]["effective"], "2026-02-15")
        self.assertEqual(laws["교원자격검정령 시행규칙"]["effective"], "2026-03-27")
        self.assertEqual(snapshot["salary_guideline_number"], "인사혁신처 예규 제220호")


class CareerRecommendationTests(unittest.TestCase):
    def test_unknown_school_kind_returns_ranked_legal_candidates(self):
        result = recommend_career("가나고등학교", "기간제교원")
        self.assertEqual(result.suggested_type, "")
        self.assertEqual(result.candidate_types, ["pub10", "priv10", "mis8", "unrep5"])
        self.assertTrue(any("국·공립" in value for value in result.required_checks))

    def test_approved_salary_form_keeps_neutral_teacher_100_type(self):
        result = recommend_career("가나고등학교", "기간제교원", approved_rate_percent=100)
        self.assertEqual(result.suggested_type, "teacher10")
        self.assertIn("기존 호봉획정표", result.reason)

    def test_private_school_requires_appointment_report_check(self):
        result = recommend_career("사립 가나고등학교", "기간제교원")
        self.assertEqual(result.suggested_type, "priv10")
        self.assertTrue(any("임면 보고" in value for value in result.required_checks))

    def test_school_hourly_rules_use_12_hour_boundary(self):
        self.assertEqual(recommend_career("가나고등학교", "시간강사", 12).suggested_type, "st3")
        self.assertEqual(recommend_career("가나고등학교", "시간강사", 13).suggested_type, "stAuto")

    def test_university_hourly_uses_weekly_class_hours(self):
        self.assertEqual(recommend_career("한국대학교", "시간강사", 6).suggested_type, "u6")
        self.assertEqual(recommend_career("한국대학교", "시간강사", 11).suggested_type, "u10")

    def test_company_and_academy_require_distinct_statutory_checks(self):
        company = recommend_career("(주)퍼플회사", "사원")
        academy = recommend_career("퍼플학원", "학원강사")
        self.assertEqual(company.suggested_type, "")
        self.assertEqual(academy.suggested_type, "")
        self.assertIn("corp4", company.candidate_types)
        self.assertIn("ac5", academy.candidate_types)
        self.assertIn("ac3", academy.candidate_types)

    def test_tutoring_place_is_pending_even_if_reported_in_source_text(self):
        for raw in ("", "교육감에게 신고된 교습소", "박사 학위 취득 및 교습소 운영"):
            with self.subTest(raw=raw):
                result = recommend_career("햇살수학교습소", "시간강사", raw_text=raw)
                self.assertEqual(result.suggested_type, "tutoringPending")
                self.assertEqual(result.confidence, "low")
                self.assertIn("ac5", result.candidate_types)
                self.assertTrue(any("세무" in value or "소득세" in value for value in result.required_checks))


class PartTimeRuleTests(unittest.TestCase):
    def test_general_short_time_excludes_under_15_and_scales_from_40(self):
        excluded = part_time_rule("corp4", 14)
        scaled = part_time_rule("corp4", 20)
        self.assertTrue(excluded["excluded"])
        self.assertEqual(excluded["factor"], 0.0)
        self.assertEqual(scaled["factor"], 0.5)

    def test_instructor_uses_separate_rule(self):
        self.assertFalse(part_time_rule("stAuto", 20)["applies"])


if __name__ == "__main__":
    unittest.main()
