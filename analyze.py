#!/usr/bin/env python3
"""GD Death Tracker 数据分析脚本

分析 general.dt 中的 runs/deaths 数据，计算：
1. 最少需要多少次 run 拼接才能通关 (0→100%)
2. 各位置/区段的难度分析
3. 游戏时间统计

用法:
  python3 analyze.py [general.dt 路径]          # 分析累计数据
  python3 analyze.py --sessions [sessions目录]   # 分析所有 session 文件
"""

import json
import sys
import os
import glob
import time
from datetime import datetime
from collections import defaultdict

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

# ── 加载数据 ──────────────────────────────────────────────────

def load_data(path="general.dt"):
    with open(path) as f:
        raw = json.load(f)
    # session 文件的数据在 "data" 子对象中
    if "data" in raw:
        return raw["data"]
    return raw

# ── 核心分析 ──────────────────────────────────────────────────

def _merge_current_best(runs, current_best):
    """将 normal mode 的 currentBest 作为一条 0→best run 合并进去"""
    runs = dict(runs)
    if current_best > 0:
        key = f"0-{current_best}"
        runs[key] = runs.get(key, 0) + 1
    return runs


def _build_death_map(deaths_raw, runs):
    """合并 deaths 和 runs 中所有死亡数据"""
    death_map = defaultdict(int)
    for k, v in deaths_raw.items():
        death_map[int(k)] += v
    for k, v in runs.items():
        b = int(k.split("-")[1])
        death_map[b] += v
    return death_map


def _build_furthest_from(runs):
    """对每个起始位置，记录能到达的最远位置"""
    furthest_from = {}
    for k, v in runs.items():
        a, b = k.split("-")
        a, b = int(a), int(b)
        if a not in furthest_from or b > furthest_from[a]:
            furthest_from[a] = b
    return furthest_from


def _find_optimal_path(furthest_from, max_pos):
    """DP 求从 0 到 max_pos 的最少 runs 路径"""
    INF = 9999
    dp = {max_pos: 0}
    next_pos = {}

    for pos in range(max_pos - 1, -1, -1):
        best = INF
        best_next = None
        for start in range(0, pos + 1):
            if start in furthest_from:
                end = furthest_from[start]
                if end > pos and end in dp:
                    candidate = 1 + dp[end]
                    if candidate < best:
                        best = candidate
                        best_next = end
        if best < INF:
            dp[pos] = best
            next_pos[pos] = best_next

    # 回溯
    optimal_path = []
    if 0 in next_pos:
        pos = 0
        while pos < max_pos:
            nxt = next_pos[pos]
            for start in range(0, pos + 1):
                if start in furthest_from and furthest_from[start] >= nxt:
                    optimal_path.append((start, furthest_from[start]))
                    break
            pos = nxt
    return dp.get(0), optimal_path


def _compute_pass_rates(runs, max_pos):
    """计算每 1% 的通过次数和通过率 (不含区段起点终点)"""
    pass_counts = [0] * (max_pos + 1)
    fail_counts = [0] * (max_pos + 1)
    for k, v in runs.items():
        a, b = k.split("-")
        a, b = int(a), int(b)
        for x in range(a + 1, b):
            if 1 <= x <= max_pos:
                pass_counts[x] += v
        if 1 <= b <= max_pos:
            fail_counts[b] += v

    pass_rates = []
    for x in range(1, max_pos + 1):
        total = pass_counts[x] + fail_counts[x]
        rate = pass_counts[x] / total if total > 0 else None
        pass_rates.append((x, pass_counts[x], fail_counts[x], rate))
    # 0 和 100 始终 100%
    pass_rates.insert(0, (0, 0, 0, 1.0))
    pass_rates.append((max_pos, 0, 0, 1.0))
    return pass_rates, pass_counts


def _compute_segment_deaths(death_map):
    """按固定区段统计死亡数"""
    segments = [
        (0, 3, "0-3%   (开场)"),
        (4, 7, "4-7%   (第一个难点)"),
        (8, 15, "8-15%"),
        (16, 26, "16-26%"),
        (27, 38, "27-38% (中间段)"),
        (39, 50, "39-50%"),
        (51, 64, "51-64%"),
        (65, 76, "65-76%"),
        (77, 84, "77-84% (后期)"),
        (85, 91, "85-91%"),
        (92, 99, "92-99% (终点前)"),
        (100, 100, "100%   (终点)"),
    ]
    return [(label, sum(death_map.get(p, 0) for p in range(lo, hi + 1)))
            for lo, hi, label in segments]


def _format_time_ns(ns):
    s = ns / 1_000_000_000
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = s % 60
    return f"{h}h {m}m {sec:.0f}s"


def analyze(data, max_pos=100):
    """主分析函数，返回包含所有统计结果的 dict"""
    runs = data.get("runs", {})
    deaths_raw = data.get("deaths", {})
    current_best = data.get("currentBest", -1)
    new_bests = data.get("newBests", [])

    runs = _merge_current_best(runs, current_best)
    death_map = _build_death_map(deaths_raw, runs)
    total_deaths = sum(death_map.values())
    furthest_from = _build_furthest_from(runs)
    min_runs, optimal_path = _find_optimal_path(furthest_from, max_pos)
    pass_rates, pass_counts = _compute_pass_rates(runs, max_pos)
    segment_deaths = _compute_segment_deaths(death_map)
    top_chokes = sorted(death_map.items(), key=lambda x: -x[1])[:20]
    top_run_segments = sorted(runs.items(), key=lambda x: -x[1])[:20]

    pg = data.get("playtimeGeneral", {})
    pp = data.get("playtimePaused", {})
    pd = data.get("playtimeDead", {})
    total_ns = pg.get("playtimeF0", 0) + pg.get("playtimeRuns", 0)
    pause_ns = pp.get("playtimeF0", 0) + pp.get("playtimeRuns", 0)
    dead_ns = pd.get("playtimeF0", 0) + pd.get("playtimeRuns", 0)

    return {
        "max_pos": max_pos,
        "current_best": current_best,
        "new_bests": new_bests,
        "total_deaths": total_deaths,
        "min_runs": min_runs,
        "optimal_path": optimal_path,
        "furthest_from": dict(sorted(furthest_from.items())),
        "segment_deaths": segment_deaths,
        "pass_rates": pass_rates,
        "pass_counts": pass_counts,
        "top_chokes": top_chokes,
        "top_runs": top_run_segments,
        "total_time": _format_time_ns(total_ns),
        "pause_time": _format_time_ns(pause_ns),
        "dead_time": _format_time_ns(dead_ns),
        "effective_time": _format_time_ns(total_ns - pause_ns),
    }


# ── 格式化输出 ──────────────────────────────────────────────────

def print_report(result):
    r = result
    print("=" * 56)
    print("  GD Death Tracker 数据分析报告")
    print("=" * 56)
    print(f"  关卡长度:          0–{r['max_pos']}%")
    print(f"  当前最佳 (正常模式): {r['current_best']}%")
    print(f"  newBests 历史:      {r['new_bests']}")
    print(f"  总死亡次数:         {r['total_deaths']}")
    print(f"  总游戏时间:         {r['total_time']}")
    print(f"  暂停时间:           {r['pause_time']}")
    print(f"  死亡时间:           {r['dead_time']}")
    print(f"  有效游戏时间:       {r['effective_time']}")
    print()

    # ── 最少 runs 拼接 ──
    print("─" * 56)
    print(f"  最少 runs 拼接通关: {r['min_runs']} 次 run")
    print("─" * 56)
    if r['optimal_path']:
        for i, (s, e) in enumerate(r['optimal_path']):
            print(f"    Run {i+1}:  {s:3d}% → {e:3d}%  ({s}% → {e}%)")
    print()

    # ── 各位置出发能到的最远位置 ──
    print("─" * 56)
    print("  从各位置出发能到达的最远位置 (摘录)")
    print("─" * 56)
    ff = r['furthest_from']
    for a in sorted(ff.keys()):
        if a <= 10 or a >= 80 or a % 5 == 0:
            print(f"    从 {a:3d}% 出发 → {ff[a]:3d}%")
    print()

    # ── 区段死亡分布 ──
    print("─" * 56)
    print("  各区段死亡分布")
    print("─" * 56)
    max_cnt = max(c for _, c in r['segment_deaths']) if r['segment_deaths'] else 1
    for label, cnt in r['segment_deaths']:
        bar_len = int(cnt / max_cnt * 30)
        bar = "█" * bar_len
        pct = cnt / r['total_deaths'] * 100
        print(f"    {label}: {cnt:5d} 次 ({pct:5.1f}%)  {bar}")
    print()

    # ── Top choke points ──
    print("─" * 56)
    print("  死亡最多的位置 (Top 15 Choke Points)")
    print("─" * 56)
    for pos, cnt in r['top_chokes'][:15]:
        pct = pos / r['max_pos'] * 100
        print(f"    位置 {pos:3d} ({pct:5.1f}%): {cnt:4d} 次")
    print()

    # ── Top 过渡段 ──
    print("─" * 56)
    print("  最难过渡段 (Top 15, 按死亡数)")
    print("─" * 56)
    for k, v in r['top_runs'][:15]:
        a, b = k.split("-")
        a, b = int(a), int(b)
        a_pct = a / r['max_pos'] * 100
        b_pct = b / r['max_pos'] * 100
        print(f"    {a:3d}%→{b:3d}% ({a_pct:5.1f}%→{b_pct:5.1f}%): {v:4d} 次")
    print()


# ── 图表绘制 ──────────────────────────────────────────────────

def _plot_pass_rate_axis(ax, pass_rates, pass_counts, max_pos):
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
    ax.grid(True, alpha=0.3, linewidth=0.5)


def _plot_optimal_path_axis(ax, optimal_path, max_pos):
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

    ax.text(0, -0.55, "0%", ha="center", fontsize=9, fontweight="bold")
    ax.text(max_pos, -0.55, "100%", ha="center", fontsize=9, fontweight="bold")

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
    ax.grid(False)


def plot_pass_rate(pass_rates, pass_counts, max_pos, output_path="pass_rate.png"):
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


def plot_optimal_path(optimal_path, max_pos, output_path="optimal_path.png"):
    """单独的最优路径交错条块图"""
    if not HAS_MATPLOTLIB or not optimal_path:
        return
    fig, ax = plt.subplots(figsize=(14, 3))
    _plot_optimal_path_axis(ax, optimal_path, max_pos)
    ax.set_title("Optimal Path: Minimum Runs to Complete (0%→100%)",
                  fontsize=13, fontweight="bold")
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Optimal path chart saved: {output_path}")


def plot_combined(pass_rates, pass_counts, max_pos, optimal_path=None,
                  output_path="pass_combined.png"):
    """组合图: 上半部通过率双轴, 下半部最优路径, 提高纵横比清晰显示"""
    if not HAS_MATPLOTLIB:
        print("  [提示] 未安装 matplotlib，跳过图表生成。")
        print("         安装: pip install matplotlib")
        return

    has_path = bool(optimal_path)
    # 组合图: 宽度14不变, 下半部高度降低
    fig = plt.figure(figsize=(14, 6.0 if has_path else 4.5))
    gs = fig.add_gridspec(
        2 if has_path else 1, 1,
        height_ratios=[3, 1.5] if has_path else [1],
        hspace=0.1 if has_path else 0.3,
    )

    ax1 = fig.add_subplot(gs[0])
    _plot_pass_rate_axis(ax1, pass_rates, pass_counts, max_pos)
    ax1.set_xticklabels([])
    ax1.set_title("Pass Rate (L) & Pass Count (R) per 1% Position",
                  fontsize=13, fontweight="bold")

    if has_path:
        ax3 = fig.add_subplot(gs[1], sharex=ax1)
        _plot_optimal_path_axis(ax3, optimal_path, max_pos)
        ax3.set_title("Optimal Path: Minimum Runs to Complete (0%→100%)",
                      fontsize=13, fontweight="bold")

    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Combined chart saved: {output_path}")


# ── 入口 ──────────────────────────────────────────────────────

def _session_timestamp(path):
    """从 session 文件路径解析时间戳字符串"""
    basename = os.path.splitext(os.path.basename(path))[0]
    try:
        ts = int(basename)
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d_%H-%M-%S")
    except ValueError:
        return basename


def process_file(path, out_dir=None):
    """分析单个 .dt 文件并生成图表"""
    data = load_data(path)
    result = analyze(data)
    print_report(result)
    if out_dir is None:
        out_dir = os.path.dirname(path) or "."

    # 判断是否为 session 文件（文件名是纯数字时间戳）
    basename = os.path.splitext(os.path.basename(path))[0]
    is_session = False
    try:
        int(basename)
        is_session = True
    except ValueError:
        pass

    if is_session:
        date_str = _session_timestamp(path)
        prefix = f"session_{date_str}"
        rate_name = f"{prefix}_pass_rate.png"
        path_name = f"{prefix}_optimal_path.png"
        combined_name = f"{prefix}_pass_combined.png"
    else:
        rate_name = "pass_rate.png"
        path_name = "optimal_path.png"
        combined_name = "pass_combined.png"

    plot_pass_rate(
        result["pass_rates"], result["pass_counts"], result["max_pos"],
        output_path=os.path.join(out_dir, rate_name),
    )
    plot_optimal_path(
        result["optimal_path"], result["max_pos"],
        output_path=os.path.join(out_dir, path_name),
    )
    plot_combined(
        result["pass_rates"], result["pass_counts"], result["max_pos"],
        optimal_path=result["optimal_path"],
        output_path=os.path.join(out_dir, combined_name),
    )


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "general.dt"
    process_file(path)
