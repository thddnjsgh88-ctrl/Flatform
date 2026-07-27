"""공고문 정밀 판정 통합 (v2 → 판정).

흐름: 공고(Announcement) → 첨부 공고문 다운로드 → docparse 로 텍스트/요건 추출
     → API 요건과 병합(merge_rules) → 프로필 판정(match).

핵심 원칙:
- **온디맨드**: 전체 공고를 일괄로 받지 않는다. 사용자가 특정 공고를 볼 때 그 하나만
  다운로드한다(서버 부하·IP 차단 방지). 받은 파일은 캐시에 재사용한다.
- 다운로드 실패/미지원 형식이면 조용히 API 요건만으로 판정한다(폴백).
"""

from __future__ import annotations

import tempfile
import urllib.request
from datetime import date
from pathlib import Path

from .docparse import UnsupportedFormat, extract_text
from .matcher import match, merge_rules
from .models import Announcement, EligibilityRules, MatchResult, UserProfile
from .parser import extract_eligibility

# 공고문 캐시 디렉터리 (같은 공고를 다시 받지 않도록 재사용)
CACHE_DIR = Path(tempfile.gettempdir()) / "flatform_docs"

_UA = "Mozilla/5.0 (compatible; FlatformBot/0.1)"
_SUFFIX_BY_CONTENT = {
    b"%PDF": ".pdf",
    b"PK\x03\x04": ".hwpx",   # HWPX(zip). 일반 zip 일 수도 있으나 공고문 맥락에선 hwpx 로 시도
    b"\xd0\xcf\x11\xe0": ".hwp",  # OLE(구형 HWP)
}


def _guess_suffix(head: bytes, url: str) -> str:
    for magic, suffix in _SUFFIX_BY_CONTENT.items():
        if head.startswith(magic):
            return suffix
    lower = url.lower()
    for suffix in (".pdf", ".hwpx", ".hwp", ".txt"):
        if lower.endswith(suffix):
            return suffix
    return ".bin"


def download_document(url: str, cache_key: str, cache_dir: Path = CACHE_DIR) -> Path:
    """공고문 첨부를 내려받아 로컬 경로를 반환한다. 캐시가 있으면 재사용한다."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    existing = list(cache_dir.glob(f"{cache_key}.*"))
    if existing:
        return existing[0]
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    path = cache_dir / f"{cache_key}{_guess_suffix(data[:8], url)}"
    path.write_bytes(data)
    return path


def rules_from_document(path: str | Path) -> EligibilityRules:
    """로컬 공고문 파일에서 자격요건을 추출한다."""
    return extract_eligibility(extract_text(path))


def match_with_document(profile: UserProfile, announcement: Announcement,
                        doc_path: str | Path | None = None,
                        today: date | None = None) -> MatchResult:
    """공고문까지 반영해 정밀 판정한다.

    doc_path 가 주어지면 그 파일을, 없고 announcement.doc_url 이 있으면 내려받아 사용한다.
    공고문을 얻지 못하면 API 요건만으로 판정(폴백)한다.
    """
    api_rules = extract_eligibility(announcement.raw_eligibility)

    path = doc_path
    if path is None and announcement.doc_url:
        try:
            path = download_document(announcement.doc_url, cache_key=announcement.id)
        except Exception:  # noqa: BLE001 - 다운로드 실패는 폴백
            path = None

    if path is None:
        return match(profile, announcement, rules=api_rules, today=today)

    try:
        doc_rules = rules_from_document(path)
    except (UnsupportedFormat, FileNotFoundError):
        return match(profile, announcement, rules=api_rules, today=today)

    return match(profile, announcement, rules=merge_rules(api_rules, doc_rules), today=today)
