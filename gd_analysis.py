"""GD Death Tracker 数据分析模块

提供数据加载、统计分析和最优路径计算功能。
"""

import json
from collections import defaultdict


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
