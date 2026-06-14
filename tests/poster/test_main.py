from agents.poster import main as poster


def test_inline_md_bold_and_italic():
    assert poster._inline_md("**굵게** 그리고 *기울임*") == (
        "<strong>굵게</strong> 그리고 <em>기울임</em>"
    )


def test_md_to_html_headings_and_paragraph():
    html = poster._md_to_html("# 제목\n## 소제목\n### 소소제목\n본문")
    assert "<h1>제목</h1>" in html
    assert "<h2>소제목</h2>" in html
    assert "<h3>소소제목</h3>" in html
    assert "<p>본문</p>" in html


def test_md_to_html_blank_line_becomes_br():
    assert "<br>" in poster._md_to_html("a\n\nb")


def test_proxy_config_none_without_env(monkeypatch):
    monkeypatch.delenv("POSTER_PROXY", raising=False)
    assert poster._proxy_config() is None


def test_proxy_config_with_credentials(monkeypatch):
    monkeypatch.setenv("POSTER_PROXY", "http://h:1")
    monkeypatch.setenv("POSTER_PROXY_USER", "u")
    monkeypatch.setenv("POSTER_PROXY_PASS", "p")
    assert poster._proxy_config() == {
        "server": "http://h:1", "username": "u", "password": "p"
    }


def test_launch_kwargs_has_stealth_args():
    kw = poster._launch_kwargs(True)
    assert kw["headless"] is True
    assert "--disable-blink-features=AutomationControlled" in kw["args"]
