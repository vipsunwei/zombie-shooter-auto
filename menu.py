#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
启动菜单（交互式入口引导）

包含通用上下箭头选择菜单，以及三个具体入口菜单：
  - select_emulator_interactive   模拟器选择（默认自动检测 auto）
  - select_mode_interactive        运行模式选择（默认闯关 battle）
  - prompt_stamina_interactive     鸡腿(体力)停止阈值输入（默认 50，仅数字）
"""

import sys

import config


def enable_ansi_escape():
    """启用 Windows 控制台 ANSI 转义码支持"""
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        return True
    except Exception:
        return False


def _arrow_select(title, options, default_index=0):
    """通用上下箭头选择菜单。

    options: (value, display) 列表；default_index: 默认高亮项索引。
    返回所选 value（回车确认，Ctrl+C 取消退出）。
    """
    import msvcrt
    enable_ansi_escape()
    selected = default_index
    print("\n" + "=" * 45)
    print(f"  {title}（上下箭头选择，回车确认）")
    print("=" * 45)
    while True:
        for i, (key, display) in enumerate(options):
            if i == selected:
                print(f"  ▶ {display}")
            else:
                print(f"    {display}")
        print("=" * 45)
        key = msvcrt.getch()
        if key == b'\xe0':
            key = msvcrt.getch()
            if key == b'H':
                selected = (selected - 1) % len(options)
            elif key == b'P':
                selected = (selected + 1) % len(options)
        elif key == b'\r':
            value = options[selected][0]
            print(f"\n✅ 已选择: {options[selected][1]}")
            return value
        elif key == b'\x03':
            print("\n\n已取消选择")
            sys.exit(0)
        print(f"\033[{len(options) + 1}A", end="", flush=True)


def select_emulator_interactive():
    """交互式选择模拟器，默认自动检测(auto)，回车确认"""
    options = [
        ("auto", "自动检测（默认）"),
        ("mumu", "MuMu 模拟器"),
        ("ldplayer", "雷电模拟器"),
    ]
    return _arrow_select("请选择模拟器", options, default_index=0)


def select_mode_interactive():
    """交互式选择运行模式，默认闯关(battle)，回车确认"""
    options = [
        ("battle", "闯关（默认）"),
        ("patrol", "巡逻车（快速巡逻）"),
    ]
    return _arrow_select("请选择运行模式", options, default_index=0)


def prompt_stamina_interactive():
    """交互输入鸡腿(体力)停止阈值，回车默认 50，只接受正整数"""
    default = config.STOP_STAMINA_THRESHOLD
    while True:
        try:
            raw = input(f"\n请输入剩余鸡腿（体力）低于多少时停止脚本 [{default}]: ").strip()
        except EOFError:
            return default
        except KeyboardInterrupt:
            print("\n\n已取消")
            sys.exit(0)
        if raw == "":
            return default
        try:
            n = int(raw)
        except ValueError:
            print("❌ 只可以输入数字，请重新输入")
            continue
        if n <= 0:
            print("❌ 请输入大于 0 的数字")
            continue
        return n
