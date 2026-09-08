# -*- coding: utf-8 -*-
"""
Publication-quality plotting utilities for GRA-MicroAnalyzer.

The plotting layer is deliberately separated from the GRA computation layer.
It provides a consistent typography, restrained visual hierarchy, deterministic
layouts, and export settings suitable for manuscript preparation.
"""

from __future__ import annotations

import logging
import textwrap
from pathlib import Path
from typing import Literal, Optional

import matplotlib
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.figure import Figure

logger = logging.getLogger(__name__)

ExportFormat = Literal["svg", "pdf", "png"]

# Generic manuscript-friendly sizes. 7.09 in is approximately 180 mm.
_DOUBLE_COLUMN_WIDTH_IN = 7.09
_SINGLE_COLUMN_WIDTH_IN = 3.35

_PRIMARY = "#2F5D8A"
_PRIMARY_LIGHT = "#BFD0E0"
_ACCENT = "#9A4F35"
_TEXT = "#222222"
_MUTED = "#6E7781"
_SPINE = "#8A8A8A"
_GRID = "#D9D9D9"
_CENTER = "#3D4650"

_HEATMAP_ANNOTATION_CELL_LIMIT = 200
_NETWORK_EDGE_LABEL_LIMIT = 12

_SCI_RC_PARAMS: dict[str, object] = {
    "font.family": "serif",
    "font.serif": [
        "Times New Roman",
        "Times",
        "STIXGeneral",
        "DejaVu Serif",
        "Liberation Serif",
    ],
    "mathtext.fontset": "stix",
    "font.size": 8.5,
    "axes.titlesize": 9.5,
    "axes.titleweight": "normal",
    "axes.labelsize": 9.0,
    "xtick.labelsize": 8.0,
    "ytick.labelsize": 8.0,
    "legend.fontsize": 8.0,
    "legend.title_fontsize": 8.0,
    "figure.dpi": 110,
    "savefig.dpi": 600,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.03,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.edgecolor": _SPINE,
    "axes.linewidth": 0.8,
    "lines.linewidth": 1.2,
    "xtick.direction": "out",
    "ytick.direction": "out",
    "xtick.major.size": 3.0,
    "ytick.major.size": 3.0,
    "xtick.major.width": 0.7,
    "ytick.major.width": 0.7,
    "xtick.color": _SPINE,
    "ytick.color": _SPINE,
    "text.color": _TEXT,
    "axes.labelcolor": _TEXT,
    "axes.titlecolor": _TEXT,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
    "svg.fonttype": "none",
}


def apply_sci_style() -> None:
    """Apply the global manuscript-oriented Matplotlib style."""
    matplotlib.rcParams.update(_SCI_RC_PARAMS)
    logger.debug("Publication rcParams applied.")


def build_grg_bar_chart(
    grg_series: pd.Series,
    title: str = "Grey relational grade ranking",
    threshold_line: Optional[float] = None,
    figure_size: Optional[tuple[float, float]] = None,
) -> Figure:
    """Build a restrained horizontal ranking chart on the fixed GRG scale [0, 1]."""
    if grg_series.empty:
        raise ValueError("grg_series must contain at least one factor.")

    sorted_series = grg_series.sort_values(ascending=True, kind="mergesort")
    n_factors = len(sorted_series)
    if figure_size is None:
        height = max(2.8, min(8.0, 1.55 + 0.34 * n_factors))
        figure_size = (_DOUBLE_COLUMN_WIDTH_IN, height)

    fig = Figure(figsize=figure_size, dpi=110)
    ax = fig.add_subplot(111)
    fig.subplots_adjust(left=0.30, right=0.97, top=0.90, bottom=0.14)

    colours = [_PRIMARY_LIGHT] * n_factors
    colours[-1] = _PRIMARY
    bars = ax.barh(
        range(n_factors),
        sorted_series.to_numpy(dtype=float),
        color=colours,
        edgecolor="white",
        linewidth=0.4,
        height=0.62,
    )

    _annotate_bars(ax, bars, sorted_series.to_numpy(dtype=float))
    ax.set_yticks(range(n_factors))
    ax.set_yticklabels([_wrap_label(name, 24) for name in sorted_series.index])
    ax.set_xlabel("Grey relational grade (GRG)", labelpad=6)
    ax.set_title(title, pad=8)
    ax.set_xlim(0.0, 1.02)
    ax.xaxis.set_major_locator(mticker.MultipleLocator(0.2))
    ax.xaxis.set_major_formatter(mticker.FormatStrFormatter("%.1f"))

    if threshold_line is not None:
        _draw_threshold_line(ax, threshold_line)

    _polish_cartesian_axes(ax, grid_axis="x")
    return fig


def build_coefficient_heatmap(
    coefficient_df: pd.DataFrame,
    title: str = "Grey relational coefficient matrix",
    figure_size: Optional[tuple[float, float]] = None,
) -> Figure:
    """Build a coefficient heatmap with automatic annotation suppression."""
    if coefficient_df.empty:
        raise ValueError("coefficient_df must not be empty.")

    data = coefficient_df.to_numpy(dtype=float)
    n_samples, n_factors = data.shape
    if not np.isfinite(data).all():
        raise ValueError("coefficient_df contains non-finite values.")

    if figure_size is None:
        width = max(_DOUBLE_COLUMN_WIDTH_IN, min(12.0, 4.6 + 0.55 * n_factors))
        height = max(3.2, min(12.0, 2.2 + 0.28 * n_samples))
        figure_size = (width, height)

    fig = Figure(figsize=figure_size, dpi=110)
    ax = fig.add_subplot(111)
    fig.subplots_adjust(left=0.13, right=0.90, top=0.90, bottom=0.22)

    image = ax.imshow(
        data,
        cmap="cividis",
        aspect="auto",
        interpolation="nearest",
        vmin=0.0,
        vmax=1.0,
    )
    cbar = fig.colorbar(image, ax=ax, fraction=0.035, pad=0.025)
    cbar.set_label(r"Grey relational coefficient, $\xi(k)$", rotation=270, labelpad=14)
    cbar.ax.tick_params(labelsize=7.5, width=0.6, length=2.5)

    x_labels = [_wrap_label(col, 18) for col in coefficient_df.columns]
    raw_x_labels = [_format_column_label(col) for col in coefficient_df.columns]
    rotation = 45 if n_factors > 5 else 25
    ax.set_xticks(range(n_factors))
    tick_artists = ax.set_xticklabels(
        x_labels,
        rotation=rotation,
        ha="right",
        rotation_mode="anchor",
    )
    for artist, raw_label in zip(tick_artists, raw_x_labels):
        artist.set_gid(raw_label)

    ax.set_yticks(range(n_samples))
    ax.set_yticklabels([str(value) for value in coefficient_df.index])
    ax.set_xlabel("Comparative factor", labelpad=6)
    ax.set_ylabel("Sample ID", labelpad=6)
    ax.set_title(title, pad=8)

    if n_samples * n_factors <= _HEATMAP_ANNOTATION_CELL_LIMIT:
        annotation_size = max(6.0, 8.0 - 0.10 * max(n_samples, n_factors))
        _annotate_heatmap_cells(ax, data, fontsize=annotation_size)

    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_color(_SPINE)
        spine.set_linewidth(0.6)
    ax.tick_params(which="both", width=0.6, length=2.5)
    return fig


def plot_network_diagram(
    target_name: str,
    grg_scores: dict[str, float],
    title: str = "GRG association network",
    colormap_name: str = "cividis",
    figure_size: tuple[float, float] = (_DOUBLE_COLUMN_WIDTH_IN, 5.2),
) -> Figure:
    """
    Build a deterministic association network.

    Edge width is mapped to the *absolute* GRG value, not re-scaled against
    the current minimum and maximum. This avoids visually exaggerating small
    differences between factors.
    """
    try:
        import networkx as nx  # type: ignore[import-untyped]  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError("networkx is required for the Network Diagram feature.") from exc

    if not grg_scores:
        raise ValueError("grg_scores must contain at least one factor.")

    ordered = sorted(grg_scores.items(), key=lambda item: (-item[1], item[0]))
    factor_names = [name for name, _ in ordered]
    grg_values = np.clip(np.array([value for _, value in ordered], dtype=float), 0.0, 1.0)
    if not np.isfinite(grg_values).all():
        raise ValueError("grg_scores contain non-finite values.")

    n_factors = len(factor_names)
    graph = nx.Graph()
    graph.add_node(target_name)
    for name, value in zip(factor_names, grg_values):
        graph.add_edge(target_name, name, grg=float(value))

    positions: dict[str, tuple[float, float]] = {target_name: (0.0, 0.0)}
    for idx, name in enumerate(factor_names):
        angle = 2.0 * np.pi * idx / max(n_factors, 1) - np.pi / 2.0
        positions[name] = (float(np.cos(angle)), float(np.sin(angle)))

    fig = Figure(figsize=figure_size, dpi=110)
    ax = fig.add_subplot(111)
    fig.subplots_adjust(left=0.05, right=0.88, top=0.90, bottom=0.06)

    cmap = matplotlib.colormaps.get_cmap(colormap_name)
    norm = matplotlib.colors.Normalize(vmin=0.0, vmax=1.0)

    nx.draw_networkx_nodes(
        graph,
        positions,
        nodelist=factor_names,
        node_color=grg_values,
        cmap=cmap,
        vmin=0.0,
        vmax=1.0,
        node_size=620,
        linewidths=0.6,
        edgecolors="white",
        ax=ax,
    )
    nx.draw_networkx_nodes(
        graph,
        positions,
        nodelist=[target_name],
        node_color=_CENTER,
        node_size=1180,
        linewidths=0.8,
        edgecolors="white",
        ax=ax,
    )

    for name, value in zip(factor_names, grg_values):
        nx.draw_networkx_edges(
            graph,
            positions,
            edgelist=[(target_name, name)],
            width=_network_linewidth(float(value)),
            edge_color=[cmap(norm(value))],
            alpha=_network_alpha(float(value)),
            ax=ax,
        )

    nx.draw_networkx_labels(
        graph,
        positions,
        labels={target_name: _wrap_label(target_name, 14)},
        font_size=7.5,
        font_color="white",
        font_weight="bold",
        ax=ax,
    )

    label_positions: dict[str, tuple[float, float]] = {}
    for name in factor_names:
        x, y = positions[name]
        scale = 1.13
        label_positions[name] = (x * scale, y * scale)
    nx.draw_networkx_labels(
        graph,
        label_positions,
        labels={name: _wrap_label(name, 15) for name in factor_names},
        font_size=7.2,
        font_color=_TEXT,
        ax=ax,
    )

    if n_factors <= _NETWORK_EDGE_LABEL_LIMIT:
        for name, value in zip(factor_names, grg_values):
            x, y = positions[name]
            ax.text(
                x * 0.52,
                y * 0.52,
                f"{value:.3f}",
                fontsize=6.3,
                ha="center",
                va="center",
                color=_TEXT,
                bbox=dict(
                    boxstyle="round,pad=0.12",
                    facecolor="white",
                    edgecolor="none",
                    alpha=0.80,
                ),
            )

    scalar = matplotlib.cm.ScalarMappable(cmap=cmap, norm=norm)
    scalar.set_array([])
    cbar = fig.colorbar(scalar, ax=ax, fraction=0.030, pad=0.015)
    cbar.set_label("Grey relational grade (GRG)", rotation=270, labelpad=13)
    cbar.ax.tick_params(labelsize=7.5, width=0.6, length=2.5)

    ax.set_title(title, pad=8)
    ax.set_xlim(-1.35, 1.35)
    ax.set_ylim(-1.25, 1.25)
    ax.set_aspect("equal")
    ax.axis("off")
    return fig


def plot_radar_chart(
    categories: list[str],
    data_dict: dict[str, list[float]],
    title: str = "Normalised sample profiles",
    figure_size: tuple[float, float] = (_DOUBLE_COLUMN_WIDTH_IN, 5.5),
) -> Figure:
    """Build a manuscript-styled radar chart using the shared Matplotlib style."""
    n_categories = len(categories)
    if n_categories < 3:
        fig = Figure(figsize=figure_size, dpi=110)
        ax = fig.add_subplot(111)
        ax.text(
            0.5,
            0.5,
            f"At least 3 comparative factors are required (got {n_categories}).",
            ha="center",
            va="center",
            transform=ax.transAxes,
        )
        ax.axis("off")
        return fig

    angles = np.linspace(0.0, 2.0 * np.pi, n_categories, endpoint=False)
    angles_closed = np.append(angles, angles[0])

    fig = Figure(figsize=figure_size, dpi=110)
    ax = fig.add_subplot(111, polar=True)
    fig.subplots_adjust(left=0.13, right=0.87, top=0.88, bottom=0.18)
    ax.set_theta_offset(np.pi / 2.0)
    ax.set_theta_direction(-1)

    palette = matplotlib.colormaps.get_cmap("tab10")
    for idx, (sample_id, values) in enumerate(data_dict.items()):
        arr = np.asarray(_pad_or_truncate(values, n_categories), dtype=float)
        arr = np.clip(arr, 0.0, 1.0)
        values_closed = np.append(arr, arr[0])
        colour = palette(idx % 10)
        ax.plot(
            angles_closed,
            values_closed,
            linewidth=1.2,
            marker="o",
            markersize=2.8,
            label=str(sample_id),
            color=colour,
        )
        ax.fill(angles_closed, values_closed, color=colour, alpha=0.07)

    ax.set_xticks(angles)
    ax.set_xticklabels([_wrap_label(cat, 13) for cat in categories], fontsize=7.8)
    ax.set_ylim(0.0, 1.0)
    ticks = np.linspace(0.2, 1.0, 5)
    ax.set_yticks(ticks)
    ax.set_yticklabels([f"{value:.1f}" for value in ticks], fontsize=6.8, color=_MUTED)
    ax.set_rlabel_position(12)
    ax.grid(color=_GRID, linewidth=0.6, linestyle="-")
    ax.spines["polar"].set_color(_SPINE)
    ax.spines["polar"].set_linewidth(0.7)
    ax.set_title(title, pad=14)

    if len(data_dict) > 1:
        ax.legend(
            loc="upper center",
            bbox_to_anchor=(0.5, -0.10),
            ncol=min(4, len(data_dict)),
            frameon=False,
            title="Sample ID",
        )
    return fig


def export_figure(
    figure: Figure,
    output_path: str | Path,
    fmt: ExportFormat = "svg",
    transparent: bool = False,
) -> Path:
    """
    Export a figure using manuscript-oriented defaults.

    SVG/PDF remain vector formats. PNG is exported at 600 dpi so fine lines
    and text survive common journal production workflows.
    """
    if fmt not in {"svg", "pdf", "png"}:
        raise ValueError(f"Unsupported figure format: {fmt}")

    path = Path(output_path).with_suffix(f".{fmt}")
    path.parent.mkdir(parents=True, exist_ok=True)
    dpi = 600 if fmt == "png" else 300
    figure.savefig(
        path,
        format=fmt,
        dpi=dpi,
        transparent=transparent,
        bbox_inches="tight",
        pad_inches=0.03,
        facecolor="none" if transparent else "white",
        metadata=_build_figure_metadata(fmt),
    )
    logger.info("Figure exported to '%s' (%s, dpi=%d).", path, fmt.upper(), dpi)
    return path.resolve()


def _annotate_bars(ax: Axes, bars, values: np.ndarray) -> None:
    for bar, value in zip(bars, values):
        y = bar.get_y() + bar.get_height() / 2.0
        if value >= 0.90:
            ax.text(
                value - 0.012,
                y,
                f"{value:.3f}",
                ha="right",
                va="center",
                fontsize=7.2,
                color="white",
            )
        else:
            ax.text(
                value + 0.012,
                y,
                f"{value:.3f}",
                ha="left",
                va="center",
                fontsize=7.2,
                color=_TEXT,
            )


def _annotate_heatmap_cells(ax: Axes, data: np.ndarray, fontsize: float) -> None:
    for row in range(data.shape[0]):
        for col in range(data.shape[1]):
            value = float(data[row, col])
            colour = "white" if value < 0.35 or value > 0.82 else _TEXT
            ax.text(
                col,
                row,
                f"{value:.2f}",
                ha="center",
                va="center",
                fontsize=fontsize,
                color=colour,
            )


def _draw_threshold_line(ax: Axes, threshold: float) -> None:
    ax.axvline(
        threshold,
        color=_ACCENT,
        linestyle="--",
        linewidth=1.0,
        label=f"Threshold = {threshold:.2f}",
    )
    ax.legend(frameon=False, loc="lower right")


def _polish_cartesian_axes(ax: Axes, grid_axis: Literal["x", "y", "both"] = "both") -> None:
    ax.spines["left"].set_color(_SPINE)
    ax.spines["bottom"].set_color(_SPINE)
    ax.tick_params(axis="both", which="both", color=_SPINE)
    ax.grid(axis=grid_axis, color=_GRID, linewidth=0.55, linestyle="-", alpha=0.85)
    ax.set_axisbelow(True)


def _network_linewidth(grg: float) -> float:
    """Absolute GRG-to-linewidth mapping; intentionally not min-max re-scaled."""
    clipped = float(np.clip(grg, 0.0, 1.0))
    return 0.70 + 2.30 * clipped


def _network_alpha(grg: float) -> float:
    clipped = float(np.clip(grg, 0.0, 1.0))
    return 0.35 + 0.55 * clipped


def _pad_or_truncate(values: list[float], target_length: int) -> list[float]:
    values = list(values)
    if len(values) >= target_length:
        return values[:target_length]
    return values + [0.0] * (target_length - len(values))


def _format_column_label(name: str) -> str:
    return str(name).replace("_", " ").strip()


def _wrap_label(name: str, width: int) -> str:
    clean = _format_column_label(name)
    return textwrap.fill(clean, width=width, break_long_words=False, break_on_hyphens=False)


def _build_figure_metadata(fmt: ExportFormat) -> dict[str, str]:
    if fmt == "svg":
        return {
            "Title": "GRA-MicroAnalyzer figure",
            "Description": "Grey relational analysis figure for materials research",
            "Creator": "GRA-MicroAnalyzer",
        }
    if fmt == "pdf":
        return {
            "Title": "GRA-MicroAnalyzer figure",
            "Author": "GRA-MicroAnalyzer",
            "Subject": "Grey relational analysis for materials research",
            "Creator": "Matplotlib via GRA-MicroAnalyzer",
        }
    return {}
