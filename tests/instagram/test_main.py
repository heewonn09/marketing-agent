from agents.instagram import main as instagram


class _FakeResp:
    def __init__(self, status_code, payload=None, headers=None):
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self._payload = payload or {}
        self.headers = headers or {}
        self.text = ""

    def json(self):
        return self._payload


def test_is_rate_limited_429():
    assert instagram._is_rate_limited(_FakeResp(429)) is True


def test_is_rate_limited_403_app_limit_code():
    r = _FakeResp(403, {"error": {"code": 4, "message": "Application request limit reached"}})
    assert instagram._is_rate_limited(r) is True


def test_is_rate_limited_403_other_is_false():
    r = _FakeResp(403, {"error": {"code": 190, "message": "Invalid token"}})
    assert instagram._is_rate_limited(r) is False


def test_is_rate_limited_success_false():
    assert instagram._is_rate_limited(_FakeResp(200, {"id": "1"})) is False


def test_graph_post_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def fake_post(url, data=None, timeout=30):
        calls["n"] += 1
        if calls["n"] == 1:
            return _FakeResp(429, {"error": {"code": 4}}, {"Retry-After": "1"})
        return _FakeResp(200, {"id": "ok"})

    monkeypatch.setattr(instagram.requests, "post", fake_post)
    monkeypatch.setattr(instagram.time, "sleep", lambda *_: None)
    res = instagram._graph_post("http://x", {"a": 1}, label="t")
    assert res.ok is True
    assert calls["n"] == 2  # 1회 재시도 후 성공


def test_graph_post_returns_last_when_exhausted(monkeypatch):
    monkeypatch.setattr(instagram, "IG_RETRY_MAX", 3)
    monkeypatch.setattr(instagram.requests, "post",
                        lambda url, data=None, timeout=30: _FakeResp(403, {"error": {"code": 4}}))
    monkeypatch.setattr(instagram.time, "sleep", lambda *_: None)
    res = instagram._graph_post("http://x", {"a": 1}, label="t")
    assert res.status_code == 403  # 소진 후 마지막 응답 반환


def test_build_caption_appends_hashtags():
    cap = instagram.build_caption({"caption": "본문", "hashtags": ["#a", "#b"]})
    assert cap == "본문\n\n#a #b"


def test_build_caption_without_hashtags():
    assert instagram.build_caption({"caption": "본문"}) == "본문"


def test_build_caption_empty():
    assert instagram.build_caption({}) == ""


def test_safe_keyword_replaces_special_chars():
    assert instagram._safe_keyword("a/b:c") == "a_b_c"
