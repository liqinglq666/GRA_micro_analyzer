# -*- coding: utf-8 -*-
# ui/widgets/config_panel.py
"""
GRA-MicroAnalyzer - Configuration Panel Widget
===============================================
Signals
-------
dataset_loaded(pd.DataFrame, Path)
run_requested(GRAConfig)
status_message(str)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import pandas as pd
from PySide6.QtCore import Qt, QElapsedTimer, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.data_model import GRAConfig, ColumnConfig, Polarity
from utils.file_io import load_dataframe

logger = logging.getLogger(__name__)

_RHO_SCALE: int = 100
_RHO_DEFAULT: float = 0.5
_RHO_MIN: float = 0.01
_RHO_MAX: float = 1.00

_POLARITY_OPTIONS: list[tuple[str, Polarity]] = [
    ("Larger is Better (+)", Polarity.LTB),
    ("Smaller is Better (-)", Polarity.STB),
]

# 通用 GroupBox 样式：增大标题与内容间距，边框圆角
_GROUP_STYLE = """
QGroupBox {
    font-weight: bold;
    font-size: 9pt;
    border: 1px solid #CDD5DF;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 4px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    left: 10px;
}
"""


class ConfigPanel(QWidget):
    dataset_loaded: Signal = Signal(object, object)   # (pd.DataFrame, Path)
    run_requested: Signal = Signal(object)             # (GRAConfig,)
    status_message: Signal = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._dataframe: Optional[pd.DataFrame] = None
        self._file_path: Optional[Path] = None
        self._run_timer: QElapsedTimer = QElapsedTimer()
        self._dot_timer: QTimer = QTimer(self)
        self._dot_count: int = 0
        self._build_ui()
        self._connect_internal_signals()

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)   # 增大外边距
        root_layout.setSpacing(12)                         # 组件间距加大
        root_layout.addWidget(self._build_file_group())
        root_layout.addWidget(self._build_column_group())
        root_layout.addWidget(self._build_polarity_group())
        root_layout.addWidget(self._build_rho_group())
        root_layout.addWidget(self._build_run_button())
        root_layout.addStretch()

    def _build_file_group(self) -> QGroupBox:
        group = QGroupBox("Data Source")
        group.setStyleSheet(_GROUP_STYLE)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(8)

        self._btn_load = QPushButton("[Open] Load Dataset...")
        self._btn_load.setMinimumHeight(30)
        self._btn_load.setToolTip(
            "Open a CSV (.csv) or Excel (.xlsx / .xls) file.\n"
            "The first row must contain column headers."
        )
        layout.addWidget(self._btn_load)

        self._lbl_file = QLabel("No file loaded.")
        self._lbl_file.setWordWrap(True)
        self._lbl_file.setStyleSheet(
            "color: #888888; font-style: italic; font-size: 8pt;"
        )
        layout.addWidget(self._lbl_file)
        return group

    def _build_column_group(self) -> QGroupBox:
        group = QGroupBox("Column Assignment")
        group.setStyleSheet(_GROUP_STYLE)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(6)

        lbl_id = QLabel("Sample ID Column:")
        lbl_id.setStyleSheet("font-size: 8pt; color: #495057;")
        layout.addWidget(lbl_id)
        self._cmb_id_column = QComboBox()
        self._cmb_id_column.setMinimumHeight(26)
        layout.addWidget(self._cmb_id_column)

        lbl_ref = QLabel("Reference Column (Target):")
        lbl_ref.setStyleSheet("font-size: 8pt; color: #495057;")
        layout.addWidget(lbl_ref)
        self._cmb_ref_column = QComboBox()
        self._cmb_ref_column.setMinimumHeight(26)
        layout.addWidget(self._cmb_ref_column)

        lbl_pol = QLabel("Reference Polarity:")
        lbl_pol.setStyleSheet("font-size: 8pt; color: #495057;")
        layout.addWidget(lbl_pol)
        self._cmb_ref_polarity = QComboBox()
        self._cmb_ref_polarity.setMinimumHeight(26)
        for label, _ in _POLARITY_OPTIONS:
            self._cmb_ref_polarity.addItem(label)
        layout.addWidget(self._cmb_ref_polarity)
        return group

    def _build_polarity_group(self) -> QGroupBox:
        group = QGroupBox("Comparative Factor Polarities")
        group.setStyleSheet(_GROUP_STYLE)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(0)

        self._tbl_polarity = QTableWidget(0, 2)
        self._tbl_polarity.setHorizontalHeaderLabels(["Factor", "Polarity"])
        self._tbl_polarity.horizontalHeader().setStretchLastSection(False)
        self._tbl_polarity.horizontalHeader().setSectionResizeMode(
            0, self._tbl_polarity.horizontalHeader().ResizeMode.Stretch
        )
        self._tbl_polarity.horizontalHeader().setSectionResizeMode(
            1, self._tbl_polarity.horizontalHeader().ResizeMode.ResizeToContents
        )
        self._tbl_polarity.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tbl_polarity.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._tbl_polarity.setAlternatingRowColors(True)
        self._tbl_polarity.verticalHeader().setVisible(False)
        self._tbl_polarity.setMinimumHeight(100)
        # 行高稍大，避免 combobox 被截断
        self._tbl_polarity.verticalHeader().setDefaultSectionSize(28)

        scroll = QScrollArea()
        scroll.setWidget(self._tbl_polarity)
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(140)
        scroll.setMaximumHeight(260)
        layout.addWidget(scroll)
        return group

    def _build_rho_group(self) -> QGroupBox:
        group = QGroupBox("Distinguishing Coefficient (rho)")
        group.setStyleSheet(_GROUP_STYLE)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(6)

        header_row = QHBoxLayout()
        lbl_left = QLabel("0.01")
        lbl_left.setStyleSheet("font-size: 8pt; color: #666;")
        self._lbl_rho_value = QLabel(f"rho = {_RHO_DEFAULT:.2f}")
        self._lbl_rho_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_rho_value.setStyleSheet("font-weight: bold; font-size: 9pt;")
        lbl_right = QLabel("1.00")
        lbl_right.setStyleSheet("font-size: 8pt; color: #666;")
        header_row.addWidget(lbl_left)
        header_row.addStretch()
        header_row.addWidget(self._lbl_rho_value)
        header_row.addStretch()
        header_row.addWidget(lbl_right)
        layout.addLayout(header_row)

        self._slider_rho = QSlider(Qt.Orientation.Horizontal)
        self._slider_rho.setRange(int(_RHO_MIN * _RHO_SCALE), int(_RHO_MAX * _RHO_SCALE))
        self._slider_rho.setValue(int(_RHO_DEFAULT * _RHO_SCALE))
        self._slider_rho.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._slider_rho.setTickInterval(10)
        layout.addWidget(self._slider_rho)
        return group

    def _build_run_button(self) -> QPushButton:
        self._btn_run = QPushButton(">> Run Analysis")
        self._btn_run.setEnabled(False)
        self._btn_run.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._btn_run.setMinimumHeight(38)   # 稍高，更易点击
        font = QFont()
        font.setBold(True)
        font.setPointSize(10)
        self._btn_run.setFont(font)
        self._btn_run.setStyleSheet(
            "QPushButton {"
            "  background-color: #2171B5;"
            "  color: white;"
            "  border-radius: 5px;"
            "  padding: 6px 16px;"
            "}"
            "QPushButton:hover:enabled { background-color: #1A5C9A; }"
            "QPushButton:disabled { background-color: #ADB5BD; color: #F8F9FA; }"
        )
        return self._btn_run

    def _connect_internal_signals(self) -> None:
        self._btn_load.clicked.connect(self._on_load_clicked)
        self._btn_run.clicked.connect(self._on_run_clicked)
        self._slider_rho.valueChanged.connect(self._on_rho_changed)
        self._cmb_ref_column.currentIndexChanged.connect(self._refresh_polarity_table)
        self._cmb_id_column.currentIndexChanged.connect(self._refresh_polarity_table)
        self._dot_timer.timeout.connect(self._on_dot_tick)

    def _on_load_clicked(self) -> None:
        file_path_str, _ = QFileDialog.getOpenFileName(
            self, "Open Dataset", "",
            "Data Files (*.csv *.xlsx *.xls);;CSV Files (*.csv);;Excel Files (*.xlsx *.xls);;All Files (*)",
        )
        if not file_path_str:
            return
        file_path = Path(file_path_str)
        self.status_message.emit(f"Loading {file_path.name}...")
        try:
            df = load_dataframe(file_path)
        except Exception as exc:
            QMessageBox.critical(self, "Load Error", f"Failed to load '{file_path.name}':\n\n{exc}")
            self.status_message.emit("File load failed.")
            logger.exception("File load error for '%s'.", file_path)
            return
        self._dataframe = df
        self._file_path = file_path
        self._lbl_file.setText(f"{file_path.name}  ({len(df):,} rows)")
        self._lbl_file.setStyleSheet(
            "color: #1A6B2A; font-style: normal; font-size: 8pt; font-weight: bold;"
        )
        self._populate_column_combos(df)
        self._refresh_polarity_table()
        self._btn_run.setEnabled(True)
        self.status_message.emit(
            f"Loaded '{file_path.name}' - {len(df):,} rows x {len(df.columns)} columns."
        )
        self.dataset_loaded.emit(df, file_path)
        logger.info("Dataset loaded: %s (%d rows).", file_path.name, len(df))

    def _populate_column_combos(self, df: pd.DataFrame) -> None:
        columns = list(df.columns)
        for cmb in (self._cmb_id_column, self._cmb_ref_column):
            cmb.blockSignals(True)
            cmb.clear()
            cmb.addItems(columns)
            cmb.blockSignals(False)
        if len(columns) >= 2:
            self._cmb_id_column.setCurrentIndex(0)
            self._cmb_ref_column.setCurrentIndex(1)

    def _refresh_polarity_table(self) -> None:
        if self._dataframe is None:
            return
        id_col = self._cmb_id_column.currentText()
        ref_col = self._cmb_ref_column.currentText()
        comparative_cols = [col for col in self._dataframe.columns if col not in (id_col, ref_col)]
        self._tbl_polarity.setRowCount(0)
        for row_idx, col_name in enumerate(comparative_cols):
            self._tbl_polarity.insertRow(row_idx)
            name_item = QTableWidgetItem(col_name)
            name_item.setToolTip(col_name)
            self._tbl_polarity.setItem(row_idx, 0, name_item)
            cmb = QComboBox()
            for label, _ in _POLARITY_OPTIONS:
                cmb.addItem(label)
            self._tbl_polarity.setCellWidget(row_idx, 1, cmb)
        self._tbl_polarity.resizeRowsToContents()

    def _on_rho_changed(self, int_value: int) -> None:
        rho = int_value / _RHO_SCALE
        self._lbl_rho_value.setText(f"rho = {rho:.2f}")

    def _on_run_clicked(self) -> None:
        if self._dataframe is None:
            QMessageBox.warning(self, "No Data", "Load a dataset first.")
            return
        config = self._build_config()
        if config is None:
            return
        self._run_timer.start()
        self.run_requested.emit(config)

    def _build_config(self) -> Optional[GRAConfig]:
        id_col = self._cmb_id_column.currentText()
        ref_col = self._cmb_ref_column.currentText()
        ref_polarity_idx = self._cmb_ref_polarity.currentIndex()
        _, ref_polarity = _POLARITY_OPTIONS[ref_polarity_idx]
        rho = self._slider_rho.value() / _RHO_SCALE
        comparative_columns: dict[str, ColumnConfig] = {}
        for row in range(self._tbl_polarity.rowCount()):
            factor_name = self._tbl_polarity.item(row, 0).text()
            cmb: QComboBox = self._tbl_polarity.cellWidget(row, 1)  # type: ignore[assignment]
            _, polarity = _POLARITY_OPTIONS[cmb.currentIndex()]
            comparative_columns[factor_name] = ColumnConfig(name=factor_name, polarity=polarity)
        if not comparative_columns:
            QMessageBox.warning(
                self, "Configuration Error",
                "At least one comparative factor is required."
            )
            return None
        if ref_col == id_col:
            QMessageBox.warning(
                self, "Configuration Error",
                "Reference column and ID column must be different."
            )
            return None
        return GRAConfig(
            id_column=id_col,
            reference_column=ref_col,
            reference_polarity=ref_polarity,
            comparative_columns=comparative_columns,
            rho=rho,
        )

    # ------------------------------------------------------------------
    # Public API — called by MainWindow
    # ------------------------------------------------------------------

    def set_running_state(self, running: bool) -> None:
        """Toggle the animated computing state of the Run button."""
        self._btn_run.setEnabled(not running)
        if running:
            self._dot_count = 0
            self._dot_timer.start(400)
            self._btn_run.setText("Computing.")
        else:
            self._dot_timer.stop()
            self._btn_run.setText(">> Run Analysis")

    def _on_dot_tick(self) -> None:
        self._dot_count = (self._dot_count + 1) % 4
        dots = "." * self._dot_count
        self._btn_run.setText(f"Computing{dots}")
