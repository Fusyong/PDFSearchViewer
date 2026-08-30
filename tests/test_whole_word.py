from __future__ import annotations

from pdfsearchviewer.models import SearchQuery
from pdfsearchviewer.search_engine import search

from test_search_engine import doc_index, sample_pdf  # noqa: F401


def test_whole_word_latin(doc_index):
    whole = search(
        doc_index,
        SearchQuery(pattern="Figure", is_regex=False, whole_word=True),
    )
    assert len(whole) >= 1
    inner = search(
        doc_index,
        SearchQuery(pattern="igur", is_regex=False, whole_word=True),
    )
    assert inner == []


def test_whole_word_allows_cjk_in_run(doc_index):
    if "正文" not in doc_index.raw_text:
        return
    hits = search(
        doc_index,
        SearchQuery(pattern="正文", is_regex=False, whole_word=True),
    )
    assert len(hits) >= 1
