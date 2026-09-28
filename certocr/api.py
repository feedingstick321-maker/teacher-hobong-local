"""로컬 호봉 OCR HTTP API와 동일 화면 정적 호스팅."""
from __future__ import annotations

import base64
import binascii
from functools import lru_cache
from pathlib import Path
import re
from threading import Lock
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel

from certocr import config
from certocr.career_rules import recommend_career
from certocr.export import build_pdf, build_xlsx
from certocr.hobong import analyze_bytes
from certocr.ocr import OcrEngine
from certocr.salary_forms import analyze_salary_bytes


class ExtractRequest(BaseModel):
    base64: str
    mimeType: str = ""
    prompt: str | None = None  # 기존 Gemini 프론트와의 요청 호환용. 사용하지 않는다.


class CareerRecommendationRequest(BaseModel):
    organization: str = ""
    position: str = ""
    weekly_hours: str | None = None
    raw_text: str = ""
    verified_facts: dict[str, str] | None = None


app = FastAPI(title="certocr local hobong engine", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "null",  # file:///D:/.../hobong.html에서 직접 연 경우
        "http://127.0.0.1:8765",
        "http://localhost:8765",
    ],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
_ocr_lock = Lock()


@lru_cache(maxsize=1)
def _engine() -> OcrEngine:
    # 학교 배포 진입점은 환경변수와 무관하게 CPU만 사용한다.
    return OcrEngine(device="cpu")


@app.middleware("http")
async def private_network_header(request: Request, call_next):
    response = await call_next(request)
    if request.method == "OPTIONS" and request.headers.get("access-control-request-private-network") == "true":
        response.headers["Access-Control-Allow-Private-Network"] = "true"
    return response


@app.get("/")
@app.get("/hobong.html")
def hobong_page():
    page = config.ROOT / "web" / "hobong.html"
    if not page.is_file():
        return JSONResponse({"error": "로컬 hobong.html이 없습니다."}, status_code=404)
    return FileResponse(
        page,
        media_type="text/html; charset=utf-8",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "engine": "local-rapidocr",
        "device": "cpu",
        "execution_provider": "CPUExecutionProvider",
        "external_api_used": False,
    }


@app.post("/api/extract")
def extract(payload: ExtractRequest):
    try:
        raw = base64.b64decode(payload.base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        return JSONResponse({"error": "base64 파일 데이터가 올바르지 않습니다.", "detail": str(exc)}, status_code=400)
    try:
        # ONNX 세션은 재사용하고 학교 PC의 CPU에서 문서 단위로 직렬 처리한다.
        with _ocr_lock:
            result = analyze_bytes(raw, payload.mimeType, _engine())
        return result.to_dict()
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception as exc:
        return JSONResponse({"error": "로컬 OCR 처리에 실패했습니다.", "detail": str(exc)}, status_code=500)


@app.post("/api/extract-salary")
def extract_salary(payload: ExtractRequest):
    try:
        raw = base64.b64decode(payload.base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        return JSONResponse({"error": "base64 파일 데이터가 올바르지 않습니다.", "detail": str(exc)}, status_code=400)
    try:
        with _ocr_lock:
            result = analyze_salary_bytes(raw, payload.mimeType, _engine())
        return result.to_dict()
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception as exc:
        return JSONResponse({"error": "기존 호봉자료 분석에 실패했습니다.", "detail": str(exc)}, status_code=500)


@app.post("/api/recommend-career")
def recommend_career_endpoint(payload: CareerRecommendationRequest):
    return recommend_career(
        payload.organization, payload.position, payload.weekly_hours, payload.raw_text,
        verified_facts=payload.verified_facts,
    ).to_dict()


def _filename(payload: dict, extension: str) -> str:
    name = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "_", str(payload.get("name") or "대상자")).strip(" .")
    return f"호봉획정표_{name or '대상자'}.{extension}"


def _attachment(content: bytes, media_type: str, filename: str) -> Response:
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            "Cache-Control": "no-store",
        },
    )


@app.post("/api/export-excel")
def export_excel(payload: dict):
    try:
        content = build_xlsx(payload)
        return _attachment(
            content,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            _filename(payload, "xlsx"),
        )
    except Exception as exc:
        return JSONResponse({"error": "엑셀 생성에 실패했습니다.", "detail": str(exc)}, status_code=500)


@app.post("/api/export-pdf")
def export_pdf(payload: dict):
    try:
        content = build_pdf(payload)
        return _attachment(content, "application/pdf", _filename(payload, "pdf"))
    except Exception as exc:
        return JSONResponse({"error": "PDF 생성에 실패했습니다.", "detail": str(exc)}, status_code=500)
