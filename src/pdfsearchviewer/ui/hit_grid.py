from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QRect, QSize
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QScrollArea, QWidget, QGridLayout, QLabel

from ..models import CameraSettings, Hit
from .hit_tile import HitTile


class HitGrid(QScrollArea):
    """Scrollable grid of hit tiles with lazy image filling."""

    hit_selected = Signal(int)
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
        self._selected: int | None = None
        self._placeholder = QLabel("暂无命中")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._grid.addWidget(self._placeholder, 0, 0)

        self.verticalScrollBar().valueChanged.connect(lambda _: self.request_visible_render())

    def set_camera(self, camera: CameraSettings) -> None:
        self._camera = camera
        for tile in self._tiles.values():
            tile.setFixedSize(QSize(camera.tile_w + 20, camera.tile_h + 60))

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
            tile.update_hit(tile.hit if hasattr(tile, "hit") else self.get_hit(hit_id))  # type: ignore[arg-type]
            h = self.get_hit(hit_id)
            if h:
                tile.update_hit(h)

    def _clear_grid(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        self._tiles.clear()

    def _rebuild(self) -> None:
        self._clear_grid()
        hits = self.visible_hits()
        if not hits:
            ph = QLabel("暂无命中")
            ph.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._grid.addWidget(ph, 0, 0)
            return

        cols = max(1, self._camera.columns)
        for i, hit in enumerate(hits):
            tile = HitTile(hit)
            tile.setFixedSize(QSize(self._camera.tile_w + 20, self._camera.tile_h + 60))
            tile.clicked.connect(self._on_tile_clicked)
            tile.review_changed.connect(self.review_changed.emit)
            r, c = divmod(i, cols)
            self._grid.addWidget(tile, r, c)
            self._tiles[hit.hit_id] = tile
            if self._selected == hit.hit_id:
                tile.set_selected(True)

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
        # If none marked needing, still request all visible for refresh after camera change
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
