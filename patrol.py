#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速巡逻模式主循环（run_quick_patrol）

流程：切战斗 → 清弹窗 → 点巡逻车 → 点快速巡逻 → 关奖励 → 循环；
巡逻满12小时出现「领取」按钮时，先点领取再继续快速巡逻。

依赖：config、device、vision、states、popups、rewards（复用现有弹窗关闭链路）。
"""

import re
import time

import config
from config import *
import device
import vision
import states
import popups
import rewards


def _ts():
    return time.strftime("%H:%M:%S")


class OutOfStamina(Exception):
    """体力（鸡腿）不足，无法继续快速巡逻"""
    pass


class BagFull(Exception):
    """背包已满，无法继续快速巡逻领奖"""
    pass


def _close_all_popups(img):
    """关闭所有已知弹窗（巡逻弹窗除外，由主循环点快速巡逻处理）。

    返回 True 表示本轮关闭了某个弹窗，调用方应 continue 进入下一轮。
    """
    if states.is_reconnect_failed_popup(img):
        print(f"[{_ts()}] 🔌 重连失败弹窗 → 关闭")
        popups.close_reconnect_failed_popup()
        return True
    if states.is_pay_popup(img):
        print(f"[{_ts()}] 💰 付费弹窗 → 关闭")
        device.close_with_verify(CLOSE_POPUP, states.is_pay_popup, "付费弹窗")
        return True
    if states.is_activity_popup(img):
        print(f"[{_ts()}] 📅 活动弹窗 → 关闭")
        device.close_with_verify(CLOSE_POPUP3, states.is_activity_popup, "活动弹窗")
        return True
    if states.is_level_detail_popup(img):
        print(f"[{_ts()}] 📋 关卡详情弹窗 → 关闭")
        popups.close_level_detail_popup()
        return True
    if states.is_reward_popup(img):
        print(f"[{_ts()}] 🎉 奖励展示 → 关闭")
        time.sleep(1.5)
        popups.close_reward_popup()
        return True
    if states.is_activity_center(img):
        print(f"[{_ts()}] 🎪 活动中心 → 关闭")
        popups.close_activity_center()
        return True
    if states.is_level_up(img):
        print(f"[{_ts()}] ⬆️ 等级提升 → 关闭")
        popups.close_level_up()
        return True
    if states.is_unclaimed_reward(img):
        print(f"[{_ts()}] 🎁 未领取奖励 → 领取并关闭")
        rewards.claim_unclaimed_reward()
        return True
    if states.is_patrol(img):
        # 巡逻弹窗本身不关，交给主循环点「快速巡逻」
        return False
    if states.has_click_blank_hint(img):
        print(f"[{_ts()}] 🖱️ 点击空白处关闭提示 → 关闭")
        popups.click_blank_to_close()
        return True
    return False


def run_quick_patrol(max_loops=None):
    """快速巡逻模式主循环：切战斗 → 清弹窗 → 点巡逻车 → 点快速巡逻 → 关奖励 → 12h领取分支。

    max_loops: 限制主循环轮数（用于测试），None 表示无限循环直到 Ctrl+C。
    """
    loop_cnt = 0
    loop_total = 0
    last_qp_stamina = None      # 上一次点击快速巡逻前的鸡腿数（用于判断是否真的消耗）
    no_consume_count = 0        # 连续点击快速巡逻但鸡腿未减少的次数
    try:
        print(f"[{_ts()}] 🚓 切换到战斗界面")
        device.click_bottom_nav("战斗")
        time.sleep(2)
        while max_loops is None or loop_total < max_loops:
            loop_total += 1
            img = device.screenshot()
            if img is None:
                print(f"[{_ts()}] ❌ 截图失败，1秒后重试")
                time.sleep(1)
                continue
            vision.ocr_screenshot(img)

            # 1.5) 背包已满：无法继续巡逻领奖，停止脚本（避免反复点快速巡逻空转）
            if states.is_bag_full(img):
                print(f"[{_ts()}] 🎒 背包已满，无法继续快速巡逻，停止脚本")
                popups.click_blank_to_close()
                time.sleep(1)
                raise BagFull

            # 1) 关闭所有已知弹窗（奖励/付费/活动等），保证循环稳定
            if _close_all_popups(img):
                loop_cnt += 1
                time.sleep(1)
                continue

            # 2) 处于巡逻车弹窗：先查体力，不足则停止；否则处理领取/快速巡逻
            if states.is_patrol(img):
                # 体力(鸡腿)检查：不足一次快速巡逻消耗就关弹窗并停止脚本（带复核防误停）
                low, stamina = states.stamina_below_confirmed(img, config.STOP_STAMINA_THRESHOLD, device.screenshot)
                if low:
                    print(f"[{_ts()}] 🍗 体力(鸡腿) {stamina} 不足 {config.STOP_STAMINA_THRESHOLD}（已复核确认），停止快速巡逻")
                    popups.click_blank_to_close()
                    time.sleep(1)
                    raise OutOfStamina
                # 可领取分支：正计时到达约 11 小时（满12h物品最多，提前也能领）
                if states.is_patrol_claimable(img):
                    claim_pos = vision.get_text_position("领取", region=PATROL_CLAIM_REGION, min_confidence=0.4)
                    if claim_pos:
                        print(f"[{_ts()}] 🎁 巡逻满12小时，点领取 {claim_pos}")
                        device.tap(claim_pos)
                        time.sleep(2)
                        # 领取后弹出奖励弹窗，下一轮循环关闭
                        continue
                    else:
                        print(f"[{_ts()}] ⚠️ 检测到计时已满但未定位到领取按钮，重试")
                        time.sleep(1)
                        continue
                # 点击快速巡逻前，核对上一次点击是否真的消耗了鸡腿。
                # 背包满时点击快速巡逻会被拦截、鸡腿不减少；连续 3 次未明显减少即判定无法巡逻。
                # 用「消耗差值」判断而非单纯比较大小，可容忍 OCR 抖动并自动纠正错误基准。
                if last_qp_stamina is not None and stamina is not None:
                    consumed = last_qp_stamina - stamina   # 正常应≈单次消耗(50)
                    if consumed < 0:
                        # 鸡腿不减反增，多为 OCR 读数异常或界面未稳，不计入、重置基准
                        no_consume_count = 0
                    elif consumed < STAMINA_PER_PATROL - 20:   # 没消耗够一次巡逻的量（正常约50）
                        no_consume_count += 1
                        print(f"[{_ts()}] ⚠ 点击快速巡逻后鸡腿未明显减少（{last_qp_stamina}→{stamina}，消耗{consumed}），连续 {no_consume_count}/3 次疑似无法巡逻（背包满？）")
                        if no_consume_count >= 3:
                            print(f"[{_ts()}] 🎒 连续 {no_consume_count} 次点击快速巡逻鸡腿均未减少，判定背包已满，停止脚本")
                            popups.click_blank_to_close()
                            time.sleep(1)
                            raise BagFull
                    else:
                        no_consume_count = 0
                last_qp_stamina = stamina

                # 点「快速巡逻」按钮（运行时 OCR 定位，区域与 is_patrol 一致）
                qp = vision.get_text_position("快速巡逻", region=QUICK_PATROL_BTN_REGION, min_confidence=0.5)
                if qp:
                    print(f"[{_ts()}] 🚓 点快速巡逻 {qp}")
                    device.tap(qp)
                    time.sleep(2)
                    # 点完快速巡逻弹出奖励弹窗，下一轮循环关闭
                    continue
                # 未识别到快速巡逻按钮（弹窗未完全加载），稍等重试
                print(f"[{_ts()}] ⏳ 巡逻弹窗已识别但未定位到快速巡逻按钮，重试")
                time.sleep(1)
                continue

            # 3) 既非奖励弹窗也非巡逻弹窗：回到战斗界面点巡逻车进入弹窗
            print(f"[{_ts()}] 🚙 点巡逻车 {PATROL_CAR_BTN}")
            device.tap(PATROL_CAR_BTN)
            time.sleep(2)
    except KeyboardInterrupt:
        print(f"\n[{_ts()}] 🛑 快速巡逻模式已停止（Ctrl+C），共处理 {loop_cnt} 次弹窗")
