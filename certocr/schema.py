"""공유 데이터 스키마 — 모든 모듈이 이 파일의 타입으로만 통신한다.

식별자는 영문(cp949 콘솔·직렬화 호환), JSON 출력 시 표시용 한글 키는
KOREAN_LABELS 매핑을 사용한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class OcrLine:
    """OCR 엔진이 반환하는 한 줄."""
    text: str
    bbox: tuple[float, float, float, float]  # (x1, y1, x2, y2) 픽셀 좌표
    conf: float  # 0.0 ~ 1.0


@dataclass
class CareerRecord:
    """경력 사항 한 행."""
    org: str            # 소속 (학교/기관명)
    position: str       # 직위
    start_date: str     # YYYY-MM-DD
    end_date: str       # YYYY-MM-DD 또는 "재직중"
    subject: str = ""   # 담당과목 (없으면 빈 문자열)
    employment_type: str = ""  # 계약제 구분/직급
    weekly_hours: str = ""     # 주당근무시간 또는 일 근무시간
    duration: str = ""         # 근무연한 표기(날짜와 구분)
    days: str = ""             # 일수형 서식


@dataclass
class CareerCertificate:
    """경력증명서에서 추출하는 최종 구조."""
    name: str                      # 성명
    birth_date: str                # 생년월일 YYYY-MM-DD
    records: list[CareerRecord] = field(default_factory=list)
    issue_date: str = ""           # 발급일
    issuer: str = ""               # 발급기관
    purpose: str = ""              # 용도
    doc_no: str = ""               # 문서번호
    layout: str = ""               # neis | legacy | variant

    def to_json_dict(self) -> dict:
        return asdict(self)


@dataclass
class GroundTruth:
    """합성 생성기가 이미지와 함께 반환하는 정답."""
    cert: CareerCertificate
    lines: list[tuple[str, tuple[float, float, float, float]]]  # (텍스트, bbox)
    layout: str  # neis | legacy | variant (구형 layout 별칭 입력은 생성기에서 지원)


@dataclass
class FieldConfidence:
    value: str
    conf: float          # 0.0 ~ 1.0
    source: str          # "ocr" | "dict" | "rule" | "llm"


@dataclass
class ExtractionResult:
    """파이프라인 최종 출력."""
    cert: CareerCertificate
    field_conf: dict = field(default_factory=dict)   # "name", "records[0].org" 등 -> float
    flags: list = field(default_factory=list)        # ["판독불가:직인영역"] 등 검토 필요 사유
    raw_lines: list = field(default_factory=list)    # list[OcrLine]

    def needs_review(self, threshold: float = 0.85) -> bool:
        if self.flags:
            return True
        return any(c < threshold for c in self.field_conf.values())

    def records_needs_review(self, threshold: float = 0.85) -> bool:
        """근무기간·기관·직종만 대상으로 한 검토 여부."""
        if not self.cert.records:
            return True
        required = ("org", "position", "start_date", "end_date")
        for i, record in enumerate(self.cert.records):
            for field_name in required:
                if not getattr(record, field_name):
                    return True
                if self.field_conf.get(f"records[{i}].{field_name}", 0.0) < threshold:
                    return True
        return any(flag.startswith(("OCR 텍스트", "경력사항", "누락:records", "기간 중첩", "저화질 fallback")) for flag in self.flags)

    def records_json_dict(self) -> dict:
        reasons = [f for f in self.flags if f.startswith(("OCR 텍스트", "경력사항", "누락:records", "기간 중첩", "저화질 fallback"))]
        for i, record in enumerate(self.cert.records):
            for field_name in ("org", "position", "start_date", "end_date"):
                score = self.field_conf.get(f"records[{i}].{field_name}", 0.0)
                if getattr(record, field_name) and score < 0.85:
                    reasons.append(f"낮은신뢰도:records[{i}].{field_name}={score:.2f}")
        return {
            "경력사항": [
                {
                    "근무기간": {"시작": r.start_date, "종료": r.end_date},
                    "근무학교(회사)": r.org,
                    "직종": r.position,
                }
                for r in self.cert.records
            ],
            "검토필요": self.records_needs_review(),
            "검토사유": reasons,
        }


KOREAN_LABELS = {
    "name": "성명",
    "birth_date": "생년월일",
    "records": "경력사항",
    "org": "소속",
    "position": "직위",
    "start_date": "시작일",
    "end_date": "종료일",
    "subject": "담당과목",
    "employment_type": "계약제구분",
    "weekly_hours": "주당근무시간",
    "duration": "근무연한",
    "days": "일수",
    "issue_date": "발급일",
    "issuer": "발급기관",
    "purpose": "용도",
    "doc_no": "문서번호",
    "layout": "서식",
}

REDACTED = "REDACTED"
UNREADABLE = "UNREADABLE"
