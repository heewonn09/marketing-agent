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


def test_clean_strips_markdown_and_heading():
    assert cardnews._clean("**데이터 기반 전략**") == "데이터 기반 전략"
    assert cardnews._clean("*기울임*") == "기울임"
    assert cardnews._clean("# 제목") == "제목"


def test_first_sentences_returns_full_when_short():
    assert cardnews._first_sentences("짧은 문장입니다.", 50) == "짧은 문장입니다."


def test_first_sentences_drops_unclosed_paren():
    out = cardnews._first_sentences("핵심 문장입니다. (ex. 부연 설명", 100)
    assert "(" not in out
    assert "ex" not in out
    assert out.startswith("핵심 문장입니다")


def test_first_sentences_trims_long_single_sentence_at_word_boundary():
    text = "가나다 라마바 사아자 차카타 파하가 나다라 마바사 아자차"
    out = cardnews._first_sentences(text, 12)
    assert len(out) <= 12
    # 단어 중간이 잘리지 않음: 결과의 모든 토큰이 원문 단어
    assert all(tok in text.split() for tok in out.split())
