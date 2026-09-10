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
from PIL import Image, ImageEnhance

import config
from config import *
from vision import has_text, find_text, get_text_position, wave_white_ratio, get_ocr_reader


# 巡逻可领取时间点：正计时小时 >= 11 即可领（11:xx:xx ~ 12:xx:xx，兼容半角/全角冒号、点号）
_PATROL_CLAIMABLE_RE = re.compile(
    r'(?<!\d)(1[1-9]|[2-9]\d)(?:\s*[:：\.]\s*\d{2}){2}(?!\d)'
)


def _stamina_from_ocr(ocr_items):
    """从 OCR 结果里找 '当前/单次' 形式的体力，返回当前值(int)或 None。

    兼容两种元素结构：全局缓存 [bbox, text, conf] 与内部裁剪块 (x_min, x_max, text)。
    """
    if not ocr_items:
        return None
    texts = []
    for it in ocr_items:
        if isinstance(it, (list, tuple)) and len(it) >= 3 and isinstance(it[2], str):
            texts.append(it[2])
        elif isinstance(it, (list, tuple)) and len(it) >= 2 and isinstance(it[1], str):
            texts.append(it[1])
    # 优先匹配 '当前/50' 形式（体力上限固定50，分母精确匹配避免OCR误识别）
    for text in texts:
        m = re.search(r"(\d+)/50", text)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                continue
    return None


def _merge_overlapping_blocks(blocks):
    """把横向重叠/紧邻的数字文本块按 x 顺序合并，避免 '16963/50' 被拆成
    '6963/50' + '16' 后取最大值丢首位。返回 [(x_min, x_max, text), ...]。"""
    if not blocks:
        return []
    ordered = sorted(blocks, key=lambda b: b[0])
    merged = [list(ordered[0])]
    for b in ordered[1:]:
        last = merged[-1]
        last_w = max(last[1] - last[0], 1)
        # 与上一块重叠，或间隔小于上一块宽度的 30% → 视为同一数字合并
        if b[0] <= last[1] + 0.3 * last_w:
            if b[0] >= last[0]:
                last[2] = last[2] + b[2]
            else:
                last[2] = b[2] + last[2]
            last[0] = min(last[0], b[0])
            last[1] = max(last[1], b[1])
        else:
            merged.append(list(b))
    return [tuple(m) for m in merged]


def get_stamina(img):
    """读取顶部体力(鸡腿)数量，返回 int 或 None。

    优先从全局 OCR 缓存(config._current_ocr_result)里找 '当前/单次' 形式
    （如 '16963/50'）取分子，对顶部体力显示区域漂移免疫（游戏更新挪动 HUD
    后裁剪区易裁掉首位数字导致误判为 None，进而让巡逻背包满兜底与战斗体力不足
    停止同时失效）。缓存缺失时（战斗循环内全局缓存只含技能/波次区域，未必含
    体力）再裁剪 STAMINA_REGION 独立 OCR 兜底。
    """
    if img is None:
        return None

    # 1) 全局 OCR 缓存优先：直接用全屏 OCR 结果，避开裁剪区漂移/数字拆块
    cached = getattr(config, "_current_ocr_result", None)
    val = _stamina_from_ocr(cached) if cached else None
    if val is not None:
        return val

    # 2) 兜底：裁剪 STAMINA_REGION 独立 OCR（增强对比 + 放大）
    x1, y1, x2, y2 = scale_region(STAMINA_REGION)
    crop = img.crop((x1, y1, x2, y2))
    # 先增强对比度（2倍），再灰度二值化变成纯黑底白字，
    # 放大 3 倍后再识别可显著降低误读率
    crop = ImageEnhance.Contrast(crop).enhance(2.0)
    crop = crop.convert('L')
    crop = crop.point(lambda x: 255 if x >= 128 else 0)
    crop = crop.resize((crop.width * 3, crop.height * 3), Image.LANCZOS)
    reader = get_ocr_reader()
    result = reader.readtext(np.array(crop))

    blocks = []   # (x_min, x_max, text)
    for item in result:
        if len(item) < 3:
            continue
        bbox, text, confidence = item[0], item[1], item[2]
        if not re.search(r"\d", text):
            continue
        xs = [p[0] for p in bbox]
        blocks.append((min(xs), max(xs), text))

    # 文本块横向重叠 = 同一个数字被拆块：合并后再解析（不再直接判 None）
    merged = _merge_overlapping_blocks(blocks)
    return _stamina_from_ocr(merged)


def stamina_below_confirmed(img, threshold, recheck_fn, retries=2):
    """判断体力(鸡腿)是否低于阈值（带复核），返回 (是否不足, 最终读数)。

    单次 OCR 丢位/误识可能把 44436 读成 4436 之类的低值，导致未到阈值就误停。
    首读低于阈值时，用 recheck_fn 重新截图再识别 retries 次：
    - 任一次复核读数 ≥ 阈值 → 判定首读为误读，不停止（返回复核值）
    - 复核读不到(None) → 视为不确定，不停止，下轮循环再判
    - 连续 retries 次复核均低于阈值 → 确认不足，停止
    首读达标时不触发复核，无额外截图开销。
    """
    stamina = get_stamina(img)
    if stamina is None or stamina >= threshold:
        return False, stamina
    for _ in range(retries):
        s = get_stamina(recheck_fn())
        if s is not None and s >= threshold:
            return False, s
        if s is None:
            return False, stamina
    return True, stamina


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
    """通关结算界面：必须同时满足「不在战斗中」+「非失败页」+「出现结算专属标签栏」。

    ⚠️ 关键修复：战斗中底部本就有「返回」导航键、还常弹「恭喜获得」奖励窗，
    旧逻辑只要命中 2/3 特征就判胜利，导致战斗中误判通关→点返回→退回选关→重打同一关。
    真正的结算页专属特征是底部标签栏（伤害统计/问题上报/奖励总览），战斗中绝不会出现；
    且结算时早已不在战斗（无波次）。两者同时约束即可彻底排除误判。

    另外失败页同样带「标签栏+返回」，故必须以 is_defeat 显式排除——否则 OCR 漏识
    「挑战失败」时，失败结算页会被错判为胜利（127 实战已踩坑）。
    """
    if is_battling(img):
        return False
    if is_defeat(img):
        return False
    tabs_region = (50, 1400, 1030, 1560)
    has_tabs = (has_text("伤害统计", region=tabs_region, min_confidence=0.3) or
                has_text("问题上报", region=tabs_region, min_confidence=0.3) or
                has_text("奖励总览", region=tabs_region, min_confidence=0.2) or
                has_text("奖励总笕", region=tabs_region, min_confidence=0.2))
    if not has_tabs:
        return False
    has_return = has_text("返回", region=(500, 1600, 1030, 1800), min_confidence=0.5)
    if not has_return:
        return False
    # 胜利专属正向文字（子串匹配，覆盖「通关结算/成功通关/完美通关/胜利/恭喜获得」）。
    # 失败页已被 is_defeat 排除，此处再要求胜利正向文字，确保不是其它未知结算页被误当胜利。
    victory_text = (has_text("通关", min_confidence=0.3) or
                    has_text("胜利", min_confidence=0.3) or
                    has_text("恭喜获得", region=(300, 350, 780, 500), min_confidence=0.5))
    return bool(victory_text)


def is_victory(img):
    """通关界面：检测"完美通关"文字（位置在屏幕上方）。结算时早已不在战斗。"""
    if is_battling(img):
        return False
    return has_text("完美通关", region=(300, 150, 780, 350))


def is_defeat(img):
    """战斗失败结算界面：检测专属字样「挑战失败」或「再来一次」（区别于「重连失败」弹窗）。

    失败页含「挑战失败 / 再来一次 / 返回」，与胜利页同样带「返回」+「恭喜获得」奖励弹窗，
    若不加此判定会被 is_victory_settlement 误判为胜利 → 点返回 → 重打同一关 → 死循环。

    ⚠️ 实战教训（重要）：127 这种硬仗结算页，「挑战失败」字体艺术化、OCR 常整词误读
    （如「挑载失败」「挑战失则」），用整词匹配会漏识 → 整页被误判为胜利（已踩坑多次）。
    故改用【子串匹配】：
      - "失败"：只要误读后"失败"两字还在即可兜底（"挑载失败"含"失败"→命中）；
      - "挑战"：覆盖"挑战失败/挑战失则"等变体；
      - "再来一次"：失败页专属按钮，几乎不可能误读，作为强信号。
    三者任一命中即判失败，优先级高于胜利判定。
    """
    # 标题区 y≈258：「挑战失败」实测中心 @(539,262)，旧 regional (y从280起) 差 18px 导致整段漏检，
    # 多年误判根源就在这，故文本框顶放宽到 y=200 覆盖标题带。
    if has_text("失败", region=(80, 200, 1000, 1050), min_confidence=0.3):
        return True
    if has_text("挑战", region=(80, 200, 1000, 1050), min_confidence=0.3):
        return True
    # 「再来一次」是失败页专属按钮，实测 @(326,1695)，与「双倍奖励」互斥（通关页该位置是双倍奖励）。
    # 旧 region=(600,1100) 根本覆盖不到 y=1695，这条检查是死的，现按实测按钮行修正。
    if has_text("再来一次", region=(150, 1600, 520, 1790), min_confidence=0.3):
        return True
    return False


def get_level_label(img=None):
    """战斗中 OCR 顶部关卡标签，返回如 '127.球场空地'；识别失败返回 None。

    仅在进入战斗时调用一次用于分析记录；独立裁剪顶部区域，不依赖全局 OCR 缓存。
    """
    if img is None:
        return None
    if not isinstance(img, Image.Image):
        img = Image.fromarray(img)
    x1, y1, x2, y2 = scale_region(config.LEVEL_LABEL_REGION)
    cropped = img.crop((x1, y1, x2, y2))
    try:
        res = get_ocr_reader().readtext(np.array(cropped))
    except Exception:
        return None
    for b, t, c in res:
        s = t.strip()
        if re.search(r'^\d+\.', s) or '球场' in s or '关' in s:
            return s
    return None


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
    pos = get_text_position(chest_name, region=(50, 900, 1050, 1750), min_confidence=0.2)
    if pos is None:
        return None
    return (pos[0], pos[1] - 80)


def is_chest_glowing(img, chest_name):
    """检测指定宝箱是否发光（未领取）

    判定依据：宝箱图标的金黄色像素 + 明显高亮光晕。
    关键修复：检测区域只取宝箱图标部分（裁掉底部文字行），避免把
    「50%血量通关」等挑战标签的金色文字误判为发光宝箱；且要求存在
    高亮光晕（发光宝箱比普通金文字亮得多），进一步排除文字干扰。
    """
    if img is None or chest_name not in CHEST_REGIONS:
        return False
    x1, y1, x2, y2 = scale_region(CHEST_REGIONS[chest_name])
    # 只取上半部分（宝箱图标），裁掉底部文字行，排除金色文字干扰
    y2 = y1 + int((y2 - y1) * 0.55)
    if isinstance(img, Image.Image):
        cropped = img.crop((x1, y1, x2, y2))
    else:
        cropped = img[y1:y2, x1:x2, :]
        cropped = Image.fromarray(cropped)
    img_np = np.array(cropped)
    # 金色图标像素
    gold_mask = (img_np[:, :, 0] > 180) & (img_np[:, :, 1] > 130) & (img_np[:, :, 2] < 100)
    # 高亮光晕（发光宝箱比普通金文字更亮）
    glow_mask = (img_np[:, :, 0] > 225) & (img_np[:, :, 1] > 195) & (img_np[:, :, 2] < 85)
    total = img_np.shape[0] * img_np.shape[1]
    gold_ratio = np.sum(gold_mask) / total * 100
    glow_ratio = np.sum(glow_mask) / total * 100
    # 必须既有金色图标、又有明显高亮光晕，才判定为发光
    # 实测未发光宝箱 glow_ratio 最高仅 1.15%，阈值取 2 留余量且不会漏领
    return bool(gold_ratio > 15 and glow_ratio > 2)


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

    注意：巡逻时间【满】时，游戏不再显示 HH:MM:SS，而是显示
    「已达到最大巡逻时间！」（实测置信度 0.99，位置 x=414~651, y=822~854）。
    此时同样是（且是收益最高的）可领取状态，若不做识别会导致满时间反而漏领，
    故先判断该文案再走时间正则。
    """
    if has_text("最大巡逻", region=PATROL_TIME_FULL_REGION, min_confidence=0.3):
        return True
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
    ax1, ay1, ax2, ay2 = scale_region(AUTO_CLOSE_POPUP_REGION)
    if isinstance(img, Image.Image):
        cropped = img.crop((ax1, ay1, ax2, ay2))
    else:
        cropped = img[ay1:ay2, ax1:ax2, :]
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
