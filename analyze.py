#!/usr/bin/env python3
"""GD Death Tracker 数据分析脚本入口

用法:
  python3 analyze.py [数据文件] [输出目录]
    数据文件: general.dt 或 session .dt 文件 (默认: general.dt)
    输出目录: 图表保存目录 (默认: 当前工作目录)
"""

import sys
import os
from datetime import datetime

from gd_analysis import load_data, analyze, print_report
from gd_plotting import plot_pass_rate, plot_optimal_path, plot_combined


def _session_timestamp(path: str) -> str:
    """从 session 文件路径解析时间戳字符串"""
    basename = os.path.splitext(os.path.basename(path))[0]
    try:
        ts = int(basename)
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d_%H-%M-%S")
    except ValueError:
        return basename


def process_file(path: str, out_dir: str = ".") -> None:
    """分析单个 .dt 文件并生成图表到 out_dir"""
    os.makedirs(out_dir, exist_ok=True)

    data = load_data(path)
    result = analyze(data)
    print_report(result)

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

    has_full_path = result["is_full_path"]
    has_any_path = bool(result["optimal_path"])
    has_rates = result["pass_rates"] is not None and len(result["pass_rates"]) > 0

    # 计算实际起止范围
    if has_any_path:
        range_start = result["range_start"]
        range_end = result["range_end"]
    else:
        range_start = 0
        range_end = 0

    if has_rates:
        plot_pass_rate(
            result["pass_rates"], result["pass_counts"], result["max_pos"],
            output_path=os.path.join(out_dir, rate_name),
        )
    else:
        print("  [跳过] 无通过率数据，不生成 pass_rate 图表")

    if has_any_path:
        plot_optimal_path(
            result["optimal_path"], result["max_pos"],
            output_path=os.path.join(out_dir, path_name),
            range_start=range_start, range_end=range_end,
        )
    else:
        print("  [跳过] 无有效 runs 数据，不生成 optimal_path 图表")

    if has_rates and has_any_path:
        plot_combined(
            result["pass_rates"], result["pass_counts"], result["max_pos"],
            optimal_path=result["optimal_path"],
            output_path=os.path.join(out_dir, combined_name),
            range_start=range_start, range_end=range_end,
        )
    else:
        print("  [跳过] 数据不足，不生成合并图表")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "general.dt"
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "."
    process_file(path, out_dir)
