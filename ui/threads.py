# -*- coding: utf-8 -*-
# ui/threads.py
"""
GRA-MicroAnalyzer - Background Worker Thread
=============================================
GRAWorker runs ONLY the GRA computation in the background thread.
All figure building happens on the main thread after result_signal.

Signals
-------
progress_signal(int)   0-100
result_signal(GRAResult)
error_signal(str)
log_signal(str)
"""

from __future__ import annotations

import logging
import traceback
from typing import Optional

import pandas as pd
from PySide6.QtCore import QThread, Signal

from core.data_model import GRAConfig, GRAResult
from core.exceptions import GRABaseException
from core.gra_engine import GreyRelationalAnalyzer

logger = logging.getLogger(__name__)


class GRAWorker(QThread):
    """
    QThread that runs the GRA computation pipeline in the background.
    No figures are created here — all plotting is done on the main thread.

    Parameters
    ----------
    dataframe : pd.DataFrame
    config    : GRAConfig
    parent    : optional Qt parent
    """

    progress_signal: Signal = Signal(int)
    result_signal: Signal = Signal(object)   # GRAResult
    error_signal: Signal = Signal(str)
    log_signal: Signal = Signal(str)

    def __init__(
        self,
        dataframe: pd.DataFrame,
        config: GRAConfig,
        parent: Optional[object] = None,
    ) -> None:
        super().__init__(parent)  # type: ignore[arg-type]
        self._dataframe: pd.DataFrame = dataframe.copy()
        self._config: GRAConfig = config
        self._analyzer: GreyRelationalAnalyzer = GreyRelationalAnalyzer()

    def run(self) -> None:
        """Execute the GRA pipeline in the worker thread."""
        try:
            result = self._stage_compute()
            self.result_signal.emit(result)
            self.progress_signal.emit(100)
            self.log_signal.emit(
                f"Result ready - top factor: '{result.top_factor}' "
                f"(GRG={result.grg_series[result.top_factor]:.4f})."
            )
            logger.info("GRAWorker completed successfully.")

        except GRABaseException as exc:
            logger.warning("GRAWorker domain error: %s", exc.message)
            self.progress_signal.emit(0)
            self.error_signal.emit(exc.message)

        except MemoryError as exc:
            message = (
                "Insufficient memory to complete the analysis.\n"
                "Try reducing the dataset size or closing other applications."
            )
            logger.error("GRAWorker MemoryError: %s", exc)
            self.progress_signal.emit(0)
            self.error_signal.emit(message)

        except Exception as exc:  # noqa: BLE001
            tb_str = traceback.format_exc()
            logger.error("GRAWorker unexpected error:\n%s", tb_str)
            self.progress_signal.emit(0)
            self.error_signal.emit(
                f"An unexpected error occurred during analysis:\n\n"
                f"{type(exc).__name__}: {exc}\n\n"
                f"Please check the application log for the full traceback."
            )

    def _stage_compute(self) -> GRAResult:
        self.progress_signal.emit(10)
        self.log_signal.emit(
            f"Computing GRA - reference: '{self._config.reference_column}', "
            f"{len(self._config.comparative_columns)} comparative factor(s)..."
        )
        result: GRAResult = self._analyzer.run(self._dataframe, self._config)
        self.progress_signal.emit(70)
        self.log_signal.emit(
            f"Computation complete - top factor: '{result.top_factor}'."
        )
        return result
