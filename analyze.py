#!/usr/bin/env python3
"""GD Death Tracker 数据分析脚本

分析 general.dt 中的 runs/deaths 数据，计算：
1. 最少需要多少次 run 拼接才能通关 (0→100%)
2. 各位置/区段的难度分析
3. 游戏时间统计

用法: python3 analyze.py [general.dt 路径]
"""

import json
import sys
import os
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
        return json.load(f)

# ── 核心分析 ──────────────────────────────────────────────────

def analyze(data, max_pos=100):
    runs = data["runs"]           # "A-B": count
    deaths_raw = data["deaths"]   # "pos": count
    current_best = data.get("currentBest", -1)
    new_bests = data.get("newBests", [])

    # ── 1. 合并 currentBest 作为一条有效的 "0→best" run ──
    #    正常模式从 0 出发到过 currentBest，等价于有一条 0→currentBest 的记录
    runs = dict(runs)  # 复制一份避免修改原数据
    if current_best > 0:
        key = f"0-{current_best}"
        runs[key] = runs.get(key, 0) + 1  # 权重+1

    # ── 2. 合并所有死亡数据 ──
    death_map = defaultdict(int)
    for k, v in deaths_raw.items():
        death_map[int(k)] += v
    for k, v in runs.items():
        b = int(k.split("-")[1])
        death_map[b] += v
    total_deaths = sum(death_map.values())

    # ── 3. 构建"从某位置出发能到的最远位置"映射 ──
    furthest_from = {}
    for k, v in runs.items():
        a, b = k.split("-")
        a, b = int(a), int(b)
        if a not in furthest_from or b > furthest_from[a]:
            furthest_from[a] = b

    # ── 4. DP 求最少 runs 路径 ──
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

    # ── 5. 回溯最优路径 ──
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

    # ── 6. 区段难度统计 ──
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
    segment_deaths = []
    for lo, hi, label in segments:
        cnt = sum(death_map.get(p, 0) for p in range(lo, hi + 1))
        segment_deaths.append((label, cnt))

    # ── 7. 每 1% 的通过率 ──
    # 对于一条 run A→B: 位置 X (A < X < B) 算通过, 位置 B 算未通过
    pass_counts = [0] * (max_pos + 1)   # pass_counts[X] = 通过 X 的次数
    fail_counts = [0] * (max_pos + 1)   # fail_counts[X] = 死在 X 的次数
    for k, v in runs.items():
        a, b = k.split("-")
        a, b = int(a), int(b)
        # 位置 a 是起点，不算通过也不算失败
        # 位置 a+1 到 b-1 算通过
        for x in range(a + 1, b):
            if 1 <= x <= max_pos:
                pass_counts[x] += v
        # 位置 b 算失败
        if 1 <= b <= max_pos:
            fail_counts[b] += v

    pass_rates = []
    for x in range(1, max_pos + 1):
        total = pass_counts[x] + fail_counts[x]
        rate = pass_counts[x] / total if total > 0 else None
        pass_rates.append((x, pass_counts[x], fail_counts[x], rate))

    # 0 和 100 始终算 100% 通过率
    pass_rates.insert(0, (0, 0, 0, 1.0))  # position 0
    pass_rates.append((max_pos, 0, 0, 1.0))  # position 100

    # ── 8. Top choke points ──
    top_chokes = sorted(death_map.items(), key=lambda x: -x[1])[:20]

    # ── 8. Top 过渡段 ──
    top_runs = sorted(runs.items(), key=lambda x: -x[1])[:20]

    # ── 9. 时间统计 ──
    pg = data.get("playtimeGeneral", {})
    pp = data.get("playtimePaused", {})
    pd = data.get("playtimeDead", {})

    def fmt_ns(ns):
        s = ns / 1_000_000_000
        h = int(s // 3600)
        m = int((s % 3600) // 60)
        sec = s % 60
        return f"{h}h {m}m {sec:.0f}s"

    total_time_ns = pg.get("playtimeF0", 0) + pg.get("playtimeRuns", 0)
    pause_time_ns = pp.get("playtimeF0", 0) + pp.get("playtimeRuns", 0)
    dead_time_ns = pd.get("playtimeF0", 0) + pd.get("playtimeRuns", 0)

    return {
        "max_pos": max_pos,
        "current_best": current_best,
        "new_bests": new_bests,
        "total_deaths": total_deaths,
        "min_runs": dp.get(0, None),
        "optimal_path": optimal_path,
        "furthest_from": dict(sorted(furthest_from.items())),
        "segment_deaths": segment_deaths,
        "pass_rates": pass_rates,
        "pass_counts": pass_counts,  # pass_counts[x] = 通过位置 x 的次数 (不含起点终点)
        "top_chokes": top_chokes,
        "top_runs": top_runs,
        "total_time": fmt_ns(total_time_ns),
        "pause_time": fmt_ns(pause_time_ns),
        "dead_time": fmt_ns(dead_time_ns),
        "effective_time": fmt_ns(total_time_ns - pause_time_ns),
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


# ── 合并折线图 ──────────────────────────────────────────────

def plot_combined(pass_rates, pass_counts, max_pos, output_path="pass_combined.png"):
    """生成双纵轴组合图: 左轴通过率, 右轴通过次数"""
    if not HAS_MATPLOTLIB:
        print("  [提示] 未安装 matplotlib，跳过图表生成。")
        print("         安装: pip install matplotlib")
        return

    positions_rate = [x for x, _, _, r in pass_rates if r is not None]
    rates = [r for _, _, _, r in pass_rates if r is not None]

    x_counts = list(range(0, max_pos + 1))
    y_counts = [pass_counts[x] for x in x_counts]

    fig, ax1 = plt.subplots(figsize=(14, 5))

    # ── 左轴: 通过率 (蓝色) ──
    color_rate = "#2196F3"
    ax1.plot(positions_rate, rates, color=color_rate, linewidth=1.5, zorder=3, label="Pass Rate")
    ax1.fill_between(positions_rate, rates, alpha=0.08, color=color_rate)
    ax1.axhline(0.5, color="#999", linestyle="--", linewidth=0.6, alpha=0.6)
    ax1.set_xlabel("Position (%)", fontsize=11)
    ax1.set_ylabel("Pass Rate", fontsize=11, color=color_rate)
    ax1.tick_params(axis="y", labelcolor=color_rate)
    ax1.set_xlim(0, max_pos)
    ax1.set_ylim(-0.05, 1.05)
    ax1.set_xticks(range(0, max_pos + 1, 5))

    # 通过率最低点标注
    sorted_by_rate = sorted(
        [(x, p, f, r) for x, p, f, r in pass_rates if r is not None],
        key=lambda t: t[3],
    )
    for x, p, f, r in sorted_by_rate[:10]:
        ax1.annotate(
            f"↓{f}",
            (x, r),
            textcoords="offset points",
            xytext=(0, -14),
            fontsize=6.5,
            color="#e53935",
            ha="center",
            va="top",
            alpha=0.8,
        )

    # ── 右轴: 通过次数 (橙色) ──
    ax2 = ax1.twinx()
    color_count = "#FF9800"
    ax2.plot(x_counts, y_counts, color=color_count, linewidth=1.5, zorder=3, label="Pass Count")
    ax2.fill_between(x_counts, y_counts, alpha=0.08, color=color_count)
    ax2.set_ylabel("Pass Count", fontsize=11, color=color_count)
    ax2.tick_params(axis="y", labelcolor=color_count)

    # 通过次数最多点标注
    sorted_idx = sorted(
        range(1, max_pos), key=lambda i: pass_counts[i], reverse=True
    )[:10]
    for i in sorted_idx:
        ax2.annotate(
            f"{pass_counts[i]}",
            (i, pass_counts[i]),
            textcoords="offset points",
            xytext=(0, 10),
            fontsize=6.5,
            color="#E65100",
            ha="center",
            va="bottom",
            alpha=0.8,
        )

    # ── 合并 legend ──
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, fontsize=9, loc="lower left")

    ax1.set_title("Pass Rate (L) & Pass Count (R) per 1% Position", fontsize=13, fontweight="bold")
    ax1.grid(True, alpha=0.3, linewidth=0.5)

    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    print(f"  Combined chart saved: {output_path}")


# ── 最优路径图示 ──────────────────────────────────────────────

def plot_optimal_path(optimal_path, max_pos, output_path="optimal_path.png"):
    """生成最优 runs 拼接路径图 — 两行交错排列以显示重叠"""
    if not HAS_MATPLOTLIB:
        return
    if not optimal_path:
        print("  No optimal path to plot.")
        return

    fig, ax = plt.subplots(figsize=(14, 3.5))

    n_runs = len(optimal_path)
    cmap = plt.colormaps["tab20"]
    colors = [cmap(i / max(n_runs, 1)) for i in range(n_runs)]

    # 两行交错: 奇数行在上 (y=0.15), 偶数行在下 (y=-0.15)
    # 灰色背景条 (两行各一条)
    for y in [-0.15, 0.15]:
        ax.barh(y, max_pos, height=0.22, color="#F0F0F0",
                edgecolor="#DDD", linewidth=0.5, zorder=1)

    for i, (start, end) in enumerate(optimal_path):
        row = i % 2
        y = 0.15 if row == 0 else -0.15
        bar_height = 0.2
        color = colors[i]

        ax.barh(y, end - start, left=start, height=bar_height,
                color=color, edgecolor="white", linewidth=0.8, zorder=2,
                label=f"Run {i+1}: {start}%→{end}%")

        # run 编号
        mid = (start + end) / 2
        ax.text(mid, y, f"#{i+1}", ha="center", va="center",
                fontsize=7.5, fontweight="bold", color="white", zorder=3)

    # 标注起点终点
    ax.text(0, -0.55, "0%", ha="center", fontsize=9, fontweight="bold")
    ax.text(max_pos, -0.55, "100%", ha="center", fontsize=9, fontweight="bold")

    # 标注关键位置百分比 (每个 run 的结束位置)
    seen = set()
    for _, end in optimal_path:
        if end not in seen:
            ax.text(end, 0.38, f"{end}%", ha="center", fontsize=7,
                    color="#666", rotation=45)
            seen.add(end)

    # 行标签
    ax.text(-2.5, 0.15, "Odd", ha="right", va="center", fontsize=8, color="#999")
    ax.text(-2.5, -0.15, "Even", ha="right", va="center", fontsize=8, color="#999")

    ax.set_xlim(-4, max_pos + 2)
    ax.set_ylim(-0.6, 0.6)
    ax.set_title("Optimal Path: Minimum Runs to Complete (0%→100%)", fontsize=13, fontweight="bold")
    ax.set_xlabel("Position (%)", fontsize=11)
    ax.set_yticks([])
    ax.legend(fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.25),
              ncol=min(n_runs, 7), framealpha=0.8)
    ax.grid(False)

    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Optimal path chart saved: {output_path}")


# ── 入口 ──────────────────────────────────────────────────────

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "general.dt"
    data = load_data(path)
    result = analyze(data)
    print_report(result)
    out_dir = os.path.dirname(path) or "."
    plot_combined(
        result["pass_rates"],
        result["pass_counts"],
        result["max_pos"],
        output_path=os.path.join(out_dir, "pass_combined.png"),
    )
    plot_optimal_path(
        result["optimal_path"],
        result["max_pos"],
        output_path=os.path.join(out_dir, "optimal_path.png"),
    )
