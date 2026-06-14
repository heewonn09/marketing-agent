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
