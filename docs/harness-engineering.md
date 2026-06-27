# 마케팅 에이전트 하네스 엔지니어링 v2
> 2026-06-28 기준 전체 심층 분석 — P0~P3 완료 후 현재 상태 기록

---

## 1. 시스템 전체 구조

### 1-1. 실행 경로

```
웹 (/run) ──────────────────────────────────────────────┐
                                                        ▼
                                            run_pipeline(job_id, keywords, auto_post)
                                                        │
CLI (orchestrator.py --resume)                         ┌┴──────────────────────────┐
  └─ 직접 에이전트 호출                                 │         Part 1             │
     (체크포인트 기반 재개)                              │  collector × N keywords    │
                                                        │  analyzer  × N keywords    │
스케줄러 (APScheduler)                                  │  writer    × N keywords    │
  └─ scheduled_run(schedule_id)                         │  reporter  (통합 1회)      │
       └─ run_pipeline(auto_post=True)                  │  monitor   (통합 1회)      │
                                                        │  cardnews  × N keywords    │
                                                        └─────────────┬─────────────┘
                                                                      │
                                               auto_post=True?─── True ──▶ _run_pipeline_part2
                                                      │
                                                    False
                                                      │
                                                pending_approval (이메일+슬랙 알림)
                                                      │
                                            /approve/<job_id> POST
                                                      │
                                                      ▼
                                            _run_pipeline_part2
                                            ├─ poster × N keywords    (fatal=False)
                                            └─ instagram × N keywords (fatal=True ← 위험)
                                                      │
                                                   done
```

### 1-2. 상태 머신 (FSM) — `utils/state_machine.py`

```
None ──▶ running ──▶ pending_approval ──▶ posting ──▶ done
              │                                  │
              ├──────────────────────────────────▶ error
              ├──▶ rejected
              └──▶ interrupted  (mark_interrupted: 서버 재시작 시)

interrupted / error ──▶ running (재실행)
```

검증은 `upsert_job()` 호출 시 `validate_transition()` 통과. **현재 위반 시 경고 로그만 남기고 DB에는 기록** — 강제 차단이 없으므로 버그 탐지용도.

### 1-3. 데이터 계층

| 계층 | 저장소 | 수명 | 비고 |
|------|--------|------|------|
| 실시간 | `jobs dict` (in-memory) | 서버 재시작 시 소멸 | SSE 큐 포함 |
| 영속성 | `data/jobs.db` SQLite | 영구 | FSM 검증, 인덱스 3개 |
| 비밀 | `data/.env.enc` Fernet | 영구 | P3-1 추가 |
| 파일 | `output/`, `data/` | 7일 cleanup | KEEP 목록 제외 |
| 로그 | `logs/app.log` | RotatingFile 2MB×5 | P3-2 추가 |

### 1-4. SSE 이벤트 프로토콜

| 이벤트 | 방향 | 의미 |
|--------|------|------|
| `STEP:<name>` | 서버→클 | 에이전트 단계 시작 |
| `LOG:<msg>` | 서버→클 | 에이전트 stdout 한 줄 |
| `ERROR:<msg>` | 서버→클 | 에이전트 실패 |
| `PENDING:<date>` | 서버→클 | Part1 완료, 승인 대기 |
| `DONE:<date>` | 서버→클 | 전체 완료 |
| `REJECTED` | 서버→클 | 사용자 거절 |
| `PING` | 서버→클 | 60초 keep-alive |

### 1-5. 에이전트별 핵심 정보

| # | 에이전트 | 입력 | 출력 | 외부 의존성 | fatal |
|---|---------|------|------|------------|-------|
| 1 | collector | keyword | `data/{kw}_{date}.json` | Naver API | True |
| 2 | analyzer | 수집 JSON | `data/analyzed_{kw}_{date}.json` | Gemini, 데이터랩 | True |
| 3 | writer | 분석 JSON | `output/content_{kw}_{date}.json` | Gemini | True |
| 4 | reporter | content×N | `output/report_{date}.{html,pdf}` | Gemini, Playwright | True |
| 5 | monitor | keywords | `data/monitor_log_{date}.json` | Gemini, Naver | True |
| 6 | cardnews | content JSON | `output/cardnews_{kw}_{date}_{1-4}.png` + imgbb URL JSON | Imagen, imgbb | False |
| 7a | poster | content JSON | 네이버 블로그 URL | Playwright | **False** |
| 7b | instagram | imgbb URLs | Instagram media_id | Meta Graph API | **True** ← 위험 |

---

## 2. 완료된 수정 사항 (P0~P3)

### P0: 서비스 중단급 버그 수정

| ID | 파일 | 수정 내용 |
|----|------|---------|
| P0-1 | `app.py` | `interrupted` 상태 SSE 복원: `ERROR:서버 재시작...` + `DONE` 전송 |
| P0-2 | `agents/instagram/main.py` | carousel_id 캐시 (`data/ig_pending_{kw}_{date}.json`), **8h TTL 만료 체크** (created_at 저장) |
| P0-3 | `app.py` | `_resolve_job_date()`: 모든 키워드 스캔 후 최다 날짜 반환 |

### P1: 안정성 수정

| ID | 파일 | 수정 내용 |
|----|------|---------|
| P1-1 | `app.py` | SSE `DONE:<date>` 형식 통일 |
| P1-2 | `app.py` | 복수 키워드 부분 실패 시 `LOG:⚠️` + `notify_error()` |
| P1-3 | (미완) | Naver 쿠키 세션 실사용 검증 — 미구현 |
| P1-4 | `utils/job_store.py` | DB 인덱스 3개 추가 |
| P1-5 | `agents/instagram/main.py` | 토큰 만료 7일 전 경고 + `send_alert()` |

### P2: UX & 운영성

| ID | 파일 | 수정 내용 |
|----|------|---------|
| P2-1 | `app.py`, `templates/index.html` | `/logs/<job_id>` 엔드포인트 + 히스토리 🔍 로그 버튼 |
| P2-2 | `app.py` | `_run_pipeline_part2`: cardnews 4장 확인 후 `--carousel` 조건부 추가 (기존 구현 확인) |
| P2-3 | `app.py` | `scheduled_run` 예외 시 `notify_error()` 추가 |
| P2-4 | — | history.json 레거시 제거 보류 (analyzer가 활발히 사용 중) |

### P3: 아키텍처 리팩터링

| ID | 파일 | 수정 내용 |
|----|------|---------|
| P3-1 | `utils/secrets.py`, `app.py`, `scripts/encrypt_env.py` | `.env` 민감 변수 Fernet 암호화 → `data/.env.enc` |
| P3-2 | `utils/logging_setup.py`, `app.py` | JSON 포맷터 + `_log` 로거 적용 (app.py 스케줄러·백업·ig-token) |
| P3-3 | `utils/state_machine.py`, `utils/job_store.py` | FSM 허용 전이 정의 + `upsert_job` 검증 통합 |
| P3-4 | `tests/test_state_machine.py`, `tests/test_secrets.py` | 27 tests 추가 (전체 174 passed) |

---

## 3. 현재 남아있는 버그 & 위험 요소

### ─── 🔴 높음 (즉시 수정 권장) ───

#### BUG-1 │ Instagram `fatal=True` — 다중 키워드 잡에서 부분 성공 불가
- **위치**: `app.py` `_run_pipeline_part2()` (line ~334)
- **현상**: N개 키워드 잡에서 keyword 1 인스타 성공, keyword 2 인스타 실패 시 잡 전체 `error` 상태가 됨
- **위험**: 블로그는 성공(fatal=False)했는데 인스타 실패로 전체 실패 처리
- **수정**: instagram도 `fatal=False`로 변경 후 별도 에러 알림 처리
```python
# 현재 (문제)
if not _run_cmd(job_id, f"인스타그램 [{keyword}]", ..., ig_args):
    return  # 이후 키워드도 중단

# 개선
ok = _run_cmd(job_id, f"인스타그램 [{keyword}]", ..., ig_args, fatal=False)
if not ok:
    jobs[job_id]["queue"].put(f"LOG:⚠️ [{keyword}] 인스타그램 발행 실패 — 다음 키워드 계속")
    threading.Thread(target=notify_error, args=([keyword], "인스타그램", "발행 실패"), daemon=True).start()
```

#### BUG-2 │ `cardnews_urls_{kw}_{date}.json` 존재 미확인 후 `--carousel` 전달
- **위치**: `app.py` `_run_pipeline_part2()` (line ~326)
- **현상**: PNG 4장은 있는데 imgbb JSON 파일이 없으면 instagram agent가 `FileNotFoundError`로 실패
- **원인**: cardnews 에이전트가 PNG 생성 후 imgbb 업로드 실패 시 PNG는 남고 JSON은 없는 상태 가능
- **수정**:
```python
json_ready = (ROOT / "output" / f"cardnews_urls_{safe_kw}_{today}.json").exists()
cardnews_ready = json_ready and all(PNG 4장 exists)
```

### ─── 🟡 중간 (1주 내 수정) ───

#### BUG-3 │ `data/ig_pending_*.json` 영구 누적
- **위치**: `utils/cleanup.py` `_PATTERNS`
- **현상**: 인스타그램 발행 실패한 키워드마다 캐시 파일 누적, cleanup 대상에 없음
- **수정**: `_PATTERNS`에 `"data/ig_pending_*.json"` 추가 (1일 retention)

#### BUG-4 │ `data/instagram_error_*.json` 영구 누적
- **위치**: `utils/cleanup.py` `_PATTERNS`
- **현상**: 에러 로그가 무한 누적
- **수정**: `_PATTERNS`에 `"data/instagram_error_*.json"` 추가 (14일 retention)

#### BUG-5 │ `LoginRateLimiter` 서버 재시작 시 초기화
- **위치**: `utils/auth_guard.py`, `app.py` (line 91)
- **현상**: `_rate_limiter = LoginRateLimiter(...)` 가 in-memory — 재시작하면 잠금 해제
- **위험**: 공격자가 서버 재시작을 유도해 브루트포스 가능
- **수정**: 잠금 상태를 `data/rate_limit.json` 또는 jobs.db에 영속

#### BUG-6 │ `/rerun` 엔드포인트에서 `user_id` / `auto_post` 복원 안됨
- **위치**: `app.py` `rerun()` (line ~693)
- **현상**: 재실행 시 항상 `pending_approval`로 가고 원래 user_id가 없어짐
- **수정**: DB에서 `user_id` 복원, `auto_post` 여부는 옵션으로 받기

### ─── 🟢 낮음 (개선사항) ───

#### IMPROVE-1 │ `notifier.py` / `cleanup.py` 여전히 `print()` 사용
- P3-2에서 `app.py`만 적용, 나머지 유틸은 미적용
- **수정**: `get_logger("notifier")`, `get_logger("cleanup")` 적용

#### IMPROVE-2 │ `_prune_jobs()` 호출 지점이 `/run` 하나뿐
- 서버가 오래 실행되면서 새 잡이 없으면 메모리 누적
- **수정**: `_run_cleanup()` 내에서도 `_prune_jobs()` 호출 또는 APScheduler 주기 추가

#### IMPROVE-3 │ 다중 키워드 병렬 실행 시 SSE 로그 순서 뒤섞임
- `ThreadPoolExecutor`로 N개 키워드가 동시에 `queue.put(LOG:...)` 호출
- 프론트엔드 콘솔 UI에서 키워드가 섞여 보임
- **수정**: 각 키워드별 로그에 `[{keyword}]` 접두어 명시 (이미 일부 적용됨, 통일 필요)

#### IMPROVE-4 │ P1-3 Naver 쿠키 실사용 검증 미완
- 현재 `_cookies_valid()` 는 로컬 시간 만료만 확인
- 실제 세션이 만료된 경우 에디터 진입 후 실패 → 스크린샷 저장 후 종료
- **수정**: 사전 경량 API 호출로 세션 유효성 확인

#### IMPROVE-5 │ FSM 전이 위반 시 `경고 로그만` — 실제 차단 없음
- `upsert_job()` 내 `validate_transition()` 실패해도 `_log.warning()`만
- 운영 안정성을 위해 **의도적으로** 경고만 하도록 설계됐지만, 비정상 전이 추적 대시보드 없음
- **수정**: `/stats` 응답에 `fsm_violations` 카운터 포함

---

## 4. 에이전트별 실패 시나리오 매트릭스

| 에이전트 | 실패 원인 | 현재 처리 | 개선 필요 |
|---------|---------|---------|---------|
| collector | Naver API 할당량 / 네트워크 | fatal=True → error | ✅ 충분 |
| analyzer | Gemini 429 rate limit | `gemini_retry` 8회 | ✅ 충분 |
| writer | 입력 파일 없음 | sys.exit(1) → fatal | ✅ 충분 |
| reporter | Gemini 실패 | 3개 모델 폴백 | ✅ 충분 |
| monitor | 신규 포스트 없음 | 정상 종료 (0) | ✅ 충분 |
| cardnews | Imagen 한도 / imgbb 실패 | fatal=False → 경고 | PNG 있고 JSON 없는 케이스 방어 필요 |
| poster | CAPTCHA / 쿠키 만료 | fatal=False → 경고 | P1-3 세션 사전 검증 |
| instagram | rate limit 2207051 | carousel 캐시 + 8h TTL | BUG-1, BUG-2 수정 필요 |

---

## 5. 보안 체크리스트

| 항목 | 현재 상태 | 비고 |
|------|---------|------|
| 로그인 세션 쿠키 | `HttpOnly + SameSite=Lax` ✅ | FORCE_HTTPS=1 시 Secure 추가 |
| 브루트포스 방어 | 5회 실패 시 15분 잠금 ✅ | `data/rate_lockouts.json` 영속화 (P5-BUG5) |
| API 키 인증 | `hmac.compare_digest` 상수 시간 비교 ✅ | |
| 민감 환경변수 | `.env.enc` Fernet 암호화 ✅ (P3-1) | `scripts/encrypt_env.py` 실행 필요 |
| 파일 경로 검증 | `re.sub` 특수문자 제거 ✅ | |
| CSRF | `X-CSRF-Token` 헤더 검증 ✅ (P6-2) | `/login`·`X-API-Key` 면제, 세션 기반 토큰 |
| SQL Injection | parameterized query ✅ | |
| XSS | Jinja2 auto-escape ✅ + `esc()` 전수 적용 ✅ (P6-3) | 스케줄 onclick `_scheduleCache` 방식으로 직렬화 제거 |

---

## 6. 운영 참고

### 서버 정보
- IP: `34.11.175.125`, Port: `5000`
- Gunicorn: `--workers 1 --worker-class gthread --threads 4 --timeout 0`
- 단일 워커 → `jobs dict` 공유 안전. 멀티 워커 전환 시 반드시 Redis 등 외부 상태 저장소 필요.

### 주요 파일 위치
```
data/jobs.db              잡 상태 DB (SQLite)
data/.enc_key             Fernet 마스터 키 (권한 600, 백업 필수)
data/.env.enc             암호화된 민감 환경변수
data/.flask_secret        Flask 세션 서명 키
data/naver_cookies.json   Naver 로그인 세션 (Fernet 암호화)
data/ig_pending_*.json    Instagram carousel 캐시 (8h TTL)
logs/app.log              앱 로그 (RotatingFile 2MB×5)
```

### 배포 절차
```bash
cd ~/marketing-agent
git pull
sudo systemctl restart marketing-agent
sudo systemctl is-active marketing-agent  # active 확인

# 첫 배포 후 민감 변수 암호화 (1회)
python scripts/encrypt_env.py
# .env에서 암호화된 키 제거 후 재시작
```

### 인스타그램 rate limit 대응
- `code=4 subcode=2207051`: 앱 레벨 콘텐츠 발행 한도 소진
- **24~48시간 대기** 후 자동 해제
- 재시도 시 캐시된 carousel_id 재사용 (컨테이너 재생성 방지)
- 캐시 8h 초과 시 자동 삭제 후 신규 컨테이너 생성

---

## 7. 다음 우선순위 로드맵

### Phase 4 ✅ 완료
1. **BUG-1** ✅: Instagram `fatal=False` + 다중 키워드 독립 처리
2. **BUG-2** ✅: `cardnews_urls JSON` 존재 확인 후 `--carousel` 전달
3. **BUG-3/4** ✅: cleanup 패턴에 `ig_pending_*.json`, `instagram_error_*.json` 추가
4. **P1-3**: Naver 쿠키 사전 세션 검증 (미구현 — 위험도 낮음)

### Phase 5 ✅ 완료
5. **BUG-5** ✅: `LoginRateLimiter` 영속화 (`data/rate_lockouts.json`)
6. **BUG-6** ✅: `/rerun` user_id 복원
7. **IMPROVE-1** ✅: notifier/cleanup 구조화 로그
8. **IMPROVE-2** ✅: `_prune_jobs()` APScheduler 30분 잡

### Phase 6 ✅ 완료 (2026-06-28)
9. 멀티 워커 지원 — Redis 기반 `jobs` 상태 공유 (**미구현**, 월 단위 대형 작업 — workers=1 유지)
10. **CSRF 토큰** ✅: `X-CSRF-Token` 헤더 검증, `csrfFetch()` 래퍼 (index.html·admin.html)
11. **XSS 수정** ✅: 스케줄 onclick `JSON.stringify` 제거 → `_scheduleCache[id]` 참조
12. **로그 UI 개선** ✅: 키워드별 색상 바 (`_kwColorMap`, `appendLog()` 패턴 감지)

### Phase 7 (다음 후보)
- **멀티 워커**: Redis pub/sub으로 `jobs` dict 대체 (현재 workers=1 필수)
- **P1-3**: Naver 쿠키 사전 세션 유효성 검증
- **Instagram 캐러셀 UI**: 발행 전 PNG 미리보기
- **알림 채널 확장**: 카카오톡·디스코드 Webhook
