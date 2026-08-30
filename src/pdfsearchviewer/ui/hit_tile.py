from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ..models import Hit
from ..normalize import color_to_hex
from ..page_numbers import to_display_page


class HitTile(QFrame):
    clicked = Signal(int)
    double_clicked = Signal(int)
    review_changed = Signal(int, object)  # hit_id, bool|None

    def __init__(self, hit: Hit, page_offset: int = 0, parent=None):
        super().__init__(parent)
        self.hit_id = hit.hit_id
        self._page_offset = page_offset
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(QSize(240, 160))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(200, 100)
        self.meta = QLabel()
        self.meta.setWordWrap(True)
        self.meta.setStyleSheet("font-size: 11px;")
        self.ok_cb = QCheckBox("正确")
        self.bad_cb = QCheckBox("有误")
        self.ok_cb.stateChanged.connect(self._on_ok)
        self.bad_cb.stateChanged.connect(self._on_bad)

        row = QWidget()
        hl = QHBoxLayout(row)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.addWidget(self.ok_cb)
        hl.addWidget(self.bad_cb)

        layout.addWidget(self.image_label)
        layout.addWidget(self.meta)
        layout.addWidget(row)
        self.update_hit(hit, page_offset)

    def set_page_offset(self, offset: int) -> None:
        self._page_offset = offset
        if hasattr(self, "hit"):
            self.update_hit(self.hit, offset)

    def update_hit(self, hit: Hit, page_offset: int | None = None) -> None:
        self.hit = hit
        self.hit_id = hit.hit_id
        if page_offset is not None:
            self._page_offset = page_offset
        disp = to_display_page(hit.page, self._page_offset)
        self.meta.setText(
            f"p{disp} | {hit.font_display} {hit.size:.1f}pt "
            f"{color_to_hex(hit.color)}\n{hit.text[:40]}"
        )
        self.ok_cb.blockSignals(True)
        self.bad_cb.blockSignals(True)
        self.ok_cb.setChecked(hit.reviewed is True)
        self.bad_cb.setChecked(hit.reviewed is False)
        self.ok_cb.blockSignals(False)
        self.bad_cb.blockSignals(False)

    def set_pixmap(self, pix: QPixmap) -> None:
        self.image_label.setPixmap(pix)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.hit_id)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(self.hit_id)
        super().mouseDoubleClickEvent(event)

    def set_selected(self, selected: bool) -> None:
        if selected:
            self.setStyleSheet("HitTile { border: 2px solid #d97706; }")
        else:
            self.setStyleSheet("")

    def _on_ok(self, state) -> None:
        if state:
            self.bad_cb.blockSignals(True)
            self.bad_cb.setChecked(False)
            self.bad_cb.blockSignals(False)
            self.review_changed.emit(self.hit_id, True)
        elif not self.bad_cb.isChecked():
            self.review_changed.emit(self.hit_id, None)

    def _on_bad(self, state) -> None:
        if state:
            self.ok_cb.blockSignals(True)
            self.ok_cb.setChecked(False)
            self.ok_cb.blockSignals(False)
            self.review_changed.emit(self.hit_id, False)
        elif not self.ok_cb.isChecked():
            self.review_changed.emit(self.hit_id, None)
