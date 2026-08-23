from __future__ import annotations

import enum

import pandas as pd
from pydantic import BaseModel, Field, field_validator, model_validator


class Polarity(str, enum.Enum):
    LTB = "LTB"
    STB = "STB"

    @property
    def label(self) -> str:
        return {
            Polarity.LTB: "Larger is Better",
            Polarity.STB: "Smaller is Better",
        }[self]

    @classmethod
    def from_label(cls, label: str) -> "Polarity":
        mapping = {
            "Larger is Better": cls.LTB,
            "Smaller is Better": cls.STB,
        }
        try:
            return mapping[label]
        except KeyError as exc:
            raise ValueError(
                f"Unknown polarity label {label!r}. Expected one of {list(mapping)}."
            ) from exc


class ColumnConfig(BaseModel):
    name: str
    polarity: Polarity

    model_config = {"frozen": True}

    def __repr__(self) -> str:
        return f"ColumnConfig(name={self.name!r}, polarity={self.polarity.value!r})"


class GRAConfig(BaseModel):
    id_column: str
    reference_column: str
    reference_polarity: Polarity
    comparative_columns: dict[str, ColumnConfig]
    rho: float = Field(default=0.5, ge=0.01, le=1.0)

    model_config = {"frozen": True}

    @field_validator("comparative_columns")
    @classmethod
    def _validate_comparative_not_empty(
        cls,
        value: dict[str, ColumnConfig],
    ) -> dict[str, ColumnConfig]:
        if not value:
            raise ValueError("At least one comparative column must be selected.")
        return value

    @model_validator(mode="after")
    def _validate_no_overlap(self) -> "GRAConfig":
        if self.reference_column in self.comparative_columns:
            raise ValueError(
                f"Reference column {self.reference_column!r} cannot also be comparative."
            )
        return self

    @property
    def comparative_column_names(self) -> list[str]:
        return list(self.comparative_columns)

    def __repr__(self) -> str:
        return (
            "GRAConfig("
            f"ref={self.reference_column!r}, "
            f"comp={self.comparative_column_names}, "
            f"rho={self.rho})"
        )


class GRAResult(BaseModel):
    config: GRAConfig
    normalised_df: pd.DataFrame
    delta_df: pd.DataFrame
    coefficient_df: pd.DataFrame
    grg_series: pd.Series
    ranked_factors: list[str]

    model_config = {
        "frozen": True,
        "arbitrary_types_allowed": True,
    }

    @property
    def top_factor(self) -> str:
        if not self.ranked_factors:
            raise ValueError("No ranked factors are available.")
        return self.ranked_factors[0]

    @property
    def n_samples(self) -> int:
        return len(self.normalised_df)

    @property
    def n_factors(self) -> int:
        return len(self.ranked_factors)

    def summary_string(self) -> str:
        lines = [
            f"GRA Result — {self.n_samples} samples, "
            f"{self.n_factors} factors (ρ = {self.config.rho})",
            "-" * 50,
        ]
        for rank, name in enumerate(self.ranked_factors, start=1):
            grade = float(self.grg_series[name])
            lines.append(f"  #{rank:>2}  {name:<35} GRG = {grade:.4f}")
        return "\n".join(lines)
