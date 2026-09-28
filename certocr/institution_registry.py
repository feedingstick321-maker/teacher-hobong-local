"""Official institution snapshots for offline career-category suggestions.

The registry identifies an institution, not a person's recognized career rate.
Exact names and explicitly recorded aliases are accepted. A current designation
does not establish the designation, duties, or employment relation of past work.
No network call is made by this module, including in frozen desktop builds.
"""
from __future__ import annotations

from functools import lru_cache
import json
import re
import unicodedata

from certocr.config import DICTS


SNAPSHOT_PATH = DICTS / "career_institutions_2026.json"


def _normalize(value: str) -> str:
    """Only harmless presentation differences; never strip legal-form words."""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value or "")).casefold()


@lru_cache(maxsize=1)
def _index() -> tuple[dict, dict[str, list[dict]]]:
    try:
        snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        groups = snapshot["groups"]
        if (not isinstance(groups, list)
                or not isinstance(snapshot["required_checks"], list)
                or not all(isinstance(item, str) for item in snapshot["required_checks"])):
            return {}, {}
        result: dict[str, list[dict]] = {}
        overrides = snapshot.get("recognition_overrides", {})
        aliases = snapshot.get("aliases", {})
        for group in groups:
            if (not isinstance(group["names"], list)
                    or not all(isinstance(item, str) for item in group["names"])):
                return {}, {}
            for name in group["names"]:
                row = {
                    "canonical_name": name,
                    "legal_form": group["legal_form"],
                    "suggested_type": group["suggested_type"],
                    "source_url": group["source_url"],
                    "as_of": group.get("as_of", snapshot["as_of"]),
                    "legal_basis": group.get("legal_basis", ""),
                }
                row.update(overrides.get(name, {}))
                for label in [name, *aliases.get(name, [])]:
                    key = _normalize(label)
                    if key:
                        result.setdefault(key, []).append(row)
        return snapshot, result
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        # A missing/corrupt bundled snapshot must not silently imply eligibility.
        return {}, {}


def lookup_career_institution(name: str) -> dict:
    """Return matched/ambiguous/not_found with source and remaining checks.

    ``pub5`` is a candidate category (5/10 ceiling); it is not a final rate.
    Other-public-institution designation alone intentionally has no suggested
    type, unless the snapshot supplies an independent explicit legal basis.
    """
    snapshot, index = _index()
    response = {
        "status": "not_found", "canonical_name": "", "legal_form": "",
        "suggested_type": "", "source_url": "", "as_of": snapshot.get("as_of", ""),
        "required_checks": [],
    }
    if not snapshot:
        response["required_checks"] = ["공식 기관 명부를 읽지 못했습니다. 기관의 법적 유형과 인정 근거를 확인하세요."]
        return response
    rows = index.get(_normalize(name), [])
    identities = {row["canonical_name"] for row in rows}
    if not identities:
        response["required_checks"] = ["이 오프라인 명부에서 일치하는 기관을 찾지 못했습니다. 미등재는 미인정을 뜻하지 않습니다."]
        return response
    if len(identities) != 1:
        response["status"] = "ambiguous"
        response["required_checks"] = ["명칭이 여러 기관과 겹칩니다. 법인등록명과 설립 근거를 확인하세요."]
        return response
    # Conflicting records for one canonical name are also an abstention.
    facts = {(row["legal_form"], row["suggested_type"]) for row in rows}
    if len(facts) != 1:
        response["status"] = "ambiguous"
        response["required_checks"] = ["기관 명부의 법적 유형 정보가 서로 다릅니다. 기준일과 설립 근거를 확인하세요."]
        return response
    response.update(rows[0])
    response["status"] = "matched"
    response["verified_on"] = snapshot.get("verified_on", "")
    response["required_checks"] = list(snapshot["required_checks"])
    if not response["suggested_type"]:
        response["required_checks"].append(
            "기타공공기관 지정만으로 50%를 확정할 수 없습니다. 인사혁신처장 또는 교육부장관의 별도 인정 근거를 확인하세요."
        )
    return response
