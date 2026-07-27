import tempfile
import unittest
from datetime import date
from pathlib import Path

from flatform.enrich import match_with_document
from flatform.matcher import match, merge_rules
from flatform.models import Announcement, EligibilityRules, UserProfile, Verdict

TODAY = date(2026, 7, 27)


class TestMergeRules(unittest.TestCase):
    def test_extra_fills_gaps(self):
        base = EligibilityRules(regions=["대구"])
        extra = EligibilityRules(min_employees=30, required_industries=["제조업"])
        merged = merge_rules(base, extra)
        self.assertEqual(merged.regions, ["대구"])
        self.assertEqual(merged.min_employees, 30)
        self.assertEqual(merged.required_industries, ["제조업"])

    def test_takes_stricter_bounds(self):
        base = EligibilityRules(max_revenue=1_000_000_000, min_employees=5)
        extra = EligibilityRules(max_revenue=500_000_000, min_employees=30)
        merged = merge_rules(base, extra)
        self.assertEqual(merged.max_revenue, 500_000_000)   # 상한은 더 작은 값
        self.assertEqual(merged.min_employees, 30)          # 하한은 더 큰 값

    def test_target_types_union(self):
        merged = merge_rules(
            EligibilityRules(target_types=["중소기업"]),
            EligibilityRules(target_types=["중소기업", "제조업"]),
        )
        self.assertEqual(merged.target_types, ["중소기업", "제조업"])


class TestMatchWithDocument(unittest.TestCase):
    def _doc(self, text: str) -> Path:
        p = Path(tempfile.mkdtemp()) / "g.txt"
        p.write_text(text, encoding="utf-8")
        return p

    def test_document_overturns_false_eligible(self):
        # API 요약만으로는 '적합'이지만 공고문 정밀 요건으로 '부적합'이 되어야 한다
        ann = Announcement(id="x", title="달성군", organ="달성군", category="",
                           raw_eligibility="대구 소재 중소기업")
        cafe = UserProfile(name="카페", region="대구", industry="음식점업",
                           years_in_business=3, annual_revenue=None, employees=2)
        self.assertEqual(match(cafe, ann, today=TODAY).verdict, Verdict.ELIGIBLE)

        doc = self._doc("대구 달성군 소재, 상시근로자 30명 이상, 대상 업종이 제조업 영위 기업")
        result = match_with_document(cafe, ann, doc_path=doc, today=TODAY)
        self.assertEqual(result.verdict, Verdict.INELIGIBLE)

    def test_falls_back_to_api_when_no_document(self):
        ann = Announcement(id="x", title="t", organ="o", category="",
                           raw_eligibility="전국 소상공인")
        cafe = UserProfile(name="카페", region="서울", industry="음식점업",
                           years_in_business=3, annual_revenue=None, employees=2)
        # 문서 없음 → API 요건만으로 판정 (예외 없이 동작)
        result = match_with_document(cafe, ann, doc_path=None, today=TODAY)
        self.assertEqual(result.verdict, Verdict.ELIGIBLE)


if __name__ == "__main__":
    unittest.main()
