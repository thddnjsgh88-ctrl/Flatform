"""K-Startup 지원사업 공고 오픈API 수집기 (공공데이터포털 경유).

서비스키는 공공데이터포털(data.go.kr)에서 '창업진흥원_K-Startup 조회서비스'
활용신청 후 발급받아 환경변수 DATA_GO_KR_KEY 로 넘긴다.

응답 필드 매핑은 공개 문서 기준의 best-effort 이며, 실제 키 발급 후
첫 호출 결과를 보고 필드명을 보정해야 한다 (PoC 단계 주의사항).
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import date, datetime

from ..models import Announcement, Source

API_URL = "https://apis.data.go.kr/B552735/kisedKstartupService01/getAnnouncementInformation01"


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    digits = "".join(ch for ch in value if ch.isdigit())[:8]
    try:
        return datetime.strptime(digits, "%Y%m%d").date()
    except ValueError:
        return None


def fetch_raw(service_key: str | None = None, count: int = 50,
              page: int = 1) -> dict:
    """K-Startup API 원본 응답(JSON)을 반환한다. 필드 매핑 검증용으로도 쓴다."""
    service_key = service_key or os.environ.get("DATA_GO_KR_KEY")
    if not service_key:
        raise RuntimeError("공공데이터포털 서비스키가 필요합니다. DATA_GO_KR_KEY 환경변수를 설정하세요.")

    params = {
        "serviceKey": service_key,
        "returnType": "json",
        "numOfRows": str(count),
        "pageNo": str(page),
    }
    with urllib.request.urlopen(f"{API_URL}?{urllib.parse.urlencode(params)}", timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def to_announcements(payload: dict) -> list[Announcement]:
    """원본 응답을 Announcement 목록으로 변환한다."""
    items = payload.get("data", [])
    announcements = []
    for item in items:
        # 자격요건 파싱 재료로 지원대상·지역·제외대상 텍스트를 합쳐서 넘긴다.
        eligibility_parts = [
            item.get("aply_trgt_ctnt", ""),
            item.get("supt_regin", ""),
            item.get("aply_excl_trgt_ctnt", ""),
        ]
        announcements.append(Announcement(
            id=f"kstartup-{item.get('pbanc_sn', '')}",
            title=item.get("biz_pbanc_nm", item.get("intg_pbanc_biz_nm", "")),
            organ=item.get("pbanc_ntrp_nm", ""),
            category=item.get("supt_biz_clsfc", ""),
            raw_eligibility=" ".join(p for p in eligibility_parts if p),
            url=item.get("detl_pg_url", ""),
            apply_start=_parse_date(item.get("pbanc_rcpt_bgng_dt")),
            apply_end=_parse_date(item.get("pbanc_rcpt_end_dt")),
            source=Source.KSTARTUP,
        ))
    return announcements


def fetch_announcements(service_key: str | None = None, count: int = 50,
                        page: int = 1) -> list[Announcement]:
    return to_announcements(fetch_raw(service_key, count, page))
