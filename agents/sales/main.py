import json
import os
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

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_SKIP_EMAIL_DOMAINS = {
    "example.com", "sentry.io", "wix.com", "wordpress.com",
    "naver.com", "kakao.com", "gmail.com", "nate.com",
    "wordnik.com", "wordnik.social", "namu.wiki",
    "cambridge.org", "wikipedia.org",
}
_SKIP_NAME_PATTERNS = re.compile(r"\.(png|jpg|jpeg|gif|svg|webp|ico)$", re.I)

SEARCH_QUERIES = [
    "마케팅 대행사 이메일 문의 서울 site:kr",
    "디지털 마케팅 대행사 contact email site:co.kr",
    "광고 대행사 소규모 이메일 한국 문의",
    "콘텐츠 마케팅 에이전시 이메일 담당자 site:kr",
]

LEADS_PATH = DATA_DIR / "sales_leads.json"
SENT_PATH = DATA_DIR / "sales_sent.json"


def _out(msg: str) -> None:
    sys.stdout.buffer.write((msg + "\n").encode("utf-8", errors="replace"))
    sys.stdout.buffer.flush()


def _is_kr_site(url: str) -> bool:
    from urllib.parse import urlparse
    host = urlparse(url).hostname or ""
    return host.endswith(".kr")


def extract_emails_from_text(text: str) -> list[str]:
    found = _EMAIL_RE.findall(text)
    return [e for e in found if e.split("@")[-1] not in _SKIP_EMAIL_DOMAINS]


def extract_emails_from_url(url: str, timeout: int = 6) -> list[str]:
    try:
        resp = requests.get(
            url,
            timeout=timeout,
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
                    "name": r.get("title", "").strip(),
                    "website": r.get("href", ""),
                    "snippet": r.get("body", ""),
                })
    return raw


def build_leads(raw: list[dict]) -> list[dict]:
    seen_emails: set[str] = set()
    leads: list[dict] = []

    for item in raw:
        if _SKIP_NAME_PATTERNS.search(item["name"]):
            continue
        if not _is_kr_site(item["website"]):
            continue

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
※ 본 메일은 영리목적 광고성 정보입니다. 수신을 원치 않으시면 본 메일에 '수신거부'로 회신해 주시면 즉시 발송을 중단합니다.
"""


def find_latest_report(output_dir: Path) -> Path | None:
    pdfs = sorted(output_dir.glob("report_*.pdf"), reverse=True)
    return pdfs[0] if pdfs else None


def _run_search() -> list[dict]:
    _out(f"[sales] 리드 탐색 시작 ({len(SEARCH_QUERIES)}개 쿼리)...")
    raw = search_leads(SEARCH_QUERIES, max_results=8)
    _out(f"[sales] 원시 결과: {len(raw)}건 → 이메일 추출 중...")
    leads = build_leads(raw)
    save_leads(leads, LEADS_PATH)
    _out(f"[sales] 리드 저장 완료: {len(leads)}건 → {str(LEADS_PATH)}")
    for lead in leads:
        _out(f"  {lead['name']} | {lead['email']} | {lead['website']}")
    return leads


def _run_send(dry_run: bool = False) -> None:
    from utils.email_sender import send_email

    leads = load_leads(LEADS_PATH)
    if not leads:
        _out("[sales] 리드 없음. --search 먼저 실행하세요.")
        return

    report = find_latest_report(ROOT / "output")
    if not report:
        _out("[sales] output/report_*.pdf 파일 없음. reporter 에이전트를 먼저 실행하세요.")
        return

    # 실제 발송은 명시적 옵트인 필요 — 무동의 콜드메일은 정보통신망법 위반 소지
    if not dry_run and os.environ.get("SALES_ENABLED", "") != "1":
        _out("[sales] 실제 발송 비활성화됨 (SALES_ENABLED!=1).")
        _out("        콜드메일은 사전 동의 없이 발송 시 정보통신망법 위반 소지가 있습니다.")
        _out("        내용 확인은 --dry-run 으로, 발송 책임을 인지한 경우에만 SALES_ENABLED=1 설정.")
        return

    sent = load_sent(SENT_PATH)
    sent_count = 0

    for i, lead in enumerate(leads, 1):
        email = lead["email"]
        subject = f"(광고) [auto.markai] {lead['name']} 마케팅 트렌드 리포트 샘플 드립니다"
        body = build_email_body(lead["name"])

        if dry_run:
            _out(f"\n{'='*60}")
            _out(f"[{i}/{len(leads)}] DRY-RUN — 실제 발송 안 함")
            _out(f"  To     : {email}")
            _out(f"  Subject: {subject}")
            _out(f"  Report : {report.name}")
            _out(f"  Body:\n{body}")
            continue

        if email in sent:
            _out(f"[sales] 건너뜀 (이미 발송): {email}")
            continue

        try:
            send_email(to=email, subject=subject, body=body, attachment_path=report)
            mark_sent(email, SENT_PATH)
            _out(f"[sales] 발송 완료: {email}")
            sent_count += 1
        except Exception as e:
            _out(f"[sales] 발송 실패 ({email}): {e}")

    if dry_run:
        _out(f"\n{'='*60}")
        _out(f"[DRY-RUN] 총 {len(leads)}건 미리보기 완료. 실제 발송하려면 --dry-run 없이 실행하세요.")
    else:
        _out(f"[sales] 발송 완료: {sent_count}건 / 전체 {len(leads)}건")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="영업 자동화 에이전트")
    parser.add_argument("--search", action="store_true", help="잠재 고객 탐색")
    parser.add_argument("--send", action="store_true", help="영업 이메일 발송")
    parser.add_argument("--dry-run", action="store_true", help="이메일 내용 미리보기 (실제 발송 안 함)")
    args = parser.parse_args()

    if not args.search and not args.send:
        parser.print_help()
        sys.exit(0)

    if args.search:
        _run_search()

    if args.send:
        _run_send(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
