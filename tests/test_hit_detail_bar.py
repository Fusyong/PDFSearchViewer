from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QLabel

from pdfsearchviewer.models import Hit
from pdfsearchviewer.ui.hit_detail_bar import (
    HitDetailBar,
    fit_detail_line,
    format_hit_detail,
    tooltip_html,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _hit(**overrides) -> Hit:
    data = dict(
        hit_id=3,
        page=4,
        text="甲乙\n丙丁" + "文" * 40,
        normalized_text="甲乙丙丁",
        bbox=(1.25, 2.5, 30.0, 12.0),
        char_start=10,
        char_end=14,
        font="ABCDEF+SimSun",
        size=12.0,
        color=0x112233,
    )
    data.update(overrides)
    return Hit(**data)


def _len_advance(text: str) -> int:
    return len(text)


def test_format_keeps_a_short_line_and_full_hover_text():
    parts = format_hit_detail(
        _hit(text="甲乙\n丙丁"),
        1,
        entry_line=2,
        entry_pattern="甲<乙>",
    )
    assert parts.head.startswith("条目 2 · #3 · 图书页 1 · PDF 5 · ")
    assert parts.quote == "甲乙 丙丁"
    assert parts.tail == " · SimSun 12.0pt #112233"
    assert "甲乙\n丙丁" in parts.full
    assert "规范化: 甲乙丙丁" in parts.full
    assert "字体: SimSun (ABCDEF+SimSun)" in parts.full
    assert "字号: 12.00 pt" in parts.full
    assert "bbox: (1.25, 2.5, 30.0, 12.0)" in parts.full
    assert "字符范围: [10, 14)" in parts.full
    assert "标记: 未标记" in parts.full
    assert "条目 第 2 行: 甲<乙>" in parts.full


def test_format_records_mark_without_changing_the_visible_line():
    plain = format_hit_detail(_hit(), 1)
    empty = format_hit_detail(_hit(mark=""), 1)
    noted = format_hit_detail(_hit(mark="  勘误  "), 1)
    assert empty.tail == plain.tail
    assert noted.tail == plain.tail
    assert "标记: 标记（空）" in empty.full
    assert "标记: 勘误" in noted.full


def test_tooltip_escapes_markup_and_keeps_line_breaks():
    html = tooltip_html("甲<乙>\n第二行")
    assert "甲&lt;乙&gt;" in html
    assert "<br>" in html
    assert "<乙>" not in html


def test_fit_shortens_quote_and_keeps_style():
    parts = format_hit_detail(_hit(), 5)
    fixed = _len_advance(parts.head + "「」" + parts.tail)
    shown = fit_detail_line(parts, fixed + 6, _len_advance)
    assert shown.startswith(parts.head + "「")
    assert shown.endswith("」" + parts.tail)
    assert "…" in shown
    assert "文" * 20 not in shown


def test_fit_shows_everything_when_there_is_room():
    parts = format_hit_detail(_hit(text="甲"), 5)
    assert fit_detail_line(parts, 10_000, _len_advance) == parts.line


def test_fit_hides_the_tail_only_when_the_line_itself_does_not_fit():
    parts = format_hit_detail(_hit(text="甲乙丙丁"), 5)
    shown = fit_detail_line(parts, 8, _len_advance)
    assert len(shown) <= 8
    assert shown.endswith("…")
    assert "SimSun" not in shown


def test_detail_bar_is_one_line_and_elides(qapp: QApplication):
    bar = HitDetailBar()
    assert bar.sizeHint().height() < 48
    assert any(label.text() == "命中详情" for label in bar.findChildren(QLabel))

    bar.show_hit(_hit(), page_offset=-4)
    bar.resize(640, bar.sizeHint().height())
    bar.show()
    qapp.processEvents()

    shown = bar.shown_text()
    assert "图书页 1" in shown
    assert "PDF 5" in shown
    assert "SimSun" in shown
    assert "#112233" in shown
    assert "…" in shown
    assert "文" * 30 not in shown
    tip = bar.toolTip()
    assert "规范化: 甲乙丙丁" in tip
    assert "ABCDEF+SimSun" in tip
    assert "字符范围: [10, 14)" in tip
    assert "甲乙<br>" in tip or "甲乙<br/>" in tip

    bar.set_page_offset(0)
    assert "图书页 5" in bar.shown_text()
    assert "PDF 5" in bar.shown_text()

    bar.clear()
    assert bar.shown_text() == "未选择"
    assert bar.toolTip() == ""
