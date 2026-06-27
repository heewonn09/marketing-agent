"""구조적 로깅 설정 — 콘솔 + 회전 파일 핸들러(UTF-8).

print 대신 일관된 포맷·레벨·영속 로그를 제공한다.
get_logger 는 같은 이름에 대해 핸들러를 중복 추가하지 않는다(idempotent).

JSON 모드 (use_json=True):
  {"ts":"...", "level":"INFO", "logger":"app", "msg":"..."}
  운영 환경에서 로그 수집기(Loki, CloudWatch 등)와 연동 시 유용.
"""

import json
import logging
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"
_configured: set[str] = set()


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }, ensure_ascii=False)


def get_logger(
    name: str,
    log_file=None,
    level: int = logging.INFO,
    use_json: bool = False,
) -> logging.Logger:
    logger = logging.getLogger(name)
    if name in _configured:
        return logger

    logger.setLevel(level)
    fmt: logging.Formatter = _JsonFormatter() if use_json else logging.Formatter(_FORMAT, _DATEFMT)

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
