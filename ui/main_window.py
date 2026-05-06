# -*- coding: utf-8 -*-
# ui/main_window.py
"""
GRA-MicroAnalyzer — Main Application Window

All four charts (Bar, Heatmap, Network, Radar) are drawn on the main thread
inside _on_result_received, immediately after the worker emits GRAResult.
No Figure objects are passed across threads.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import pandas as pd
from PySide6.QtCore import Qt, QAbstractTableModel, QElapsedTimer, QModelIndex, QPersistentModelIndex
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTableView,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from core.data_model import GRAConfig, GRAResult
from ui.threads import GRAWorker
from ui.widgets.config_panel import ConfigPanel
from ui.widgets.plot_canvas import PlotCanvas
from ui.widgets.radar_widget import RadarWidget
from utils.file_io import save_results_to_excel
from utils.plot_styler import (
    build_coefficient_heatmap,
    build_grg_bar_chart,
    plot_network_diagram,
)

logger = logging.getLogger(__name__)

_PREVIEW_ROW_LIMIT: int = 1_000
_WINDOW_TITLE: str = (
    "GRA-MicroAnalyzer \u2014 Grey Relational Analysis for Microstructural Attribution"
)
_MIN_WIDTH: int = 1400
_MIN_HEIGHT: int = 800
_LEFT_PANEL_MAX_WIDTH: int = 320


# ---------------------------------------------------------------------------
# Pandas -> Qt Table Model
# ---------------------------------------------------------------------------


class _PandasTableModel(QAbstractTableModel):
    """
    Minimal read-only QAbstractTableModel adapter for a Pandas DataFrame.
    Displays up to _PREVIEW_ROW_LIMIT rows.
    """

    def __init__(
        self,
        dataframe: pd.DataFrame,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._df: pd.DataFrame = dataframe.head(_PREVIEW_ROW_LIMIT).reset_index(drop=False)

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:
        return len(self._df)

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:
        return len(self._df.columns)

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if not index.isValid():
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            value = self._df.iat[index.row(), index.column()]
            if isinstance(value, float):
                return f"{value:.4f}"
            return str(value)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            value = self._df.iat[index.row(), index.column()]
            if isinstance(value, (int, float)):
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return str(self._df.columns[section])
        return str(section + 1)


# ---------------------------------------------------------------------------
# Main Window
# ---------------------------------------------------------------------------


class MainWindow(QMainWindow):
    """Top-level application window for GRA-MicroAnalyzer."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self._dataframe: Optional[pd.DataFrame] = None
        self._last_result: Optional[GRAResult] = None
        self._worker: Optional[GRAWorker] = None
        self._worker_running: bool = False
        self._run_timer: QElapsedTimer = QElapsedTimer()

        # Export button references (populated by _build_export_bar)
        self._btn_export_excel: QPushButton
        self._btn_export_excel_heatmap_tab: QPushButton
        self._btn_export_excel_network_tab: QPushButton
        self._btn_export_excel_radar_tab: QPushButton
        self._btn_save_grg_fig: QPushButton
        self._btn_save_heatmap_fig: QPushButton
        self._btn_save_network_fig: QPushButton
        self._btn_save_radar_fig: QPushButton

        self._setup_window()
        self._setup_menu_bar()
        self._setup_central_widget()
        self._setup_status_bar()
        self._connect_signals()

        logger.info("MainWindow initialised.")

    # ------------------------------------------------------------------
    # Window-level Setup
    # ------------------------------------------------------------------

    def _setup_window(self) -> None:
        self.setWindowTitle(_WINDOW_TITLE)
        self.setMinimumSize(_MIN_WIDTH, _MIN_HEIGHT)
        self.resize(1600, 900)

    def _setup_menu_bar(self) -> None:
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("&File")

        action_load = QAction("&Load Dataset\u2026", self)
        action_load.setShortcut("Ctrl+O")
        action_load.setStatusTip("Open a CSV or Excel data file.")
        action_load.triggered.connect(self._action_load_dataset)

        self._action_save = QAction("&Save Results\u2026", self)
        self._action_save.setShortcut("Ctrl+S")
        self._action_save.setStatusTip("Export GRA results to an Excel workbook.")
        self._action_save.setEnabled(False)
        self._action_save.triggered.connect(self._action_save_results)

        action_quit = QAction("&Quit", self)
        action_quit.setShortcut("Ctrl+Q")
        action_quit.triggered.connect(QApplication.quit)

        file_menu.addAction(action_load)
        file_menu.addAction(self._action_save)
        file_menu.addSeparator()
        file_menu.addAction(action_quit)

        help_menu = menu_bar.addMenu("&Help")
        action_about = QAction("&About GRA-MicroAnalyzer", self)
        action_about.triggered.connect(self._action_show_about)
        help_menu.addAction(action_about)

    def _setup_central_widget(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        self._config_panel = ConfigPanel()
        self._config_panel.setMaximumWidth(_LEFT_PANEL_MAX_WIDTH)
        self._config_panel.setMinimumWidth(300)
        splitter.addWidget(self._config_panel)

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        self._tabs.setStyleSheet(
            "QTabBar::tab {"
            "  padding: 6px 16px; min-width: 110px; font-size: 9pt;"
            "  border-bottom: 3px solid transparent;"
            "}"
            "QTabBar::tab:selected {"
            "  border-bottom: 3px solid #2171B5; font-weight: bold; color: #2171B5;"
            "}"
            "QTabBar::tab:hover:!selected {"
            "  border-bottom: 3px solid #93C4E8;"
            "}"
        )
        self._tabs.addTab(self._build_preview_tab(),  "[1] Data Preview")
        self._tabs.addTab(self._build_results_tab(),  "[2] GRG Results")
        self._tabs.addTab(self._build_heatmap_tab(),  "[3] Coefficient Heatmap")
        self._tabs.addTab(self._build_network_tab(),  "[4] Network Diagram")
        self._tabs.addTab(self._build_radar_tab(),    "[5] Radar Chart")

        splitter.addWidget(self._tabs)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([320, 1280])
        self.setCentralWidget(splitter)

    def _setup_status_bar(self) -> None:
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)

        self._progress_bar = QProgressBar()
        self._progress_bar.setMaximumWidth(200)
        self._progress_bar.setMaximumHeight(16)
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(False)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setFormat("%p%")
        self._status_bar.addPermanentWidget(self._progress_bar)
        self._status_bar.showMessage("Ready \u2014 load a dataset to begin.")

    # ------------------------------------------------------------------
    # Tab Builders
    # ------------------------------------------------------------------

    def _build_preview_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        toolbar = QToolBar("Preview Actions")
        toolbar.setMovable(False)
        toolbar.setStyleSheet(
            "QToolBar {"
            "  border: none; background: #F8F9FA;"
            "  border-bottom: 1px solid #DEE2E6; padding: 3px 6px;"
            "}"
        )
        action_copy_sel = QAction("Copy Selection", self)
        action_copy_sel.setShortcut(QKeySequence.StandardKey.Copy)
        action_copy_sel.setToolTip(
            "Copy highlighted cells to clipboard as tab-separated text  [Ctrl+C]"
        )
        action_copy_sel.triggered.connect(self._copy_selection_to_clipboard)
        toolbar.addAction(action_copy_sel)

        toolbar.addSeparator()

        action_copy_all = QAction("Copy All", self)
        action_copy_all.setShortcut(QKeySequence("Ctrl+Shift+C"))
        action_copy_all.setToolTip(
            "Copy the entire visible table to clipboard  [Ctrl+Shift+C]"
        )
        action_copy_all.triggered.connect(self._copy_all_to_clipboard)
        toolbar.addAction(action_copy_all)
        layout.addWidget(toolbar)

        self._preview_notice = QLabel()
        self._preview_notice.setStyleSheet(
            "background: #FFF3CD; color: #856404; padding: 4px; font-size: 8pt;"
        )
        self._preview_notice.setVisible(False)
        layout.addWidget(self._preview_notice)

        self._table_view_widget = QTableView()
        self._table_view_widget.setAlternatingRowColors(True)
        self._table_view_widget.horizontalHeader().setStretchLastSection(True)
        self._table_view_widget.setSelectionMode(
            QTableView.SelectionMode.ExtendedSelection  # type: ignore[attr-defined]
        )
        self._table_view_widget.setEditTriggers(
            QTableView.EditTrigger.NoEditTriggers  # type: ignore[attr-defined]
        )
        layout.addWidget(self._table_view_widget)
        return container

    def _build_results_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._plot_canvas_grg = PlotCanvas(show_toolbar=False)
        layout.addWidget(self._plot_canvas_grg)
        layout.addWidget(self._build_export_bar(tab="bar"))
        return container

    def _build_heatmap_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._plot_canvas_heatmap = PlotCanvas(show_toolbar=False)
        self._plot_canvas_heatmap.cell_hovered.connect(self._on_heatmap_cell_hovered)
        layout.addWidget(self._plot_canvas_heatmap)
        layout.addWidget(self._build_export_bar(tab="heatmap"))
        return container

    def _build_network_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._plot_canvas_network = PlotCanvas(show_toolbar=False)
        layout.addWidget(self._plot_canvas_network)
        layout.addWidget(self._build_export_bar(tab="network"))
        return container

    def _build_radar_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._radar_widget = RadarWidget()
        layout.addWidget(self._radar_widget)
        layout.addWidget(self._build_export_bar(tab="radar"))
        return container

    def _build_export_bar(self, tab: str) -> QWidget:
        bar = QWidget()
        bar.setStyleSheet(
            "QWidget { background: #F0F4F8; border-top: 1px solid #CDD5DF; }"
            "QPushButton { padding: 4px 12px; }"
        )
        bar.setFixedHeight(34)
        h_layout = QHBoxLayout(bar)
        h_layout.setContentsMargins(8, 2, 8, 2)
        h_layout.setSpacing(8)

        export_label = QLabel("Export:")
        export_label.setStyleSheet(
            "color: #495057; font-weight: bold; font-size: 8pt; border: none;"
        )
        h_layout.addWidget(export_label)

        btn_excel = QPushButton("Results to Excel (.xlsx)")
        btn_excel.setToolTip(
            "Export GRG Summary, Normalised, \u0394 Delta, and \u03be Coefficient "
            "matrices to a multi-sheet Excel workbook."
        )
        btn_excel.setEnabled(False)
        btn_excel.setFixedHeight(26)
        btn_excel.clicked.connect(self._action_save_results)
        h_layout.addWidget(btn_excel)

        if tab == "heatmap":
            btn_fig = QPushButton("Save Heatmap (SVG / PDF)")
            btn_fig.setToolTip("Export heatmap as a vector graphic.")
            btn_fig.setEnabled(False)
            btn_fig.setFixedHeight(26)
            btn_fig.clicked.connect(
                lambda: self._plot_canvas_heatmap.prompt_save_figure(self)
            )
            self._btn_save_heatmap_fig = btn_fig
            self._btn_export_excel_heatmap_tab = btn_excel

        elif tab == "network":
            btn_fig = QPushButton("Save Network (SVG / PDF)")
            btn_fig.setToolTip("Export network diagram as a vector graphic.")
            btn_fig.setEnabled(False)
            btn_fig.setFixedHeight(26)
            btn_fig.clicked.connect(
                lambda: self._plot_canvas_network.prompt_save_figure(self)
            )
            self._btn_save_network_fig = btn_fig
            self._btn_export_excel_network_tab = btn_excel

        elif tab == "radar":
            btn_fig = QPushButton("Save Radar (SVG / PNG)")
            btn_fig.setToolTip("Export radar chart as SVG or PNG.")
            btn_fig.setEnabled(False)
            btn_fig.setFixedHeight(26)
            # ✅ 直接调用 RadarWidget.prompt_save_figure — 不经过任何中间方法
            btn_fig.clicked.connect(
                lambda: self._radar_widget.prompt_save_figure(self)
            )
            self._btn_save_radar_fig = btn_fig
            self._btn_export_excel_radar_tab = btn_excel

        else:  # bar
            btn_fig = QPushButton("Save Chart (SVG / PDF)")
            btn_fig.setToolTip("Export GRG bar chart as a vector graphic.")
            btn_fig.setEnabled(False)
            btn_fig.setFixedHeight(26)
            btn_fig.clicked.connect(
                lambda: self._plot_canvas_grg.prompt_save_figure(self)
            )
            self._btn_save_grg_fig = btn_fig
            self._btn_export_excel = btn_excel

        h_layout.addWidget(btn_fig)
        h_layout.addStretch()
        return bar

    # ------------------------------------------------------------------
    # Signal Wiring
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        self._config_panel.dataset_loaded.connect(self._on_dataset_loaded)
        self._config_panel.run_requested.connect(self._on_run_requested)
        self._config_panel.status_message.connect(self._status_bar.showMessage)

    # ------------------------------------------------------------------
    # Slots — ConfigPanel
    # ------------------------------------------------------------------

    def _on_dataset_loaded(self, dataframe: pd.DataFrame, file_path: Path) -> None:
        self._dataframe = dataframe
        self._last_result = None
        self._action_save.setEnabled(False)
        self._set_export_buttons_enabled(False)

        model = _PandasTableModel(dataframe)
        self._table_view_widget.setModel(model)
        self._table_view_widget.resizeColumnsToContents()

        if len(dataframe) > _PREVIEW_ROW_LIMIT:
            self._preview_notice.setText(
                f"\u26a0  Preview capped at {_PREVIEW_ROW_LIMIT:,} rows.  "
                f"Full dataset ({len(dataframe):,} rows) is used for analysis."
            )
            self._preview_notice.setVisible(True)
        else:
            self._preview_notice.setVisible(False)

        self._tabs.setCurrentIndex(0)
        self.setWindowTitle(f"{file_path.name} \u2014 GRA-MicroAnalyzer")
        logger.info(
            "Data preview updated — %d rows shown.",
            min(len(dataframe), _PREVIEW_ROW_LIMIT),
        )

    def _on_run_requested(self, config: GRAConfig) -> None:
        if self._worker_running:
            QMessageBox.warning(
                self,
                "Analysis in Progress",
                "An analysis is already running. Please wait for it to complete.",
            )
            return
        if self._dataframe is None:
            QMessageBox.critical(self, "No Data", "Load a dataset before running.")
            return
        self._start_worker(self._dataframe, config)

    # ------------------------------------------------------------------
    # Worker Management
    # ------------------------------------------------------------------

    def _start_worker(self, dataframe: pd.DataFrame, config: GRAConfig) -> None:
        self._worker = GRAWorker(dataframe=dataframe, config=config, parent=None)
        self._worker.progress_signal.connect(self._progress_bar.setValue)
        self._worker.log_signal.connect(self._status_bar.showMessage)
        self._worker.result_signal.connect(self._on_result_received)
        self._worker.error_signal.connect(self._on_worker_error)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.finished.connect(self._worker.deleteLater)

        self._worker_running = True
        self._run_timer.start()
        self._config_panel.set_running_state(True)
        self._progress_bar.setVisible(True)
        self._progress_bar.setValue(0)
        self._worker.start()
        logger.info("GRAWorker thread started.")

    def _on_result_received(self, result: GRAResult) -> None:
        """
        Called on the main thread when GRAWorker emits result_signal.
        All four charts are built here — no Figure is ever passed across threads.
        """
        self._last_result = result
        self._action_save.setEnabled(True)
        self._set_export_buttons_enabled(True)

        ref_col   = result.config.reference_column
        comp_cols = list(result.config.comparative_columns.keys())
        grg_dict: dict[str, float] = result.grg_series.to_dict()

        # --- [2] GRG Bar Chart ---
        try:
            bar_fig = build_grg_bar_chart(
                grg_series=result.grg_series,
                title=f"Grey Relational Grade \u2014 Reference: {ref_col}",
            )
            self._plot_canvas_grg.display_figure(bar_fig)
        except Exception as exc:
            logger.exception("Bar chart failed: %s", exc)

        # --- [3] Coefficient Heatmap ---
        try:
            heatmap_fig = build_coefficient_heatmap(
                coefficient_df=result.coefficient_df,
                title=f"Relational Coefficient Matrix \u2014 Reference: {ref_col}",
            )
            self._plot_canvas_heatmap.display_figure(heatmap_fig)
        except Exception as exc:
            logger.exception("Heatmap failed: %s", exc)

        # --- [4] Network Diagram ---
        try:
            network_fig = plot_network_diagram(
                target_name=ref_col,
                grg_scores=grg_dict,
                title=f"Topology Network \u2014 Reference: {ref_col}",
            )
            self._plot_canvas_network.display_figure(network_fig)
        except Exception as exc:
            logger.exception("Network diagram failed: %s", exc)

        # --- [5] Radar Chart — pure QPainter, zero matplotlib polar involvement ---
        try:
            norm_df    = result.normalised_df
            id_col     = result.config.id_column
            if id_col in norm_df.columns:
                sample_ids = norm_df[id_col].astype(str).tolist()
            else:
                sample_ids = [str(i) for i in norm_df.index]

            available_comp = [c for c in comp_cols if c in norm_df.columns]
            data_dict: dict[str, list[float]] = {
                sid: norm_df.iloc[idx][available_comp].tolist()
                for idx, sid in enumerate(sample_ids)
            }
            self._radar_widget.plot(
                categories=available_comp,
                data_dict=data_dict,
                title=f"Radar Chart \u2014 Reference: {ref_col}",
            )
        except Exception as exc:
            logger.exception("Radar chart failed: %s", exc)

        # Switch to GRG Results tab
        self._tabs.setCurrentIndex(1)
        logger.info(
            "All charts rendered — top factor: '%s' (GRG=%.4f).",
            result.top_factor,
            result.grg_series[result.top_factor],
        )

    def _on_worker_error(self, message: str) -> None:
        QMessageBox.critical(self, "Analysis Error", message)
        self._status_bar.showMessage("Analysis failed \u2014 see error dialog.")
        logger.warning("Worker error: %s", message)

    def _on_heatmap_cell_hovered(
        self, row_label: str, col_label: str, value: float
    ) -> None:
        self._status_bar.showMessage(
            f"Sample: {row_label}  \u2502  Factor: {col_label}  \u2502  \u03be = {value:.4f}"
        )

    def _on_worker_finished(self) -> None:
        elapsed_ms = self._run_timer.elapsed() if self._run_timer.isValid() else 0
        elapsed_str = f"{elapsed_ms / 1000:.2f} s" if elapsed_ms > 0 else "N/A"
        self._worker_running = False
        self._worker = None
        self._config_panel.set_running_state(False)
        self._progress_bar.setVisible(False)
        self._status_bar.showMessage(
            f"Analysis complete \u2014 elapsed: {elapsed_str}.  Results ready for export."
        )
        logger.debug("GRAWorker thread finished — elapsed %s.", elapsed_str)

    # ------------------------------------------------------------------
    # Clipboard Helpers
    # ------------------------------------------------------------------

    def _copy_selection_to_clipboard(self) -> None:
        model = self._table_view_widget.model()
        if model is None:
            self._status_bar.showMessage("No data loaded \u2014 nothing to copy.")
            return
        selection = self._table_view_widget.selectionModel().selectedIndexes()
        if not selection:
            self._status_bar.showMessage(
                "No cells selected \u2014 use Ctrl+Shift+C to copy the entire table."
            )
            return
        cells: dict[tuple[int, int], str] = {}
        for index in selection:
            cells[(index.row(), index.column())] = str(
                model.data(index, Qt.ItemDataRole.DisplayRole) or ""
            )
        selected_rows = sorted({r for r, _ in cells})
        selected_cols = sorted({c for _, c in cells})
        headers = [
            str(
                model.headerData(col, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
                or ""
            )
            for col in selected_cols
        ]
        lines = ["\t".join(headers)]
        for row in selected_rows:
            lines.append("\t".join(cells.get((row, col), "") for col in selected_cols))
        QApplication.clipboard().setText("\n".join(lines))
        self._status_bar.showMessage(
            f"Copied {len(cells)} cell(s) across {len(selected_rows)} row(s) to clipboard."
        )
        logger.debug("Selection clipboard copy — %d cells.", len(cells))

    def _copy_all_to_clipboard(self) -> None:
        model = self._table_view_widget.model()
        if model is None:
            self._status_bar.showMessage("No data loaded \u2014 nothing to copy.")
            return
        n_rows = model.rowCount()
        n_cols = model.columnCount()
        headers = [
            str(
                model.headerData(col, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
                or ""
            )
            for col in range(n_cols)
        ]
        lines = ["\t".join(headers)]
        for row in range(n_rows):
            lines.append("\t".join(
                str(model.data(model.index(row, col), Qt.ItemDataRole.DisplayRole) or "")
                for col in range(n_cols)
            ))
        QApplication.clipboard().setText("\n".join(lines))
        self._status_bar.showMessage(
            f"Entire preview copied \u2014 {n_rows} rows \u00d7 {n_cols} columns."
        )
        logger.debug("Full table clipboard copy — %d x %d.", n_rows, n_cols)

    # ------------------------------------------------------------------
    # Export Button State
    # ------------------------------------------------------------------

    def _set_export_buttons_enabled(self, enabled: bool) -> None:
        self._btn_export_excel.setEnabled(enabled)
        self._btn_export_excel_heatmap_tab.setEnabled(enabled)
        self._btn_export_excel_network_tab.setEnabled(enabled)
        self._btn_export_excel_radar_tab.setEnabled(enabled)
        self._btn_save_grg_fig.setEnabled(enabled)
        self._btn_save_heatmap_fig.setEnabled(enabled)
        self._btn_save_network_fig.setEnabled(enabled)
        self._btn_save_radar_fig.setEnabled(enabled)

    # ------------------------------------------------------------------
    # Menu Action Handlers
    # ------------------------------------------------------------------

    def _action_load_dataset(self) -> None:
        self._config_panel._on_load_clicked()

    def _action_save_results(self) -> None:
        if self._last_result is None:
            QMessageBox.information(
                self, "No Results", "Run an analysis before exporting results."
            )
            return
        file_path_str, _ = QFileDialog.getSaveFileName(
            self,
            "Export Results to Excel",
            "gra_results",
            "Excel Workbook (*.xlsx);;All Files (*)",
        )
        if not file_path_str:
            return
        try:
            saved_path = save_results_to_excel(
                result=self._last_result,
                output_path=file_path_str,
            )
            QMessageBox.information(
                self,
                "Export Successful",
                f"Results exported to:\n{saved_path}\n\n"
                "Sheets:\n"
                "  1. GRG Ranking\n"
                "  2. Normalised Sequences\n"
                "  3. Delta Matrix\n"
                "  4. Xi Coefficient Matrix\n"
                "  5. Analysis Config",
            )
            self._status_bar.showMessage(f"Results saved: {saved_path.name}")
        except Exception as exc:
            QMessageBox.critical(self, "Export Failed", f"Could not save results:\n{exc}")
            logger.exception("Excel export failed.")

    def _action_show_about(self) -> None:
        QMessageBox.about(
            self,
            "About GRA-MicroAnalyzer",
            "<b>GRA-MicroAnalyzer</b> v1.0.0<br><br>"
            "Grey Relational Analysis for Microstructural Attribution<br>"
            "Designed for Material Science Researchers.<br><br>"
            "Implements Deng Ju-Long\u2019s Grey Relational Analysis (1989) "
            "for identifying dominant microstructural factors in material "
            "degradation studies.<br><br>"
            "<i>Open-source. Built with PySide6, Pandas, NumPy, Matplotlib.</i>",
        )

    # ------------------------------------------------------------------
    # Window Events
    # ------------------------------------------------------------------

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._worker is not None and self._worker.isRunning():
            reply = QMessageBox.question(
                self,
                "Analysis in Progress",
                "An analysis is currently running.\n\nClose anyway and wait for it to finish?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return
            self._worker.wait(3_000)
        event.accept()
        logger.info("MainWindow closed.")
