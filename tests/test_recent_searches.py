from __future__ import annotations

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from pdfsearchviewer.recent_searches import (
    RecentSearches,
    load_recent,
    promote,
    save_recent,
)
from pdfsearchviewer.ui.search_panel import SearchPanel


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_promote_moves_newest_first_and_drops_duplicate():
    assert promote(["a", "b"], "b") == ["b", "a"]
    assert promote(["a", "b"], "a") is None
    assert promote(["a"], "") is None
    assert promote(["a", "b", "c"], "d", limit=2) == ["d", "a"]


def test_promote_keeps_whitespace_pattern():
    assert promote([], "  ") == ["  "]


def test_load_missing_or_corrupt(tmp_path):
    assert load_recent(tmp_path / "missing.json") == []
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    assert load_recent(bad) == []
    weird = tmp_path / "weird.json"
    weird.write_text(json.dumps({"patterns": ["a", "", "a", 3, "b", "  "]}), encoding="utf-8")
    assert load_recent(weird) == ["a", "b", "  "]


def test_recent_roundtrip(tmp_path):
    path = tmp_path / "sub" / "recent_searches.json"
    store = RecentSearches(path)
    assert store.remember(r"第\d+章") == [r"第\d+章"]
    assert store.remember("甲") == ["甲", r"第\d+章"]
    assert store.remember("甲") is None
    again = RecentSearches(path)
    assert again.patterns == ["甲", r"第\d+章"]
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["patterns"] == ["甲", r"第\d+章"]


def test_search_box_remembers_and_dropdown_fills(qapp, tmp_path):
    path = tmp_path / "recent_searches.json"
    save_recent(path, ["alpha", "beta"])
    panel = SearchPanel(recent_path=path)
    calls: list[str] = []
    panel.search_requested.connect(lambda query: calls.append(query.pattern))
    panel.show()
    qapp.processEvents()

    assert panel.pattern.currentText() == ""
    assert [panel.pattern.itemText(i) for i in range(panel.pattern.count())] == [
        "alpha",
        "beta",
    ]
    assert panel.pattern.completer() is None

    panel.pattern.showPopup()
    view = panel.pattern.view()
    rect = view.visualRect(view.model().index(1, 0))
    QTest.mouseClick(
        view.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        rect.center(),
    )
    qapp.processEvents()
    assert panel.pattern.currentText() == "beta"
    assert calls == []

    panel.pattern.setEditText(r"\c+")
    QTest.keyClick(panel.pattern.lineEdit(), Qt.Key.Key_Return)
    qapp.processEvents()
    assert calls == [r"\c+"]
    assert [panel.pattern.itemText(i) for i in range(panel.pattern.count())] == [
        r"\c+",
        "alpha",
        "beta",
    ]
    assert panel.pattern.currentText() == r"\c+"
    assert load_recent(path) == [r"\c+", "alpha", "beta"]

    panel.pattern.setEditText("beta")
    panel._last_submit_at = 0.0
    panel._emit_search()
    assert calls == [r"\c+", "beta"]
    assert load_recent(path)[0] == "beta"


def test_search_options_default_on(qapp, tmp_path):
    panel = SearchPanel(recent_path=tmp_path / "recent_searches.json")
    assert panel.is_regex.isChecked()
    assert panel.case_insensitive.isChecked()
    assert panel.dotall.isChecked()
    assert panel.strip_ws.isChecked()
    assert not panel.whole_word.isChecked()
    query = panel.build_search_query()
    assert query.is_regex
    assert query.case_insensitive
    assert query.dotall
    assert query.normalize.strip_whitespace
    assert query.normalize.collapse_single_newlines


def test_blank_search_is_not_stored(qapp, tmp_path):
    path = tmp_path / "recent_searches.json"
    panel = SearchPanel(recent_path=path)
    panel.pattern.setEditText("")
    panel._emit_search()
    assert panel.pattern.count() == 0
    assert not path.exists()
