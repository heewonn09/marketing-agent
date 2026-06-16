import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def db(tmp_path):
    from utils import user_store
    p = tmp_path / "test.db"
    user_store.init_users(p)
    return p


def test_create_and_get_user(db):
    from utils import user_store
    uid = user_store.create_user("alice", "hashed_pw", role="user", plan="starter", db_path=db)
    assert uid > 0
    u = user_store.get_user_by_username("alice", db_path=db)
    assert u["username"] == "alice"
    assert u["role"] == "user"
    assert u["plan"] == "starter"
    assert u["enabled"] is True


def test_create_duplicate_username_raises(db):
    from utils import user_store
    user_store.create_user("bob", "pw1", db_path=db)
    with pytest.raises(Exception):
        user_store.create_user("bob", "pw2", db_path=db)


def test_verify_user_correct_password(db):
    from utils import user_store
    from werkzeug.security import generate_password_hash
    h = generate_password_hash("secret")
    user_store.create_user("carol", h, db_path=db)
    u = user_store.verify_user("carol", "secret", db_path=db)
    assert u is not None
    assert u["username"] == "carol"


def test_verify_user_wrong_password(db):
    from utils import user_store
    from werkzeug.security import generate_password_hash
    user_store.create_user("dave", generate_password_hash("right"), db_path=db)
    assert user_store.verify_user("dave", "wrong", db_path=db) is None


def test_verify_user_disabled(db):
    from utils import user_store
    from werkzeug.security import generate_password_hash
    uid = user_store.create_user("eve", generate_password_hash("pw"), db_path=db)
    user_store.update_user(uid, enabled=False, db_path=db)
    assert user_store.verify_user("eve", "pw", db_path=db) is None


def test_list_users(db):
    from utils import user_store
    user_store.create_user("u1", "h", db_path=db)
    user_store.create_user("u2", "h", db_path=db)
    users = user_store.list_users(db_path=db)
    assert len(users) == 2


def test_update_user_plan(db):
    from utils import user_store
    uid = user_store.create_user("frank", "h", plan="starter", db_path=db)
    user_store.update_user(uid, plan="pro", db_path=db)
    u = user_store.get_user_by_id(uid, db_path=db)
    assert u["plan"] == "pro"


def test_delete_user(db):
    from utils import user_store
    uid = user_store.create_user("grace", "h", db_path=db)
    user_store.delete_user(uid, db_path=db)
    assert user_store.get_user_by_id(uid, db_path=db) is None


def test_get_nonexistent_user_returns_none(db):
    from utils import user_store
    assert user_store.get_user_by_username("nobody", db_path=db) is None
    assert user_store.get_user_by_id(9999, db_path=db) is None


def test_upsert_admin(db):
    from utils import user_store
    from werkzeug.security import generate_password_hash
    h = generate_password_hash("adminpw")
    user_store.upsert_admin("heewon09", h, db_path=db)
    u = user_store.get_user_by_username("heewon09", db_path=db)
    assert u["role"] == "admin"
    # 재실행해도 중복 생성 없음
    user_store.upsert_admin("heewon09", h, db_path=db)
    assert len(user_store.list_users(db_path=db)) == 1


# ── user_id 잡 격리 ─────────────────────────────────────────────────────────
def test_jobs_list_filter_by_user_id(tmp_path):
    from utils import job_store, user_store
    db = tmp_path / "j.db"
    job_store.init_db(db)
    user_store.init_users(db)
    uid1 = user_store.create_user("u1", "h", db_path=db)
    uid2 = user_store.create_user("u2", "h", db_path=db)
    job_store.upsert_job("job1", "done", ["kw1"], "2026-06-17", db_path=db, user_id=uid1)
    job_store.upsert_job("job2", "done", ["kw2"], "2026-06-17", db_path=db, user_id=uid2)
    job_store.upsert_job("job3", "done", ["kw3"], "2026-06-17", db_path=db, user_id=uid1)

    res1 = job_store.list_jobs(db_path=db, user_id=uid1)
    assert res1["total"] == 2
    assert all(j["user_id"] == uid1 for j in res1["items"])

    res2 = job_store.list_jobs(db_path=db, user_id=uid2)
    assert res2["total"] == 1

    res_all = job_store.list_jobs(db_path=db)  # user_id=None → 전체 (admin용)
    assert res_all["total"] == 3


def test_get_job_returns_user_id(tmp_path):
    from utils import job_store, user_store
    db = tmp_path / "j.db"
    job_store.init_db(db)
    user_store.init_users(db)
    uid = user_store.create_user("u", "h", db_path=db)
    job_store.upsert_job("jobx", "done", ["kw"], "2026-06-17", db_path=db, user_id=uid)
    j = job_store.get_job("jobx", db_path=db)
    assert j["user_id"] == uid
