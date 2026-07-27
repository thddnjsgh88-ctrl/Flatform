"""도메인 모델 정의.

Announcement       : 수집된 지원사업 공고 (원문 자격요건 텍스트 포함)
EligibilityRules   : 공고 원문에서 추출한 구조화된 자격요건
UserProfile        : 자격 판정 대상 사업자(소상공인) 프로필
RuleCheck / Match  : 개별 요건 판정 결과와 공고 단위 종합 판정
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import date


class Source(str, enum.Enum):
    BIZINFO = "bizinfo"      # 기업마당
    KSTARTUP = "kstartup"    # K-Startup
    SAMPLE = "sample"        # 번들 샘플 데이터


@dataclass
class Announcement:
    id: str
    title: str
    organ: str                       # 소관 기관 (부처/지자체/공공기관)
    category: str                    # 지원 분야 (금융, 기술, 판로 등)
    raw_eligibility: str             # 공고 원문의 지원자격 텍스트
    url: str = ""
    apply_start: date | None = None
    apply_end: date | None = None
    source: Source = Source.SAMPLE

    def is_open(self, today: date) -> bool:
        """접수 기간 내 여부. 기간 정보가 없으면 열린 것으로 간주한다."""
        if self.apply_end is not None and today > self.apply_end:
            return False
        if self.apply_start is not None and today < self.apply_start:
            return False
        return True


@dataclass
class EligibilityRules:
    """공고 자격요건의 구조화 표현. 모든 경계값은 포함(inclusive) 기준으로 정규화한다."""

    regions: list[str] = field(default_factory=list)   # 비어 있으면 전국
    min_years: float | None = None                     # 업력 하한 (년)
    max_years: float | None = None                     # 업력 상한 (년)
    min_revenue: int | None = None                     # 연 매출 하한 (원)
    max_revenue: int | None = None                     # 연 매출 상한 (원)
    min_employees: int | None = None                   # 상시근로자 하한 (명)
    max_employees: int | None = None                   # 상시근로자 상한 (명)
    min_age: int | None = None                         # 대표자 나이 하한 (만)
    max_age: int | None = None                         # 대표자 나이 상한 (만)
    target_types: list[str] = field(default_factory=list)  # 소상공인/중소기업/예비창업자/청년

    def is_empty(self) -> bool:
        return not any([
            self.regions, self.target_types,
            self.min_years is not None, self.max_years is not None,
            self.min_revenue is not None, self.max_revenue is not None,
            self.min_employees is not None, self.max_employees is not None,
            self.min_age is not None, self.max_age is not None,
        ])


# 상시근로자 기준으로 소상공인을 판별할 때 업종별 상한 (소상공인기본법 시행령 단순화)
MANUFACTURING_LIKE_INDUSTRIES = ("제조", "건설", "운수", "광업")
SMALL_BUSINESS_EMPLOYEE_LIMIT_DEFAULT = 5
SMALL_BUSINESS_EMPLOYEE_LIMIT_MANUFACTURING = 10

# 특수 기업 특성 대상 사업 (해당 인증/자격이 없으면 신청 불가한 전용 사업).
# 사용자 프로필의 business_traits 와 대조해 전용 사업 여부를 판정한다.
SPECIAL_TARGET_TYPES = (
    "사회적기업", "예비사회적기업", "마을기업", "장애인기업",
    "여성기업", "협동조합", "자활기업", "1인창조기업", "소셜벤처",
)


@dataclass
class UserProfile:
    name: str
    region: str                      # 시도 단위 (서울, 경기, ...)
    industry: str                    # 업종 대분류 표기 (예: "음식점업", "제조업")
    years_in_business: float         # 업력 (년). 0 이면 예비창업자
    annual_revenue: int | None       # 연 매출 (원). 모르면 None
    employees: int                   # 상시근로자 수
    age: int | None = None           # 대표자 나이 (만)
    business_traits: list[str] = field(default_factory=list)  # 사회적기업/여성기업 등 보유 특성

    @property
    def is_pre_startup(self) -> bool:
        return self.years_in_business == 0

    @property
    def small_business_employee_limit(self) -> int:
        if any(k in self.industry for k in MANUFACTURING_LIKE_INDUSTRIES):
            return SMALL_BUSINESS_EMPLOYEE_LIMIT_MANUFACTURING
        return SMALL_BUSINESS_EMPLOYEE_LIMIT_DEFAULT

    @property
    def is_small_business(self) -> bool:
        """상시근로자 수 기준의 소상공인 여부 (매출 기준은 PoC 범위 밖)."""
        return self.employees < self.small_business_employee_limit


class Verdict(str, enum.Enum):
    ELIGIBLE = "적합"
    INELIGIBLE = "부적합"
    UNKNOWN = "판단보류"     # 프로필 정보 부족으로 판정 불가한 요건 존재
    CLOSED = "접수마감"


@dataclass
class RuleCheck:
    name: str                        # 요건 이름 (지역, 업력, 매출, ...)
    passed: bool | None              # None 이면 정보 부족으로 판정 불가
    reason: str                      # 사람이 읽을 수 있는 판정 사유


@dataclass
class MatchResult:
    announcement: Announcement
    rules: EligibilityRules
    verdict: Verdict
    checks: list[RuleCheck] = field(default_factory=list)

    @property
    def failed_checks(self) -> list[RuleCheck]:
        return [c for c in self.checks if c.passed is False]

    @property
    def unknown_checks(self) -> list[RuleCheck]:
        return [c for c in self.checks if c.passed is None]
