"""공고문 첨부파일(PDF/HWPX/HWP/TXT)에서 본문 텍스트를 추출하는 v2 모듈.

핵심 아이디어: 기존 parser 는 이미 매출·상시근로자·나이·업력을 정규식으로 뽑는다.
API 요약 텍스트에는 그 숫자가 없어서 못 뽑았을 뿐이므로, 공고문 본문 텍스트만
넣어주면 그대로 동작한다. 이 모듈은 "문서 → 텍스트" 만 책임진다.

지원 형식:
    .txt   표준 라이브러리
    .pdf   pypdf (pip install pypdf)
    .hwpx  표준 라이브러리 (zip + xml)
    .hwp   LibreOffice(soffice)로 pdf 변환 후 추출 — soffice 설치 필요

실행:
    python -m flatform.docparse 공고문.pdf          # 추출된 자격요건 출력
    python -m flatform.docparse 공고문.hwp --text   # 추출된 원문 텍스트도 출력
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from .models import EligibilityRules
from .parser import extract_eligibility


class UnsupportedFormat(Exception):
    pass


def _extract_txt(path: Path) -> str:
    for enc in ("utf-8", "cp949", "euc-kr"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="ignore")


def _extract_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # 사용자 안내
        raise UnsupportedFormat(
            "PDF 추출에는 pypdf 가 필요합니다. 먼저 실행하세요:  pip install pypdf"
        ) from exc
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _extract_hwpx(path: Path) -> str:
    """HWPX 는 zip 컨테이너. Contents/section*.xml 의 텍스트 노드(<*:t>)를 모은다."""
    texts: list[str] = []
    with zipfile.ZipFile(path) as zf:
        section_files = sorted(
            n for n in zf.namelist()
            if re.search(r"Contents/section\d+\.xml$", n)
        )
        for name in section_files:
            raw = zf.read(name)
            try:
                root = ET.fromstring(raw)
            except ET.ParseError:
                texts.append(_strip_xml(raw.decode("utf-8", "ignore")))
                continue
            for el in root.iter():
                # 네임스페이스를 떼어낸 지역명이 't'(텍스트 런)인 노드
                if el.tag.rsplit("}", 1)[-1] == "t" and el.text:
                    texts.append(el.text)
    return " ".join(texts)


def _strip_xml(s: str) -> str:
    return re.sub(r"<[^>]+>", " ", s)


def _extract_hwp_via_soffice(path: Path) -> str:
    """구형 HWP(바이너리)는 LibreOffice 로 PDF 변환 후 추출한다."""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise UnsupportedFormat(
            ".hwp(구형) 추출에는 LibreOffice 가 필요합니다. "
            "libreoffice.org 에서 설치하거나, 공고문을 PDF 로 저장해 사용하세요."
        )
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            [soffice, "--headless", "--convert-to", "pdf", "--outdir", tmp, str(path)],
            check=True, capture_output=True, timeout=120,
        )
        pdfs = list(Path(tmp).glob("*.pdf"))
        if not pdfs:
            raise UnsupportedFormat("LibreOffice 변환 결과 PDF 를 찾지 못했습니다.")
        return _extract_pdf(pdfs[0])


def extract_text(path: str | Path) -> str:
    """공고문 파일에서 본문 텍스트를 추출한다. 형식은 확장자로 판별한다."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return _extract_txt(path)
    if suffix == ".pdf":
        return _extract_pdf(path)
    if suffix == ".hwpx":
        return _extract_hwpx(path)
    if suffix == ".hwp":
        return _extract_hwp_via_soffice(path)
    raise UnsupportedFormat(f"지원하지 않는 형식입니다: {suffix} (지원: .pdf .hwpx .hwp .txt)")


def extract_rules(path: str | Path) -> tuple[str, EligibilityRules]:
    """공고문 → 본문 텍스트 → 구조화된 자격요건. (텍스트, 규칙)을 반환한다."""
    text = extract_text(path)
    return text, extract_eligibility(text)


def _print_rules(rules: EligibilityRules) -> None:
    rows = [
        ("지역", ", ".join(rules.regions) or "—"),
        ("업력", _range(rules.min_years, rules.max_years, "년")),
        ("매출", _revenue(rules.min_revenue, rules.max_revenue)),
        ("상시근로자", _range(rules.min_employees, rules.max_employees, "명")),
        ("나이", _range(rules.min_age, rules.max_age, "세")),
        ("대상유형", ", ".join(rules.target_types) or "—"),
    ]
    print("\n추출된 자격요건")
    print("-" * 40)
    for label, value in rows:
        print(f"  {label:<6}: {value}")
    if rules.is_empty():
        print("  (자격요건을 하나도 추출하지 못했습니다)")


def _range(lo, hi, unit: str) -> str:
    if lo is None and hi is None:
        return "—"
    if lo is not None and hi is not None:
        return f"{lo:g}~{hi:g}{unit}"
    if hi is not None:
        return f"{hi:g}{unit} 이하"
    return f"{lo:g}{unit} 이상"


def _revenue(lo, hi) -> str:
    def fmt(won):
        return f"{won / 100_000_000:g}억원" if won >= 100_000_000 else f"{won / 10_000:g}만원"
    if lo is None and hi is None:
        return "—"
    if hi is not None and lo is None:
        return f"{fmt(hi)} 이하"
    if lo is not None and hi is None:
        return f"{fmt(lo)} 이상"
    return f"{fmt(lo)}~{fmt(hi)}"


def main() -> None:
    ap = argparse.ArgumentParser(description="공고문에서 자격요건 추출 (v2)")
    ap.add_argument("file", help="공고문 파일 경로 (.pdf .hwpx .hwp .txt)")
    ap.add_argument("--text", action="store_true", help="추출된 원문 텍스트도 출력")
    args = ap.parse_args()

    try:
        text, rules = extract_rules(args.file)
    except (UnsupportedFormat, FileNotFoundError) as exc:
        print(f"오류: {exc}")
        raise SystemExit(1)

    print(f"본문 텍스트 {len(text):,}자 추출")
    if args.text:
        print("-" * 40)
        print(text[:2000] + ("…" if len(text) > 2000 else ""))
    _print_rules(rules)


if __name__ == "__main__":
    main()
