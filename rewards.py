#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
奖励与关卡操作（双倍奖励、宝箱领取、胜利结算、关卡切换）

依赖：config、device（tap/screenshot/close_with_verify）、vision（OCR 检索）、
      states（判定）、popups（关闭奖励弹窗）。
"""

import time
import re

import config
from config import *
import device
import vision
import states


def get_today_remaining_count():
    """解析今日剩余双倍奖励次数，返回 (当前次数, 总次数) 或 None"""
    result = config._current_ocr_result
    if result is None:
        return None
    for item in result:
        box, text, confidence = item
        if "今日剩余次数" in text:
            numbers = re.findall(r'\d+', text)
            if len(numbers) >= 2:
                return (int(numbers[0]), int(numbers[1]))
            elif len(numbers) == 1:
                num_str = numbers[0]
                if len(num_str) >= 2:
                    current = int(num_str[0])
                    total = int(num_str[-1])
                    return (current, total)
                return (int(num_str), None)
    return None


def should_click_double_reward():
    """是否应该点击双倍奖励按钮（双倍奖励按钮 + 完美通关 + 剩余次数>0）"""
    double_reward_pos = vision.find_text("双倍奖励", min_confidence=0.3)
    if not double_reward_pos:
        return False
    if not vision.has_text("完美通关", region=(300, 200, 780, 350), min_confidence=0.5):
        return False
    remaining = get_today_remaining_count()
    if remaining is None:
        return False
    current_count, _ = remaining
    if current_count <= 0:
        return False
    return True


def claim_unclaimed_reward():
    """点击"未领取"按钮领取奖励，返回 True=点击成功"""
    pos = vision.get_text_position("未领取", region=(0, 1300, 200, 1500), min_confidence=0.3)
    if pos is None:
        pos = vision.get_text_position("末领取", region=(0, 1300, 200, 1500), min_confidence=0.3)
    if pos is None:
        return False
    tap_x = pos[0]
    tap_y = pos[1] - 60
    print(f"    → 点击'未领取'按钮 ({tap_x}, {tap_y})")
    device.tap((tap_x, tap_y))
    time.sleep(2)
    return True


def click_next_level():
    """点击右箭头，跳到下一关"""
    device.tap(NEXT_LEVEL_BTN)
    time.sleep(1.5)
    print(f"    → 点击右箭头，跳到下一关")


def claim_all_chests(img):
    """一键领取所有未领取的通关宝箱（点最右边发光宝箱），返回 True=点击了宝箱。

    只点【发光】的宝箱——发光即代表"已达成且未领取"，精准命中，一次点击解决。
    不做按文字位置的无谓点击：未通关的宝箱点了是空操作，还会弹出"奖励预览"面板干扰界面。
    """
    glowing = states.get_glowing_chests(img)
    if not glowing:
        print(f"    → 没有发光的宝箱，无需领取")
        return False
    target_chest = glowing[-1]
    click_pos = CHEST_CLICK_POSITIONS[target_chest]
    print(f"    🎁 检测到{len(glowing)}个发光宝箱: {glowing}")
    print(f"    → 点击[{target_chest}] 原始坐标{click_pos}（分辨率{config.screen_w}×{config.screen_h}）")
    device.tap(click_pos)
    time.sleep(1.5)
    for wait_idx in range(5):
        img_reward = device.screenshot()
        if img_reward is None:
            time.sleep(0.5)
            continue
        # has_text 读的是 OCR 缓存：必须先对新截图做 OCR 刷新，否则判定用的是旧缓存
        vision.ocr_screenshot(img_reward)
        if states.is_reward_popup(img_reward):
            print(f"    → 检测到奖励展示界面，点击关闭（第{wait_idx + 1}次）")
            device.close_with_verify(REWARD_POPUP_CLOSE_BTN, states.is_reward_popup, "奖励展示")
            break
        time.sleep(0.5)
    else:
        print(f"    → 未检测到奖励展示界面，继续")
    return True


def do_victory():
    """通关流程：判断双倍奖励，最后点返回（宝箱在选关页由 claim_all_chests 领取）"""
    should_double = should_click_double_reward()
    if should_double:
        double_reward_pos = vision.find_text("双倍奖励", min_confidence=0.3)
        if double_reward_pos:
            remaining = get_today_remaining_count()
            remaining_str = f"{remaining[0]}/{remaining[1]}" if remaining else "未知"
            print(f"    → 完美通关 + 双倍奖励(剩余{remaining_str})，先点击双倍奖励 {double_reward_pos}")
            device.tap(double_reward_pos)
            time.sleep(2)
            img = device.screenshot()
            if img is not None:
                vision.ocr_screenshot(img)
    else:
        if not vision.has_text("完美通关", region=(300, 200, 780, 350), min_confidence=0.5):
            print(f"    → 非完美通关，跳过双倍奖励，直接点返回")
        else:
            remaining = get_today_remaining_count()
            if remaining and remaining[0] <= 0:
                remaining_str = f"{remaining[0]}/{remaining[1]}" if remaining[1] else str(remaining[0])
                print(f"    → 双倍奖励次数已用完({remaining_str})，跳过双倍奖励，直接点返回")
            elif not vision.find_text("双倍奖励", min_confidence=0.3):
                print(f"    → 未检测到双倍奖励按钮，直接点返回")
            else:
                print(f"    → 不满足双倍奖励条件，直接点返回")

    return_pos = vision.get_text_position("返回", region=VICTORY_RETURN_REGION, min_confidence=0.5)
    if return_pos:
        print(f"    → OCR识别到「返回」按钮位置 {return_pos}，点击返回")
        device.tap(return_pos)
    else:
        fallback_pos = VICTORY_RETURN_FALLBACK
        print(f"    ⚠ OCR未识别到「返回」按钮，用兜底位置 {fallback_pos}")
        device.tap(fallback_pos)
    time.sleep(2)
