#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
向僵尸开炮 - 自动闯关脚本（主入口 · 编排层）

只负责整体流程编排：解析参数 → 连接设备 → 选择模式 → 运行主循环 → 收尾。
  - 参数从哪来          → cli.py（命令行 / 交互菜单）
  - 每个界面怎么处理    → handlers.py（表驱动分派）
"""

import time
import os
import sys

from version import __version__

import config
from config import *
import device
import vision
import states
import patrol
import cli
from handlers import (
    BATTLE_HANDLERS,
    UI_HANDLERS,
    CONTINUE,
    LoopContext,
    _dispatch,
    _log,
)


# ============================================================
#  主循环（流程编排）
# ============================================================

def main():
    config.EMULATOR_TYPE = cli.parse_args()
    emulator_display = {"mumu": "MuMu", "ldplayer": "雷电", "auto": "自动检测"}.get(
        config.EMULATOR_TYPE, config.EMULATOR_TYPE)

    print("=" * 55)
    print(f"   向僵尸开炮 · 自动闯关脚本 v{__version__}")
    print("=" * 55)
    print(f"  模拟器: {emulator_display}（可用参数: mumu / leidian）")
    strategy_display = config.SKILL_STRATEGY
    if config.SKILL_STRATEGY == "priority":
        strategy_display = f"priority（已配置{len(config.SKILL_PRIORITIES)}个词条）"
    print(f"  策略 : 技能选 {strategy_display}")
    print(f"  鸡腿停止阈值: {config.STOP_STAMINA_THRESHOLD}")
    print("  停止 : Ctrl+C")
    print("-" * 55)

    print("[1/3] 检测并连接 ADB ...")
    adb_path, device_addr, emulator_name = device.init_adb()

    print("[2/3] 模拟器分辨率: ", end="")
    config.screen_w, config.screen_h = device.get_screen_size()
    print(f"{config.screen_w}×{config.screen_h}")

    print("[3/3] 验证截图 ...")
    test = device.screenshot()
    if test is None:
        print("❌ 截图失败，请检查 ADB 连接")
        return
    print(f"      截图尺寸: {test.size}")
    print("-" * 55)
    print(f"✅ 启动成功！模拟器: {emulator_name}，开始自动闯关\n")

    if config.MODE == "patrol":
        print("🚓 进入快速巡逻模式")
        try:
            patrol.run_quick_patrol()
        except patrol.OutOfStamina:
            print("🍗 体力（鸡腿）不足，停止脚本")
            sys.exit(config.OUT_OF_STAMINA_EXIT)
        except patrol.BagFull:
            print("🎒 背包已满，停止脚本")
            sys.exit(config.BAG_FULL_EXIT)
        return

    ctx = LoopContext()
    config.in_battle_loop = False

    try:
        while True:
            t0 = time.time()
            img = device.screenshot()
            screenshot_time = time.time() - t0
            if img is None:
                _log("❌ 截图失败，1秒后重试")
                time.sleep(1)
                continue

            t1 = time.time()
            if config.in_battle_loop:
                ocr_result = vision.ocr_battle_loop(img)
            else:
                ocr_result = vision.ocr_screenshot(img)
            ocr_time = time.time() - t1
            text_count = len(ocr_result) if ocr_result else 0
            _log(f"📸 截图{screenshot_time:.1f}s + 🔍 OCR{ocr_time:.1f}s({text_count}字)")

            # 注：鸡腿(体力)不足判断已移至 关卡选择(_on_level_select) 处理器、点开始游戏之前

            if not config.in_battle_loop:
                if (states.is_victory_settlement(img) or states.is_skill_select(img) or
                        states.is_elite_drop(img) or states.is_battling(img)):
                    config.in_battle_loop = True
                    _log("🔄 检测到游戏循环界面，自动切换到游戏循环中")

            if config.in_battle_loop:
                # 战斗加载阶段(just_started 起 3 秒内)豁免"未检测波次跳出"；
                # 加载完成后必须复位 just_started，否则跳出保护会被永久屏蔽
                if ctx.just_started and time.time() - ctx.just_start_time >= 3:
                    ctx.just_started = False
                if not ctx.just_started and config._wave_miss_count >= 3:
                    miss_cnt = config._wave_miss_count
                    config.in_battle_loop = False
                    config._wave_miss_count = 0
                    _log(f"🔄 连续{miss_cnt}次未检测到波次，自动跳出游戏循环")
                    continue
                result = _dispatch(BATTLE_HANDLERS, ctx, img)
            else:
                result = _dispatch(UI_HANDLERS, ctx, img)

            if result is CONTINUE:
                # 处理器要求直接进入下一轮（等价于原来的 continue 语义）
                continue

            if config.in_battle_loop:
                time.sleep(BATTLE_LOOP_INTERVAL)
            else:
                time.sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:
        print("\n" + "=" * 55)
        print("  脚本已停止")
        print(f"  本次运行: 选技能 {ctx.skill_cnt} 次 | 通关 {ctx.level_cnt} 关 | 关弹窗 {ctx.popup_cnt} 次")
        print("=" * 55)
    except Exception as e:
        print(f"\n❌ 运行出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)  # 非0退出码：交给启动器按契约判定为「崩溃→重启」
    finally:
        if os.path.exists(SCREENSHOT_LOCAL):
            try:
                os.remove(SCREENSHOT_LOCAL)
            except Exception:
                pass


if __name__ == "__main__":
    main()
