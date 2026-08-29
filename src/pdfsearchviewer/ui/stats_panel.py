from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QHeaderView,
    QAbstractItemView,
)

from ..models import Hit
from ..stats import group_hits, summary_counts


class StatsPanel(QWidget):
    filter_requested = Signal(object)  # set[int] | None

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        self.summary = QLabel("命中: 0")
        self.group_by = QComboBox()
        self.group_by.addItem("按原文形态", "text")
        self.group_by.addItem("按规范化形态", "normalized")
        self.group_by.addItem("按字体", "font")
        self.group_by.addItem("按字号", "size")
        self.group_by.addItem("按字色", "color")
        self.group_by.currentIndexChanged.connect(self._refresh_table)

        top = QHBoxLayout()
        top.addWidget(QLabel("分组"))
        top.addWidget(self.group_by)
        top.addStretch(1)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["分组", "数量"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._on_select)

        self.clear_filter_btn_hint = QLabel("点击行筛选小窗；再点空白取消")
        self.clear_filter_btn_hint.setStyleSheet("color: #666; font-size: 11px;")

        layout.addWidget(self.summary)
        layout.addLayout(top)
        layout.addWidget(self.table)
        layout.addWidget(self.clear_filter_btn_hint)

        self._hits: list[Hit] = []
        self._groups = []

    def set_hits(self, hits: list[Hit]) -> None:
        self._hits = hits
        sc = summary_counts(hits)
        self.summary.setText(
            f"命中 {sc['total']}｜原文形态 {sc['unique_text']}｜"
            f"规范化 {sc['unique_normalized']}｜字体 {sc['unique_font']}｜"
            f"字号 {sc['unique_size']}｜字色 {sc['unique_color']}\n"
            f"复核 ✓{sc['reviewed_ok']} ✗{sc['reviewed_bad']} 未审 {sc['unreviewed']}"
        )
        self._refresh_table()

    def _refresh_table(self) -> None:
        by = self.group_by.currentData()
        self._groups = group_hits(self._hits, by) if self._hits else []
        self.table.setRowCount(len(self._groups))
        for i, g in enumerate(self._groups):
            self.table.setItem(i, 0, QTableWidgetItem(g.label))
            self.table.setItem(i, 1, QTableWidgetItem(str(g.count)))

    def _on_select(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            self.filter_requested.emit(None)
            return
        g = self._groups[rows[0].row()]
        self.filter_requested.emit(set(g.hit_ids))
