# 웹 스케줄러 관리 기능 — 설계

## Context
현재 예약 포스팅은 `app.py`의 `scheduled_run()`이 `CronTrigger(hour=9, minute=0)`(매일 09:00, 월요일 아님)로 고정돼 있고, 대상 키워드는 `.env`의 `SCHEDULED_KEYWORDS`에서 읽는다. 서버 `.env`에 키워드가 미설정이라 **현재 사실상 아무것도 발행되지 않으며**, 요일·시간·키워드·채널을 바꾸려면 코드/.env 수정 + 재배포가 필요하다.

목표: **웹 UI에서 여러 개의 예약 스케줄을 직접 추가/수정/삭제**하고, 각 스케줄이 미리 저장한 커스텀 설정(키워드·요일·시간·발행 채널·활성화)대로 **승인 없이 자동 발행**되게 한다. 변경은 서버 재시작 없이 즉시 반영된다.

## 비목표 (YAGNI)
- 스케줄별 캡션 톤/이미지 스타일 커스텀 (현행 콘텐츠 생성 로직 그대로 사용)
- 분 단위보다 세밀한 주기, 1회성 예약, 타임존 선택(Asia/Seoul 고정)
- 스케줄 실행 이력 별도 화면 (기존 `/history`로 충분)

---

## 1. 데이터 모델
`data/jobs.db`(SQLite)에 `schedules` 테이블 신설, `utils/job_store.py`에 CRUD 추가.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | INTEGER PK AUTOINCREMENT | 스케줄 식별자 |
| `name` | TEXT | 표시용 라벨(선택, 비면 키워드로 대체) |
| `keywords` | TEXT(JSON 배열) | 실행할 키워드들 |
| `days` | TEXT | 요일 cron 표기, 예 `"mon,thu"` |
| `hour` | INTEGER | 0–23 |
| `minute` | INTEGER | 0–59 |
| `post_blog` | INTEGER(0/1) | 네이버 블로그 발행 여부 |
| `post_instagram` | INTEGER(0/1) | 인스타그램 발행 여부 |
| `enabled` | INTEGER(0/1) | 활성/일시중지 |
| `created_at`, `updated_at` | TEXT(ISO8601) | |

`job_store.py` 함수: `init_db`에 테이블 생성 추가, `create_schedule`, `update_schedule`, `delete_schedule`, `get_schedule`, `list_schedules`.

## 2. APScheduler 라이브 관리 (`app.py`)
- 앱 시작 시: 기존 `_run_cleanup`(02:00) 잡 유지 + `list_schedules()`의 `enabled=1` 각 항목을 `scheduler.add_job(scheduled_run, CronTrigger(day_of_week=days, hour, minute, timezone="Asia/Seoul"), args=[schedule_id], id=f"sched_{id}", replace_existing=True)`로 등록.
- 기존 단일 잡 `scheduler.add_job(scheduled_run, CronTrigger(hour=9, minute=0))`은 **제거**하고, `scheduled_run` 시그니처를 `scheduled_run(schedule_id)`로 변경(인자 없는 옛 호출 제거). `SCHEDULED_KEYWORDS` env는 **폐기**(웹 스케줄로 완전 대체) — 이중 발행 방지를 위해 폴백 두지 않음.
- CRUD 시: 생성→`add_job`, 수정→`reschedule_job`+args 갱신(간단히 remove 후 add), 삭제/비활성→`remove_job`. 헬퍼 `_apply_schedule(sched)` / `_unschedule(id)`로 캡슐화.

## 3. 스케줄 실행
```python
def scheduled_run(schedule_id: int):
    sched = get_schedule(schedule_id)
    if not sched or not sched["enabled"]:
        return
    keywords = sched["keywords"]
    # 동시 중복 방지: 같은 스케줄의 이전 실행이 아직 진행 중이면 스킵
    job_id = uuid.uuid4().hex[:8]
    jobs[job_id] = {... , "schedule_id": schedule_id}
    upsert_job(job_id, "running", keywords)
    threading.Thread(target=run_pipeline,
        args=(job_id, keywords),
        kwargs={"auto_post": True,
                "post_blog": sched["post_blog"],
                "post_instagram": sched["post_instagram"]},
        daemon=True).start()
```

## 4. 채널 플래그
`run_pipeline(job_id, keywords, auto_post=False, post_blog=True, post_instagram=True)`:
- **카드뉴스 생성은 `post_instagram`일 때만** 실행(Imagen 유료 비용 절감).
- `_run_pipeline_part2(job_id, keywords, today, post_blog, post_instagram)`: `post_blog`면 poster, `post_instagram`면 instagram 실행. 둘 다 False면 Part2 생략하고 바로 done.
- 수동 `/run`(웹 버튼)은 기본값(blog+ig, auto_post=False=승인대기) 그대로 유지 — 기존 동작 불변.

## 5. 웹 API (`app.py`, 인증 필요)
| 메서드·경로 | 동작 |
|------|------|
| `GET /schedules` | 스케줄 목록 + 각 다음 실행 시각 |
| `POST /schedules` | 생성 (JSON 바디 검증: 키워드 비어있지 않음, hour/minute 범위, days 유효, 채널 ≥1) |
| `PUT /schedules/<id>` | 수정 |
| `DELETE /schedules/<id>` | 삭제 |
| `POST /schedules/<id>/toggle` | enabled 토글 |

검증 실패 시 400 + 메시지. 모든 경로는 기존 `_require_auth` 적용.

## 6. 웹 UI (`templates/index.html`)
"예약 관리" 섹션(접이식): 스케줄 카드 목록(이름·키워드·요일/시간·채널 배지·ON/OFF 토글·다음 실행)과 추가/수정 폼(키워드 입력, 요일 체크박스 7개, 시간 select, 블로그/IG 토글, 활성화). 저장 시 위 API 호출 후 목록 갱신. 기존 UI 스타일/패턴 따름.

## 7. 안전장치
- 인증: 기존 Basic/세션 재사용.
- 타임존: Asia/Seoul 고정.
- 미스파이어: APScheduler 기본(놓친 회차 스킵), `coalesce=True`, `max_instances=1`.
- 동시 중복: `max_instances=1`로 같은 스케줄 동시 실행 차단.

## 8. 테스트
- `tests/test_infra.py`(또는 신규): `schedules` CRUD(create/get/list/update/delete) 단위 테스트.
- cron 변환 헬퍼: `days/hour/minute → CronTrigger` 유효성(잘못된 입력 거부).
- 채널 게이트: `_run_pipeline_part2`가 플래그대로 poster/instagram 호출/생략(모킹), `post_instagram=False`면 카드뉴스 생략.
- API: 검증 실패(빈 키워드/범위 초과) 400 (Flask test client).

## Verification
1. `venv\Scripts\python -m pytest tests/ -q` (현재 109 passed + 신규).
2. 로컬 앱 기동 후 `/schedules` CRUD를 test client/curl로 호출 → DB 반영·APScheduler 잡 등록 확인.
3. 임박한 시각(예: 현재+2분)으로 스케줄 생성 → 실제 실행·발행(또는 채널 게이트) 확인. 또는 `scheduled_run(id)` 직접 호출로 스모크.
4. 서버 배포 후 웹 UI에서 스케줄 추가 → 다음 실행 시각 표시·동작 확인.
