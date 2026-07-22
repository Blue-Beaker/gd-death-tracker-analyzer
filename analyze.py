#!/usr/bin/env python3
"""GD Death Tracker 数据分析脚本入口

用法:
  python3 analyze.py [general.dt 路径]     # 分析累计数据
  python3 analyze.py <session.dt 路径>     # 分析单个 session 文件
"""

import sys
import os
from datetime import datetime

from gd_analysis import load_data, analyze, print_report
from gd_plotting import plot_pass_rate, plot_optimal_path, plot_combined


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
