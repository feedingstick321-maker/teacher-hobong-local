from __future__ import annotations

import unittest

from certocr.salary_forms import (
    classify_salary_page,
    extract_dates,
    extract_salary_rows,
    merge_salary_rows,
)
from certocr.schema import OcrLine


def lines(*texts: str) -> list[OcrLine]:
    return [OcrLine(text, (50, 80 + i * 50, 1450, 112 + i * 50), 0.95) for i, text in enumerate(texts)]


class SalaryFormClassificationTests(unittest.TestCase):
    def test_classifies_supported_forms_before_generic_certificates(self):
        cases = (
            ("교육공무원 호봉 재획정표", "salary_redetermination"),
            ("교 육 공 무 원 호 봉 획 정 | 표", "salary_determination"),
            ("호봉획정을 위한 경력기간 합산신청서", "career_aggregation_application"),
            ("시간 강사 경력 환산", "hourly_instructor_conversion"),
        )
        for title, expected in cases:
            with self.subTest(title=title):
                self.assertEqual(classify_salary_page(lines(title))[0], expected)

    def test_extracts_adjacent_four_digit_dates(self):
        values = extract_dates("2025-07-142025-07-17|13|42|1")
        self.assertEqual([item[0] for item in values], ["2025-07-14", "2025-07-17"])


class SalaryRowExtractionTests(unittest.TestCase):
    def test_filters_summary_and_reversed_rows(self):
        source = lines(
            "2023-03-01 | 2024-02-29 | 가나고등학교 | 기간제교원 | 100%",
            "잔여월수 | 2025-03-01 | 2024-03-01 | 계",
        )
        rows = extract_salary_rows(source, 1, "salary_determination")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["organization"], "가나고등학교")
        self.assertEqual(rows[0]["position"], "기간제교원")
        self.assertEqual(rows[0]["suggested_type"], "teacher10")

    def test_hourly_page_separates_weekly_and_standard_hours(self):
        source = lines("2025-07-142025-07-17 | 13 | 06.3.1 이후 | 42 | 1")
        row = extract_salary_rows(source, 2, "hourly_instructor_conversion")[0]
        self.assertEqual(row["weeklyHours"], "13")
        self.assertEqual(row["recognized_standard_hours"], "42")
        self.assertEqual(row["suggested_type"], "")
        self.assertIn("근무기관 확인 필요", row["review_reasons"])

    def test_split_application_dates_are_compacted(self):
        source = lines("(주)퍼플아카데미 | 사원 | 2024. | 02.13 | 2024. | 07.12 | 40%")
        row = extract_salary_rows(source, 3, "career_aggregation_application")[0]
        self.assertEqual((row["start"], row["end"]), ("2024-02-13", "2024-07-12"))
        self.assertEqual(row["position"], "사원")
        self.assertEqual(row["suggested_type"], "")
        self.assertEqual(row["approved_rate_percent"], 40)
        self.assertIn("corp4", row["candidate_types"])

    def test_same_period_merges_application_and_hourly_details(self):
        application = extract_salary_rows(
            lines("세마고등학교 | 시간강사 | 2025.07.14 | 2025.07.17"),
            3,
            "career_aggregation_application",
        )[0]
        hourly = extract_salary_rows(
            lines("2025-07-142025-07-17 | 13 | 42 | 1"),
            2,
            "hourly_instructor_conversion",
        )[0]
        merged = merge_salary_rows([application, hourly])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["organization"], "세마고등학교")
        self.assertEqual(merged[0]["weeklyHours"], "13")
        self.assertEqual(merged[0]["suggested_type"], "stAuto")
        self.assertEqual(merged[0]["source_pages"], [3, 2])


if __name__ == "__main__":
    unittest.main()
