"""One-line hit summary. Overflow is elided; the tooltip keeps the full record."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget

from ..models import Hit
from ..normalize import color_to_hex
from ..page_numbers import to_display_page
from ..stats import mark_label


@dataclass(frozen=True, slots=True)
class HitDetailParts:
    """Fixed ends of the one-line summary, the shrinkable quote, and the hover text."""

    head: str
    quote: str
    tail: str
    full: str

    @property
    def line(self) -> str:
        return f"{self.head}「{self.quote}」{self.tail}"


def _mark_line(hit: Hit) -> str:
    return f"标记: {mark_label(hit.mark)}"


def format_hit_detail(
    hit: Hit,
    display_page: int,
    *,
    entry_line: int | None = None,
    entry_pattern: str | None = None,
) -> HitDetailParts:
    """Build a short visible line and the complete hover text.

    The line keeps identity and style (page, text, font, size, color).
    Normalized form, raw font name, box, and character span stay in ``full``.
    """
    labels: list[str] = []
    if entry_line is not None:
        labels.append(f"条目 {entry_line}")
    labels.extend(
        [
            f"#{hit.hit_id}",
            f"图书页 {display_page}",
            f"PDF {hit.page + 1}",
        ]
    )
    head = " · ".join(labels) + " · "
    tail = f" · {hit.font_display} {hit.size:.1f}pt {color_to_hex(hit.color)}"
    quote = " ".join(hit.text.split())

    lines: list[str] = []
    if entry_line is not None:
        lines.append(f"条目 第 {entry_line} 行: {entry_pattern or ''}")
    lines.extend(
        [
            f"命中 #{hit.hit_id}",
            f"图书页 {display_page}（PDF 第 {hit.page + 1} 页）",
            f"原文: {hit.text}",
            f"规范化: {hit.normalized_text}",
            f"字体: {hit.font_display} ({hit.font})",
            f"字号: {hit.size:.2f} pt",
            f"字色: {color_to_hex(hit.color)}",
            f"bbox: {hit.bbox}",
            f"字符范围: [{hit.char_start}, {hit.char_end})",
            _mark_line(hit),
        ]
    )
    return HitDetailParts(head=head, quote=quote, tail=tail, full="\n".join(lines))


def tooltip_html(full: str) -> str:
    """Escape hover text and wrap it so a long match does not become one huge line."""
    body = escape(full.replace("\r\n", "\n").replace("\r", "\n")).replace("\n", "<br>")
    return f'<table width="420"><tr><td>{body}</td></tr></table>'


def fit_detail_line(parts: HitDetailParts, width: int, advance) -> str:
    """Fit ``parts`` into ``width`` pixels.

    ``advance(text) -> int`` is the rendered width of ``text``.
    The matched text is shortened first. Style at the end stays while it fits.
    A non-positive width means layout has not run yet, so the full line is kept.
    """
    if width <= 0:
        return parts.line
    open_q, close_q = "「", "」"
    fixed = advance(parts.head) + advance(open_q) + advance(close_q) + advance(parts.tail)
    avail = width - fixed
    if avail >= advance(parts.quote):
        return parts.line
    if avail >= advance("…"):
        shown = _elide_end(parts.quote, avail, advance)
        return f"{parts.head}{open_q}{shown}{close_q}{parts.tail}"
    return _elide_end(parts.line, width, advance)


def _elide_end(text: str, width: int, advance) -> str:
    if width <= 0:
        return ""
    if advance(text) <= width:
        return text
    ellipsis = "…"
    if advance(ellipsis) > width:
        return ""
    best = ""
    lo, hi = 0, len(text)
    while lo <= hi:
        mid = (lo + hi) // 2
        candidate = text[:mid] + ellipsis
        if advance(candidate) <= width:
            best = candidate
            lo = mid + 1
        else:
            hi = mid - 1
    return best or ellipsis


class _ShrinkingLabel(QLabel):
    """Single-line label that yields width to its neighbors instead of pushing them."""

    def __init__(self, on_resize, parent=None):
        super().__init__(parent)
        self._on_resize = on_resize
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

    def sizeHint(self):
        hint = super().sizeHint()
        hint.setWidth(0)
        return hint

    def minimumSizeHint(self):
        hint = super().minimumSizeHint()
        hint.setWidth(0)
        return hint

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._on_resize()


class HitDetailBar(QWidget):
    """``命中详情`` and the current hit on one line."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hit: Hit | None = None
        self._page_offset = 0
        self._entry_line: int | None = None
        self._entry_pattern: str | None = None
        self._parts: HitDetailParts | None = None
        self._refreshing = False

        self._caption = QLabel("命中详情")
        self._value = _ShrinkingLabel(self._apply_line, self)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(self._caption)
        row.addWidget(self._value, 1)
        self.clear()

    def clear(self) -> None:
        self._hit = None
        self._entry_line = None
        self._entry_pattern = None
        self._parts = None
        self._value.setStyleSheet("color: #777;")
        self._value.setText("未选择")
        self._set_tip("")

    def show_hit(
        self,
        hit: Hit,
        *,
        page_offset: int,
        entry_line: int | None = None,
        entry_pattern: str | None = None,
    ) -> None:
        self._hit = hit
        self._page_offset = page_offset
        self._entry_line = entry_line
        self._entry_pattern = entry_pattern
        self._value.setStyleSheet("")
        self._rebuild()

    def refresh(self) -> None:
        if self._hit is not None:
            self._rebuild()

    def set_page_offset(self, offset: int) -> None:
        self._page_offset = offset
        if self._hit is not None:
            self._rebuild()

    def shown_text(self) -> str:
        return self._value.text()

    def _rebuild(self) -> None:
        assert self._hit is not None
        display_page = to_display_page(self._hit.page, self._page_offset)
        self._parts = format_hit_detail(
            self._hit,
            display_page,
            entry_line=self._entry_line,
            entry_pattern=self._entry_pattern,
        )
        self._set_tip(tooltip_html(self._parts.full))
        self._apply_line()

    def _apply_line(self) -> None:
        if self._parts is None or self._refreshing:
            return
        self._refreshing = True
        try:
            width = self._value.contentsRect().width()
            text = fit_detail_line(self._parts, width, self._value.fontMetrics().horizontalAdvance)
            if text != self._value.text():
                self._value.setText(text)
        finally:
            self._refreshing = False

    def _set_tip(self, tip: str) -> None:
        self.setToolTip(tip)
        self._caption.setToolTip(tip)
        self._value.setToolTip(tip)
