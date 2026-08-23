# -*- coding: utf-8 -*-
"""
utils/file_io.py
File I/O utilities for GRA-MicroAnalyzer.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd
    from core.data_model import GRAResult


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _read_csv_any_encoding(path: Path) -> "pd.DataFrame":
    """Try common encodings until one works."""
    import pandas as pd

    for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030", "latin-1"):
        try:
            return pd.read_csv(path, encoding=enc)
        except (UnicodeDecodeError, LookupError):
            continue
    raise ValueError(
        f"Cannot decode '{path.name}' with any supported encoding. "
        "Please re-save it as UTF-8."
    )


# ---------------------------------------------------------------------------
# Public API — Loading
# ---------------------------------------------------------------------------

def load_dataframe(file_path) -> "pd.DataFrame":
    """Load a CSV or Excel file into a DataFrame."""
    import pandas as pd

    path = Path(file_path)
    suffix = path.suffix.lower()

    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    if suffix in (".xlsx", ".xls"):
        return pd.read_excel(path)
    if suffix == ".csv":
        return _read_csv_any_encoding(path)

    raise ValueError(f"Unsupported file type: '{suffix}'. Use .csv, .xlsx, or .xls.")


def load_dataset(file_path) -> "pd.DataFrame":
    """
    Extended version of load_dataframe.
    Strips fully-empty rows/columns after loading and normalises headers.
    """
    df = load_dataframe(file_path)
    df = df.dropna(how="all").dropna(axis=1, how="all")
    df = df.rename(columns=lambda c: str(c).strip())
    df = df.reset_index(drop=True)

    if df.empty:
        raise ValueError("The selected file contains no usable tabular data.")
    if len(df.columns) < 2:
        raise ValueError("At least two columns are required: one ID/target column and one factor column.")

    return df


# ---------------------------------------------------------------------------
# Public API — Saving
# ---------------------------------------------------------------------------

def save_results_to_excel(result: "GRAResult", output_path) -> Path:
    """Export a completed GRAResult to a multi-sheet Excel workbook."""
    import pandas as pd

    out = Path(output_path)
    if out.suffix.lower() != ".xlsx":
        out = out.with_suffix(".xlsx")
    out.parent.mkdir(parents=True, exist_ok=True)

    grg_series = result.grg_series.sort_values(ascending=False)
    grg_df = pd.DataFrame({
        "Rank":                  range(1, len(grg_series) + 1),
        "Factor":                grg_series.index.tolist(),
        "Grey Relational Grade": grg_series.values.round(6),
        "Percentile (%)":        (grg_series.rank(pct=True) * 100).round(1).values,
    })

    norm_df = result.normalised_df.copy().round(6)
    delta_df = result.delta_df.copy().round(6)
    coeff_df = result.coefficient_df.copy().round(6)

    cfg = result.config
    comp_cols = cfg.comparative_columns
    config_rows = [
        ("Reference Column (Target)", cfg.reference_column),
        ("Reference Polarity",        cfg.reference_polarity.label),
        ("Distinguishing Coeff. ρ",   cfg.rho),
        ("Sample ID Column",          cfg.id_column if cfg.id_column else "— (none)"),
        ("Number of Comparative Factors", len(comp_cols)),
        ("", ""),
        ("Comparative Factors", "Polarity"),
    ]
    for col_name, col_cfg in comp_cols.items():
        config_rows.append((col_name, col_cfg.polarity.label))
    config_df = pd.DataFrame(config_rows, columns=["Parameter", "Value"])

    sheets = {
        "GRG Ranking":           (grg_df,    False),
        "Normalised Sequences":  (norm_df,   True),
        "Delta Matrix":          (delta_df,  True),
        "Xi Coefficient Matrix": (coeff_df,  True),
        "Analysis Config":       (config_df, False),
    }

    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        for sheet_name, (df, write_index) in sheets.items():
            df.to_excel(writer, sheet_name=sheet_name, index=write_index)
            ws = writer.sheets[sheet_name]
            for col_cells in ws.columns:
                max_len = max(
                    (len(str(cell.value)) if cell.value is not None else 0)
                    for cell in col_cells
                )
                ws.column_dimensions[col_cells[0].column_letter].width = min(
                    max_len + 4, 50
                )

    return out.resolve()
