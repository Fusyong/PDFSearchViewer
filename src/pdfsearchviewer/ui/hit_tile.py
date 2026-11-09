from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, QTimer, Signal, QSize
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..models import Hit
from ..page_numbers import to_display_page
from ..stats import EMPTY_MARK_LABEL


class MarkNoteDialog(QDialog):
    """Ask for an optional mark note.

    Enter (or 确定) keeps the typed text, including an empty string.
    Esc discards whatever was typed and stores an empty mark.
    Closing the window does the same as Esc.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.note = ""
        self._done = False
        self.setWindowTitle("标记")
        self.setModal(True)

        layout = QVBoxLayout(self)
        hint = QLabel("输入信息。直接回车确认（可留空）；Esc 不输入信息。")
        hint.setWordWrap(True)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("可留空")
        self.edit.setMinimumWidth(280)
        self.edit.installEventFilter(self)
        ok = QPushButton("确定")
        ok.setDefault(True)
        ok.clicked.connect(self._commit_text)

        layout.addWidget(hint)
        layout.addWidget(self.edit)
        layout.addWidget(ok)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.edit.setFocus(Qt.FocusReason.OtherFocusReason)
        self.edit.selectAll()

    def eventFilter(self, watched, event) -> bool:
        if watched is self.edit and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Escape:
                self._commit_empty()
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._commit_text()
                return True
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._commit_empty()
            return
        super().keyPressEvent(event)

    def _commit_text(self) -> None:
        self._finish(self.edit.text().strip())

    def _commit_empty(self) -> None:
        self._finish("")

    def _finish(self, note: str) -> None:
        if self._done:
            return
        self._done = True
        self.note = note
        self.done(QDialog.DialogCode.Accepted)


def ask_mark_note(parent=None) -> str:
    dialog = MarkNoteDialog(parent)
    dialog.exec()
    return dialog.note


class HitTile(QFrame):
    clicked = Signal(int)
    double_clicked = Signal(int)
    mark_changed = Signal(int, object)  # hit_id, str | None

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
        self.meta.setWordWrap(False)
        self.meta.setStyleSheet("font-size: 11px;")
        self.mark_cb = QCheckBox("标记")
        self.mark_cb.clicked.connect(self._on_mark_clicked)

        row = QWidget()
        hl = QHBoxLayout(row)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.addWidget(self.mark_cb)
        hl.addStretch(1)

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
        self.meta.setText(f"p{disp}")
        self.mark_cb.blockSignals(True)
        self.mark_cb.setChecked(hit.mark is not None)
        self.mark_cb.setToolTip("" if hit.mark is None else (hit.mark.strip() or EMPTY_MARK_LABEL))
        self.mark_cb.blockSignals(False)

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

    def _on_mark_clicked(self, _checked: bool = False) -> None:
        if self.mark_cb.isChecked():
            # Let the checkbox click finish before the modal dialog opens.
            QTimer.singleShot(0, self._prompt_mark)
            return
        self.mark_changed.emit(self.hit_id, None)

    def _prompt_mark(self) -> None:
        if not self.mark_cb.isChecked():
            return
        note = ask_mark_note(self.window())
        self.mark_changed.emit(self.hit_id, note)
