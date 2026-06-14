"""
파이프라인 완료/오류 알림 — 이메일(Gmail SMTP) + 슬랙 Webhook
필요 환경변수:
  SMTP_USER         Gmail 주소 (예: you@gmail.com)
  SMTP_PASSWORD     Gmail 앱 비밀번호 16자 (구글 계정 → 앱 비밀번호)
  ALERT_EMAIL       수신 이메일 (SMTP_USER와 같아도 됨)
  SLACK_WEBHOOK_URL Slack Incoming Webhook URL (선택)
"""
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

try:
    import requests as _requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False


def _send_email(subject: str, body_html: str) -> bool:
    smtp_user = os.environ.get("SMTP_USER", "").strip()
    smtp_pass = os.environ.get("SMTP_PASSWORD", "").strip()
    to_addr   = os.environ.get("ALERT_EMAIL", "").strip() or smtp_user
    if not (smtp_user and smtp_pass and to_addr):
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = smtp_user
        msg["To"]      = to_addr
        msg.attach(MIMEText(body_html, "html", "utf-8"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as srv:
            srv.login(smtp_user, smtp_pass)
            srv.sendmail(smtp_user, to_addr, msg.as_string())
        return True
    except Exception as e:
        print(f"[notifier] 이메일 전송 실패: {e}")
        return False


def _send_slack(text: str) -> bool:
    webhook = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if not webhook or not _HAS_REQUESTS:
        return False
    try:
        res = _requests.post(webhook, json={"text": text}, timeout=10)
        return res.status_code == 200
    except Exception as e:
        print(f"[notifier] 슬랙 전송 실패: {e}")
        return False


def notify_done(keywords: list, report_date: str, base_url: str = "") -> None:
    kw_str     = ", ".join(keywords)
    report_url = f"{base_url}/download/{report_date}" if base_url else ""
    app_url    = f"{base_url}" if base_url else ""

    subject = f"[마케팅 에이전트] ✅ 완료: {kw_str} ({report_date})"

    body = f"""
<!DOCTYPE html>
<html lang="ko">
<body style="font-family:'Malgun Gothic',Arial,sans-serif;background:#f0f2f7;padding:24px">
<div style="max-width:520px;margin:0 auto;background:white;border-radius:14px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,.1)">
  <div style="background:linear-gradient(135deg,#667eea,#764ba2);padding:28px 32px;color:white">
    <div style="font-size:22px;font-weight:700;margin-bottom:4px">✅ 파이프라인 완료</div>
    <div style="font-size:13px;opacity:.8">마케팅 자동화 에이전트</div>
  </div>
  <div style="padding:28px 32px">
    <table style="width:100%;border-collapse:collapse">
      <tr><td style="padding:8px 0;color:#718096;font-size:13px;width:80px">키워드</td>
          <td style="padding:8px 0;font-weight:600;color:#2d3748">{kw_str}</td></tr>
      <tr><td style="padding:8px 0;color:#718096;font-size:13px">날짜</td>
          <td style="padding:8px 0;font-weight:600;color:#2d3748">{report_date}</td></tr>
    </table>
    <div style="margin-top:24px;display:flex;gap:10px;flex-wrap:wrap">
      {f'<a href="{report_url}" style="display:inline-block;padding:10px 22px;background:linear-gradient(135deg,#38a169,#2f855a);color:white;text-decoration:none;border-radius:8px;font-size:13px;font-weight:700">📄 PDF 리포트 다운로드</a>' if report_url else ''}
      {f'<a href="{app_url}" style="display:inline-block;padding:10px 22px;background:linear-gradient(135deg,#667eea,#764ba2);color:white;text-decoration:none;border-radius:8px;font-size:13px;font-weight:700">🚀 대시보드 보기</a>' if app_url else ''}
    </div>
  </div>
  <div style="padding:16px 32px;background:#f7fafc;font-size:11px;color:#a0aec0;text-align:center">
    마케팅 자동화 에이전트 · 자동 발송 메일입니다
  </div>
</div>
</body>
</html>"""

    slack_text = (
        f"✅ *마케팅 파이프라인 완료*\n"
        f"키워드: `{kw_str}`\n"
        f"날짜: {report_date}"
        + (f"\n<{report_url}|📄 PDF 리포트 다운로드>" if report_url else "")
        + (f"  |  <{app_url}|🚀 대시보드>" if app_url else "")
    )

    email_ok = _send_email(subject, body)
    slack_ok  = _send_slack(slack_text)
    print(f"[notifier] 완료 알림 — 이메일: {'✓' if email_ok else '✗'}, 슬랙: {'✓' if slack_ok else '✗ (미설정)'}")


def notify_error(keywords: list, step: str, detail: str = "") -> None:
    kw_str = ", ".join(keywords)
    base_url = os.environ.get("CARDNEWS_BASE_URL", "")

    subject = f"[마케팅 에이전트] ❌ 오류: {kw_str} — {step}"

    body = f"""
<!DOCTYPE html>
<html lang="ko">
<body style="font-family:'Malgun Gothic',Arial,sans-serif;background:#f0f2f7;padding:24px">
<div style="max-width:520px;margin:0 auto;background:white;border-radius:14px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,.1)">
  <div style="background:linear-gradient(135deg,#e53e3e,#c53030);padding:28px 32px;color:white">
    <div style="font-size:22px;font-weight:700;margin-bottom:4px">❌ 파이프라인 오류</div>
    <div style="font-size:13px;opacity:.8">마케팅 자동화 에이전트</div>
  </div>
  <div style="padding:28px 32px">
    <table style="width:100%;border-collapse:collapse">
      <tr><td style="padding:8px 0;color:#718096;font-size:13px;width:80px">키워드</td>
          <td style="padding:8px 0;font-weight:600;color:#2d3748">{kw_str}</td></tr>
      <tr><td style="padding:8px 0;color:#718096;font-size:13px">실패 스텝</td>
          <td style="padding:8px 0;font-weight:600;color:#c53030">{step}</td></tr>
      {f'<tr><td style="padding:8px 0;color:#718096;font-size:13px;vertical-align:top">오류</td><td style="padding:8px 0;font-size:12px;color:#4a5568;background:#fff5f5;border-radius:6px;padding:8px 10px;word-break:break-all">{detail}</td></tr>' if detail else ''}
    </table>
    {f'<div style="margin-top:20px"><a href="{base_url}" style="display:inline-block;padding:10px 22px;background:linear-gradient(135deg,#667eea,#764ba2);color:white;text-decoration:none;border-radius:8px;font-size:13px;font-weight:700">🚀 대시보드에서 재실행</a></div>' if base_url else ''}
  </div>
  <div style="padding:16px 32px;background:#f7fafc;font-size:11px;color:#a0aec0;text-align:center">
    마케팅 자동화 에이전트 · 자동 발송 메일입니다
  </div>
</div>
</body>
</html>"""

    slack_text = (
        f"❌ *마케팅 파이프라인 오류*\n"
        f"키워드: `{kw_str}`\n"
        f"실패 스텝: `{step}`"
        + (f"\n오류: {detail[:200]}" if detail else "")
        + (f"\n<{base_url}|🚀 대시보드에서 재실행>" if base_url else "")
    )

    email_ok = _send_email(subject, body)
    slack_ok  = _send_slack(slack_text)
    print(f"[notifier] 오류 알림 — 이메일: {'✓' if email_ok else '✗'}, 슬랙: {'✓' if slack_ok else '✗ (미설정)'}")
