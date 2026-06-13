# Sales Automation Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 소규모 마케팅 대행사를 자동으로 탐색해 이메일 리드를 수집하고, 샘플 리포트를 첨부한 개인화 영업 이메일을 자동 발송하는 에이전트 구축.

**Architecture:** DuckDuckGo 검색으로 한국 마케팅 대행사 URL을 수집한 뒤 페이지를 크롤링해 이메일을 추출, `data/sales_leads.json`에 저장한다. 발송은 `utils/email_sender.py` Gmail SMTP 유틸을 통해 처리하며 `data/sales_sent.json`으로 중복을 방지한다.

**Tech Stack:** Python 3.11, duckduckgo-search, requests, smtplib (stdlib), python-dotenv, pytest + unittest.mock

---

## File Map

| 경로 | 역할 |
|------|------|
| `agents/sales/__init__.py` | 패키지 마커 (빈 파일) |
| `agents/sales/main.py` | CLI 진입점 + 탐색/발송 오케스트레이션 |
| `utils/__init__.py` | 패키지 마커 (빈 파일) |
| `utils/email_sender.py` | Gmail SMTP 유틸 (첨부 파일 지원) |
| `tests/sales/__init__.py` | 테스트 패키지 마커 |
| `tests/sales/test_leads.py` | 리드 탐색 로직 단위 테스트 |
| `tests/sales/test_email.py` | 이메일 유틸 단위 테스트 |
| `data/sales_leads.json` | 수집된 리드 (런타임 생성) |
| `data/sales_sent.json` | 발송 기록 (런타임 생성) |
| `requirements.txt` | duckduckgo-search 추가 |

---

## Task 1: duckduckgo-search 패키지 추가

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: requirements.txt에 패키지 추가**

```
duckduckgo-search>=6.0.0
```

`requirements.txt` 파일의 마지막 줄에 추가한다.

- [ ] **Step 2: 가상환경에 설치**

```bash
./venv/bin/pip install duckduckgo-search
```

Expected output: `Successfully installed duckduckgo-search-...`

- [ ] **Step 3: 설치 확인**

```bash
./venv/bin/python -c "from duckduckgo_search import DDGS; print('ok')"
```

Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "chore: add duckduckgo-search dependency for sales agent"
```

---

## Task 2: utils/email_sender.py 생성 (테스트 선작성)

**Files:**
- Create: `utils/__init__.py`
- Create: `utils/email_sender.py`
- Create: `tests/sales/__init__.py`
- Create: `tests/sales/test_email.py`

- [ ] **Step 1: 패키지 마커 생성**

`utils/__init__.py` — 빈 파일.
`tests/sales/__init__.py` — 빈 파일.

- [ ] **Step 2: 실패 테스트 작성**

`tests/sales/test_email.py`:

```python
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, call


def test_send_email_raises_when_env_missing():
    from utils.email_sender import send_email

    env = {k: v for k, v in os.environ.items() if k not in ("GMAIL_USER", "GMAIL_APP_PASSWORD")}
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(EnvironmentError, match="GMAIL_USER"):
            send_email(to="a@b.com", subject="s", body="b")


def test_send_email_calls_smtp(tmp_path):
    from utils.email_sender import send_email

    env = {"GMAIL_USER": "sender@gmail.com", "GMAIL_APP_PASSWORD": "secret"}
    with patch.dict(os.environ, env):
        with patch("smtplib.SMTP_SSL") as mock_ssl:
            mock_server = MagicMock()
            mock_ssl.return_value.__enter__ = lambda s: mock_server
            mock_ssl.return_value.__exit__ = MagicMock(return_value=False)

            send_email(to="target@example.kr", subject="테스트", body="안녕하세요")

            mock_ssl.assert_called_once_with("smtp.gmail.com", 465)
            mock_server.login.assert_called_once_with("sender@gmail.com", "secret")
            mock_server.send_message.assert_called_once()


def test_send_email_attaches_pdf(tmp_path):
    from utils.email_sender import send_email

    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")

    env = {"GMAIL_USER": "sender@gmail.com", "GMAIL_APP_PASSWORD": "secret"}
    with patch.dict(os.environ, env):
        with patch("smtplib.SMTP_SSL") as mock_ssl:
            mock_server = MagicMock()
            mock_ssl.return_value.__enter__ = lambda s: mock_server
            mock_ssl.return_value.__exit__ = MagicMock(return_value=False)

            send_email(to="a@b.kr", subject="s", body="b", attachment_path=pdf)

            msg_arg = mock_server.send_message.call_args[0][0]
            payloads = msg_arg.get_payload()
            assert len(payloads) == 2  # 본문 + 첨부
            assert payloads[1].get_filename() == "report.pdf"
```

- [ ] **Step 3: 테스트 실행 — 실패 확인**

```bash
./venv/bin/pytest tests/sales/test_email.py -v
```

Expected: `ImportError` 또는 `ModuleNotFoundError` (utils.email_sender 없음)

- [ ] **Step 4: utils/email_sender.py 구현**

```python
import os
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path


def send_email(
    to: str,
    subject: str,
    body: str,
    attachment_path: Path | None = None,
) -> None:
    user = os.environ.get("GMAIL_USER")
    password = os.environ.get("GMAIL_APP_PASSWORD")
    if not user or not password:
        raise EnvironmentError("GMAIL_USER / GMAIL_APP_PASSWORD가 .env에 없습니다.")

    msg = MIMEMultipart()
    msg["From"] = user
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    if attachment_path and Path(attachment_path).exists():
        with open(attachment_path, "rb") as f:
            part = MIMEApplication(f.read(), Name=Path(attachment_path).name)
        part["Content-Disposition"] = f'attachment; filename="{Path(attachment_path).name}"'
        msg.attach(part)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(user, password)
        server.send_message(msg)
```

- [ ] **Step 5: 테스트 실행 — 통과 확인**

```bash
./venv/bin/pytest tests/sales/test_email.py -v
```

Expected: `3 passed`

- [ ] **Step 6: Commit**

```bash
git add utils/__init__.py utils/email_sender.py tests/sales/__init__.py tests/sales/test_email.py
git commit -m "feat: add Gmail SMTP utility with attachment support"
```

---

## Task 3: 리드 탐색 로직 (테스트 선작성)

**Files:**
- Create: `agents/sales/__init__.py`
- Create: `agents/sales/main.py` (탐색 함수만, CLI 미포함)
- Create: `tests/sales/test_leads.py`

- [ ] **Step 1: 실패 테스트 작성**

`tests/sales/test_leads.py`:

```python
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


FAKE_DDG_RESULTS = [
    {
        "title": "디지털마케팅랩 - 소규모 마케팅 대행사",
        "href": "https://digitalmarketinglab.kr",
        "body": "문의: contact@digitalmarketinglab.kr | 서울 강남구",
    },
    {
        "title": "마케팅플러스",
        "href": "https://marketingplus.co.kr",
        "body": "info@marketingplus.co.kr 010-1234-5678",
    },
]

FAKE_PAGE_HTML = """
<html><body>
이메일: sales@example.kr 또는 support@example.co.kr로 문의하세요.
</body></html>
"""


def test_search_leads_returns_list():
    from agents.sales.main import search_leads

    mock_ddgs = MagicMock()
    mock_ddgs.__enter__ = lambda s: mock_ddgs
    mock_ddgs.__exit__ = MagicMock(return_value=False)
    mock_ddgs.text.return_value = iter(FAKE_DDG_RESULTS)

    with patch("agents.sales.main.DDGS", return_value=mock_ddgs):
        results = search_leads(["마케팅 대행사 이메일 site:kr"], max_results=5)

    assert isinstance(results, list)
    assert len(results) == 2
    assert results[0]["website"] == "https://digitalmarketinglab.kr"
    assert results[0]["name"] == "디지털마케팅랩 - 소규모 마케팅 대행사"


def test_extract_emails_from_snippet():
    from agents.sales.main import extract_emails_from_text

    text = "문의: contact@digitalmarketinglab.kr | 서울 강남구"
    emails = extract_emails_from_text(text)
    assert emails == ["contact@digitalmarketinglab.kr"]


def test_extract_emails_from_text_returns_empty_for_no_email():
    from agents.sales.main import extract_emails_from_text

    assert extract_emails_from_text("이메일 없는 텍스트") == []


def test_extract_emails_from_page(tmp_path):
    from agents.sales.main import extract_emails_from_url

    with patch("agents.sales.main.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.text = FAKE_PAGE_HTML
        mock_get.return_value = mock_resp

        emails = extract_emails_from_url("https://example.kr")

    assert "sales@example.kr" in emails
    assert "support@example.co.kr" in emails


def test_extract_emails_from_url_returns_empty_on_error():
    from agents.sales.main import extract_emails_from_url

    with patch("agents.sales.main.requests.get", side_effect=Exception("timeout")):
        result = extract_emails_from_url("https://bad-url.kr")

    assert result == []


def test_build_leads_deduplicates_emails():
    from agents.sales.main import build_leads

    raw = [
        {"name": "A사", "website": "https://a.kr", "snippet": "info@a.kr"},
        {"name": "A사 복사본", "website": "https://a.kr", "snippet": "info@a.kr"},
    ]

    with patch("agents.sales.main.extract_emails_from_url", return_value=["info@a.kr"]):
        leads = build_leads(raw)

    emails = [l["email"] for l in leads]
    assert emails.count("info@a.kr") == 1


def test_save_and_load_leads(tmp_path):
    from agents.sales.main import save_leads, load_leads

    leads = [{"name": "테스트사", "email": "test@test.kr", "website": "https://test.kr"}]
    path = tmp_path / "leads.json"
    save_leads(leads, path)

    loaded = load_leads(path)
    assert loaded == leads
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
./venv/bin/pytest tests/sales/test_leads.py -v
```

Expected: `ImportError` (agents.sales.main 없음)

- [ ] **Step 3: agents/sales/__init__.py 생성 (빈 파일)**

- [ ] **Step 4: agents/sales/main.py — 탐색 함수 구현**

```python
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import requests
from duckduckgo_search import DDGS
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT / "data"

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_SKIP_DOMAINS = {"example.com", "sentry.io", "wix.com", "wordpress.com",
                 "naver.com", "kakao.com", "gmail.com", "nate.com"}

SEARCH_QUERIES = [
    "소규모 마케팅 대행사 이메일 contact",
    "마케팅 대행사 문의 이메일 site:.kr",
    "디지털마케팅 대행사 이메일 소규모",
    "콘텐츠 마케팅 대행사 이메일 직원 10인",
]


def extract_emails_from_text(text: str) -> list[str]:
    found = _EMAIL_RE.findall(text)
    return [e for e in found if e.split("@")[-1] not in _SKIP_DOMAINS]


def extract_emails_from_url(url: str, timeout: int = 6) -> list[str]:
    try:
        resp = requests.get(
            url, timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (compatible; SalesBot/1.0)"},
        )
        return list(set(extract_emails_from_text(resp.text)))
    except Exception:
        return []


def search_leads(queries: list[str], max_results: int = 10) -> list[dict]:
    raw: list[dict] = []
    with DDGS() as ddgs:
        for query in queries:
            for r in ddgs.text(query, region="kr-kr", max_results=max_results):
                raw.append({
                    "name": r.get("title", "").split(" - ")[0].strip(),
                    "website": r.get("href", ""),
                    "snippet": r.get("body", ""),
                })
    return raw


def build_leads(raw: list[dict]) -> list[dict]:
    seen_emails: set[str] = set()
    leads: list[dict] = []

    for item in raw:
        emails = extract_emails_from_text(item["snippet"])
        if not emails:
            emails = extract_emails_from_url(item["website"])

        for email in emails:
            if email in seen_emails:
                continue
            seen_emails.add(email)
            leads.append({
                "name": item["name"],
                "email": email,
                "website": item["website"],
                "found_at": datetime.now().isoformat(),
            })

    return leads


def save_leads(leads: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(leads, f, ensure_ascii=False, indent=2)


def load_leads(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)
```

(CLI의 `main()` 함수는 Task 5에서 추가)

- [ ] **Step 5: 테스트 실행 — 통과 확인**

```bash
./venv/bin/pytest tests/sales/test_leads.py -v
```

Expected: `7 passed`

- [ ] **Step 6: Commit**

```bash
git add agents/sales/__init__.py agents/sales/main.py tests/sales/test_leads.py
git commit -m "feat(sales): lead search and email extraction logic"
```

---

## Task 4: 발송 로직 + 발송 기록 관리

**Files:**
- Modify: `agents/sales/main.py` (발송 관련 함수 추가)
- Modify: `tests/sales/test_email.py` (발송 기록 테스트 추가)

- [ ] **Step 1: 발송 기록 테스트 추가**

`tests/sales/test_email.py` 파일 끝에 추가:

```python
def test_load_sent_returns_empty_when_missing(tmp_path):
    from agents.sales.main import load_sent

    result = load_sent(tmp_path / "missing.json")
    assert result == set()


def test_mark_sent_persists(tmp_path):
    from agents.sales.main import load_sent, mark_sent

    path = tmp_path / "sent.json"
    mark_sent("a@b.kr", path)
    mark_sent("c@d.kr", path)

    loaded = load_sent(path)
    assert "a@b.kr" in loaded
    assert "c@d.kr" in loaded


def test_build_email_body_contains_company_name():
    from agents.sales.main import build_email_body

    body = build_email_body("테스트마케팅")
    assert "테스트마케팅" in body


def test_find_latest_report_returns_none_when_empty(tmp_path):
    from agents.sales.main import find_latest_report

    result = find_latest_report(tmp_path)
    assert result is None


def test_find_latest_report_returns_latest(tmp_path):
    from agents.sales.main import find_latest_report

    (tmp_path / "report_2026-06-01.pdf").write_bytes(b"pdf1")
    (tmp_path / "report_2026-06-10.pdf").write_bytes(b"pdf2")

    result = find_latest_report(tmp_path)
    assert result is not None
    assert "2026-06-10" in result.name
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
./venv/bin/pytest tests/sales/test_email.py -v
```

Expected: `ImportError` 또는 `AttributeError` (함수 미구현)

- [ ] **Step 3: agents/sales/main.py에 발송 관련 함수 추가**

파일의 `load_leads()` 함수 아래에 추가:

```python
SENT_PATH = DATA_DIR / "sales_sent.json"
LEADS_PATH = DATA_DIR / "sales_leads.json"


def load_sent(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with open(path, encoding="utf-8") as f:
        return set(json.load(f))


def mark_sent(email: str, path: Path) -> None:
    sent = load_sent(path)
    sent.add(email)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sorted(sent), f, ensure_ascii=False, indent=2)


def build_email_body(company_name: str) -> str:
    return f"""안녕하세요, {company_name} 담당자님.

저희는 매주 네이버 실시간 데이터를 기반으로 마케팅 트렌드 리포트를 자동 생성하는 auto.markai 팀입니다.

소규모 마케팅 대행사를 위한 주간 리포트 샘플을 첨부해 드립니다.
실시간 트렌드 키워드, 콘텐츠 퍼포먼스 예측, 다음 주 공략 키워드 등을 포함하고 있습니다.

관심 있으시면 편하게 회신 주시면 감사하겠습니다.

---
auto.markai | 마케팅 인사이트 자동화
"""


def find_latest_report(output_dir: Path) -> Path | None:
    pdfs = sorted(output_dir.glob("report_*.pdf"), reverse=True)
    return pdfs[0] if pdfs else None
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

```bash
./venv/bin/pytest tests/sales/test_email.py -v
```

Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add agents/sales/main.py tests/sales/test_email.py
git commit -m "feat(sales): add sent-record management and email body builder"
```

---

## Task 5: CLI main() 함수 + .env 항목 문서화

**Files:**
- Modify: `agents/sales/main.py` (main() 추가)
- Modify: `.env` (GMAIL 항목 추가 — 플레이스홀더)

- [ ] **Step 1: .env에 Gmail 플레이스홀더 추가**

`.env` 파일 끝에 추가 (실제 값은 사용자가 직접 입력):

```
# 영업 이메일 발송용 Gmail 계정
GMAIL_USER=your_gmail@gmail.com
GMAIL_APP_PASSWORD=your_app_password_here
```

> **주의:** Gmail 앱 비밀번호는 Google 계정 → 보안 → 2단계 인증 → 앱 비밀번호에서 생성.

- [ ] **Step 2: agents/sales/main.py에 main() 추가**

파일 끝에 추가:

```python
def _run_search() -> list[dict]:
    print(f"[sales] 리드 탐색 시작 ({len(SEARCH_QUERIES)}개 쿼리)...")
    raw = search_leads(SEARCH_QUERIES, max_results=8)
    print(f"[sales] 원시 결과: {len(raw)}건 → 이메일 추출 중...")
    leads = build_leads(raw)
    save_leads(leads, LEADS_PATH)
    print(f"[sales] 리드 저장 완료: {len(leads)}건 → {LEADS_PATH}")
    for l in leads:
        print(f"  {l['name']} | {l['email']} | {l['website']}")
    return leads


def _run_send() -> None:
    from utils.email_sender import send_email

    leads = load_leads(LEADS_PATH)
    if not leads:
        print("[sales] 리드 없음. --search 먼저 실행하세요.", file=sys.stderr)
        return

    report = find_latest_report(ROOT / "output")
    if not report:
        print("[sales] output/report_*.pdf 파일 없음. reporter 에이전트를 먼저 실행하세요.", file=sys.stderr)
        return

    sent = load_sent(SENT_PATH)
    sent_count = 0

    for lead in leads:
        email = lead["email"]
        if email in sent:
            print(f"[sales] 건너뜀 (이미 발송): {email}")
            continue

        subject = f"[auto.markai] {lead['name']} 마케팅 트렌드 리포트 샘플 드립니다"
        body = build_email_body(lead["name"])

        try:
            send_email(to=email, subject=subject, body=body, attachment_path=report)
            mark_sent(email, SENT_PATH)
            print(f"[sales] 발송 완료: {email}")
            sent_count += 1
        except Exception as e:
            print(f"[sales] 발송 실패 ({email}): {e}", file=sys.stderr)

    print(f"[sales] 발송 완료: {sent_count}건 / 전체 {len(leads)}건")


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="영업 자동화 에이전트")
    parser.add_argument("--search", action="store_true", help="잠재 고객 탐색")
    parser.add_argument("--send", action="store_true", help="영업 이메일 발송")
    args = parser.parse_args()

    if not args.search and not args.send:
        parser.print_help()
        sys.exit(0)

    if args.search:
        _run_search()

    if args.send:
        _run_send()


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: 전체 테스트 실행**

```bash
./venv/bin/pytest tests/sales/ -v
```

Expected: `15 passed`

- [ ] **Step 4: Commit**

```bash
git add agents/sales/main.py .env
git commit -m "feat(sales): add CLI entry point with --search and --send flags"
```

---

## Task 6: 탐색 테스트 실행

> 이 Task는 실제 DuckDuckGo 요청을 보내는 통합 테스트다. 인터넷 연결이 필요하다.

**Files:** 없음 (실행만)

- [ ] **Step 1: --search 실행**

```bash
./venv/bin/python agents/sales/main.py --search
```

Expected 출력:
```
[sales] 리드 탐색 시작 (4개 쿼리)...
[sales] 원시 결과: N건 → 이메일 추출 중...
[sales] 리드 저장 완료: M건 → .../data/sales_leads.json
  업체명 | contact@example.kr | https://example.kr
  ...
```

- [ ] **Step 2: 저장 파일 확인**

```bash
cat data/sales_leads.json | head -40
```

Expected: 업체명, 이메일, 웹사이트, 타임스탬프가 담긴 JSON 배열.

- [ ] **Step 3: 결과 검토 후 이메일 발송 여부 사용자 확인**

결과를 확인하고 이상 없으면 `--send` 플래그로 발송.

---

## Task 7: Deploy

- [ ] **Step 1: push 및 VM 배포**

```bash
git push origin main
bash deploy.sh
```

Expected: VM 서비스 `active (running)` 확인.
