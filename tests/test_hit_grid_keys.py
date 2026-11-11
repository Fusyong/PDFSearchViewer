from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from pdfsearchviewer.models import CameraSettings, Hit, LayoutMode, ViewMode
from pdfsearchviewer.ui.hit_grid import HitGrid, arrow_step, next_hit_in_direction


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _hit(hit_id: int, page: int) -> Hit:
    return Hit(
        hit_id=hit_id,
        page=page,
        text="甲",
        normalized_text="甲",
        bbox=(0.0, 0.0, 10.0, 10.0),
        char_start=0,
        char_end=1,
        font="SimSun",
        size=12.0,
        color=0,
    )


def test_arrow_step_ignores_modified_keys():
    assert arrow_step(Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier) == (0, 1)
    assert arrow_step(Qt.Key.Key_Up, Qt.KeyboardModifier.KeypadModifier) == (-1, 0)
    assert arrow_step(Qt.Key.Key_Left, Qt.KeyboardModifier.ShiftModifier) is None
    assert arrow_step(Qt.Key.Key_Down, Qt.KeyboardModifier.ControlModifier) is None
    assert arrow_step(Qt.Key.Key_A, Qt.KeyboardModifier.NoModifier) is None


def test_next_hit_skips_empty_cells_and_stops_at_the_edge():
    cells = {
        (0, 1): 10,
        (1, 0): 20,
        (1, 1): 30,
        (2, 1): 40,
    }
    assert next_hit_in_direction(cells, None, 0, 1) == 10
    assert next_hit_in_direction(cells, None, -1, 0) == 40
    assert next_hit_in_direction(cells, (0, 1), 1, 0) == 30
    assert next_hit_in_direction(cells, (0, 1), 0, -1) is None
    assert next_hit_in_direction(cells, (1, 1), 1, 0) == 40
    assert next_hit_in_direction(cells, (1, 1), 0, -1) == 20
    assert next_hit_in_direction(cells, (2, 1), 0, -1) is None
    assert next_hit_in_direction(cells, (1, 0), 1, 0) is None
    assert next_hit_in_direction({}, (0, 0), 0, 1) is None


def _show(grid: HitGrid, qapp: QApplication) -> None:
    grid.resize(900, 700)
    grid.show()
    qapp.processEvents()


def _press(widget, key, qapp: QApplication, modifier=Qt.KeyboardModifier.NoModifier) -> None:
    QTest.keyClick(widget, key, modifier)
    qapp.processEvents()


def test_row_layout_arrows_follow_the_grid(qapp: QApplication):
    grid = HitGrid()
    grid.set_camera(
        CameraSettings(
            view_mode=ViewMode.FIT_WIDTH,
            layout=LayoutMode.ROW,
            columns=3,
            tile_w=80,
            tile_h=40,
        )
    )
    grid.set_hits([_hit(i, i) for i in range(5)])
    _show(grid, qapp)
    selected: list[int] = []
    grid.hit_selected.connect(selected.append)

    QTest.mouseClick(grid._tiles[0], Qt.MouseButton.LeftButton)
    qapp.processEvents()
    assert selected == [0]
    assert qapp.focusWidget() is grid

    _press(grid, Qt.Key.Key_Right, qapp)
    _press(grid, Qt.Key.Key_Right, qapp)
    _press(grid, Qt.Key.Key_Right, qapp)  # edge of the row: stay put
    _press(grid, Qt.Key.Key_Down, qapp)  # nothing under the last column
    assert selected == [0, 1, 2]
    _press(grid, Qt.Key.Key_Left, qapp)
    _press(grid, Qt.Key.Key_Down, qapp)
    assert selected[-1] == 4
    _press(grid, Qt.Key.Key_Left, qapp)
    _press(grid, Qt.Key.Key_Up, qapp)
    assert selected[-1] == 0

    before = len(selected)
    _press(grid, Qt.Key.Key_Right, qapp, Qt.KeyboardModifier.ShiftModifier)
    assert len(selected) == before

    grid.close()
    grid.deleteLater()
    qapp.processEvents()


def test_column_layout_down_stays_in_the_lane(qapp: QApplication):
    grid = HitGrid()
    grid.set_camera(
        CameraSettings(
            view_mode=ViewMode.LOCAL,
            layout=LayoutMode.COLUMN,
            columns=2,
            tile_w=80,
            tile_h=40,
        )
    )
    grid.set_hits([_hit(i, i) for i in range(4)])
    _show(grid, qapp)
    selected: list[int] = []
    grid.hit_selected.connect(selected.append)
    grid._select(0)
    _press(grid, Qt.Key.Key_Down, qapp)
    _press(grid, Qt.Key.Key_Right, qapp)
    assert selected[-2:] == [1, 3]
    grid.close()
    grid.deleteLater()
    qapp.processEvents()


def test_book_arrows_skip_empty_pages(qapp: QApplication):
    grid = HitGrid()
    grid.set_camera(CameraSettings(view_mode=ViewMode.BOOK, tile_w=80, tile_h=40))
    # display pages with offset 0: pdf 0 → 1 (right), pdf 1 → 2 (left), pdf 2 → 3 (right)
    grid.set_hits(
        [
            _hit(10, 0),
            _hit(20, 1),
            _hit(30, 2),
            _hit(40, 2),
        ]
    )
    _show(grid, qapp)
    selected: list[int] = []
    grid.hit_selected.connect(selected.append)
    grid._select(10)
    _press(grid, Qt.Key.Key_Down, qapp)
    _press(grid, Qt.Key.Key_Down, qapp)
    _press(grid, Qt.Key.Key_Left, qapp)  # empty verso beside the second recto hit
    _press(grid, Qt.Key.Key_Up, qapp)
    _press(grid, Qt.Key.Key_Left, qapp)
    assert selected == [10, 30, 40, 30, 20]

    box = grid._tiles[20].mark_cb
    box.setFocus()
    qapp.processEvents()
    assert qapp.focusWidget() is box
    _press(box, Qt.Key.Key_Right, qapp)
    assert selected[-1] == 30

    grid.close()
    grid.deleteLater()
    qapp.processEvents()


def test_arrow_with_no_selection_enters_the_grid(qapp: QApplication):
    grid = HitGrid()
    grid.set_camera(
        CameraSettings(view_mode=ViewMode.FIT_WIDTH, layout=LayoutMode.ROW, columns=2)
    )
    grid.set_hits([_hit(1, 0), _hit(2, 1), _hit(3, 2)])
    _show(grid, qapp)
    selected: list[int] = []
    grid.hit_selected.connect(selected.append)
    grid.setFocus()
    _press(grid, Qt.Key.Key_Down, qapp)
    assert selected == [1]
    grid.close()
    grid.deleteLater()
    qapp.processEvents()
