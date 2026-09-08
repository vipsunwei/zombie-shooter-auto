#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
招募模式主流程（run_recruit）

流程（分阶段实现中）：
  阶段1: 切到基地界面（循环点基地 + OCR 验证）✅ 已实现
  阶段2: 基地界面 OCR 找「酒馆」并点击进入酒馆界面（已实现，待实机校准）
  阶段3: 酒馆界面 OCR 找「招募10次」并点击触发十连抽（已实现，待实机校准）
  阶段4: 【普通酒馆】循环「再抽10次」直到仅剩「确认」（券用完）
  阶段5: 切【进阶酒馆】同样抽完，两个酒馆券都抽完才算招募完毕（已实现）

依赖：config、device、vision（复用现有点击 / OCR 链路）。
按钮定位统一用 OCR 文字识别 + 固定坐标兜底（与现有「开始游戏」「返回」一致）。
"""

import sys
import time

import numpy as np
import config
from config import *
import device
import vision
import states
import popups


# ---- 招募相关区域/坐标（基准分辨率 1080x1920，经 scale_region 自动缩放，待实机校准）----
TAVERN_REGION = (600, 1300, 1080, 1850)   # 基地界面右下角「酒馆」OCR 识别区
TAVERN_FALLBACK = (900, 1650)             # OCR 失败时的兜底点击坐标
RECRUIT10_REGION = (300, 1300, 1080, 1780)  # 酒馆界面「招募10次」OCR 识别区
RECRUIT10_FALLBACK = (540, 1560)           # OCR 失败时的兜底点击坐标
RECRUIT1_FALLBACK = (540, 1680)            # OCR 失败时的兜底点击坐标（单抽按钮通常在十连下方）
POPUP_REGION = (0, 300, 1080, 1850)        # 「恭喜获得」弹窗内按钮 OCR 识别区（待校准）
TAVERN_TAB_POS = (789, 1873)               # 酒馆界面底部「酒馆」标签（进阶酒馆切回普通用，基准坐标）
ADVANCED_TAB_POS = (950, 1874)             # 酒馆界面底部「进阶酒馆」标签（普通酒馆切入进阶用，基准坐标）


def _ts():
    """带时间戳的日志前缀（与 patrol.py 风格一致）"""
    return time.strftime("%H:%M:%S")


def _close_all_popups(img):
    """关闭所有已知弹窗（参照 patrol._close_all_popups，去掉巡逻/未领取分支）。

    关键约束：关闭点击只落在「右上角 / 右下角 / 底部中间(540,1720)」等安全区，
    绝不点左下角（如 BACK_BTN 85,1785 与巡逻车 110,1643 几乎重叠，会误触巡逻）。
    返回 True 表示本轮关闭了某个弹窗；False 表示无已知弹窗可关。
    """
    if states.is_reconnect_failed_popup(img):
        print(f"[{_ts()}] 🔌 重连失败弹窗 → 关闭")
        popups.close_reconnect_failed_popup()
        return True
    if states.is_pay_popup(img):
        print(f"[{_ts()}] 💰 付费礼包弹窗 → 关闭")
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
    if states.is_patrol(img):
        # 启动前若残留巡逻车弹窗（来自之前的巡逻模式），点空白关闭清掉；
        # 这是「关闭」而非「开始巡逻」，避免遮挡底部基地导航。
        print(f"[{_ts()}] 🚙 巡逻车弹窗 → 点空白关闭（清残留，不开始巡逻）")
        popups.close_patrol()
        return True
    if states.has_click_blank_hint(img):
        print(f"[{_ts()}] 🖱️ 点击空白处关闭提示 → 关闭")
        popups.click_blank_to_close()
        return True
    return False


def _clear_popups_before_base():
    """进入基地前循环关闭所有已知弹窗，避免弹窗遮挡底部导航。

    最多重试若干轮；若仍有无法识别的弹窗，不再点左下角返回（避免误触巡逻车），
    直接尝试进入基地。
    """
    for _ in range(8):
        img = device.screenshot()
        if img is None:
            print(f"[{_ts()}] ❌ 截图失败，1秒后重试")
            time.sleep(1)
            continue
        vision.ocr_screenshot(img)
        if not _close_all_popups(img):
            print(f"[{_ts()}] ✅ 已无已知弹窗遮挡")
            return
        time.sleep(1)
    print(f"[{_ts()}] ⚠️ 连续多轮仍有未识别弹窗，不再点左下角返回（避免误触巡逻车），直接尝试进入基地")


def enter_base():
    """反复点击底部导航「基地」tab，直到 OCR 验证确实停在基地界面。

    底部导航处于界面最上层，点基地不会误触左下角巡逻车按钮，
    即便有弹窗遮挡也能直接切入基地，故用「循环点基地 + 验证」而非先关弹窗。
    """
    for attempt in range(1, 6):
        print(f"[{_ts()}] 🏠 点底部导航「基地」（第 {attempt} 次）")
        device.click_bottom_nav("基地")
        time.sleep(2)
        img = device.screenshot()
        if img is None:
            print(f"[{_ts()}] ⚠️ 截图失败，重试")
            continue
        vision.ocr_screenshot(img)
        sel = device.get_selected_bottom_nav()
        print(f"[{_ts()}] 🧭 底部导航当前选中: {sel}")
        if sel == "基地":
            print(f"[{_ts()}] ✅ 已进入基地界面")
            return True
    print(f"[{_ts()}] ⚠️ 多次点击基地导航仍未确认进入基地界面（请人工核对）")
    return False


def click_tavern():
    """基地界面右下角 OCR 识别「酒馆」并点击，验证进入酒馆界面。

    OCR 优先（TAVERN_REGION），识别不到回退 TAVERN_FALLBACK 固定坐标。
    点击后截图 OCR 校验是否出现「招募10次」（酒馆界面特征）以确认进入。
    """
    img = device.screenshot()
    if img is None:
        print(f"[{_ts()}] ❌ 截图失败，无法识别酒馆")
        return False
    vision.ocr_screenshot(img)
    pos = vision.get_text_position("酒馆", region=TAVERN_REGION, min_confidence=0.5)
    if pos:
        print(f"[{_ts()}] 🍺 OCR 找到「酒馆」{pos}，点击")
        device.tap(pos)
    else:
        print(f"[{_ts()}] ⚠️ 未 OCR 到「酒馆」，回退固定坐标 {TAVERN_FALLBACK}")
        device.tap(TAVERN_FALLBACK)
    time.sleep(2)
    # 校验是否进入酒馆界面：检测「招募10次」按钮（酒馆界面特征，需先刷新 OCR 缓存）
    for wait_idx in range(2):
        img2 = device.screenshot()
        if img2 is None:
            time.sleep(1)
            continue
        vision.ocr_screenshot(img2)
        if vision.has_text("招募10次", min_confidence=0.4):
            print(f"[{_ts()}] ✅ 已确认进入酒馆界面（检测到「招募10次」）")
            return True
        time.sleep(1.5)
    print(f"[{_ts()}] ⚠️ 未能确认进入酒馆界面（请人工核对坐标/区域）")
    return False


def _tab_features(img, base_x, base_y):
    """采样底部标签中心区域的颜色特征，判断哪个标签高亮选中。

    返回 (gray_mean, sat_mean)：
      - gray_mean 平均灰度；
      - sat_mean 彩色程度(最大-最小通道均值)，选中标签文字通常更鲜艳(橙/黄)故 sat 更高。
    坐标用基准分辨率，经 scale_region 自动缩放。
    """
    x1, y1, x2, y2 = scale_region((base_x - 25, base_y - 35, base_x + 25, base_y + 35))
    crop = img.crop((max(0, x1), max(0, y1), x2, y2))
    if crop.width <= 0 or crop.height <= 0:
        return (0.0, 0.0)
    arr = np.array(crop.convert("RGB")).astype(float)
    gray = arr.mean()
    sat = (arr.max(axis=2) - arr.min(axis=2)).mean()
    return (float(gray), float(sat))


def _is_advanced_selected(g_n, s_n, g_a, s_a):
    """判断当前选中的是否为【进阶】酒馆。

    选中标签特征：灰度更低(更暗) 且 饱和度更高(更鲜艳)。但实测两个酒馆界面下
    灰度区分度不稳定（有时差仅 2，且普通选中时酒馆灰度反而略高），而饱和度方向
    始终与选中态一致（进阶选中→进阶更鲜艳；普通选中→酒馆更鲜艳）。
    故以饱和度为首要判据，灰度差足够大时作为辅助/冲突仲裁。
    """
    sat_adv = s_a > s_n      # 进阶更鲜艳 → 倾向进阶选中
    gray_adv = g_a < g_n     # 进阶更暗 → 倾向进阶选中
    if sat_adv == gray_adv:
        # 两指标一致（都指向进阶 / 都指向普通）
        return sat_adv
    # 指标冲突：看哪个区分度更大
    sat_diff = abs(s_a - s_n)
    gray_diff = abs(g_a - g_n)
    if gray_diff < 8:
        # 灰度几乎无区分 → 信饱和度
        return sat_adv
    if sat_diff < 8:
        # 饱和度几乎无区分 → 信灰度
        return gray_adv
    # 区分度都大但冲突：偏向灰度（原始实测选中标更暗）
    return gray_adv


def ensure_in_tavern():
    """确保当前停在【普通】酒馆界面（状态感知）。

    逻辑（不依赖「切换形象」等易变特征，普通/进阶靠「点酒馆标签」归一）：
      - 已在酒馆类界面（有「招募10次」）→ 点底部「酒馆」标签确保停在普通酒馆，
        再校验仍有「招募10次」即认为已进入普通酒馆；
      - 其他界面（基地 / 主城等）→ 先进基地（循环点基地验证）再点酒馆。
    这样无论从哪个界面启动都能进入酒馆并接着走招募流程。
    """
    img = device.screenshot()
    if img is None:
        print(f"[{_ts()}] ❌ 截图失败，无法判定当前界面")
        return False
    vision.ocr_screenshot(img)
    if vision.has_text("招募10次", min_confidence=0.4):
        # 已在酒馆类界面：用底部标签颜色特征判断当前是普通还是进阶
        # 实测：当前选中的标签灰度更低（更暗），故「进阶更暗 → 在进阶酒馆」
        g_n, s_n = _tab_features(img, TAVERN_TAB_POS[0], TAVERN_TAB_POS[1])
        g_a, s_a = _tab_features(img, ADVANCED_TAB_POS[0], ADVANCED_TAB_POS[1])
        print(f"[{_ts()}] 🧭 标签 亮度 酒馆={g_n:.0f} 进阶={g_a:.0f} | 饱和度 酒馆={s_n:.0f} 进阶={s_a:.0f}（选中标更暗且更鲜艳）")
        if _is_advanced_selected(g_n, s_n, g_a, s_a):
            # 进阶标签更暗 → 当前在进阶酒馆，点「酒馆」标签切回普通
            print(f"[{_ts()}] 🔄 当前在【进阶】酒馆（进阶标签更暗），点「酒馆」标签切回普通")
            device.tap(TAVERN_TAB_POS)
            time.sleep(2)
            for wait_idx in range(2):
                img2 = device.screenshot()
                if img2 is None:
                    time.sleep(1)
                    continue
                vision.ocr_screenshot(img2)
                g_n2, s_n2 = _tab_features(img2, TAVERN_TAB_POS[0], TAVERN_TAB_POS[1])
                g_a2, s_a2 = _tab_features(img2, ADVANCED_TAB_POS[0], ADVANCED_TAB_POS[1])
                print(f"[{_ts()}] 🧭 切回后 标签 亮度 酒馆={g_n2:.0f} 进阶={g_a2:.0f} | 饱和度 酒馆={s_n2:.0f} 进阶={s_a2:.0f}（普通标签应更鲜艳）")
                # 关键：普通/进阶界面都有「招募10次」，仅看文本无法区分；必须用标签亮度反判是否已切回普通
                if vision.has_text("招募10次", min_confidence=0.4) and not _is_advanced_selected(g_n2, s_n2, g_a2, s_a2):
                    print(f"[{_ts()}] ✅ 已切回【普通】酒馆界面（酒馆标签更暗）")
                    return True
                time.sleep(1.5)
            print(f"[{_ts()}] ⚠️ 切回普通酒馆失败（请校准 TAVERN_TAB_POS 或检查标签亮度特征）")
            return False
        # 酒馆标签更暗（或相等）→ 已在普通酒馆
        print(f"[{_ts()}] 🍺 当前已在【普通】酒馆界面（酒馆标签更暗），跳过切回")
        return True
    # 不在酒馆类界面：进基地再点酒馆
    print(f"[{_ts()}] 🔄 当前不在酒馆，走 进基地 → 点酒馆")
    if not enter_base():
        return False
    return click_tavern()


def click_recruit_10():
    """酒馆界面 OCR 识别「招募10次」并点击，验证十连抽弹窗出现。

    OCR 优先（RECRUIT10_REGION），识别不到回退 RECRUIT10_FALLBACK 固定坐标。
    点击后截图 OCR 校验是否出现「恭喜获得」/「再抽10次」弹窗以确认触发。
    """
    img = device.screenshot()
    if img is None:
        print(f"[{_ts()}] ❌ 截图失败，无法识别招募10次")
        return False
    vision.ocr_screenshot(img)
    pos = vision.get_text_position("招募10次", region=RECRUIT10_REGION, min_confidence=0.5)
    if pos:
        print(f"[{_ts()}] 🎲 OCR 找到「招募10次」{pos}，点击")
        device.tap(pos)
    else:
        print(f"[{_ts()}] ⚠️ 未 OCR 到「招募10次」，回退固定坐标 {RECRUIT10_FALLBACK}")
        device.tap(RECRUIT10_FALLBACK)
    time.sleep(2)
    # 校验是否触发十连抽弹窗：检测「恭喜获得」或「再抽10次」字样
    for wait_idx in range(2):
        img2 = device.screenshot()
        if img2 is None:
            time.sleep(1)
            continue
        vision.ocr_screenshot(img2)
        if vision.has_text("恭喜获得", min_confidence=0.4) or vision.has_text("再抽10次", min_confidence=0.4):
            print(f"[{_ts()}] ✅ 已确认触发十连抽弹窗（检测到恭喜获得/再抽10次）")
            return True
        time.sleep(1.5)
    print(f"[{_ts()}] ⚠️ 未能确认触发十连抽弹窗（可能无招募券 / 坐标未命中）")
    return False


def click_recruit_1():
    """酒馆界面 OCR 识别「招募1次」并点击，验证单抽弹窗出现。

    降级用途：当「招募10次」因券不足 10 张而点不动时，若仍有零头券(>=1)，
    点「招募1次」应能触发单抽弹窗；只有连「招募1次」也无效，才是真无券。
    OCR 优先（RECRUIT10_REGION），识别不到回退 RECRUIT1_FALLBACK 固定坐标。
    """
    img = device.screenshot()
    if img is None:
        print(f"[{_ts()}] ❌ 截图失败，无法识别招募1次")
        return False
    vision.ocr_screenshot(img)
    pos = vision.get_text_position("招募1次", region=RECRUIT10_REGION, min_confidence=0.5)
    if not pos:
        pos = vision.get_text_position("招募一次", region=RECRUIT10_REGION, min_confidence=0.5)
    if pos:
        print(f"[{_ts()}] 🎲 OCR 找到「招募1次」{pos}，点击")
        device.tap(pos)
    else:
        print(f"[{_ts()}] ⚠️ 未 OCR 到「招募1次」，回退固定坐标 {RECRUIT1_FALLBACK}")
        device.tap(RECRUIT1_FALLBACK)
    time.sleep(2)
    # 校验是否触发单抽弹窗：检测「恭喜获得」/「再抽1次」/「再抽一次」字样
    for wait_idx in range(2):
        img2 = device.screenshot()
        if img2 is None:
            time.sleep(1)
            continue
        vision.ocr_screenshot(img2)
        if vision.has_text("恭喜获得", min_confidence=0.4) or \
           vision.has_text("再抽1次", min_confidence=0.4) or \
           vision.has_text("再抽一次", min_confidence=0.4):
            print(f"[{_ts()}] ✅ 已确认触发单抽弹窗（检测到恭喜获得/再抽1次）")
            return True
        time.sleep(1.5)
    print(f"[{_ts()}] ⚠️ 未能确认触发单抽弹窗（可能无招募券 / 坐标未命中）")
    return False


def _popup_texts():
    """取当前 OCR 结果中的弹窗文本指纹（去重文本集合），用于判断点「再抽10次」后弹窗是否变化。"""
    result = config._current_ocr_result
    if not result:
        return frozenset()
    return frozenset(item[1] for item in result if len(item) >= 3 and item[2] >= 0.3)


def loop_congrats_popup(label="本酒馆", max_recruits=None, again_keys=("再抽10次",)):
    """循环处理「恭喜获得」弹窗，抽够次数或券用完即关弹窗返回。

    每轮截图 OCR：
      - 命中「再抽10次」且未达 max_recruits → 点它继续十连；点后重新 OCR 比对弹窗文本，
        若连续 2 次点击后弹窗「无变化」，说明招募券不足十连（<10 张，点了也不生效），
        判定券不足并点「确认」关弹窗退出（不再无限空点）；
      - 达 max_recruits 或仅剩「确认」（券不足）→ 点「确认」关闭弹窗并返回；
      - 两者皆未命中（既无「再抽10次」也无「确认」，多见于弹窗未加载或根本没弹窗）→
        连续 8 轮仍如此则判定异常，停止等待退出，避免死循环。
    max_recruits=None 表示一直抽到券用完（正式行为）；开发阶段可传小数字快速验证。
    注意：点「确认」仅关闭弹窗、返回调用方，不退出脚本（便于接着处理下一个酒馆）。
    """
    recruit_count = 1  # click_recruit_10 已触发第 1 次十连
    stale_count = 0     # 点「再抽10次」后弹窗无变化的累计次数
    no_btn_rounds = 0   # 既无「再抽10次」也无「确认」的连续轮数
    for round_idx in range(1, 201):
        img = device.screenshot()
        if img is None:
            time.sleep(1)
            continue
        vision.ocr_screenshot(img)
        fp_before = _popup_texts()
        pos_again = None
        again_label = None
        for _k in again_keys:
            _p = vision.get_text_position(_k, region=POPUP_REGION, min_confidence=0.5)
            if _p:
                pos_again, again_label = _p, _k
                break
        if pos_again and (max_recruits is None or recruit_count < max_recruits):
            print(f"[{_ts()}] 🔁 {label} 第 {recruit_count} 次: 点「{again_label}」{pos_again}")
            device.tap(pos_again)
            recruit_count += 1
            time.sleep(2)
            # 校验点击是否真的触发新十连：重新 OCR，弹窗文本应变化（出现新获得）
            img2 = device.screenshot()
            if img2 is not None:
                vision.ocr_screenshot(img2)
                if _popup_texts() == fp_before:
                    stale_count += 1
                    print(f"[{_ts()}] ⚠️ {label} 点「{again_label}」后弹窗文本无变化（疑似招募券不足，无法继续抽），第 {stale_count} 次")
                    if stale_count >= 2:
                        print(f"[{_ts()}] ✅ {label} 连续 {stale_count} 次点击无进展，判定招募券不足，停止并关闭弹窗")
                        pos_confirm = vision.get_text_position("确认", region=POPUP_REGION, min_confidence=0.5)
                        if pos_confirm:
                            device.tap(pos_confirm)
                            time.sleep(1)
                        return
                else:
                    stale_count = 0
            no_btn_rounds = 0
            continue
        pos_confirm = vision.get_text_position("确认", region=POPUP_REGION, min_confidence=0.5)
        if pos_confirm:
            if max_recruits is not None and recruit_count >= max_recruits:
                print(f"[{_ts()}] ✅ {label} 已达 {max_recruits} 次十连，点「确认」{pos_confirm} 关闭弹窗")
            else:
                print(f"[{_ts()}] ✅ {label} 仅剩「确认」（招募券已用完），点「确认」{pos_confirm} 关闭弹窗")
            device.tap(pos_confirm)
            time.sleep(1)
            return
        # 既无「再抽10次」也无「确认」：弹窗未加载，或根本没有弹窗（如没券）
        no_btn_rounds += 1
        print(f"[{_ts()}] ⏳ {label} 第 {round_idx} 轮未识别到「再抽10次」/「确认」，等待重试（{no_btn_rounds}/8）")
        if no_btn_rounds >= 8:
            print(f"[{_ts()}] ⚠️ {label} 连续 {no_btn_rounds} 轮无弹窗按钮，判定非十连弹窗状态，停止等待")
            return
        time.sleep(1.5)
    print(f"[{_ts()}] ⚠️ {label} 弹窗循环达到上限(200)，强制结束")


def go_advanced_tavern():
    """从普通酒馆切换到【进阶】酒馆（点底部「进阶酒馆」标签）。

    验证切到进阶酒馆：OCR 有「招募10次」且无「切换形象」(普通独有 UI)。
    """
    print(f"[{_ts()}] 🔄 切换到进阶酒馆（点「进阶酒馆」标签 {ADVANCED_TAB_POS}）")
    device.tap(ADVANCED_TAB_POS)
    time.sleep(2)
    for wait_idx in range(2):
        img = device.screenshot()
        if img is None:
            time.sleep(1)
            continue
        vision.ocr_screenshot(img)
        has_recruit = vision.has_text("招募10次", min_confidence=0.4)
        g_n, s_n = _tab_features(img, TAVERN_TAB_POS[0], TAVERN_TAB_POS[1])
        g_a, s_a = _tab_features(img, ADVANCED_TAB_POS[0], ADVANCED_TAB_POS[1])
        print(f"[{_ts()}] 🧭 标签 亮度 酒馆={g_n:.0f} 进阶={g_a:.0f} | 饱和度 酒馆={s_n:.0f} 进阶={s_a:.0f}（选中标更暗且更鲜艳）")
        if has_recruit and _is_advanced_selected(g_n, s_n, g_a, s_a):
            print(f"[{_ts()}] ✅ 已切换到【进阶】酒馆界面（进阶标签更暗/更鲜艳）")
            return True
        time.sleep(1.5)
    print(f"[{_ts()}] ⚠️ 未能确认切换到进阶酒馆（请校准 ADVANCED_TAB_POS）")
    return False


def run_recruit():
    """招募模式主流程：普通酒馆抽完 → 切进阶酒馆抽完，两个酒馆券都抽完才算完毕。

    状态感知：无论启动在哪个界面（基地/普通酒馆/进阶酒馆），都先确保进入
    【普通】酒馆抽十连；券用完（弹窗仅剩「确认」）后切到【进阶】酒馆继续抽，
    直到进阶券也用完，流程结束。
    """
    try:
        print(f"[{_ts()}] 🏠 进入招募模式")
        # 清启动时可能存在的残留弹窗（已知类型），避免遮挡
        _clear_popups_before_base()
        # —— 第一段：普通酒馆 ——
        if not ensure_in_tavern():
            print(f"[{_ts()}] ❌ 未能进入普通酒馆界面，停止招募")
            return
        print(f"[{_ts()}] 🎯 开始【普通酒馆】招募")
        if click_recruit_10():
            loop_congrats_popup("普通酒馆")
        else:
            print(f"[{_ts()}] ⚠️ 普通酒馆十连未触发（券<10），降级尝试「招募1次」")
            if click_recruit_1():
                loop_congrats_popup("普通酒馆", again_keys=("再抽1次", "再抽一次"))
            else:
                print(f"[{_ts()}] ⚠️ 普通酒馆无招募券（连「招募1次」也点不动），跳过本酒馆")
        # —— 第二段：进阶酒馆 ——
        if not go_advanced_tavern():
            print(f"[{_ts()}] ❌ 未能进入进阶酒馆，仅普通酒馆完成")
            return
        print(f"[{_ts()}] 🎯 开始【进阶酒馆】招募")
        if click_recruit_10():
            loop_congrats_popup("进阶酒馆")
        else:
            print(f"[{_ts()}] ⚠️ 进阶酒馆十连未触发（券<10），降级尝试「招募1次」")
            if click_recruit_1():
                loop_congrats_popup("进阶酒馆", again_keys=("再抽1次", "再抽一次"))
            else:
                print(f"[{_ts()}] ⚠️ 进阶酒馆无招募券（连「招募1次」也点不动），跳过本酒馆")
        print(f"[{_ts()}] ✅ 普通酒馆 + 进阶酒馆 招募均已处理完毕，流程完毕")
    finally:
        device.clean_screenshots()
