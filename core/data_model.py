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
        if self.id_column == self.reference_column:
            raise ValueError("ID column and reference column must be different.")
        if self.id_column in self.comparative_columns:
            raise ValueError("ID column cannot also be a comparative factor.")
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


class DataQualityReport(BaseModel):
    """Audit trail describing how input data changed before GRA computation."""

    original_rows: int = 0
    retained_rows: int = 0
    dropped_rows: int = 0
    conversion_failures: dict[str, int] = Field(default_factory=dict)
    non_finite_values: dict[str, int] = Field(default_factory=dict)
    dropped_constant_factors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    model_config = {"frozen": True}


class GRAResult(BaseModel):
    config: GRAConfig
    normalised_df: pd.DataFrame
    delta_df: pd.DataFrame
    coefficient_df: pd.DataFrame
    grg_series: pd.Series
    ranked_factors: list[str]
    data_quality: DataQualityReport = Field(default_factory=DataQualityReport)

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

    @property
    def rank_by_factor(self) -> dict[str, int]:
        """Competition ranks; tied GRG values receive the same rank."""
        ranks = self.grg_series.rank(method="min", ascending=False)
        return {str(name): int(rank) for name, rank in ranks.items()}

    def summary_string(self) -> str:
        lines = [
            f"GRA Result — {self.n_samples} samples, "
            f"{self.n_factors} factors (ρ = {self.config.rho})",
            "-" * 50,
        ]
        ranks = self.rank_by_factor
        for name in self.ranked_factors:
            grade = float(self.grg_series[name])
            lines.append(f"  #{ranks[name]:>2}  {name:<35} GRG = {grade:.4f}")

        if self.data_quality.original_rows:
            lines.extend(
                [
                    "-" * 50,
                    "Data quality: "
                    f"{self.data_quality.retained_rows}/{self.data_quality.original_rows} "
                    "rows retained",
                ]
            )
        return "\n".join(lines)
