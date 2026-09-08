# -*- coding: utf-8 -*-
"""Configuration panel widget for GRA-MicroAnalyzer."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import pandas as pd
from PySide6.QtCore import Qt, QElapsedTimer, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
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

from core.data_model import ColumnConfig, GRAConfig, Polarity
from utils.data_inspection import detect_reliable_numeric_columns
from utils.file_io import load_dataset

logger = logging.getLogger(__name__)

_RHO_SCALE = 100
_RHO_DEFAULT = 0.5
_RHO_MIN = 0.01
_RHO_MAX = 1.00

_POLARITY_OPTIONS: list[tuple[str, Polarity]] = [
    ("Larger is Better (+)", Polarity.LTB),
    ("Smaller is Better (-)", Polarity.STB),
]

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
    dataset_loaded = Signal(object, object)   # (pd.DataFrame, Path)
    run_requested = Signal(object)            # (GRAConfig,)
    status_message = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._dataframe: Optional[pd.DataFrame] = None
        self._file_path: Optional[Path] = None
        self._numeric_columns: list[str] = []
        self._numeric_quality: dict[str, tuple[int, int, float]] = {}
        self._run_timer = QElapsedTimer()
        self._dot_timer = QTimer(self)
        self._dot_count = 0
        self._build_ui()
        self._connect_internal_signals()

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(12)
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
            "The first row must contain unique column headers."
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

        layout.addWidget(QLabel("Sample ID Column:"))
        self._cmb_id_column = QComboBox()
        self._cmb_id_column.setMinimumHeight(26)
        layout.addWidget(self._cmb_id_column)

        layout.addWidget(QLabel("Reference Column (Target):"))
        self._cmb_ref_column = QComboBox()
        self._cmb_ref_column.setMinimumHeight(26)
        layout.addWidget(self._cmb_ref_column)

        layout.addWidget(QLabel("Reference Polarity:"))
        self._cmb_ref_polarity = QComboBox()
        self._cmb_ref_polarity.setMinimumHeight(26)
        for label, _ in _POLARITY_OPTIONS:
            self._cmb_ref_polarity.addItem(label)
        layout.addWidget(self._cmb_ref_polarity)
        return group

    def _build_polarity_group(self) -> QGroupBox:
        group = QGroupBox("Comparative Factors")
        group.setStyleSheet(_GROUP_STYLE)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(5)

        hint = QLabel(
            "Only checked factors are included in GRA. Numeric-compatible columns "
            "must have at least 80% finite numeric values and at least 3 valid values."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #5F6B76; font-size: 8pt;")
        layout.addWidget(hint)

        button_row = QHBoxLayout()
        self._btn_select_all = QPushButton("Select all")
        self._btn_clear_all = QPushButton("Clear all")
        self._btn_select_all.setFixedHeight(24)
        self._btn_clear_all.setFixedHeight(24)
        button_row.addWidget(self._btn_select_all)
        button_row.addWidget(self._btn_clear_all)
        button_row.addStretch()
        layout.addLayout(button_row)

        self._tbl_polarity = QTableWidget(0, 3)
        self._tbl_polarity.setHorizontalHeaderLabels(["Use", "Factor", "Polarity"])
        self._tbl_polarity.horizontalHeader().setStretchLastSection(False)
        self._tbl_polarity.horizontalHeader().setSectionResizeMode(
            0, self._tbl_polarity.horizontalHeader().ResizeMode.ResizeToContents
        )
        self._tbl_polarity.horizontalHeader().setSectionResizeMode(
            1, self._tbl_polarity.horizontalHeader().ResizeMode.Stretch
        )
        self._tbl_polarity.horizontalHeader().setSectionResizeMode(
            2, self._tbl_polarity.horizontalHeader().ResizeMode.ResizeToContents
        )
        self._tbl_polarity.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tbl_polarity.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._tbl_polarity.setAlternatingRowColors(True)
        self._tbl_polarity.verticalHeader().setVisible(False)
        self._tbl_polarity.setMinimumHeight(100)
        self._tbl_polarity.verticalHeader().setDefaultSectionSize(28)

        scroll = QScrollArea()
        scroll.setWidget(self._tbl_polarity)
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(150)
        scroll.setMaximumHeight(280)
        layout.addWidget(scroll)
        return group

    def _build_rho_group(self) -> QGroupBox:
        group = QGroupBox("Distinguishing Coefficient (rho)")
        group.setStyleSheet(_GROUP_STYLE)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(6)

        header_row = QHBoxLayout()
        header_row.addWidget(QLabel("0.01"))
        header_row.addStretch()
        self._lbl_rho_value = QLabel(f"rho = {_RHO_DEFAULT:.2f}")
        self._lbl_rho_value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_rho_value.setStyleSheet("font-weight: bold; font-size: 9pt;")
        header_row.addWidget(self._lbl_rho_value)
        header_row.addStretch()
        header_row.addWidget(QLabel("1.00"))
        layout.addLayout(header_row)

        self._slider_rho = QSlider(Qt.Orientation.Horizontal)
        self._slider_rho.setRange(
            int(_RHO_MIN * _RHO_SCALE),
            int(_RHO_MAX * _RHO_SCALE),
        )
        self._slider_rho.setValue(int(_RHO_DEFAULT * _RHO_SCALE))
        self._slider_rho.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._slider_rho.setTickInterval(10)
        layout.addWidget(self._slider_rho)
        return group

    def _build_run_button(self) -> QPushButton:
        self._btn_run = QPushButton(">> Run Analysis")
        self._btn_run.setEnabled(False)
        self._btn_run.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self._btn_run.setMinimumHeight(38)
        font = QFont()
        font.setBold(True)
        font.setPointSize(10)
        self._btn_run.setFont(font)
        self._btn_run.setStyleSheet(
            "QPushButton { background-color: #2171B5; color: white; border-radius: 5px; padding: 6px 16px; }"
            "QPushButton:hover:enabled { background-color: #1A5C9A; }"
            "QPushButton:disabled { background-color: #ADB5BD; color: #F8F9FA; }"
        )
        return self._btn_run

    def _connect_internal_signals(self) -> None:
        self._btn_load.clicked.connect(self._on_load_clicked)
        self._btn_run.clicked.connect(self._on_run_clicked)
        self._btn_select_all.clicked.connect(
            lambda: self._set_all_factor_checks(True)
        )
        self._btn_clear_all.clicked.connect(
            lambda: self._set_all_factor_checks(False)
        )
        self._slider_rho.valueChanged.connect(self._on_rho_changed)
        self._cmb_ref_column.currentIndexChanged.connect(self._refresh_polarity_table)
        self._cmb_id_column.currentIndexChanged.connect(self._refresh_polarity_table)
        self._dot_timer.timeout.connect(self._on_dot_tick)

    def _on_load_clicked(self) -> None:
        file_path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Open Dataset",
            "",
            "Data Files (*.csv *.xlsx *.xls);;CSV Files (*.csv);;Excel Files (*.xlsx *.xls);;All Files (*)",
        )
        if not file_path_str:
            return

        file_path = Path(file_path_str)
        self.status_message.emit(f"Loading {file_path.name}...")
        try:
            dataframe = load_dataset(file_path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(
                self,
                "Load Error",
                f"Failed to load '{file_path.name}':\n\n{exc}",
            )
            self.status_message.emit("File load failed.")
            logger.exception("File load error for '%s'.", file_path)
            return

        self._dataframe = dataframe
        self._file_path = file_path
        (
            self._numeric_columns,
            self._numeric_quality,
        ) = detect_reliable_numeric_columns(dataframe)
        self._lbl_file.setText(f"{file_path.name}  ({len(dataframe):,} rows)")
        self._lbl_file.setStyleSheet(
            "color: #1A6B2A; font-style: normal; font-size: 8pt; font-weight: bold;"
        )
        self._populate_column_combos(dataframe)
        self._refresh_polarity_table()
        self._btn_run.setEnabled(bool(self._numeric_columns))

        numeric_note = (
            f" {len(self._numeric_columns)} reliable numeric-compatible column(s) detected."
        )
        if not self._numeric_columns:
            numeric_note += " No column meets the numeric quality threshold."
        self.status_message.emit(
            f"Loaded '{file_path.name}' - {len(dataframe):,} rows x "
            f"{len(dataframe.columns)} columns.{numeric_note}"
        )
        self.dataset_loaded.emit(dataframe, file_path)
        logger.info("Dataset loaded: %s (%d rows).", file_path.name, len(dataframe))

    def _detect_numeric_columns(self, dataframe: pd.DataFrame) -> list[str]:
        """Compatibility wrapper for the previous widget-local helper."""
        columns, quality = detect_reliable_numeric_columns(dataframe)
        self._numeric_quality = quality
        return columns

    def _populate_column_combos(self, dataframe: pd.DataFrame) -> None:
        all_columns = list(dataframe.columns)
        numeric_columns = self._numeric_columns

        self._cmb_id_column.blockSignals(True)
        self._cmb_id_column.clear()
        self._cmb_id_column.addItems(all_columns)
        self._cmb_id_column.blockSignals(False)

        self._cmb_ref_column.blockSignals(True)
        self._cmb_ref_column.clear()
        self._cmb_ref_column.addItems(numeric_columns)
        self._cmb_ref_column.blockSignals(False)

        if all_columns:
            self._cmb_id_column.setCurrentIndex(0)
        if numeric_columns:
            self._cmb_ref_column.setCurrentIndex(0)

    def _refresh_polarity_table(self) -> None:
        if self._dataframe is None:
            return

        id_col = self._cmb_id_column.currentText()
        ref_col = self._cmb_ref_column.currentText()
        comparative_cols = [
            column
            for column in self._numeric_columns
            if column not in (id_col, ref_col)
        ]

        self._tbl_polarity.setRowCount(0)
        for row_idx, column_name in enumerate(comparative_cols):
            self._tbl_polarity.insertRow(row_idx)

            check = QCheckBox()
            check.setChecked(True)
            check.setToolTip("Include this factor in the GRA computation.")
            self._tbl_polarity.setCellWidget(row_idx, 0, check)

            valid_count, total_rows, valid_ratio = self._numeric_quality.get(
                column_name,
                (0, len(self._dataframe), 0.0),
            )
            name_item = QTableWidgetItem(column_name)
            name_item.setToolTip(
                f"{column_name}\nFinite numeric values: {valid_count}/{total_rows} "
                f"({valid_ratio:.1%})"
            )
            self._tbl_polarity.setItem(row_idx, 1, name_item)

            combo = QComboBox()
            for label, _ in _POLARITY_OPTIONS:
                combo.addItem(label)
            self._tbl_polarity.setCellWidget(row_idx, 2, combo)

        self._tbl_polarity.resizeRowsToContents()

    def _set_all_factor_checks(self, checked: bool) -> None:
        for row in range(self._tbl_polarity.rowCount()):
            widget = self._tbl_polarity.cellWidget(row, 0)
            if isinstance(widget, QCheckBox):
                widget.setChecked(checked)

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
        if not ref_col:
            QMessageBox.warning(
                self,
                "Configuration Error",
                "Select a reliable numeric-compatible reference column.",
            )
            return None

        ref_polarity_idx = self._cmb_ref_polarity.currentIndex()
        _, ref_polarity = _POLARITY_OPTIONS[ref_polarity_idx]
        rho = self._slider_rho.value() / _RHO_SCALE

        comparative_columns: dict[str, ColumnConfig] = {}
        for row in range(self._tbl_polarity.rowCount()):
            check = self._tbl_polarity.cellWidget(row, 0)
            item = self._tbl_polarity.item(row, 1)
            combo = self._tbl_polarity.cellWidget(row, 2)
            if (
                not isinstance(check, QCheckBox)
                or not check.isChecked()
                or item is None
                or not isinstance(combo, QComboBox)
            ):
                continue

            factor_name = item.text()
            _, polarity = _POLARITY_OPTIONS[combo.currentIndex()]
            comparative_columns[factor_name] = ColumnConfig(
                name=factor_name,
                polarity=polarity,
            )

        if not comparative_columns:
            QMessageBox.warning(
                self,
                "Configuration Error",
                "Select at least one comparative factor using the checkboxes.",
            )
            return None
        if ref_col == id_col:
            QMessageBox.warning(
                self,
                "Configuration Error",
                "Reference column and ID column must be different.",
            )
            return None

        try:
            return GRAConfig(
                id_column=id_col,
                reference_column=ref_col,
                reference_polarity=ref_polarity,
                comparative_columns=comparative_columns,
                rho=rho,
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Configuration Error", str(exc))
            return None

    def set_running_state(self, running: bool) -> None:
        """Toggle the animated computing state of the Run button."""
        self._btn_run.setEnabled(not running and bool(self._numeric_columns))
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
