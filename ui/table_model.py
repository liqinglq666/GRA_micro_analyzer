"""Read-only DataFrame table model and clipboard serializers for the desktop UI."""

from __future__ import annotations

from typing import Iterable, Optional

import pandas as pd
from PySide6.QtCore import (
    QAbstractItemModel,
    QAbstractTableModel,
    QModelIndex,
    QPersistentModelIndex,
    Qt,
)
from PySide6.QtWidgets import QWidget

PREVIEW_ROW_LIMIT = 1_000


class PandasTableModel(QAbstractTableModel):
    """Minimal read-only DataFrame adapter used by the data preview."""

    def __init__(self, dataframe: pd.DataFrame, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._df = dataframe.head(PREVIEW_ROW_LIMIT).reset_index(drop=False)

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
        value = self._df.iat[index.row(), index.column()]
        if role == Qt.ItemDataRole.DisplayRole:
            if isinstance(value, float):
                return f"{value:.4f}"
            return str(value)
        if role == Qt.ItemDataRole.TextAlignmentRole and isinstance(value, (int, float)):
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


def selected_indexes_to_tsv(
    model: QAbstractItemModel,
    indexes: Iterable[QModelIndex],
) -> tuple[str, int]:
    """Serialize selected cells exactly as the historical rectangular copy flow."""
    selected = list(indexes)
    cells = {
        (index.row(), index.column()): str(
            model.data(index, Qt.ItemDataRole.DisplayRole) or ""
        )
        for index in selected
    }
    rows = sorted({row for row, _ in cells})
    cols = sorted({column for _, column in cells})
    headers = [_header_text(model, column) for column in cols]
    lines = ["\t".join(headers)]
    for row in rows:
        lines.append("\t".join(cells.get((row, column), "") for column in cols))
    return "\n".join(lines), len(cells)


def model_to_tsv(model: QAbstractItemModel) -> tuple[str, int, int]:
    """Serialize the full preview model to tab-separated text."""
    n_rows = model.rowCount()
    n_cols = model.columnCount()
    headers = [_header_text(model, column) for column in range(n_cols)]
    lines = ["\t".join(headers)]
    for row in range(n_rows):
        lines.append(
            "\t".join(
                str(
                    model.data(
                        model.index(row, column),
                        Qt.ItemDataRole.DisplayRole,
                    )
                    or ""
                )
                for column in range(n_cols)
            )
        )
    return "\n".join(lines), n_rows, n_cols


def _header_text(model: QAbstractItemModel, column: int) -> str:
    return str(
        model.headerData(
            column,
            Qt.Orientation.Horizontal,
            Qt.ItemDataRole.DisplayRole,
        )
        or ""
    )
