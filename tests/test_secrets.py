"""utils/secrets.py 단위 테스트."""
import json
import os
import tempfile
from pathlib import Path

import pytest
from cryptography.fernet import Fernet


# ── load_env_secrets ──────────────────────────────────────────────────────────

def test_load_env_secrets_no_file(tmp_path, monkeypatch):
    """data/.env.enc 없으면 0 반환."""
    import utils.secrets as sec
    monkeypatch.setattr(sec, "_ENV_ENC_FILE", tmp_path / "nonexistent.enc")
    assert sec.load_env_secrets() == 0


def test_load_env_secrets_injects_vars(tmp_path, monkeypatch):
    """올바른 .env.enc → os.environ 주입 확인."""
    import utils.secrets as sec
    # 테스트용 키 생성
    key = Fernet.generate_key()
    f = Fernet(key)
    payload = json.dumps({"TEST_SECRET_VAR": "hello_test"}).encode()
    enc_file = tmp_path / ".env.enc"
    enc_file.write_bytes(f.encrypt(payload))
    monkeypatch.setattr(sec, "_ENV_ENC_FILE", enc_file)
    monkeypatch.setattr(sec, "_load_or_create_key", lambda: key)
    monkeypatch.setattr(sec, "get_fernet", lambda: Fernet(key))

    count = sec.load_env_secrets()
    assert count == 1
    assert os.environ.get("TEST_SECRET_VAR") == "hello_test"
    # 정리
    os.environ.pop("TEST_SECRET_VAR", None)


def test_load_env_secrets_bad_file(tmp_path, monkeypatch):
    """손상된 .env.enc → 0 반환, 예외 없음."""
    import utils.secrets as sec
    enc_file = tmp_path / ".env.enc"
    enc_file.write_bytes(b"corrupted_data")
    monkeypatch.setattr(sec, "_ENV_ENC_FILE", enc_file)
    assert sec.load_env_secrets() == 0


# ── encrypt_env_secrets ───────────────────────────────────────────────────────

def test_encrypt_env_secrets_writes_enc(tmp_path, monkeypatch):
    """encrypt_env_secrets 가 .env.enc 를 생성하고 복호화 가능해야 함."""
    import utils.secrets as sec
    key = Fernet.generate_key()
    enc_file = tmp_path / ".env.enc"
    monkeypatch.setattr(sec, "_ENV_ENC_FILE", enc_file)
    monkeypatch.setattr(sec, "_load_or_create_key", lambda: key)
    monkeypatch.setattr(sec, "get_fernet", lambda: Fernet(key))

    env_file = tmp_path / ".env"
    env_file.write_text("NAVER_PW=testpass123\nOTHER_VAR=public\n", encoding="utf-8")

    result = sec.encrypt_env_secrets(env_file)
    assert "NAVER_PW" in result
    assert "OTHER_VAR" not in result
    assert enc_file.exists()

    # 복호화 확인
    raw = enc_file.read_bytes()
    decrypted = json.loads(Fernet(key).decrypt(raw).decode())
    assert decrypted["NAVER_PW"] == "testpass123"


def test_encrypt_env_secrets_no_sensitive_keys(tmp_path, monkeypatch):
    """민감 키 없는 .env → 빈 dict 반환."""
    import utils.secrets as sec
    env_file = tmp_path / ".env"
    env_file.write_text("OTHER_VAR=public\nDEBUG=true\n", encoding="utf-8")
    result = sec.encrypt_env_secrets(env_file)
    assert result == {}


# ── save/load_encrypted_json ──────────────────────────────────────────────────

def test_save_and_load_encrypted_json(tmp_path, monkeypatch):
    """저장 → 복호화 왕복."""
    import utils.secrets as sec
    key = Fernet.generate_key()
    monkeypatch.setattr(sec, "_load_or_create_key", lambda: key)
    monkeypatch.setattr(sec, "get_fernet", lambda: Fernet(key))

    path = tmp_path / "test.enc"
    obj = {"cookie": "abc123", "session": [1, 2, 3]}
    sec.save_encrypted_json(path, obj)
    loaded, was_enc = sec.load_encrypted_json(path)
    assert loaded == obj
    assert was_enc is True


def test_load_legacy_plaintext_json(tmp_path, monkeypatch):
    """평문 JSON 도 읽어야 한다 (마이그레이션 호환)."""
    import utils.secrets as sec
    key = Fernet.generate_key()
    monkeypatch.setattr(sec, "_load_or_create_key", lambda: key)
    monkeypatch.setattr(sec, "get_fernet", lambda: Fernet(key))

    path = tmp_path / "plain.json"
    path.write_text('{"key":"value"}', encoding="utf-8")
    loaded, was_enc = sec.load_encrypted_json(path)
    assert loaded == {"key": "value"}
    assert was_enc is False
