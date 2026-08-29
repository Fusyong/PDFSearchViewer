from __future__ import annotations

import sys
from pathlib import Path

# Allow running as python -m pdfsearchviewer or script without install
_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def main() -> int:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt
    from pdfsearchviewer.ui.main_window import MainWindow

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("PDFSearchViewer")
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
