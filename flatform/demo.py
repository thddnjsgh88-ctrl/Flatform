"""파이프라인 데모: 샘플 공고 로드 → 자격요건 구조화 → 프로필별 자격 판정 리포트.

실행: python -m flatform.demo [--today YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
from datetime import date

from .collectors import load_sample_announcements
from .matcher import match_all
from .models import MatchResult, UserProfile, Verdict

_ICONS = {
    Verdict.ELIGIBLE: "✅",
    Verdict.UNKNOWN: "❓",
    Verdict.INELIGIBLE: "❌",
    Verdict.CLOSED: "⏰",
}

DEMO_PROFILES = [
    UserProfile(
        name="김서울 (마포 카페, 3년차)",
        region="서울", industry="음식점업",
        years_in_business=3, annual_revenue=250_000_000, employees=2, age=34,
    ),
    UserProfile(
        name="박경기 (부천 부품 제조, 6년차)",
        region="경기", industry="제조업",
        years_in_business=6, annual_revenue=1_200_000_000, employees=8, age=52,
    ),
    UserProfile(
        name="이예비 (부산, 예비창업자·매출 미입력)",
        region="부산", industry="정보통신업",
        years_in_business=0, annual_revenue=None, employees=0, age=45,
    ),
]


def _deadline_label(result: MatchResult, today: date) -> str:
    end = result.announcement.apply_end
    if end is None:
        return "상시"
    days = (end - today).days
    return f"~{end.isoformat()} (D-{days})" if days >= 0 else f"{end.isoformat()} 마감"


def render_report(profile: UserProfile, results: list[MatchResult], today: date) -> str:
    lines = [
        "=" * 72,
        f"프로필: {profile.name}",
        f"  지역 {profile.region} · 업종 {profile.industry} · 업력 {profile.years_in_business:g}년"
        f" · 상시근로자 {profile.employees}명"
        f" · 연매출 {'미입력' if profile.annual_revenue is None else format(profile.annual_revenue, ',') + '원'}",
        "=" * 72,
    ]
    for result in results:
        ann = result.announcement
        lines.append(f"{_ICONS[result.verdict]} [{result.verdict.value}] {ann.title}")
        lines.append(f"    {ann.organ} · {ann.category} · 접수 {_deadline_label(result, today)}")
        if result.verdict == Verdict.INELIGIBLE:
            for check in result.failed_checks:
                lines.append(f"    ✗ {check.reason}")
        elif result.verdict == Verdict.UNKNOWN:
            for check in result.unknown_checks:
                lines.append(f"    ? {check.reason}")
    counts = {v: sum(1 for r in results if r.verdict == v) for v in Verdict}
    lines.append(
        f"  → 적합 {counts[Verdict.ELIGIBLE]} · 판단보류 {counts[Verdict.UNKNOWN]}"
        f" · 부적합 {counts[Verdict.INELIGIBLE]} · 마감 {counts[Verdict.CLOSED]}"
    )
    return "\n".join(lines)


def main() -> None:
    arg_parser = argparse.ArgumentParser(description="Flatform 자격 판정 데모")
    arg_parser.add_argument("--today", type=date.fromisoformat, default=date.today(),
                            help="판정 기준일 (기본: 오늘)")
    args = arg_parser.parse_args()

    announcements = load_sample_announcements()
    print(f"샘플 공고 {len(announcements)}건 로드 (기준일 {args.today.isoformat()})\n")
    for profile in DEMO_PROFILES:
        print(render_report(profile, match_all(profile, announcements, today=args.today), args.today))
        print()


if __name__ == "__main__":
    main()
