from datetime import datetime, timedelta
from pathlib import Path

from utils.logging_setup import get_logger

_log = get_logger("cleanup", log_file=Path(__file__).parent.parent / "logs" / "app.log")

KEEP = frozenset({
    "history.json",
    "monitor_state.json",
    "sales_leads.json",
    "sales_sent.json",
    "naver_cookies.json",
    "jobs.db",
})

_PATTERNS = [
    "output/report_*.pdf",
    "output/report_*.html",
    "output/content_*.json",
    "output/cardnews_*.png",
    "data/analyzed_*.json",
    "data/*_20[0-9][0-9]-[0-9][0-9]-[0-9][0-9].json",
]

# 보존 기간이 다른 패턴 (days 무시, 고정 보존)
_SHORT_PATTERNS: list[tuple[str, int]] = [
    ("data/ig_pending_*.json", 1),       # carousel 캐시 — 8h TTL 이후 잔여분 1일 후 정리
    ("data/instagram_error_*.json", 14), # Instagram 에러 로그 — 14일 보존
]


def cleanup_old_files(root: Path, days: int = 7) -> list[Path]:
    now = datetime.now()
    cutoff = now - timedelta(days=days)
    deleted: list[Path] = []
    for pattern in _PATTERNS:
        for f in root.glob(pattern):
            if f.name in KEEP:
                continue
            if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                f.unlink()
                deleted.append(f)
    for pattern, keep_days in _SHORT_PATTERNS:
        short_cutoff = now - timedelta(days=keep_days)
        for f in root.glob(pattern):
            if f.name in KEEP:
                continue
            if datetime.fromtimestamp(f.stat().st_mtime) < short_cutoff:
                f.unlink()
                deleted.append(f)
    return deleted
