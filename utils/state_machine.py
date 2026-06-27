"""잡 상태 전이 FSM (Finite State Machine).

허용된 전이만 통과시켜 DB 불일치를 방지한다.
upsert_job() 이 이 모듈에 의존하므로 외부 라이브러리 import 없이 순수 Python 으로 작성.

상태 다이어그램:
  created ──▶ running ──▶ pending_approval ──▶ posting ──▶ done
                    │                                 │
                    └────────────────────────────────▶ error
                    └─▶ rejected
                    └─▶ interrupted  (서버 재시작 시 강제 전이)
  posting ──▶ done
  posting ──▶ error
  pending_approval ──▶ rejected
  * ──▶ interrupted   (mark_interrupted 가 running 상태만 대상)
"""

from __future__ import annotations

# 허용된 (현재 상태 → 다음 상태) 전이 집합
# None 은 "아무 상태에서나" (초기 생성)
ALLOWED_TRANSITIONS: frozenset[tuple[str | None, str]] = frozenset({
    (None,                "created"),
    (None,                "running"),          # 신규 잡 즉시 running 허용
    ("created",           "running"),
    ("running",           "pending_approval"),
    ("running",           "posting"),          # auto_post 시 pending 건너뜀
    ("running",           "done"),
    ("running",           "error"),
    ("running",           "interrupted"),
    ("running",           "rejected"),         # 드문 경우
    ("pending_approval",  "posting"),
    ("pending_approval",  "rejected"),
    ("pending_approval",  "error"),
    ("posting",           "done"),
    ("posting",           "error"),
    ("interrupted",       "running"),          # 재실행
    ("error",             "running"),          # 재실행
    ("rejected",          "running"),          # 재실행
    # 멱등 전이 — 같은 상태로의 업데이트 허용 (upsert 중복 호출 방어)
    ("done",              "done"),
    ("error",             "error"),
})

# 어떤 상태에서든 허용되는 전이 (최종 상태 기록용)
_ALWAYS_ALLOWED: frozenset[str] = frozenset({"interrupted", "error"})


class InvalidTransitionError(ValueError):
    """허용되지 않는 상태 전이 시도."""


def validate_transition(current: str | None, next_status: str) -> None:
    """current → next_status 전이가 허용되는지 검증.

    허용되지 않으면 InvalidTransitionError 를 raise 한다.
    next_status 가 _ALWAYS_ALLOWED 에 속하면 무조건 통과.
    """
    if next_status in _ALWAYS_ALLOWED:
        return
    if (current, next_status) not in ALLOWED_TRANSITIONS:
        raise InvalidTransitionError(
            f"잘못된 상태 전이: {current!r} → {next_status!r}"
        )


def is_terminal(status: str) -> bool:
    """더 이상 전이가 없는 최종 상태 여부."""
    return status in {"done", "rejected"}
