"""기업마당(bizinfo.go.kr) 지원사업정보 API 수집기.

인증키는 기업마당 > 활용정보 > 정책정보 개방에서 발급받아
환경변수 BIZINFO_API_KEY 로 넘긴다.

응답 필드 매핑은 공개 문서 기준의 best-effort 이며, 실제 키 발급 후
첫 호출 결과를 보고 필드명을 보정해야 한다 (PoC 단계 주의사항).
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from datetime import date

from ..models import Announcement, Source

API_URL = "https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do"

_TAG = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    return _TAG.sub(" ", text or "").strip()


def _parse_period(value: str) -> tuple[date | None, date | None]:
    """'20260701 ~ 20260731' 형태의 접수기간 문자열을 (시작, 종료)로 파싱한다."""
    dates = re.findall(r"(\d{4})[.\-/]?(\d{2})[.\-/]?(\d{2})", value or "")
    parsed = [date(int(y), int(m), int(d)) for y, m, d in dates[:2]]
    if len(parsed) == 2:
        return parsed[0], parsed[1]
    if len(parsed) == 1:
        return None, parsed[0]
    return None, None


def fetch_announcements(api_key: str | None = None, count: int = 50,
                        hashtags: str | None = None) -> list[Announcement]:
    """기업마당 공고를 수집해 Announcement 목록으로 변환한다.

    hashtags 예: "서울,소상공인" — API 측 필터를 그대로 전달한다.
    """
    api_key = api_key or os.environ.get("BIZINFO_API_KEY")
    if not api_key:
        raise RuntimeError("기업마당 인증키가 필요합니다. BIZINFO_API_KEY 환경변수를 설정하세요.")

    params = {"crtfcKey": api_key, "dataType": "json", "searchCnt": str(count)}
    if hashtags:
        params["hashtags"] = hashtags
    with urllib.request.urlopen(f"{API_URL}?{urllib.parse.urlencode(params)}", timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    items = payload.get("jsonArray", payload if isinstance(payload, list) else [])
    announcements = []
    for item in items:
        start, end = _parse_period(item.get("reqstBeginEndDe", ""))
        announcements.append(Announcement(
            id=f"bizinfo-{item.get('pblancId', item.get('pblancNm', ''))}",
            title=_strip_html(item.get("pblancNm", "")),
            organ=item.get("jrsdInsttNm", ""),
            category=item.get("pldirSportRealmLclasCodeNm", ""),
            raw_eligibility=_strip_html(item.get("bsnsSumryCn", "")),
            url=urllib.parse.urljoin("https://www.bizinfo.go.kr", item.get("pblancUrl", "")),
            apply_start=start,
            apply_end=end,
            source=Source.BIZINFO,
        ))
    return announcements
