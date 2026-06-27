"""민감 파일(쿠키 등)의 at-rest 암호화 헬퍼.

키 우선순위:
1. 환경변수 COOKIE_ENCRYPTION_KEY (urlsafe base64 32바이트, Fernet 키) — 운영 권장
2. data/.enc_key 파일 (없으면 자동 생성, 권한 600)

load_encrypted_json 은 레거시 평문 JSON 도 읽어 (was_encrypted=False) 반환하므로
기존 평문 파일을 무중단으로 마이그레이션할 수 있다.

.env 민감 변수 암호화:
- encrypt_env_secrets(".env") → data/.env.enc 생성 (1회 마이그레이션)
- load_env_secrets() → data/.env.enc 복호화 후 os.environ 주입 (앱 시작 시 호출)
"""

import json
import os
import sys
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

_ROOT = Path(__file__).parent.parent
_KEY_FILE = _ROOT / "data" / ".enc_key"
_ENV_ENC_FILE = _ROOT / "data" / ".env.enc"

# .env 에서 암호화 대상 키 (평문으로 두면 git 유출 위험)
SENSITIVE_ENV_KEYS: frozenset[str] = frozenset({
    "NAVER_PW",
    "ADMIN_PASSWORD",
    "API_KEY",
    "GEMINI_API_KEY",
    "IG_ACCESS_TOKEN",
    "IG_APP_SECRET",
    "DATALAB_CLIENT_ID",
    "DATALAB_CLIENT_SECRET",
    "NAVER_CLIENT_ID",
    "NAVER_CLIENT_SECRET",
    "SMTP_PASSWORD",
})


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


# ── .env 민감 변수 암호화 ─────────────────────────────────────────────────────

def load_env_secrets(override: bool = True) -> int:
    """data/.env.enc 를 복호화해 os.environ 에 주입. 반환값: 주입된 키 수.

    app.py 에서 load_dotenv() 보다 먼저 호출해야 암호화된 값이 우선 적용된다.
    .env.enc 가 없으면 0 반환 (정상 — 마이그레이션 전 상태).
    """
    if not _ENV_ENC_FILE.exists():
        return 0
    try:
        raw = _ENV_ENC_FILE.read_bytes()
        data = get_fernet().decrypt(raw)
        env_dict: dict[str, str] = json.loads(data.decode("utf-8"))
        count = 0
        for k, v in env_dict.items():
            if override or k not in os.environ:
                os.environ[k] = str(v)
                count += 1
        return count
    except Exception as e:
        print(f"[secrets] .env.enc 복호화 실패: {e}", file=sys.stderr)
        return 0


def encrypt_env_secrets(env_path: "Path | str | None" = None) -> dict[str, str]:
    """env_path(.env)에서 SENSITIVE_ENV_KEYS 를 읽어 data/.env.enc 에 암호화 저장.

    반환값: 암호화된 key→value dict (마이그레이션 확인용).
    .env 파일 자체는 수정하지 않는다 — 사용자가 직접 민감 값을 제거해야 한다.
    """
    try:
        from dotenv import dotenv_values
    except ImportError:
        raise RuntimeError("python-dotenv 패키지가 필요합니다.")

    path = Path(env_path) if env_path else (_ROOT / ".env")
    env = dotenv_values(str(path))
    sensitive = {k: v for k, v in env.items() if k in SENSITIVE_ENV_KEYS and v}
    if not sensitive:
        return {}

    data = json.dumps(sensitive, ensure_ascii=False).encode("utf-8")
    token = get_fernet().encrypt(data)
    _ENV_ENC_FILE.parent.mkdir(exist_ok=True)
    _ENV_ENC_FILE.write_bytes(token)
    try:
        os.chmod(_ENV_ENC_FILE, 0o600)
    except OSError:
        pass
    return sensitive
