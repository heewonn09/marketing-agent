# Immediate Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 코드 검토 후 실제로 미구현된 3가지를 완료한다 — Instagram 토큰 주간 갱신 스케줄러, API 키 인증(Basic Auth 제거), 결과 공유 링크.

**Architecture:**
- Task 1: `app.py` APScheduler에 주 1회 IG 토큰 갱신 잡 추가.
- Task 2: `app.py` `_require_auth`에서 `X-API-Key` 헤더 지원 추가, `WWW-Authenticate: Basic` 응답 제거.
- Task 3: `app.py`에 `/share/<job_id>` 엔드포인트 추가(인증 면제, 읽기 전용).

**Tech Stack:** Python 3.14, Flask, APScheduler, requests, pytest

**사전 확인 — 이미 구현됨(건드리지 않음):**
- Gemini 재시도: `utils/gemini_retry.py` + `@gemini_retry` (analyzer/writer/cardnews/instagram 전부) ✅
- Sales SALES_ENABLED 가드: `agents/sales/main.py:184` ✅
- Instagram `ensure_fresh_token()`: 매 호출마다 갱신 ✅
- Flask 세션 로그인 + LoginRateLimiter ✅
- 카드뉴스 미리보기 `loadCardnews()` + `#cardnews-gallery` ✅

---

## File Structure

- Modify: `app.py` — 토큰 스케줄러 잡, API 키 인증, `/share` 엔드포인트
- Modify: `.env` — `API_KEY=` 항목 추가
- Modify: `tests/test_security.py` — API 키 테스트 추가

---

## Task 1: Instagram 토큰 주간 갱신 스케줄러

**배경:** `ensure_fresh_token()`은 Instagram 포스팅 시에만 실행된다.
Instagram이 60일 이상 호출되지 않으면 토큰이 만료되어 다음 발행이 조용히 실패한다.
매주 일요일 03:00에 토큰을 갱신하면 이 위험을 제거할 수 있다.

**Files:**
- Modify: `app.py`

- [ ] **Step 1: `_refresh_ig_token_job()` 함수 추가**

`app.py`에서 `_run_cleanup()` 함수 바로 뒤에 추가:

```python
def _refresh_ig_token_job() -> None:
    """Instagram 액세스 토큰 주간 갱신 (만료 방지).

    INSTAGRAM_ACCESS_TOKEN 미설정 시 조용히 건너뜀.
    갱신 실패 시 alert_sender로 알림.
    """
    access_token = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "").strip()
    if not access_token:
        print("[ig-token] INSTAGRAM_ACCESS_TOKEN 미설정 — 건너뜀")
        return
    try:
        import requests as _req
        res = _req.get(
            "https://graph.instagram.com/refresh_access_token",
            params={"grant_type": "ig_refresh_token", "access_token": access_token},
            timeout=15,
        )
        if not res.ok:
            msg = f"토큰 갱신 실패 {res.status_code}: {res.text[:80]}"
            print(f"[ig-token] {msg}")
            try:
                from utils.alert_sender import send_alert
                send_alert("[marketing-agent] Instagram 토큰 갱신 실패", msg)
            except Exception:
                pass
            return
        data = res.json()
        new_token = data.get("access_token", "")
        days = data.get("expires_in", 0) // 86400
        print(f"[ig-token] 갱신 완료 — 만료까지 {days}일")
        if new_token and new_token != access_token:
            env_path = ROOT / ".env"
            text = env_path.read_text(encoding="utf-8")
            import re as _re2
            text = _re2.sub(
                r"^INSTAGRAM_ACCESS_TOKEN=.*$",
                f"INSTAGRAM_ACCESS_TOKEN={new_token}",
                text,
                flags=_re2.MULTILINE,
            )
            env_path.write_text(text, encoding="utf-8")
            os.environ["INSTAGRAM_ACCESS_TOKEN"] = new_token
            print("[ig-token] .env 토큰 업데이트 완료")
    except Exception as e:
        msg = f"토큰 갱신 예외: {e}"
        print(f"[ig-token] {msg}")
        try:
            from utils.alert_sender import send_alert
            send_alert("[marketing-agent] Instagram 토큰 갱신 예외", msg)
        except Exception:
            pass
```

- [ ] **Step 2: 스케줄러에 주 1회 잡 등록**

`app.py`에서 `scheduler.add_job(_run_cleanup, ...)` 줄 바로 아래에 추가:

```python
scheduler.add_job(
    _refresh_ig_token_job,
    CronTrigger(day_of_week="sun", hour=3, minute=0, timezone="Asia/Seoul"),
    id="ig_token_refresh",
    replace_existing=True,
)
```

- [ ] **Step 3: 앱 시작 시 즉시 1회 실행 (토큰 상태 확인)**

`DISABLE_SCHEDULER` 가드 블록 안(`scheduler.start()` 바로 위)에 추가:

```python
if os.environ.get("DISABLE_SCHEDULER") != "1":
    for _s in list_schedules():
        if _s["enabled"]:
            _apply_schedule(_s)
    # 서버 시작 시 IG 토큰 갱신 1회 선제 실행
    threading.Thread(target=_refresh_ig_token_job, daemon=True).start()
    scheduler.start()
```

> `threading.Thread`는 이미 `import threading`이 상단에 있음.

- [ ] **Step 4: 동작 확인**

```powershell
cd "C:\Users\이희원\marketing-agent"
.\venv\Scripts\python.exe -c "
import os
os.environ['DISABLE_SCHEDULER'] = '1'
# 토큰 미설정 시 건너뜀 확인
from app import _refresh_ig_token_job
os.environ.pop('INSTAGRAM_ACCESS_TOKEN', None)
_refresh_ig_token_job()
print('건너뜀 동작 확인됨')
"
```

Expected: `[ig-token] INSTAGRAM_ACCESS_TOKEN 미설정 — 건너뜀` + `건너뜀 동작 확인됨`

- [ ] **Step 5: 커밋**

```bash
git add app.py
git commit -m "feat(scheduler): Instagram 토큰 주간 자동 갱신 (매주 일요일 03:00)"
```

---

## Task 2: API 키 인증 (Basic Auth 제거)

**배경:** 현재 `/run` 등 API 호출 시 Basic Auth 자격증명(아이디:비밀번호)을 매 요청에 전송한다.
`X-API-Key` 헤더 방식으로 교체하면 별도 API 키로 프로그래밍 접근을 격리할 수 있고,
브라우저에서 Basic Auth 팝업이 뜨는 문제도 제거된다.

**Files:**
- Modify: `app.py`
- Modify: `.env`
- Modify: `tests/test_security.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_security.py` 끝에 추가:

```python
# ── API 키 인증 ──────────────────────────────────────────────────────────────
import os as _os2


def _app_client(monkeypatch, api_key: str = "test-key-abc123"):
    monkeypatch.setenv("ADMIN_USER", "testuser")
    monkeypatch.setenv("ADMIN_PASSWORD", "testpass")
    monkeypatch.setenv("API_KEY", api_key)
    _os2.environ["DISABLE_SCHEDULER"] = "1"
    import importlib, app as _app_mod
    importlib.reload(_app_mod)
    _app_mod.app.config["TESTING"] = True
    return _app_mod.app.test_client()


def test_api_key_header_grants_access(monkeypatch):
    c = _app_client(monkeypatch)
    r = c.get("/stats", headers={"X-API-Key": "test-key-abc123"})
    assert r.status_code == 200


def test_wrong_api_key_denied(monkeypatch):
    c = _app_client(monkeypatch)
    r = c.get("/stats", headers={"X-API-Key": "wrong-key"})
    assert r.status_code == 401


def test_no_api_key_redirects_browser(monkeypatch):
    c = _app_client(monkeypatch)
    r = c.get("/stats", headers={"Accept": "text/html"})
    assert r.status_code == 302


def test_basic_auth_no_longer_accepted(monkeypatch):
    import base64
    c = _app_client(monkeypatch)
    cred = base64.b64encode(b"testuser:testpass").decode()
    r = c.get("/stats", headers={"Authorization": f"Basic {cred}"})
    # Basic Auth는 더 이상 API 접근 허용하지 않음 — 로그인 페이지로 리디렉트되거나 401
    assert r.status_code in (302, 401)
```

- [ ] **Step 2: 실패 확인**

```powershell
$env:DISABLE_SCHEDULER = "1"
.\venv\Scripts\python.exe -m pytest tests/test_security.py -k "api_key" -v
```

Expected: `FAILED` (`test_api_key_header_grants_access` — 401 또는 404)

- [ ] **Step 3: `app.py` 수정 — `_require_auth` 함수 교체**

`app.py`에서 `ADMIN_USER`, `ADMIN_PASSWORD`, `ADMIN_PASSWORD_HASH` 선언 직후에 추가:

```python
API_KEY = os.environ.get("API_KEY", "").strip()
```

그리고 `_require_auth` 함수 전체를 아래로 교체:

OLD (`_require_auth` 전체):
```python
@app.before_request
def _require_auth():
    if not _auth_enabled():
        return
    if request.path in _AUTH_EXEMPT_PATHS:
        return
    if any(request.path.startswith(p) for p in _AUTH_EXEMPT_PREFIXES):
        return
    if session.get("authenticated"):
        return
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Basic "):
        if _rate_limiter.is_locked(request.remote_addr or "?"):
            return Response("로그인 시도가 너무 많습니다. 잠시 후 다시 시도하세요.", 429)
        try:
            user, pwd = base64.b64decode(auth[6:]).decode().split(":", 1)
            if _check_credentials(user, pwd):
                _rate_limiter.register_success(request.remote_addr or "?")
                return
            _rate_limiter.register_failure(request.remote_addr or "?")
        except Exception:
            pass
    if "text/html" in request.headers.get("Accept", ""):
        return redirect(url_for("login", next=request.path))
    return Response("인증이 필요합니다", 401,
                    {"WWW-Authenticate": 'Basic realm="Marketing Agent"'})
```

NEW:
```python
@app.before_request
def _require_auth():
    if not _auth_enabled():
        return
    if request.path in _AUTH_EXEMPT_PATHS:
        return
    if any(request.path.startswith(p) for p in _AUTH_EXEMPT_PREFIXES):
        return
    if session.get("authenticated"):
        return
    # X-API-Key 헤더 — 프로그래밍 접근용 (Basic Auth 대체)
    req_api_key = request.headers.get("X-API-Key", "").strip()
    if req_api_key and API_KEY and hmac.compare_digest(req_api_key.encode(), API_KEY.encode()):
        return
    # 브라우저: 로그인 페이지로 리디렉트
    if "text/html" in request.headers.get("Accept", ""):
        return redirect(url_for("login", next=request.path))
    # API 클라이언트: 401 (WWW-Authenticate 헤더 없이 — Basic Auth 팝업 방지)
    return Response("인증이 필요합니다. X-API-Key 헤더를 사용하세요.", 401)
```

> `hmac`은 `app.py` 상단에 이미 `import base64`와 함께 있지 않으므로 상단 import 블록에 추가:
> ```python
> import hmac
> ```
> (이미 있으면 건너뜀)

- [ ] **Step 4: `.env`에 `API_KEY` 추가**

`.env` 파일에서 `ADMIN_PASSWORD` 줄 바로 아래에 추가:

```
API_KEY=마케팅에이전트api키여기입력
```

> 실제 값은 충분히 길고 무작위여야 함. 예: `python3 -c "import secrets; print(secrets.token_hex(32))"` 으로 생성.

GCP VM `.env`에도 동일하게 추가해야 함 (Task 4에서 배포 시 처리).

- [ ] **Step 5: 테스트 통과 확인**

```powershell
$env:DISABLE_SCHEDULER = "1"
.\venv\Scripts\python.exe -m pytest tests/test_security.py -k "api_key" -v
```

Expected: `4 passed`

- [ ] **Step 6: 전체 테스트 통과 확인**

```powershell
$env:DISABLE_SCHEDULER = "1"
.\venv\Scripts\python.exe -m pytest tests/ -q
```

Expected: 전부 passed (기존 테스트 회귀 없음)

- [ ] **Step 7: 커밋**

```bash
git add app.py .env tests/test_security.py
git commit -m "feat(auth): X-API-Key 헤더 인증 추가, Basic Auth 제거"
```

---

## Task 3: 결과 공유 링크 `/share/<job_id>`

**배경:** 현재 결과를 외부 고객사에 보여주려면 웹 UI 계정을 공유해야 한다.
인증 없이 접근 가능한 읽기 전용 공유 링크를 추가하면 고객 데모가 가능해진다.

**Files:**
- Modify: `app.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_security.py` 끝에 추가:

```python
# ── 공유 링크 ─────────────────────────────────────────────────────────────────
def test_share_link_no_auth_required(monkeypatch, tmp_path):
    """공유 링크는 인증 없이 접근 가능해야 한다."""
    import json
    _os2.environ["DISABLE_SCHEDULER"] = "1"
    monkeypatch.setenv("ADMIN_USER", "testuser")
    monkeypatch.setenv("ADMIN_PASSWORD", "testpass")
    monkeypatch.setenv("API_KEY", "test-key")
    import importlib, app as _app_mod
    importlib.reload(_app_mod)

    # 테스트용 결과 파일 생성
    out_dir = tmp_path / "output"
    out_dir.mkdir()
    content = {"naver_blog": {"title": "테스트"}, "instagram": {}, "ad_copy": {}}
    (out_dir / "content_테스트키워드_2026-06-17.json").write_text(
        json.dumps(content, ensure_ascii=False), encoding="utf-8"
    )
    monkeypatch.setattr(_app_mod, "ROOT", tmp_path)

    _app_mod.app.config["TESTING"] = True
    with _app_mod.app.test_client() as c:
        # job_id를 DB에 직접 삽입
        _app_mod.upsert_job("sharetest1", "done", ["테스트키워드"], "2026-06-17")
        r = c.get("/share/sharetest1")  # 인증 헤더 없음
    assert r.status_code == 200
    data = json.loads(r.data)
    assert "date" in data
    assert "keywords" in data


def test_share_link_unknown_job_returns_404(monkeypatch):
    _os2.environ["DISABLE_SCHEDULER"] = "1"
    monkeypatch.setenv("ADMIN_USER", "testuser")
    monkeypatch.setenv("ADMIN_PASSWORD", "testpass")
    monkeypatch.setenv("API_KEY", "test-key")
    import importlib, app as _app_mod
    importlib.reload(_app_mod)
    _app_mod.app.config["TESTING"] = True
    with _app_mod.app.test_client() as c:
        r = c.get("/share/nonexistentjobid")
    assert r.status_code == 404
```

- [ ] **Step 2: 실패 확인**

```powershell
$env:DISABLE_SCHEDULER = "1"
.\venv\Scripts\python.exe -m pytest tests/test_security.py -k "share_link" -v
```

Expected: `FAILED` (404 — 라우트 없음)

- [ ] **Step 3: `/share/<job_id>` 엔드포인트 구현**

`app.py`에서 `/download/<report_date>` 라우트 바로 뒤에 추가:

```python
@app.route("/share/<job_id>")
def share(job_id: str):
    """인증 없이 접근 가능한 읽기 전용 공유 링크.

    job_id에 해당하는 잡 정보 + 생성된 콘텐츠 요약을 반환.
    콘텐츠 파일이 없으면 메타 정보만 반환.
    """
    job = get_job(job_id)
    if not job:
        return jsonify({"error": "공유 링크를 찾을 수 없습니다"}), 404

    result = {
        "job_id": job_id,
        "status": job.get("status"),
        "date": job.get("date"),
        "keywords": job.get("keywords", []),
        "contents": [],
    }

    for keyword in job.get("keywords", []):
        safe_kw = _re.sub(r'[<>:"/\\|?*\n\r\t]', "_", keyword)
        report_date = job.get("date") or ""
        content_path = ROOT / "output" / f"content_{safe_kw}_{report_date}.json"
        if content_path.exists():
            with open(content_path, encoding="utf-8") as f:
                content = _json.load(f)
            result["contents"].append({
                "keyword": keyword,
                "naver_blog_title": content.get("naver_blog", {}).get("title", ""),
                "instagram_caption": content.get("instagram", {}).get("caption", "")[:100],
                "ad_headline": content.get("ad_copy", {}).get("headline", ""),
                "cardnews": [
                    f"/cardnews/cardnews_{safe_kw}_{report_date}_{i}.png"
                    for i in range(1, 5)
                    if (ROOT / "output" / f"cardnews_{safe_kw}_{report_date}_{i}.png").exists()
                ],
            })

    return jsonify(result)
```

그리고 `_AUTH_EXEMPT_PREFIXES`에 `/share/` 추가:

OLD:
```python
_AUTH_EXEMPT_PREFIXES = ("/stream/", "/cardnews/")
```

NEW:
```python
_AUTH_EXEMPT_PREFIXES = ("/stream/", "/cardnews/", "/share/")
```

- [ ] **Step 4: 테스트 통과 확인**

```powershell
$env:DISABLE_SCHEDULER = "1"
.\venv\Scripts\python.exe -m pytest tests/test_security.py -k "share_link" -v
```

Expected: `2 passed`

- [ ] **Step 5: 전체 테스트 통과 확인**

```powershell
$env:DISABLE_SCHEDULER = "1"
.\venv\Scripts\python.exe -m pytest tests/ -q
```

Expected: 전부 passed

- [ ] **Step 6: 커밋**

```bash
git add app.py tests/test_security.py
git commit -m "feat(api): /share/<job_id> 읽기 전용 공유 링크 (인증 면제)"
```

---

## Task 4: .env API_KEY 생성 + 배포

**Files:** `.env`, GCP VM `.env`

- [ ] **Step 1: API_KEY 생성**

```powershell
cd "C:\Users\이희원\marketing-agent"
.\venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
```

출력된 값을 `.env`의 `API_KEY=` 줄에 입력.

- [ ] **Step 2: 로컬 동작 확인**

```powershell
.\venv\Scripts\python.exe app.py
```

별도 터미널에서:
```powershell
# API 키로 접근 (200 기대)
$key = (Get-Content .env | Select-String '^API_KEY=') -replace '^API_KEY=', ''
Invoke-WebRequest -Uri "http://localhost:5000/stats" -Headers @{"X-API-Key" = $key} -Method GET | Select-Object StatusCode
# 인증 없이 접근 (401 기대)
Invoke-WebRequest -Uri "http://localhost:5000/stats" -Method GET -ErrorAction SilentlyContinue | Select-Object StatusCode
```

- [ ] **Step 3: GCP VM .env에 API_KEY 추가**

터미널에서 (사용자가 직접 실행):
```bash
ssh jhjttmtmtmjgt@34.11.175.125
nano ~/marketing-agent/.env
# API_KEY=<위에서 생성한 동일한 키 값> 추가 후 저장
```

- [ ] **Step 4: 푸시 + 배포**

```bash
git push origin main
ssh jhjttmtmtmjgt@34.11.175.125 'cd ~/marketing-agent && git pull && sudo systemctl restart marketing-agent'
```

- [ ] **Step 5: 배포 후 확인**

```powershell
$key = (Get-Content .env | Select-String '^API_KEY=') -replace '^API_KEY=', ''
Invoke-WebRequest -Uri "http://34.11.175.125:5000/stats" -Headers @{"X-API-Key" = $key} -Method GET | Select-Object StatusCode
```

Expected: `StatusCode: 200`

---

## 자체 검토 (spec 대비)

| 요구사항 | Task | 구현 |
|---|---|---|
| Instagram 토큰 주간 갱신 | Task 1 | `_refresh_ig_token_job` + CronTrigger(sun 03:00) |
| 앱 시작 시 즉시 갱신 | Task 1 | `threading.Thread(target=_refresh_ig_token_job)` |
| 갱신 실패 시 알림 | Task 1 | `send_alert` 호출 |
| Basic Auth 제거 | Task 2 | `_require_auth` 에서 Basic 처리 삭제 |
| X-API-Key 헤더 인증 | Task 2 | `hmac.compare_digest` 상수 시간 비교 |
| `API_KEY` env var | Task 2 | `.env` + `os.environ.get("API_KEY")` |
| Basic Auth 팝업 제거 | Task 2 | `WWW-Authenticate` 헤더 없음 |
| 공유 링크 인증 면제 | Task 3 | `_AUTH_EXEMPT_PREFIXES`에 `/share/` 추가 |
| 공유 링크 콘텐츠 반환 | Task 3 | 키워드별 블로그 제목 + 인스타 캡션 + 카드뉴스 URL |
| 없는 job_id → 404 | Task 3 | `if not job: return 404` |
| 배포 | Task 4 | git push + systemctl restart |
