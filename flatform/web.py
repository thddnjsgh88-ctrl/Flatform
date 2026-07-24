"""프로필을 입력하면 자격 판정 결과를 보여주는 최소 웹 앱.

파이썬 표준 라이브러리(http.server)만 사용한다. 실행:

    python -m flatform.web                  # 샘플 공고로 실행 (기본)
    python -m flatform.web --source bizinfo  # 기업마당 실 API (BIZINFO_API_KEY 필요)
    python -m flatform.web --port 9000

브라우저에서 http://127.0.0.1:8000 접속.

엔드포인트:
    GET  /                → 프로필 입력 화면(index.html)
    GET  /api/meta        → 로드된 공고 수·출처
    POST /api/match       → 프로필 JSON을 받아 판정 결과 JSON 반환
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .collectors import load_sample_announcements
from .matcher import match_all
from .models import Announcement, MatchResult, UserProfile

STATIC_DIR = Path(__file__).resolve().parent / "static"


def _load_announcements(source: str, count: int) -> tuple[list[Announcement], str]:
    """출처별 공고 로드. 실 API 실패 시 샘플로 자동 폴백한다."""
    if source == "samples":
        return load_sample_announcements(), "번들 샘플"
    try:
        if source == "bizinfo":
            from .collectors import bizinfo
            return bizinfo.fetch_announcements(count=count), "기업마당 API"
        from .collectors import kstartup
        return kstartup.fetch_announcements(count=count), "K-Startup API"
    except Exception as exc:  # noqa: BLE001 - 실 API 미설정/네트워크 실패는 샘플로 폴백
        print(f"⚠️  {source} 수집 실패({exc}). 샘플 공고로 폴백합니다.")
        return load_sample_announcements(), "번들 샘플(폴백)"


def _deadline_info(result: MatchResult, today: date) -> dict:
    end = result.announcement.apply_end
    if end is None:
        return {"label": "상시 접수", "d_day": None}
    days = (end - today).days
    return {"label": end.isoformat(), "d_day": days}


def _serialize(result: MatchResult, today: date) -> dict:
    ann = result.announcement
    return {
        "title": ann.title,
        "organ": ann.organ,
        "category": ann.category,
        "url": ann.url,
        "verdict": result.verdict.value,
        "deadline": _deadline_info(result, today),
        "failed": [c.reason for c in result.failed_checks],
        "unknown": [c.reason for c in result.unknown_checks],
        "passed": [c.reason for c in result.checks if c.passed is True],
    }


def _build_profile(payload: dict) -> UserProfile:
    """폼 입력(JSON)을 UserProfile 로 변환한다. 빈 문자열은 미입력으로 처리한다."""
    def _opt_int(value: object) -> int | None:
        if value in (None, "", "미입력"):
            return None
        return int(value)

    return UserProfile(
        name=str(payload.get("name") or "익명").strip(),
        region=str(payload["region"]).strip(),
        industry=str(payload["industry"]).strip(),
        years_in_business=float(payload["years_in_business"]),
        annual_revenue=_opt_int(payload.get("annual_revenue")),
        employees=int(payload["employees"]),
        age=_opt_int(payload.get("age")),
    )


class Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, announcements, source_label, **kwargs):
        self.announcements = announcements
        self.source_label = source_label
        super().__init__(*args, **kwargs)

    def log_message(self, *args):  # 콘솔 로그 최소화
        pass

    def _send_json(self, obj: dict, status: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str) -> None:
        try:
            body = path.read_bytes()
        except FileNotFoundError:
            self.send_error(404, "Not Found")
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            self._send_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
        elif self.path == "/api/meta":
            self._send_json({"count": len(self.announcements), "source": self.source_label})
        else:
            self.send_error(404, "Not Found")

    def do_POST(self) -> None:
        if self.path != "/api/match":
            self.send_error(404, "Not Found")
            return
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            profile = _build_profile(payload)
        except (ValueError, KeyError) as exc:
            self._send_json({"error": f"입력값 오류: {exc}"}, status=400)
            return

        today = date.today()
        results = match_all(profile, self.announcements, today=today)
        summary: dict[str, int] = {}
        for r in results:
            summary[r.verdict.value] = summary.get(r.verdict.value, 0) + 1
        self._send_json({
            "profile": {"name": profile.name},
            "summary": summary,
            "results": [_serialize(r, today) for r in results],
        })


def main() -> None:
    parser = argparse.ArgumentParser(description="Flatform 자격 판정 웹 앱")
    parser.add_argument("--source", choices=["samples", "bizinfo", "kstartup"], default="samples")
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    announcements, source_label = _load_announcements(args.source, args.count)
    handler = partial(Handler, announcements=announcements, source_label=source_label)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"공고 {len(announcements)}건 로드 ({source_label})")
    print(f"▶ http://{args.host}:{args.port} 접속 (Ctrl+C 로 종료)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n종료합니다.")
        server.shutdown()


if __name__ == "__main__":
    main()
