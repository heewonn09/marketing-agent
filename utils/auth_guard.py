"""인증 자격증명 검증 + 로그인 시도 제한 (전송/저장과 무관한 순수 로직).

app.py 에서 import 해 사용하며, Flask 앱 생성 없이 단위 테스트 가능하도록 분리한다.
"""

import hmac
import time

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
    """IP(또는 임의 키)별 로그인 실패 횟수 제한 + 잠금."""

    def __init__(self, max_attempts: int = 5, window: int = 300, lockout: int = 900):
        self.max_attempts = max_attempts
        self.window = window
        self.lockout = lockout
        self._attempts: dict[str, list[float]] = {}
        self._locked_until: dict[str, float] = {}

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

    def register_success(self, key: str) -> None:
        self._attempts.pop(key, None)
        self._locked_until.pop(key, None)
