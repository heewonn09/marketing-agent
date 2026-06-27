import json
import logging
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path

from utils.state_machine import validate_transition, InvalidTransitionError

_log = logging.getLogger("job_store")

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
                duration_seconds     INTEGER,
                error_message        TEXT
            )
        """)
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
        # 기존 DB 마이그레이션: 새 컬럼 추가
        for col_def in [
            "ALTER TABLE jobs ADD COLUMN naver_post_url TEXT",
            "ALTER TABLE jobs ADD COLUMN instagram_media_id TEXT",
            "ALTER TABLE jobs ADD COLUMN instagram_permalink TEXT",
            "ALTER TABLE jobs ADD COLUMN duration_seconds INTEGER",
            "ALTER TABLE jobs ADD COLUMN error_message TEXT",
            "ALTER TABLE jobs ADD COLUMN user_id INTEGER",
            "ALTER TABLE schedules ADD COLUMN user_id INTEGER",
        ]:
            try:
                conn.execute(col_def)
            except sqlite3.OperationalError:
                pass  # 이미 존재하는 컬럼
        # 쿼리 성능 인덱스 (히스토리 필터·정렬)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_user_created ON jobs(user_id, created_at DESC)")
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
    error_message: str | None = None,
    user_id: int | None = None,
) -> None:
    path = db_path or _DEFAULT_DB
    now = datetime.now().isoformat()
    with sqlite3.connect(path) as conn:
        existing = conn.execute(
            "SELECT created_at, keywords, date, naver_post_url, instagram_media_id, "
            "instagram_permalink, duration_seconds, error_message, user_id, status FROM jobs WHERE job_id = ?",
            (job_id,)
        ).fetchone()
        current_status = existing[9] if existing else None
        # FSM 검증 — 허용되지 않는 전이는 경고 로그만 (강제 중단 방지)
        try:
            validate_transition(current_status, status)
        except InvalidTransitionError as _e:
            _log.warning("FSM: %s (job=%s) — 전이 허용", _e, job_id)
        created_at         = existing[0] if existing else now
        final_keywords     = json.dumps(keywords) if keywords is not None else (existing[1] if existing else "[]")
        final_date         = date if date is not None else (existing[2] if existing else None)
        final_naver_url    = naver_post_url if naver_post_url is not None else (existing[3] if existing else None)
        final_ig_media_id  = instagram_media_id if instagram_media_id is not None else (existing[4] if existing else None)
        final_ig_permalink = instagram_permalink if instagram_permalink is not None else (existing[5] if existing else None)
        final_duration     = duration_seconds if duration_seconds is not None else (existing[6] if existing else None)
        final_error_msg    = error_message if error_message is not None else (existing[7] if existing else None)
        final_user_id      = user_id if user_id is not None else (existing[8] if existing else None)
        conn.execute(
            """INSERT OR REPLACE INTO jobs
               (job_id, status, keywords, date, created_at, updated_at,
                naver_post_url, instagram_media_id, instagram_permalink,
                duration_seconds, error_message, user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (job_id, status, final_keywords, final_date, created_at, now,
             final_naver_url, final_ig_media_id, final_ig_permalink,
             final_duration, final_error_msg, final_user_id),
        )


def get_job(job_id: str, db_path: Path | None = None) -> dict | None:
    path = db_path or _DEFAULT_DB
    with sqlite3.connect(path) as conn:
        row = conn.execute(
            "SELECT job_id, status, keywords, date, naver_post_url, instagram_media_id, "
            "instagram_permalink, duration_seconds, error_message, user_id FROM jobs WHERE job_id = ?",
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
        "error_message": row[8],
        "user_id": row[9],
    }


def list_jobs(
    page: int = 1,
    per_page: int = 10,
    status: str = "",
    q: str = "",
    from_date: str = "",
    to_date: str = "",
    db_path: Path | None = None,
    user_id: int | None = None,
) -> dict:
    """페이지네이션·필터 지원 목록 반환.

    user_id=None 이면 전체(admin), user_id 지정 시 해당 사용자 잡만 반환.
    반환 형식: {"items": [...], "total": N, "page": N, "pages": N}
    """
    path = db_path or _DEFAULT_DB
    where_clauses: list[str] = []
    params: list = []

    if status:
        where_clauses.append("status = ?")
        params.append(status)
    if q:
        where_clauses.append("keywords LIKE ?")
        params.append(f"%{q}%")
    if from_date:
        where_clauses.append("created_at >= ?")
        params.append(from_date)
    if to_date:
        where_clauses.append("created_at <= ?")
        params.append(to_date + "T23:59:59")
    if user_id is not None:
        where_clauses.append("user_id = ?")
        params.append(user_id)

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    with sqlite3.connect(path) as conn:
        total: int = conn.execute(
            f"SELECT COUNT(*) FROM jobs {where_sql}", params
        ).fetchone()[0]

        offset = (page - 1) * per_page
        rows = conn.execute(
            f"SELECT job_id, status, keywords, date, created_at, "
            f"naver_post_url, instagram_media_id, instagram_permalink, "
            f"duration_seconds, error_message, user_id "
            f"FROM jobs {where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params + [per_page, offset],
        ).fetchall()

    pages = max(1, (total + per_page - 1) // per_page)
    items = [
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
            "error_message": row[9],
            "user_id": row[10],
        }
        for row in rows
    ]
    return {"items": items, "total": total, "page": page, "pages": pages}


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
