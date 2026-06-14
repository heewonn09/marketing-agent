from agents.instagram import main as instagram


def test_build_caption_appends_hashtags():
    cap = instagram.build_caption({"caption": "본문", "hashtags": ["#a", "#b"]})
    assert cap == "본문\n\n#a #b"


def test_build_caption_without_hashtags():
    assert instagram.build_caption({"caption": "본문"}) == "본문"


def test_build_caption_empty():
    assert instagram.build_caption({}) == ""


def test_safe_keyword_replaces_special_chars():
    assert instagram._safe_keyword("a/b:c") == "a_b_c"
