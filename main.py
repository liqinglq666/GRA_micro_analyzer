# main.py
"""
GRA-MicroAnalyzer — Application Entry Point
============================================
Responsibilities:
1. Configure the root Python logger before any module imports log.
2. Apply the SCI-paper Matplotlib style globally.
3. Construct the QApplication with HiDPI and platform flags.
4. Install a top-level exception hook so unhandled exceptions are shown
   in a QMessageBox rather than silently crashing the process.
5. Instantiate and show MainWindow.
6. Return the QApplication exit code to the OS.
"""

from __future__ import annotations

import sys

# ---- Must run BEFORE logging is configured ----
# Force Windows console to output UTF-8 so that any Unicode in log
# messages (em-dashes, arrows, etc.) is not garbled by the default GBK
# code page.  reconfigure() is available on Python 3.7+ / Windows.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import logging
import traceback
from typing import Type

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox


def _configure_logging() -> None:
    """
    Set up the root logger to write INFO-level messages to stdout with a
    timestamped, module-qualified format.

    Call this before importing any application module so that all
    module-level loggers inherit this configuration.
    """
    log_format = (
        "%(asctime)s  %(levelname)-8s  %(name)s:%(lineno)d  %(message)s"
    )
    # Use explicit StreamHandler with encoding='utf-8' so that Unicode
    # characters in log messages (Greek letters, special symbols, etc.)
    # from any module (including gra_engine) are never garbled on Windows.
    handler = logging.StreamHandler(stream=open(
        sys.stdout.fileno(), mode='w', encoding='utf-8', closefd=False, buffering=1
    ))
    handler.setFormatter(logging.Formatter(fmt=log_format, datefmt="%Y-%m-%d %H:%M:%S"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    logging.getLogger("matplotlib").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)


def _install_exception_hook(app: QApplication) -> None:
    """
    Replace the default sys.excepthook so that unhandled exceptions in
    the main thread display a QMessageBox instead of printing to stderr
    and exiting silently on some platforms.

    Parameters
    ----------
    app:
        The running QApplication instance (needed to ensure an event loop
        is available when the hook fires).
    """
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
        dialog.setText(
            "An unexpected error has occurred.  "
            "The application may be in an unstable state."
        )
        dialog.setDetailedText(tb_str)
        dialog.exec()

    sys.excepthook = _hook


def _build_application() -> QApplication:
    """
    Construct and configure the QApplication instance.

    Sets the application name, organisation, and enables HiDPI scaling
    via the AA_EnableHighDpiScaling attribute (PySide6 handles this
    automatically on Qt 6, but we set it explicitly for clarity).

    Returns
    -------
    QApplication
        The configured application object.  Must be created before any
        QWidget.
    """
    # Qt 6 enables HiDPI by default; this call is a no-op but documents
    # intent clearly for future maintainers.
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
    """
    Application entry point.

    Returns
    -------
    int
        Process exit code (0 = clean exit, non-zero = error).
    """
    _configure_logging()
    logger = logging.getLogger(__name__)
    logger.info("GRA-MicroAnalyzer starting up...")

    # Deferred imports — logging must be configured first.
    from utils.plot_styler import apply_sci_style
    from ui.main_window import MainWindow

    app = _build_application()
    _install_exception_hook(app)
    apply_sci_style()

    window = MainWindow()
    window.show()

    logger.info("Event loop started.")
    exit_code = app.exec()
    logger.info("GRA-MicroAnalyzer exiting with code %d.", exit_code)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
