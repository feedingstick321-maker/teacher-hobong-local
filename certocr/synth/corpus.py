"""개인정보가 아닌 합성용 한국어 말뭉치."""
from __future__ import annotations

import random
from datetime import date, timedelta

SURNAMES = ["김", "이", "박", "최", "정", "강", "조", "윤", "장", "임", "한", "오", "서", "신"]
GIVEN = ["서준", "하윤", "도윤", "지우", "민준", "서연", "예준", "지민", "현우", "수빈", "은지", "준호"]
SCHOOLS = [
    "가람초등학교", "늘봄초등학교", "다온초등학교", "한빛초등학교", "푸른중학교",
    "새솔중학교", "미래고등학교", "한울고등학교", "별내고등학교", "해솔고등학교",
    "수원가온초등학교", "성남새롬중학교", "고양한빛고등학교", "용인마루초등학교",
]
POSITIONS = ["기간제교사", "교사", "시간강사", "보건교사", "사서교사", "전문상담교사"]
SUBJECTS = ["국어", "수학", "영어", "과학", "사회", "체육", "음악", "미술", "특수", ""]
OFFICES = ["경기도교육청", "서울특별시교육청", "인천광역시교육청", "강원특별자치도교육청"]


def person_name(rng: random.Random) -> str:
    return rng.choice(SURNAMES) + rng.choice(GIVEN)


def make_records(rng: random.Random, count: int | None = None) -> list[dict[str, str]]:
    count = count or rng.randint(1, 5)
    cursor = date(rng.randint(2001, 2021), 3, 1)
    rows: list[dict[str, str]] = []
    for _ in range(count):
        cursor += timedelta(days=rng.randint(0, 180))
        months = rng.randint(2, 24)
        end = cursor + timedelta(days=months * 30 - 1)
        rows.append({
            "org": rng.choice(SCHOOLS), "position": rng.choice(POSITIONS),
            "start_date": cursor.isoformat(), "end_date": end.isoformat(),
            "subject": rng.choice(SUBJECTS), "employment_type": "기간제" if rng.random() < .75 else "",
            "weekly_hours": str(rng.choice([10, 14, 18, 20, 22])),
            "duration": f"{months // 12}년 {months % 12}월" if months >= 12 else f"{months}개월",
            "days": "",
        })
        cursor = end + timedelta(days=1)
    return rows
