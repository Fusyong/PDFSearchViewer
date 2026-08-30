"""Page browse view with SumatraPDF-like zoom and pick tools."""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import Qt, Signal, QEvent, QPoint, QRect
from PySide6.QtGui import (
    QColor,
    QImage,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
    QShortcut,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..models import BBox, CharInfo, DocumentIndex, Hit, strip_font_subset
from ..page_numbers import to_display_page, to_pdf_page
from ..renderer import PdfRenderSession


class ZoomMode(str, Enum):
    FIT_PAGE = "fit_page"
    ACTUAL = "actual"
    FIT_WIDTH = "fit_width"
    FIT_CONTENT = "fit_content"
    CUSTOM = "custom"


class PickMode(str, Enum):
    NONE = "none"
    STYLE = "style"
    REGION = "region"


class _PageCanvas(QLabel):
    clicked_pdf = Signal(float, float)
    region_dragged = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.setMouseTracking(True)
        self.pick_mode = PickMode.NONE
        self._zoom = 1.0
        self._origin = (0.0, 0.0)
        # PDF page bounds (x0, y0, x1, y1); used to clamp region picks
        self._page_bounds: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
        self._dragging = False
        self._a: QPoint | None = None
        self._b: QPoint | None = None
        self._highlights: list[BBox] = []
        self._base: QImage | None = None

    def set_page_image(
        self,
        image: QImage,
        zoom: float,
        origin: tuple[float, float] = (0.0, 0.0),
        highlights: list[BBox] | None = None,
        page_bounds: tuple[float, float, float, float] | None = None,
    ) -> None:
        self._base = image
        self._zoom = zoom
        self._origin = origin
        self._highlights = highlights or []
        if page_bounds is not None:
            self._page_bounds = page_bounds
        elif image is not None and not image.isNull() and zoom > 0:
            self._page_bounds = (0.0, 0.0, image.width() / zoom, image.height() / zoom)
        else:
            self._page_bounds = (0.0, 0.0, 0.0, 0.0)
        self._paint()

    def _paint(self) -> None:
        if self._base is None:
            self.clear()
            return
        img = self._base.copy()
        p = QPainter(img)
        ox, oy = self._origin
        z = self._zoom
        p.setPen(QPen(QColor(255, 80, 0, 220), 2))
        for bb in self._highlights:
            x0, y0 = (bb[0] - ox) * z, (bb[1] - oy) * z
            w, h = (bb[2] - bb[0]) * z, (bb[3] - bb[1]) * z
            p.fillRect(int(x0), int(y0), max(1, int(w)), max(1, int(h)), QColor(255, 200, 0, 70))
            p.drawRect(int(x0), int(y0), max(1, int(w)), max(1, int(h)))
        if self._dragging and self._a and self._b:
            r = QRect(self._a, self._b).normalized()
            p.setPen(QPen(QColor(30, 100, 220), 1, Qt.PenStyle.DashLine))
            p.fillRect(r, QColor(30, 100, 220, 40))
            p.drawRect(r)
        p.end()
        self.setPixmap(QPixmap.fromImage(img))
        self.adjustSize()

    def _to_pdf(self, pos: QPoint) -> tuple[float, float]:
        """Map widget pos to PDF pts; clamp to page bounds (outside becomes edge)."""
        ox, oy = self._origin
        x = ox + pos.x() / self._zoom
        y = oy + pos.y() / self._zoom
        x0, y0, x1, y1 = self._page_bounds
        if x1 > x0 and y1 > y0:
            x = min(max(x, x0), x1)
            y = min(max(y, y0), y1)
        return x, y

    def begin_region_drag(self, pos: QPoint) -> None:
        """Start region drag at widget-local pos (may be outside the page image)."""
        if self.pick_mode != PickMode.REGION:
            return
        self._dragging = True
        self._a = self._b = pos
        self._paint()
        self.grabMouse()

    def _end_region_drag(self, end: QPoint) -> None:
        if QWidget.mouseGrabber() is self:
            self.releaseMouse()
        if not (self._dragging and self._a):
            self._dragging = False
            self._a = self._b = None
            self._paint()
            return
        self._dragging = False
        self._b = end
        r = QRect(self._a, self._b).normalized()
        self._a = self._b = None
        if r.width() >= 3 and r.height() >= 3:
            x0, y0 = self._to_pdf(r.topLeft())
            x1, y1 = self._to_pdf(r.bottomRight())
            self.region_dragged.emit((x0, y0, x1, y1))
        self._paint()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        pt = event.position().toPoint()
        if self.pick_mode == PickMode.REGION:
            self.begin_region_drag(pt)
        elif self.pick_mode == PickMode.STYLE:
            self.clicked_pdf.emit(*self._to_pdf(pt))
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._dragging:
            self._b = event.position().toPoint()
            self._paint()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._end_region_drag(event.position().toPoint())
        super().mouseReleaseEvent(event)


class PageView(QWidget):
    style_picked = Signal(str, float, int)
    region_picked = Signal(object)
    page_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._session: PdfRenderSession | None = None
        self._index: DocumentIndex | None = None
        self._hits: list[Hit] = []
        self._page = 0
        self._offset = 0
        self._zoom_mode = ZoomMode.FIT_PAGE
        self._custom_zoom = 1.25
        self._continuous = True
        self._focus: BBox | None = None

        root = QVBoxLayout(self)
        bar = QHBoxLayout()

        self.page_spin = QSpinBox()
        self.page_spin.setRange(1, 1)
        self.page_spin.valueChanged.connect(self._on_page_spin)
        bar.addWidget(QLabel("页"))
        bar.addWidget(self.page_spin)

        self.zoom_combo = QComboBox()
        for label, mode in (
            ("适合整页", ZoomMode.FIT_PAGE),
            ("适合页宽", ZoomMode.FIT_WIDTH),
            ("适合内容", ZoomMode.FIT_CONTENT),
            ("实际大小", ZoomMode.ACTUAL),
        ):
            self.zoom_combo.addItem(label, mode.value)
        self.zoom_combo.setCurrentIndex(0)
        self.zoom_combo.currentIndexChanged.connect(self._on_zoom_combo)
        bar.addWidget(QLabel("视图"))
        bar.addWidget(self.zoom_combo)

        self.btn_style = QToolButton()
        self.btn_style.setText("拾取属性")
        self.btn_style.setCheckable(True)
        self.btn_style.toggled.connect(self._toggle_style)
        bar.addWidget(self.btn_style)

        self.btn_region = QToolButton()
        self.btn_region.setText("框选坐标")
        self.btn_region.setCheckable(True)
        self.btn_region.toggled.connect(self._toggle_region)
        bar.addWidget(self.btn_region)

        self.status = QLabel("")
        bar.addWidget(self.status, stretch=1)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(False)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.canvas = _PageCanvas()
        self.canvas.clicked_pdf.connect(self._on_click)
        self.canvas.region_dragged.connect(self._on_region)
        self.scroll.setWidget(self.canvas)
        self.scroll.viewport().installEventFilter(self)

        root.addLayout(bar)
        root.addWidget(self.scroll, stretch=1)
        self._install_shortcuts()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def eventFilter(self, watched, event):  # noqa: N802
        """Allow region drag to start on empty viewport margins (outside page)."""
        if watched is self.scroll.viewport() and self.canvas.pick_mode == PickMode.REGION:
            if (
                event.type() == QEvent.Type.MouseButtonPress
                and event.button() == Qt.MouseButton.LeftButton
            ):
                local = self.canvas.mapFrom(
                    self.scroll.viewport(), event.position().toPoint()
                )
                self.canvas.begin_region_drag(local)
                return True
        return super().eventFilter(watched, event)

    def _install_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+0"), self, lambda: self._set_zoom(ZoomMode.FIT_PAGE))
        QShortcut(QKeySequence("Ctrl+1"), self, lambda: self._set_zoom(ZoomMode.ACTUAL, 1.0))
        QShortcut(QKeySequence("Ctrl+2"), self, lambda: self._set_zoom(ZoomMode.FIT_WIDTH))
        QShortcut(QKeySequence("Ctrl+3"), self, lambda: self._set_zoom(ZoomMode.FIT_CONTENT))
        QShortcut(QKeySequence("+"), self, self._zoom_in)
        QShortcut(QKeySequence("-"), self, self._zoom_out)
        QShortcut(QKeySequence("Ctrl+="), self, self._zoom_in)
        QShortcut(QKeySequence("Ctrl+-"), self, self._zoom_out)
        QShortcut(QKeySequence("z"), self, self._cycle_zoom)
        QShortcut(QKeySequence("c"), self, self._toggle_continuous)
        QShortcut(QKeySequence(Qt.Key.Key_PageDown), self, lambda: self.goto_page(self._page + 1))
        QShortcut(QKeySequence(Qt.Key.Key_PageUp), self, lambda: self.goto_page(self._page - 1))

    def set_session(
        self, session: PdfRenderSession | None, index: DocumentIndex | None = None
    ) -> None:
        self._session = session
        self._index = index
        if session:
            self._sync_range()
            self.goto_page(0)
        else:
            self.canvas.set_page_image(QImage(), 1.0)
            self.status.setText("")

    def set_page_offset(self, offset: int) -> None:
        self._offset = offset
        self._sync_range()
        self.page_spin.blockSignals(True)
        self.page_spin.setValue(to_display_page(self._page, offset))
        self.page_spin.blockSignals(False)
        self._update_status()

    def set_hits(self, hits: list[Hit]) -> None:
        self._hits = hits
        self._render()

    def goto_page(self, pdf_page: int, focus_bbox: BBox | None = None) -> None:
        if not self._session:
            return
        pdf_page = max(0, min(self._session.page_count - 1, pdf_page))
        self._page = pdf_page
        self._focus = focus_bbox
        self.page_spin.blockSignals(True)
        self.page_spin.setValue(to_display_page(pdf_page, self._offset))
        self.page_spin.blockSignals(False)
        self._render()
        self.page_changed.emit(pdf_page)
        if focus_bbox:
            self._scroll_to(focus_bbox)

    def goto_hit(self, hit: Hit) -> None:
        self.goto_page(hit.page, focus_bbox=hit.bbox)

    def _sync_range(self) -> None:
        if not self._session:
            self.page_spin.setRange(1, 1)
            return
        lo = to_display_page(0, self._offset)
        hi = to_display_page(self._session.page_count - 1, self._offset)
        self.page_spin.setRange(min(lo, hi), max(lo, hi))

    def _on_page_spin(self, display: int) -> None:
        self.goto_page(to_pdf_page(display, self._offset))

    def _on_zoom_combo(self, *_args) -> None:
        self._zoom_mode = ZoomMode(self.zoom_combo.currentData())
        self._render()

    def _set_zoom(self, mode: ZoomMode, custom: float | None = None) -> None:
        if custom is not None:
            self._custom_zoom = custom
        self._zoom_mode = mode
        idx = self.zoom_combo.findData(mode.value)
        if idx >= 0:
            self.zoom_combo.blockSignals(True)
            self.zoom_combo.setCurrentIndex(idx)
            self.zoom_combo.blockSignals(False)
        self._render()

    def _zoom_in(self) -> None:
        self._custom_zoom = min(8.0, self._effective_zoom() * 1.25)
        self._zoom_mode = ZoomMode.CUSTOM
        self._render()

    def _zoom_out(self) -> None:
        self._custom_zoom = max(0.25, self._effective_zoom() / 1.25)
        self._zoom_mode = ZoomMode.CUSTOM
        self._render()

    def _cycle_zoom(self) -> None:
        order = [ZoomMode.FIT_PAGE, ZoomMode.FIT_WIDTH, ZoomMode.FIT_CONTENT]
        try:
            nxt = order[(order.index(self._zoom_mode) + 1) % len(order)]
        except ValueError:
            nxt = ZoomMode.FIT_WIDTH
        self._set_zoom(nxt)

    def _toggle_continuous(self) -> None:
        self._continuous = not self._continuous
        self._update_status()

    def _viewport_size(self) -> tuple[int, int]:
        s = self.scroll.viewport().size()
        return max(100, s.width() - 16), max(100, s.height() - 16)

    def _content_bbox(self, page: int) -> BBox | None:
        if self._index:
            chars = [c for c in self._index.chars if c.page == page]
            if chars:
                return (
                    min(c.bbox[0] for c in chars),
                    min(c.bbox[1] for c in chars),
                    max(c.bbox[2] for c in chars),
                    max(c.bbox[3] for c in chars),
                )
        if self._session:
            r = self._session.page_rect(page)
            return (r.x0, r.y0, r.x1, r.y1)
        return None

    def _effective_zoom(self) -> float:
        if not self._session:
            return 1.0
        rect = self._session.page_rect(self._page)
        vw, vh = self._viewport_size()
        m = self._zoom_mode
        if m == ZoomMode.ACTUAL:
            return 1.0
        if m == ZoomMode.CUSTOM:
            return self._custom_zoom
        if m == ZoomMode.FIT_WIDTH:
            return vw / max(1.0, rect.width)
        if m == ZoomMode.FIT_PAGE:
            return min(vw / max(1.0, rect.width), vh / max(1.0, rect.height))
        cb = self._content_bbox(self._page)
        if not cb:
            return min(vw / max(1.0, rect.width), vh / max(1.0, rect.height))
        return min(vw / max(1.0, cb[2] - cb[0]), vh / max(1.0, cb[3] - cb[1]))

    def _highlights(self) -> list[BBox]:
        boxes = [h.bbox for h in self._hits if h.page == self._page]
        if self._focus:
            boxes.append(self._focus)
        return boxes

    def _render(self) -> None:
        if not self._session:
            return
        z = self._effective_zoom()
        img = self._session.render_page(self._page, z)
        rect = self._session.page_rect(self._page)
        self.canvas.set_page_image(
            img,
            z,
            (0.0, 0.0),
            self._highlights(),
            page_bounds=(float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1)),
        )
        self._update_status()

    def _scroll_to(self, bbox: BBox) -> None:
        z = self._effective_zoom()
        cx = (bbox[0] + bbox[2]) / 2 * z
        cy = (bbox[1] + bbox[3]) / 2 * z
        vp = self.scroll.viewport().rect()
        self.scroll.ensureVisible(int(cx), int(cy), vp.width() // 3, vp.height() // 3)

    def _update_status(self) -> None:
        if not self._session:
            self.status.setText("")
            return
        d = to_display_page(self._page, self._offset)
        cont = "连续" if self._continuous else "单页"
        self.status.setText(
            f"{cont} · 图书页 {d}（PDF {self._page + 1}/{self._session.page_count}）"
            f" · {self._zoom_mode.value} · {self._effective_zoom() * 100:.0f}%"
        )

    def _toggle_style(self, on: bool) -> None:
        if on:
            self.btn_region.blockSignals(True)
            self.btn_region.setChecked(False)
            self.btn_region.blockSignals(False)
            self.canvas.pick_mode = PickMode.STYLE
        elif not self.btn_region.isChecked():
            self.canvas.pick_mode = PickMode.NONE

    def _toggle_region(self, on: bool) -> None:
        if on:
            self.btn_style.blockSignals(True)
            self.btn_style.setChecked(False)
            self.btn_style.blockSignals(False)
            self.canvas.pick_mode = PickMode.REGION
        elif not self.btn_style.isChecked():
            self.canvas.pick_mode = PickMode.NONE

    def _char_at(self, x: float, y: float) -> CharInfo | None:
        if not self._index:
            return None
        best: CharInfo | None = None
        best_a = float("inf")
        for ch in self._index.chars:
            if ch.page != self._page:
                continue
            x0, y0, x1, y1 = ch.bbox
            if x0 <= x <= x1 and y0 <= y <= y1:
                a = (x1 - x0) * (y1 - y0)
                if a < best_a:
                    best_a, best = a, ch
        return best

    def _on_click(self, x: float, y: float) -> None:
        if self.canvas.pick_mode != PickMode.STYLE:
            return
        ch = self._char_at(x, y)
        if not ch:
            return
        self.style_picked.emit(strip_font_subset(ch.font), ch.size, ch.color)
        self.btn_style.setChecked(False)
        self.canvas.pick_mode = PickMode.NONE

    def _on_region(self, region: object) -> None:
        self.region_picked.emit(region)
        self.btn_region.setChecked(False)
        self.canvas.pick_mode = PickMode.NONE

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.angleDelta().y() > 0:
                self._zoom_in()
            else:
                self._zoom_out()
            event.accept()
            return
        super().wheelEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._zoom_mode in (ZoomMode.FIT_WIDTH, ZoomMode.FIT_PAGE, ZoomMode.FIT_CONTENT):
            self._render()
