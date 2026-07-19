"""번들 샘플 공고 로더. 실제 공고 유형을 본뜬 데이터로 파서·매처를 오프라인 검증한다."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from ..models import Announcement, Source

_DATA_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "sample_announcements.json"


def _parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def load_sample_announcements(path: Path | None = None) -> list[Announcement]:
    raw = json.loads((path or _DATA_FILE).read_text(encoding="utf-8"))
    return [
        Announcement(
            id=item["id"],
            title=item["title"],
            organ=item["organ"],
            category=item["category"],
            raw_eligibility=item["raw_eligibility"],
            url=item.get("url", ""),
            apply_start=_parse_date(item.get("apply_start")),
            apply_end=_parse_date(item.get("apply_end")),
            source=Source.SAMPLE,
        )
        for item in raw
    ]
