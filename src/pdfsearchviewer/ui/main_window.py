from __future__ import annotations

import csv
import json
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
    QTextEdit,
    QListWidget,
    QPushButton,
)

from ..cache import IndexCache
from ..indexer import file_fingerprint, index_pdf
from ..models import CameraSettings, DocumentIndex, Hit, SearchQuery
from ..normalize import color_to_hex
from ..renderer import PdfRenderSession
from ..search_engine import search
from .hit_grid import HitGrid
from .search_panel import SearchPanel
from .stats_panel import StatsPanel


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDFSearchViewer — 印前文字一致性检查")
        self.resize(1400, 900)

        self.cache = IndexCache()
        self.index: DocumentIndex | None = None
        self.hits: list[Hit] = []
        self.camera = CameraSettings()
        self.render_session: PdfRenderSession | None = None
        self.current_search_id: int | None = None
        self._hit_by_id: dict[int, Hit] = {}

        self._build_ui()
        self._build_menu()
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self._flush_render_queue)
        self._pending_render_ids: list[int] = []

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: search + sessions
        left = QWidget()
        left_l = QVBoxLayout(left)
        self.search_panel = SearchPanel()
        self.search_panel.search_requested.connect(self.run_search)
        left_l.addWidget(self.search_panel)
        left_l.addWidget(QLabel("已保存会话"))
        self.session_list = QListWidget()
        self.session_list.itemDoubleClicked.connect(self._load_session)
        left_l.addWidget(self.session_list)
        refresh_btn = QPushButton("刷新会话列表")
        refresh_btn.clicked.connect(self._refresh_sessions)
        left_l.addWidget(refresh_btn)

        # Center: camera + grid + detail
        center = QWidget()
        center_l = QVBoxLayout(center)
        cam_bar = QHBoxLayout()
        self.zoom_spin = QDoubleSpinBox()
        self.zoom_spin.setRange(0.5, 8.0)
        self.zoom_spin.setSingleStep(0.25)
        self.zoom_spin.setValue(self.camera.zoom)
        self.margin_spin = QDoubleSpinBox()
        self.margin_spin.setRange(0, 100)
        self.margin_spin.setValue(self.camera.margin)
        self.pan_x_spin = QDoubleSpinBox()
        self.pan_x_spin.setRange(-500, 500)
        self.pan_x_spin.setValue(0)
        self.pan_y_spin = QDoubleSpinBox()
        self.pan_y_spin.setRange(-500, 500)
        self.pan_y_spin.setValue(0)
        self.tile_w_spin = QSpinBox()
        self.tile_w_spin.setRange(80, 800)
        self.tile_w_spin.setValue(self.camera.tile_w)
        self.tile_h_spin = QSpinBox()
        self.tile_h_spin.setRange(60, 600)
        self.tile_h_spin.setValue(self.camera.tile_h)
        self.cols_spin = QSpinBox()
        self.cols_spin.setRange(1, 12)
        self.cols_spin.setValue(self.camera.columns)

        for w, lab in [
            (self.zoom_spin, "缩放"),
            (self.margin_spin, "边距"),
            (self.pan_x_spin, "平移X"),
            (self.pan_y_spin, "平移Y"),
            (self.tile_w_spin, "窗宽"),
            (self.tile_h_spin, "窗高"),
            (self.cols_spin, "列数"),
        ]:
            cam_bar.addWidget(QLabel(lab))
            cam_bar.addWidget(w)
            w.valueChanged.connect(self._on_camera_changed)

        apply_cam = QPushButton("应用视图")
        apply_cam.clicked.connect(self._apply_camera)
        cam_bar.addWidget(apply_cam)
        cam_bar.addStretch(1)

        self.hit_grid = HitGrid()
        self.hit_grid.hit_selected.connect(self._on_hit_selected)
        self.hit_grid.review_changed.connect(self._on_review)
        self.hit_grid.viewport_needs_render.connect(self._queue_render)

        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setMaximumHeight(140)

        center_l.addLayout(cam_bar)
        center_l.addWidget(self.hit_grid, stretch=1)
        center_l.addWidget(QLabel("命中详情"))
        center_l.addWidget(self.detail)

        # Right: stats
        self.stats_panel = StatsPanel()
        self.stats_panel.filter_requested.connect(self._on_stat_filter)

        splitter.addWidget(left)
        splitter.addWidget(center)
        splitter.addWidget(self.stats_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([320, 800, 280])

        root.addWidget(splitter)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("打开 PDF 开始检查")

    def _build_menu(self) -> None:
        tb = QToolBar("主工具")
        self.addToolBar(tb)
        open_act = QAction("打开 PDF", self)
        open_act.triggered.connect(self.open_pdf)
        export_csv = QAction("导出 CSV", self)
        export_csv.triggered.connect(self.export_csv)
        export_json = QAction("导出 JSON", self)
        export_json.triggered.connect(self.export_json)
        save_sess = QAction("保存会话", self)
        save_sess.triggered.connect(self.save_session)
        tb.addAction(open_act)
        tb.addAction(save_sess)
        tb.addAction(export_csv)
        tb.addAction(export_json)

        menu = self.menuBar().addMenu("文件")
        menu.addAction(open_act)
        menu.addAction(save_sess)
        menu.addAction(export_csv)
        menu.addAction(export_json)

    def open_pdf(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "打开 PDF", "", "PDF (*.pdf)")
        if not path:
            return
        self._load_pdf(path)

    def _load_pdf(self, path: str) -> None:
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            fp = file_fingerprint(path)
            cached = self.cache.get_index(fp)
            if cached and Path(cached.path).exists():
                # Prefer cache if fingerprint matches; update path if moved
                cached.path = str(Path(path).resolve())
                self.index = cached
                self.statusBar().showMessage(f"已从缓存加载索引：{Path(path).name}，{cached.page_count} 页")
            else:
                self.statusBar().showMessage("正在建立索引…")
                QApplication.processEvents()

                def prog(cur, total):
                    self.statusBar().showMessage(f"索引中 {cur}/{total}")
                    QApplication.processEvents()

                self.index = index_pdf(path, progress=prog)
                self.cache.put_index(self.index)
                self.statusBar().showMessage(
                    f"已索引：{Path(path).name}，{self.index.page_count} 页，"
                    f"{len(self.index.chars)} 字符"
                )

            if self.render_session:
                self.render_session.close()
            self.render_session = PdfRenderSession(path)
            self.hits = []
            self.current_search_id = None
            self._hit_by_id = {}
            self.hit_grid.set_hits([])
            self.stats_panel.set_hits([])
            self._refresh_sessions()
        except Exception as e:
            QMessageBox.critical(self, "打开失败", str(e))
        finally:
            QApplication.restoreOverrideCursor()

    def run_search(self, query: SearchQuery) -> None:
        if not self.index:
            QMessageBox.information(self, "提示", "请先打开 PDF")
            return
        if not query.pattern:
            QMessageBox.information(self, "提示", "请输入搜索式")
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.hits = search(self.index, query)
            self._hit_by_id = {h.hit_id: h for h in self.hits}
            self.hit_grid.set_camera(self.camera)
            self.hit_grid.set_hits(self.hits)
            self.stats_panel.set_hits(self.hits)
            self.statusBar().showMessage(f"找到 {len(self.hits)} 处命中")
        except ValueError as e:
            QMessageBox.warning(self, "搜索错误", str(e))
        finally:
            QApplication.restoreOverrideCursor()

    def save_session(self) -> None:
        if not self.index or not self.hits:
            QMessageBox.information(self, "提示", "没有可保存的搜索结果")
            return
        query = self.search_panel.build_query()
        name = query.pattern[:40]
        sid = self.cache.save_search(self.index.fingerprint, query, self.hits, name=name)
        self.current_search_id = sid
        self._refresh_sessions()
        self.statusBar().showMessage(f"已保存会话 #{sid}")

    def _refresh_sessions(self) -> None:
        self.session_list.clear()
        if not self.index:
            return
        for s in self.cache.list_searches(self.index.fingerprint):
            self.session_list.addItem(
                f"#{s['id']} {s['pattern'][:30]} ({s['hit_count']})"
            )
            self.session_list.item(self.session_list.count() - 1).setData(
                Qt.ItemDataRole.UserRole, s["id"]
            )

    def _load_session(self) -> None:
        item = self.session_list.currentItem()
        if not item:
            return
        sid = item.data(Qt.ItemDataRole.UserRole)
        self.hits = self.cache.load_hits(sid)
        self.current_search_id = sid
        self._hit_by_id = {h.hit_id: h for h in self.hits}
        self.hit_grid.set_hits(self.hits)
        self.stats_panel.set_hits(self.hits)
        self.statusBar().showMessage(f"已加载会话 #{sid}，{len(self.hits)} 命中")

    def _on_camera_changed(self, *_args) -> None:
        pass

    def _apply_camera(self) -> None:
        self.camera = CameraSettings(
            zoom=self.zoom_spin.value(),
            margin=self.margin_spin.value(),
            pan_x=self.pan_x_spin.value(),
            pan_y=self.pan_y_spin.value(),
            tile_w=self.tile_w_spin.value(),
            tile_h=self.tile_h_spin.value(),
            columns=self.cols_spin.value(),
        )
        self.hit_grid.set_camera(self.camera)
        # rebuild layout for column change
        self.hit_grid.set_hits(self.hits, self.hit_grid.filter_ids)
        self.hit_grid.force_rerender_all_visible()

    def _queue_render(self, hit_ids: list) -> None:
        self._pending_render_ids = list(dict.fromkeys(hit_ids))
        self._render_timer.start(30)

    def _flush_render_queue(self) -> None:
        if not self.render_session:
            return
        for hid in self._pending_render_ids[:24]:
            hit = self._hit_by_id.get(hid)
            if not hit:
                continue
            try:
                img = self.render_session.render(hit, self.camera)
                self.hit_grid.update_tile_pixmap(hid, QPixmap.fromImage(img))
            except Exception:
                continue
        self._pending_render_ids = self._pending_render_ids[24:]
        if self._pending_render_ids:
            self._render_timer.start(30)

    def _on_hit_selected(self, hit_id: int) -> None:
        hit = self._hit_by_id.get(hit_id)
        if not hit:
            return
        self.detail.setPlainText(
            f"命中 #{hit.hit_id}  第 {hit.page + 1} 页\n"
            f"原文: {hit.text!r}\n"
            f"规范化: {hit.normalized_text!r}\n"
            f"字体: {hit.font_display} ({hit.font})\n"
            f"字号: {hit.size:.2f} pt\n"
            f"字色: {color_to_hex(hit.color)}\n"
            f"bbox: {hit.bbox}\n"
            f"字符范围: [{hit.char_start}, {hit.char_end})"
        )

    def _on_review(self, hit_id: int, reviewed) -> None:
        hit = self._hit_by_id.get(hit_id)
        if hit:
            hit.reviewed = reviewed
        if self.current_search_id is not None:
            self.cache.update_hit_review(self.current_search_id, hit_id, reviewed)
        self.stats_panel.set_hits(self.hits)

    def _on_stat_filter(self, ids) -> None:
        self.hit_grid.set_filter(ids)

    def export_csv(self) -> None:
        if not self.hits:
            QMessageBox.information(self, "提示", "无命中可导出")
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出 CSV", "hits.csv", "CSV (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(
                [
                    "hit_id",
                    "page",
                    "text",
                    "normalized_text",
                    "font",
                    "size",
                    "color",
                    "x0",
                    "y0",
                    "x1",
                    "y1",
                    "reviewed",
                ]
            )
            for h in self.hits:
                w.writerow(
                    [
                        h.hit_id,
                        h.page + 1,
                        h.text,
                        h.normalized_text,
                        h.font_display,
                        h.size,
                        color_to_hex(h.color),
                        *h.bbox,
                        "" if h.reviewed is None else ("ok" if h.reviewed else "bad"),
                    ]
                )
        self.statusBar().showMessage(f"已导出 {path}")

    def export_json(self) -> None:
        if not self.hits:
            QMessageBox.information(self, "提示", "无命中可导出")
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出 JSON", "hits.json", "JSON (*.json)")
        if not path:
            return
        data = [
            {
                "hit_id": h.hit_id,
                "page": h.page + 1,
                "text": h.text,
                "normalized_text": h.normalized_text,
                "font": h.font_display,
                "size": h.size,
                "color": color_to_hex(h.color),
                "bbox": list(h.bbox),
                "reviewed": h.reviewed,
            }
            for h in self.hits
        ]
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self.statusBar().showMessage(f"已导出 {path}")

    def closeEvent(self, event) -> None:
        if self.render_session:
            self.render_session.close()
        self.cache.close()
        super().closeEvent(event)
