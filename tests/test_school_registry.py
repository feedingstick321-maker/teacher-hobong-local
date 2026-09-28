from __future__ import annotations

import unittest

from certocr.career_rules import recommend_career
from certocr.school_registry import _index, lookup_school


class SchoolRegistryTests(unittest.TestCase):
    def test_hongcheon_public_school_is_matched_offline(self):
        school = lookup_school("홍천고등학교")
        self.assertEqual((school.status, school.foundation), ("matched", "공립"))
        self.assertIn("S100000530", school.school_codes)
        self.assertEqual(school.year, 2026)
        self.assertEqual(lookup_school("강원특별자치도교육청 홍천고등학교").foundation, "공립")

    def test_known_private_and_national_schools(self):
        self.assertEqual(lookup_school("민족사관고등학교").foundation, "사립")
        self.assertEqual(lookup_school("서울대학교사범대학부설고등학교").foundation, "국립")

    def test_name_matching_does_not_guess_from_substring(self):
        self.assertEqual(lookup_school("신설홍천고등학교").status, "not_found")
        self.assertEqual(lookup_school("홍천고등학교 홍천초등학교").status, "ambiguous")

    def test_mixed_foundation_homonym_is_ambiguous(self):
        _, index = _index()
        mixed = next(name for name, rows in index.items()
                     if len({row["foundation"] for row in rows
                             if not row.get("closed") and not row.get("abolished")}) > 1)
        self.assertEqual(lookup_school(mixed).status, "ambiguous")


class SchoolCareerRecommendationTests(unittest.TestCase):
    def test_public_school_suggests_ten_with_historical_check(self):
        result = recommend_career("홍천고등학교", "기간제교원")
        self.assertEqual(result.suggested_type, "pub10")
        self.assertEqual(result.confidence, "mid")
        self.assertTrue(any("근무 당시" in item for item in result.required_checks))
        self.assertIn("학교알리미", result.reason)

    def test_private_school_keeps_appointment_report_check(self):
        result = recommend_career("민족사관고등학교", "기간제교원")
        self.assertEqual(result.suggested_type, "priv10")
        self.assertTrue(any("임면 보고" in item for item in result.required_checks))

    def test_conflicting_user_label_abstains(self):
        result = recommend_career("사립 홍천고등학교", "기간제교원")
        self.assertEqual(result.suggested_type, "")
        self.assertIn("충돌", result.reason)

    def test_nonexistent_school_still_abstains(self):
        result = recommend_career("가나고등학교", "기간제교원")
        self.assertEqual(result.suggested_type, "")


if __name__ == "__main__":
    unittest.main()
