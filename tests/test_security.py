import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from utils import auth_guard
from werkzeug.security import generate_password_hash


# ── secrets (at-rest 암호화) ──────────────────────────────────────────────
@pytest.fixture
def secrets_mod(tmp_path, monkeypatch):
    """KEY_FILE 을 tmp 로 격리하고 env 키 제거한 secrets 모듈 반환."""
    monkeypatch.delenv("COOKIE_ENCRYPTION_KEY", raising=False)
    from utils import secrets as secrets_module
    importlib.reload(secrets_module)
    monkeypatch.setattr(secrets_module, "_KEY_FILE", tmp_path / ".enc_key")
    return secrets_module


def test_encrypt_decrypt_round_trip(secrets_mod, tmp_path):
    target = tmp_path / "cookies.json"
    payload = [{"name": "NID_SES", "value": "secret", "한글": "값"}]
    secrets_mod.save_encrypted_json(target, payload)

    # 파일은 평문 JSON 이 아니어야 한다
    raw = target.read_bytes()
    assert not raw.lstrip().startswith(b"[")

    obj, was_encrypted = secrets_mod.load_encrypted_json(target)
    assert was_encrypted is True
    assert obj == payload


def test_load_legacy_plaintext_json(secrets_mod, tmp_path):
    target = tmp_path / "legacy.json"
    payload = [{"name": "NID_AUT", "value": "old"}]
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    obj, was_encrypted = secrets_mod.load_encrypted_json(target)
    assert was_encrypted is False
    assert obj == payload


def test_env_key_used_when_set(tmp_path, monkeypatch):
    from cryptography.fernet import Fernet
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("COOKIE_ENCRYPTION_KEY", key)
    from utils import secrets as secrets_module
    importlib.reload(secrets_module)
    # 키 파일을 만들지 않고도 동작해야 한다
    monkeypatch.setattr(secrets_module, "_KEY_FILE", tmp_path / "nonexistent" / ".enc_key")
    target = tmp_path / "c.json"
    secrets_module.save_encrypted_json(target, {"a": 1})
    assert not (tmp_path / "nonexistent" / ".enc_key").exists()
    assert secrets_module.load_encrypted_json(target)[0] == {"a": 1}


# ── verify_credentials ────────────────────────────────────────────────────
def test_verify_credentials_plaintext_ok():
    assert auth_guard.verify_credentials("admin", "pw", "admin", "pw") is True


def test_verify_credentials_wrong_password():
    assert auth_guard.verify_credentials("admin", "nope", "admin", "pw") is False


def test_verify_credentials_no_admin_configured():
    assert auth_guard.verify_credentials("admin", "pw", "", "pw") is False


def test_verify_credentials_hash():
    h = generate_password_hash("s3cret")
    assert auth_guard.verify_credentials("admin", "s3cret", "admin", admin_password_hash=h) is True
    assert auth_guard.verify_credentials("admin", "wrong", "admin", admin_password_hash=h) is False


def test_verify_credentials_hash_takes_precedence_over_plaintext():
    h = generate_password_hash("hashed")
    # 평문은 틀려도 해시가 맞으면 통과
    assert auth_guard.verify_credentials("admin", "hashed", "admin", "plain", h) is True


# ── LoginRateLimiter ──────────────────────────────────────────────────────
def test_rate_limiter_locks_after_max_attempts():
    rl = auth_guard.LoginRateLimiter(max_attempts=3, window=300, lockout=900)
    assert rl.is_locked("1.2.3.4", now=0) is False
    for i in range(3):
        rl.register_failure("1.2.3.4", now=i)
    assert rl.is_locked("1.2.3.4", now=3) is True


def test_rate_limiter_unlocks_after_lockout():
    rl = auth_guard.LoginRateLimiter(max_attempts=2, window=300, lockout=900)
    rl.register_failure("ip", now=0)
    rl.register_failure("ip", now=1)
    assert rl.is_locked("ip", now=100) is True
    assert rl.is_locked("ip", now=1000) is False


def test_rate_limiter_window_expiry():
    rl = auth_guard.LoginRateLimiter(max_attempts=3, window=300, lockout=900)
    rl.register_failure("ip", now=0)
    rl.register_failure("ip", now=1)
    # 윈도우(300s) 밖이면 이전 시도는 무시 → 잠기지 않음
    rl.register_failure("ip", now=400)
    assert rl.is_locked("ip", now=401) is False


def test_rate_limiter_success_resets():
    rl = auth_guard.LoginRateLimiter(max_attempts=2, window=300, lockout=900)
    rl.register_failure("ip", now=0)
    rl.register_success("ip")
    rl.register_failure("ip", now=1)
    assert rl.is_locked("ip", now=2) is False


# ── 멀티유저 로그인 ──────────────────────────────────────────────────────────
import json as _json2
import os as _os3
from werkzeug.security import generate_password_hash as _gph


def test_db_user_can_login(monkeypatch):
    from utils import user_store as _us
    _os3.environ["DISABLE_SCHEDULER"] = "1"
    monkeypatch.setenv("ADMIN_USER", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "adminpw")
    monkeypatch.delenv("API_KEY", raising=False)
    import importlib, app as _a
    importlib.reload(_a)
    _a.app.config["TESTING"] = True
    db = _a.ROOT / "data" / "jobs.db"
    uid = _us.create_user("testuser_login", _gph("testpw"), db_path=db)
    with _a.app.test_client() as c:
        r = c.post("/login", data={"username": "testuser_login", "password": "testpw"},
                   follow_redirects=False)
        assert r.status_code == 302
    _us.delete_user(uid, db_path=db)


def test_wrong_password_returns_login_form(monkeypatch):
    _os3.environ["DISABLE_SCHEDULER"] = "1"
    monkeypatch.setenv("ADMIN_USER", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "adminpw")
    monkeypatch.delenv("API_KEY", raising=False)
    import importlib, app as _a
    importlib.reload(_a)
    _a.app.config["TESTING"] = True
    with _a.app.test_client() as c:
        r = c.post("/login", data={"username": "admin", "password": "wrongpw"},
                   follow_redirects=False)
    assert r.status_code == 200


def test_env_admin_still_works(monkeypatch):
    _os3.environ["DISABLE_SCHEDULER"] = "1"
    monkeypatch.setenv("ADMIN_USER", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "adminpw")
    monkeypatch.delenv("API_KEY", raising=False)
    import importlib, app as _a
    importlib.reload(_a)
    _a.app.config["TESTING"] = True
    with _a.app.test_client() as c:
        r = c.post("/login", data={"username": "admin", "password": "adminpw"},
                   follow_redirects=False)
    assert r.status_code == 302


# ── per-user 잡 격리 ─────────────────────────────────────────────────────────
import sqlite3 as _sqlite3


def test_user_sees_only_own_jobs(monkeypatch):
    _os3.environ["DISABLE_SCHEDULER"] = "1"
    monkeypatch.setenv("ADMIN_USER", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "adminpw")
    monkeypatch.delenv("API_KEY", raising=False)
    import importlib, app as _a
    from utils import user_store as _us, job_store as _js
    importlib.reload(_a)
    _a.app.config["TESTING"] = True
    db = _a.ROOT / "data" / "jobs.db"

    # 이전 실패 실행 잔여물 정리
    for name in ("viewer1_iso", "viewer2_iso"):
        existing = _us.get_user_by_username(name, db_path=db)
        if existing:
            _us.delete_user(existing["id"], db_path=db)
    with _sqlite3.connect(db) as _c:
        _c.execute("DELETE FROM jobs WHERE job_id IN ('job-iso-v1','job-iso-v2')")

    uid1 = _us.create_user("viewer1_iso", _gph("pw1"), db_path=db)
    uid2 = _us.create_user("viewer2_iso", _gph("pw2"), db_path=db)
    _js.upsert_job("job-iso-v1", "done", ["kw1"], "2026-06-17", user_id=uid1)
    _js.upsert_job("job-iso-v2", "done", ["kw2"], "2026-06-17", user_id=uid2)

    with _a.app.test_client() as c:
        c.post("/login", data={"username": "viewer1_iso", "password": "pw1"})
        r = c.get("/history")
        data = _json2.loads(r.data)
        job_ids = [j["job_id"] for j in data["items"]]
        assert "job-iso-v1" in job_ids
        assert "job-iso-v2" not in job_ids

    for uid in [uid1, uid2]:
        _us.delete_user(uid, db_path=db)
    with _sqlite3.connect(db) as conn:
        conn.execute("DELETE FROM jobs WHERE job_id IN ('job-iso-v1','job-iso-v2')")


def test_admin_sees_all_jobs(monkeypatch):
    _os3.environ["DISABLE_SCHEDULER"] = "1"
    monkeypatch.setenv("ADMIN_USER", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "adminpw")
    monkeypatch.delenv("API_KEY", raising=False)
    import importlib, app as _a
    from utils import user_store as _us, job_store as _js
    importlib.reload(_a)
    _a.app.config["TESTING"] = True
    db = _a.ROOT / "data" / "jobs.db"

    uid = _us.create_user("other_user_adm", _gph("pw"), db_path=db)
    _js.upsert_job("job-admin-view", "done", ["kw"], "2026-06-17", user_id=uid)

    with _a.app.test_client() as c:
        c.post("/login", data={"username": "admin", "password": "adminpw"})
        r = c.get("/history")
        data = _json2.loads(r.data)
        job_ids = [j["job_id"] for j in data["items"]]
        assert "job-admin-view" in job_ids

    _us.delete_user(uid, db_path=db)
    with _sqlite3.connect(db) as conn:
        conn.execute("DELETE FROM jobs WHERE job_id='job-admin-view'")


# ── admin 라우트 ──────────────────────────────────────────────────────────────
def test_admin_page_requires_admin_role(monkeypatch):
    _os3.environ["DISABLE_SCHEDULER"] = "1"
    monkeypatch.setenv("ADMIN_USER", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "adminpw")
    monkeypatch.delenv("API_KEY", raising=False)
    import importlib, app as _a
    from utils import user_store as _us
    importlib.reload(_a)
    _a.app.config["TESTING"] = True
    db = _a.ROOT / "data" / "jobs.db"
    existing = _us.get_user_by_username("normaluser_t5", db_path=db)
    if existing:
        _us.delete_user(existing["id"], db_path=db)
    uid = _us.create_user("normaluser_t5", _gph("pw"), role="user", db_path=db)
    with _a.app.test_client() as c:
        c.post("/login", data={"username": "normaluser_t5", "password": "pw"})
        r = c.get("/admin")
        assert r.status_code == 403
    _us.delete_user(uid, db_path=db)


def test_admin_can_list_users(monkeypatch):
    _os3.environ["DISABLE_SCHEDULER"] = "1"
    monkeypatch.setenv("ADMIN_USER", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "adminpw")
    monkeypatch.delenv("API_KEY", raising=False)
    import importlib, app as _a
    importlib.reload(_a)
    _a.app.config["TESTING"] = True
    with _a.app.test_client() as c:
        c.post("/login", data={"username": "admin", "password": "adminpw"})
        r = c.get("/admin/users")
        assert r.status_code == 200
        data = _json2.loads(r.data)
        assert "users" in data


def test_admin_create_and_delete_user(monkeypatch):
    _os3.environ["DISABLE_SCHEDULER"] = "1"
    monkeypatch.setenv("ADMIN_USER", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "adminpw")
    monkeypatch.delenv("API_KEY", raising=False)
    import importlib, app as _a
    importlib.reload(_a)
    _a.app.config["TESTING"] = True
    with _a.app.test_client() as c:
        c.post("/login", data={"username": "admin", "password": "adminpw"})
        r = c.post("/admin/users",
                   json={"username": "newuser_t5", "password": "newpw", "plan": "starter"})
        assert r.status_code == 201
        uid = _json2.loads(r.data)["id"]
        r = c.delete(f"/admin/users/{uid}")
        assert r.status_code == 200
