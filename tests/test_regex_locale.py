"""Tests for local character-class escapes (\\y \\c \\p and complements)."""

from __future__ import annotations

import re

import pytest

from pdfsearchviewer.models import (
    CharInfo,
    DocumentIndex,
    SearchQuery,
)
from pdfsearchviewer.regex_locale import (
    CJK_PUNCT_CHARS,
    HAN_NUMERAL_CHARS,
    PINYIN_CHARS,
    expand_locale_escapes,
)
from pdfsearchviewer.search_engine import search


def test_expand_y_outside_class():
    out = expand_locale_escapes(r"\y+")
    assert out.startswith("[")
    assert out.endswith("]+")
    assert "a" in out and "ā" in out
    assert re.fullmatch(out, "pīn")
    assert re.fullmatch(out, "123") is None


def test_expand_Y_complement():
    out = expand_locale_escapes(r"\Y")
    assert out.startswith("[^")
    assert re.fullmatch(out, "中")
    assert re.fullmatch(out, "a") is None


def test_expand_c_han():
    out = expand_locale_escapes(r"\c+")
    assert re.fullmatch(out, "汉字")
    assert re.fullmatch(out, "A") is None
    assert re.fullmatch(out, "。") is None


def test_expand_C_non_han():
    out = expand_locale_escapes(r"\C+")
    assert re.fullmatch(out, "abc")
    assert re.fullmatch(out, "汉") is None


def test_expand_p_punct():
    out = expand_locale_escapes(r"\p+")
    for ch in CJK_PUNCT_CHARS:
        assert re.fullmatch(out, ch), ch
    assert re.fullmatch(out, "，。")
    assert re.fullmatch(out, "a") is None


def test_expand_P_non_punct():
    out = expand_locale_escapes(r"\P+")
    assert re.fullmatch(out, "字a")
    assert re.fullmatch(out, "。") is None


def test_expand_j_numeral():
    out = expand_locale_escapes(r"\j+")
    assert re.fullmatch(out, "三千")
    assert re.fullmatch(out, "〇一二")
    assert re.fullmatch(out, "亿兆")
    for ch in HAN_NUMERAL_CHARS:
        assert re.fullmatch(expand_locale_escapes(r"\j"), ch), ch
    assert re.fullmatch(out, "甲") is None
    assert re.fullmatch(out, "3") is None


def test_expand_J_complement():
    out = expand_locale_escapes(r"\J")
    assert re.fullmatch(out, "甲")
    assert re.fullmatch(out, "三") is None


def test_complement_J_inside_class_raises():
    with pytest.raises(ValueError, match=r"\\J"):
        expand_locale_escapes(r"[a\J]")


def test_inject_inside_class():
    out = expand_locale_escapes(r"[0-9\y]")
    assert out.startswith("[0-9")
    assert out.endswith("]")
    assert re.fullmatch(out, "5")
    assert re.fullmatch(out, "ā")
    assert re.fullmatch(out, "中") is None


def test_complement_via_caret_and_y():
    out = expand_locale_escapes(r"[^\y]")
    assert re.fullmatch(out, "中")
    assert re.fullmatch(out, "a") is None


def test_complement_inside_class_raises():
    with pytest.raises(ValueError, match=r"\\Y"):
        expand_locale_escapes(r"[a\Y]")


def test_escaped_bracket_not_class():
    out = expand_locale_escapes(r"\[\y\]")
    assert out.startswith(r"\[")
    assert "ā" in out or "a" in out


def test_double_backslash_not_escape():
    # \\y is backslash + y, not the locale escape
    out = expand_locale_escapes(r"\\y")
    assert out == r"\\y"


def test_pinyin_set_covers_product_chars():
    body = expand_locale_escapes(r"\y")
    cre = re.compile(body)
    for ch in PINYIN_CHARS:
        # Combining sequences may be multiple code points; match whole char cluster
        assert cre.fullmatch(ch) is not None, repr(ch)


def _index_from_text(text: str) -> DocumentIndex:
    chars = [
        CharInfo(
            text=ch,
            font="Test",
            size=12.0,
            color=0,
            bbox=(float(i), 0.0, float(i + 1), 12.0),
            page=0,
            block=0,
            line=0,
            span=0,
            char_index=i,
        )
        for i, ch in enumerate(text)
    ]
    return DocumentIndex(
        path="mem://test",
        fingerprint="test",
        page_count=1,
        page_sizes=[(100.0, 100.0)],
        chars=chars,
        spans=[],
        raw_text=text,
        stream_map=list(range(len(text))),
    )


def test_search_with_locale_escapes():
    idx = _index_from_text("拼音han字，标点。")
    hits_c = search(idx, SearchQuery(pattern=r"\c+", is_regex=True))
    assert [h.text for h in hits_c] == ["拼音", "字", "标点"]

    hits_p = search(idx, SearchQuery(pattern=r"\p", is_regex=True))
    assert {h.text for h in hits_p} == {"，", "。"}

    hits_y = search(idx, SearchQuery(pattern=r"\y+", is_regex=True))
    assert any("han" in h.text for h in hits_y)

    idx2 = _index_from_text("卷一章三甲")
    hits_j = search(idx2, SearchQuery(pattern=r"\j+", is_regex=True))
    assert [h.text for h in hits_j] == ["一", "三"]


def test_search_literal_does_not_expand():
    idx = _index_from_text(r"\c 字")
    hits = search(idx, SearchQuery(pattern=r"\c", is_regex=False))
    assert len(hits) == 1
    assert hits[0].text == r"\c"
