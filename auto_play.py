#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
向僵尸开炮 - 自动闯关脚本（主入口）

组合各模块：device（设备控制）、vision（OCR）、states（界面判定）、
popups（弹窗关闭）、skills（词条选择）、rewards（奖励/关卡），运行主循环。

使用方法：
  python auto_play.py              # 默认 MuMu
  python auto_play.py mumu         # 指定 MuMu
  python auto_play.py leidian / ld # 指定雷电
  python auto_play.py auto         # 自动检测
  python auto_play.py --help
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
import popups
import skills
import rewards
import patrol


# ============================================================
#  命令行参数解析（入口辅助）
# ============================================================

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
    无 --emulator 时弹出交互式选择菜单。
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
  python auto_play.py                            # 弹出选择菜单（上下箭头选择模拟器）
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
    emulator = None
    i = 0
    while i < len(args):
        arg = args[i]
        if arg.startswith("--mode="):
            mode = _validate_mode(arg.split("=", 1)[1])
        elif arg in ("-m", "--mode"):
            if i + 1 >= len(args):
                print("❌ --mode/-m 缺少参数")
                sys.exit(1)
            mode = _validate_mode(args[i + 1])
            i += 1
        elif arg.startswith("-m="):
            mode = _validate_mode(arg.split("=", 1)[1])
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
        elif arg in ("-s", "--min-stamina"):
            if i + 1 >= len(args):
                print("❌ --min-stamina/-s 缺少参数")
                sys.exit(1)
            config.STOP_STAMINA_THRESHOLD = _validate_stamina(args[i + 1])
            i += 1
        elif arg.startswith("-s="):
            config.STOP_STAMINA_THRESHOLD = _validate_stamina(arg.split("=", 1)[1])
        elif arg.startswith("-"):
            print(f"❌ 未知参数: {arg}（仅支持 --emulator/-e / --mode/-m）")
            sys.exit(1)
        else:
            print(f"❌ 不支持位置参数: {arg}（请使用 --emulator/-e / --mode/-m）")
            sys.exit(1)
        i += 1

    config.MODE = mode
    if emulator is None:
        return select_emulator_interactive()
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


def enable_ansi_escape():
    """启用 Windows 控制台 ANSI 转义码支持"""
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        return True
    except Exception:
        return False


def select_emulator_interactive():
    """交互式选择模拟器（上下箭头选择，回车确认）"""
    import msvcrt
    enable_ansi_escape()
    options = [
        ("mumu", "MuMu 模拟器（默认推荐）"),
        ("ldplayer", "雷电模拟器"),
        ("auto", "自动检测"),
    ]
    selected = 0
    print("\n" + "=" * 45)
    print("  请选择模拟器（上下箭头选择，回车确认）")
    print("=" * 45)
    menu_start_line = 4
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
            emulator_type = options[selected][0]
            print(f"\n✅ 已选择: {options[selected][1]}")
            return emulator_type
        elif key == b'\x03':
            print("\n\n已取消选择")
            sys.exit(0)
        print(f"\033[{len(options) + 1}A", end="", flush=True)


# ============================================================
#  主循环
# ============================================================

def main():
    config.EMULATOR_TYPE = parse_args()
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

    skill_cnt = 0
    level_cnt = 0
    popup_cnt = 0
    unknown_cnt = 0
    last_status = ""
    just_started = False
    just_start_time = 0
    config.in_battle_loop = False

    try:
        while True:
            t0 = time.time()
            img = device.screenshot()
            screenshot_time = time.time() - t0
            if img is None:
                print(f"[{time.strftime('%H:%M:%S')}] ❌ 截图失败，1秒后重试")
                time.sleep(1)
                continue

            t1 = time.time()
            if config.in_battle_loop:
                ocr_result = vision.ocr_battle_loop(img)
            else:
                ocr_result = vision.ocr_screenshot(img)
            ocr_time = time.time() - t1
            text_count = len(ocr_result) if ocr_result else 0
            print(f"[{time.strftime('%H:%M:%S')}] 📸 截图{screenshot_time:.1f}s + 🔍 OCR{ocr_time:.1f}s({text_count}字)")

            # 注：鸡腿(体力)不足判断已移至下方 关卡选择(is_level_select) 分支、点开始游戏之前

            status = "战斗中"

            if not config.in_battle_loop:
                if (states.is_victory_settlement(img) or states.is_skill_select(img) or
                        states.is_elite_drop(img) or states.is_battling(img)):
                    config.in_battle_loop = True
                    print(f"[{time.strftime('%H:%M:%S')}] 🔄 检测到游戏循环界面，自动切换到游戏循环中")

            if config.in_battle_loop:
                # 战斗加载阶段(just_started 起 3 秒内)豁免"未检测波次跳出"；
                # 加载完成后必须复位 just_started，否则跳出保护会被永久屏蔽
                if just_started and time.time() - just_start_time >= 3:
                    just_started = False
                if not just_started and config._wave_miss_count >= 3:
                    status = "已离开游戏界面"
                    miss_cnt = config._wave_miss_count
                    config.in_battle_loop = False
                    config._wave_miss_count = 0
                    print(f"[{time.strftime('%H:%M:%S')}] 🔄 连续{miss_cnt}次未检测到波次，自动跳出游戏循环")
                    continue

                if states.is_auto_close_popup(img):
                    status = "已激活技能弹窗"
                    print(f"[{time.strftime('%H:%M:%S')}] ⚡ 检测到已激活技能弹窗（秒后自动关闭）→ 点击左下角直接关闭")
                    popups.close_auto_close_popup()
                    popup_cnt += 1
                    unknown_cnt = 0
                elif states.is_reconnect_failed_popup(img):
                    status = "重连失败弹窗"
                    print(f"[{time.strftime('%H:%M:%S')}] 🔌 检测到重连失败断开连接弹窗 → 点击确定按钮关闭")
                    popups.close_reconnect_failed_popup()
                    popup_cnt += 1
                    unknown_cnt = 0
                elif states.is_victory_settlement(img):
                    status = "通关结算"
                    level_cnt += 1
                    config.in_battle_loop = False
                    print(f"[{time.strftime('%H:%M:%S')}] 🏆 第 {level_cnt} 关通关！→ 点击返回，跳出游戏循环")
                    rewards.do_victory()
                    if CLEAN_SCREENSHOT_PER_LEVEL:
                        device.clean_screenshots()
                        print(f"[{time.strftime('%H:%M:%S')}] 🧹 已清理本关截图")
                    unknown_cnt = 0
                elif states.is_skill_select(img):
                    status = "选择技能"
                    pos_name, pos_coord, left_name, middle_name, right_name, reason, selected_name, selected_score = skills.do_select_skill()
                    skill_cnt += 1
                    if left_name or middle_name or right_name:
                        if selected_score > 0:
                            print(f"[{time.strftime('%H:%M:%S')}] ⚡ 选择技能 [{left_name}|{middle_name}|{right_name}] → 选[{selected_name}]，优先级({selected_score})")
                        else:
                            print(f"[{time.strftime('%H:%M:%S')}] ⚡ 选择技能 [{left_name}|{middle_name}|{right_name}] → 选[{selected_name}]，随机选择")
                    else:
                        print(f"[{time.strftime('%H:%M:%S')}] ⚡ 选择技能 → 选[{selected_name}]，随机选择")
                    time.sleep(1.2)
                    unknown_cnt = 0
                elif states.is_elite_drop(img):
                    status = "精英掉落"
                    print(f"[{time.strftime('%H:%M:%S')}] 🎁 精英掉落")
                    popups.close_elite_drop()
                    unknown_cnt = 0
                else:
                    back_pos = vision.find_text("返回", min_confidence=0.5)
                    if not back_pos:
                        status = "战斗中"
                        unknown_cnt = 0
                    else:
                        print(f"[{time.strftime('%H:%M:%S')}] 🏁 检测到返回按钮{back_pos}，进入结算处理")
                        if states.is_victory(img):
                            print(f"[{time.strftime('%H:%M:%S')}] 🏆 检测到通关结算界面，处理结算")
                            rewards.do_victory()
                            if CLEAN_SCREENSHOT_PER_LEVEL:
                                device.clean_screenshots()
                                print(f"[{time.strftime('%H:%M:%S')}] 🧹 已清理本关截图")
                        else:
                            print(f"[{time.strftime('%H:%M:%S')}] ↩️  未检测到通关结算界面，直接点击返回按钮 {back_pos}")
                            device.tap(back_pos)
                            time.sleep(1)
                        config.in_battle_loop = False
                        unknown_cnt = 0
            else:
                if states.is_reconnect_failed_popup(img):
                    status = "重连失败弹窗"
                    print(f"[{time.strftime('%H:%M:%S')}] 🔌 检测到重连失败断开连接弹窗 → 点击确定按钮关闭")
                    popups.close_reconnect_failed_popup()
                    popup_cnt += 1
                    unknown_cnt = 0
                elif states.is_pay_popup(img):
                    status = "付费弹窗"
                    print(f"[{time.strftime('%H:%M:%S')}] 💰 付费/见面豪礼弹窗")
                    device.close_with_verify(CLOSE_POPUP, states.is_pay_popup, "付费弹窗")
                    popup_cnt += 1
                    unknown_cnt = 0
                elif states.is_activity_popup(img):
                    status = "活动弹窗"
                    print(f"[{time.strftime('%H:%M:%S')}] 📅 本周活动弹窗")
                    device.close_with_verify(CLOSE_POPUP3, states.is_activity_popup, "活动弹窗")
                    popup_cnt += 1
                    unknown_cnt = 0
                elif states.is_level_detail_popup(img):
                    status = "关卡详情弹窗"
                    print(f"[{time.strftime('%H:%M:%S')}] 📋 关卡详情弹窗 → 点击右上角×关闭")
                    popups.close_level_detail_popup()
                    popup_cnt += 1
                    unknown_cnt = 0
                elif states.is_reward_popup(img):
                    status = "奖励展示"
                    print(f"[{time.strftime('%H:%M:%S')}] 🎉 奖励展示界面 → 点击左下角关闭")
                    popups.close_reward_popup()
                    unknown_cnt = 0
                elif states.has_click_blank_hint(img):
                    status = "点击空白关闭"
                    print(f"[{time.strftime('%H:%M:%S')}] 🖱️ 检测到「点击空白处关闭」提示 → 点击关闭")
                    popups.click_blank_to_close()
                    unknown_cnt = 0
                elif states.is_activity_center(img):
                    status = "活动中心"
                    print(f"[{time.strftime('%H:%M:%S')}] 🎪 活动中心界面 → 点右上角×关闭")
                    popups.close_activity_center()
                    unknown_cnt = 0
                elif states.is_level_up(img):
                    status = "等级提升"
                    print(f"[{time.strftime('%H:%M:%S')}] ⬆️ 等级提升界面 → 点击屏幕继续")
                    popups.close_level_up()
                    unknown_cnt = 0
                elif states.is_patrol(img):
                    status = "巡逻界面"
                    print(f"[{time.strftime('%H:%M:%S')}] 🚶 巡逻/扫荡界面 → 点击空白处关闭")
                    popups.close_patrol()
                    unknown_cnt = 0
                elif states.is_unclaimed_reward(img):
                    status = "未领取奖励"
                    print(f"[{time.strftime('%H:%M:%S')}] 🎁 检测到'未领取'按钮 → 点击领取")
                    rewards.claim_unclaimed_reward()
                    img2 = device.screenshot()
                    if img2 is not None:
                        vision.ocr_screenshot(img2)
                        if states.is_reward_popup(img2):
                            print(f"    → 检测到奖励展示界面 → 关闭")
                            popups.close_reward_popup()
                    perfect_pos = None
                    for retry in range(3):
                        img3 = device.screenshot()
                        if img3 is not None:
                            vision.ocr_screenshot(img3)
                            if retry == 0:
                                print(f"    → 在下半部分检测完美通关宝箱...")
                            perfect_pos = states.is_claimable_chest("完美通关")
                            if perfect_pos:
                                break
                            else:
                                print(f"    → 第{retry + 1}次未识别到完美通关文字，{0.5 if retry < 2 else 0}秒后重试...")
                                time.sleep(0.5)
                        else:
                            break
                    if perfect_pos:
                        print(f"    → 识别到完美通关文字，宝箱位置 {perfect_pos}，点击领取")
                        device.tap(perfect_pos)
                        time.sleep(2)
                        img4 = device.screenshot()
                        if img4 is not None:
                            vision.ocr_screenshot(img4)
                            if states.is_reward_popup(img4):
                                print(f"    → 检测到奖励展示界面 → 关闭")
                                popups.close_reward_popup()
                            else:
                                print(f"    → 未弹出奖励界面（可能已领取）")
                    else:
                        print(f"    → 多次重试仍未识别到完美通关文字（可能已领取或OCR未识别）")
                    unknown_cnt = 0
                elif states.is_perfect_clear(img):
                    status = "完美通关"
                    print(f"[{time.strftime('%H:%M:%S')}] ✅ 当前关卡已完美通关 → 点击右箭头跳到下一关")
                    rewards.click_next_level()
                    unknown_cnt = 0
                elif states.is_level_list(img):
                    status = "关卡列表"
                    print(f"[{time.strftime('%H:%M:%S')}] 📋 关卡列表 → 点选择进入单关选择")
                    device.tap(REWARD_POPUP_CLOSE_BTN)
                    time.sleep(1.5)
                    unknown_cnt = 0
                elif states.is_level_select(img):
                    status = "关卡选择"
                    if rewards.claim_all_chests(img):
                        time.sleep(1)
                        unknown_cnt = 0
                        continue
                    # 点开始游戏前：先确认"开始游戏"按钮确实在界面上、能定位到
                    start_pos = vision.get_text_position(
                        "开始游戏", region=(300, 1480, 780, 1680), min_confidence=0.1)
                    if start_pos is None:
                        print(f"    ⚠ 未定位到「开始游戏」按钮（可能并非关卡选择界面或OCR未识别），本轮回退重试")
                        unknown_cnt = 0
                        continue
                    # 点开始游戏前判断鸡腿是否足够开下一关；不足则停止脚本（游戏循环中不判断）
                    stamina = states.get_stamina(img)
                    if stamina is not None and stamina < config.STOP_STAMINA_THRESHOLD:
                        print(f"[{time.strftime('%H:%M:%S')}] 🍗 体力(鸡腿) {stamina} 不足 {config.STOP_STAMINA_THRESHOLD}，停止循环闯关")
                        device.click_bottom_nav("战斗")
                        time.sleep(1.5)
                        sys.exit(config.OUT_OF_STAMINA_EXIT)
                    config.in_battle_loop = True
                    print(f"[{time.strftime('%H:%M:%S')}] ▶ 关卡选择 → 点开始游戏{start_pos}，进入游戏循环")
                    device.tap(start_pos)
                    just_started = True
                    just_start_time = time.time()
                    print(f"    → 验证是否真正进入战斗界面（最多6秒）...")
                    entered_battle = False
                    for _ in range(12):  # 12 × 0.5s = 6s
                        time.sleep(0.5)
                        img_v = device.screenshot()
                        if img_v is None:
                            continue
                        vision.ocr_screenshot(img_v)  # 刷新OCR缓存，使文本判据基于当前帧
                        if states.is_battling(img_v):
                            entered_battle = True
                            break
                        if states.is_level_select(img_v) or states.is_level_list(img_v):
                            # 仍停在关卡选择页：点击未生效，重新点开始游戏并刷新加载计时
                            start_pos = vision.get_text_position(
                                "开始游戏", region=(300, 1480, 780, 1680), min_confidence=0.1)
                            if start_pos is None:
                                start_pos = START_BTN  # OCR未定位到则回退固定坐标
                            print(f"    → 仍在关卡选择页，重新点击开始游戏{start_pos}")
                            device.tap(start_pos)
                            just_started = True
                            just_start_time = time.time()
                            continue
                        if states.is_auto_close_popup(img_v):
                            print(f"    → 检测到已激活技能弹窗，点击左下角关闭")
                            popups.close_auto_close_popup()
                            continue
                        # 其余视为战斗加载/过渡画面，继续等待
                    if entered_battle:
                        print(f"    ✅ 已确认进入战斗界面")
                    else:
                        print(f"    ⚠ 未在限定时间内确认进入战斗，回退到关卡选择重试")
                        config.in_battle_loop = False
                        just_started = False
                    unknown_cnt = 0
                elif states.is_victory(img):
                    status = "通关"
                    level_cnt += 1
                    print(f"[{time.strftime('%H:%M:%S')}] 🏆 第 {level_cnt} 关通关！→ 点击返回")
                    rewards.do_victory()
                    if CLEAN_SCREENSHOT_PER_LEVEL:
                        device.clean_screenshots()
                        print(f"[{time.strftime('%H:%M:%S')}] 🧹 已清理本关截图")
                    unknown_cnt = 0
                elif states.is_battling(img):
                    status = "战斗中"
                    config.in_battle_loop = True
                    print(f"[{time.strftime('%H:%M:%S')}] ⚔ 检测到战斗中，自动进入游戏循环")
                    unknown_cnt = 0
                else:
                    if just_started and (time.time() - just_start_time < 3):
                        status = "战斗加载中"
                        unknown_cnt = 0
                    else:
                        just_started = False
                        selected_nav = device.get_selected_bottom_nav()
                        if selected_nav and selected_nav != "战斗":
                            status = f"底部导航-{selected_nav}"
                            print(f"[{time.strftime('%H:%M:%S')}] 🧭 底部导航当前选中「{selected_nav}」，点击「战斗」切换到战斗界面")
                            if device.click_bottom_nav("战斗"):
                                time.sleep(1.5)
                            unknown_cnt = 0
                        elif selected_nav == "战斗":
                            status = "战斗页面-加载中"
                            unknown_cnt = 0
                        else:
                            unknown_cnt += 1
                            status = f"未知界面({unknown_cnt})"
                            if unknown_cnt >= 8:
                                print(f"[{time.strftime('%H:%M:%S')}] ⚠ 连续{unknown_cnt}次未知界面，兜底点左下角返回按钮")
                                device.fallback_back()
                                unknown_cnt = 0

            last_status = status

            if config.in_battle_loop:
                time.sleep(BATTLE_LOOP_INTERVAL)
            else:
                time.sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:
        print("\n" + "=" * 55)
        print("  脚本已停止")
        print(f"  本次运行: 选技能 {skill_cnt} 次 | 通关 {level_cnt} 关 | 关弹窗 {popup_cnt} 次")
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
