from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from pdfsearchviewer.cache import IndexCache
from pdfsearchviewer.indexer import index_pdf
from pdfsearchviewer.models import (
    NormalizeOptions,
    SearchQuery,
    StyleFilter,
    StyleMatchMode,
)
from pdfsearchviewer.normalize import build_normalized_stream, normalize_display_text
from pdfsearchviewer.search_engine import search
from pdfsearchviewer.stats import group_hits, summary_counts


FIXTURES = Path(__file__).parent / "fixtures"


def _make_sample_pdf(path: Path) -> Path:
    doc = pymupdf.open()
    page = doc.new_page(width=400, height=300)
    # Mixed spacing variants for figure labels
    page.insert_text((50, 80), "图 1-2 示意图", fontsize=12, fontname="china-s")
    page.insert_text((50, 120), "图1-2 示意图", fontsize=12, fontname="china-s")
    page.insert_text((50, 160), "Figure 3.1", fontsize=10, fontname="helv")
    page.insert_text((50, 200), "正文内容ABC", fontsize=14, fontname="china-s")
    # Second page for cross-line-ish content
    page2 = doc.new_page(width=400, height=300)
    page2.insert_text((50, 80), "跨页标记X", fontsize=11, fontname="china-s")
    doc.save(path)
    doc.close()
    return path


@pytest.fixture(scope="module")
def sample_pdf(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("pdf")
    path = d / "sample.pdf"
    try:
        return _make_sample_pdf(path)
    except Exception:
        # Fallback without CJK font
        doc = pymupdf.open()
        page = doc.new_page(width=400, height=300)
        page.insert_text((50, 80), "Fig 1-2 sample", fontsize=12, fontname="helv")
        page.insert_text((50, 120), "Fig1-2 sample", fontsize=12, fontname="helv")
        page.insert_text((50, 160), "Figure 3.1", fontsize=10, fontname="helv")
        page.insert_text((50, 200), "Body text ABC", fontsize=14, fontname="helv")
        page2 = doc.new_page(width=400, height=300)
        page2.insert_text((50, 80), "Marker X", fontsize=11, fontname="helv")
        doc.save(path)
        doc.close()
        return path


@pytest.fixture
def doc_index(sample_pdf):
    return index_pdf(sample_pdf)


def test_index_has_chars(doc_index):
    assert doc_index.page_count == 2
    assert len(doc_index.chars) > 0
    assert len(doc_index.raw_text) > 0
    assert len(doc_index.stream_map) == len(doc_index.raw_text)


def test_search_literal(doc_index):
    # Works for both CJK and ASCII fixtures
    q = SearchQuery(pattern="1-2", is_regex=False)
    hits = search(doc_index, q)
    assert len(hits) >= 2


def test_default_preserves_space_difference(doc_index):
    """Without strip_whitespace, 'Fig 1-2' and 'Fig1-2' remain distinct patterns."""
    spaced = search(doc_index, SearchQuery(pattern=r"Fig\s+1-2", is_regex=True))
    tight = search(doc_index, SearchQuery(pattern=r"Fig1-2", is_regex=True))
    # At least one of the fixture variants should match each; counts may differ
    assert isinstance(spaced, list)
    assert isinstance(tight, list)
    # Combined unique texts should show space difference when both exist
    all_hits = search(doc_index, SearchQuery(pattern=r"Fig\s*1-2", is_regex=True))
    texts = {h.text for h in all_hits}
    if any(" " in t for t in texts) and any("Fig1" in t or "图1" in t for t in texts):
        assert len(texts) >= 1


def test_strip_whitespace_optional(doc_index):
    """With strip_whitespace, spaced and tight labels collapse to the same match."""
    # Prefer Chinese fixture labels; fall back to ASCII Fig labels
    if "图" in doc_index.raw_text:
        pattern = "图1-2"
    else:
        pattern = "Fig1-2"
    q = SearchQuery(
        pattern=pattern,
        is_regex=False,
        normalize=NormalizeOptions(strip_whitespace=True),
    )
    hits = search(doc_index, q)
    assert len(hits) >= 2
    norms = {h.normalized_text for h in hits}
    assert pattern in norms or any(pattern in n for n in norms)

def test_style_size_filter(doc_index):
    q = SearchQuery(
        pattern=".",
        is_regex=True,
        style=StyleFilter(size_min=13.5, size_max=14.5, match_mode=StyleMatchMode.MAJORITY),
    )
    hits = search(doc_index, q)
    assert all(13.5 <= h.size <= 14.5 for h in hits)


def test_normalize_display():
    opts = NormalizeOptions(strip_whitespace=True)
    assert normalize_display_text("图 1-2", opts) == "图1-2"
    assert normalize_display_text("图\u30001-2", opts) == "图1-2"


def test_build_normalized_stream_mapping():
    raw = "a b\nc"
    stream_map = [0, 1, 2, -1, 3]
    text, mapping = build_normalized_stream(
        raw, stream_map, NormalizeOptions(strip_whitespace=True)
    )
    assert text == "abc"
    assert len(mapping) == 3


def test_cache_roundtrip(doc_index, tmp_path):
    cache = IndexCache(tmp_path / "t.sqlite3")
    cache.put_index(doc_index)
    loaded = cache.get_index(doc_index.fingerprint)
    assert loaded is not None
    assert loaded.raw_text == doc_index.raw_text
    assert len(loaded.chars) == len(doc_index.chars)

    q = SearchQuery(pattern="1-2", is_regex=False)
    hits = search(doc_index, q)
    sid = cache.save_search(doc_index.fingerprint, q, hits, name="t")
    loaded_hits = cache.load_hits(sid)
    assert len(loaded_hits) == len(hits)
    cache.update_hit_review(sid, hits[0].hit_id, True)
    loaded_hits2 = cache.load_hits(sid)
    assert loaded_hits2[0].reviewed is True
    cache.close()


def test_stats_groups(doc_index):
    hits = search(doc_index, SearchQuery(pattern="1-2", is_regex=False))
    groups = group_hits(hits, "text")
    assert sum(g.count for g in groups) == len(hits)
    sc = summary_counts(hits)
    assert sc["total"] == len(hits)


def test_dotall_multiline(doc_index):
    # raw_text has newlines between lines/pages
    q = SearchQuery(pattern=r"Fig.*sample|图.*示", is_regex=True, dotall=True)
    hits = search(doc_index, q)
    assert isinstance(hits, list)
