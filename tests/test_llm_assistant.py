import json
import unittest
from unittest.mock import patch

from certocr import llm_assistant


class AssistantTests(unittest.TestCase):
    def test_structured_evidence_is_included_without_inventing_unknown_facts(self):
        case = llm_assistant.prepare_case({"organization": "가상기업", "position": "사무직",
            "raw_text": "원본 문장", "verified_facts": {"legal_form": "commercial_company",
            "employment_verified": "yes", "visiting_education": "no", "tax_evidence": "unknown"}})
        self.assertIn("상법상 회사", case["raw_text"])
        self.assertIn("근로계약과 정기 급여", case["raw_text"])
        self.assertIn("방문 교육 업무가 아님", case["raw_text"])
        self.assertNotIn("세무자료", case["raw_text"])
        self.assertTrue(case["raw_text"].startswith("원본 문장"))

    def test_empty_or_oversized_input_is_rejected(self):
        for payload in ({"organization": "기관"}, {"organization": "기관", "position": "직종", "raw_text": "가"*4001}):
            with self.assertRaises(ValueError):
                llm_assistant.prepare_case(payload)

    def test_public_and_shared_servers_rejected(self):
        for endpoint in ("http://127.0.0.1:11434", "http://example.com:1234", "https://127.0.0.1:1234"):
            with self.assertRaises(ValueError):
                llm_assistant.configure(endpoint)

    def test_frozen_cpu_options(self):
        module = llm_assistant.configure("http://127.0.0.1:19001")
        self.assertEqual(module.MODEL_OPTIONS, {"num_gpu":0,"temperature":0,"num_ctx":4096,"num_predict":40,"seed":260926})

    @patch("certocr.llm_assistant._http")
    def test_warmup_requires_cpu_resident(self, http):
        http.side_effect = [
            {"models":[{"name":llm_assistant.MODEL,"digest":llm_assistant.MODEL_DIGEST}]},
            {"done":True}, {"models":[{"name":llm_assistant.MODEL,"digest":llm_assistant.MODEL_DIGEST,"size_vram":0,"size":123}]}]
        result = llm_assistant.warmup("http://127.0.0.1:19001")
        self.assertTrue(result["ready"])
        self.assertEqual(result["size_vram"], 0)
        self.assertFalse(result["external_api_used"])
        self.assertEqual(http.call_args_list[1].args[2]["keep_alive"], -1)

    @patch("certocr.llm_assistant._http")
    def test_gpu_resident_rejected(self, http):
        http.side_effect = [
            {"models":[{"name":llm_assistant.MODEL,"digest":llm_assistant.MODEL_DIGEST}]},
            {"done":True}, {"models":[{"name":llm_assistant.MODEL,"digest":llm_assistant.MODEL_DIGEST,"size_vram":1024}]}]
        with self.assertRaises(ValueError):
            llm_assistant.warmup("http://127.0.0.1:19001")

    def test_llm_candidate_cannot_auto_apply(self):
        module = llm_assistant.configure("http://127.0.0.1:19001")
        result = {"predicted":"corp4","prompt_sha256":"test","retrieved_ids":[],"latency_seconds":1,"actual_model_options":module.MODEL_OPTIONS}
        with patch.object(module,"predict_qwen",return_value=result):
            candidate=llm_assistant.predict({"organization":"가상회사","position":"직원","raw_text":"증빙"},"http://127.0.0.1:19001")
        self.assertFalse(candidate["auto_apply"])
        self.assertTrue(candidate["review_required"])
        self.assertNotIn("prompt",candidate)
