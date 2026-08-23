# -*- coding: utf-8 -*-
# utils/plot_styler.py
"""
GRA-MicroAnalyzer — Publication-Quality Plot Styler
====================================================
All Matplotlib figure construction is centralised here.  Figures are
built to SCI-paper standards:

- Font:  Times New Roman (serif), fallback to DejaVu Serif.
- DPI:   300 for raster previews; vector formats (SVG/PDF) are resolution-
         independent.
- Spines: Top and right spines removed on all axes.
- Layout: tight_layout() applied before export.
- Colour: High-contrast palettes drawn from established scientific colour
          conventions (blue gradient for bars, RdYlGn diverging for
          heatmaps).

Public Functions
----------------
apply_sci_style()           — Apply the global rcParams style context.
build_grg_bar_chart()       — Horizontal sorted bar chart of GRG values.
build_coefficient_heatmap() — Annotated ξ(k) coefficient matrix.
export_figure()             — Save a Figure to SVG, PDF, or PNG.
plot_network_diagram()      — Topology network showing GRG coupling strengths.
plot_radar_chart()          — Radar / spider chart comparing normalised sample profiles.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal, Optional

# networkx is imported lazily inside plot_network_diagram() so that the
# rest of the module (bar chart, heatmap, radar chart) remains available
# even when networkx is not installed.  Users who never select the Network
# Diagram plot type will not encounter any import error at startup.

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.figure import Figure

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

ExportFormat = Literal["svg", "pdf", "png"]

# ---------------------------------------------------------------------------
# Colour constants
# ---------------------------------------------------------------------------

_BLUE_DARK: str = "#2171B5"
_BLUE_LIGHT: str = "#C6DBEF"
_ORANGE: str = "#D94801"
_GREY_TEXT: str = "#333333"
_SPINE_COLOUR: str = "#AAAAAA"

# ---------------------------------------------------------------------------
# Global style configuration
# ---------------------------------------------------------------------------

_SCI_RC_PARAMS: dict[str, object] = {
    "font.family": "serif",
    "font.serif": ["Times New Roman", "DejaVu Serif", "Liberation Serif"],
    "font.size": 10,
    "axes.titlesize": 11,
    "axes.labelsize": 10,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 9,
    "figure.dpi": 100,
    "savefig.dpi": 300,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.edgecolor": _SPINE_COLOUR,
    "axes.linewidth": 0.8,
    "xtick.direction": "out",
    "ytick.direction": "out",
    "xtick.major.size": 3.5,
    "ytick.major.size": 3.5,
    "xtick.color": _SPINE_COLOUR,
    "ytick.color": _SPINE_COLOUR,
    "text.color": _GREY_TEXT,
    "axes.labelcolor": _GREY_TEXT,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
}


def apply_sci_style() -> None:
    """
    Apply the publication-quality rcParams to the current Matplotlib session.

    Call this once at application startup (in ``main.py``) before any
    figures are created.  It sets a global style; individual functions
    may override specific parameters via ``ax.set_*`` calls.
    """
    matplotlib.rcParams.update(_SCI_RC_PARAMS)
    logger.debug("SCI rcParams applied to Matplotlib session.")


# ---------------------------------------------------------------------------
# Public — Bar Chart
# ---------------------------------------------------------------------------


def build_grg_bar_chart(
    grg_series: pd.Series,
    title: str = "Grey Relational Grade (GRG) — Factor Ranking",
    threshold_line: Optional[float] = None,
    figure_size: tuple[float, float] = (7.0, 4.5),
) -> Figure:
    """
    Build a horizontal bar chart of GRG values, sorted descending.

    Parameters
    ----------
    grg_series:
        Pandas Series with factor names as index and GRG floats as values.
    title:
        Figure title string.
    threshold_line:
        Optional vertical dashed orange line at this GRG value.
    figure_size:
        ``(width_inches, height_inches)``.

    Returns
    -------
    matplotlib.figure.Figure
    """
    sorted_series = grg_series.sort_values(ascending=True)
    n_factors = len(sorted_series)
    colours = _build_gradient_colours(n_factors)

    fig = Figure(figsize=figure_size, dpi=100)
    ax = fig.add_subplot(111)
    fig.subplots_adjust(left=0.22, right=0.96, top=0.93, bottom=0.10)

    bars = ax.barh(
        y=range(n_factors),
        width=sorted_series.values,
        color=colours,
        edgecolor="white",
        linewidth=0.5,
        height=0.65,
    )

    _annotate_bars(ax, bars, sorted_series.values)

    ax.set_yticks(range(n_factors))
    ax.set_yticklabels(
        [_format_column_label(name) for name in sorted_series.index],
        fontsize=9,
    )
    ax.set_xlabel("Grey Relational Grade (GRG)", labelpad=8)
    ax.set_title(title, pad=12, fontweight="bold")
    ax.set_xlim(0.0, min(1.05, sorted_series.max() * 1.15))
    ax.xaxis.set_major_formatter(mticker.FormatStrFormatter("%.2f"))

    if threshold_line is not None:
        _draw_threshold_line(ax, threshold_line)

    _polish_axes(ax)

    logger.debug("GRG bar chart built with %d factors.", n_factors)
    return fig


# ---------------------------------------------------------------------------
# Public — Coefficient Heatmap
# ---------------------------------------------------------------------------

_LABEL_MAX_CHARS: int = 12
_ANNOT_FONT_MIN: float = 6.5
_ANNOT_FONT_BASE: float = 9.0


def build_coefficient_heatmap(
    coefficient_df: pd.DataFrame,
    title: str = "Grey Relational Coefficient Matrix ξ(k)",
    figure_size: Optional[tuple[float, float]] = None,
) -> Figure:
    """
    Build an annotated heatmap of the ξ(k) relational coefficient matrix.

    Parameters
    ----------
    coefficient_df:
        DataFrame of shape ``(n_samples, n_comparative)`` with ξ(k) values.
    title:
        Figure title string.
    figure_size:
        Override auto-computed size.

    Returns
    -------
    matplotlib.figure.Figure
    """
    data = coefficient_df.values
    n_samples, n_factors = data.shape

    if figure_size is None:
        auto_width = max(9.0, 7.0 + n_factors * 0.9)
        auto_height = max(4.0, 2.8 + n_samples * 0.45)
        computed_size: tuple[float, float] = (auto_width, auto_height)
    else:
        computed_size = figure_size

    fig = Figure(figsize=computed_size, dpi=100)
    ax = fig.add_subplot(111)
    fig.subplots_adjust(left=0.12, right=0.88, top=0.92, bottom=0.18)

    img = ax.imshow(
        data,
        cmap="Blues",
        aspect="auto",
        vmin=0.0,
        vmax=1.0,
    )

    cbar = fig.colorbar(img, ax=ax, fraction=0.035, pad=0.03)
    cbar.set_label("ξ(k) Relational Coefficient", labelpad=10, rotation=270, va="bottom")
    cbar.ax.tick_params(labelsize=8)

    annot_fmt = ".2f" if n_factors > 8 else ".3f"
    annot_fontsize = max(_ANNOT_FONT_MIN, _ANNOT_FONT_BASE - n_factors * 0.22)
    _annotate_heatmap_cells(ax, data, fmt=annot_fmt, fontsize=annot_fontsize)

    x_rotation = 50 if n_factors > 6 else 35
    raw_labels = [_format_column_label(col) for col in coefficient_df.columns]
    display_labels = [
        (lbl if len(lbl) <= _LABEL_MAX_CHARS else lbl[:_LABEL_MAX_CHARS - 1] + "...")
        for lbl in raw_labels
    ]

    ax.set_xticks(range(n_factors))
    x_tick_labels = ax.set_xticklabels(
        display_labels,
        rotation=x_rotation,
        ha="right",
        rotation_mode="anchor",
        fontsize=max(7.0, 9.5 - n_factors * 0.18),
    )
    for tick_lbl, full_name in zip(x_tick_labels, raw_labels):
        tick_lbl.set_gid(full_name)

    ax.set_yticks(range(n_samples))
    ax.set_yticklabels(
        coefficient_df.index.tolist(),
        fontsize=max(7.5, 9.5 - n_samples * 0.18),
    )
    ax.set_xlabel("Comparative Factor", labelpad=10)
    ax.set_ylabel("Sample ID", labelpad=10)
    ax.set_title(title, pad=14, fontweight="bold")

    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_color(_SPINE_COLOUR)
        spine.set_linewidth(0.6)

    logger.debug(
        "Coefficient heatmap built — shape (%d × %d).",
        n_samples, n_factors,
    )
    return fig


# ---------------------------------------------------------------------------
# Public — Network Diagram
# ---------------------------------------------------------------------------

_NETWORK_CENTER_COLOR: str = "#D94801"
_NETWORK_PEER_COLOR: str = "#AEC6E8"
_NETWORK_CENTER_SIZE: int = 1_800
_NETWORK_PEER_SIZE: int = 900
_NETWORK_LW_MIN: float = 0.8
_NETWORK_LW_MAX: float = 6.0


def plot_network_diagram(
    target_name: str,
    grg_scores: dict[str, float],
    title: str = "Topology Network — GRG Coupling Strength",
    colormap_name: str = "Blues",
    figure_size: tuple[float, float] = (7.5, 6.0),
) -> Figure:
    """
    Build a topology network diagram with GRG-weighted edges.

    networkx is imported lazily here — the module loads fine without it.

    Parameters
    ----------
    target_name:
        Centre node label (reference sequence name).
    grg_scores:
        ``{factor_name: grg_value}`` for all comparative factors.
    title:
        Figure title.
    colormap_name:
        Matplotlib colormap for edge colour encoding.
    figure_size:
        ``(width_inches, height_inches)``.

    Returns
    -------
    matplotlib.figure.Figure

    Raises
    ------
    ImportError
        If networkx is not installed.
    ValueError
        If grg_scores is empty.
    """
    # Lazy import — only required for this function.
    try:
        import networkx as nx  # type: ignore[import-untyped]  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError(
            "networkx is required for the Network Diagram feature.\n"
            "Install it via:  pip install networkx>=3.0"
        ) from exc

    if not grg_scores:
        raise ValueError(
            "plot_network_diagram requires at least one GRG score entry."
        )

    factor_names: list[str] = list(grg_scores.keys())
    grg_values: np.ndarray = np.clip(
        np.array([grg_scores[f] for f in factor_names], dtype=float), 0.0, 1.0
    )

    G: nx.Graph = nx.Graph()
    G.add_node(target_name)
    for factor, grg in zip(factor_names, grg_values):
        G.add_node(factor)
        G.add_edge(target_name, factor, grg=float(grg))

    init_pos: dict[str, tuple[float, float]] = {target_name: (0.0, 0.0)}
    n_factors = len(factor_names)
    for i, f in enumerate(factor_names):
        angle = 2.0 * np.pi * i / max(n_factors, 1)
        init_pos[f] = (np.cos(angle), np.sin(angle))

    if n_factors >= 2:
        pos: dict[str, tuple[float, float]] = nx.spring_layout(
            G,
            pos=init_pos,
            fixed=[target_name],
            k=1.8 / np.sqrt(n_factors),
            iterations=80,
            seed=42,
        )
    else:
        pos = init_pos

    cmap = matplotlib.colormaps.get_cmap(colormap_name)
    norm = matplotlib.colors.Normalize(vmin=0.0, vmax=1.0)

    grg_min, grg_max = grg_values.min(), grg_values.max()
    lw_range = _NETWORK_LW_MAX - _NETWORK_LW_MIN

    if np.isclose(grg_min, grg_max):
        edge_linewidths: list[float] = [_NETWORK_LW_MIN + lw_range * 0.5] * n_factors
    else:
        edge_linewidths = [
            _NETWORK_LW_MIN + lw_range * (g - grg_min) / (grg_max - grg_min)
            for g in grg_values
        ]

    edge_colours: list[tuple[float, float, float, float]] = [
        cmap(norm(g)) for g in grg_values
    ]

    peripheral_nodes: list[str] = factor_names
    center_node: list[str] = [target_name]
    edge_list: list[tuple[str, str]] = [(target_name, f) for f in factor_names]

    fig = Figure(figsize=figure_size, dpi=100)
    ax = fig.add_subplot(111)
    fig.subplots_adjust(left=0.05, right=0.88, top=0.92, bottom=0.05)

    nx.draw_networkx_nodes(
        G, pos, nodelist=peripheral_nodes,
        node_color=_NETWORK_PEER_COLOR, node_size=_NETWORK_PEER_SIZE,
        ax=ax, linewidths=0.8, edgecolors="#5A7FA8",
    )
    nx.draw_networkx_nodes(
        G, pos, nodelist=center_node,
        node_color=_NETWORK_CENTER_COLOR, node_size=_NETWORK_CENTER_SIZE,
        ax=ax, linewidths=1.2, edgecolors="#8B2500",
    )

    for (u, v), lw, colour in zip(edge_list, edge_linewidths, edge_colours):
        nx.draw_networkx_edges(
            G, pos, edgelist=[(u, v)],
            width=lw, edge_color=[colour], alpha=0.85, ax=ax, style="solid",
        )

    nx.draw_networkx_labels(
        G, pos,
        labels={target_name: _format_column_label(target_name)},
        font_size=8, font_color="white", font_weight="bold", ax=ax,
    )
    label_pos: dict[str, tuple[float, float]] = {
        f: (pos[f][0], pos[f][1] + 0.07) for f in peripheral_nodes
    }
    nx.draw_networkx_labels(
        G, label_pos,
        labels={f: _format_column_label(f) for f in peripheral_nodes},
        font_size=7.5, font_color=_GREY_TEXT, ax=ax,
    )

    for (u, v), grg_val in zip(edge_list, grg_values):
        mid_x = (pos[u][0] + pos[v][0]) / 2.0
        mid_y = (pos[u][1] + pos[v][1]) / 2.0
        ax.text(
            mid_x, mid_y, f"{grg_val:.3f}",
            fontsize=6.5, ha="center", va="center", color=_GREY_TEXT,
            bbox=dict(boxstyle="round,pad=0.15", facecolor="white",
                      edgecolor="none", alpha=0.75),
        )

    sm = matplotlib.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, fraction=0.030, pad=0.02)
    cbar.set_label(
        "Grey Relational Grade (GRG)",
        labelpad=10, rotation=270, va="bottom", fontsize=9,
    )
    cbar.ax.tick_params(labelsize=8)

    ax.set_title(title, pad=14, fontweight="bold", fontsize=11)
    ax.axis("off")

    logger.debug("Network diagram built — %d factors, centre '%s'.", n_factors, target_name)
    return fig


# ---------------------------------------------------------------------------
# Public — Radar Chart
# ---------------------------------------------------------------------------

_RADAR_MIN_CATEGORIES: int = 3
_RADAR_FILL_ALPHA: float = 0.25
_RADAR_YLIM_MAX: float = 1.05
_RADAR_GRID_LEVELS: int = 5


def plot_radar_chart(
    categories: list[str],
    data_dict: dict[str, list[float]],
    title: str = "Optimization Envelope - Normalised Sample Profiles",
    figure_size: tuple[float, float] = (8.0, 7.5),
) -> Figure:
    """
    Build a publication-quality radar (spider) chart.

    Each sample in *data_dict* is drawn as a closed polygon on polar axes.
    Values must lie in [0, 1] (GRA normalisation range).

    Closure
    -------
    Both angles and values are explicitly closed::

        angles_closed = np.append(angles, angles[0] + 2π)
        values_closed = np.append(values, values[0])

    The ``+ 2π`` ensures the closing arc travels the correct short forward
    path rather than wrapping backwards across the chart.

    Parameters
    ----------
    categories:
        Ordered list of factor names (spoke labels).
    data_dict:
        ``{sample_id: [v1, v2, ..., vN]}`` with values in [0, 1].
    title:
        Figure title.
    figure_size:
        ``(width_inches, height_inches)``.

    Returns
    -------
    matplotlib.figure.Figure
    """
    n_cats = len(categories)

    # ------------------------------------------------------------------ #
    # Edge case: too few categories                                        #
    # ------------------------------------------------------------------ #
    if n_cats < _RADAR_MIN_CATEGORIES:
        fig_err = Figure(figsize=figure_size, dpi=100)
        ax_err = fig_err.add_subplot(111)          # plain axes — predictable behaviour
        ax_err.set_title(title, pad=18, fontweight="bold", fontsize=11)
        ax_err.text(
            0.5, 0.5,
            f"At least {_RADAR_MIN_CATEGORIES} comparative factors are\n"
            "required for a Radar Chart.\n"
            f"Current selection: {n_cats} factor(s).",
            transform=ax_err.transAxes,
            ha="center", va="center",
            fontsize=10, color=_GREY_TEXT,
            bbox=dict(boxstyle="round,pad=0.5", facecolor="#FFF3CD",
                      edgecolor="#FFC107", alpha=0.9),
        )
        ax_err.axis("off")
        logger.warning(
            "plot_radar_chart: %d categories supplied (min %d); returning placeholder.",
            n_cats, _RADAR_MIN_CATEGORIES,
        )
        return fig_err

    # ------------------------------------------------------------------ #
    # Figure + polar axes                                                  #
    # Use Figure() directly (not plt.subplots) to avoid pyplot's global   #
    # figure manager interfering with PySide6's FigureCanvasQTAgg embed.  #
    # ------------------------------------------------------------------ #
    fig = Figure(figsize=figure_size, dpi=100)
    # Use add_axes with explicit rect [left, bottom, width, height] in figure
    # fraction coordinates. This is the ONLY reliable way to centre a polar
    # axes — subplots_adjust and tight_layout both have known bugs with polar
    # projections in matplotlib and produce off-centre / clipped circles.
    # Margins: 0.15 left/right for spoke labels, 0.18 bottom for legend, 0.10 top for title.
    ax = fig.add_axes([0.15, 0.18, 0.70, 0.72], polar=True)
    ax.set_clip_on(False)

    # ------------------------------------------------------------------ #
    # Spoke angles                                                         #
    # First spoke at 12 o'clock: apply rotation = -π/2                   #
    # ------------------------------------------------------------------ #
    angles_raw: np.ndarray = np.linspace(0.0, 2.0 * np.pi, n_cats, endpoint=False)
    _ROTATION: float = -np.pi / 2.0
    angles: np.ndarray = angles_raw + _ROTATION

    # Closed array for ax.plot() — append first angle + 2π to ensure the
    # closing segment travels the forward (short) arc, not backwards.
    angles_closed: np.ndarray = np.append(
        angles, angles_raw[0] + _ROTATION + 2.0 * np.pi
    )

    # ------------------------------------------------------------------ #
    # Colour palette — tab10, one colour per sample                       #
    # ------------------------------------------------------------------ #
    sample_ids: list[str] = list(data_dict.keys())
    n_samples = len(sample_ids)
    palette = matplotlib.colormaps.get_cmap("tab10")
    colours: list[tuple[float, float, float, float]] = [
        palette(i % 10) for i in range(n_samples)
    ]

    # ------------------------------------------------------------------ #
    # Draw each sample polygon                                            #
    # ------------------------------------------------------------------ #
    for (sample_id, raw_values), colour in zip(data_dict.items(), colours):
        values_arr: np.ndarray = np.array(
            _pad_or_truncate(list(raw_values), n_cats), dtype=float
        )
        values_arr = np.clip(values_arr, 0.0, 1.0)
        values_closed: np.ndarray = np.append(values_arr, values_arr[0])

        ax.fill(angles_closed, values_closed, color=colour, alpha=_RADAR_FILL_ALPHA)
        ax.plot(
            angles_closed, values_closed,
            color=colour, linewidth=1.6, linestyle="-", label=sample_id,
        )
        ax.scatter(
            angles, values_arr,
            color=colour, s=28, zorder=5, linewidths=0.8, edgecolors="white",
        )

    # ------------------------------------------------------------------ #
    # Spoke labels                                                         #
    # ------------------------------------------------------------------ #
    ax.set_xticks(angles)
    display_labels = [
        (
            _format_column_label(cat)
            if len(cat) <= _LABEL_MAX_CHARS
            else _format_column_label(cat[:_LABEL_MAX_CHARS - 1]) + "..."
        )
        for cat in categories
    ]
    ax.set_xticklabels(display_labels, fontsize=8.5, color=_GREY_TEXT)
    # Prevent individual tick label artists from being clipped
    for lbl in ax.get_xticklabels():
        lbl.set_clip_on(False)

    # ------------------------------------------------------------------ #
    # Radial axis                                                          #
    # ------------------------------------------------------------------ #
    ax.set_ylim(0.0, _RADAR_YLIM_MAX)

    grid_ticks = np.linspace(0.0, 1.0, _RADAR_GRID_LEVELS + 1)[1:]
    ax.set_yticks(grid_ticks)
    ax.set_yticklabels(
        [f"{v:.1f}" for v in grid_ticks],
        fontsize=7, color=_SPINE_COLOUR,
    )
    ax.yaxis.set_tick_params(labelsize=7)

    # Place radial labels midway between spoke 1 and spoke 2 to avoid overlap.
    # Matplotlib set_rlabel_position() uses degrees, 0° = right, CCW positive.
    # Our rotation puts spoke 1 at top = 90° in Matplotlib coords.
    # Offset by half a spoke gap to land between spoke 1 and spoke N.
    _half_gap_deg: float = (360.0 / n_cats) / 2.0
    ax.set_rlabel_position(90.0 + _half_gap_deg)

    ax.grid(visible=True, color=_SPINE_COLOUR, linestyle=":", linewidth=0.6, alpha=0.7)
    ax.spines["polar"].set_visible(False)

    # ------------------------------------------------------------------ #
    # Legend and title                                                     #
    # ------------------------------------------------------------------ #
    if n_samples > 1:
        ax.legend(
            loc="lower center",
            bbox_to_anchor=(0.5, -0.22),
            bbox_transform=ax.transAxes,
            frameon=True,
            framealpha=0.85,
            fontsize=8,
            title="Sample ID",
            title_fontsize=8,
            ncol=min(n_samples, 4),
        )

    ax.set_title(title, pad=18, fontweight="bold", fontsize=11)

    logger.debug("Radar chart built — %d categories, %d samples.", n_cats, n_samples)
    return fig


# ---------------------------------------------------------------------------
# Public — Export
# ---------------------------------------------------------------------------


def export_figure(
    figure: Figure,
    output_path: str | Path,
    fmt: ExportFormat = "svg",
    transparent: bool = False,
) -> Path:
    """
    Save a Matplotlib Figure to disk.

    Parameters
    ----------
    figure:
        The Figure to save.
    output_path:
        Destination file path (extension overridden by *fmt*).
    fmt:
        One of ``'svg'``, ``'pdf'``, or ``'png'``.
    transparent:
        Transparent background (useful for PNG).

    Returns
    -------
    Path
        Resolved absolute path of the saved file.
    """
    path = Path(output_path).with_suffix(f".{fmt}")
    path.parent.mkdir(parents=True, exist_ok=True)

    save_kwargs: dict[str, object] = {
        "format": fmt,
        "dpi": 300,
        "transparent": transparent,
        "bbox_inches": "tight",
        "metadata": _build_figure_metadata(fmt),
    }

    figure.savefig(path, **save_kwargs)
    logger.info("Figure exported to '%s' (%s).", path, fmt.upper())
    return path.resolve()


# ---------------------------------------------------------------------------
# Private — Drawing Helpers
# ---------------------------------------------------------------------------


def _build_gradient_colours(n: int) -> list[str]:
    cmap = matplotlib.colormaps.get_cmap("Blues")
    sample_points = np.linspace(0.85, 0.30, n)
    return [matplotlib.colors.to_hex(cmap(t)) for t in sample_points]


def _annotate_bars(
    ax: Axes, bars: matplotlib.container.BarContainer, values: np.ndarray
) -> None:
    for bar, value in zip(bars, values):
        x_pos = bar.get_width() + 0.005
        y_pos = bar.get_y() + bar.get_height() / 2.0
        ax.text(
            x_pos, y_pos, f"{value:.4f}",
            va="center", ha="left", fontsize=8, color=_GREY_TEXT,
        )


def _annotate_heatmap_cells(
    ax: Axes,
    data: np.ndarray,
    fmt: str = ".3f",
    fontsize: float = 8.0,
) -> None:
    n_rows, n_cols = data.shape
    _DARK_THRESHOLD: float = 0.55
    for row in range(n_rows):
        for col in range(n_cols):
            value = data[row, col]
            is_dark = value >= _DARK_THRESHOLD
            text_colour = "white" if is_dark else _GREY_TEXT
            ax.text(
                col, row, format(value, fmt),
                ha="center", va="center", fontsize=fontsize,
                color=text_colour,
                fontweight="bold" if is_dark else "normal",
            )


def _draw_threshold_line(ax: Axes, threshold: float) -> None:
    ax.axvline(
        x=threshold, color=_ORANGE, linestyle="--", linewidth=1.2,
        alpha=0.85, label=f"Threshold = {threshold:.2f}", zorder=3,
    )
    ax.legend(frameon=False, fontsize=8, loc="lower right")


def _polish_axes(ax: Axes) -> None:
    ax.spines["left"].set_color(_SPINE_COLOUR)
    ax.spines["bottom"].set_color(_SPINE_COLOUR)
    ax.tick_params(axis="both", which="both", length=3, color=_SPINE_COLOUR)
    ax.grid(axis="x", linestyle=":", linewidth=0.5, alpha=0.6, color=_SPINE_COLOUR)


# ---------------------------------------------------------------------------
# Private — Miscellaneous
# ---------------------------------------------------------------------------


def _pad_or_truncate(values: list[float], target_length: int) -> list[float]:
    if len(values) >= target_length:
        return values[:target_length]
    return values + [0.0] * (target_length - len(values))


def _format_column_label(name: str) -> str:
    return name.replace("_", " ").strip()


def _build_figure_metadata(fmt: ExportFormat) -> dict[str, str]:
    base_meta: dict[str, str] = {
        "Title": "GRA-MicroAnalyzer Output",
        "Author": "GRA-MicroAnalyzer",
        "Subject": "Grey Relational Analysis — Material Science",
    }
    if fmt == "svg":
        return base_meta
    if fmt == "pdf":
        return {**base_meta, "Creator": "Matplotlib via GRA-MicroAnalyzer"}
    return {}
