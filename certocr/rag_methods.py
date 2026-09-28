"""Reproducible CPU-only retrieval and Qwen classifiers.

The retrieval corpus is development data only. Legal classes are scenario
classification targets, not final recognition decisions for real personnel.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
import math
import os
import re
import time
from urllib.request import Request
from certocr.local_http import open_local

TYPES = ("corp4", "oth3", "pub5", "ac5", "ac3", "tutoringPending", "relig6", "review")
PENDING_TYPES = {"review", "tutoringPending"}
SCHEMA = {"type": "object", "properties": {"type": {"type": "string", "enum": list(TYPES)}},
          "required": ["type"], "additionalProperties": False}
DESCRIPTIVE_LABELS = {"corp4": "상법회사직원40", "oth3": "민간법인개인회사직원30", "pub5": "공공법인직원50",
                      "ac5": "등록학원강사50", "ac3": "미등록학원강사30", "tutoringPending": "교습소확인필요",
                      "relig6": "종교법인인정직무60", "review": "증빙확인필요"}
OLLAMA_BASE_URL = os.environ.get("CERTOCR_ASSISTANT_ENDPOINT", "").rstrip("/")
MODEL_OPTIONS = {"num_gpu": 0, "temperature": 0, "num_ctx": 4096, "num_predict": 40, "seed": 260926}

RULE_PROMPT = """한국 교원의 과거 경력을 아래 코드로 분류한다. 기관의 이름보다 명시된 사실을 따른다. 외부 지식을 추측하지 않는다. 법적 유형 후보 분류이며 실제 호봉 확정이 아니다.
판단 순서:
1. 교습소 교습자이면 tutoringPending. 신고 여부와 관계없이 담당자의 신고·세무자료 확인을 남긴다.
2. 공공기관 지정/설립근거, 법적 형태, 필요한 고용·급여 증빙이 미확인·미제출이면 review. 명칭에 공공/재단/주식회사만 있다고 증빙을 보충하지 않는다. 부정문을 긍정 근거로 쓰지 않는다.
3. 법에 따른 공기업·준정부기관·지방공사/공단·인정 공공법인에서 행정·경영·연구·기술 업무: pub5. 일반 민간 재단·사단은 제외.
4. 등록 학원의 강사: ac5. 미등록 학원의 강사이고 객관적 소득세·부가세 자료가 있음: ac3. 등록 여부 불명 또는 필요한 세무 증빙 없음: review. 학원 사무직은 강사로 간주하지 않는다.
5. 비영리 종교법인의 교육활동 관련 인정 직무(전임전도사 등): relig6. 종교법인 명칭만 있고 인정 직무 불명: review.
6. 학생 가정 직접 방문지도를 목적으로 하는 회사의 방문 지도 직원: oth3. 상법상 회사여도 이 예외가 우선이다.
7. 상법상 합명·합자·주식·유한회사 직원이고 근로계약·정기보수가 확인됨: corp4. 보험판매원·상점점원·위촉 수수료 직무는 corp4로 인정하지 않고 review.
8. 일반 민법상 사단·재단법인 또는 법인격 없는 개인회사 직원이고 고용·정기보수가 확인됨: oth3.
위 조건을 판단할 사실이 부족하거나 서로 충돌하면 review. JSON {"type":"코드"}만 출력한다.
"""

COMPACT_PROMPT = """사실만 보고 교원 경력의 유형 코드를 선택한다. 부정/미확인을 증명으로 간주하지 않는다.
교습소 교습자=tutoringPending(확인필요).
법정 공기업/준정부기관/지방공사/공단/인정 공공법인 + 행정/경영/연구/기술직=pub5.
등록 학원의 강사=ac5; 미등록 학원 강사+세무 증빙=ac3.
종교법인 교육활동 인정 직무= relig6.
근로계약/정기급여 확인된 상법 회사 직원=corp4. 단 보험판매원/상점점원 제외.
일반 민간 사단/재단/개인기업 직원+고용/급여 확인=oth3. 학생 직접 방문지도 회사도 oth3.
필수 사실이 불명/부족/충돌하거나 위촉 수수료뿐이면 review. 공공이라는 상호는 지정 증거가 아니다.
답변은 JSON {"type":"코드"} 한 개.
"""


def sha(value: str | bytes) -> str:
    return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()


def case_text(case: dict) -> str:
    return "기관: " + str(case.get("organization", "")) + "\n직종: " + str(case.get("position", "")) + "\n기록: " + str(case.get("raw_text", ""))


def retrieval_text(case: dict) -> str:
    # Institution names/numeric dates are not legal ground truth; ignore the name
    # field in retrieval and normalize dates so fabricated name patterns do not
    # drive the result. The record and role still contain relevant legal form.
    text = str(case.get("position", "")) + " " + str(case.get("raw_text", ""))
    text = re.sub(r"\d+(?:[.~/:-]\d+)*", "#", text)
    return re.sub(r"\s+", "", text).lower()


def features(text: str) -> Counter:
    return Counter(text[i:i+n] for n in (2, 3, 4) for i in range(len(text)-n+1))


class CharRetriever:
    """Standard-library TF-IDF cosine search, plus conservative weighted kNN."""

    def __init__(self, cases: list[dict]):
        unique = {}
        for case in cases:
            unique.setdefault((retrieval_text(case), case["gold_type"]), case)
        self.cases = list(unique.values())
        counts = [features(retrieval_text(case)) for case in self.cases]
        document_frequency = Counter(key for item in counts for key in item)
        self.idf = {key: math.log((1+len(counts))/(1+value))+1 for key, value in document_frequency.items()}
        self.vectors = [self._vector(item) for item in counts]

    def _vector(self, counts: Counter) -> dict:
        result = {key: (1+math.log(value))*self.idf[key] for key, value in counts.items() if key in self.idf}
        length = math.sqrt(sum(value*value for value in result.values())) or 1
        return {key: value/length for key, value in result.items()}

    def search(self, case: dict, k: int = 5, exclude_same_text: bool = False) -> list[dict]:
        text = retrieval_text(case)
        query = self._vector(features(text))
        matches = []
        for source, vector in zip(self.cases, self.vectors):
            if exclude_same_text and retrieval_text(source) == text:
                continue
            similarity = sum(value*vector.get(key, 0) for key, value in query.items())
            matches.append({"case": source, "similarity": round(similarity, 6)})
        matches.sort(key=lambda row: (-row["similarity"], row["case"]["id"]))
        return matches[:k]

    def predict(self, case: dict, exclude_same_text: bool = False) -> dict:
        started = time.perf_counter()
        # Frozen from leave-identical-template-out development selection.
        matches = self.search(case, 7, exclude_same_text)
        votes = defaultdict(float)
        for match in matches:
            votes[match["case"]["gold_type"]] += match["similarity"]
        ranked = sorted(votes.items(), key=lambda item: (-item[1], item[0]))
        total = sum(votes.values()) or 1
        margin = ((ranked[0][1] - (ranked[1][1] if len(ranked)>1 else 0))/total) if ranked else 0
        predicted = ranked[0][0] if ranked and matches[0]["similarity"] >= .25 and margin >= .25 else "review"
        return {"predicted": predicted, "latency_seconds": round(time.perf_counter()-started, 6),
                "similarity": matches[0]["similarity"] if matches else 0, "margin": round(margin,6),
                "neighbors": [{"id": row["case"]["id"], "gold_type": row["case"]["gold_type"], "similarity": row["similarity"]} for row in matches]}


def build_prompt(case: dict, variant: str, retriever: CharRetriever | None = None, exclude_same_text: bool = False) -> tuple[str, list[dict]]:
    variant = variant.removeprefix("chat_")
    descriptive = variant.startswith("descriptive")
    base = COMPACT_PROMPT if variant == "compact" or descriptive else RULE_PROMPT
    matches = retriever.search(case, 3, exclude_same_text) if variant in ("rag", "descriptive_rag") and retriever else []
    examples = ""
    if matches:
        examples = "\n아래는 유사하지만 별개의 참고 사례다. 대상의 부정/증빙 차이가 있으면 참고 정답을 복사하지 않는다.\n"
        for number, row in enumerate(matches, 1):
            examples += f"예시 {number}: {case_text(row['case'])}\n정답: {row['case']['gold_type']}\n"
    prompt = base + examples + "\n분류 대상:\n" + case_text(case) + "\nJSON:"
    if descriptive:
        for code, label in DESCRIPTIVE_LABELS.items():
            prompt = prompt.replace(code, label)
    return prompt, matches


def predict_qwen(case: dict, variant: str, retriever: CharRetriever | None = None, model: str = "qwen3.5:0.8b", exclude_same_text: bool = False) -> dict:
    prompt, matches = build_prompt(case, variant, retriever, exclude_same_text)
    payload = {"model": model, "prompt": prompt, "stream": False, "think": False,
               "format": SCHEMA, "keep_alive": -1, "options": MODEL_OPTIONS}
    endpoint = "generate"
    if variant.startswith("chat_"):
        endpoint = "chat"
        base = COMPACT_PROMPT if variant == "chat_compact" or "descriptive" in variant else RULE_PROMPT
        if "descriptive" in variant:
            for code, label in DESCRIPTIVE_LABELS.items():
                base = base.replace(code, label)
            payload["format"] = {"type": "object", "properties": {"type": {"type": "string", "enum": list(DESCRIPTIVE_LABELS.values())}}, "required": ["type"], "additionalProperties": False}
        payload.pop("prompt")
        payload["messages"] = [{"role": "system", "content": base}, {"role": "user", "content": prompt[len(base):]}]
        payload["options"] = {**MODEL_OPTIONS, "presence_penalty": 0}
    started = time.perf_counter()
    raw, error, result = "", None, {}
    try:
        request = Request(OLLAMA_BASE_URL+"/api/"+endpoint, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers={"Content-Type": "application/json"})
        with open_local(request, timeout=180) as response:
            result = json.load(response)
        raw = str((result.get("message") or {}).get("content") if endpoint == "chat" else result.get("response") or "")
        parsed = json.loads(raw)
        predicted = parsed.get("type") if isinstance(parsed, dict) else None
        if "descriptive" in variant:
            predicted = {label: code for code, label in DESCRIPTIVE_LABELS.items()}.get(predicted, predicted)
        if predicted not in TYPES:
            predicted = "invalid"
    except Exception as exc:
        predicted, error = "error", f"{type(exc).__name__}: {exc}"
    return {"predicted": predicted, "latency_seconds": round(time.perf_counter()-started,6),
            "raw_response": raw, "error": error, "prompt_sha256": sha(prompt), "prompt": prompt,
            "endpoint": endpoint, "actual_model_options": payload["options"],
            "retrieved_ids": [row["case"]["id"] for row in matches],
            "ollama": {key: result.get(key) for key in ("model", "done_reason", "total_duration", "load_duration", "prompt_eval_count", "prompt_eval_duration", "eval_count", "eval_duration")}}
