#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
界面处理器（表驱动分派的「处理策略」层）

每个界面一个 _on_xxx(ctx, img) 处理器；由 _dispatch 按 BATTLE_HANDLERS /
UI_HANDLERS 的顺序匹配执行——列表顺序即优先级（与原 if/elif 顺序一致），
末项用 _always 恒真兜底。
"""

import time
import sys

import config
from config import *
import device
import vision
import states
import popups
import skills
import rewards


class _Continue:
    """处理器返回标记：表示本轮循环直接进入下一轮（等价于原来的 continue）"""

    def __repr__(self):
        return "<CONTINUE>"


CONTINUE = _Continue()


class LoopContext:
    """主循环可变状态容器。

    各界面处理器通过它读写计数与加载计时，避免在主函数里堆大量 nonlocal。
    """

    def __init__(self):
        self.skill_cnt = 0
        self.level_cnt = 0
        self.popup_cnt = 0
        self.unknown_cnt = 0
        self.just_started = False
        self.just_start_time = 0.0


def _log(msg):
    """带时间戳的统一日志输出"""
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


def _always(img):
    """兜底判定：恒真，作为分派表最后一项"""
    return True


def _dispatch(handlers, ctx, img):
    """按顺序匹配界面，执行第一个命中的处理器并返回其状态字符串。

    handlers: [(is_func, handler), ...]；is_func(img) 为真的第一项被执行，
    因此列表顺序即优先级（与原先 if/elif 的顺序一致）。
    """
    for is_func, handler in handlers:
        if is_func(img):
            return handler(ctx, img)
    return None


# ---------------- 通用处理器（战斗内外共用） ----------------

def _on_reconnect_failed(ctx, img):
    _log("🔌 检测到重连失败断开连接弹窗 → 点击确定按钮关闭")
    popups.close_reconnect_failed_popup()
    ctx.popup_cnt += 1
    ctx.unknown_cnt = 0
    return "重连失败弹窗"


# ---------------- 战斗循环内的界面处理器 ----------------

def _on_auto_close_popup(ctx, img):
    _log("⚡ 检测到已激活技能弹窗（秒后自动关闭）→ 点击左下角直接关闭")
    popups.close_auto_close_popup()
    ctx.popup_cnt += 1
    ctx.unknown_cnt = 0
    return "已激活技能弹窗"


def _on_victory_settlement(ctx, img):
    ctx.level_cnt += 1
    config.in_battle_loop = False
    _log(f"🏆 第 {ctx.level_cnt} 关通关！→ 点击返回，跳出游戏循环")
    rewards.do_victory()
    if CLEAN_SCREENSHOT_PER_LEVEL:
        device.clean_screenshots()
        _log("🧹 已清理本关截图")
    ctx.unknown_cnt = 0
    return "通关结算"


def _on_skill_select(ctx, img):
    (pos_name, pos_coord, left_name, middle_name, right_name,
     reason, selected_name, selected_score) = skills.do_select_skill()
    ctx.skill_cnt += 1
    if left_name or middle_name or right_name:
        if selected_score > 0:
            _log(f"⚡ 选择技能 [{left_name}|{middle_name}|{right_name}] → 选[{selected_name}]，优先级({selected_score:.1f})")
        else:
            _log(f"⚡ 选择技能 [{left_name}|{middle_name}|{right_name}] → 选[{selected_name}]，随机选择")
    else:
        _log(f"⚡ 选择技能 → 选[{selected_name}]，随机选择")
    time.sleep(1.2)
    ctx.unknown_cnt = 0
    return "选择技能"


def _on_elite_drop(ctx, img):
    _log("🎁 精英掉落")
    popups.close_elite_drop()
    ctx.unknown_cnt = 0
    return "精英掉落"


def _on_battle_default(ctx, img):
    """战斗中兜底：未命中任何已知界面时，检测「返回」按钮进入结算处理"""
    back_pos = vision.get_text_position("返回", region=VICTORY_RETURN_REGION, min_confidence=0.5)
    if not back_pos:
        ctx.unknown_cnt = 0
        return "战斗中"
    _log(f"🏁 检测到返回按钮{back_pos}，进入结算处理")
    if states.is_victory(img):
        _log("🏆 检测到通关结算界面，处理结算")
        rewards.do_victory()
        if CLEAN_SCREENSHOT_PER_LEVEL:
            device.clean_screenshots()
            _log("🧹 已清理本关截图")
    else:
        _log(f"↩️  未检测到通关结算界面，直接点击返回按钮 {back_pos}")
        device.tap(back_pos)
        time.sleep(1)
    config.in_battle_loop = False
    ctx.unknown_cnt = 0
    return "返回结算"


# 战斗循环内分派表（顺序即优先级，最后一项恒真兜底）
BATTLE_HANDLERS = [
    (states.is_auto_close_popup, _on_auto_close_popup),
    (states.is_reconnect_failed_popup, _on_reconnect_failed),
    (states.is_victory_settlement, _on_victory_settlement),
    (states.is_skill_select, _on_skill_select),
    (states.is_elite_drop, _on_elite_drop),
    (_always, _on_battle_default),
]


# ---------------- 非战斗（主界面）的界面处理器 ----------------

def _on_pay(ctx, img):
    _log("💰 付费/见面豪礼弹窗")
    device.close_with_verify(CLOSE_POPUP, states.is_pay_popup, "付费弹窗")
    ctx.popup_cnt += 1
    ctx.unknown_cnt = 0
    return "付费弹窗"


def _on_activity(ctx, img):
    _log("📅 本周活动弹窗")
    device.close_with_verify(CLOSE_POPUP3, states.is_activity_popup, "活动弹窗")
    ctx.popup_cnt += 1
    ctx.unknown_cnt = 0
    return "活动弹窗"


def _on_level_detail(ctx, img):
    _log("📋 关卡详情弹窗 → 点击右上角×关闭")
    popups.close_level_detail_popup()
    ctx.popup_cnt += 1
    ctx.unknown_cnt = 0
    return "关卡详情弹窗"


def _on_reward(ctx, img):
    _log("🎉 奖励展示界面 → 点击左下角关闭")
    popups.close_reward_popup()
    ctx.unknown_cnt = 0
    return "奖励展示"


def _on_click_blank(ctx, img):
    _log("🖱️ 检测到「点击空白处关闭」提示 → 点击关闭")
    popups.click_blank_to_close()
    ctx.unknown_cnt = 0
    return "点击空白关闭"


def _on_activity_center(ctx, img):
    _log("🎪 活动中心界面 → 点右上角×关闭")
    popups.close_activity_center()
    ctx.unknown_cnt = 0
    return "活动中心"


def _on_level_up(ctx, img):
    _log("⬆️ 等级提升界面 → 点击屏幕继续")
    popups.close_level_up()
    ctx.unknown_cnt = 0
    return "等级提升"


def _on_patrol(ctx, img):
    _log("🚶 巡逻/扫荡界面 → 点击空白处关闭")
    popups.close_patrol()
    ctx.unknown_cnt = 0
    return "巡逻界面"


def _on_unclaimed(ctx, img):
    _log("🎁 检测到'未领取'按钮 → 点击领取")
    rewards.claim_unclaimed_reward()
    img2 = device.screenshot()
    if img2 is not None:
        vision.ocr_screenshot(img2)
        if states.is_reward_popup(img2):
            _log("    → 检测到奖励展示界面 → 关闭")
            popups.close_reward_popup()
    perfect_pos = None
    for retry in range(3):
        img3 = device.screenshot()
        if img3 is not None:
            vision.ocr_screenshot(img3)
            if retry == 0:
                _log("    → 在下半部分检测完美通关宝箱...")
            perfect_pos = states.is_claimable_chest("完美通关")
            if perfect_pos:
                break
            else:
                _log(f"    → 第{retry + 1}次未识别到完美通关文字，{0.5 if retry < 2 else 0}秒后重试...")
                time.sleep(0.5)
        else:
            break
    if perfect_pos:
        _log(f"    → 识别到完美通关文字，宝箱位置 {perfect_pos}，点击领取")
        device.tap(perfect_pos)
        time.sleep(2)
        img4 = device.screenshot()
        if img4 is not None:
            vision.ocr_screenshot(img4)
            if states.is_reward_popup(img4):
                _log("    → 检测到奖励展示界面 → 关闭")
                popups.close_reward_popup()
            else:
                _log("    → 未弹出奖励界面（可能已领取）")
    else:
        _log("    → 多次重试仍未识别到完美通关文字（可能已领取或OCR未识别）")
    ctx.unknown_cnt = 0
    return "未领取奖励"


def _on_perfect_clear(ctx, img):
    _log("✅ 当前关卡已完美通关 → 点击右箭头跳到下一关")
    rewards.click_next_level()
    ctx.unknown_cnt = 0
    return "完美通关"


def _on_level_list(ctx, img):
    _log("📋 关卡列表 → 点选择进入单关选择")
    device.tap(REWARD_POPUP_CLOSE_BTN)
    time.sleep(1.5)
    ctx.unknown_cnt = 0
    return "关卡列表"


def _on_level_select(ctx, img):
    if rewards.claim_all_chests(img):
        time.sleep(1)
        ctx.unknown_cnt = 0
        return CONTINUE
    # 点开始游戏前：先确认"开始游戏"按钮确实在界面上、能定位到
    start_pos = vision.get_text_position(
        "开始游戏", region=(300, 1480, 780, 1680), min_confidence=0.1)
    if start_pos is None:
        _log("    ⚠ 未定位到「开始游戏」按钮（可能并非关卡选择界面或OCR未识别），本轮回退重试")
        ctx.unknown_cnt = 0
        return CONTINUE
    # 点开始游戏前判断鸡腿是否足够开下一关；不足则停止脚本（游戏循环中不判断）
    low, stamina = states.stamina_below_confirmed(img, config.STOP_STAMINA_THRESHOLD, device.screenshot)
    if low:
        _log(f"🍗 体力(鸡腿) {stamina} 不足 {config.STOP_STAMINA_THRESHOLD}（已复核确认），停止循环闯关")
        device.click_bottom_nav("战斗")
        time.sleep(1.5)
        sys.exit(config.OUT_OF_STAMINA_EXIT)
    config.in_battle_loop = True
    _log(f"▶ 关卡选择 → 点开始游戏{start_pos}，进入游戏循环")
    device.tap(start_pos)
    ctx.just_started = True
    ctx.just_start_time = time.time()
    _log("    → 验证是否真正进入战斗界面（最多6秒）...")
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
            _log(f"    → 仍在关卡选择页，重新点击开始游戏{start_pos}")
            device.tap(start_pos)
            ctx.just_started = True
            ctx.just_start_time = time.time()
            continue
        if states.is_auto_close_popup(img_v):
            _log("    → 检测到已激活技能弹窗，点击左下角关闭")
            popups.close_auto_close_popup()
            continue
        # 其余视为战斗加载/过渡画面，继续等待
    if entered_battle:
        _log("    ✅ 已确认进入战斗界面")
    else:
        _log("    ⚠ 未在限定时间内确认进入战斗，回退到关卡选择重试")
        config.in_battle_loop = False
        ctx.just_started = False
    ctx.unknown_cnt = 0
    return "关卡选择"


def _on_victory(ctx, img):
    ctx.level_cnt += 1
    _log(f"🏆 第 {ctx.level_cnt} 关通关！→ 点击返回")
    rewards.do_victory()
    if CLEAN_SCREENSHOT_PER_LEVEL:
        device.clean_screenshots()
        _log("🧹 已清理本关截图")
    ctx.unknown_cnt = 0
    return "通关"


def _on_battling(ctx, img):
    config.in_battle_loop = True
    _log("⚔ 检测到战斗中，自动进入游戏循环")
    ctx.unknown_cnt = 0
    return "战斗中"


def _on_unknown(ctx, img):
    """主界面兜底：未命中任何已知界面时，按 加载中 / 底部导航 / 未知界面 处理"""
    if ctx.just_started and (time.time() - ctx.just_start_time < 3):
        ctx.unknown_cnt = 0
        return "战斗加载中"
    ctx.just_started = False
    selected_nav = device.get_selected_bottom_nav()
    if selected_nav and selected_nav != "战斗":
        _log(f"🧭 底部导航当前选中「{selected_nav}」，点击「战斗」切换到战斗界面")
        if device.click_bottom_nav("战斗"):
            time.sleep(1.5)
        ctx.unknown_cnt = 0
        return f"底部导航-{selected_nav}"
    elif selected_nav == "战斗":
        ctx.unknown_cnt = 0
        return "战斗页面-加载中"
    else:
        ctx.unknown_cnt += 1
        status = f"未知界面({ctx.unknown_cnt})"
        if ctx.unknown_cnt >= 8:
            _log(f"⚠ 连续{ctx.unknown_cnt}次未知界面，兜底点左下角返回按钮")
            device.fallback_back()
            ctx.unknown_cnt = 0
        return status


# 主界面分派表（顺序即优先级，最后一项恒真兜底）
UI_HANDLERS = [
    (states.is_reconnect_failed_popup, _on_reconnect_failed),
    (states.is_pay_popup, _on_pay),
    (states.is_activity_popup, _on_activity),
    (states.is_level_detail_popup, _on_level_detail),
    (states.is_reward_popup, _on_reward),
    (states.has_click_blank_hint, _on_click_blank),
    (states.is_activity_center, _on_activity_center),
    (states.is_level_up, _on_level_up),
    (states.is_patrol, _on_patrol),
    (states.is_unclaimed_reward, _on_unclaimed),
    (states.is_perfect_clear, _on_perfect_clear),
    (states.is_level_list, _on_level_list),
    (states.is_level_select, _on_level_select),
    (states.is_victory, _on_victory),
    (states.is_battling, _on_battling),
    (_always, _on_unknown),
]
