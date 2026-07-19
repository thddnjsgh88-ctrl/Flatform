# Flatform

정부·지자체 지원사업 공고를 수집해 **자격요건을 구조화**하고, 소상공인 프로필과 대조해
**"지금 신청 가능한 사업"을 판정**해주는 파이프라인 PoC.

핵심 가설: 사용자의 페인포인트는 "공고를 못 찾는 것"이 아니라
**"내가 되는지 판단이 안 되는 것"** 이다. 이 PoC는 그 판정 엔진의 최소 검증판이다.

## 파이프라인 구조

```
[수집]                    [구조화]                 [판정]
기업마당 API  ─┐
K-Startup API ─┼─→ Announcement ─→ parser.py ─→ EligibilityRules ─┐
샘플 데이터    ─┘   (공고+자격 원문)   (규칙 기반 추출)   (지역·업력·매출·   ├─→ matcher.py ─→ 적합/부적합/판단보류/마감
                                                근로자·나이·유형)  │      + 판정 사유
                                              UserProfile ────────┘
```

| 모듈 | 역할 |
|---|---|
| `flatform/collectors/bizinfo.py` | 기업마당 지원사업정보 API 수집 (`BIZINFO_API_KEY` 필요) |
| `flatform/collectors/kstartup.py` | K-Startup 공고 오픈API 수집 (`DATA_GO_KR_KEY` 필요) |
| `flatform/collectors/samples.py` | 오프라인 개발용 샘플 공고 8건 (`data/sample_announcements.json`) |
| `flatform/parser.py` | 공고 원문 → 구조화 자격요건 (정규식 기반, 보수적 추출) |
| `flatform/matcher.py` | 프로필 × 자격요건 판정 + 사람이 읽을 수 있는 사유 생성 |
| `flatform/demo.py` | 3개 데모 프로필로 전체 파이프라인 실행 리포트 |

## 실행

Python 3.11+ / 외부 의존성 없음 (표준 라이브러리만 사용).

```bash
# 데모 (샘플 공고 8건 × 프로필 3명 판정 리포트)
python -m flatform.demo --today 2026-07-19

# 테스트
python -m unittest discover -s tests
```

## 실 API 연동 검증

API 키 발급 (모두 무료):

1. **기업마당**: [bizinfo.go.kr](https://www.bizinfo.go.kr) 회원가입 → 활용정보 > 정책정보 개방 →
   OpenAPI 인증키 신청 → 발급된 인증키를 `BIZINFO_API_KEY` 로 설정
2. **K-Startup**: [data.go.kr](https://www.data.go.kr) 회원가입 →
   "창업진흥원_K-Startup 조회서비스" 검색 → 활용신청(자동승인) →
   마이페이지의 **Decoding 인증키**를 `DATA_GO_KR_KEY` 로 설정

```bash
# macOS/Linux                      # Windows (PowerShell)
export BIZINFO_API_KEY=발급키       $env:BIZINFO_API_KEY="발급키"
export DATA_GO_KR_KEY=발급키        $env:DATA_GO_KR_KEY="발급키"
```

수집 + 파서 커버리지 검증:

```bash
python -m flatform.validate --source bizinfo --count 100
python -m flatform.validate --source kstartup --count 100
python -m flatform.validate --source samples    # 키 없이 리포트 형식 확인
```

원본 응답은 `data/raw/` 에 저장되고, 요건 항목별 추출률과 미추출 공고 예시가
출력된다. 필드 매핑이 어긋나면 실제 필드명 목록을 경고와 함께 보여준다.

## 판정 로직 원칙

- **오판보다 보류**: 파서가 확신 못 하는 요건은 추출하지 않고, 프로필 정보가 부족한
  요건은 `판단보류`로 표시해 "이 정보를 입력하면 판정 가능"을 안내한다.
  → 사용자가 프로필을 채울수록 판정이 정확해지는 구조 = 프로필 DB가 쌓이는 구조.
- **모든 판정에 사유**: 부적합이면 어떤 요건이 어떻게 어긋났는지 문장으로 제시한다.
- **소상공인 판별**: 상시근로자 수 기준(서비스업 5인 미만, 제조·건설·운수·광업 10인 미만)의
  단순화 버전. 매출액 기준(소상공인기본법 시행령)은 후속 과제.

## PoC 한계 (알고 있는 것)

1. **정규식 파서의 재현율**: "전년도 수출실적 보유" 같은 비정형 요건은 추출하지 못해
   해당 요건이 무시된다 (거짓 적합 가능). 실서비스는 LLM 기반 추출 + 사람 검수 큐가 필요.
2. **API 필드 매핑은 best-effort**: 실제 키 발급 후 첫 응답을 보고 필드명 보정 필요.
3. **기초지자체 공고 미수집**: 시·군·구 홈페이지 공고 크롤링이 실질적 차별화 지점이며 후속 과제.
4. **HWP/PDF 첨부 공고문 미처리**: 현재는 공고 요약 텍스트만 파싱한다.

## 다음 단계 후보

- [ ] 실 API 키 발급 후 기업마당·K-Startup 라이브 수집 검증
- [ ] LLM 기반 자격요건 추출기 추가 (정규식 파서와 교차 검증)
- [ ] 사용자 프로필 입력 → 판정 결과를 보여주는 웹 프론트엔드
- [ ] 마감 임박(D-7) 알림
- [ ] 기초지자체 공고 크롤러 1~2곳 파일럿
