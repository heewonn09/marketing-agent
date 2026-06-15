"""상태 파일 일일 백업 — jobs.db/history.json 등을 날짜별 디렉터리로 복사.

같은 디스크 내 백업이라 디스크 장애엔 무력하지만, 앱 버그·실수 삭제·손상에
대한 복구점을 제공한다. 오프사이트가 필요하면 backups/ 를 GCS/rsync로 동기화.
"""

import shutil
from datetime import date, timedelta
from pathlib import Path

# 백업 대상 (cleanup의 KEEP 목록과 동일한 영속 상태 파일)
_STATE_FILES = ["jobs.db", "history.json", "monitor_state.json",
                "naver_cookies.json", "sales_sent.json"]


def _prune_old(backups_dir: Path, keep_days: int) -> None:
    if not backups_dir.exists():
        return
    cutoff = date.today() - timedelta(days=keep_days)
    for d in backups_dir.iterdir():
        if not d.is_dir():
            continue
        try:
            d_date = date.fromisoformat(d.name)
        except ValueError:
            continue
        if d_date < cutoff:
            shutil.rmtree(d, ignore_errors=True)


def backup_state(root, keep_days: int = 14) -> list[str]:
    """data/ 의 상태 파일을 data/backups/YYYY-MM-DD/ 로 복사하고 오래된 백업 정리.

    복사된 파일명 리스트 반환.
    """
    data = Path(root) / "data"
    backups = data / "backups"
    dest = backups / date.today().isoformat()
    dest.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    for name in _STATE_FILES:
        src = data / name
        if src.exists():
            shutil.copy2(src, dest / name)
            copied.append(name)

    _prune_old(backups, keep_days)
    return copied
