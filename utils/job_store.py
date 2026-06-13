import json
import sqlite3
from datetime import datetime
from pathlib import Path

_DEFAULT_DB: Path | None = None


def init_db(db_path: Path) -> None:
    global _DEFAULT_DB
    _DEFAULT_DB = db_path
    db_path.parent.mkdir(exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id     TEXT PRIMARY KEY,
                status     TEXT NOT NULL,
                keywords   TEXT,
                date       TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
    mark_interrupted(db_path)


def upsert_job(
    job_id: str,
    status: str,
    keywords: list[str] | None = None,
    date: str | None = None,
    db_path: Path | None = None,
) -> None:
    path = db_path or _DEFAULT_DB
    now = datetime.now().isoformat()
    with sqlite3.connect(path) as conn:
        existing = conn.execute(
            "SELECT created_at FROM jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        created_at = existing[0] if existing else now
        conn.execute(
            """INSERT OR REPLACE INTO jobs
               (job_id, status, keywords, date, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (job_id, status, json.dumps(keywords or []), date, created_at, now),
        )


def get_job(job_id: str, db_path: Path | None = None) -> dict | None:
    path = db_path or _DEFAULT_DB
    with sqlite3.connect(path) as conn:
        row = conn.execute(
            "SELECT job_id, status, keywords, date FROM jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
    if not row:
        return None
    return {
        "job_id": row[0],
        "status": row[1],
        "keywords": json.loads(row[2] or "[]"),
        "date": row[3],
    }


def mark_interrupted(db_path: Path | None = None) -> int:
    path = db_path or _DEFAULT_DB
    with sqlite3.connect(path) as conn:
        cur = conn.execute(
            "UPDATE jobs SET status = 'interrupted', updated_at = ? WHERE status = 'running'",
            (datetime.now().isoformat(),),
        )
        return cur.rowcount
