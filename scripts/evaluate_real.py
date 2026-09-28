"""fingerprint 검증과 행 순서 무관 매칭을 적용한 실물 평가."""
from __future__ import annotations

import argparse
import itertools
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from certocr import config
from certocr.benchmark import current_manifest, verify_manifest

SPECIAL = {"", "REDACTED", "UNREADABLE"}
META_FIELDS = ()
RECORD_FIELDS = ("org", "position", "start_date", "end_date")


def _norm(v) -> str:
    value = "".join(str(v or "").replace("재직중", "현재").split())
    return value.replace("기간제교사", "기간제교원").replace("두드림학교교과학습강사", "교과학습강사")


def _field_norm(field: str, value) -> str:
    normalized = _norm(value)
    if field == "org":
        normalized = normalized.replace("경기도교육청", "")
    return normalized


def _record_cost(gt: dict, pred: dict) -> int:
    return sum(_norm(gt.get(k)) != _norm(pred.get(k)) for k in ("start_date", "end_date", "org") if gt.get(k) not in SPECIAL)


def match_records(gt_records: list[dict], pred_records: list[dict]) -> list[dict]:
    if not gt_records:
        return []
    if not pred_records:
        return [{} for _ in gt_records]
    best, best_cost = None, 10**9
    choices = pred_records + [{}] * max(0, len(gt_records) - len(pred_records))
    for indexes in itertools.permutations(range(len(choices)), min(len(gt_records), len(choices))):
        candidate = [choices[i] for i in indexes]
        cost = sum(_record_cost(g, p) for g, p in zip(gt_records, candidate))
        if cost < best_cost:
            best, best_cost = candidate, cost
    return best or [{} for _ in gt_records]


def score_document(gt: dict, pred: dict) -> tuple[int, int, dict[str, tuple[int, int]]]:
    ok = total = 0; by_field: dict[str, tuple[int, int]] = {}
    for key in META_FIELDS:
        if gt.get(key) not in SPECIAL:
            hit = int(_norm(gt[key]) == _norm(pred.get(key))); ok += hit; total += 1; by_field[key] = (hit, 1)
    matched = match_records(gt.get("records", []), pred.get("records", []))
    for rec, candidate in zip(gt.get("records", []), matched):
        for key in RECORD_FIELDS:
            if rec.get(key) not in SPECIAL:
                hit = int(_field_norm(key, rec[key]) == _field_norm(key, candidate.get(key))); ok += hit; total += 1
                a, b = by_field.get("record."+key, (0, 0)); by_field["record."+key] = (a+hit, b+1)
    return ok, total, by_field


def _percentile(values: list[float], q: float) -> float:
    if not values: return 0.0
    values = sorted(values); pos = (len(values)-1)*q; lo = int(pos); hi = min(lo+1, len(values)-1)
    return values[lo] + (values[hi]-values[lo])*(pos-lo)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--labels", type=Path, default=config.DATA / "real_samples" / "real_labels.jsonl")
    p.add_argument("--folds", type=Path, default=config.DATA / "real_samples" / "folds.json")
    p.add_argument("--predictions", type=Path, default=config.OUT / "real_predictions.jsonl")
    p.add_argument("--out", type=Path, default=config.OUT / "real_report.md")
    args = p.parse_args()
    labels = {x["image_id"]: x for x in map(json.loads, args.labels.read_text(encoding="utf-8").splitlines())}
    preds = {x["image_id"]: x for x in map(json.loads, args.predictions.read_text(encoding="utf-8").splitlines())}
    manifest_path = args.predictions.with_suffix(".manifest.json")
    if not manifest_path.is_file():
        print(f"fingerprint manifest missing: {manifest_path}", file=sys.stderr); return 3
    saved = json.loads(manifest_path.read_text(encoding="utf-8"))
    mismatches = verify_manifest(saved, current_manifest(args.labels, args.folds, len(labels)))
    if mismatches:
        print("fingerprint mismatch: " + ", ".join(mismatches), file=sys.stderr); return 4
    folds = json.loads(args.folds.read_text(encoding="utf-8"))["folds"]
    groups = defaultdict(lambda: [0, 0, [], 0])
    field_stats = defaultdict(lambda: [0, 0])
    review_tp = review_fn = auto_ok = auto_total = 0
    doc_accs = []
    for image_id, row in labels.items():
        pred_row = preds.get(image_id, {}); pcert = pred_row.get("prediction", {}).get("cert", {})
        ok, total, per_field = score_document(row["cert"], pcert); doc_acc = ok/total if total else 0; doc_accs.append(doc_acc)
        for field, (a,b) in per_field.items(): field_stats[field][0] += a; field_stats[field][1] += b
        fold_name = next((f["name"] for f in folds if image_id in f["images"]), "unassigned")
        sec = float(pred_row.get("seconds", 0));
        for group in ("all", "fold:"+fold_name, "layout:"+row["cert"]["layout"], "quality:"+row["quality"]):
            groups[group][0] += ok; groups[group][1] += total; groups[group][2].append(sec); groups[group][3] += 1
        unreadable = "UNREADABLE" in json.dumps(row["cert"], ensure_ascii=False)
        review = bool(pred_row.get("needs_review", pred_row.get("prediction", {}).get("flags")))
        if unreadable: review_tp += int(review); review_fn += int(not review)
        if not review: auto_total += 1; auto_ok += int(ok == total)
    body = ["# certocr 경력사항 전용 실물 평가", "", "평가 필드: 근무 시작일, 근무 종료일, 근무학교(회사), 직종", "", f"Fingerprint: `{saved['code_sha256'][:16]}` / GPU physical {config.GPU_INDEX}", "", "| group | pages | micro accuracy | P50 sec | P95 sec |", "|---|---:|---:|---:|---:|"]
    for key in sorted(groups, key=lambda x: (x != "all", x)):
        ok,total,times,n = groups[key]; body.append(f"| {key} | {n} | {ok/total if total else 0:.4f} | {_percentile(times,.5):.3f} | {_percentile(times,.95):.3f} |")
    body += ["", f"- Document macro accuracy: {statistics.mean(doc_accs):.4f}", f"- Unreadable review recall: {review_tp}/{review_tp+review_fn} ({review_tp/(review_tp+review_fn) if review_tp+review_fn else 1:.1%})", f"- Auto-accept precision: {auto_ok}/{auto_total} ({auto_ok/auto_total if auto_total else 1:.1%}); coverage {auto_total}/{len(labels)}", "", "## Field accuracy", "", "| field | correct | total | accuracy |", "|---|---:|---:|---:|"]
    for field in sorted(field_stats):
        a,b = field_stats[field]; body.append(f"| {field} | {a} | {b} | {a/b:.4f} |")
    args.out.write_text("\n".join(body)+"\n", encoding="utf-8"); print(args.out); return 0


if __name__ == "__main__":
    raise SystemExit(main())
