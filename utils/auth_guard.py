"""인증 자격증명 검증 + 로그인 시도 제한 (전송/저장과 무관한 순수 로직).

app.py 에서 import 해 사용하며, Flask 앱 생성 없이 단위 테스트 가능하도록 분리한다.

LoginRateLimiter.persist_path 를 지정하면 잠금 상태를 JSON 파일에 영속화한다.
서버 재시작 후에도 잠금이 유지되어 브루트포스 방어가 지속된다.
"""

import hmac
import json
import time
from pathlib import Path

from werkzeug.security import check_password_hash


def verify_credentials(
    user: str,
    pwd: str,
    admin_user: str,
    admin_password: str = "",
    admin_password_hash: str = "",
) -> bool:
    """상수 시간 비교로 자격증명 검증.

    admin_password_hash(werkzeug 해시)가 있으면 우선 사용하고,
    없으면 admin_password 평문과 상수 시간 비교한다.
    user/pwd 검사를 단축 평가 없이 모두 계산해 타이밍 누출을 줄인다.
    """
    if not admin_user:
        return False
    user_ok = hmac.compare_digest((user or "").encode(), admin_user.encode())
    if admin_password_hash:
        pwd_ok = check_password_hash(admin_password_hash, pwd or "")
    elif admin_password:
        pwd_ok = hmac.compare_digest((pwd or "").encode(), admin_password.encode())
    else:
        return False
    return user_ok and pwd_ok


class LoginRateLimiter:
    """IP(또는 임의 키)별 로그인 실패 횟수 제한 + 잠금.

    persist_path 지정 시 잠금 상태를 JSON 파일에 저장해 서버 재시작 후에도 유지.
    """

    def __init__(
        self,
        max_attempts: int = 5,
        window: int = 300,
        lockout: int = 900,
        persist_path: "Path | str | None" = None,
    ):
        self.max_attempts = max_attempts
        self.window = window
        self.lockout = lockout
        self._attempts: dict[str, list[float]] = {}
        self._locked_until: dict[str, float] = {}
        self._persist_path: Path | None = Path(persist_path) if persist_path else None
        if self._persist_path:
            self._load()

    # ── 영속화 ─────────────────────────────────────────────────────────────────

    def _load(self) -> None:
        if not self._persist_path or not self._persist_path.exists():
            return
        try:
            data = json.loads(self._persist_path.read_text(encoding="utf-8"))
            now = time.time()
            # 만료된 항목 제거 후 로드
            self._locked_until = {k: v for k, v in data.items() if v > now}
        except Exception:
            pass

    def _save(self) -> None:
        if not self._persist_path:
            return
        try:
            self._persist_path.parent.mkdir(exist_ok=True)
            self._persist_path.write_text(
                json.dumps(self._locked_until, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    # ── 퍼블릭 API ─────────────────────────────────────────────────────────────

    def is_locked(self, key: str, now: float | None = None) -> bool:
        now = now if now is not None else time.time()
        return now < self._locked_until.get(key, 0)

    def register_failure(self, key: str, now: float | None = None) -> None:
        now = now if now is not None else time.time()
        bucket = [t for t in self._attempts.get(key, []) if now - t < self.window]
        bucket.append(now)
        self._attempts[key] = bucket
        if len(bucket) >= self.max_attempts:
            self._locked_until[key] = now + self.lockout
            self._attempts[key] = []
            self._save()

    def register_success(self, key: str) -> None:
        self._attempts.pop(key, None)
        self._locked_until.pop(key, None)
        self._save()
