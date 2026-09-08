"""Pure helpers that prepare GRA results for UI visualisations."""

from __future__ import annotations

from core.data_model import GRAResult


def limited_network_scores(
    result: GRAResult,
    max_factors: int,
) -> tuple[dict[str, float], bool]:
    """Return network scores, preserving stable GRG ordering when truncation is needed."""
    scores = result.grg_series.to_dict()
    if len(scores) <= max_factors:
        return scores, False

    limited = (
        result.grg_series.sort_values(ascending=False, kind="mergesort")
        .head(max_factors)
        .to_dict()
    )
    return limited, True


def radar_payload(
    result: GRAResult,
    comparative_columns: list[str],
    max_samples: int,
) -> tuple[list[str], dict[str, list[float]], bool]:
    """Prepare the exact factor/sample payload used by the radar chart."""
    norm_df = result.normalised_df
    available = [column for column in comparative_columns if column in norm_df.columns]
    sample_df = norm_df.head(max_samples)
    sample_ids = [str(index) for index in sample_df.index]
    data = {
        sample_id: sample_df.iloc[position][available].astype(float).tolist()
        for position, sample_id in enumerate(sample_ids)
    }
    return available, data, len(norm_df) > max_samples
