"""Optional packaged CPU assistant. It never decides recognized career periods."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from urllib.request import Request
from certocr.local_http import open_local, validate_endpoint

MODEL = "qwen3.5:4b"
MODEL_DIGEST = "2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd"

VERIFIED_SENTENCES = {
    "legal_form": {
        "commercial_company": "근무 기관은 상법상 회사로 확인됨.",
        "civil_corporation": "근무 기관은 민법상 재단·사단법인으로 확인됨.",
        "individual_business": "근무 기관은 법인격 없는 개인사업체로 확인됨.",
        "public_recognized": "근무 당시 인정 대상 공공기관·공공법인 해당 근거가 확인됨."},
    "employment_verified": {"yes": "근로계약과 정기 급여가 증빙으로 확인됨.",
                            "no": "근로관계 또는 정기 급여가 아님이 확인됨."},
    "academy_registration": {"registered": "근무 당시 학원 등록·교습소 신고 이력 확인됨.",
                             "unregistered": "근무 당시 미등록 학원·미신고 교습소였음이 확인됨."},
    "tax_evidence": {"yes": "해당 근무경력을 입증하는 사업자등록·소득세·부가세 등 세무자료 확인됨.",
                     "no": "검토한 세무자료로는 해당 근무경력을 입증하지 못함."},
    "visiting_education": {"yes": "학생 가정을 직접 방문하여 지도하는 업무임.",
                           "no": "학생 가정 방문 교육 업무가 아님."},
    "public_role": {"yes": "실제 담당 업무는 행정·경영·연구·기술 업무로 확인됨.",
                    "no": "실제 담당 업무가 행정·경영·연구·기술 업무에 속하지 않음."},
}


def prepare_case(payload: dict) -> dict:
    case = {key: str(payload.get(key) or "").strip() for key in ("organization", "position", "raw_text")}
    if not case["organization"] or not case["position"]:
        raise ValueError("근무학교(회사)와 직종을 각각 입력하세요.")
    if len(case["organization"]) > 200 or len(case["position"]) > 200 or len(case["raw_text"]) > 4000:
        raise ValueError("기관명·직종은 각각 200자, 한 경력의 증빙 내용은 4,000자 이내로 입력하세요.")
    facts = payload.get("verified_facts")
    if isinstance(facts, dict):
        sentences = [values.get(facts.get(key)) for key, values in VERIFIED_SENTENCES.items()
                     if isinstance(facts.get(key), str)]
        sentences = [sentence for sentence in sentences if sentence]
        if sentences:
            case["raw_text"] += "\n담당자가 증빙에서 확인한 항목 (원문과 상충하면 review):\n" + "\n".join(sentences)
    return case


def configure(endpoint: str):
    endpoint = validate_endpoint(endpoint)
    os.environ["CERTOCR_ASSISTANT_ENDPOINT"] = endpoint
    from certocr import rag_methods
    rag_methods.OLLAMA_BASE_URL = endpoint.rstrip("/")
    return rag_methods


def _http(endpoint: str, route: str, payload=None):
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(endpoint + route, data=body, headers={"Content-Type": "application/json"})
    with open_local(request, timeout=180) as response:
        return json.load(response)


def warmup(endpoint: str) -> dict:
    methods = configure(endpoint)
    models = _http(endpoint, "/api/tags").get("models", [])
    if not any(row.get("name") == MODEL and row.get("digest") == MODEL_DIGEST for row in models):
        raise ValueError("동봉된 4B 모델이 검증한 모델과 일치하지 않습니다.")
    _http(endpoint, "/api/generate", {"model": MODEL, "stream": False,
          "think": False, "keep_alive": -1, "options": methods.MODEL_OPTIONS})
    loaded = _http(endpoint, "/api/ps").get("models", [])
    resident = next((row for row in loaded if row.get("name") == MODEL), None)
    if not resident:
        raise ValueError("AI 모델을 메모리에 올리지 못했습니다.")
    if resident.get("size_vram") != 0 or resident.get("digest") != MODEL_DIGEST:
        raise ValueError("CPU 전용 모델 준비 검증에 실패했습니다.")
    return {"ready": True, "device": "cpu", "size_vram": 0,
            "resident_bytes": resident.get("size"), "model": MODEL,
            "model_digest": MODEL_DIGEST, "external_api_used": False}


def predict(payload: dict, endpoint: str) -> dict:
    methods = configure(endpoint)
    case = prepare_case(payload)
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    corpus = root / "data" / "dicts" / "llm_development_400.jsonl"
    cases = [json.loads(line) for line in corpus.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    result = methods.predict_qwen(case, "chat_descriptive_rag", methods.CharRetriever(cases), MODEL)
    if result.get("error") or result["predicted"] not in methods.TYPES:
        raise ValueError(result.get("error") or "모델 답변을 참고 후보로 해석하지 못했습니다.")
    if (result.get("ollama", {}).get("prompt_eval_count") or 0) >= methods.MODEL_OPTIONS["num_ctx"] - 64:
        raise ValueError("증빙 내용이 모델 처리 길이에 근접했습니다. 한 경력의 핵심 증빙만 요약한 뒤 다시 요청하세요.")
    return {"suggested_type": result["predicted"], "auto_apply": False,
            "review_required": True, "model": MODEL, "device": "cpu",
            "external_api_used": False, "prompt_sha256": result["prompt_sha256"],
            "retrieved_ids": result["retrieved_ids"], "latency_seconds": result["latency_seconds"],
            "model_options": result["actual_model_options"],
            "model_digest": MODEL_DIGEST,
            "reason": "4B 모델의 참고 후보이며 증빙 확인·법적 인정·호봉 확정 결과가 아닙니다. 자동 적용되지 않습니다."}
