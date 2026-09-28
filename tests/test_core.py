from __future__ import annotations

import hashlib
import random
import tempfile
import unittest
from pathlib import Path

from certocr.extract.correct import normalize_date, parse_duration
from certocr.extract.structure import structure_lines
from certocr.ocr.engine import OcrEngine
from certocr.ocr.metrics import cer
from certocr.pipeline import process
from certocr.schema import OcrLine
from certocr.synth import generate_certificate


class DateTests(unittest.TestCase):
    def test_dates(self):
        cases = {"2023. 8.14.": "2023-08-14", "2022.03.01": "2022-03-01", "25.6.20.": "2025-06-20", "현재": "재직중"}
        for raw, expected in cases.items():
            self.assertEqual(normalize_date(raw), expected)
        self.assertIsNone(normalize_date("2023.13.45"))

    def test_duration(self):
        self.assertEqual(parse_duration("1년 6월 7일"), {"years": 1, "months": 6, "days": 7})
        self.assertEqual(parse_duration("2개월 19일"), {"years": 0, "months": 2, "days": 19})
        self.assertEqual(parse_duration("월 4일"), {"years": 0, "months": 0, "days": 4})

    def test_org_and_position_normalization(self):
        from certocr.extract.correct import correct_organization, find_organizations, normalize_position
        self.assertEqual(correct_organization("매고등학교"), "이매고등학교")
        self.assertEqual(correct_organization("임곡증학교"), "임곡중학교")
        self.assertIn("향남고등학교", find_organizations("근무부서 향남고"))
        self.assertEqual(normalize_position("두드림학교 / 교과학습 / 강사"), "교과학습강사")


class SynthTests(unittest.TestCase):
    def test_deterministic_and_bounds(self):
        a, ga = generate_certificate(random.Random(17), "neis")
        b, gb = generate_certificate(random.Random(17), "neis")
        self.assertEqual(hashlib.sha256(a.tobytes()).digest(), hashlib.sha256(b.tobytes()).digest())
        self.assertEqual(ga.cert, gb.cert)
        for _, (x1, y1, x2, y2) in ga.lines:
            self.assertGreaterEqual(min(x1, y1), 0)
            self.assertLessEqual(x2, a.width)
            self.assertLessEqual(y2, a.height)

    def test_layouts_and_invalid(self):
        for name in ("neis", "legacy", "variant", "gov24", "private", "legacy_hanja"):
            image, gt = generate_certificate(random.Random(1), name)
            self.assertEqual(image.size, (1654, 2339))
            self.assertTrue(gt.lines)
        with self.assertRaises(ValueError):
            generate_certificate(random.Random(1), "unknown")


class StructureTests(unittest.TestCase):
    def test_neis_row_and_noise(self):
        lines = [
            OcrLine("FAX 0310000000 0001/0001", (0, 0, 300, 20), .9),
            OcrLine("성명 홍길동", (20, 100, 180, 130), .98),
            OcrLine("생년월일 1980. 3. 2.", (400, 100, 700, 130), .97),
            OcrLine("계약제 구분 주당근무시간", (20, 200, 500, 230), .96),
            OcrLine("2022-03-01", (20, 300, 150, 330), .99),
            OcrLine("2023-02-28", (180, 300, 310, 330), .99),
            OcrLine("기간제", (340, 300, 410, 330), .99),
            OcrLine("수학", (440, 300, 500, 330), .99),
            OcrLine("20", (520, 300, 550, 330), .99),
            OcrLine("가람초등학교", (600, 300, 760, 330), .99),
            OcrLine("2026. 7. 12.", (400, 800, 600, 830), .99),
            OcrLine("가람초등학교장", (400, 850, 650, 880), .99),
        ]
        result = structure_lines(lines)
        self.assertEqual(len(result.cert.records), 1)
        self.assertEqual(result.cert.records[0].org, "가람초등학교")
        self.assertEqual(result.cert.records[0].position, "기간제교원")
        self.assertEqual(result.cert.records[0].weekly_hours, "20")
        self.assertEqual(result.cert.layout, "neis")

    def test_overlapping_contract_end_is_repaired(self):
        lines = [
            OcrLine("2023-03-01", (10,100,120,130), .95), OcrLine("2024-08-26", (140,100,250,130), .95), OcrLine("기간제교사", (270,100,380,130), .95),
            OcrLine("2024-03-01", (10,160,120,190), .95), OcrLine("2025-02-28", (140,160,250,190), .95), OcrLine("기간제교사", (270,160,380,190), .95),
        ]
        result = structure_lines(lines)
        self.assertEqual(result.cert.records[0].end_date, "2024-02-29")
        self.assertIn("기간 중첩 OCR 보정", result.flags)


class MetricAndErrorTests(unittest.TestCase):
    def test_cer(self):
        self.assertAlmostEqual(cer("가나다", "가라다"), 1/3)
        self.assertEqual(cer("", ""), 0)
        self.assertEqual(cer("", "x"), 1)

    def test_missing_models_and_bad_image(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(FileNotFoundError):
                OcrEngine(Path(td))
            bad = Path(td) / "x.txt"; bad.write_text("not image", encoding="utf-8")
            with self.assertRaises(ValueError):
                process(bad)

    def test_records_only_json_and_review(self):
        from certocr.schema import CareerCertificate, CareerRecord, ExtractionResult
        record = CareerRecord("가람초등학교", "기간제교사", "2025-03-01", "2026-02-28")
        result = ExtractionResult(CareerCertificate("", "", [record]), {
            "records[0].org": .99, "records[0].position": .99,
            "records[0].start_date": .99, "records[0].end_date": .99,
        })
        payload = result.records_json_dict()
        self.assertFalse(payload["검토필요"])
        self.assertEqual(payload["경력사항"][0]["근무학교(회사)"], "가람초등학교")


if __name__ == "__main__":
    unittest.main()
