"""학교알리미 학교기본정보 스냅샷을 이용한 오프라인 설립구분 조회.

학교명만으로 법정 경력환산율을 확정하지 않는다. 동명 학교의 설립구분이
다르거나 오래된/폐교 자료이면 판별을 보류한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
import re
import unicodedata

from certocr.config import DICTS


SNAPSHOT_PATH = DICTS / "school_foundation_2026.json"
FOUNDATIONS = {"국립", "공립", "사립"}


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value or "")).strip()


@dataclass(frozen=True)
class SchoolLookup:
    status: str  # matched / ambiguous / inactive / not_found / unavailable
    foundation: str = ""
    school_name: str = ""
    school_codes: tuple[str, ...] = ()
    year: int = 0


@lru_cache(maxsize=1)
def _index() -> tuple[int, dict[str, list[dict]]]:
    try:
        snapshot = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        year = int(snapshot["year"])
        rows = snapshot["schools"]
    except (OSError, ValueError, KeyError, TypeError):
        return 0, {}
    result: dict[str, list[dict]] = {}
    for row in rows:
        if row.get("foundation") not in FOUNDATIONS or not row.get("code"):
            continue
        name = _normalize(str(row.get("name") or ""))
        if name:
            result.setdefault(name, []).append(row)
    return year, result


def lookup_school(organization: str) -> SchoolLookup:
    year, index = _index()
    if not index:
        return SchoolLookup("unavailable")
    organization = unicodedata.normalize("NFKC", organization or "").strip()
    whole = _normalize(organization)
    names: list[str] = []
    if whole in index:
        names.append(whole)
    else:
        # 소속기관 앞뒤에 시도교육청이나 직종이 붙었을 때만 토큰 단위 조회.
        # 부분 문자열로 찾으면 '홍천고등학교'와 '용인홍천고등학교'를 혼동한다.
        for token in re.split(r"[\s,;/|()[\]{}]+", organization):
            key = _normalize(token)
            if key in index and key not in names:
                names.append(key)
    if len(names) != 1:
        return SchoolLookup("ambiguous" if names else "not_found", year=year)

    rows = index[names[0]]
    active = [row for row in rows if not row.get("closed") and not row.get("abolished")]
    if not active:
        return SchoolLookup("inactive", school_name=rows[0]["name"], year=year)

    # 동명 학교가 서로 다른 지역에 있는 경우, 입력된 관할청/주소가 한 곳을
    # 확실히 가리키면 좁힌다. 단순 학교명만 있으면 설립구분이 일치할 때만 사용.
    if len(active) > 1:
        hinted = [row for row in active if any(
            label and len(_normalize(label)) >= 3 and _normalize(label) in whole
            for label in (row.get("province"), row.get("district"))
        )]
        if hinted:
            active = hinted
    foundations = {row["foundation"] for row in active}
    if len(foundations) != 1:
        return SchoolLookup(
            "ambiguous", school_name=active[0]["name"],
            school_codes=tuple(row["code"] for row in active), year=year,
        )
    return SchoolLookup(
        "matched", foundation=next(iter(foundations)), school_name=active[0]["name"],
        school_codes=tuple(row["code"] for row in active), year=year,
    )
