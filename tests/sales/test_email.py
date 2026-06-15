import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


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

# ── #6 콜드메일 법적 보강 ────────────────────────────────────────────────
def test_email_body_has_unsubscribe_notice():
    from agents.sales.main import build_email_body
    body = build_email_body("테스트회사")
    assert "수신거부" in body
    assert "광고성 정보" in body


def test_run_send_blocked_without_sales_enabled(monkeypatch):
    from agents.sales import main as sales
    import utils.email_sender as es
    monkeypatch.setattr(sales, "_out", lambda *a, **k: None)
    monkeypatch.delenv("SALES_ENABLED", raising=False)
    monkeypatch.setattr(sales, "load_leads",
                        lambda p: [{"name": "A", "email": "a@b.com", "website": "x"}])
    monkeypatch.setattr(sales, "find_latest_report", lambda d: Path("dummy.pdf"))
    calls = {"n": 0}
    monkeypatch.setattr(es, "send_email", lambda **k: calls.__setitem__("n", calls["n"] + 1))
    sales._run_send(dry_run=False)
    assert calls["n"] == 0  # SALES_ENABLED 없으면 발송 안 함


def test_run_send_allows_with_sales_enabled(monkeypatch):
    from agents.sales import main as sales
    import utils.email_sender as es
    monkeypatch.setattr(sales, "_out", lambda *a, **k: None)
    monkeypatch.setenv("SALES_ENABLED", "1")
    monkeypatch.setattr(sales, "load_leads",
                        lambda p: [{"name": "A", "email": "a@b.com", "website": "x"}])
    monkeypatch.setattr(sales, "find_latest_report", lambda d: Path("dummy.pdf"))
    monkeypatch.setattr(sales, "load_sent", lambda p: set())
    monkeypatch.setattr(sales, "mark_sent", lambda e, p: None)
    calls = {"n": 0}
    monkeypatch.setattr(es, "send_email", lambda **k: calls.__setitem__("n", calls["n"] + 1))
    sales._run_send(dry_run=False)
    assert calls["n"] == 1  # 옵트인 시 발송
