from __future__ import annotations

import os
import sqlite3

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QCheckBox, QDialog

from pdfsearchviewer.cache import IndexCache
from pdfsearchviewer.models import Hit
from pdfsearchviewer.page_numbers import to_display_page
from pdfsearchviewer.stats import EMPTY_MARK_LABEL, UNMARKED_LABEL, group_hits, summary_counts
from pdfsearchviewer.ui.hit_tile import HitTile, MarkNoteDialog
from pdfsearchviewer.ui.stats_panel import StatsPanel


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _hit(hit_id: int, mark: str | None, page: int = 0) -> Hit:
    return Hit(hit_id, page, "甲", "甲", (0.0, 0.0, 1.0, 1.0), 0, 1, "F", 10.0, 0, mark=mark)


def test_group_by_mark_splits_notes_and_names_empty():
    hits = [
        _hit(1, None),
        _hit(2, ""),
        _hit(3, "   "),
        _hit(4, "勘误"),
        _hit(5, " 勘误 "),
        _hit(6, EMPTY_MARK_LABEL),
    ]
    groups = {g.key: g for g in group_hits(hits, "mark")}
    assert sum(g.count for g in groups.values()) == len(hits)
    assert groups["\x00"].label == UNMARKED_LABEL
    assert groups["\x00"].hit_ids == [1]
    assert groups["\x01"].label == EMPTY_MARK_LABEL
    assert groups["\x01"].hit_ids == [2, 3]
    assert groups["\x02勘误"].label == "勘误"
    assert groups["\x02勘误"].hit_ids == [4, 5]
    assert groups["\x02" + EMPTY_MARK_LABEL].label == EMPTY_MARK_LABEL
    assert groups["\x02" + EMPTY_MARK_LABEL].hit_ids == [6]
    counts = summary_counts(hits)
    assert counts["marked"] == 5
    assert counts["unmarked"] == 1


def test_stats_panel_lists_mark_groups(qapp: QApplication):
    panel = StatsPanel()
    panel.set_hits([_hit(1, None), _hit(2, ""), _hit(3, "勘误"), _hit(4, "勘误")])
    index = panel.group_by.findData("mark")
    assert panel.group_by.itemText(index) == "按信息"
    panel.group_by.setCurrentIndex(index)
    qapp.processEvents()
    labels = [panel.table.item(row, 0).text() for row in range(panel.table.rowCount())]
    assert labels.count("勘误") == 1
    assert EMPTY_MARK_LABEL in labels
    assert UNMARKED_LABEL in labels
    assert "标记 3 未标记 1" in panel.summary.text()


def test_tile_shows_only_the_page_and_one_mark_box(qapp: QApplication):
    hit = _hit(7, None, page=4)
    tile = HitTile(hit, page_offset=2)
    tile.show()
    qapp.processEvents()
    assert tile.meta.text() == f"p{to_display_page(4, 2)}"
    boxes = tile.findChildren(QCheckBox)
    assert [box.text() for box in boxes] == ["标记"]
    assert boxes[0].isChecked() is False

    hit.mark = ""
    tile.update_hit(hit)
    assert tile.mark_cb.isChecked() is True
    assert tile.mark_cb.toolTip() == EMPTY_MARK_LABEL

    hit.mark = "勘误"
    tile.update_hit(hit)
    assert tile.mark_cb.toolTip() == "勘误"
    tile.close()


def test_checking_mark_asks_and_emits_note(qapp: QApplication, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "pdfsearchviewer.ui.hit_tile.ask_mark_note",
        lambda parent=None: "勘误",
    )
    tile = HitTile(_hit(3, None))
    notes: list[tuple[int, object]] = []
    tile.mark_changed.connect(lambda hit_id, note: notes.append((hit_id, note)))
    tile.show()
    qapp.processEvents()
    QTest.mouseClick(tile.mark_cb, Qt.MouseButton.LeftButton)
    QTest.qWait(30)
    assert notes == [(3, "勘误")]
    assert tile.mark_cb.isChecked() is True
    tile.close()


def test_unchecking_mark_clears_without_dialog(qapp: QApplication, monkeypatch: pytest.MonkeyPatch):
    def _forbidden(parent=None):
        raise AssertionError("取消标记时不应再询问信息")

    monkeypatch.setattr("pdfsearchviewer.ui.hit_tile.ask_mark_note", _forbidden)
    tile = HitTile(_hit(3, "勘误"))
    notes: list[object] = []
    tile.mark_changed.connect(lambda _hit_id, note: notes.append(note))
    tile.show()
    qapp.processEvents()
    assert tile.mark_cb.isChecked() is True
    QTest.mouseClick(tile.mark_cb, Qt.MouseButton.LeftButton)
    QTest.qWait(30)
    assert notes == [None]
    assert tile.mark_cb.isChecked() is False
    tile.close()


def test_mark_dialog_enter_keeps_text_and_escape_is_empty(qapp: QApplication):
    dialog = MarkNoteDialog()
    dialog.show()
    qapp.processEvents()
    dialog.edit.setText("  勘误  ")
    QTest.keyClick(dialog.edit, Qt.Key.Key_Return)
    assert dialog.note == "勘误"
    assert dialog.result() == QDialog.DialogCode.Accepted

    empty = MarkNoteDialog()
    empty.show()
    qapp.processEvents()
    QTest.keyClick(empty.edit, Qt.Key.Key_Return)
    assert empty.note == ""
    assert empty.result() == QDialog.DialogCode.Accepted

    discarded = MarkNoteDialog()
    discarded.show()
    qapp.processEvents()
    discarded.edit.setText("不会保存")
    QTest.keyClick(discarded.edit, Qt.Key.Key_Escape)
    assert discarded.note == ""
    assert discarded.result() == QDialog.DialogCode.Accepted

    closed = MarkNoteDialog()
    closed.edit.setText("关掉")
    closed.reject()
    assert closed.note == ""


def test_old_reviews_migrate_to_mark_notes(tmp_path):
    db = tmp_path / "old.sqlite3"
    conn = sqlite3.connect(db)
    conn.execute(
        """
        CREATE TABLE hits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            search_id INTEGER NOT NULL,
            hit_id INTEGER NOT NULL,
            page INTEGER NOT NULL,
            text TEXT NOT NULL,
            normalized_text TEXT NOT NULL,
            bbox_json TEXT NOT NULL,
            char_start INTEGER NOT NULL,
            char_end INTEGER NOT NULL,
            font TEXT NOT NULL,
            size REAL NOT NULL,
            color INTEGER NOT NULL,
            reviewed INTEGER
        )
        """
    )
    conn.executemany(
        """
        INSERT INTO hits (
            search_id, hit_id, page, text, normalized_text, bbox_json,
            char_start, char_end, font, size, color, reviewed
        ) VALUES (1, ?, 0, 'a', 'a', '[0, 0, 1, 1]', 0, 1, 'F', 10, 0, ?)
        """,
        [(1, 1), (2, 0), (3, None)],
    )
    conn.commit()
    conn.close()

    cache = IndexCache(db)
    loaded = {hit.hit_id: hit.mark for hit in cache.load_hits(1)}
    cache.close()
    assert loaded == {1: "正确", 2: "有误", 3: None}
