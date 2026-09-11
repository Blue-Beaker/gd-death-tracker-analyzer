"""GD Death Tracker 图表绘制模块

提供通过率/通过次数双轴图和最优路径交错条块图的绘制功能。
"""

import os
from typing import Any, Optional

from gd_analysis import OptimalPath, PassRates

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False


# ── 底层绘制函数 ──────────────────────────────────────────────

def _plot_pass_rate_axis(
    ax: "plt.Axes", pass_rates: PassRates, pass_counts: list[int], max_pos: int
) -> None:
    """在指定 Axes 上绘制通过率(左轴) + 通过次数(右轴)"""
    positions_rate = [x for x, _, _, r in pass_rates if r is not None]
    rates = [r for _, _, _, r in pass_rates if r is not None]
    x_counts = list(range(0, max_pos + 1))
    y_counts = [pass_counts[x] for x in x_counts]

    color_rate = "#2196F3"
    ax.plot(positions_rate, rates, color=color_rate, linewidth=1.5, zorder=3, label="Pass Rate")
    ax.fill_between(positions_rate, rates, alpha=0.08, color=color_rate)
    ax.axhline(0.5, color="#999", linestyle="--", linewidth=0.6, alpha=0.6)
    ax.set_ylabel("Pass Rate", fontsize=11, color=color_rate)
    ax.tick_params(axis="y", labelcolor=color_rate)
    ax.set_xlim(0, max_pos)
    ax.set_ylim(-0.05, 1.05)

    # 通过率最低点标注
    sorted_by_rate = sorted(
        [(x, p, f, r) for x, p, f, r in pass_rates if r is not None],
        key=lambda t: t[3],
    )
    for x, p, f, r in sorted_by_rate[:10]:
        ax.annotate(f"↓{f}", (x, r), textcoords="offset points",
                    xytext=(0, -14), fontsize=6.5, color="#e53935",
                    ha="center", va="top", alpha=0.8)

    # 右轴: 通过次数
    ax2 = ax.twinx()
    color_count = "#FF9800"
    ax2.plot(x_counts, y_counts, color=color_count, linewidth=1.5, zorder=3, label="Pass Count")
    ax2.fill_between(x_counts, y_counts, alpha=0.08, color=color_count)
    ax2.set_ylabel("Pass Count", fontsize=11, color=color_count)
    ax2.tick_params(axis="y", labelcolor=color_count)

    sorted_idx = sorted(range(1, max_pos), key=lambda i: pass_counts[i], reverse=True)[:10]
    for i in sorted_idx:
        ax2.annotate(f"{pass_counts[i]}", (i, pass_counts[i]),
                     textcoords="offset points", xytext=(0, 10),
                     fontsize=6.5, color="#E65100",
                     ha="center", va="bottom", alpha=0.8)

    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2, fontsize=9, loc="lower left")

    # 每 20% 主刻度，每 5% 次刻度网格线
    ax.set_xticks(range(0, max_pos + 1, 20))
    ax.set_xticks(range(0, max_pos + 1, 5), minor=True)
    ax.grid(True, alpha=0.3, linewidth=0.5)
    ax.grid(True, which="minor", alpha=0.1, linewidth=0.3)


def _plot_optimal_path_axis(
    ax: "plt.Axes", optimal_path: OptimalPath, max_pos: int,
    range_start: int = 0, range_end: int = 100,
) -> None:
    """在指定 Axes 上绘制最优路径交错条块图"""
    n_runs = len(optimal_path)
    cmap = plt.colormaps["tab20"]
    colors = [cmap(i / max(n_runs, 1)) for i in range(n_runs)]

    for y in [-0.15, 0.15]:
        ax.barh(y, max_pos, height=0.22, color="#F0F0F0",
                edgecolor="#DDD", linewidth=0.5, zorder=1)

    for i, (start, end) in enumerate(optimal_path):
        row = i % 2
        y = 0.15 if row == 0 else -0.15
        color = colors[i]
        ax.barh(y, end - start, left=start, height=0.2, color=color,
                edgecolor="white", linewidth=0.8, zorder=2,
                label=f"Run {i+1}: {start}%→{end}%")
        ax.text((start + end) / 2, y, f"#{i+1}", ha="center", va="center",
                fontsize=7.5, fontweight="bold", color="white", zorder=3)

    ax.text(range_start, -0.55, f"{range_start}%", ha="center", fontsize=9, fontweight="bold")
    ax.text(range_end, -0.55, f"{range_end}%", ha="center", fontsize=9, fontweight="bold")

    seen = set()
    for _, end in optimal_path:
        if end not in seen:
            ax.text(end, 0.38, f"{end}%", ha="center", fontsize=7,
                    color="#666", rotation=45)
            seen.add(end)

    ax.text(-2.5, 0.15, "Odd", ha="right", va="center", fontsize=8, color="#999")
    ax.text(-2.5, -0.15, "Even", ha="right", va="center", fontsize=8, color="#999")
    ax.set_xlim(-4, max_pos + 2)
    ax.set_ylim(-0.6, 0.6)
    ax.set_xlabel("Position (%)", fontsize=11)
    ax.set_yticks([])
    ax.legend(fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.35),
              ncol=min(n_runs, 7), framealpha=0.8)
    # 每 20% 主刻度，每 5% 次刻度网格线
    ax.set_xticks(range(0, max_pos + 1, 20))
    ax.set_xticks(range(0, max_pos + 1, 5), minor=True)
    ax.grid(True, alpha=0.15, linewidth=0.4)
    ax.grid(True, which="minor", alpha=0.06, linewidth=0.2)


# ── 顶层绘图入口 ──────────────────────────────────────────────

def plot_pass_rate(
    pass_rates: PassRates, pass_counts: list[int], max_pos: int,
    output_path: str = "pass_rate.png",
) -> None:
    """单独的通过率+通过次数双轴图"""
    if not HAS_MATPLOTLIB:
        return
    fig, ax = plt.subplots(figsize=(14, 4.5))
    _plot_pass_rate_axis(ax, pass_rates, pass_counts, max_pos)
    ax.set_xlabel("Position (%)", fontsize=11)
    ax.set_title("Pass Rate (L) & Pass Count (R) per 1% Position",
                  fontsize=13, fontweight="bold")
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Pass rate chart saved: {output_path}")


def plot_optimal_path(
    optimal_path: OptimalPath, max_pos: int,
    output_path: str = "optimal_path.png",
    range_start: int = 0, range_end: int = 100,
) -> None:
    """单独的最优路径交错条块图"""
    if not HAS_MATPLOTLIB or not optimal_path:
        return
    fig, ax = plt.subplots(figsize=(14, 3))
    _plot_optimal_path_axis(ax, optimal_path, max_pos, range_start, range_end)
    if range_start == 0 and range_end == 100:
        title = "Optimal Path: Minimum Runs to Complete (0%→100%)"
    else:
        title = f"Longest Segment: {range_start}%→{range_end}%"
    ax.set_title(title, fontsize=13, fontweight="bold")
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Optimal path chart saved: {output_path}")


def plot_combined(
    pass_rates: PassRates, pass_counts: list[int], max_pos: int,
    optimal_path: Optional[OptimalPath] = None,
    output_path: str = "pass_combined.png",
    range_start: int = 0, range_end: int = 100,
) -> None:
    """组合图: 上半部通过率双轴, 下半部最优路径"""
    if not HAS_MATPLOTLIB:
        print("  [提示] 未安装 matplotlib，跳过图表生成。")
        print("         安装: pip install matplotlib")
        return

    has_path = bool(optimal_path)
    fig = plt.figure(figsize=(14, 6.5 if has_path else 4.5))
    gs = fig.add_gridspec(
        2 if has_path else 1, 1,
        height_ratios=[3, 1.5] if has_path else [1],
        hspace=0.3 if has_path else 0.3,
    )

    ax1 = fig.add_subplot(gs[0])
    _plot_pass_rate_axis(ax1, pass_rates, pass_counts, max_pos)
    ax1.set_title("Pass Rate (L) & Pass Count (R) per 1% Position",
                  fontsize=13, fontweight="bold")

    if has_path:
        ax3 = fig.add_subplot(gs[1])
        # 对齐横轴范围
        ax3.set_xlim(ax1.get_xlim())
        _plot_optimal_path_axis(ax3, optimal_path, max_pos, range_start, range_end)
        if range_start == 0 and range_end == 100:
            path_title = "Optimal Path: Minimum Runs to Complete (0%→100%)"
        else:
            path_title = f"Longest Segment: {range_start}%→{range_end}%"
        ax3.set_title(path_title, fontsize=13, fontweight="bold")

    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Combined chart saved: {output_path}")
