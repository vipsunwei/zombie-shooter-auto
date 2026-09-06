#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
弹窗关闭逻辑（所有 close_* + 通用点击空白关闭）

依赖：config、device（tap/screenshot）、vision（OCR 缓存更新）、states（判定）、skills（精英掉落后选技能）。
"""

import time

import config
from config import *
import device
import vision
import states
import skills


def close_level_detail_popup():
    """关闭关卡详情弹窗：点击右上角×按钮，验证式关闭"""
    close_pos = LEVEL_DETAIL_CLOSE_BTN
    for attempt in range(1, 3):
        print(f"    → 第{attempt}次点击右上角×关闭关卡详情弹窗 {close_pos}")
        device.tap(close_pos)
        time.sleep(1)
        img = device.screenshot()
        if img is None:
            continue
        vision.ocr_screenshot(img)
        if not states.is_level_detail_popup(img):
            print(f"    ✅ 关卡详情弹窗已关闭，停止操作")
            return True
        print(f"    ⚠ 弹窗仍在，准备重试")
    print(f"    ❌ 关卡详情弹窗多次尝试未关闭，跳过（下轮循环再处理）")
    return False


def close_reward_popup():
    """关闭奖励界面（点击 (850,1684) 空白关闭区，连点两次间隔1s，安全无副作用）。"""
    tap_pos = REWARD_CLOSE_BTN
    device.tap(tap_pos)
    time.sleep(1)
    device.tap(tap_pos)
    print(f"    ✅ 已点击奖励关闭区 {tap_pos} 两次")
    return True


def click_blank_to_close():
    """通用关闭：点击弹窗外空白区域关闭（巡逻车/扫荡等带"点击空白处关闭"提示的界面）"""
    blank_pos = BLANK_CLOSE_BTN
    for attempt in range(1, 3):
        print(f"    → 第{attempt}次点击开始按钮右侧空白区域 {blank_pos}")
        device.tap(blank_pos)
        time.sleep(1)
        img = device.screenshot()
        if img is None:
            continue
        vision.ocr_screenshot(img)
        if not states.has_click_blank_hint(img):
            print(f"    ✅ 界面已关闭，停止操作")
            return True
        print(f"    ⚠ 界面仍在，准备重试")
    print(f"    ❌ 多次尝试未关闭，跳过（下轮循环再处理）")
    return False


def close_patrol():
    """关闭巡逻/扫荡界面：使用通用的"点击空白处关闭"逻辑"""
    return click_blank_to_close()


def close_level_up():
    """关闭等级提升界面：点击底部"点击屏幕继续"位置，验证式关闭"""
    tap_pos = LEVEL_UP_CLOSE_BTN
    for attempt in range(1, 3):
        print(f"    → 第{attempt}次点击底部「点击屏幕继续」 {tap_pos}")
        device.tap(tap_pos)
        time.sleep(1)
        img = device.screenshot()
        if img is None:
            continue
        vision.ocr_screenshot(img)
        if not states.is_level_up(img):
            print(f"    ✅ 等级提升界面已关闭，停止操作")
            return True
        print(f"    ⚠ 等级提升界面仍在，准备重试")
    print(f"    ❌ 等级提升界面多次尝试未关闭，跳过（下轮循环再处理）")
    return False


def close_activity_center():
    """关闭活动中心界面：点击右上角×关闭按钮，验证式关闭"""
    for attempt in range(1, 3):
        print(f"    → 第{attempt}次点活动中心关闭按钮 {ACTIVITY_CENTER_CLOSE_BTN}")
        device.tap(ACTIVITY_CENTER_CLOSE_BTN)
        time.sleep(1)
        img = device.screenshot()
        if img is None:
            continue
        vision.ocr_screenshot(img)
        if not states.is_activity_center(img):
            print(f"    ✅ 活动中心已关闭，停止操作")
            return True
        print(f"    ⚠ 活动中心仍在，准备重试")
    print(f"    ❌ 活动中心多次尝试未关闭，跳过（下轮循环再处理）")
    return False


def close_elite_drop():
    """关闭精英掉落界面：点左下角快速结束转盘，确认仍在则再点关闭"""
    ELITE_TAP = REWARD_BOTTOM_BTN
    device.tap(ELITE_TAP)
    print(f"    → 第1次点左下角结束转盘 {ELITE_TAP}")
    time.sleep(1.5)
    img = device.screenshot()
    if img is not None:
        vision.ocr_screenshot(img)
    if not states.is_elite_drop(img):
        if states.is_skill_select(img):
            print(f"    ✅ 精英掉落已关闭，检测到选择技能界面，直接选择词条")
            pos_name, pos_coord, left_name, middle_name, right_name, reason, _, _ = skills.do_select_skill()
            if left_name or middle_name or right_name:
                print(f"    → 左[{left_name}] 中[{middle_name}] 右[{right_name}]")
            print(f"    → 已选择{pos_name}卡片{pos_coord}，原因：{reason}")
        else:
            print(f"    ✅ 转盘结束后精英掉落已关闭，无需第二次点击")
        return True
    print(f"    → 确认仍在精英掉落界面，第2次点左下角关闭 {ELITE_TAP}")
    device.tap(ELITE_TAP)
    time.sleep(0.8)
    img = device.screenshot()
    if img is not None:
        vision.ocr_screenshot(img)
    if not states.is_elite_drop(img):
        print(f"    ✅ 精英掉落已关闭，停止操作")
        return True
    print(f"    ⚠ 精英掉落仍在，再点一次左下角")
    device.tap(ELITE_TAP)
    time.sleep(0.8)
    img = device.screenshot()
    if img is not None:
        vision.ocr_screenshot(img)
    if not states.is_elite_drop(img):
        print(f"    ✅ 精英掉落已关闭，停止操作")
        return True
    print(f"    ❌ 精英掉落多次尝试未关闭，跳过（下轮循环再处理）")
    return False


def close_auto_close_popup():
    """关闭已激活技能弹窗：点击左下角直接关闭，验证式关闭"""
    tap_pos = REWARD_BOTTOM_BTN
    for attempt in range(1, 3):
        print(f"    → 第{attempt}次点击左下角关闭已激活技能弹窗 {tap_pos}")
        device.tap(tap_pos)
        time.sleep(1)
        img = device.screenshot()
        if img is None:
            continue
        vision.ocr_screenshot(img)
        if not states.is_auto_close_popup(img):
            print(f"    ✅ 已激活技能弹窗已关闭，停止操作")
            return True
        print(f"    ⚠ 弹窗仍在，准备重试")
    print(f"    ❌ 已激活技能弹窗多次尝试未关闭，跳过（下轮循环再处理）")
    return False


def close_reconnect_failed_popup():
    """关闭"重连失败断开连接"弹窗：点击"确定"按钮，验证式关闭"""
    tap_pos = RECONNECT_FAIL_BTN
    for attempt in range(1, 3):
        print(f"    → 第{attempt}次点击确定按钮关闭重连失败弹窗 {tap_pos}")
        device.tap(tap_pos)
        time.sleep(1)
        img = device.screenshot()
        if img is None:
            continue
        vision.ocr_screenshot(img)
        if not states.is_reconnect_failed_popup(img):
            print(f"    ✅ 重连失败弹窗已关闭，停止操作")
            return True
        print(f"    ⚠ 弹窗仍在，准备重试")
    print(f"    ❌ 重连失败弹窗多次尝试未关闭，跳过（下轮循环再处理）")
    return False
