import logging

from utils.logging_setup import get_logger


def test_logger_writes_to_file(tmp_path):
    log_file = tmp_path / "sub" / "app.log"
    logger = get_logger("test.writes", log_file=log_file)
    logger.info("안녕 hello")
    for h in logger.handlers:
        h.flush()
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "안녕 hello" in content
    assert "[INFO]" in content


def test_logger_idempotent_no_duplicate_handlers(tmp_path):
    name = "test.idempotent"
    logger1 = get_logger(name, log_file=tmp_path / "a.log")
    count1 = len(logger1.handlers)
    logger2 = get_logger(name, log_file=tmp_path / "a.log")
    assert logger1 is logger2
    assert len(logger2.handlers) == count1  # 재호출 시 핸들러 추가 안 됨


def test_logger_respects_level(tmp_path):
    log_file = tmp_path / "lvl.log"
    logger = get_logger("test.level", log_file=log_file, level=logging.WARNING)
    logger.info("이건 안 보임")
    logger.warning("이건 보임")
    for h in logger.handlers:
        h.flush()
    content = log_file.read_text(encoding="utf-8")
    assert "이건 보임" in content
    assert "이건 안 보임" not in content


def test_logger_console_only_when_no_file():
    logger = get_logger("test.console_only")
    # 파일 핸들러 없이 StreamHandler 만 있어야 한다
    assert any(isinstance(h, logging.StreamHandler) for h in logger.handlers)
    assert not any(h.__class__.__name__ == "RotatingFileHandler" for h in logger.handlers)
