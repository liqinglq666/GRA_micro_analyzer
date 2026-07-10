from __future__ import annotations

import logging
import sys
import traceback
from pathlib import Path
from typing import Type

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox


for stream in (sys.stdout, sys.stderr):
    if stream is not None and hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


def _configure_logging() -> None:
    root = logging.getLogger()
    if root.handlers:
        return

    formatter = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(name)s:%(lineno)d  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if sys.stdout is not None and hasattr(sys.stdout, "write"):
        handler: logging.Handler = logging.StreamHandler(sys.stdout)
    else:
        try:
            handler = logging.FileHandler(
                Path.home() / ".gra_micro_analyzer.log",
                encoding="utf-8",
            )
        except OSError:
            handler = logging.NullHandler()

    handler.setFormatter(formatter)
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    logging.getLogger("matplotlib").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)


def _install_exception_hook() -> None:
    def _hook(
        exc_type: Type[BaseException],
        exc_value: BaseException,
        exc_tb: object,
    ) -> None:
        tb_str = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        logging.critical("Unhandled exception:\n%s", tb_str)

        dialog = QMessageBox()
        dialog.setIcon(QMessageBox.Icon.Critical)
        dialog.setWindowTitle("Unhandled Exception")
        dialog.setText("程序遇到未处理异常，当前结果可能不可靠。")
        dialog.setDetailedText(tb_str)
        dialog.exec()

    sys.excepthook = _hook


def _build_application() -> QApplication:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("GRA-MicroAnalyzer")
    app.setApplicationDisplayName("GRA-MicroAnalyzer")
    app.setOrganizationName("MaterialScienceLab")
    app.setApplicationVersion("1.0.0")
    return app


def main() -> int:
    _configure_logging()
    logger = logging.getLogger(__name__)
    logger.info("GRA-MicroAnalyzer starting up...")

    from ui.main_window import MainWindow
    from utils.plot_styler import apply_sci_style

    app = _build_application()
    _install_exception_hook()
    apply_sci_style()

    window = MainWindow()
    window.show()

    exit_code = app.exec()
    logger.info("GRA-MicroAnalyzer exiting with code %d.", exit_code)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
