import json
import os
import sys
import urllib.request
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _send_email(to: str, subject: str, body: str) -> None:
    from utils.email_sender import send_email
    send_email(to=to, subject=subject, body=body)


def send_alert(subject: str, body: str) -> None:
    """설정된 채널(Gmail, Slack)로 알림 발송. 둘 다 미설정이면 콘솔 출력."""
    sent = False

    alert_email = os.environ.get("ALERT_EMAIL", "").strip()
    if alert_email:
        try:
            _send_email(to=alert_email, subject=subject, body=body)
            print(f"[alert] 이메일 발송 완료 → {alert_email}")
            sent = True
        except Exception as e:
            print(f"[alert] 이메일 발송 실패: {e}", file=sys.stderr)

    slack_url = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if slack_url:
        try:
            payload = json.dumps({"text": f"*{subject}*\n{body}"}).encode()
            req = urllib.request.Request(
                slack_url, data=payload,
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=5)
            print("[alert] Slack 발송 완료")
            sent = True
        except Exception as e:
            print(f"[alert] Slack 발송 실패: {e}", file=sys.stderr)

    if not sent:
        print(
            f"[alert] ALERT_EMAIL / SLACK_WEBHOOK_URL 미설정 — 콘솔 출력만\n"
            f"  제목: {subject}\n  내용: {body}"
        )
