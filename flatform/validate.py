"""실 API 연동 검증 도구: 공고를 수집해 원본을 저장하고 파서 추출 커버리지를 리포트한다.

실행 예:
    # 기업마당 (BIZINFO_API_KEY 필요)
    python -m flatform.validate --source bizinfo --count 100

    # K-Startup (DATA_GO_KR_KEY 필요)
    python -m flatform.validate --source kstartup --count 100

    # 키 없이 번들 샘플로 리포트 형식 확인
    python -m flatform.validate --source samples

하는 일:
1. API 원본 응답을 data/raw/{source}-{날짜}.json 에 저장 (필드 매핑 보정 재료)
2. Announcement 로 변환 — 제목/자격요건 텍스트가 비어 있으면 매핑 오류 경고와 함께
   원본 응답의 실제 필드명 목록을 출력한다
3. 공고별로 파서를 돌려 요건 항목별 추출 건수와 커버리지(%)를 리포트한다
4. 아무 요건도 추출되지 않은 공고를 예시로 보여줘 파서 개선 지점을 알려준다
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from .collectors import bizinfo, kstartup, load_sample_announcements
from .models import Announcement
from .parser import extract_eligibility

RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def _save_raw(source: str, payload: object) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"{source}-{date.today().isoformat()}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _collect(source: str, count: int) -> list[Announcement]:
    if source == "samples":
        return load_sample_announcements()
    if source == "bizinfo":
        payload = bizinfo.fetch_raw(count=count)
        saved = _save_raw(source, payload)
        print(f"원본 응답 저장: {saved}")
        announcements = bizinfo.to_announcements(payload)
    else:
        payload = kstartup.fetch_raw(count=count)
        saved = _save_raw(source, payload)
        print(f"원본 응답 저장: {saved}")
        announcements = kstartup.to_announcements(payload)

    # 필드 매핑이 어긋나면 제목이 비는 형태로 드러난다 — 실제 필드명을 보여준다
    empty_titles = sum(1 for a in announcements if not a.title.strip())
    if announcements and empty_titles > len(announcements) / 2:
        sample_item = None
        if isinstance(payload, dict):
            for key in ("jsonArray", "data", "items"):
                if isinstance(payload.get(key), list) and payload[key]:
                    sample_item = payload[key][0]
                    break
        print("⚠️  공고 제목이 대부분 비어 있습니다. API 필드 매핑 보정이 필요합니다.")
        if isinstance(sample_item, dict):
            print(f"   원본 응답의 실제 필드명: {sorted(sample_item.keys())}")
    return announcements


FIELD_LABELS = [
    ("지역", lambda r: bool(r.regions)),
    ("업력", lambda r: r.min_years is not None or r.max_years is not None),
    ("매출", lambda r: r.min_revenue is not None or r.max_revenue is not None),
    ("상시근로자", lambda r: r.min_employees is not None or r.max_employees is not None),
    ("나이", lambda r: r.min_age is not None or r.max_age is not None),
    ("대상유형", lambda r: bool(r.target_types)),
]


def report(announcements: list[Announcement], show_misses: int = 5) -> None:
    total = len(announcements)
    if total == 0:
        print("수집된 공고가 없습니다.")
        return

    parsed = [(a, extract_eligibility(a.raw_eligibility)) for a in announcements]
    with_any = [(a, r) for a, r in parsed if not r.is_empty()]
    misses = [a for a, r in parsed if r.is_empty()]

    print()
    print(f"공고 {total}건 파서 커버리지 리포트")
    print("-" * 48)
    for label, has_field in FIELD_LABELS:
        n = sum(1 for _, r in parsed if has_field(r))
        print(f"  {label:<6}: {n:>4}건 추출 ({n / total:>5.1%})")
    print("-" * 48)
    print(f"  1개 이상 요건 추출: {len(with_any)}건 / {total}건 ({len(with_any) / total:.1%})")

    if misses and show_misses:
        print(f"\n요건 미추출 공고 예시 (파서 개선 대상, 최대 {show_misses}건):")
        for a in misses[:show_misses]:
            snippet = " ".join(a.raw_eligibility.split())[:80] or "(자격요건 텍스트 없음)"
            print(f"  - {a.title}")
            print(f"    자격 원문: {snippet}")


def main() -> None:
    arg_parser = argparse.ArgumentParser(description="실 API 수집 + 파서 커버리지 검증")
    arg_parser.add_argument("--source", choices=["bizinfo", "kstartup", "samples"],
                            default="samples")
    arg_parser.add_argument("--count", type=int, default=100, help="수집 건수 (기본 100)")
    arg_parser.add_argument("--show-misses", type=int, default=5,
                            help="미추출 공고 예시 출력 수 (기본 5)")
    args = arg_parser.parse_args()

    announcements = _collect(args.source, args.count)
    report(announcements, show_misses=args.show_misses)


if __name__ == "__main__":
    main()
