from utils.config import env_int


def test_env_int_uses_default_when_unset(monkeypatch):
    monkeypatch.delenv("MY_LIMIT", raising=False)
    assert env_int("MY_LIMIT", 30) == 30


def test_env_int_parses_value(monkeypatch):
    monkeypatch.setenv("MY_LIMIT", "7")
    assert env_int("MY_LIMIT", 30) == 7


def test_env_int_falls_back_on_invalid(monkeypatch):
    monkeypatch.setenv("MY_LIMIT", "abc")
    assert env_int("MY_LIMIT", 30) == 30


def test_env_int_falls_back_on_empty(monkeypatch):
    monkeypatch.setenv("MY_LIMIT", "   ")
    assert env_int("MY_LIMIT", 30) == 30
