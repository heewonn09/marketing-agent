import json

import pytest

from agents.collector import main as collector


class _FakeResp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_fetch_page_strips_html_and_skips_linkless(monkeypatch):
    payload = {
        "items": [
            {"title": "<b>제목</b>", "link": "http://a", "description": "<p>요약</p>"},
            {"title": "링크없음", "link": "", "description": "무시"},
        ]
    }
    monkeypatch.setattr(
        collector.urllib.request, "urlopen", lambda req: _FakeResp(payload)
    )
    results = collector._fetch_page("kw", 1, "id", "sec")
    assert len(results) == 1
    item = results[0]
    assert item["title"] == "제목"
    assert item["summary"] == "요약"
    assert item["link"] == "http://a"
    assert "collected_at" in item


def test_collect_naver_blog_raises_without_env(monkeypatch):
    monkeypatch.delenv("NAVER_CLIENT_ID", raising=False)
    monkeypatch.delenv("NAVER_CLIENT_SECRET", raising=False)
    with pytest.raises(EnvironmentError):
        collector.collect_naver_blog("kw")


def test_collect_naver_blog_deduplicates_by_link(monkeypatch):
    monkeypatch.setenv("NAVER_CLIENT_ID", "id")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "sec")
    # 모든 페이지가 동일 link 를 반환 → dedup 후 1개만 남아야 한다
    dup = [{"title": "t", "link": "http://dup", "summary": "s", "collected_at": "x"}]
    monkeypatch.setattr(collector, "_fetch_page", lambda *a, **k: list(dup))
    results = collector.collect_naver_blog("kw", target=30)
    assert len(results) == 1
    assert results[0]["link"] == "http://dup"


def test_collect_naver_blog_respects_target(monkeypatch):
    monkeypatch.setenv("NAVER_CLIENT_ID", "id")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "sec")

    def fake_fetch(keyword, start, cid, csec):
        # 한 페이지가 target 보다 많은 고유 항목(5개)을 반환
        return [
            {"title": "t", "link": f"http://{i}", "summary": "s", "collected_at": "x"}
            for i in range(5)
        ]

    monkeypatch.setattr(collector, "_fetch_page", fake_fetch)
    results = collector.collect_naver_blog("kw", target=3)
    assert len(results) == 3  # target 에서 정확히 끊겨야 함
