"""파이프라인 체크포인트 — 완료한 단계를 기록해 실패 지점부터 재개할 수 있게 한다.

CLI orchestrator 전용(웹 app.py 의 run_pipeline 과는 무관). 단계 키 집합을
JSON 파일로 저장한다.
"""

import json
from pathlib import Path


def load_completed(path) -> set[str]:
    p = Path(path)
    if not p.exists():
        return set()
    try:
        return set(json.loads(p.read_text(encoding="utf-8")))
    except (ValueError, OSError):
        return set()


def mark_completed(path, step_key: str) -> None:
    done = load_completed(path)
    done.add(step_key)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(sorted(done), ensure_ascii=False), encoding="utf-8")


def clear(path) -> None:
    p = Path(path)
    if p.exists():
        p.unlink()
