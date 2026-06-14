# 보안 가이드

이 문서는 두 가지 Critical 이슈(인증/시크릿 보안, poster 봇 감지)에 대한 보강 내용과 설정 방법을 다룬다.

## 1. 전송 구간 암호화 (HTTPS)

GCP 웹앱이 평문 HTTP 로 노출되면 Basic Auth 자격증명·세션 쿠키가 평문 전송된다.
Caddy 리버스 프록시로 TLS 를 종단한다.

1. `deploy/Caddyfile` 참고해 Caddy 설치·설정 (도메인 있으면 자동 Let's Encrypt, IP 만 있으면 `tls internal`).
2. `.env` 에 `FORCE_HTTPS=1` 추가 → 세션 쿠키에 `Secure` 플래그가 붙는다.
3. gunicorn 은 외부 직접 노출을 끊고 로컬만 listen 권장:
   `marketing-agent.service` 의 `--bind 0.0.0.0:5000` → `--bind 127.0.0.1:5000`.
   (Caddy 가 443 → 127.0.0.1:5000 으로 프록시)
4. 앱은 `ProxyFix` 로 `X-Forwarded-Proto` 를 인식해 원래 스킴을 판별한다.

## 2. 인증 강화 (app.py)

| 항목 | 동작 |
|------|------|
| `SECRET_KEY` 영구화 | env 없으면 `data/.flask_secret` 에 저장·재사용 (재시작 시 세션 유지) |
| 상수 시간 비교 | `hmac.compare_digest` 로 타이밍 공격 완화 (`utils/auth_guard.py`) |
| 비밀번호 해시 지원 | `ADMIN_PASSWORD_HASH`(werkzeug 해시) 설정 시 평문 `ADMIN_PASSWORD` 대신 사용 |
| 로그인 시도 제한 | IP 별 5회 실패 시 15분 잠금(429) — `LoginRateLimiter` |
| 세션 쿠키 보호 | `HttpOnly`, `SameSite=Lax`, `FORCE_HTTPS=1` 시 `Secure` |

비밀번호 해시 생성:
```powershell
.\venv\Scripts\python.exe -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('새비밀번호'))"
```
출력값을 `.env` 의 `ADMIN_PASSWORD_HASH=` 에 넣고 `ADMIN_PASSWORD` 는 제거한다.

## 3. 시크릿 at-rest 암호화 (utils/secrets.py)

`data/naver_cookies.json`(네이버 세션 쿠키 = 계정 탈취 위험)을 Fernet 으로 암호화 저장한다.

- 키 우선순위: `COOKIE_ENCRYPTION_KEY`(env, 권장) → `data/.enc_key`(자동 생성, 권한 600).
- **레거시 평문 쿠키는 자동으로 읽혀 다음 저장 시 암호화 형식으로 마이그레이션**되므로 기존 세션이 끊기지 않는다.
- 운영 키 생성:
  ```powershell
  .\venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```
  출력을 `.env` 의 `COOKIE_ENCRYPTION_KEY=` 에 넣으면 키 파일 대신 env 키를 쓴다.

> 참고: 키 파일을 데이터와 같은 디렉터리에 두면 파일시스템 접근자에 대한 방어력은 제한적이다.
> 강한 보호가 필요하면 `COOKIE_ENCRYPTION_KEY` 를 시크릿 매니저/환경변수로 주입하라.

## 4. poster 봇 감지 회피 (agents/poster/main.py)

GCP 등 데이터센터 IP 에서 네이버 자동 로그인이 봇으로 차단되는 문제에 대한 스텔스 보강:

- `navigator.webdriver` 제거, `languages`/`plugins`/`chrome.runtime`/`permissions` 지문 위장 (init 스크립트).
- 실행 인자 `--disable-blink-features=AutomationControlled`, `--no-sandbox`, `--disable-dev-shm-usage`.
- 컨텍스트 `locale=ko-KR`, `timezone_id=Asia/Seoul`.
- 프록시 지원: `.env` 에 `POSTER_PROXY`(예: `http://host:port`), 필요 시 `POSTER_PROXY_USER`/`POSTER_PROXY_PASS`.

> ⚠️ 스텔스는 봇 탐지와의 지속적인 숨바꼭질이라 100% 보장되지 않는다.
> 데이터센터 IP 가 막히면 **주거용(residential) 프록시**를 `POSTER_PROXY` 로 지정하는 것이 가장 효과적이다.
> 그래도 막히면 `--manual-login` 으로 쿠키를 1회 확보(이제 암호화 저장됨)해 재사용한다.

## 추가된 환경변수 요약

```dotenv
# 인증
ADMIN_USER=admin
ADMIN_PASSWORD_HASH=          # (권장) werkzeug 해시. 설정 시 ADMIN_PASSWORD 불필요
SECRET_KEY=                   # 미설정 시 data/.flask_secret 자동 생성
FORCE_HTTPS=1                 # HTTPS(리버스 프록시) 운영 시

# 시크릿 암호화
COOKIE_ENCRYPTION_KEY=        # 미설정 시 data/.enc_key 자동 생성

# poster 스텔스/프록시
POSTER_PROXY=                 # http://host:port (권장: residential proxy)
POSTER_PROXY_USER=
POSTER_PROXY_PASS=
```
