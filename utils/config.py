"""환경변수 기반 설정 헬퍼.

하드코딩된 상한값을 .env 로 조정할 수 있게 하되, 미설정/잘못된 값이면
안전한 기본값으로 폴백한다.
"""

import os


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default
