import json
import urllib.error

from agents.analyzer import main as analyzer
from agents.analyzer.main import count_keywords


def test_count_keywords_counts_and_filters_stopwords():
    posts = [
        {"title": "마케팅 마케팅 AI", "summary": "마케팅 the and"},
    ]
    result = count_keywords(posts)
    # "마케팅"(한글 2+) 3회, "AI"(영문 2자)는 3자 미만이라 제외,
    # "the"/"and"는 불용어 제외
    assert result[0] == {"word": "마케팅", "count": 3}
    assert all(r["word"] not in {"the", "and"} for r in result)


def test_count_keywords_respects_top_n():
    posts = [{"title": "사과 바나나 포도", "summary": "딸기 수박"}]
    result = count_keywords(posts, top_n=2)
    assert len(result) == 2


def test_count_keywords_english_min_length():
    posts = [{"title": "AI ML data", "summary": ""}]
    words = {r["word"] for r in count_keywords(posts)}
    # 3자 이상 영문만: "data" 포함, "AI"/"ML"(2자)은 제외
    assert "data" in words
    assert "AI" not in words and "ML" not in words


def test_count_keywords_empty_posts():
    assert count_keywords([]) == []


# ── fetch_search_trends: 실패(degraded)와 빈 결과(정상) 구분 ──────────────
class _FakeResp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_fetch_search_trends_empty_keywords_is_ok():
    trends, ok = analyzer.fetch_search_trends([], "id", "sec")
    assert trends == []
    assert ok is True


def test_fetch_search_trends_success(monkeypatch):
    payload = {"results": [{"title": "AI", "data": [{"ratio": 10}, {"ratio": 20}]}]}
    monkeypatch.setattr(
        analyzer.urllib.request, "urlopen", lambda req: _FakeResp(payload)
    )
    trends, ok = analyzer.fetch_search_trends(["AI"], "id", "sec")
    assert ok is True
    assert trends[0]["keyword"] == "AI"
    assert trends[0]["trend"] == [10, 20]
    assert trends[0]["change_rate"] == "+100%"


def test_fetch_search_trends_http_error_is_degraded(monkeypatch):
    def boom(req):
        raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {}, None)

    monkeypatch.setattr(analyzer.urllib.request, "urlopen", boom)
    trends, ok = analyzer.fetch_search_trends(["AI"], "id", "sec")
    assert trends == []
    assert ok is False  # 실패는 빈 결과와 구분되어야 한다
