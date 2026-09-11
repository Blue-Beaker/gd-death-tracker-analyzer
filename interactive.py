#!/usr/bin/env python3
"""GD Death Tracker 交互式分析入口

用法:
  python3 interactive.py [levels目录] [输出目录]
    levels目录: 包含各关卡子目录的文件夹
                (默认: 从 GD 存档自动查找)
    输出目录:   图表保存目录 (默认: 当前工作目录)

交互流程:
  1. 列出所有关卡 (关名 + id) 供选择
  2. 选择关卡后列出 main (general.dt) 或各 session
  3. 分析所选数据并生成图表
"""

import os
import sys
import glob

from analyze import process_file, _session_timestamp

# GD 存档中 death_tracker mod 的 levels 目录相对路径
LEVELS_REL = os.path.join("geode", "mods", "elohmrow.death_tracker", "levels")


def _default_gd_save_dirs() -> list[str]:
    """按操作系统推断 GD 存档的默认目录

    Windows:  %LOCALAPPDATA%\\GeometryDash\\
    macOS:    $HOME/Library/Application Support/GeometryDash/
    Linux:    <SteamLibrary>/steamapps/compatdata/322170/pfx/
              drive_c/users/<user>/AppData/Local/GeometryDash/
    """
    home = os.path.expanduser("~")
    dirs = []

    if sys.platform.startswith("win"):
        local = os.environ.get("LOCALAPPDATA") or os.path.join(home, "AppData", "Local")
        dirs.append(os.path.join(local, "GeometryDash"))
    elif sys.platform == "darwin":
        dirs.append(os.path.join(home, "Library", "Application Support", "GeometryDash"))
    else:
        # Linux: 扫描常见 Steam 库中的 compatdata/322170/pfx
        steam_roots = [
            os.path.join(home, ".local/share/Steam"),
            os.path.join(home, ".steam/steam"),
            os.path.join(home, ".var/app/com.valvesoftware.Steam/data/Steam"),
        ]
        # 读取额外 Steam 库路径
        for root in list(steam_roots):
            vdf = os.path.join(root, "steamapps", "libraryfolders.vdf")
            if os.path.exists(vdf):
                try:
                    with open(vdf) as f:
                        for line in f:
                            line = line.strip()
                            if '"path"' in line:
                                p = line.split('"')[3]
                                steam_roots.append(p)
                except OSError:
                    pass

        for root in steam_roots:
            pfx = os.path.join(root, "steamapps", "compatdata", "322170", "pfx")
            users_dir = os.path.join(pfx, "drive_c", "users")
            if not os.path.isdir(users_dir):
                continue
            for user in os.listdir(users_dir):
                gd = os.path.join(users_dir, user, "AppData", "Local", "GeometryDash")
                if gd not in dirs:
                    dirs.append(gd)

    return dirs


def _find_default_levels() -> str:
    """查找 levels 目录

    优先使用运行目录下的 levels (符号链接)，否则从 GD 默认存档位置查找。
    """
    # 1. 运行目录下的 levels
    local_levels = os.path.join(os.getcwd(), "levels")
    if os.path.isdir(local_levels):
        return local_levels

    # 2. GD 默认存档位置
    for gd in _default_gd_save_dirs():
        c = os.path.join(gd, LEVELS_REL)
        if os.path.isdir(c):
            return c
    return ""


def _scan_levels(levels_dir: str) -> list[dict]:
    """扫描 levels 目录，返回 [{id, name, dir, has_general, sessions}]"""
    levels = []
    if not os.path.isdir(levels_dir):
        return levels

    for entry in sorted(os.listdir(levels_dir)):
        level_dir = os.path.join(levels_dir, entry)
        if not os.path.isdir(level_dir):
            continue

        meta_path = os.path.join(level_dir, "metadata")
        if not os.path.exists(meta_path):
            continue

        meta = load_json(meta_path)
        name = meta.get("levelName", "") or "(未命名)"

        general_path = os.path.join(level_dir, "general.dt")
        sessions_dir = os.path.join(level_dir, "sessions")
        sessions = []
        if os.path.isdir(sessions_dir):
            sessions = sorted(
                os.path.splitext(os.path.basename(p))[0]
                for p in glob.glob(os.path.join(sessions_dir, "*.dt"))
            )

        levels.append({
            "id": entry,
            "name": name,
            "dir": level_dir,
            "has_general": os.path.exists(general_path),
            "general_path": general_path,
            "sessions": sessions,
            "sessions_dir": sessions_dir,
        })
    return levels


def load_json(path: str) -> dict:
    import json
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _prompt_choice(prompt: str, options: list[str]) -> int:
    """显示选项并让用户选择，返回索引

    输入序号直接选择；输入非序号则按子串搜索匹配项，
    唯一匹配时直接选中，多个匹配时列出匹配项 (带原列表序号) 重新选择。
    """
    print(prompt)
    for i, opt in enumerate(options, 1):
        print(f"  {i}. {opt}")

    while True:
        raw = input("请输入序号 (或搜索关键字): ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return int(raw) - 1

        # 按子串搜索 (在完整列表中)
        matches = [i for i, opt in enumerate(options) if raw.lower() in opt.lower()]
        if len(matches) == 1:
            idx = matches[0]
            print(f"  匹配到: {idx + 1}. {options[idx]}")
            return idx
        if len(matches) > 1:
            print(f"  找到 {len(matches)} 个匹配项:")
            for idx in matches:
                print(f"  {idx + 1}. {options[idx]}")
            continue
        print(f"  无匹配项，请输入 1-{len(options)} 或搜索关键字")


def main(levels_dir: str, out_dir: str) -> None:
    # 关卡选择
    levels = _scan_levels(levels_dir)
    if not levels:
        print(f"未在 '{levels_dir}' 找到任何带 metadata 的关卡")
        return

    options = [f"{lv['name']}  [{lv['id']}]" for lv in levels]
    idx = _prompt_choice(f"\n找到 {len(levels)} 个关卡:", options)
    level = levels[idx]
    print(f"\n已选择: {level['name']} [{level['id']}]")

    # main / session 选择
    data_options = []
    data_paths = []
    if level["has_general"]:
        data_options.append("main (general.dt)")
        data_paths.append(level["general_path"])
    for s in level["sessions"]:
        data_options.append(f"session {_session_timestamp(s + '.dt')} ({s})")
        data_paths.append(os.path.join(level["sessions_dir"], s + ".dt"))

    if not data_options:
        print("该关卡没有可分析的数据文件")
        return

    didx = _prompt_choice("\n选择要分析的数据:", data_options)
    data_path = data_paths[didx]
    print(f"\n分析: {data_path}\n")

    process_file(data_path, out_dir)


if __name__ == "__main__":
    levels_dir = sys.argv[1] if len(sys.argv) > 1 else ""
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "."

    if not levels_dir:
        levels_dir = _find_default_levels()
        if not levels_dir:
            print("未能在默认存档位置找到 death_tracker levels 目录。")
            print("已搜索以下 GD 存档目录:")
            for gd in _default_gd_save_dirs():
                print(f"  {gd}")
            print("\n请手动传入 levels 目录:")
            print("  python3 interactive.py <levels目录> [输出目录]")
            sys.exit(1)
        print(f"自动定位 levels 目录: {levels_dir}")

    main(levels_dir, out_dir)
