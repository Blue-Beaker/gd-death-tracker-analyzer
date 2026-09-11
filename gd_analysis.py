"""GD Death Tracker 数据分析模块

提供数据加载、统计分析和最优路径计算功能。
"""

import json
from collections import defaultdict
from typing import Any, Optional

# 类型别名
Runs = dict["Run", int]            # Run -> count
Deaths = dict["Death", int]        # Death -> count
FurthestFrom = dict[int, int]      # start -> furthest end
OptimalPath = list[tuple[int, int]]  # [(start, end), ...]
PassRates = list[tuple[int, int, int, Optional[float]]]  # (pos, pass, fail, rate)
SegmentDeaths = list[tuple[str, int]]  # (label, count)
Result = dict[str, Any]


class Run:
    """一次尝试: 从 start 出发，死在 end"""

    start: int
    end: int

    def __init__(self, start: int, end: int) -> None:
        self.start = start
        self.end = end

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Run) and (self.start, self.end) == (other.start, other.end)

    def __hash__(self) -> int:
        # 每一对 (start, end) 都有唯一 hash
        return (self.start << 16) | self.end

    def __repr__(self) -> str:
        return f"Run({self.start}, {self.end})"

    @classmethod
    def from_key(cls, key: str) -> "Run":
        """从 'A-B' 字符串解析"""
        a, b = key.split("-")
        return cls(int(a), int(b))


class Death(Run):
    """一次死亡: 从 0 出发，死在 end"""

    def __init__(self, end: int) -> None:
        super().__init__(0, end)

    @classmethod
    def from_key(cls, key: str) -> "Death":
        """从 'pos' 字符串解析"""
        return cls(int(key))


# ── 加载数据 ──────────────────────────────────────────────────

def load_data(path: str = "general.dt") -> dict[str, Any]:
    with open(path) as f:
        raw = json.load(f)
    # session 文件的数据在 "data" 子对象中
    data = raw["data"] if "data" in raw else raw

    # 将 runs/deaths 的字符串键转换为 Run/Death 实例
    if "runs" in data:
        data["runs"] = {Run.from_key(k): v for k, v in data["runs"].items()}
    if "deaths" in data:
        data["deaths"] = {Death.from_key(k): v for k, v in data["deaths"].items()}
    return data


# ── 核心分析 ──────────────────────────────────────────────────

def _merge_current_best(runs: Runs, deaths: Deaths, current_best: int) -> Runs:
    """将所有 deaths 计数合并入 runs，并加入 normal mode 的 currentBest

    Death(end) 等价于 Run(0, end)，因此可直接合并为同一起点的 run。
    currentBest 作为一条 0→best run 加入。
    """
    merged = dict(runs)
    for death, v in deaths.items():
        key = Run(death.start, death.end)
        merged[key] = merged.get(key, 0) + v
    if current_best > 0:
        key = Run(0, current_best)
        merged[key] = merged.get(key, 0) + 1
    return merged


def _build_death_map(runs: Runs) -> dict[int, int]:
    """统计每个 end 位置的死亡次数 (deaths 已合并入 runs)"""
    death_map: dict[int, int] = defaultdict(int)
    for run, v in runs.items():
        death_map[run.end] += v
    return death_map


def _build_furthest_from(runs: Runs) -> FurthestFrom:
    """对每个起始位置，记录能到达的最远位置"""
    furthest_from: FurthestFrom = {}
    for run in runs:
        if run.start not in furthest_from or run.end > furthest_from[run.start]:
            furthest_from[run.start] = run.end
    return furthest_from


def _find_optimal_path(
    furthest_from: FurthestFrom, max_pos: int
) -> tuple[Optional[int], OptimalPath, int, int, bool]:
    """DP 求从 0 到 max_pos 的最少 runs 路径

    若找不到完整路径，则找 session 中覆盖范围最广的一段区间
    (最早 start → 最远 end)，并在该区间内求最少 runs 拼接。
    返回 (min_runs, path, range_start, range_end, is_full)。
    """
    INF = 9999
    dp: dict[int, int] = {max_pos: 0}
    next_pos: dict[int, Optional[int]] = {}

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

    # 回溯完整 0→100 路径
    if 0 in next_pos:
        path: OptimalPath = []
        pos = 0
        while pos < max_pos:
            nxt = next_pos[pos]
            if not nxt:
                break
            for start in range(0, pos + 1):
                if start in furthest_from and furthest_from[start] >= nxt:
                    path.append((start, furthest_from[start]))
                    break
            pos = nxt
        return dp.get(0), path, 0, max_pos, True

    # 回退: 找覆盖最广的区间
    if not furthest_from:
        return None, [], 0, 0, False

    min_start = min(furthest_from.keys())
    max_end = max(furthest_from.values())

    # 在该区间内重新做 DP
    dp_seg: dict[int, int] = {max_end: 0}
    next_seg: dict[int, Optional[int]] = {}
    for pos in range(max_end - 1, min_start - 1, -1):
        best = INF
        best_next = None
        for start in range(min_start, pos + 1):
            if start in furthest_from:
                end = furthest_from[start]
                if end > pos and end <= max_end and end in dp_seg:
                    candidate = 1 + dp_seg[end]
                    if candidate < best:
                        best = candidate
                        best_next = end
        if best < INF:
            dp_seg[pos] = best
            next_seg[pos] = best_next

    path = []
    if min_start in next_seg:
        pos = min_start
        while pos < max_end:
            nxt = next_seg[pos]
            if not nxt:
                break
            for start in range(min_start, pos + 1):
                if start in furthest_from and furthest_from[start] >= nxt:
                    path.append((start, furthest_from[start]))
                    break
            pos = nxt
        return dp_seg.get(min_start), path, min_start, max_end, False

    # 极端回退: 只有一段
    return None, [(min_start, max_end)], min_start, max_end, False


def _compute_pass_rates(
    runs: Runs, max_pos: int
) -> tuple[PassRates, list[int]]:
    """计算每 1% 的通过次数和通过率 (不含区段起点终点)"""
    pass_counts = [0] * (max_pos + 1)
    fail_counts = [0] * (max_pos + 1)
    for run, v in runs.items():
        a, b = run.start, run.end
        for x in range(a + 1, b):
            if 1 <= x <= max_pos:
                pass_counts[x] += v
        if 1 <= b <= max_pos:
            fail_counts[b] += v

    pass_rates: PassRates = []
    for x in range(1, max_pos + 1):
        total = pass_counts[x] + fail_counts[x]
        rate = pass_counts[x] / total if total > 0 else None
        pass_rates.append((x, pass_counts[x], fail_counts[x], rate))
    # 0 和 100 始终 100%
    pass_rates.insert(0, (0, 0, 0, 1.0))
    pass_rates.append((max_pos, 0, 0, 1.0))
    return pass_rates, pass_counts


def _compute_segment_deaths(death_map: dict[int, int]) -> SegmentDeaths:
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


def _format_time_ns(ns: int) -> str:
    s = ns / 1_000_000_000
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = s % 60
    return f"{h}h {m}m {sec:.0f}s"


def analyze(data: dict[str, Any], max_pos: int = 100) -> Result:
    """主分析函数，返回包含所有统计结果的 dict"""
    runs = data.get("runs", {})
    deaths_raw = data.get("deaths", {})
    current_best = data.get("currentBest", -1)
    new_bests = data.get("newBests", [])

    runs = _merge_current_best(runs, deaths_raw, current_best)
    death_map = _build_death_map(runs)
    total_deaths = sum(death_map.values())
    furthest_from = _build_furthest_from(runs)
    min_runs, optimal_path, range_start, range_end, is_full_path = _find_optimal_path(furthest_from, max_pos)
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
        "range_start": range_start,
        "range_end": range_end,
        "is_full_path": is_full_path,
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

def print_report(result: Result) -> None:
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
    if r['is_full_path']:
        print(f"  最少 runs 拼接通关: {r['min_runs']} 次 run (0%→100%)")
    else:
        print(f"  区间 {r['range_start']}%→{r['range_end']}% 最少 runs: {r['min_runs']} 次")
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
    for run, v in r['top_runs'][:15]:
        a, b = run.start, run.end
        a_pct = a / r['max_pos'] * 100
        b_pct = b / r['max_pos'] * 100
        print(f"    {a:3d}%→{b:3d}% ({a_pct:5.1f}%→{b_pct:5.1f}%): {v:4d} 次")
    print()
