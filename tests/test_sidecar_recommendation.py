from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from certocr.sidecar import main


class SidecarRecommendationTests(unittest.TestCase):
    def test_verified_facts_are_used_by_real_sidecar_command(self):
        with tempfile.TemporaryDirectory() as directory:
            request = Path(directory) / "request.json"
            output = Path(directory) / "result.json"
            request.write_text(json.dumps({
                "organization": "가상기획",
                "position": "행정 직원",
                "verified_facts": {"legal_form": "individual_business", "employment_verified": "yes"},
            }, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(main(["recommend-career", "--request", str(request), "--output", str(output)]), 0)
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["suggested_type"], "oth3")
            self.assertEqual(result["decision_status"], "candidate")
            self.assertTrue(any(e["source"] == "user_verified" for e in result["evidence"]))

    def test_official_institution_without_employment_stays_review(self):
        with tempfile.TemporaryDirectory() as directory:
            request = Path(directory) / "request.json"
            output = Path(directory) / "result.json"
            request.write_text(json.dumps({"organization": "한국전력공사", "position": "회계담당"}, ensure_ascii=False), encoding="utf-8")
            self.assertEqual(main(["recommend-career", "--request", str(request), "--output", str(output)]), 0)
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["suggested_type"], "")
            self.assertEqual(result["decision_status"], "review")
            self.assertIn("pub5", result["candidate_types"])

    def test_offline_recommendation_command(self):
        with tempfile.TemporaryDirectory() as directory:
            request = Path(directory) / "request.json"
            output = Path(directory) / "result.json"
            request.write_text(json.dumps({
                "organization": "홍천고등학교",
                "position": "기간제교원",
                "raw_text": "홍천고등학교 기간제교원",
            }, ensure_ascii=False), encoding="utf-8")
            code = main(["recommend-career", "--request", str(request), "--output", str(output)])
            self.assertEqual(code, 0)
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["suggested_type"], "pub10")
            self.assertIn("학교알리미", result["reason"])


if __name__ == "__main__":
    unittest.main()
