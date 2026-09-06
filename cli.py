#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
命令行参数解析（入口辅助）

负责把「命令行参数 / 交互菜单」的输入，统一成 main 所需的运行参数：
模拟器类型、运行模式、鸡腿停止阈值。
"""

import sys

import config
import menu


def _normalize_emulator(emulator):
    """将用户输入的模拟器名称规范化为内部统一格式"""
    if emulator in ["leidian", "ld", "ldplayer", "雷电", "leidianplayer"]:
        return "ldplayer"
    elif emulator in ["mumu", "mu", "mumuplayer", "网易", "netease"]:
        return "mumu"
    elif emulator in ["auto", "自动", "auto_detect"]:
        return "auto"
    else:
        print(f"⚠ 未知模拟器类型: {emulator}，使用默认MuMu")
        return "mumu"


def parse_args():
    """解析命令行参数，返回模拟器类型字符串（内部统一用 mumu / ldplayer）。

    参数统一为显式 --option 风格，并支持单字母短选项：
      --emulator, -e <类型>      模拟器：mumu / leidian(或 ld) / auto（自动检测）
      --mode, -m <模式>          运行模式：battle（默认，循环闯关）/ patrol（快速巡逻）
      --min-stamina, -s <数量>   鸡腿(体力)低于此值即停止脚本（默认 50）
    无 --emulator 时弹出模拟器选择菜单；无 --mode 时弹出模式选择菜单；
    无 --min-stamina 时提示输入鸡腿停止阈值（默认 50）。任一项已通过命令行指定则跳过对应菜单。
    """
    args = sys.argv[1:]
    if "--help" in args or "-h" in args:
        print("""
向僵尸开炮 - 自动闯关脚本
==========================

用法:
  python auto_play.py [--emulator|-e <类型>] [--mode|-m <模式>] [--min-stamina|-s <数量>]

模拟器类型 (--emulator, -e):
  mumu         MuMu模拟器（默认）
  leidian      雷电模拟器（简写: ld）
  auto         自动检测

运行模式 (--mode, -m):
  battle       循环闯关（默认）
  patrol       快速巡逻

鸡腿停止阈值 (--min-stamina, -s):
  <数量>       自定义鸡腿不足停止线，例如 -s 80 表示剩 80 鸡腿即停（默认 50）

示例:
  python auto_play.py                            # 依次弹出：模拟器 / 模式 / 鸡腿停止阈值 菜单
  python auto_play.py --emulator mumu            # 指定 MuMu
  python auto_play.py --emulator leidian         # 指定雷电
  python auto_play.py --emulator auto            # 自动检测
  python auto_play.py --mode patrol              # 快速巡逻模式（长选项）
  python auto_play.py -m patrol                  # 快速巡逻模式（短选项）
  python auto_play.py -e auto -m patrol          # 短选项：自动检测 + 快速巡逻
  python auto_play.py -m patrol -s 80            # 自定义鸡腿停止阈值 80

其他参数:
  --help, -h    显示此帮助信息
        """)
        sys.exit(0)

    mode = "battle"
    mode_provided = False
    emulator = None
    stamina_provided = False
    i = 0
    while i < len(args):
        arg = args[i]
        if arg.startswith("--mode="):
            mode = _validate_mode(arg.split("=", 1)[1])
            mode_provided = True
        elif arg in ("-m", "--mode"):
            if i + 1 >= len(args):
                print("❌ --mode/-m 缺少参数")
                sys.exit(1)
            mode = _validate_mode(args[i + 1])
            mode_provided = True
            i += 1
        elif arg.startswith("-m="):
            mode = _validate_mode(arg.split("=", 1)[1])
            mode_provided = True
        elif arg.startswith("--emulator="):
            emulator = _normalize_emulator(arg.split("=", 1)[1])
        elif arg in ("-e", "--emulator"):
            if i + 1 >= len(args):
                print("❌ --emulator/-e 缺少参数")
                sys.exit(1)
            emulator = _normalize_emulator(args[i + 1])
            i += 1
        elif arg.startswith("-e="):
            emulator = _normalize_emulator(arg.split("=", 1)[1])
        elif arg.startswith("--min-stamina="):
            config.STOP_STAMINA_THRESHOLD = _validate_stamina(arg.split("=", 1)[1])
            stamina_provided = True
        elif arg in ("-s", "--min-stamina"):
            if i + 1 >= len(args):
                print("❌ --min-stamina/-s 缺少参数")
                sys.exit(1)
            config.STOP_STAMINA_THRESHOLD = _validate_stamina(args[i + 1])
            stamina_provided = True
            i += 1
        elif arg.startswith("-s="):
            config.STOP_STAMINA_THRESHOLD = _validate_stamina(arg.split("=", 1)[1])
            stamina_provided = True
        elif arg.startswith("-"):
            print(f"❌ 未知参数: {arg}（仅支持 --emulator/-e / --mode/-m / --min-stamina/-s）")
            sys.exit(1)
        else:
            print(f"❌ 不支持位置参数: {arg}（请使用 --emulator/-e / --mode/-m / --min-stamina/-s）")
            sys.exit(1)
        i += 1

    config.MODE = mode
    if emulator is None:
        emulator = menu.select_emulator_interactive()
    if not mode_provided:
        config.MODE = menu.select_mode_interactive()
    if not stamina_provided:
        config.STOP_STAMINA_THRESHOLD = menu.prompt_stamina_interactive()
    return emulator


def _validate_mode(mode):
    """校验运行模式参数，返回小写模式名；非法则报错退出"""
    mode = mode.lower()
    if mode not in ("battle", "patrol"):
        print(f"❌ 未知模式: {mode}（仅支持 battle / patrol）")
        sys.exit(1)
    return mode


def _validate_stamina(value):
    """校验自定义鸡腿停止阈值，返回正整数；非法则报错退出"""
    try:
        n = int(value)
    except ValueError:
        print(f"❌ 鸡腿阈值需为整数: {value}")
        sys.exit(1)
    if n <= 0:
        print(f"❌ 鸡腿阈值需为正整数: {value}")
        sys.exit(1)
    return n
