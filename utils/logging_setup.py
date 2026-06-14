"""구조적 로깅 설정 — 콘솔 + 회전 파일 핸들러(UTF-8).

print 대신 일관된 포맷·레벨·영속 로그를 제공한다.
get_logger 는 같은 이름에 대해 핸들러를 중복 추가하지 않는다(idempotent).
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"
_configured: set[str] = set()


def get_logger(name: str, log_file=None, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    if name in _configured:
        return logger

    logger.setLevel(level)
    fmt = logging.Formatter(_FORMAT, _DATEFMT)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    logger.addHandler(console)

    if log_file is not None:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            path, maxBytes=2_000_000, backupCount=5, encoding="utf-8"
        )
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)

    logger.propagate = False
    _configured.add(name)
    return logger
