import unittest

from flatform.parser import extract_eligibility, extract_regions


class TestRegionExtraction(unittest.TestCase):
    def test_region_with_context(self):
        rules = extract_eligibility("서울특별시 소재 소상공인")
        self.assertEqual(rules.regions, ["서울"])

    def test_long_name_normalized(self):
        self.assertEqual(extract_regions("경상북도 관내 기업"), ["경북"])

    def test_nationwide_means_no_restriction(self):
        self.assertEqual(extract_regions("전국 소상공인 누구나"), [])

    def test_region_without_context_ignored(self):
        # '소재'류 문맥 없이 등장한 지역명은 제한으로 해석하지 않는다
        self.assertEqual(extract_regions("부산 지역경제 활성화를 위한 사업"), [])


class TestNumericExtraction(unittest.TestCase):
    def test_years_max(self):
        rules = extract_eligibility("창업 후 7년 이내 기업")
        self.assertEqual(rules.max_years, 7)

    def test_years_min(self):
        rules = extract_eligibility("업력 2년 이상인 사업자")
        self.assertEqual(rules.min_years, 2)

    def test_revenue_billion(self):
        rules = extract_eligibility("연 매출액 10억원 이하인 사업자")
        self.assertEqual(rules.max_revenue, 1_000_000_000)

    def test_revenue_ten_million(self):
        rules = extract_eligibility("매출액 3천만원 이상")
        self.assertEqual(rules.min_revenue, 30_000_000)

    def test_employees_strict_less_than(self):
        rules = extract_eligibility("상시근로자 수 5인 미만")
        self.assertEqual(rules.max_employees, 4)

    def test_employees_at_most(self):
        rules = extract_eligibility("상시 근로자 10명 이하")
        self.assertEqual(rules.max_employees, 10)

    def test_age_range(self):
        rules = extract_eligibility("만 19세 이상 만 39세 이하 청년")
        self.assertEqual(rules.min_age, 19)
        self.assertEqual(rules.max_age, 39)


class TestTargetTypes(unittest.TestCase):
    def test_keywords_collected(self):
        rules = extract_eligibility("예비창업자 및 창업 3년 이내 소상공인")
        self.assertIn("예비창업자", rules.target_types)
        self.assertIn("소상공인", rules.target_types)

    def test_empty_text(self):
        self.assertTrue(extract_eligibility("자세한 내용은 공고문 참조").is_empty())


if __name__ == "__main__":
    unittest.main()
