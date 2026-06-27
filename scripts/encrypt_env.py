#!/usr/bin/env python3
"""민감 환경변수 초기 암호화 스크립트 (1회 실행).

실행: python scripts/encrypt_env.py [--env .env]

동작:
  1. .env 에서 SENSITIVE_ENV_KEYS 값을 읽어 data/.env.enc 에 Fernet 암호화 저장
  2. 암호화된 키 목록 출력
  3. .env 에서 해당 값을 주석 처리할 것을 안내

app.py 는 시작 시 data/.env.enc 를 자동 로드하므로
.env 에서 민감 값을 제거해도 동작에 문제 없다.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.secrets import encrypt_env_secrets, SENSITIVE_ENV_KEYS, _ENV_ENC_FILE

parser = argparse.ArgumentParser(description="민감 .env 변수 Fernet 암호화")
parser.add_argument("--env", default=".env", help=".env 파일 경로 (기본: .env)")
args = parser.parse_args()

env_path = Path(args.env)
if not env_path.exists():
    print(f"[ERROR] {env_path} 파일이 없습니다.", file=sys.stderr)
    sys.exit(1)

print(f"[encrypt_env] {env_path} → {_ENV_ENC_FILE}")
encrypted = encrypt_env_secrets(env_path)

if not encrypted:
    print("[INFO] 암호화할 민감 키가 없습니다 (이미 제거됐거나 해당 키 없음).")
    sys.exit(0)

print(f"\n✅ data/.env.enc 저장 완료 — {len(encrypted)}개 키 암호화:")
for k in sorted(encrypted):
    print(f"   {k}")

print("\n📌 다음 단계: .env 에서 아래 키의 값을 제거하거나 주석 처리하세요.")
print("   (app.py 시작 시 .env.enc 에서 자동 복호화됩니다)\n")
for k in sorted(encrypted):
    print(f"   # {k}=<removed — stored in data/.env.enc>")

print(f"\n🔑 암호화 키 위치: data/.enc_key (백업 필수, git 에 커밋 금지)")
