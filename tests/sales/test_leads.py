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
