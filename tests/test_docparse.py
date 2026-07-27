import tempfile
import unittest
import zipfile
from pathlib import Path

from flatform.docparse import UnsupportedFormat, extract_rules, extract_text


class TestDocParse(unittest.TestCase):
    def _tmp(self, name: str, write) -> Path:
        d = Path(tempfile.mkdtemp())
        p = d / name
        write(p)
        return p

    def test_txt_extracts_numeric_criteria(self):
        # v2 핵심: 문서 본문을 넣으면 API 에 없던 숫자 자격이 추출된다
        p = self._tmp("g.txt", lambda p: p.write_text(
            "서울특별시 소재 소상공인, 상시근로자 5인 미만, 연 매출액 10억원 이하, 만 39세 이하",
            encoding="utf-8"))
        text, rules = extract_rules(p)
        self.assertEqual(rules.regions, ["서울"])
        self.assertEqual(rules.max_employees, 4)
        self.assertEqual(rules.max_revenue, 1_000_000_000)
        self.assertEqual(rules.max_age, 39)
        self.assertIn("소상공인", rules.target_types)

    def test_hwpx_extracts_text(self):
        section = ('<?xml version="1.0" encoding="UTF-8"?>'
                   '<hml xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
                   '<hp:p><hp:run><hp:t>경기도 관내 중소기업, 상시근로자 10명 이하</hp:t></hp:run></hp:p>'
                   '</hml>')

        def write(p):
            with zipfile.ZipFile(p, "w") as z:
                z.writestr("Contents/section0.xml", section)

        p = self._tmp("g.hwpx", write)
        text, rules = extract_rules(p)
        self.assertIn("중소기업", rules.target_types)
        self.assertEqual(rules.max_employees, 10)
        self.assertEqual(rules.regions, ["경기"])

    def test_unsupported_format(self):
        p = self._tmp("g.docx", lambda p: p.write_bytes(b"PK\x03\x04"))
        with self.assertRaises(UnsupportedFormat):
            extract_text(p)

    def test_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            extract_text("/nonexistent/path/g.pdf")


if __name__ == "__main__":
    unittest.main()
