"""구조화된 자격요건과 사용자 프로필을 대조해 공고별 적합 여부를 판정한다.

판정 원칙:
- 하나라도 명확히 어긋나는 요건이 있으면 '부적합' (사유를 모두 수집)
- 어긋나는 요건은 없지만 프로필 정보 부족으로 판정 불가한 요건이 있으면 '판단보류'
- 접수 기간이 지난 공고는 요건과 무관하게 '접수마감'
"""

from __future__ import annotations

from datetime import date

from .models import (
    SPECIAL_TARGET_TYPES,
    Announcement,
    EligibilityRules,
    MatchResult,
    RuleCheck,
    UserProfile,
    Verdict,
)
from .parser import extract_eligibility


def _fmt_revenue(won: float) -> str:
    if won >= 100_000_000:
        value = won / 100_000_000
        return f"{value:g}억원"
    return f"{won / 10_000:g}만원"


def _check_region(profile: UserProfile, rules: EligibilityRules) -> RuleCheck | None:
    if not rules.regions:
        return None
    if profile.region in rules.regions:
        return RuleCheck("지역", True, f"{profile.region} 소재 — 대상 지역({', '.join(rules.regions)})에 해당")
    return RuleCheck("지역", False, f"대상 지역이 {', '.join(rules.regions)}이나 신청자는 {profile.region} 소재")


def _check_years(profile: UserProfile, rules: EligibilityRules) -> RuleCheck | None:
    if rules.min_years is None and rules.max_years is None:
        return None
    years = profile.years_in_business
    if rules.max_years is not None and years > rules.max_years:
        return RuleCheck("업력", False, f"업력 {rules.max_years:g}년 이내 대상이나 현재 업력 {years:g}년")
    if rules.min_years is not None and years < rules.min_years:
        return RuleCheck("업력", False, f"업력 {rules.min_years:g}년 이상 대상이나 현재 업력 {years:g}년")
    return RuleCheck("업력", True, f"업력 {years:g}년 — 요건 충족")


def _check_revenue(profile: UserProfile, rules: EligibilityRules) -> RuleCheck | None:
    if rules.min_revenue is None and rules.max_revenue is None:
        return None
    revenue = profile.annual_revenue
    if revenue is None:
        bound = rules.max_revenue if rules.max_revenue is not None else rules.min_revenue
        return RuleCheck("매출", None, f"매출 요건(기준 {_fmt_revenue(bound)}) 존재 — 연 매출 정보를 입력하면 판정 가능")
    if rules.max_revenue is not None and revenue > rules.max_revenue:
        return RuleCheck("매출", False, f"연 매출 {_fmt_revenue(rules.max_revenue)} 이하 대상이나 현재 {_fmt_revenue(revenue)}")
    if rules.min_revenue is not None and revenue < rules.min_revenue:
        return RuleCheck("매출", False, f"연 매출 {_fmt_revenue(rules.min_revenue)} 이상 대상이나 현재 {_fmt_revenue(revenue)}")
    return RuleCheck("매출", True, f"연 매출 {_fmt_revenue(revenue)} — 요건 충족")


def _check_employees(profile: UserProfile, rules: EligibilityRules) -> RuleCheck | None:
    if rules.min_employees is None and rules.max_employees is None:
        return None
    count = profile.employees
    if rules.max_employees is not None and count > rules.max_employees:
        return RuleCheck("상시근로자", False, f"상시근로자 {rules.max_employees}명 이하 대상이나 현재 {count}명")
    if rules.min_employees is not None and count < rules.min_employees:
        return RuleCheck("상시근로자", False, f"상시근로자 {rules.min_employees}명 이상 대상이나 현재 {count}명")
    return RuleCheck("상시근로자", True, f"상시근로자 {count}명 — 요건 충족")


def _check_industry(profile: UserProfile, rules: EligibilityRules) -> RuleCheck | None:
    if not rules.required_industries:
        return None
    # 대상 업종 키워드가 신청자 업종 표기에 포함되면 해당 (예: '제조업' ⊆ '제조업')
    matched = [ind for ind in rules.required_industries if ind in profile.industry]
    targets = ", ".join(rules.required_industries)
    if matched:
        return RuleCheck("업종", True, f"업종 {profile.industry} — 대상 업종({targets})에 해당")
    return RuleCheck("업종", False, f"대상 업종은 {targets}이나 신청자 업종은 {profile.industry}")


def _check_age(profile: UserProfile, rules: EligibilityRules) -> RuleCheck | None:
    if rules.min_age is None and rules.max_age is None:
        return None
    if profile.age is None:
        return RuleCheck("나이", None, "대표자 나이 요건 존재 — 나이 정보를 입력하면 판정 가능")
    if rules.max_age is not None and profile.age > rules.max_age:
        return RuleCheck("나이", False, f"만 {rules.max_age}세 이하 대상이나 현재 만 {profile.age}세")
    if rules.min_age is not None and profile.age < rules.min_age:
        return RuleCheck("나이", False, f"만 {rules.min_age}세 이상 대상이나 현재 만 {profile.age}세")
    return RuleCheck("나이", True, f"만 {profile.age}세 — 요건 충족")


def _check_target_types(profile: UserProfile, rules: EligibilityRules) -> list[RuleCheck]:
    checks: list[RuleCheck] = []
    if "소상공인" in rules.target_types:
        limit = profile.small_business_employee_limit
        if profile.is_small_business:
            checks.append(RuleCheck(
                "소상공인", True,
                f"{profile.industry} 상시근로자 {profile.employees}명 (< {limit}명) — 소상공인 해당"))
        else:
            checks.append(RuleCheck(
                "소상공인", False,
                f"{profile.industry} 기준 상시근로자 {limit}명 미만이어야 하나 현재 {profile.employees}명"))
    if "예비창업자" in rules.target_types:
        # "예비창업자 및 창업 N년 이내 기업" 형태는 업력 요건이 함께 추출되므로
        # 업력 검사에 위임하고, 예비창업자 '전용' 공고에서만 업력 0을 요구한다.
        if rules.max_years is None:
            if profile.is_pre_startup:
                checks.append(RuleCheck("예비창업자", True, "사업자등록 전 — 예비창업자 해당"))
            else:
                checks.append(RuleCheck(
                    "예비창업자", False,
                    f"예비창업자 대상 공고이나 이미 창업 {profile.years_in_business:g}년차"))

    # 특수 기업유형(사회적기업·마을기업 등) 전용 사업.
    # 사용자가 해당 특성을 보유했다고 밝히지 않았으면, 잘못 '적합' 처리하지 않도록
    # '판단보류'로 두고 확인을 유도한다(거짓 적합 방지).
    for special in SPECIAL_TARGET_TYPES:
        if special in rules.target_types:
            if special in profile.business_traits:
                checks.append(RuleCheck(special, True, f"{special} 보유 — 대상 해당"))
            else:
                checks.append(RuleCheck(
                    special, None,
                    f"{special} 전용 사업 — 해당 여부 확인 필요"))
    return checks


def _pick(a, b, fn):
    """둘 다 값이 있으면 fn 으로 고르고, 하나만 있으면 그 값을 쓴다."""
    if a is None:
        return b
    if b is None:
        return a
    return fn(a, b)


def merge_rules(base: EligibilityRules, extra: EligibilityRules) -> EligibilityRules:
    """API 요건(base)과 공고문 요건(extra)을 병합한다.

    - 하한(min_*)은 더 큰 값, 상한(max_*)은 더 작은 값으로 '더 엄격하게' 취한다.
    - 지역·업종은 API 값이 있으면 유지하고 없을 때만 공고문 값으로 채운다
      (공고문 지역 추출의 오탐이 자격을 부당히 넓히지 않도록 보수적으로).
    - 대상유형은 합집합(정보성이라 넓혀도 판정에 해롭지 않음).
    """
    return EligibilityRules(
        regions=base.regions or extra.regions,
        required_industries=base.required_industries or extra.required_industries,
        target_types=list(dict.fromkeys(base.target_types + extra.target_types)),
        min_years=_pick(base.min_years, extra.min_years, max),
        max_years=_pick(base.max_years, extra.max_years, min),
        min_revenue=_pick(base.min_revenue, extra.min_revenue, max),
        max_revenue=_pick(base.max_revenue, extra.max_revenue, min),
        min_employees=_pick(base.min_employees, extra.min_employees, max),
        max_employees=_pick(base.max_employees, extra.max_employees, min),
        min_age=_pick(base.min_age, extra.min_age, max),
        max_age=_pick(base.max_age, extra.max_age, min),
    )


def match(profile: UserProfile, announcement: Announcement,
          rules: EligibilityRules | None = None,
          today: date | None = None) -> MatchResult:
    today = today or date.today()
    if rules is None:
        rules = extract_eligibility(announcement.raw_eligibility)

    checks: list[RuleCheck] = []
    for check in (
        _check_region(profile, rules),
        _check_years(profile, rules),
        _check_revenue(profile, rules),
        _check_employees(profile, rules),
        _check_age(profile, rules),
        _check_industry(profile, rules),
    ):
        if check is not None:
            checks.append(check)
    checks.extend(_check_target_types(profile, rules))

    if not announcement.is_open(today):
        verdict = Verdict.CLOSED
    elif any(c.passed is False for c in checks):
        verdict = Verdict.INELIGIBLE
    elif any(c.passed is None for c in checks):
        verdict = Verdict.UNKNOWN
    else:
        verdict = Verdict.ELIGIBLE
    return MatchResult(announcement=announcement, rules=rules, verdict=verdict, checks=checks)


def match_all(profile: UserProfile, announcements: list[Announcement],
              today: date | None = None) -> list[MatchResult]:
    """공고 전체를 판정하고 적합 → 판단보류 → 부적합 → 마감 순으로 정렬해 반환한다."""
    order = {Verdict.ELIGIBLE: 0, Verdict.UNKNOWN: 1, Verdict.INELIGIBLE: 2, Verdict.CLOSED: 3}
    results = [match(profile, a, today=today) for a in announcements]
    results.sort(key=lambda r: (order[r.verdict], r.announcement.apply_end or date.max))
    return results
