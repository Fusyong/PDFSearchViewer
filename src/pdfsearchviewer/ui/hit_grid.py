from __future__ import annotations

from collections import defaultdict

from PySide6.QtCore import Qt, Signal, QRect, QSize
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QScrollArea, QWidget, QGridLayout, QVBoxLayout

from ..models import CameraSettings, Hit, LayoutMode, ViewMode
from ..page_numbers import spread_left_page, to_display_page
from .hit_tile import HitTile


class _EmptyPageSlot(QFrame):
    """Placeholder for a facing-page cell with no hit."""

    def __init__(self, display_page: int | None, tile_w: int, tile_h: int, parent=None):
        super().__init__(parent)
        self.setFixedSize(QSize(tile_w + 20, tile_h + 60))
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "_EmptyPageSlot { background: #f3f3f3; border: 1px dashed #bbb; }"
        )
        layout = QVBoxLayout(self)
        lab = QLabel()
        lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lab.setStyleSheet("color: #999; font-size: 12px;")
        if display_page is None or display_page < 1:
            lab.setText("（空）")
        else:
            lab.setText(f"p{display_page}\n（无命中）")
        layout.addWidget(lab)


class HitGrid(QScrollArea):
    """Scrollable grid of hit tiles with lazy image filling."""

    hit_selected = Signal(int)
    hit_activated = Signal(int)  # double-click → browse page
    review_changed = Signal(int, object)
    viewport_needs_render = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self._container = QWidget()
        self._grid = QGridLayout(self._container)
        self._grid.setSpacing(8)
        self.setWidget(self._container)

        self._hits: list[Hit] = []
        self._tiles: dict[int, HitTile] = {}
        self._filter_ids: set[int] | None = None
        self._camera = CameraSettings()
        self._page_offset = 0
        self._selected: int | None = None
        self._placeholder = QLabel("暂无命中")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._grid.addWidget(self._placeholder, 0, 0)

        self.verticalScrollBar().valueChanged.connect(lambda _: self.request_visible_render())

    def set_camera(self, camera: CameraSettings) -> None:
        self._camera = camera
        for tile in self._tiles.values():
            tile.setFixedSize(QSize(camera.tile_w + 20, camera.tile_h + 60))

    def set_page_offset(self, offset: int) -> None:
        rebuild = offset != self._page_offset and self._camera.view_mode == ViewMode.BOOK
        self._page_offset = offset
        for tile in self._tiles.values():
            tile.set_page_offset(offset)
        if rebuild:
            self._rebuild()

    def set_hits(self, hits: list[Hit], filter_ids: set[int] | None = None) -> None:
        self._hits = hits
        self._filter_ids = filter_ids
        self._rebuild()

    def set_filter(self, filter_ids: set[int] | None) -> None:
        self._filter_ids = filter_ids
        self._rebuild()

    @property
    def filter_ids(self) -> set[int] | None:
        return self._filter_ids

    def visible_hits(self) -> list[Hit]:
        if self._filter_ids is None:
            return list(self._hits)
        return [h for h in self._hits if h.hit_id in self._filter_ids]

    def get_hit(self, hit_id: int) -> Hit | None:
        for h in self._hits:
            if h.hit_id == hit_id:
                return h
        return None

    def update_hit_review(self, hit_id: int, reviewed: bool | None) -> None:
        for h in self._hits:
            if h.hit_id == hit_id:
                h.reviewed = reviewed
                break
        tile = self._tiles.get(hit_id)
        if tile:
            h = self.get_hit(hit_id)
            if h:
                tile.update_hit(h, self._page_offset)

    def _clear_grid(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        self._tiles.clear()

    def _make_tile(self, hit: Hit) -> HitTile:
        tile = HitTile(hit, page_offset=self._page_offset)
        tile.setFixedSize(QSize(self._camera.tile_w + 20, self._camera.tile_h + 60))
        tile.clicked.connect(self._on_tile_clicked)
        tile.double_clicked.connect(self.hit_activated.emit)
        tile.review_changed.connect(self.review_changed.emit)
        if self._selected == hit.hit_id:
            tile.set_selected(True)
        self._tiles[hit.hit_id] = tile
        return tile

    def _empty_slot(self, display_page: int | None) -> _EmptyPageSlot:
        return _EmptyPageSlot(
            display_page, self._camera.tile_w, self._camera.tile_h
        )

    def _rebuild_book(self, hits: list[Hit]) -> None:
        """Two columns: left = even display page, right = left + 1; empty if no hit."""
        by_spread: dict[int, tuple[list[Hit], list[Hit]]] = defaultdict(lambda: ([], []))
        for hit in hits:
            disp = to_display_page(hit.page, self._page_offset)
            left = spread_left_page(disp)
            left_hits, right_hits = by_spread[left]
            if disp % 2 == 0:
                left_hits.append(hit)
            else:
                right_hits.append(hit)

        row = 0
        for left_page in sorted(by_spread.keys()):
            left_hits, right_hits = by_spread[left_page]
            right_page = left_page + 1
            n = max(len(left_hits), len(right_hits), 1)
            for i in range(n):
                if i < len(left_hits):
                    self._grid.addWidget(self._make_tile(left_hits[i]), row, 0)
                else:
                    # page 0 means "no verso" (e.g. before page 1)
                    slot_page = left_page if left_page >= 1 else None
                    self._grid.addWidget(self._empty_slot(slot_page), row, 0)
                if i < len(right_hits):
                    self._grid.addWidget(self._make_tile(right_hits[i]), row, 1)
                else:
                    self._grid.addWidget(self._empty_slot(right_page), row, 1)
                row += 1

    def _rebuild_linear(self, hits: list[Hit]) -> None:
        lanes = max(1, self._camera.columns)
        for i, hit in enumerate(hits):
            tile = self._make_tile(hit)
            if self._camera.layout == LayoutMode.COLUMN:
                c, r = divmod(i, lanes)
            else:
                r, c = divmod(i, lanes)
            self._grid.addWidget(tile, r, c)

    def _rebuild(self) -> None:
        self._clear_grid()
        hits = self.visible_hits()
        if not hits:
            ph = QLabel("暂无命中")
            ph.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._grid.addWidget(ph, 0, 0)
            return

        if self._camera.view_mode == ViewMode.BOOK:
            self._rebuild_book(hits)
        else:
            self._rebuild_linear(hits)

        self.request_visible_render()

    def _on_tile_clicked(self, hit_id: int) -> None:
        self._selected = hit_id
        for hid, tile in self._tiles.items():
            tile.set_selected(hid == hit_id)
        self.hit_selected.emit(hit_id)

    def update_tile_pixmap(self, hit_id: int, pixmap: QPixmap) -> None:
        tile = self._tiles.get(hit_id)
        if tile:
            tile.set_pixmap(pixmap)

    def visible_hit_ids_needing_images(self) -> list[int]:
        if not self._tiles:
            return []
        vp = self.viewport().rect()
        top_left = self._container.mapFrom(self.viewport(), vp.topLeft())
        bottom_right = self._container.mapFrom(self.viewport(), vp.bottomRight())
        view_rect = QRect(top_left, bottom_right).adjusted(0, -300, 0, 300)
        needed = []
        for hid, tile in self._tiles.items():
            if view_rect.intersects(tile.geometry()):
                pm = tile.image_label.pixmap()
                if pm is None or pm.isNull():
                    needed.append(hid)
        if not needed:
            for hid, tile in self._tiles.items():
                if view_rect.intersects(tile.geometry()):
                    needed.append(hid)
        return needed

    def request_visible_render(self) -> None:
        self.viewport_needs_render.emit(self.visible_hit_ids_needing_images())

    def force_rerender_all_visible(self) -> None:
        """Clear pixmaps and re-request (after camera change)."""
        for tile in self._tiles.values():
            tile.image_label.clear()
        self.request_visible_render()
