from __future__ import annotations

from io import BytesIO
import unittest
from zipfile import ZipFile

import fitz

from certocr.export import build_pdf, build_xlsx


PAYLOAD = {
    "name": "홍길동",
    "affiliation": "가나다고등학교",
    "position": "교사",
    "proposedPosition": "교사",
    "qual": "정교사(2급)",
    "edu": "한국대학교 국어교육과",
    "grade": "10",
    "careerTotal": "1년 0월 0일",
    "deductYears": "0년 0월 0일",
    "requiredYears": "1년",
    "baseGrade": "8호봉",
    "eduYears": "0년",
    "bonusYears": "1년",
    "remain": "2월 3일",
    "finalGrade": "10호봉",
    "nextPromo": "2027-01-01",
    "printDate": "2026년 7월 12일",
    "authorRank": "교육행정8급",
    "author": "박담당",
    "careers": [{
        "content": "가나다고등학교 기간제교원",
        "sY": "2024", "sM": "03", "sD": "01",
        "eY": "2025", "eM": "02", "eD": "28",
        "rate": "100", "cY": "1", "cM": "0", "cD": "0", "note": "",
    }],
    "total": {"Y": "1", "M": "0", "D": "0"},
}


class ExportTests(unittest.TestCase):
    def test_document_text_is_not_a_formula_or_external_link(self):
        payload = {**PAYLOAD, "name": '=HYPERLINK("https://example.invalid", "name")',
                   "careers": [{"content": "=1+1", "note": "https://example.invalid"}]}
        with ZipFile(BytesIO(build_xlsx(payload))) as archive:
            sheet = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
            self.assertNotIn("<f>", sheet)
            self.assertNotIn("<hyperlink", sheet)
            self.assertIn("=1+1", archive.read("xl/sharedStrings.xml").decode("utf-8"))

    def test_xlsx_is_valid_and_contains_korean_form(self):
        data = build_xlsx(PAYLOAD)
        self.assertTrue(data.startswith(b"PK"))
        with ZipFile(BytesIO(data)) as archive:
            self.assertIn("xl/worksheets/sheet1.xml", archive.namelist())
            shared = archive.read("xl/sharedStrings.xml").decode("utf-8")
            self.assertIn("호봉획정표", shared)
            self.assertIn("제청(내신) 직위(직급)", shared)
            self.assertIn("환산 총경력 연수", shared)
            self.assertIn("가나다고등학교 기간제교원", shared)
            self.assertIn("법령 자료 확인 2026-09-26", shared)
            workbook = archive.read("xl/workbook.xml").decode("utf-8")
            self.assertIn("호봉획정표", workbook)

    def test_pdf_is_valid_a4_and_contains_korean_form(self):
        data = build_pdf(PAYLOAD)
        self.assertTrue(data.startswith(b"%PDF-"))
        document = fitz.open(stream=data, filetype="pdf")
        self.assertGreaterEqual(document.page_count, 1)
        page = document[0]
        self.assertAlmostEqual(page.rect.width, 595.28, delta=1.0)
        self.assertAlmostEqual(page.rect.height, 841.89, delta=1.0)
        text = "\n".join(p.get_text() for p in document)
        self.assertIn("호봉획정표", text)
        self.assertIn("경력 연수", text)
        self.assertIn("사정 호봉에 필요한 경력 연수", text)
        self.assertIn("가나다고등학교", text)
        self.assertIn("법령 자료 확인 2026-09-26", text)
        document.close()

    def test_empty_career_still_generates_both_formats(self):
        payload = dict(PAYLOAD)
        payload["careers"] = []
        self.assertGreater(len(build_xlsx(payload)), 1000)
        self.assertGreater(len(build_pdf(payload)), 1000)

    def test_more_than_thirteen_careers_continues_on_second_form_page(self):
        payload = dict(PAYLOAD)
        payload["careers"] = [{**PAYLOAD["careers"][0], "content": f"가상 경력 {i}"} for i in range(15)]
        document = fitz.open(stream=build_pdf(payload), filetype="pdf")
        self.assertEqual(document.page_count, 2)
        self.assertIn("가상 경력 14", document[1].get_text())
        document.close()
        with ZipFile(BytesIO(build_xlsx(payload))) as archive:
            self.assertIn("xl/worksheets/sheet2.xml", archive.namelist())

    def test_tutoring_review_note_and_new_career_fields_survive_export(self):
        payload = dict(PAYLOAD)
        payload["careers"] = [{
            "start": "2022.03.01", "end": "2023.02.28",
            "content": "햇살수학교습소 교습자", "rawPeriod": "1년 0월 0일",
            "rate": "50%", "convertedPeriod": "0년 6월 0일",
            "note": "확인 필요·50% 잠정",
        }]
        pdf = fitz.open(stream=build_pdf(payload), filetype="pdf")
        pdf_text = pdf[0].get_text()
        for value in ("햇살수학교습소", "2022.03.01", "50%", "확인 필요", "0년 6월 0일"):
            self.assertIn(value, pdf_text)
        pdf.close()
        with ZipFile(BytesIO(build_xlsx(payload))) as archive:
            shared = archive.read("xl/sharedStrings.xml").decode("utf-8")
            for value in ("햇살수학교습소", "2022.03.01", "50%", "확인 필요·50% 잠정"):
                self.assertIn(value, shared)


if __name__ == "__main__":
    unittest.main()
