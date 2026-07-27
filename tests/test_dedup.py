import unittest

from flatform.dedup import deduplicate, normalize_title
from flatform.models import Announcement


def ann(id, title, organ="기관", elig="", doc_url=""):
    return Announcement(id=id, title=title, organ=organ, category="",
                        raw_eligibility=elig, doc_url=doc_url)


class TestNormalizeTitle(unittest.TestCase):
    def test_strips_year_round_and_boilerplate(self):
        a = normalize_title("2026년 청년창업 지원사업 참여기업 모집 공고 (2차)")
        b = normalize_title("청년창업 지원사업 (재공고)")
        self.assertEqual(a, b)

    def test_region_preserved(self):
        # 지역이 다르면 다른 사업으로 본다 (거짓 병합 방지)
        self.assertNotEqual(
            normalize_title("[경북] 창업지원사업"),
            normalize_title("[대구] 창업지원사업"),
        )


class TestDeduplicate(unittest.TestCase):
    def test_cross_source_duplicate_merged(self):
        items = [
            ann("bizinfo-1", "2026년 청년창업 지원사업 모집공고", elig="짧음"),
            ann("kstartup-1", "청년창업 지원사업 (2차)", elig="더 긴 자격요건 텍스트", doc_url="u"),
        ]
        result = deduplicate(items)
        self.assertEqual(len(result), 1)
        # 더 풍부한(공고문 URL 보유) 레코드가 살아남는다
        self.assertEqual(result[0].id, "kstartup-1")

    def test_distinct_regions_kept(self):
        items = [
            ann("a", "[경북] 창업지원사업 공고"),
            ann("b", "[대구] 창업지원사업 공고"),
        ]
        self.assertEqual(len(deduplicate(items)), 2)

    def test_order_preserved(self):
        items = [ann("a", "사업 A"), ann("b", "사업 B"), ann("c", "사업 C")]
        self.assertEqual([x.id for x in deduplicate(items)], ["a", "b", "c"])

    def test_same_title_different_organ_kept(self):
        items = [ann("a", "경영개선 지원", organ="서울시"),
                 ann("b", "경영개선 지원", organ="부산시")]
        self.assertEqual(len(deduplicate(items)), 2)


if __name__ == "__main__":
    unittest.main()
