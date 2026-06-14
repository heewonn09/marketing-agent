"""민감 파일(쿠키 등)의 at-rest 암호화 헬퍼.

키 우선순위:
1. 환경변수 COOKIE_ENCRYPTION_KEY (urlsafe base64 32바이트, Fernet 키) — 운영 권장
2. data/.enc_key 파일 (없으면 자동 생성, 권한 600)

load_encrypted_json 은 레거시 평문 JSON 도 읽어 (was_encrypted=False) 반환하므로
기존 평문 파일을 무중단으로 마이그레이션할 수 있다.
"""

import json
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

_ROOT = Path(__file__).parent.parent
_KEY_FILE = _ROOT / "data" / ".enc_key"


def _load_or_create_key() -> bytes:
    env_key = os.environ.get("COOKIE_ENCRYPTION_KEY")
    if env_key:
        return env_key.encode() if isinstance(env_key, str) else env_key
    if _KEY_FILE.exists():
        return _KEY_FILE.read_bytes().strip()
    key = Fernet.generate_key()
    _KEY_FILE.parent.mkdir(exist_ok=True)
    _KEY_FILE.write_bytes(key)
    try:
        os.chmod(_KEY_FILE, 0o600)
    except OSError:
        pass
    return key


def get_fernet() -> Fernet:
    return Fernet(_load_or_create_key())


def save_encrypted_json(path, obj) -> None:
    """obj 를 JSON 직렬화 후 Fernet 으로 암호화해 path 에 저장."""
    data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    token = get_fernet().encrypt(data)
    p = Path(path)
    p.parent.mkdir(exist_ok=True)
    p.write_bytes(token)
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass


def load_encrypted_json(path):
    """암호화 또는 레거시 평문 JSON 을 읽는다.

    Returns (obj, was_encrypted). was_encrypted=False 이면 호출측에서
    save_encrypted_json 으로 재저장해 마이그레이션할 수 있다.
    """
    raw = Path(path).read_bytes()
    try:
        data = get_fernet().decrypt(raw)
        return json.loads(data.decode("utf-8")), True
    except (InvalidToken, ValueError):
        pass
    return json.loads(raw.decode("utf-8")), False
