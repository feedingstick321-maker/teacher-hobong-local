from __future__ import annotations

import unittest

from certocr.hobong import (
    PageExtraction,
    classify_page,
    extract_education_page,
    extract_qualification_page,
    merge_pages,
)
from certocr.schema import OcrLine
from scripts.patch_hobong_html import patch_html


def lines(*texts: str) -> list[OcrLine]:
    result = []
    for i, text in enumerate(texts):
        y = 100 + i * 45
        result.append(OcrLine(text, (100, y, 900, y + 30), 0.96))
    return result


class DocumentRoutingTests(unittest.TestCase):
    def test_classifies_spaced_teacher_certificate_title(self):
        kind, confidence = classify_page(lines("교 원 자 격 증", "중등학교 정교사(2급) 국어"))
        self.assertEqual(kind, "teacher_certificate")
        self.assertGreater(confidence, 0.9)

    def test_classifies_graduation_and_degree(self):
        self.assertEqual(classify_page(lines("졸 업 증 명 서"))[0], "graduation_certificate")
        self.assertEqual(classify_page(lines("학위수여증명서", "교육학석사"))[0], "degree_certificate")


class EducationExtractionTests(unittest.TestCase):
    def test_general_bachelor_maps_to_uni4(self):
        page = extract_education_page(lines(
            "졸업증명서",
            "입학일자: 2000년 03월 02일",
            "졸업년월일: 2007년 08월 17일",
            "학위명: 문학사",
            "제1전공: 한국어문학전공(심화과정)",
            "단 국 대 학 교 총장",
        ), 1, "graduation_certificate", 0.99)
        self.assertEqual(page.fields["edu"], "uni4")
        self.assertEqual(page.fields["institution"], "단국대학교")
        self.assertEqual(page.fields["major"], "한국어문학전공")
        self.assertFalse(page.fields["isSabeom"])

    def test_teacher_college_bachelor_maps_to_edu4(self):
        page = extract_education_page(lines(
            "졸업증명서",
            "입학년월일 2016년 3월 2일",
            "졸업년월일 2020년 2월 25일",
            "대학 사범대학",
            "학과 및 전공 국어교육과",
            "학위 문학사",
            "공 주 대 학 교 총장",
        ), 1, "graduation_certificate", 0.99)
        self.assertEqual(page.fields["edu"], "edu4")
        self.assertTrue(page.fields["isSabeom"])

    def test_master_creates_career_only_with_verified_period(self):
        master = extract_education_page(lines(
            "학위수여증명서 (교육대학원)",
            "임 학 일 자: 2018년 2월 10일",
            "학과/전공: 영어교육",
            "학위수여일자: 2020년 8월 18일",
            "학위: 교육학석사(영어교육)",
            "서강대학교 총장",
        ), 1, "degree_certificate", 0.99)
        result = merge_pages([master], [])
        self.assertEqual(result.basic_info["edu"], "")
        self.assertEqual(result.careers[0]["suggested_type"], "ms10")
        self.assertEqual(result.careers[0]["start"], "2018-02-10")
        self.assertEqual(result.careers[0]["end"], "2020-08-18")

        no_period = PageExtraction(2, "degree_certificate", 0.99, {
            "institution": "단국대학교", "division": "교육대학원",
            "degree_level": "master", "eduText": "단국대학교 교육대학원",
            "admission_date": "", "degree_award_date": "2010-08-20", "edu": "",
        }, ["입학일 미기재"])
        result = merge_pages([no_period], [])
        self.assertEqual(result.careers, [])
        self.assertTrue(result.review_required)

    def test_issuer_doctor_title_does_not_override_master_degree(self):
        page = extract_education_page(lines(
            "학위기",
            "교육대학원에서 교육학과 석사과정을 이수",
            "교육학석사(국어교육)의 자격을 갖추었으므로",
            "교육학석사 학위를 수여함",
            "2010년 8월 20일",
            "교육대학원장 철학박사 홍길동",
            "단국대학교 총장",
        ), 1, "degree_certificate", .99)
        self.assertEqual(page.fields["degree_level"], "master")
        self.assertEqual(page.fields["degree_award_date"], "2010-08-20")


class QualificationAndMergeTests(unittest.TestCase):
    def test_highest_teacher_qualification_is_selected(self):
        grade2 = extract_qualification_page(lines("교원자격증", "중등학교 정교사(2급) 국어"), 1, .99)
        grade1 = extract_qualification_page(lines("교원자격증", "중등학교 정교사(1급) 국어"), 2, .99)
        result = merge_pages([grade2, grade1], [])
        self.assertEqual(result.basic_info["qual"], "정교사1급")
        self.assertEqual(grade1.fields["subject"], "국어")

    def test_graduate_degree_does_not_replace_undergraduate_edu(self):
        bachelor = PageExtraction(1, "graduation_certificate", .99, {
            "edu": "uni4", "eduText": "단국대학교 한국어문학전공",
            "degree_level": "bachelor", "isSabeom": False,
        })
        master = PageExtraction(2, "degree_certificate", .99, {
            "edu": "", "eduText": "단국대학교 교육대학원 국어교육",
            "degree_level": "master", "admission_date": "",
            "degree_award_date": "2010-08-20",
        })
        result = merge_pages([bachelor, master], [])
        self.assertEqual(result.basic_info["edu"], "uni4")
        self.assertEqual(result.basic_info["eduText"], "단국대학교 교육대학원 국어교육")

    def test_subject_repairs_single_bad_major_prefix(self):
        qual = extract_qualification_page(lines("교원자격증", "중등학교 정교사(2급) 국어"), 1, .99)
        bachelor = PageExtraction(2, "graduation_certificate", .99, {
            "edu": "edu4", "eduText": "공주대학교 사범대학 카어교육과",
            "institution": "공주대학교", "division": "사범대학",
            "major": "카어교육과", "degree_level": "bachelor", "isSabeom": True,
        })
        result = merge_pages([qual, bachelor], [])
        self.assertEqual(result.basic_info["eduText"], "공주대학교 사범대학 국어교육과")


class FrontendPatchTests(unittest.TestCase):
    def test_patch_keeps_export_api_and_redirects_only_extract(self):
        source = """<script>
const API_BASE_URL = 'https://example.test';
if(data.basic_info.edu) state.edu = data.basic_info.edu;
fetch(API_BASE_URL + '/api/extract', {});
fetch(API_BASE_URL + '/api/export-excel', {});
</script>"""
        patched = patch_html(source)
        self.assertIn("window.location.protocol === 'file:'", patched)
        self.assertIn("http://127.0.0.1:8765", patched)
        self.assertIn("fetch(OCR_API_BASE_URL + '/api/extract'", patched)
        self.assertIn("fetch(API_BASE_URL + '/api/export-excel'", patched)
        self.assertIn("basic_info.eduText", patched)


if __name__ == "__main__":
    unittest.main()
