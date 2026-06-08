import json
import os
import pytest
from unittest.mock import patch, MagicMock


SAMPLE_DATA = {
    "keyword": "AI 마케팅",
    "trends": ["트렌드1", "트렌드2"],
    "insights": ["인사이트1"],
    "keywords": [{"word": "생성형 AI", "relevance": "high", "context": "설명"}],
    "posts": [{"title": "제목", "summary": "요약", "tags": ["태그"]}],
}

FAKE_CONTENT = {
    "naver_blog": {
        "title": "AI 마케팅 완전 정복",
        "body": "본문 내용입니다.",
        "hashtags": ["#AI마케팅"],
    },
    "instagram": {
        "caption": "✨ AI로 마케팅 혁신!",
        "hashtags": ["#AI"],
    },
    "ad_copy": {
        "headline": "AI로 매출 2배",
        "subheadline": "지금 바로 시작하세요",
        "cta": "무료 체험하기",
    },
}


def test_generate_content_returns_three_formats():
    from agents.writer.generator import generate_content

    mock_response = MagicMock()
    mock_response.text = json.dumps(FAKE_CONTENT)

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}):
        with patch("google.genai.Client", return_value=mock_client):
            result = generate_content(SAMPLE_DATA)

    assert "naver_blog" in result
    assert "instagram" in result
    assert "ad_copy" in result
    assert "title" in result["naver_blog"]
    assert "body" in result["naver_blog"]
    assert "hashtags" in result["naver_blog"]
    assert "caption" in result["instagram"]
    assert "hashtags" in result["instagram"]
    assert "headline" in result["ad_copy"]
    assert "subheadline" in result["ad_copy"]
    assert "cta" in result["ad_copy"]


def test_generate_content_raises_when_api_key_missing():
    from agents.writer.generator import generate_content

    env = {k: v for k, v in os.environ.items() if k != "GEMINI_API_KEY"}
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(EnvironmentError, match="GEMINI_API_KEY"):
            generate_content({"keyword": "test"})


def test_build_prompt_includes_keyword():
    from agents.writer.generator import build_prompt

    data = {
        "keyword": "AI 마케팅",
        "trends": ["트렌드1", "트렌드2"],
        "insights": ["인사이트1"],
        "keywords": [{"word": "생성형 AI", "relevance": "high", "context": "설명"}],
        "posts": [],
    }

    prompt = build_prompt(data)

    assert "AI 마케팅" in prompt
    assert "트렌드1" in prompt
    assert "인사이트1" in prompt
    assert "생성형 AI" in prompt


def test_build_prompt_handles_missing_fields():
    from agents.writer.generator import build_prompt

    prompt = build_prompt({"keyword": "테스트"})

    assert "테스트" in prompt
