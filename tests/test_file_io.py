from pathlib import Path

import pandas as pd
import pytest

from core.data_model import ColumnConfig, GRAConfig, Polarity
from core.gra_engine import GreyRelationalAnalyzer
from utils.file_io import load_dataset, save_results_to_excel


def test_duplicate_headers_after_whitespace_trim_are_rejected(tmp_path: Path):
    csv_path = tmp_path / "duplicate_headers.csv"
    csv_path.write_text(
        "Sample,Target, Target\nA,1,2\nB,2,3\nC,3,4\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Duplicate column headers"):
        load_dataset(csv_path)


def test_excel_export_contains_data_quality_sheet_and_tied_ranks(tmp_path: Path):
    df = pd.DataFrame(
        {
            "Sample": ["A", "B", "C"],
            "Target": [1.0, 2.0, 3.0],
            "Factor_A": [1.0, 2.0, 3.0],
            "Factor_B": [10.0, 20.0, 30.0],
        }
    )
    config = GRAConfig(
        id_column="Sample",
        reference_column="Target",
        reference_polarity=Polarity.LTB,
        comparative_columns={
            "Factor_A": ColumnConfig(name="Factor_A", polarity=Polarity.LTB),
            "Factor_B": ColumnConfig(name="Factor_B", polarity=Polarity.LTB),
        },
        rho=0.5,
    )
    result = GreyRelationalAnalyzer().run(df, config)

    output = save_results_to_excel(result, tmp_path / "result.xlsx")
    workbook = pd.ExcelFile(output)
    assert "Data Quality" in workbook.sheet_names

    ranking = pd.read_excel(output, sheet_name="GRG Ranking")
    assert ranking.loc[0, "Rank"] == 1
    assert ranking.loc[1, "Rank"] == 1

    quality = pd.read_excel(output, sheet_name="Data Quality")
    original_rows = quality.loc[
        quality["Data Quality Item"] == "Original rows", "Value"
    ].iloc[0]
    retained_rows = quality.loc[
        quality["Data Quality Item"] == "Retained rows", "Value"
    ].iloc[0]
    assert original_rows == 3
    assert retained_rows == 3
