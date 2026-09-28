from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from certocr.sidecar import main


class SidecarTests(unittest.TestCase):
    def test_korean_errors_are_utf8_even_with_windows_legacy_pipe_encoding(self):
        with tempfile.TemporaryDirectory() as temp:
            request = Path(temp) / "request.json"
            request.write_text("[]", encoding="utf-8")
            result = subprocess.run([sys.executable, "-m", "certocr.sidecar", "recommend-career",
                "--request", str(request), "--output", str(Path(temp)/"result.json")],
                capture_output=True, env={**os.environ, "PYTHONIOENCODING": "cp949"}, timeout=30)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stderr.decode("utf-8"))["error"], "요청 JSON은 객체여야 합니다.")

    def test_export_commands_write_valid_files(self):
        payload = {
            "name": "홍길동", "affiliation": "가나다고등학교", "position": "교사",
            "qual": "정교사(2급)", "edu": "한국대학교 국어교육과", "grade": "10",
            "careers": [], "total": {},
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            request = root / "request.json"
            request.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            xlsx = root / "result.xlsx"
            pdf = root / "result.pdf"
            self.assertEqual(main(["export-excel", "--request", str(request), "--output", str(xlsx)]), 0)
            self.assertEqual(main(["export-pdf", "--request", str(request), "--output", str(pdf)]), 0)
            self.assertTrue(xlsx.read_bytes().startswith(b"PK"))
            self.assertTrue(pdf.read_bytes().startswith(b"%PDF-"))


if __name__ == "__main__":
    unittest.main()
