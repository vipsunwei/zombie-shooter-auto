#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
界面状态判定（所有 is_* 函数）

职责：根据 OCR 缓存 / 像素统计判断当前处于哪个界面。
只做判定、不做操作（不调用 tap / screenshot），因此只依赖 vision 与 config，
不依赖 device，从而避免 device<->states 循环依赖。
"""

import re
import numpy as np
from PIL import Image

import config
from config import *
from vision import has_text, find_text, get_text_position, wave_white_ratio, get_ocr_reader


# 巡逻可领取时间点：正计时小时 >= 11 即可领（11:xx:xx ~ 12:xx:xx，兼容半角/全角冒号、点号）
_PATROL_CLAIMABLE_RE = re.compile(
    r'(?<!\d)(1[1-9]|[2-9]\d)(?:\s*[:：\.]\s*\d{2}){2}(?!\d)'
)


def get_stamina(img):
    """读取顶部体力(鸡腿)数量，返回 int 或 None。

    对顶部体力区域(STAMINA_REGION)独立裁剪 OCR，不依赖全局 OCR 缓存，
    因此在战斗循环(ocr_battle_loop 裁剪区域)中也能可靠识别。
    区域文本形如 '53263/50'（当前/单次消耗）。OCR 可能把数字拆成多块或误识，
    故收集区域内所有整数，返回最大值（当前鸡腿数远大于单次消耗 50 与误识碎片）。
    """
    if img is None:
        return None
    x1, y1, x2, y2 = scale_region(STAMINA_REGION)
    crop = img.crop((x1, y1, x2, y2))
    reader = get_ocr_reader()
    result = reader.readtext(np.array(crop))
    best = None
    for item in result:
        if len(item) < 3:
            continue
        text = item[1]
        # 同一文本块可能含多个数字（如 '53263/50'），逐块取最大值
        for m in re.finditer(r"\d+", text):
            try:
                val = int(m.group().replace(",", ""))
            except ValueError:
                continue
            if best is None or val > best:
                best = val
    return best


# ============================================================
#  基于 OCR 文字的界面判定
# ============================================================

def is_skill_select(img):
    """选择技能界面：检测"选择技能"文字（位置在屏幕中上方）"""
    return has_text("选择技能", region=(300, 400, 780, 560))


def is_elite_drop(img):
    """精英掉落界面：检测"精英掉落"文字（字体较小，OCR置信度偏低）"""
    return has_text("精英掉落", region=(300, 1200, 780, 1450), min_confidence=0.2)


def is_victory_settlement(img):
    """通关结算界面：满足2个以上特征即认为是结算页面
    特征：标签栏（伤害统计/问题上报/奖励总览）、返回按钮、恭喜获得
    """
    tabs_region = (50, 1400, 1030, 1560)
    has_tabs = (has_text("伤害统计", region=tabs_region, min_confidence=0.3) or
                has_text("问题上报", region=tabs_region, min_confidence=0.3) or
                has_text("奖励总览", region=tabs_region, min_confidence=0.2) or
                has_text("奖励总笕", region=tabs_region, min_confidence=0.2))
    has_return = has_text("返回", region=(500, 1600, 1030, 1800), min_confidence=0.5)
    has_congrats = has_text("恭喜获得", region=(300, 350, 780, 500), min_confidence=0.5)
    return sum([has_tabs, has_return, has_congrats]) >= 2


def is_victory(img):
    """通关界面：检测"完美通关"文字（位置在屏幕上方）"""
    return has_text("完美通关", region=(300, 150, 780, 350))


def is_perfect_clear(img=None):
    """检测界面上半部分是否有"完美通关"文字（关卡标题下方，y≈330-420）"""
    return has_text("完美通关", region=(300, 320, 800, 430), min_confidence=0.3)


def is_unclaimed_reward(img=None):
    """检测界面上是否有"未领取"按钮（OCR可能把"未"识别成"末"）"""
    if has_text("未领取", region=(0, 1300, 200, 1500), min_confidence=0.3):
        return True
    if has_text("末领取", region=(0, 1300, 200, 1500), min_confidence=0.3):
        return True
    return False


def is_reward_popup(img=None):
    """检测是否是奖励展示界面（"恭喜获得"）"""
    return has_text("恭喜获得", region=(300, 500, 800, 700), min_confidence=0.3)


def is_bag_full(img=None):
    """检测背包已满提示（弹窗内'背包已满'/'背包空间不足'等）。

    仅匹配'背包已满'而非常单独'背包'，避免与底部'背包'导航按钮混淆。
    """
    if has_text("背包已满", min_confidence=0.3):
        return True
    if has_text("背包空间不足", min_confidence=0.3):
        return True
    return False


def is_claimable_chest(chest_name):
    """检测指定宝箱是否可领取（通过文字位置判断）
    chest_name: "成功通关" / "50%血量通关" / "完美通关"
    返回: (x, y) 宝箱位置，未找到返回 None
    """
    pos = get_text_position(chest_name, region=(50, 1300, 1050, 1550), min_confidence=0.2)
    if pos is None:
        return None
    return (pos[0], pos[1] - 80)


def is_chest_glowing(img, chest_name):
    """检测指定宝箱是否发光（未领取）：通过宝箱区域的金黄色像素比例判断"""
    if img is None or chest_name not in CHEST_REGIONS:
        return False
    x1, y1, x2, y2 = CHEST_REGIONS[chest_name]
    if isinstance(img, Image.Image):
        cropped = img.crop((x1, y1, x2, y2))
    else:
        cropped = img[y1:y2, x1:x2, :]
        cropped = Image.fromarray(cropped)
    img_np = np.array(cropped)
    gold_mask = (img_np[:, :, 0] > 180) & (img_np[:, :, 1] > 130) & (img_np[:, :, 2] < 100)
    gold_count = np.sum(gold_mask)
    total = img_np.shape[0] * img_np.shape[1]
    ratio = gold_count / total * 100
    return bool(ratio > 15)


def get_glowing_chests(img):
    """获取所有发光（未领取）的宝箱列表，按从左到右排序"""
    glowing = []
    for chest_name in ["成功通关", "50%血量通关", "完美通关"]:
        if is_chest_glowing(img, chest_name):
            glowing.append(chest_name)
    return glowing


def is_level_select(img):
    """单关选择界面：检测"开始游戏"文字（字体艺术化，阈值降到0.1）"""
    return has_text("开始游戏", region=(300, 1480, 780, 1680), min_confidence=0.1)


def is_level_list(img):
    """关卡列表界面：检测"关卡选择"标题 + 底部"选择"按钮"""
    has_title = has_text("关卡选择", region=(50, 50, 350, 160))
    has_select_btn = has_text("选择", region=(300, 1650, 780, 1880))
    return has_title and has_select_btn


def is_battling(img):
    """战斗中界面：双判据（波次区白色像素占比 或 OCR命中"波次"）"""
    ratio = wave_white_ratio(img)
    if ratio > WAVE_WHITE_THRESHOLD:
        return True
    return has_text("波次", region=(600, 0, 1080, 120))


def is_pay_popup(img):
    """付费/见面豪礼弹窗：检测弹窗区域内的特征文字（限制在屏幕中间）"""
    region = (200, 200, 900, 1500)
    return (has_text("见面豪礼", region=region) or
            has_text("付费", region=region) or
            has_text("限时礼包", region=region))


def is_activity_popup(img):
    """本周活动弹窗：检测弹窗区域内的特征文字（限制在屏幕中间）"""
    region = (200, 200, 900, 1500)
    return has_text("本周活动", region=region)


def is_activity_center(img):
    """活动中心界面：检测"炙热咆哮"或"超值回馈"文字"""
    return (has_text("炙热咆哮", region=(100, 750, 500, 900), min_confidence=0.5) or
            has_text("超值回馈", region=(500, 900, 900, 1100), min_confidence=0.5))


def is_level_up(img):
    """等级提升界面：检测"等级提升"标题 或 "点击屏幕继续"提示"""
    if has_text("等级提升", region=(300, 200, 780, 350), min_confidence=0.5):
        return True
    if has_text("点击屏幕继续", region=(300, 1750, 780, 1900), min_confidence=0.5):
        return True
    return False


def is_level_detail_popup(img):
    """关卡详情弹窗：检测"本关怪物"或"本关掉落"文字"""
    if has_text("本关怪物", region=(300, 400, 780, 550), min_confidence=0.5):
        return True
    if has_text("本关掉落", region=(300, 750, 780, 900), min_confidence=0.5):
        return True
    return False


def has_click_blank_hint(img):
    """检测界面上是否有"点击空白处关闭"提示（通用关闭提示）"""
    return has_text("点击空白处关闭", region=(300, 1750, 780, 1900), min_confidence=0.3)


def is_patrol(img):
    """巡逻/扫荡界面：检测"快速巡逻" 或 "最长巡逻"+"点击空白处关闭"组合"""
    if has_text("快速巡逻", region=(150, 1400, 450, 1550), min_confidence=0.5):
        return True
    if has_text("最长巡逻", region=(300, 700, 600, 800), min_confidence=0.3):
        if has_text("点击空白处关闭", region=(300, 1750, 780, 1900), min_confidence=0.3):
            return True
    return False


def is_patrol_claim(img=None):
    """检测巡逻弹窗内「领取」按钮（限定区域，避开未领取奖励区域）"""
    return has_text("领取", region=PATROL_CLAIM_REGION, min_confidence=0.4)


def is_patrol_claimable(img=None):
    """检测巡逻是否已到可领取时间点（正计时 11~12 小时即可领）。

    巡逻【领取】按钮是常驻的，不要求满 12 小时；满 12 小时只是可领物品最多。
    因此当正计时到达约 11 小时（文本小时位 >= 11，例如 11:xx:xx / 12:00:00）
    即可点领取。通过正则匹配 PATROL_TIME_REGION 区域内小时 >= 11 的时间文本，
    兼容半角/全角冒号、点号等 OCR 常见误识；0 小时（00:xx:xx）不会命中。
    """
    result = config._current_ocr_result
    if result is None:
        return False
    x1, y1, x2, y2 = scale_region(PATROL_TIME_REGION)
    for item in result:
        if len(item) < 3:
            continue
        box, text, confidence = item
        if confidence < 0.3:
            continue
        cx = sum(p[0] for p in box) / 4
        cy = sum(p[1] for p in box) / 4
        if not (x1 <= cx <= x2 and y1 <= cy <= y2):
            continue
        if _PATROL_CLAIMABLE_RE.search(text):
            return True
    return False


def is_auto_close_popup(img):
    """检测已激活技能弹窗（底部有"秒后自动关闭"文字），独立做 OCR 不依赖全局缓存"""
    if img is None:
        return False
    if isinstance(img, Image.Image):
        cropped = img.crop((360, 1735, 720, 1840))
    else:
        cropped = img[1735:1840, 360:720, :]
        cropped = Image.fromarray(cropped)
    cropped_np = np.array(cropped)
    ocr_reader = get_ocr_reader()
    result = ocr_reader.readtext(cropped_np, detail=1)
    for item in result:
        if len(item) >= 3:
            bbox, text, confidence = item[0], item[1], item[2]
            if "秒后自动关闭" in text or "自动关闭" in text:
                if confidence >= 0.3:
                    return True
    return False


def is_reconnect_failed_popup(img):
    """检测"重连失败断开连接"提示弹窗"""
    return has_text("重连失败", min_confidence=0.3) or has_text("断开连接", min_confidence=0.3)
