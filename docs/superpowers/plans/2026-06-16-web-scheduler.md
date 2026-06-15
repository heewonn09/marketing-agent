# 웹 스케줄러 관리 기능 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 웹에서 여러 예약 스케줄(키워드·요일·시간·발행채널·활성화)을 추가/수정/삭제하고, 저장한 설정대로 승인 없이 자동 발행한다. 변경은 서버 재시작 없이 즉시 반영.

**Architecture:** `jobs.db`에 `schedules` 테이블 추가(`utils/job_store.py`), 검증·cron 변환은 순수 모듈(`utils/schedule_util.py`)로 분리해 단위 테스트. `app.py`는 APScheduler 잡을 라이브로 add/remove하고, `run_pipeline`에 채널 플래그를 흘려 선택 채널만 발행. 웹은 `/schedules` CRUD API + index.html "예약 관리" 섹션.

**Tech Stack:** Flask, APScheduler(CronTrigger), SQLite(sqlite3), pytest, 바닐라 JS.

---

## File Structure
- `utils/schedule_util.py` (생성): 검증·요일 정규화·cron kwargs (순수 함수, 외부 의존 없음).
- `utils/job_store.py` (수정): `schedules` 테이블 + CRUD.
- `app.py` (수정): 스케줄러 startup 가드, `run_pipeline`/`_run_pipeline_part2` 채널 플래그, `scheduled_run(schedule_id)`, `_apply_schedule`/`_unschedule`, `/schedules` CRUD 라우트.
- `templates/index.html` (수정): "예약 관리" UI 섹션 + JS.
- `tests/test_schedule_util.py`, `tests/test_schedules_store.py`, `tests/test_app_schedules.py` (생성).

---

## Task 1: schedule_util — 검증/요일/ cron 변환 (순수)

**Files:**
- Create: `utils/schedule_util.py`
- Test: `tests/test_schedule_util.py`

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_schedule_util.py
import pytest
from utils.schedule_util import normalize_days, cron_kwargs, validate_schedule


def test_normalize_days_from_list():
    assert normalize_days(["mon", "thu"]) == "mon,thu"

def test_normalize_days_from_csv_and_dedup_order():
    assert normalize_days("thu, mon, mon") == "mon,thu"

def test_normalize_days_rejects_invalid():
    with pytest.raises(ValueError):
        normalize_days(["funday"])

def test_cron_kwargs():
    assert cron_kwargs("mon,thu", 9, 0) == {"day_of_week": "mon,thu", "hour": 9, "minute": 0}

def test_validate_ok():
    ok, err = validate_schedule({"keywords": ["AI 마케팅"], "days": ["mon"],
                                 "hour": 9, "minute": 0, "post_blog": True, "post_instagram": False})
    assert ok and err == ""

def test_validate_empty_keywords():
    ok, err = validate_schedule({"keywords": [], "days": ["mon"], "hour": 9, "minute": 0,
                                 "post_blog": True, "post_instagram": True})
    assert not ok and "키워드" in err

def test_validate_bad_hour():
    ok, err = validate_schedule({"keywords": ["x"], "days": ["mon"], "hour": 24, "minute": 0,
                                 "post_blog": True, "post_instagram": True})
    assert not ok

def test_validate_no_channel():
    ok, err = validate_schedule({"keywords": ["x"], "days": ["mon"], "hour": 9, "minute": 0,
                                 "post_blog": False, "post_instagram": False})
    assert not ok and "채널" in err
```

- [ ] **Step 2: 실패 확인** — `pytest tests/test_schedule_util.py -q` → ModuleNotFoundError.

- [ ] **Step 3: 구현**

```python
# utils/schedule_util.py
"""스케줄 입력 검증 / 요일 정규화 / APScheduler cron kwargs (순수 함수)."""

_VALID_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def normalize_days(days) -> str:
    if isinstance(days, str):
        items = [d.strip() for d in days.split(",") if d.strip()]
    else:
        items = [str(d).strip() for d in days if str(d).strip()]
    for d in items:
        if d not in _VALID_DAYS:
            raise ValueError(f"잘못된 요일: {d}")
    # 중복 제거 + 요일 순서 정렬
    ordered = [d for d in _VALID_DAYS if d in set(items)]
    if not ordered:
        raise ValueError("요일이 비어있습니다")
    return ",".join(ordered)


def cron_kwargs(days: str, hour: int, minute: int) -> dict:
    return {"day_of_week": days, "hour": int(hour), "minute": int(minute)}


def validate_schedule(payload: dict) -> tuple[bool, str]:
    kws = payload.get("keywords") or []
    if not isinstance(kws, list) or not [k for k in kws if str(k).strip()]:
        return False, "키워드를 1개 이상 입력하세요"
    try:
        normalize_days(payload.get("days"))
    except ValueError as e:
        return False, str(e)
    hour, minute = payload.get("hour"), payload.get("minute")
    if not isinstance(hour, int) or not (0 <= hour <= 23):
        return False, "시(hour)는 0~23"
    if not isinstance(minute, int) or not (0 <= minute <= 59):
        return False, "분(minute)은 0~59"
    if not (payload.get("post_blog") or payload.get("post_instagram")):
        return False, "발행 채널을 최소 1개 선택하세요"
    return True, ""
```

- [ ] **Step 4: 통과 확인** — `pytest tests/test_schedule_util.py -q` → 8 passed.
- [ ] **Step 5: 커밋** — `git add utils/schedule_util.py tests/test_schedule_util.py && git commit -m "feat(schedule): 검증/요일/cron 순수 유틸"`

---

## Task 2: schedules 테이블 + job_store CRUD

**Files:**
- Modify: `utils/job_store.py`
- Test: `tests/test_schedules_store.py`

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_schedules_store.py
from utils import job_store


def test_schedule_crud(tmp_path):
    db = tmp_path / "jobs.db"
    job_store.init_db(db)
    sid = job_store.create_schedule(
        name="월요 발행", keywords=["AI 마케팅"], days="mon,thu", hour=9, minute=0,
        post_blog=True, post_instagram=False, enabled=True, db_path=db)
    assert isinstance(sid, int)

    s = job_store.get_schedule(sid, db_path=db)
    assert s["keywords"] == ["AI 마케팅"]
    assert s["days"] == "mon,thu" and s["hour"] == 9
    assert s["post_blog"] is True and s["post_instagram"] is False and s["enabled"] is True

    job_store.update_schedule(sid, db_path=db, hour=10, post_instagram=True, enabled=False)
    s = job_store.get_schedule(sid, db_path=db)
    assert s["hour"] == 10 and s["post_instagram"] is True and s["enabled"] is False

    assert len(job_store.list_schedules(db_path=db)) == 1
    job_store.delete_schedule(sid, db_path=db)
    assert job_store.get_schedule(sid, db_path=db) is None
    assert job_store.list_schedules(db_path=db) == []


def test_list_schedules_empty(tmp_path):
    db = tmp_path / "jobs.db"
    job_store.init_db(db)
    assert job_store.list_schedules(db_path=db) == []
```

- [ ] **Step 2: 실패 확인** — `pytest tests/test_schedules_store.py -q` → AttributeError: create_schedule 없음.

- [ ] **Step 3: 구현** — `utils/job_store.py`의 `init_db` 안 `jobs` 테이블 생성 직후 schedules 테이블 추가:

```python
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schedules (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                name           TEXT,
                keywords       TEXT NOT NULL,
                days           TEXT NOT NULL,
                hour           INTEGER NOT NULL,
                minute         INTEGER NOT NULL,
                post_blog      INTEGER NOT NULL DEFAULT 1,
                post_instagram INTEGER NOT NULL DEFAULT 1,
                enabled        INTEGER NOT NULL DEFAULT 1,
                created_at     TEXT NOT NULL,
                updated_at     TEXT NOT NULL
            )
        """)
```

그리고 파일 끝에 CRUD 추가(기존 `_DEFAULT_DB` 패턴 동일):

```python
def _row_to_schedule(row) -> dict:
    return {
        "id": row[0], "name": row[1], "keywords": json.loads(row[2] or "[]"),
        "days": row[3], "hour": row[4], "minute": row[5],
        "post_blog": bool(row[6]), "post_instagram": bool(row[7]),
        "enabled": bool(row[8]), "created_at": row[9], "updated_at": row[10],
    }


_SCHED_COLS = "id,name,keywords,days,hour,minute,post_blog,post_instagram,enabled,created_at,updated_at"


def create_schedule(name, keywords, days, hour, minute,
                    post_blog=True, post_instagram=True, enabled=True, db_path=None) -> int:
    path = db_path or _DEFAULT_DB
    now = datetime.now().isoformat()
    with sqlite3.connect(path) as conn:
        cur = conn.execute(
            """INSERT INTO schedules
               (name, keywords, days, hour, minute, post_blog, post_instagram, enabled, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (name, json.dumps(keywords, ensure_ascii=False), days, int(hour), int(minute),
             int(bool(post_blog)), int(bool(post_instagram)), int(bool(enabled)), now, now),
        )
        return cur.lastrowid


def get_schedule(schedule_id, db_path=None) -> dict | None:
    path = db_path or _DEFAULT_DB
    with sqlite3.connect(path) as conn:
        row = conn.execute(f"SELECT {_SCHED_COLS} FROM schedules WHERE id=?", (schedule_id,)).fetchone()
    return _row_to_schedule(row) if row else None


def list_schedules(db_path=None) -> list[dict]:
    path = db_path or _DEFAULT_DB
    with sqlite3.connect(path) as conn:
        rows = conn.execute(f"SELECT {_SCHED_COLS} FROM schedules ORDER BY id").fetchall()
    return [_row_to_schedule(r) for r in rows]


def update_schedule(schedule_id, db_path=None, **fields) -> None:
    allowed = {"name", "keywords", "days", "hour", "minute", "post_blog", "post_instagram", "enabled"}
    sets, vals = [], []
    for k, v in fields.items():
        if k not in allowed:
            continue
        if k == "keywords":
            v = json.dumps(v, ensure_ascii=False)
        elif k in ("post_blog", "post_instagram", "enabled"):
            v = int(bool(v))
        sets.append(f"{k}=?")
        vals.append(v)
    if not sets:
        return
    sets.append("updated_at=?")
    vals.append(datetime.now().isoformat())
    vals.append(schedule_id)
    path = db_path or _DEFAULT_DB
    with sqlite3.connect(path) as conn:
        conn.execute(f"UPDATE schedules SET {', '.join(sets)} WHERE id=?", vals)


def delete_schedule(schedule_id, db_path=None) -> None:
    path = db_path or _DEFAULT_DB
    with sqlite3.connect(path) as conn:
        conn.execute("DELETE FROM schedules WHERE id=?", (schedule_id,))
```

(`json`, `sqlite3`, `datetime`는 job_store가 이미 import 함.)

- [ ] **Step 4: 통과 확인** — `pytest tests/test_schedules_store.py -q` → 2 passed.
- [ ] **Step 5: 커밋** — `git add utils/job_store.py tests/test_schedules_store.py && git commit -m "feat(job_store): schedules 테이블 + CRUD"`

---

## Task 3: app.py — 스케줄러 startup 가드 (테스트 가능화)

**Files:**
- Modify: `app.py` (스케줄러 블록, 파일 하단)

- [ ] **Step 1: 구현** — `app.py` 하단 `scheduler.start()`를 env 가드로 감싸 테스트에서 import 가능하게:

```python
scheduler = BackgroundScheduler(timezone="Asia/Seoul")
scheduler.add_job(_run_cleanup, CronTrigger(hour=2, minute=0, timezone="Asia/Seoul"))
# (기존 매일 09:00 scheduled_run 잡은 제거 — 웹 스케줄로 대체)

if os.environ.get("DISABLE_SCHEDULER") != "1":
    for _s in list_schedules():            # Task 4에서 정의된 _apply_schedule 사용
        if _s["enabled"]:
            _apply_schedule(_s)
    scheduler.start()
```

- [ ] **Step 2: 확인** — `DISABLE_SCHEDULER=1 python -c "import app"` 가 스케줄러 없이 import 되는지(에러 없음). Windows: `$env:DISABLE_SCHEDULER=1; .\venv\Scripts\python.exe -c "import app; print('ok')"`
- [ ] **Step 3: 커밋** — `git add app.py && git commit -m "chore(app): 스케줄러 startup 가드(DISABLE_SCHEDULER)"`

> 주: import 순서상 `_apply_schedule`/`scheduled_run`은 Task 4에서 추가되어 같은 파일 위쪽에 정의된다. 본 Task와 Task 4는 한 커밋으로 합쳐도 무방.

---

## Task 4: app.py — 채널 플래그 + scheduled_run + 스케줄 적용 헬퍼

**Files:**
- Modify: `app.py` (`run_pipeline`, `_run_pipeline_part2`, `scheduled_run`, import)
- Test: `tests/test_app_schedules.py`

- [ ] **Step 1: 실패 테스트 작성 (채널 게이트)**

```python
# tests/test_app_schedules.py
import os, queue, time
os.environ["DISABLE_SCHEDULER"] = "1"   # import 시 스케줄러 미기동
import app as a


def _job(jid, kws):
    a.jobs[jid] = {"status": "running", "queue": queue.Queue(), "date": None,
                   "keywords": kws, "last_step": None, "started_at": time.time(),
                   "naver_post_url": None, "instagram_media_id": None, "instagram_permalink": None}


def test_part2_blog_only(monkeypatch):
    ran = []
    monkeypatch.setattr(a, "_run_cmd",
        lambda jid, name, script, args, fatal=True: ran.append(script) or True)
    monkeypatch.setattr(a, "notify_done", lambda *x, **k: None)
    monkeypatch.setattr(a, "upsert_job", lambda *x, **k: None)
    _job("j1", ["k"])
    a._run_pipeline_part2("j1", ["k"], "2026-06-16", post_blog=True, post_instagram=False)
    assert any("poster" in s for s in ran)
    assert not any("instagram" in s for s in ran)


def test_part2_ig_only(monkeypatch):
    ran = []
    monkeypatch.setattr(a, "_run_cmd",
        lambda jid, name, script, args, fatal=True: ran.append(script) or True)
    monkeypatch.setattr(a, "notify_done", lambda *x, **k: None)
    monkeypatch.setattr(a, "upsert_job", lambda *x, **k: None)
    _job("j2", ["k"])
    a._run_pipeline_part2("j2", ["k"], "2026-06-16", post_blog=False, post_instagram=True)
    assert any("instagram" in s for s in ran)
    assert not any("poster" in s for s in ran)
```

- [ ] **Step 2: 실패 확인** — `DISABLE_SCHEDULER=1 pytest tests/test_app_schedules.py -q` → `_run_pipeline_part2` TypeError(인자 없음).

- [ ] **Step 3: 구현** — `_run_pipeline_part2` 시그니처/게이트 변경:

```python
def _run_pipeline_part2(job_id, keywords, today, post_blog=True, post_instagram=True):
    if post_blog:
        for keyword in keywords:
            ok = _run_cmd(job_id, f"포스팅 [{keyword}]", "agents/poster/main.py",
                          ["--keyword", keyword, "--date", today], fatal=False)
            if not ok:
                jobs[job_id]["queue"].put(
                    "LOG:[poster] 네이버 봇 감지 또는 로그인 실패 — 로컬에서 별도 실행 필요. 다음 스텝 계속 진행.")
    if post_instagram:
        for keyword in keywords:
            safe_kw = _re.sub(r'[<>:"/\\|?*\n\r\t]', "_", keyword)
            cardnews_ready = all(
                (ROOT / "output" / f"cardnews_{safe_kw}_{today}_{i}.png").exists() for i in range(1, 5))
            ig_args = ["--keyword", keyword, "--date", today]
            if cardnews_ready:
                ig_args.append("--carousel")
                jobs[job_id]["queue"].put("LOG:[instagram] 카드뉴스 4장 감지 → 캐러셀 업로드")
            if not _run_cmd(job_id, f"인스타그램 [{keyword}]", "agents/instagram/main.py", ig_args):
                return
    jobs[job_id]["status"] = "done"
    jobs[job_id]["date"] = today
    duration = int(time.time() - jobs[job_id].get("started_at", time.time()))
    jobs[job_id]["duration_seconds"] = duration
    upsert_job(job_id, "done", keywords, today,
               naver_post_url=jobs[job_id].get("naver_post_url"),
               instagram_media_id=jobs[job_id].get("instagram_media_id"),
               instagram_permalink=jobs[job_id].get("instagram_permalink"),
               duration_seconds=duration)
    jobs[job_id]["queue"].put(f"DONE:{today}")
    base_url = os.environ.get("CARDNEWS_BASE_URL", "")
    threading.Thread(target=notify_done, args=(keywords, today, base_url), daemon=True).start()
```

`run_pipeline`에 플래그 추가 + 카드뉴스 게이트:

```python
def run_pipeline(job_id, keywords, auto_post=False, post_blog=True, post_instagram=True):
    import concurrent.futures
    today = date.today().isoformat()
    # ... (기존 수집/분석/작성 + 부분실패 로직 그대로) ...
    for name, script, step_args in [
        ("리포트 [통합]", "agents/reporter/main.py", ["--date", today]),
        ("모니터 [통합]", "agents/monitor/main.py",  ["--keywords"] + keywords + ["--once"]),
    ]:
        if not _run_cmd(job_id, name, script, step_args):
            return
    if post_instagram:   # 카드뉴스(Imagen 유료)는 IG 발행 시에만 생성
        for keyword in keywords:
            ok = _run_cmd(job_id, f"카드뉴스 [{keyword}]", "agents/cardnews/main.py",
                          ["--keyword", keyword, "--date", today], fatal=False)
            if not ok:
                jobs[job_id]["queue"].put("LOG:[cardnews] 카드뉴스 생성 실패 — 다음 스텝 계속 진행.")
    if auto_post:
        _run_pipeline_part2(job_id, keywords, today, post_blog, post_instagram)
    else:
        jobs[job_id]["status"] = "pending_approval"
        jobs[job_id]["date"] = today
        upsert_job(job_id, "pending_approval", keywords, today)
        jobs[job_id]["queue"].put(f"PENDING:{today}")
        base_url = os.environ.get("CARDNEWS_BASE_URL", "")
        threading.Thread(target=notify_approval_pending, args=(keywords, today, base_url), daemon=True).start()
```

`scheduled_run` 교체 + 적용 헬퍼 추가(스케줄러 정의보다 위, run_pipeline 근처):

```python
def scheduled_run(schedule_id: int):
    sched = get_schedule(schedule_id)
    if not sched or not sched["enabled"]:
        print(f"[scheduler] 스케줄 {schedule_id} 없음/비활성 — 생략")
        return
    keywords = sched["keywords"]
    if not keywords:
        return
    print(f"[scheduler] 자동 실행: id={schedule_id} {keywords}")
    job_id = uuid.uuid4().hex[:8]
    jobs[job_id] = {"status": "running", "queue": queue.Queue(), "date": None,
                    "keywords": keywords, "last_step": None, "started_at": time.time(),
                    "schedule_id": schedule_id,
                    "naver_post_url": None, "instagram_media_id": None, "instagram_permalink": None}
    upsert_job(job_id, "running", keywords)
    threading.Thread(target=run_pipeline, args=(job_id, keywords),
                     kwargs={"auto_post": True, "post_blog": sched["post_blog"],
                             "post_instagram": sched["post_instagram"]}, daemon=True).start()


def _apply_schedule(sched: dict):
    from utils.schedule_util import cron_kwargs
    scheduler.add_job(
        scheduled_run, CronTrigger(timezone="Asia/Seoul", **cron_kwargs(sched["days"], sched["hour"], sched["minute"])),
        args=[sched["id"]], id=f"sched_{sched['id']}",
        replace_existing=True, coalesce=True, max_instances=1)


def _unschedule(schedule_id: int):
    try:
        scheduler.remove_job(f"sched_{schedule_id}")
    except Exception:
        pass
```

import 추가(상단 utils 블록):

```python
from utils.job_store import (init_db, upsert_job, get_job, list_jobs,
                             create_schedule, get_schedule, list_schedules,
                             update_schedule, delete_schedule)
```
(notify_approval_pending는 이미 import되어 있음)

- [ ] **Step 4: 통과 확인** — `DISABLE_SCHEDULER=1 pytest tests/test_app_schedules.py -q` → 2 passed.
- [ ] **Step 5: 커밋** — `git add app.py tests/test_app_schedules.py && git commit -m "feat(app): 채널 플래그 + scheduled_run(schedule_id) + 적용 헬퍼"`

---

## Task 5: app.py — /schedules CRUD 라우트

**Files:**
- Modify: `app.py` (라우트)
- Test: `tests/test_app_schedules.py` (추가)

- [ ] **Step 1: 실패 테스트 추가**

```python
def _client(monkeypatch, tmp_path):
    # 인증 비활성(ADMIN 미설정) + 스케줄러 미기동 상태의 test client
    monkeypatch.setattr(a, "ADMIN_USER", "")
    a.app.config["TESTING"] = True
    return a.app.test_client()


def test_create_and_list_schedule(monkeypatch, tmp_path):
    monkeypatch.setattr(a, "_apply_schedule", lambda s: None)
    monkeypatch.setattr(a, "_unschedule", lambda i: None)
    c = _client(monkeypatch, tmp_path)
    r = c.post("/schedules", json={"name": "t", "keywords": ["AI 마케팅"], "days": ["mon"],
                                   "hour": 9, "minute": 0, "post_blog": True, "post_instagram": False})
    assert r.status_code == 200
    sid = r.get_json()["id"]
    lst = c.get("/schedules").get_json()
    assert any(s["id"] == sid for s in lst)


def test_create_rejects_invalid(monkeypatch, tmp_path):
    monkeypatch.setattr(a, "_apply_schedule", lambda s: None)
    c = _client(monkeypatch, tmp_path)
    r = c.post("/schedules", json={"keywords": [], "days": ["mon"], "hour": 9, "minute": 0,
                                   "post_blog": False, "post_instagram": False})
    assert r.status_code == 400
```

- [ ] **Step 2: 실패 확인** — `DISABLE_SCHEDULER=1 pytest tests/test_app_schedules.py -q` → 404 (라우트 없음).

- [ ] **Step 3: 구현** — `app.py`에 라우트 추가(`# ── 라우트` 섹션 내):

```python
from utils.schedule_util import validate_schedule, normalize_days

@app.route("/schedules", methods=["GET"])
def schedules_list():
    out = []
    for s in list_schedules():
        job = scheduler.get_job(f"sched_{s['id']}")
        s = dict(s)
        s["next_run"] = job.next_run_time.isoformat() if (job and job.next_run_time) else None
        out.append(s)
    return jsonify(out)


@app.route("/schedules", methods=["POST"])
def schedules_create():
    data = request.get_json(silent=True) or {}
    ok, err = validate_schedule(data)
    if not ok:
        return jsonify({"error": err}), 400
    sid = create_schedule(
        name=data.get("name", ""), keywords=[k.strip() for k in data["keywords"] if str(k).strip()],
        days=normalize_days(data["days"]), hour=data["hour"], minute=data["minute"],
        post_blog=bool(data["post_blog"]), post_instagram=bool(data["post_instagram"]),
        enabled=bool(data.get("enabled", True)))
    sched = get_schedule(sid)
    if sched["enabled"]:
        _apply_schedule(sched)
    return jsonify({"id": sid})


@app.route("/schedules/<int:sid>", methods=["PUT"])
def schedules_update(sid):
    if not get_schedule(sid):
        return jsonify({"error": "없는 스케줄"}), 404
    data = request.get_json(silent=True) or {}
    ok, err = validate_schedule(data)
    if not ok:
        return jsonify({"error": err}), 400
    update_schedule(sid, name=data.get("name", ""),
                    keywords=[k.strip() for k in data["keywords"] if str(k).strip()],
                    days=normalize_days(data["days"]), hour=data["hour"], minute=data["minute"],
                    post_blog=bool(data["post_blog"]), post_instagram=bool(data["post_instagram"]),
                    enabled=bool(data.get("enabled", True)))
    sched = get_schedule(sid)
    _unschedule(sid)
    if sched["enabled"]:
        _apply_schedule(sched)
    return jsonify({"ok": True})


@app.route("/schedules/<int:sid>", methods=["DELETE"])
def schedules_delete(sid):
    _unschedule(sid)
    delete_schedule(sid)
    return jsonify({"ok": True})


@app.route("/schedules/<int:sid>/toggle", methods=["POST"])
def schedules_toggle(sid):
    s = get_schedule(sid)
    if not s:
        return jsonify({"error": "없는 스케줄"}), 404
    new_enabled = not s["enabled"]
    update_schedule(sid, enabled=new_enabled)
    _unschedule(sid)
    if new_enabled:
        _apply_schedule(get_schedule(sid))
    return jsonify({"enabled": new_enabled})
```

`/schedules*`는 인증 면제 목록에 넣지 않으므로 기존 `_require_auth` 적용됨(관리자 전용).

- [ ] **Step 4: 통과 확인** — `DISABLE_SCHEDULER=1 pytest tests/test_app_schedules.py -q` → 4 passed.
- [ ] **Step 5: 전체** — `pytest tests/ -q` (스케줄러 import 테스트는 DISABLE_SCHEDULER 설정됨). 커밋 `git add app.py tests/test_app_schedules.py && git commit -m "feat(app): /schedules CRUD 라우트"`

---

## Task 6: index.html — "예약 관리" UI

**Files:**
- Modify: `templates/index.html`

- [ ] **Step 1: 구현** — 기존 스타일을 따라 접이식 "예약 관리" 섹션 추가. 목록(카드: 이름·키워드·요일/시간·채널 배지·다음 실행·ON/OFF·수정/삭제)과 폼(키워드 input, 요일 체크박스 7개, 시간 `<select>` 0–23 / 분 select, 블로그·IG 토글, 활성화 체크박스). JS:
  - `loadSchedules()` → `GET /schedules` → 카드 렌더
  - `saveSchedule()` → 신규는 `POST /schedules`, 수정은 `PUT /schedules/<id>` (요일은 체크된 값 배열)
  - `toggleSchedule(id)` → `POST /schedules/<id>/toggle`
  - `deleteSchedule(id)` → `DELETE /schedules/<id>` (confirm)
  - 페이지 로드시 `loadSchedules()` 호출.

(요일 매핑: 월=mon … 일=sun. 입력 검증은 서버가 하므로 프론트는 최소 검증.)

- [ ] **Step 2: 수동 확인** — 로컬 기동(`.\venv\Scripts\python.exe app.py`) 후 브라우저에서 스케줄 추가/토글/삭제 → 목록·다음 실행 시각 갱신 확인.
- [ ] **Step 3: 커밋** — `git add templates/index.html && git commit -m "feat(ui): 예약 관리 섹션"`

---

## Task 7: 통합 검증 + 배포

- [ ] **Step 1: 전체 테스트** — `.\venv\Scripts\python.exe -m pytest tests/ -q` → 전부 통과.
- [ ] **Step 2: 임박 스케줄 스모크** — 현재+2분, 요일=오늘로 스케줄 생성 후 대기 → 실행 로그/발행(또는 채널 게이트) 확인. 또는 `DISABLE_SCHEDULER=1`에서 `app.scheduled_run(sid)` 직접 호출 스모크.
- [ ] **Step 3: 커밋·푸시·배포** — `git push origin main` → 서버 `git pull` + `sudo systemctl restart marketing-agent` → 웹 UI에서 스케줄 추가·다음 실행 시각 확인. CI green 확인.

---

## 자체 검토 결과 (spec 대비)
- 데이터 모델/CRUD: Task 2 ✓ | 검증·cron: Task 1 ✓ | 채널 플래그·카드뉴스 게이트: Task 4 ✓ | 라이브 add/remove: Task 4(_apply/_unschedule)+Task 5(라우트) ✓ | scheduled_run(id)·옛 잡 제거: Task 3·4 ✓ | API: Task 5 ✓ | UI: Task 6 ✓ | 인증/타임존/coalesce/max_instances: Task 4·5 ✓ | 테스트: Task 1·2·4·5 ✓
- 함수명 일관성: `_apply_schedule`/`_unschedule`/`scheduled_run`/`create_schedule` 등 전 Task 동일 사용.
