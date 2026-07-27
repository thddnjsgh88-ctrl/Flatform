"""공고 중복 제거.

기업마당·K-Startup 등 여러 소스를 합치면 같은 사업이 중복 등장한다.
제목을 정규화(차수·연도·'공고' 등 제거)하고 소관 기관과 함께 키로 삼아 중복을
판별한다. 서로 다른 사업을 잘못 합치는 것(거짓 병합)이 더 위험하므로, 지역·핵심
명칭은 보존하고 보수적으로 병합한다.
"""

from __future__ import annotations

import re

from .models import Announcement

# 같은 사업을 다르게 표기하게 만드는 요소들(차수·연도·정형 단어)만 제거한다.
_DROP = re.compile(r"(재공고|\d+\s*차|\d+\s*회|추가\s*모집|재모집|모집공고|참여기업|참가기업|모집|공고|안내)")
_YEAR = re.compile(r"\d{4}\s*년도?")
_NONWORD = re.compile(r"[\s\[\]()<>·ㆍ,.\-–—「」『』/'\"|]+")


def normalize_title(title: str) -> str:
    """제목을 비교용으로 정규화한다. 지역·사업 핵심명은 보존한다."""
    t = _YEAR.sub(" ", title)
    t = _DROP.sub(" ", t)
    t = _NONWORD.sub("", t)
    return t.lower()


def _richness(a: Announcement) -> tuple[int, int]:
    """더 유용한 레코드 판별용: 공고문 URL 보유 > 자격 텍스트 길이."""
    return (1 if a.doc_url else 0, len(a.raw_eligibility or ""))


def deduplicate(announcements: list[Announcement]) -> list[Announcement]:
    """정규화 제목 + 기관 기준 중복을 제거하고 더 풍부한 레코드를 남긴다.

    원본 순서를 보존한다. 정규화 제목이 빈 문자열이면(제목이 특수문자뿐 등)
    안전하게 중복 판별에서 제외해 그대로 유지한다.
    """
    kept: dict[tuple[str, str], int] = {}
    result: list[Announcement] = []
    for a in announcements:
        key = (normalize_title(a.title), (a.organ or "").replace(" ", ""))
        if not key[0]:
            result.append(a)
            continue
        if key in kept:
            i = kept[key]
            if _richness(a) > _richness(result[i]):
                result[i] = a          # 중복 중 더 풍부한 레코드로 교체
        else:
            kept[key] = len(result)
            result.append(a)
    return result
