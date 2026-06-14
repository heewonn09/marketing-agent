from agents.cardnews import main as cardnews


def test_safe_keyword_replaces_special_chars():
    assert cardnews._safe_keyword('a/b:c*d?e') == "a_b_c_d_e"


def test_wrap_preserves_all_characters():
    font = cardnews._find_font(20)
    text = "가나다라마바사아자차카타파하" * 3
    lines = cardnews._wrap(text, font, 120)
    # 줄바꿈을 하더라도 글자는 하나도 손실되면 안 된다
    assert "".join(lines) == text


def test_wrap_width_one_forces_one_char_per_line():
    font = cardnews._find_font(20)
    lines = cardnews._wrap("abcde", font, 1)
    assert lines == list("abcde")
