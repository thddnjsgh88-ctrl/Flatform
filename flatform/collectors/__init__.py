"""공고 수집기 모듈.

- bizinfo  : 기업마당 지원사업정보 API (인증키 필요, https://www.bizinfo.go.kr/apiDetail.do?id=bizinfoApi)
- kstartup : K-Startup 공고 오픈API (공공데이터포털 서비스키 필요, https://www.data.go.kr/data/15125364/openapi.do)
- samples  : 오프라인 개발·데모용 번들 샘플 공고
"""

from .samples import load_sample_announcements

__all__ = ["load_sample_announcements"]
