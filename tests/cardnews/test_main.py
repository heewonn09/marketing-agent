"""cardnews (Gemini Imagen 3 기반 홍보 이미지 생성기) 테스트.

기존 Pillow 카드 디자인은 b56e8d7에서 Imagen 3 구현으로 교체됨.
현재 순수/모킹 가능한 함수: _safe_keyword, _generate_prompts, _generate_image.
"""
from agents.cardnews import main as cardnews


# ── 가짜 Gemini 클라이언트 ────────────────────────────────────────────────
class _FakeResp:
    def __init__(self, text):
        self.text = text


class _FakeModels:
    def __init__(self, text):
        self._text = text

    def generate_content(self, **kw):
        return _FakeResp(self._text)


class _FakeClient:
    def __init__(self, text):
        self.models = _FakeModels(text)


def _patch_client(monkeypatch, text):
    monkeypatch.setattr(cardnews, "_client", lambda: _FakeClient(text))


# ── _safe_keyword ─────────────────────────────────────────────────────────
def test_safe_keyword_replaces_special_chars():
    assert cardnews._safe_keyword('a/b:c*d?e') == "a_b_c_d_e"


# ── _generate_prompts ─────────────────────────────────────────────────────
def test_generate_prompts_parses_json_array(monkeypatch):
    _patch_client(monkeypatch, '["p1", "p2", "p3", "p4"]')
    out = cardnews._generate_prompts({}, "AI 마케팅")
    assert out == ["p1", "p2", "p3", "p4"]


def test_generate_prompts_pads_to_four(monkeypatch):
    _patch_client(monkeypatch, '["only one"]')
    out = cardnews._generate_prompts({}, "AI 마케팅")
    assert len(out) == 4
    assert out[0] == "only one"


def test_generate_prompts_fallback_on_bad_json(monkeypatch):
    _patch_client(monkeypatch, "여기엔 JSON 배열이 없습니다")
    out = cardnews._generate_prompts({}, "AI 마케팅")
    assert len(out) == 4
    assert all("AI 마케팅" in p for p in out)  # 폴백 프롬프트는 키워드 포함


# ── _generate_image ───────────────────────────────────────────────────────
def test_generate_image_returns_none_on_error(monkeypatch):
    class _RaisingModels:
        def generate_images(self, **kw):
            raise RuntimeError("API 오류")

    class _RaisingClient:
        models = _RaisingModels()

    monkeypatch.setattr(cardnews, "_client", lambda: _RaisingClient())
    assert cardnews._generate_image("prompt", 1) is None
