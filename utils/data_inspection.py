"""Dataset-inspection helpers shared by UI configuration code."""

from __future__ import annotations

from typing import Final

import numpy as np
import pandas as pd

MIN_NUMERIC_VALID_COUNT: Final[int] = 3
MIN_NUMERIC_VALID_RATIO: Final[float] = 0.80

NumericQuality = tuple[int, int, float]


def detect_reliable_numeric_columns(
    dataframe: pd.DataFrame,
    *,
    min_valid_count: int = MIN_NUMERIC_VALID_COUNT,
    min_valid_ratio: float = MIN_NUMERIC_VALID_RATIO,
) -> tuple[list[str], dict[str, NumericQuality]]:
    """Return reliable numeric-compatible columns and per-column quality stats.

    The conversion and finite-value rules intentionally match the historical
    ``ConfigPanel._detect_numeric_columns`` implementation.
    """
    numeric_columns: list[str] = []
    quality: dict[str, NumericQuality] = {}
    total_rows = len(dataframe)

    for column in dataframe.columns:
        converted = pd.to_numeric(dataframe[column], errors="coerce")
        finite_mask = np.isfinite(converted.to_numpy(dtype=float, na_value=np.nan))
        valid_count = int(finite_mask.sum())
        valid_ratio = valid_count / total_rows if total_rows else 0.0
        quality[column] = (valid_count, total_rows, valid_ratio)

        if valid_count >= min_valid_count and valid_ratio >= min_valid_ratio:
            numeric_columns.append(column)

    return numeric_columns, quality
