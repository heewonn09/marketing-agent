import json
import sqlite3
from collections import Counter
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
                job_id               TEXT PRIMARY KEY,
                status               TEXT NOT NULL,
                keywords             TEXT,
                date                 TEXT,
                created_at           TEXT NOT NULL,
                updated_at           TEXT NOT NULL,
                naver_post_url       TEXT,
                instagram_media_id   TEXT,
                instagram_permalink  TEXT,
                duration_seconds     INTEGER
            )
        """)
        # 기존 DB 마이그레이션: 새 컬럼 추가
        for col_def in [
            "ALTER TABLE jobs ADD COLUMN naver_post_url TEXT",
            "ALTER TABLE jobs ADD COLUMN instagram_media_id TEXT",
            "ALTER TABLE jobs ADD COLUMN instagram_permalink TEXT",
            "ALTER TABLE jobs ADD COLUMN duration_seconds INTEGER",
        ]:
            try:
                conn.execute(col_def)
            except sqlite3.OperationalError:
                pass  # 이미 존재하는 컬럼
    mark_interrupted(db_path)


def upsert_job(
    job_id: str,
    status: str,
    keywords: list[str] | None = None,
    date: str | None = None,
    db_path: Path | None = None,
    naver_post_url: str | None = None,
    instagram_media_id: str | None = None,
    instagram_permalink: str | None = None,
    duration_seconds: int | None = None,
) -> None:
    path = db_path or _DEFAULT_DB
    now = datetime.now().isoformat()
    with sqlite3.connect(path) as conn:
        existing = conn.execute(
            "SELECT created_at, keywords, date, naver_post_url, instagram_media_id, instagram_permalink, duration_seconds FROM jobs WHERE job_id = ?",
            (job_id,)
        ).fetchone()
        created_at             = existing[0] if existing else now
        final_keywords         = json.dumps(keywords) if keywords is not None else (existing[1] if existing else "[]")
        final_date             = date if date is not None else (existing[2] if existing else None)
        final_naver_url        = naver_post_url if naver_post_url is not None else (existing[3] if existing else None)
        final_ig_media_id      = instagram_media_id if instagram_media_id is not None else (existing[4] if existing else None)
        final_ig_permalink     = instagram_permalink if instagram_permalink is not None else (existing[5] if existing else None)
        final_duration         = duration_seconds if duration_seconds is not None else (existing[6] if existing else None)
        conn.execute(
            """INSERT OR REPLACE INTO jobs
               (job_id, status, keywords, date, created_at, updated_at,
                naver_post_url, instagram_media_id, instagram_permalink, duration_seconds)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (job_id, status, final_keywords, final_date, created_at, now,
             final_naver_url, final_ig_media_id, final_ig_permalink, final_duration),
        )


def get_job(job_id: str, db_path: Path | None = None) -> dict | None:
    path = db_path or _DEFAULT_DB
    with sqlite3.connect(path) as conn:
        row = conn.execute(
            "SELECT job_id, status, keywords, date, naver_post_url, instagram_media_id, instagram_permalink, duration_seconds FROM jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
    if not row:
        return None
    return {
        "job_id": row[0],
        "status": row[1],
        "keywords": json.loads(row[2] or "[]"),
        "date": row[3],
        "naver_post_url": row[4],
        "instagram_media_id": row[5],
        "instagram_permalink": row[6],
        "duration_seconds": row[7],
    }


def list_jobs(limit: int = 20, db_path: Path | None = None) -> list[dict]:
    path = db_path or _DEFAULT_DB
    with sqlite3.connect(path) as conn:
        rows = conn.execute(
            "SELECT job_id, status, keywords, date, created_at, "
            "naver_post_url, instagram_media_id, instagram_permalink, duration_seconds "
            "FROM jobs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {
            "job_id": row[0],
            "status": row[1],
            "keywords": json.loads(row[2] or "[]"),
            "date": row[3],
            "created_at": row[4],
            "naver_post_url": row[5],
            "instagram_media_id": row[6],
            "instagram_permalink": row[7],
            "duration_seconds": row[8],
        }
        for row in rows
    ]


def get_stats(db_path: Path | None = None) -> dict:
    path = db_path or _DEFAULT_DB
    with sqlite3.connect(path) as conn:
        total    = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        done     = conn.execute("SELECT COUNT(*) FROM jobs WHERE status='done'").fetchone()[0]
        errors   = conn.execute("SELECT COUNT(*) FROM jobs WHERE status='error'").fetchone()[0]
        week_cnt = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE created_at >= datetime('now', '-7 days')"
        ).fetchone()[0]
        avg_dur  = conn.execute(
            "SELECT AVG(duration_seconds) FROM jobs WHERE status='done' AND duration_seconds IS NOT NULL"
        ).fetchone()[0]
        kw_rows  = conn.execute("SELECT keywords FROM jobs WHERE keywords IS NOT NULL").fetchall()

    kw_counter: Counter = Counter()
    for (kw_json,) in kw_rows:
        try:
            for kw in json.loads(kw_json or "[]"):
                kw_counter[kw.strip()] += 1
        except Exception:
            pass

    top_kw = kw_counter.most_common(1)[0][0] if kw_counter else ""
    success_rate = round(done * 100 / total) if total else 0
    return {
        "total": total,
        "done": done,
        "error": errors,
        "week_jobs": week_cnt,
        "success_rate": success_rate,
        "top_keyword": top_kw,
        "avg_duration_seconds": round(avg_dur) if avg_dur else None,
    }


def mark_interrupted(db_path: Path | None = None) -> int:
    path = db_path or _DEFAULT_DB
    with sqlite3.connect(path) as conn:
        cur = conn.execute(
            "UPDATE jobs SET status = 'interrupted', updated_at = ? WHERE status = 'running'",
            (datetime.now().isoformat(),),
        )
        return cur.rowcount
