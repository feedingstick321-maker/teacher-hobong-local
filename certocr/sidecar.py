"""Tauri가 호출하는 CPU 전용 Python 사이드카 명령."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from certocr.export import build_pdf, build_xlsx
from certocr.career_rules import recommend_career
from certocr.hobong import analyze_bytes
from certocr.ocr import OcrEngine
from certocr.salary_forms import analyze_salary_bytes


def _write_status(**values) -> None:
    sys.stdout.write(json.dumps(values, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _load_payload(path: str) -> dict:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("요청 JSON은 객체여야 합니다.")
    return value


def main(argv: list[str] | None = None) -> int:
    # Frozen Windows executables otherwise use the local code page for pipes,
    # while Tauri decodes IPC process output as UTF-8.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="certocr-sidecar")
    parser.add_argument("--version", action="version", version="certocr-sidecar 1.0.0")
    commands = parser.add_subparsers(dest="command", required=True)

    extract = commands.add_parser("extract")
    extract.add_argument("--input", required=True)
    extract.add_argument("--output", required=True)
    extract.add_argument("--mime", default="")

    extract_salary = commands.add_parser("extract-salary")
    extract_salary.add_argument("--input", required=True)
    extract_salary.add_argument("--output", required=True)
    extract_salary.add_argument("--mime", default="")

    recommend = commands.add_parser("recommend-career")
    recommend.add_argument("--request", required=True)
    recommend.add_argument("--output", required=True)

    for name in ("warmup-llm", "recommend-llm"):
        assistant = commands.add_parser(name)
        assistant.add_argument("--endpoint", required=True)
        assistant.add_argument("--output", required=True)
        if name == "recommend-llm":
            assistant.add_argument("--request", required=True)

    for name in ("export-excel", "export-pdf"):
        export = commands.add_parser(name)
        export.add_argument("--request", required=True)
        export.add_argument("--output", required=True)

    args = parser.parse_args(argv)
    try:
        if args.command in ("warmup-llm", "recommend-llm"):
            from certocr.llm_assistant import predict, warmup
            result = warmup(args.endpoint) if args.command == "warmup-llm" else predict(_load_payload(args.request), args.endpoint)
            target = Path(args.output)
            target.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
            _write_status(ok=True, output=str(target), device="cpu", external_api_used=False)
            return 0
        if args.command in ("extract", "extract-salary"):
            source = Path(args.input)
            analyzer = analyze_salary_bytes if args.command == "extract-salary" else analyze_bytes
            result = analyzer(source.read_bytes(), args.mime, OcrEngine(device="cpu"))
            target = Path(args.output)
            target.write_text(json.dumps(result.to_dict(), ensure_ascii=False), encoding="utf-8")
            _write_status(ok=True, output=str(target), device="cpu")
            return 0

        payload = _load_payload(args.request)
        if args.command == "recommend-career":
            result = recommend_career(
                organization=str(payload.get("organization") or ""),
                position=str(payload.get("position") or ""),
                weekly_hours=payload.get("weekly_hours"),
                raw_text=str(payload.get("raw_text") or ""),
                verified_facts=payload.get("verified_facts") if isinstance(payload.get("verified_facts"), dict) else None,
            )
            target = Path(args.output)
            target.write_text(json.dumps(result.to_dict(), ensure_ascii=False), encoding="utf-8")
            _write_status(ok=True, output=str(target), device="cpu")
            return 0
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        content = build_xlsx(payload) if args.command == "export-excel" else build_pdf(payload)
        target.write_bytes(content)
        _write_status(ok=True, output=str(target), bytes=len(content), device="cpu")
        return 0
    except Exception as exc:
        sys.stderr.write(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False) + "\n")
        sys.stderr.flush()
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
