from datetime import datetime, timedelta
from pathlib import Path

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


def cleanup_old_files(root: Path, days: int = 7) -> list[Path]:
    cutoff = datetime.now() - timedelta(days=days)
    deleted: list[Path] = []
    for pattern in _PATTERNS:
        for f in root.glob(pattern):
            if f.name in KEEP:
                continue
            if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                f.unlink()
                deleted.append(f)
                print(f"[cleanup] 삭제: {f.name}")
    return deleted
