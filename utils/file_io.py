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

    for enc in ("utf-8-sig", "utf-8", "gbk", "latin-1"):
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
    """
    Load a CSV or Excel file into a DataFrame.
    Used by ConfigPanel to preview uploaded data.
    """
    import pandas as pd

    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix in (".xlsx", ".xls"):
        return pd.read_excel(path)
    if suffix == ".csv":
        return _read_csv_any_encoding(path)

    raise ValueError(f"Unsupported file type: '{suffix}'. Use .csv, .xlsx, or .xls.")


def load_dataset(file_path) -> "pd.DataFrame":
    """
    Extended version of load_dataframe.
    Strips fully-empty rows/columns after loading.
    """
    df = load_dataframe(file_path)
    df = df.dropna(how="all").dropna(axis=1, how="all")
    df = df.reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Public API — Saving
# ---------------------------------------------------------------------------

def save_results_to_excel(result: "GRAResult", output_path) -> Path:
    """
    Export a completed GRAResult to a multi-sheet Excel workbook.

    Sheet layout
    ------------
    1. GRG Ranking          — Factors ranked by descending Grey Relational Grade,
                              with rank number, GRG value, and percentile.
    2. Normalised Sequences — The x* normalised data matrix (values in [0, 1]).
    3. Delta (Δ) Matrix     — Absolute difference |x0*(k) - xi*(k)| per cell.
    4. ξ Coefficient Matrix — Grey relational coefficient ξ(k) per cell.
    5. Analysis Config      — All parameters used in this run (rho, columns, etc.).

    Parameters
    ----------
    result:
        Fully computed GRAResult from GRAWorker.
    output_path:
        Destination .xlsx path. Parent directories are created automatically.

    Returns
    -------
    Path
        Resolved path of the written file.
    """
    import pandas as pd

    out = Path(output_path)
    if not out.suffix:
        out = out.with_suffix(".xlsx")
    out.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Sheet 1 — GRG Ranking
    # ------------------------------------------------------------------
    grg_series = result.grg_series.sort_values(ascending=False)
    grg_df = pd.DataFrame({
        "Rank":                  range(1, len(grg_series) + 1),
        "Factor":                grg_series.index.tolist(),
        "Grey Relational Grade": grg_series.values.round(6),
        "Percentile (%)":        (grg_series.rank(pct=True) * 100).round(1).values,
    })

    # ------------------------------------------------------------------
    # Sheet 2 — Normalised Sequences
    # ------------------------------------------------------------------
    norm_df = result.normalised_df.copy()
    norm_df = norm_df.round(6)

    # ------------------------------------------------------------------
    # Sheet 3 — Delta Matrix
    # ------------------------------------------------------------------
    delta_df = result.delta_df.copy()
    delta_df = delta_df.round(6)

    # ------------------------------------------------------------------
    # Sheet 4 — ξ Coefficient Matrix
    # ------------------------------------------------------------------
    coeff_df = result.coefficient_df.copy()
    coeff_df = coeff_df.round(6)

    # ------------------------------------------------------------------
    # Sheet 5 — Analysis Config
    # ------------------------------------------------------------------
    cfg = result.config
    comp_cols = cfg.comparative_columns  # dict[str, ColumnConfig]

    config_rows = [
        ("Reference Column (Target)", cfg.reference_column),
        ("Reference Polarity",        cfg.reference_polarity.label),
        ("Distinguishing Coeff. ρ",   cfg.rho),
        ("Sample ID Column",          cfg.id_column if cfg.id_column else "— (none)"),
        ("Number of Comparative Factors", len(comp_cols)),
        ("", ""),  # blank separator
        ("Comparative Factors", "Polarity"),
    ]
    for col_name, col_cfg in comp_cols.items():
        config_rows.append((col_name, col_cfg.polarity.label))

    config_df = pd.DataFrame(config_rows, columns=["Parameter", "Value"])

    # ------------------------------------------------------------------
    # Write workbook
    # ------------------------------------------------------------------
    sheets = {
        "GRG Ranking":           (grg_df,    False),   # (df, write_index)
        "Normalised Sequences":  (norm_df,   True),
        "Delta Matrix":          (delta_df,  True),
        "Xi Coefficient Matrix": (coeff_df,  True),
        "Analysis Config":       (config_df, False),
    }

    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        for sheet_name, (df, write_index) in sheets.items():
            df.to_excel(writer, sheet_name=sheet_name, index=write_index)

            # Auto-fit column widths
            ws = writer.sheets[sheet_name]
            for col_cells in ws.columns:
                max_len = max(
                    (len(str(cell.value)) if cell.value is not None else 0)
                    for cell in col_cells
                )
                ws.column_dimensions[col_cells[0].column_letter].width = min(
                    max_len + 4, 50
                )

    return out
