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

from ..models import NormalizeOptions, SearchQuery, StyleFilter, StyleMatchMode
from ..normalize import parse_hex_color


class SearchPanel(QWidget):
    search_requested = Signal(object)  # SearchQuery

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        self.pattern = QLineEdit()
        self.pattern.setPlaceholderText("正则或普通文本…")
        self.is_regex = QCheckBox("正则表达式")
        self.is_regex.setChecked(True)
        self.case_insensitive = QCheckBox("忽略大小写")
        self.dotall = QCheckBox(". 匹配换行")
        self.strip_ws = QCheckBox("去掉空白后再匹配（适合图题/编号等体例宽松核对）")
        self.strip_ws.setChecked(False)

        opts = QVBoxLayout()
        opts.addWidget(self.is_regex)
        opts.addWidget(self.case_insensitive)
        opts.addWidget(self.dotall)
        opts.addWidget(self.strip_ws)

        style_box = QGroupBox("样式过滤（可选）")
        form = QFormLayout(style_box)
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
        form.addRow("字体", self.font_edit)
        form.addRow("字号 ≥", self.size_min)
        form.addRow("字号 ≤", self.size_max)
        form.addRow("字色", self.color_edit)
        form.addRow("匹配方式", self.match_mode)

        page_row = QHBoxLayout()
        self.page_from = QSpinBox()
        self.page_from.setRange(0, 99999)
        self.page_from.setSpecialValueText("起")
        self.page_from.setValue(0)
        self.page_to = QSpinBox()
        self.page_to.setRange(0, 99999)
        self.page_to.setSpecialValueText("止")
        self.page_to.setValue(0)
        self.use_page_range = QCheckBox("限定页码（1-based）")
        page_row.addWidget(self.use_page_range)
        page_row.addWidget(QLabel("从"))
        page_row.addWidget(self.page_from)
        page_row.addWidget(QLabel("到"))
        page_row.addWidget(self.page_to)

        self.search_btn = QPushButton("搜索")
        self.search_btn.clicked.connect(self._emit_search)
        self.pattern.returnPressed.connect(self._emit_search)

        layout.addWidget(QLabel("搜索式"))
        layout.addWidget(self.pattern)
        layout.addLayout(opts)
        layout.addWidget(style_box)
        layout.addLayout(page_row)
        layout.addWidget(self.search_btn)
        layout.addStretch(1)

    def build_query(self) -> SearchQuery:
        fonts = [f.strip() for f in self.font_edit.text().split(",") if f.strip()]
        colors: list[int] = []
        for part in self.color_edit.text().split(","):
            part = part.strip()
            if not part:
                continue
            c = parse_hex_color(part)
            if c is not None:
                colors.append(c)

        size_min = self.size_min.value() if self.size_min.value() > 0 else None
        size_max = self.size_max.value() if self.size_max.value() > 0 else None

        page_from = page_to = None
        if self.use_page_range.isChecked():
            page_from = max(0, self.page_from.value() - 1)
            page_to = max(0, self.page_to.value() - 1)
            if page_to < page_from:
                page_from, page_to = page_to, page_from

        return SearchQuery(
            pattern=self.pattern.text(),
            is_regex=self.is_regex.isChecked(),
            case_insensitive=self.case_insensitive.isChecked(),
            dotall=self.dotall.isChecked(),
            normalize=NormalizeOptions(strip_whitespace=self.strip_ws.isChecked()),
            style=StyleFilter(
                fonts=fonts,
                size_min=size_min,
                size_max=size_max,
                colors=colors,
                match_mode=StyleMatchMode(self.match_mode.currentData()),
            ),
            page_from=page_from,
            page_to=page_to,
        )

    def _emit_search(self) -> None:
        self.search_requested.emit(self.build_query())
