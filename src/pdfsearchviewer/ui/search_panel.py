from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..models import BBox, NormalizeOptions, SearchQuery, StyleFilter, StyleMatchMode
from ..normalize import color_to_hex, parse_hex_color
from ..page_numbers import to_display_page, to_pdf_page


class SearchPanel(QWidget):
    search_requested = Signal(object)  # SearchQuery — text search only
    filters_changed = Signal()  # presentation filters (style / region / page)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        self.pattern = QLineEdit()
        self.pattern.setPlaceholderText("正则或普通文本…（\\y \\c \\p \\j 等见帮助）")
        self.is_regex = QCheckBox("正则表达式")
        self.is_regex.setChecked(True)
        self.is_regex.setToolTip(
            "使用 Python re 方言。本地扩展：\\y/\\Y 拼音，\\c/\\C 汉字，"
            "\\p/\\P 中文标点，\\j/\\J 汉字数字。"
            "详见菜单「帮助 → 本地字符集转义…」。"
        )
        self.case_insensitive = QCheckBox("忽略大小写")
        self.whole_word = QCheckBox("整词匹配")
        self.whole_word.setToolTip(
            "匹配两侧不能是英文字母、数字或下划线（便于整词搜英文/编号；连续汉字中仍可命中）。"
        )
        self.dotall = QCheckBox("忽略单个换行")
        self.dotall.setToolTip(
            "匹配时去掉单个换行，便于搜跨行词语；连续两个及以上换行（空行）仍保留为分隔，可用 $ 锚定。"
        )
        self.strip_ws = QCheckBox("忽略空白")
        self.strip_ws.setChecked(False)
        self.strip_ws.setToolTip(
            "忽略搜索字符串和页面文本两侧的空白字符后再匹配。"
        )

        opts = QVBoxLayout()
        opts.addWidget(self.is_regex)
        opts.addWidget(self.case_insensitive)
        opts.addWidget(self.whole_word)
        opts.addWidget(self.dotall)
        opts.addWidget(self.strip_ws)

        style_box = QGroupBox("样式过滤")
        form = QFormLayout(style_box)
        self.use_style = QCheckBox("启用样式过滤")
        self.font_edit = QLineEdit()
        self.font_edit.setPlaceholderText("字体名子串，逗号分隔")
        self.size_min = QDoubleSpinBox()
        self.size_min.setRange(0, 200)
        self.size_min.setSpecialValueText("不限")
        self.size_min.setValue(0)
        self.size_max = QDoubleSpinBox()
        self.size_max.setRange(0, 200)
        self.size_max.setSpecialValueText("不限")
        self.size_max.setValue(0)
        self.color_edit = QLineEdit()
        self.color_edit.setPlaceholderText("如 #000000，逗号分隔")
        self.match_mode = QComboBox()
        self.match_mode.addItem("多数字符", StyleMatchMode.MAJORITY.value)
        self.match_mode.addItem("首个 span", StyleMatchMode.FIRST_SPAN.value)
        self.match_mode.addItem("全部字符", StyleMatchMode.ALL.value)
        self.match_mode.addItem("任一字符", StyleMatchMode.ANY.value)
        self._style_widgets = (
            self.font_edit,
            self.size_min,
            self.size_max,
            self.color_edit,
            self.match_mode,
        )
        for w in self._style_widgets:
            w.setEnabled(False)
        self.use_style.toggled.connect(self._on_style_toggled)
        form.addRow(self.use_style)
        form.addRow("字体", self.font_edit)
        form.addRow("字号 ≥", self.size_min)
        form.addRow("字号 ≤", self.size_max)
        form.addRow("字色", self.color_edit)
        form.addRow("匹配方式", self.match_mode)

        region_box = QGroupBox("坐标过滤")
        region_form = QFormLayout(region_box)
        self.use_region = QCheckBox("启用坐标过滤")
        self.region_x0 = QDoubleSpinBox()
        self.region_y0 = QDoubleSpinBox()
        self.region_x1 = QDoubleSpinBox()
        self.region_y1 = QDoubleSpinBox()
        for sp in (self.region_x0, self.region_y0, self.region_x1, self.region_y1):
            sp.setRange(-10000, 10000)
            sp.setDecimals(2)
            sp.setSingleStep(1.0)
            sp.setEnabled(False)
        self.use_region.toggled.connect(self._on_region_toggled)
        region_form.addRow(self.use_region)
        region_form.addRow("x0", self.region_x0)
        region_form.addRow("y0", self.region_y0)
        region_form.addRow("x1", self.region_x1)
        region_form.addRow("y1", self.region_y1)

        page_box = QGroupBox("页码")
        page_form = QFormLayout(page_box)
        self.page_offset = QSpinBox()
        self.page_offset.setRange(-99999, 99999)
        self.page_offset.setValue(0)
        self.page_offset.setToolTip(
            "图书页码 = PDF页（1-based）+ 偏置。可为负数。"
            "用户看到与输入的均为偏置后的页码。"
        )
        page_row = QHBoxLayout()
        self.page_from = QSpinBox()
        self.page_from.setRange(-99999, 99999)
        self.page_from.setValue(1)
        self.page_to = QSpinBox()
        self.page_to.setRange(-99999, 99999)
        self.page_to.setValue(1)
        self._page_count = 0
        self._default_page_to: int | None = None
        self.use_page_range = QCheckBox("页码过滤")
        page_row.addWidget(self.use_page_range)
        page_row.addWidget(QLabel("从"))
        page_row.addWidget(self.page_from)
        page_row.addWidget(QLabel("到"))
        page_row.addWidget(self.page_to)
        page_form.addRow("页码偏置", self.page_offset)
        page_form.addRow(page_row)

        self.search_btn = QPushButton("搜索")
        self.search_btn.clicked.connect(self._emit_search)
        self.pattern.returnPressed.connect(self._emit_search)

        layout.addWidget(QLabel("搜索"))
        layout.addWidget(self.pattern)
        layout.addLayout(opts)
        layout.addWidget(style_box)
        layout.addWidget(region_box)
        layout.addWidget(page_box)
        layout.addWidget(self.search_btn)
        layout.addStretch(1)

        self.page_offset.valueChanged.connect(self._on_offset_sync_page_to)
        self._connect_filter_signals()

    def _connect_filter_signals(self) -> None:
        self.use_style.toggled.connect(lambda *_: self.filters_changed.emit())
        self.use_region.toggled.connect(lambda *_: self.filters_changed.emit())
        self.use_page_range.toggled.connect(lambda *_: self.filters_changed.emit())
        for w in (
            self.size_min,
            self.size_max,
            self.region_x0,
            self.region_y0,
            self.region_x1,
            self.region_y1,
            self.page_from,
            self.page_to,
        ):
            w.valueChanged.connect(lambda *_: self.filters_changed.emit())
        self.font_edit.editingFinished.connect(self.filters_changed.emit)
        self.color_edit.editingFinished.connect(self.filters_changed.emit)
        self.match_mode.currentIndexChanged.connect(
            lambda *_: self.filters_changed.emit()
        )

    def set_page_count(self, page_count: int) -> None:
        """Remember document length; set page-range end to last display page."""
        self._page_count = max(0, int(page_count))
        self._apply_page_to_max()

    def _display_page_max(self) -> int | None:
        if self._page_count <= 0:
            return None
        return to_display_page(self._page_count - 1, self.page_offset_value())

    def _apply_page_to_max(self) -> None:
        hi = self._display_page_max()
        if hi is None:
            return
        self.page_to.blockSignals(True)
        self.page_to.setValue(hi)
        self.page_to.blockSignals(False)
        self._default_page_to = hi

    def _on_offset_sync_page_to(self, *_args) -> None:
        hi = self._display_page_max()
        if hi is None:
            return
        # Keep following the document end while user has not overridden it
        if self._default_page_to is None or self.page_to.value() == self._default_page_to:
            self.page_to.blockSignals(True)
            self.page_to.setValue(hi)
            self.page_to.blockSignals(False)
        self._default_page_to = hi

    def page_offset_value(self) -> int:
        return int(self.page_offset.value())

    def _on_style_toggled(self, checked: bool) -> None:
        for w in self._style_widgets:
            w.setEnabled(checked)

    def _on_region_toggled(self, checked: bool) -> None:
        for sp in (self.region_x0, self.region_y0, self.region_x1, self.region_y1):
            sp.setEnabled(checked)

    def apply_region(self, region: BBox, *, apply: bool = False) -> None:
        """Fill region filter from a picked PDF-coordinate box."""
        x0, y0, x1, y1 = region
        if x0 > x1:
            x0, x1 = x1, x0
        if y0 > y1:
            y0, y1 = y1, y0
        self.use_region.blockSignals(True)
        self.use_region.setChecked(True)
        self.use_region.blockSignals(False)
        self._on_region_toggled(True)
        for sp, val in (
            (self.region_x0, x0),
            (self.region_y0, y0),
            (self.region_x1, x1),
            (self.region_y1, y1),
        ):
            sp.blockSignals(True)
            sp.setValue(val)
            sp.blockSignals(False)
        if apply:
            self.filters_changed.emit()

    def apply_style_pick(
        self,
        *,
        font: str | None = None,
        size: float | None = None,
        color: int | None = None,
        apply: bool = False,
    ) -> None:
        """Fill style fields from a text property pick."""
        self.use_style.blockSignals(True)
        self.use_style.setChecked(True)
        self.use_style.blockSignals(False)
        self._on_style_toggled(True)
        if font:
            self.font_edit.blockSignals(True)
            self.font_edit.setText(font)
            self.font_edit.blockSignals(False)
        if size is not None:
            self.size_min.blockSignals(True)
            self.size_max.blockSignals(True)
            self.size_min.setValue(max(0.0, size - 0.05))
            self.size_max.setValue(size + 0.05)
            self.size_min.blockSignals(False)
            self.size_max.blockSignals(False)
        if color is not None:
            self.color_edit.blockSignals(True)
            self.color_edit.setText(color_to_hex(color))
            self.color_edit.blockSignals(False)
        if apply:
            self.filters_changed.emit()

    def _read_region(self) -> BBox | None:
        if not self.use_region.isChecked():
            return None
        x0 = self.region_x0.value()
        y0 = self.region_y0.value()
        x1 = self.region_x1.value()
        y1 = self.region_y1.value()
        if x0 > x1:
            x0, x1 = x1, x0
        if y0 > y1:
            y0, y1 = y1, y0
        if abs(x1 - x0) < 1e-6 and abs(y1 - y0) < 1e-6:
            return None
        return (x0, y0, x1, y1)

    def build_search_query(self) -> SearchQuery:
        """Text search only — style / region / page are not included."""
        return SearchQuery(
            pattern=self.pattern.text(),
            is_regex=self.is_regex.isChecked(),
            case_insensitive=self.case_insensitive.isChecked(),
            dotall=self.dotall.isChecked(),
            whole_word=self.whole_word.isChecked(),
            normalize=NormalizeOptions(
                strip_whitespace=self.strip_ws.isChecked(),
                collapse_single_newlines=self.dotall.isChecked(),
            ),
        )

    def presentation_filters(self) -> tuple[StyleFilter, int | None, int | None]:
        """Style / region / page range for display filtering."""
        fonts: list[str] = []
        colors: list[int] = []
        size_min = size_max = None
        match_mode = StyleMatchMode.MAJORITY
        if self.use_style.isChecked():
            fonts = [f.strip() for f in self.font_edit.text().split(",") if f.strip()]
            for part in self.color_edit.text().split(","):
                part = part.strip()
                if not part:
                    continue
                c = parse_hex_color(part)
                if c is not None:
                    colors.append(c)
            size_min = self.size_min.value() if self.size_min.value() > 0 else None
            size_max = self.size_max.value() if self.size_max.value() > 0 else None
            match_mode = StyleMatchMode(self.match_mode.currentData())

        offset = self.page_offset_value()
        page_from = page_to = None
        if self.use_page_range.isChecked():
            page_from = to_pdf_page(self.page_from.value(), offset)
            page_to = to_pdf_page(self.page_to.value(), offset)
            if page_to < page_from:
                page_from, page_to = page_to, page_from
            page_from = max(0, page_from)
            page_to = max(0, page_to)

        style = StyleFilter(
            fonts=fonts,
            size_min=size_min,
            size_max=size_max,
            colors=colors,
            region=self._read_region(),
            match_mode=match_mode,
        )
        return style, page_from, page_to

    def build_query(self) -> SearchQuery:
        """Full query snapshot (search + presentation filters) for session save."""
        q = self.build_search_query()
        style, page_from, page_to = self.presentation_filters()
        q.style = style
        q.page_from = page_from
        q.page_to = page_to
        return q

    def _emit_search(self) -> None:
        self.search_requested.emit(self.build_search_query())
