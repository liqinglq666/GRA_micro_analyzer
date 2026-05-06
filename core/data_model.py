# core/data_model.py
"""
GRA-MicroAnalyzer 鈥� Domain Data Models
=======================================
All configuration and result objects are immutable (frozen) Pydantic v2
models.  Immutability guarantees that:

1. The UI layer cannot accidentally mutate config after handing it to
   the worker thread.
2. Results passed back via Qt signals are safe to inspect from any
   thread without synchronisation primitives.

If Pydantic is not available the module falls back to stdlib dataclasses
with manual validators, preserving runtime compatibility.
"""

from __future__ import annotations

import enum
from typing import Dict, Optional

import pandas as pd

try:
    from pydantic import BaseModel, Field, field_validator, model_validator
    _PYDANTIC_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PYDANTIC_AVAILABLE = False


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class Polarity(str, enum.Enum):
    """
    Normalisation direction for a single data sequence.

    Attributes
    ----------
    LTB:
        Larger-is-Better.  x* = (x - min) / (max - min).
        Use when higher raw values indicate better performance,
        e.g. Tensile Strain, Compressive Strength.
    STB:
        Smaller-is-Better.  x* = (max - x) / (max - min).
        Use when lower raw values indicate better performance,
        e.g. Crack Width, Water Absorption, Porosity.
    """

    LTB = "LTB"
    STB = "STB"

    # Convenience display labels used directly in QComboBox items.
    @property
    def label(self) -> str:
        """Return a human-readable label for display in the UI."""
        labels: dict[str, str] = {
            "LTB": "Larger is Better",
            "STB": "Smaller is Better",
        }
        return labels[self.value]

    @classmethod
    def from_label(cls, label: str) -> "Polarity":
        """
        Reverse-lookup from a UI display label back to the enum member.

        Parameters
        ----------
        label:
            One of the strings returned by :py:attr:`label`.

        Raises
        ------
        ValueError
            If *label* does not match any known polarity label.
        """
        mapping: dict[str, Polarity] = {
            "Larger is Better": cls.LTB,
            "Smaller is Better": cls.STB,
        }
        if label not in mapping:
            raise ValueError(
                f"Unknown polarity label '{label}'. "
                f"Expected one of: {list(mapping.keys())}."
            )
        return mapping[label]


# ---------------------------------------------------------------------------
# Configuration Model
# ---------------------------------------------------------------------------


class ColumnConfig(BaseModel if _PYDANTIC_AVAILABLE else object):  # type: ignore[misc]
    """
    Configuration for a single comparative sequence column.

    Attributes
    ----------
    name:
        The exact column header string from the loaded DataFrame.
    polarity:
        The normalisation direction for this column.
    """

    name: str
    polarity: Polarity

    if _PYDANTIC_AVAILABLE:
        model_config = {"frozen": True}

    def __repr__(self) -> str:
        return (
            f"ColumnConfig(name={self.name!r}, polarity={self.polarity.value!r})"
        )


class GRAConfig(BaseModel if _PYDANTIC_AVAILABLE else object):  # type: ignore[misc]
    """
    Complete, validated configuration for one GRA run.

    This object is constructed by the ConfigPanel widget and passed
    directly to the GRAWorker thread.  All fields are validated on
    construction; an invalid config never reaches the engine.

    Attributes
    ----------
    id_column:
        Column used as sample identifiers in plots and result tables.
        Need not be numeric.
    reference_column:
        The macroscopic performance indicator (reference sequence).
    reference_polarity:
        Normalisation direction for the reference sequence.
    comparative_columns:
        Ordered mapping from column name to its ColumnConfig.
        Must contain at least one entry.
    rho:
        Distinguishing coefficient 蟻 鈭� (0, 1].  Default 0.5 per
        Deng (1989).  Values closer to 0 amplify differences between
        relational coefficients; values near 1 compress them.
    """

    id_column: str
    reference_column: str
    reference_polarity: Polarity
    comparative_columns: Dict[str, ColumnConfig]
    rho: float = Field(default=0.5, ge=0.01, le=1.0)

    if _PYDANTIC_AVAILABLE:
        model_config = {"frozen": True}

        @field_validator("comparative_columns")
        @classmethod
        def _validate_comparative_not_empty(
            cls, v: Dict[str, ColumnConfig]
        ) -> Dict[str, ColumnConfig]:
            if not v:
                raise ValueError(
                    "At least one comparative column must be selected."
                )
            return v

        @model_validator(mode="after")
        def _validate_no_overlap(self) -> "GRAConfig":
            if self.reference_column in self.comparative_columns:
                raise ValueError(
                    f"Reference column '{self.reference_column}' cannot "
                    f"also appear as a comparative column."
                )
            return self

    @property
    def comparative_column_names(self) -> list[str]:
        """Return an ordered list of comparative column name strings."""
        return list(self.comparative_columns.keys())

    def __repr__(self) -> str:
        return (
            f"GRAConfig("
            f"ref={self.reference_column!r}, "
            f"comp={self.comparative_column_names}, "
            f"rho={self.rho})"
        )


# ---------------------------------------------------------------------------
# Result Model
# ---------------------------------------------------------------------------


class GRAResult(BaseModel if _PYDANTIC_AVAILABLE else object):  # type: ignore[misc]
    """
    Immutable container for all artefacts produced by one GRA run.

    Attributes
    ----------
    config:
        The exact configuration that produced these results, enabling
        full reproducibility from the result object alone.
    normalised_df:
        DataFrame of shape (n_samples, n_sequences) holding x* values
        for all sequences (reference + comparative).
    delta_df:
        DataFrame of shape (n_samples, n_comparative) holding |螖| values.
    coefficient_df:
        DataFrame of shape (n_samples, n_comparative) holding 尉(k) values.
    grg_series:
        Series of length n_comparative holding the Grey Relational Grade
        for each comparative factor, sorted descending.
    ranked_factors:
        List of comparative column names sorted from highest to lowest GRG,
        i.e. from most influential to least influential.
    """

    config: GRAConfig
    normalised_df: pd.DataFrame
    delta_df: pd.DataFrame
    coefficient_df: pd.DataFrame
    grg_series: pd.Series
    ranked_factors: list[str]

    if _PYDANTIC_AVAILABLE:
        model_config = {"frozen": True, "arbitrary_types_allowed": True}

    @property
    def top_factor(self) -> str:
        """Return the single most influential comparative factor."""
        return self.ranked_factors[0]

    @property
    def n_samples(self) -> int:
        """Return the number of material samples analysed."""
        return len(self.normalised_df)

    @property
    def n_factors(self) -> int:
        """Return the number of comparative factors evaluated."""
        return len(self.ranked_factors)

    def summary_string(self) -> str:
        """
        Produce a compact plain-text summary suitable for a status bar
        or log entry.

        Returns
        -------
        str
            Multi-line summary of GRG values in descending rank order.
        """
        lines: list[str] = [
            f"GRA Result 鈥� {self.n_samples} samples, "
            f"{self.n_factors} factors (蟻 = {self.config.rho})",
            "-" * 50,
        ]
        for rank, name in enumerate(self.ranked_factors, start=1):
            grade = self.grg_series[name]
            lines.append(f"  #{rank:>2}  {name:<35} GRG = {grade:.4f}")
        return "\n".join(lines)
