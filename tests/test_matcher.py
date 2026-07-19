import unittest
from datetime import date

from flatform.matcher import match, match_all
from flatform.models import Announcement, UserProfile, Verdict

TODAY = date(2026, 7, 19)


def make_announcement(eligibility: str, apply_end: date | None = date(2026, 8, 31)) -> Announcement:
    return Announcement(
        id="test", title="테스트 공고", organ="테스트기관", category="테스트",
        raw_eligibility=eligibility, apply_end=apply_end,
    )


SEOUL_CAFE = UserProfile(
    name="카페", region="서울", industry="음식점업",
    years_in_business=3, annual_revenue=250_000_000, employees=2, age=34,
)


class TestMatch(unittest.TestCase):
    def test_eligible(self):
        ann = make_announcement("서울특별시 소재 소상공인, 상시근로자 5인 미만, 연 매출액 10억원 이하")
        result = match(SEOUL_CAFE, ann, today=TODAY)
        self.assertEqual(result.verdict, Verdict.ELIGIBLE)

    def test_region_mismatch(self):
        ann = make_announcement("경기도 관내 소재 소상공인")
        result = match(SEOUL_CAFE, ann, today=TODAY)
        self.assertEqual(result.verdict, Verdict.INELIGIBLE)
        self.assertEqual(result.failed_checks[0].name, "지역")

    def test_unknown_when_revenue_missing(self):
        profile = UserProfile(
            name="미입력", region="서울", industry="음식점업",
            years_in_business=1, annual_revenue=None, employees=1,
        )
        ann = make_announcement("연 매출액 5억원 이하 사업자")
        result = match(profile, ann, today=TODAY)
        self.assertEqual(result.verdict, Verdict.UNKNOWN)

    def test_closed_overrides_eligibility(self):
        ann = make_announcement("전국 소상공인 누구나", apply_end=date(2026, 6, 30))
        result = match(SEOUL_CAFE, ann, today=TODAY)
        self.assertEqual(result.verdict, Verdict.CLOSED)

    def test_small_business_limit_by_industry(self):
        # 제조업은 상시근로자 10인 미만까지 소상공인으로 인정
        factory = UserProfile(
            name="공장", region="경기", industry="제조업",
            years_in_business=6, annual_revenue=1_200_000_000, employees=8, age=52,
        )
        ann = make_announcement("전국 소상공인 대상 지원")
        self.assertEqual(match(factory, ann, today=TODAY).verdict, Verdict.ELIGIBLE)

        service = UserProfile(
            name="식당", region="경기", industry="음식점업",
            years_in_business=6, annual_revenue=500_000_000, employees=8, age=52,
        )
        self.assertEqual(match(service, ann, today=TODAY).verdict, Verdict.INELIGIBLE)

    def test_pre_startup_only_announcement(self):
        ann = make_announcement("부산광역시 소재 예비창업자 중 만 40세 이상")
        pre = UserProfile(
            name="예비", region="부산", industry="정보통신업",
            years_in_business=0, annual_revenue=None, employees=0, age=45,
        )
        self.assertEqual(match(pre, ann, today=TODAY).verdict, Verdict.ELIGIBLE)
        self.assertEqual(match(SEOUL_CAFE, ann, today=TODAY).verdict, Verdict.INELIGIBLE)

    def test_pre_startup_with_years_alternative(self):
        # "예비창업자 및 창업 3년 이내" 공고는 3년차 기업도 적합해야 한다
        ann = make_announcement("전국의 예비창업자 및 창업 후 3년 이내 기업")
        self.assertEqual(match(SEOUL_CAFE, ann, today=TODAY).verdict, Verdict.ELIGIBLE)

    def test_sort_order(self):
        anns = [
            make_announcement("경기도 관내 소재 기업"),                        # 부적합
            make_announcement("전국 소상공인 누구나"),                         # 적합
            make_announcement("전국 대상", apply_end=date(2026, 1, 1)),        # 마감
        ]
        results = match_all(SEOUL_CAFE, anns, today=TODAY)
        self.assertEqual(
            [r.verdict for r in results],
            [Verdict.ELIGIBLE, Verdict.INELIGIBLE, Verdict.CLOSED],
        )


if __name__ == "__main__":
    unittest.main()
