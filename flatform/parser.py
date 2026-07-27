"""공고 원문(지원자격 텍스트)에서 구조화된 자격요건을 추출하는 규칙 기반 파서.

PoC 범위: 정규식 기반으로 지역·업력·매출·상시근로자·나이·대상유형을 뽑는다.
공고 문면은 비정형이므로 여기서 못 뽑는 요건은 '판단보류'로 흘려보내는 것이
잘못 뽑아서 오판하는 것보다 낫다는 원칙으로 보수적으로 추출한다.
"""

from __future__ import annotations

import re

from .models import SPECIAL_TARGET_TYPES, EligibilityRules

# 17개 시도. 긴 표기를 짧은 표준 표기로 정규화한다.
REGION_ALIASES = {
    "서울": "서울", "서울특별시": "서울",
    "부산": "부산", "부산광역시": "부산",
    "대구": "대구", "대구광역시": "대구",
    "인천": "인천", "인천광역시": "인천",
    "광주": "광주", "광주광역시": "광주",
    "대전": "대전", "대전광역시": "대전",
    "울산": "울산", "울산광역시": "울산",
    "세종": "세종", "세종특별자치시": "세종",
    "경기": "경기", "경기도": "경기",
    "강원": "강원", "강원도": "강원", "강원특별자치도": "강원",
    "충북": "충북", "충청북도": "충북",
    "충남": "충남", "충청남도": "충남",
    "전북": "전북", "전라북도": "전북", "전북특별자치도": "전북",
    "전남": "전남", "전라남도": "전남",
    "경북": "경북", "경상북도": "경북",
    "경남": "경남", "경상남도": "경남",
    "제주": "제주", "제주특별자치도": "제주",
}
# 긴 이름 먼저 매칭되도록 길이 역순 정렬
_REGION_PATTERN = re.compile(
    "(" + "|".join(sorted(REGION_ALIASES, key=len, reverse=True)) + ")"
)
_REGION_CONTEXT = re.compile(r"소재|관내|지역\s*내|소재지|위치한")

_NUM = r"(\d+(?:\.\d+)?)"

# 업력: "창업 후 7년 이내", "업력 3년 미만 기업", "창업 7년 이내"
_YEARS_MAX = re.compile(rf"(?:창업\s*(?:후)?|업력)\s*{_NUM}\s*년\s*(?:이내|이하|미만)")
_YEARS_MIN = re.compile(rf"(?:창업\s*(?:후)?|업력)\s*{_NUM}\s*년\s*이상")

# 매출: "연 매출액 10억원 이하", "매출액 3천만원 이상"
_REVENUE = re.compile(rf"(?:연\s*)?매출(?:액)?\s*{_NUM}\s*(억|천만|백만|만)\s*원?\s*(이하|미만|이상|초과)")
_REVENUE_UNITS = {"억": 100_000_000, "천만": 10_000_000, "백만": 1_000_000, "만": 10_000}

# 상시근로자: "상시근로자 수 5인 미만", "상시 근로자 10명 이하"
_EMPLOYEES = re.compile(r"상시\s*근로자(?:\s*수)?\s*(\d+)\s*(?:인|명)\s*(이하|미만|이상|초과)")

# 나이: "만 39세 이하", "만 19세 이상 39세 이하"
_AGE = re.compile(r"만\s*(\d+)\s*세\s*(이하|미만|이상|초과)")

# 일반 대상유형 + 특수 기업유형(SPECIAL_TARGET_TYPES). 긴 표기가 먼저 매칭되도록 정렬한다.
# "예비사회적기업"이 "사회적기업"보다 먼저 잡혀야 중복 태깅을 피할 수 있다.
_TARGET_KEYWORDS = tuple(sorted(
    ("소상공인", "중소기업", "예비창업자", "청년", *SPECIAL_TARGET_TYPES),
    key=len, reverse=True,
))


def _apply_bound(rules: EligibilityRules, attr_min: str, attr_max: str,
                 value: float | int, direction: str, integer: bool) -> None:
    """비교 방향(이하/미만/이상/초과)을 포함 경계로 정규화해 rules 에 반영한다.

    정수 요건(인원·나이)의 '미만/초과'는 1을 가감해 포함 경계로 바꾸고,
    실수 요건(업력·매출)은 문서화된 단순화로서 미만≈이하, 초과≈이상으로 둔다.
    """
    if direction in ("이하", "이내", "미만"):
        if integer and direction == "미만":
            value -= 1
        current = getattr(rules, attr_max)
        if current is None or value < current:
            setattr(rules, attr_max, value)
    else:  # 이상 / 초과
        if integer and direction == "초과":
            value += 1
        current = getattr(rules, attr_min)
        if current is None or value > current:
            setattr(rules, attr_min, value)


def extract_regions(text: str) -> list[str]:
    """'소재'류 문맥이 있는 경우에만 지역 제한으로 해석한다. '전국'이 명시되면 제한 없음."""
    if "전국" in text:
        return []
    if not _REGION_CONTEXT.search(text):
        return []
    found: list[str] = []
    for match in _REGION_PATTERN.finditer(text):
        normalized = REGION_ALIASES[match.group(1)]
        if normalized not in found:
            found.append(normalized)
    return found


def extract_eligibility(text: str) -> EligibilityRules:
    rules = EligibilityRules()
    rules.regions = extract_regions(text)

    for m in _YEARS_MAX.finditer(text):
        _apply_bound(rules, "min_years", "max_years", float(m.group(1)), "이하", integer=False)
    for m in _YEARS_MIN.finditer(text):
        _apply_bound(rules, "min_years", "max_years", float(m.group(1)), "이상", integer=False)

    for m in _REVENUE.finditer(text):
        amount = int(float(m.group(1)) * _REVENUE_UNITS[m.group(2)])
        _apply_bound(rules, "min_revenue", "max_revenue", amount, m.group(3), integer=False)

    for m in _EMPLOYEES.finditer(text):
        _apply_bound(rules, "min_employees", "max_employees", int(m.group(1)), m.group(2), integer=True)

    for m in _AGE.finditer(text):
        _apply_bound(rules, "min_age", "max_age", int(m.group(1)), m.group(2), integer=True)

    # 긴 표기부터 검사하고, 이미 잡은 표기의 부분문자열은 건너뛴다
    # (예: "예비사회적기업"을 잡았으면 "사회적기업"은 중복 태깅하지 않음).
    for keyword in _TARGET_KEYWORDS:
        if keyword in text and not any(keyword in t for t in rules.target_types):
            rules.target_types.append(keyword)

    return rules
