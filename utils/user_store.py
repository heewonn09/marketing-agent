"""사용자 계정 CRUD — jobs.db의 users 테이블 사용."""

import sqlite3
from datetime import datetime
from pathlib import Path

from werkzeug.security import check_password_hash


def _path(db_path: Path | None) -> Path:
    if db_path is not None:
        return db_path
    from utils.job_store import _DEFAULT_DB  # 런타임 참조 (init_db 이후 값)
    return _DEFAULT_DB


def init_users(db_path: Path | None = None) -> None:
    """users 테이블 생성 (없을 때만)."""
    with sqlite3.connect(_path(db_path)) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT    UNIQUE NOT NULL,
                password_hash TEXT    NOT NULL,
                role          TEXT    NOT NULL DEFAULT 'user',
                plan          TEXT    NOT NULL DEFAULT 'starter',
                enabled       INTEGER NOT NULL DEFAULT 1,
                created_at    TEXT    NOT NULL,
                updated_at    TEXT    NOT NULL
            )
        """)


def _row_to_user(row) -> dict:
    return {
        "id": row[0],
        "username": row[1],
        "password_hash": row[2],
        "role": row[3],
        "plan": row[4],
        "enabled": bool(row[5]),
        "created_at": row[6],
        "updated_at": row[7],
    }


_COLS = "id, username, password_hash, role, plan, enabled, created_at, updated_at"


def create_user(
    username: str,
    password_hash: str,
    role: str = "user",
    plan: str = "starter",
    db_path: Path | None = None,
) -> int:
    now = datetime.now().isoformat()
    with sqlite3.connect(_path(db_path)) as conn:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, role, plan, enabled, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 1, ?, ?)",
            (username, password_hash, role, plan, now, now),
        )
        return cur.lastrowid


def get_user_by_username(username: str, db_path: Path | None = None) -> dict | None:
    with sqlite3.connect(_path(db_path)) as conn:
        row = conn.execute(
            f"SELECT {_COLS} FROM users WHERE username = ?", (username,)
        ).fetchone()
    return _row_to_user(row) if row else None


def get_user_by_id(user_id: int, db_path: Path | None = None) -> dict | None:
    with sqlite3.connect(_path(db_path)) as conn:
        row = conn.execute(
            f"SELECT {_COLS} FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    return _row_to_user(row) if row else None


def list_users(db_path: Path | None = None) -> list[dict]:
    with sqlite3.connect(_path(db_path)) as conn:
        rows = conn.execute(
            f"SELECT {_COLS} FROM users ORDER BY created_at"
        ).fetchall()
    return [_row_to_user(r) for r in rows]


def update_user(user_id: int, db_path: Path | None = None, **fields) -> None:
    allowed = {"username", "password_hash", "role", "plan", "enabled"}
    sets, vals = [], []
    for k, v in fields.items():
        if k not in allowed:
            continue
        if k == "enabled":
            v = int(bool(v))
        sets.append(f"{k} = ?")
        vals.append(v)
    if not sets:
        return
    sets.append("updated_at = ?")
    vals.extend([datetime.now().isoformat(), user_id])
    with sqlite3.connect(_path(db_path)) as conn:
        conn.execute(f"UPDATE users SET {', '.join(sets)} WHERE id = ?", vals)


def delete_user(user_id: int, db_path: Path | None = None) -> None:
    with sqlite3.connect(_path(db_path)) as conn:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))


def verify_user(username: str, password: str, db_path: Path | None = None) -> dict | None:
    """비밀번호 검증. 성공 + enabled 이면 user dict, 아니면 None."""
    u = get_user_by_username(username, db_path=db_path)
    if not u or not u["enabled"]:
        return None
    if check_password_hash(u["password_hash"], password):
        return u
    return None


def upsert_admin(username: str, password_hash: str, db_path: Path | None = None) -> None:
    """env var 관리자를 DB에 동기화. 없으면 생성, 있으면 password_hash 업데이트."""
    existing = get_user_by_username(username, db_path=db_path)
    if existing:
        update_user(existing["id"], password_hash=password_hash, role="admin", db_path=db_path)
    else:
        create_user(username, password_hash, role="admin", plan="agency", db_path=db_path)
