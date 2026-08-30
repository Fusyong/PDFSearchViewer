from __future__ import annotations

import pymupdf
import pytest

from pdfsearchviewer.models import (
    AlignMode,
    CameraSettings,
    SearchQuery,
    StyleFilter,
    StyleMatchMode,
    ViewMode,
)
from pdfsearchviewer.page_numbers import (
    spread_left_page,
    spread_right_page,
    to_display_page,
    to_pdf_page,
)
from pdfsearchviewer.renderer import _clip_rect
from pdfsearchviewer.search_engine import filter_hits, search

# Reuse sample PDF fixtures from the search-engine suite
from test_search_engine import doc_index, sample_pdf  # noqa: F401


def test_page_offset_roundtrip():
    assert to_display_page(0, 0) == 1
    assert to_display_page(4, -4) == 1
    assert to_pdf_page(1, -4) == 4
    assert to_display_page(0, -2) == -1
    assert to_pdf_page(-1, -2) == 0
    for offset in (-10, -1, 0, 3, 20):
        for pdf in range(0, 50):
            assert to_pdf_page(to_display_page(pdf, offset), offset) == pdf


def test_region_filter(doc_index):
    all_hits = search(doc_index, SearchQuery(pattern=".", is_regex=True))
    assert len(all_hits) > 0
    region = (0.0, 0.0, 400.0, 100.0)
    hits = filter_hits(
        all_hits,
        StyleFilter(region=region, match_mode=StyleMatchMode.MAJORITY),
    )
    assert len(hits) <= len(all_hits)
    assert len(hits) >= 1
    for h in hits:
        cy = (h.bbox[1] + h.bbox[3]) / 2
        assert cy <= 120.0


def test_clip_rect_fit_width_left():
    page = pymupdf.Rect(0, 0, 400, 600)
    hit = (100.0, 200.0, 140.0, 220.0)
    cam = CameraSettings(
        zoom=2.0,
        tile_w=220,
        tile_h=120,
        view_mode=ViewMode.FIT_WIDTH,
        align=AlignMode.LEFT,
    )
    clip = _clip_rect(hit, page, cam)
    assert abs(clip.x0 - page.x0) < 1e-6
    assert abs(clip.width - page.width) < 1e-6


def test_clip_rect_local_center():
    page = pymupdf.Rect(0, 0, 400, 600)
    hit = (100.0, 200.0, 140.0, 220.0)
    cam = CameraSettings(
        zoom=2.0,
        tile_w=220,
        tile_h=120,
        view_mode=ViewMode.LOCAL,
        align=AlignMode.CENTER,
    )
    clip = _clip_rect(hit, page, cam)
    assert clip.x0 < 120 < clip.x1
    assert clip.y0 < 210 < clip.y1


def test_spread_pages():
    assert spread_left_page(1) == 0
    assert spread_right_page(0) == 1
    assert spread_left_page(2) == 2
    assert spread_right_page(2) == 3
    assert spread_left_page(3) == 2
    assert spread_left_page(4) == 4
    assert spread_left_page(5) == 4


def test_clip_rect_book_like_fit_width():
    page = pymupdf.Rect(0, 0, 400, 600)
    hit = (100.0, 200.0, 140.0, 220.0)
    cam = CameraSettings(
        zoom=2.0,
        tile_w=220,
        tile_h=120,
        view_mode=ViewMode.BOOK,
        align=AlignMode.LEFT,
    )
    clip = _clip_rect(hit, page, cam)
    assert abs(clip.x0 - page.x0) < 1e-6
    assert abs(clip.width - page.width) < 1e-6


def test_camera_default_is_book():
    assert CameraSettings().view_mode == ViewMode.BOOK
