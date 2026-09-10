#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
技能词条配置与选择

职责：
- load_skill_config：动态加载 skill_config.py（带缓存，支持热更新）
- ocr_skill_region / get_skill_names_from_ocr：识别三张卡片的词条名称
- get_skill_priority：按配置计算词条优先级
- do_select_skill：按策略点击卡片

依赖：config、device（tap/screenshot）、vision（OCR）。
"""

import os
import re
import time
import random
import importlib.util

import numpy as np
from PIL import Image

import config
from config import *
import device
import vision


# 配置路径：SKILL_CONFIG_PATH 是 git 托管的默认配置（程序只读，不修改）；
# RUNTIME_CONFIG_PATH 是运行时配置（非 git 托管），失败调优时改写它，下一局选牌自动重载。
SKILL_CONFIG_PATH = os.path.join(config.BASE_DIR, "skill_config.py")
RUNTIME_CONFIG_PATH = os.path.join(config.BASE_DIR, "skill_runtime.py")


def _append_skill_log(line):
    """追加一条选卡记录到日志（复盘用：看每局实际点了哪些词条）

    日志路径 config.SKILL_PICK_LOG；写入失败不影响主流程。
    """
    try:
        # 确保 .logs/ 目录存在（auto_play 启动时已建，但单独跑 skills 时需自建）
        os.makedirs(os.path.dirname(config.SKILL_PICK_LOG), exist_ok=True)
        with open(config.SKILL_PICK_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _summary_line():
    """生成本局选卡汇总（用于对比不同局之间的词条组合质量）"""
    picked = config.SKILL_PICKED
    if not picked:
        return ""
    total = sum(picked.values())
    detail = "，".join(
        f"{name}×{cnt}" for name, cnt in sorted(picked.items(), key=lambda x: -x[1]))
    return f"--- 本局共选 {total} 次：{detail} ---"


def load_skill_config():
    """加载词条优先级配置（带缓存，支持热更新）。

    默认配置来自 git 托管的 skill_config.py；程序不直接修改它，而是首次运行时把其复制为
    非 git 托管的 skill_runtime.py，之后只读写 skill_runtime.py（失败调优改写它，下一局自动重载）。
    """
    config_path = RUNTIME_CONFIG_PATH

    # 运行时配置缺失 → 以默认配置为模板生成（首次运行 / 被手动删除后）
    if not os.path.exists(config_path):
        if not os.path.exists(SKILL_CONFIG_PATH):
            if config._skill_config_exists is False:
                return False
            config._skill_config_exists = False
            config._skill_config_mtime = None
            config.SKILL_PRIORITIES = {}
            return False
        try:
            with open(SKILL_CONFIG_PATH, encoding="utf-8") as f:
                src = f.read()
            with open(config_path, "w", encoding="utf-8") as f:
                f.write(src)
        except Exception as e:
            print(f"⚠️ 生成运行时配置 skill_runtime.py 失败: {e}")
            return False

    try:
        current_mtime = os.path.getmtime(config_path)
    except OSError:
        config.SKILL_PRIORITIES = {}
        return False

    if (config._skill_config_exists is True and
            config._skill_config_mtime == current_mtime and
            config._skill_config is not None):
        return True

    try:
        spec = importlib.util.spec_from_file_location("skill_runtime", config_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if hasattr(module, "strategy"):
            config.SKILL_STRATEGY = module.strategy
        config.SKILL_PRIORITIES = getattr(module, "priorities", {})
        config.SKILL_REQUIRES = getattr(module, "SKILL_REQUIRES", {})
        config.SKILL_PICK_DECAY = getattr(module, "PICK_DECAY", 0.5)
        config.SKILL_REQUIRE_DECAY = getattr(module, "REQUIRE_DECAY", 0.3)
        config._skill_config = module
        config._skill_config_mtime = current_mtime
        config._skill_config_exists = True
        return True
    except Exception as e:
        print(f"⚠️ 加载 skill_runtime.py 失败: {e}，保留当前配置")
        config.SKILL_PRIORITIES = {}
        config._skill_config_mtime = current_mtime
        config._skill_config_exists = True
        return False


def apply_enabled_series(series_list):
    """按系别组合列表合并优先级到 config.SKILL_PRIORITIES（不读文件，热生效）

    仅在内存切换预设，不修改 skill_config.py；元素系不在预设中，故不会误切流派。
    """
    mod = config._skill_config
    if mod is None:
        load_skill_config()
        mod = config._skill_config
    if mod is None:
        return
    priorities = {}
    for name in series_list:
        d = getattr(mod, name, None)
        if isinstance(d, dict):
            priorities.update(d)
        else:
            print(f"⚠️ 调优预设系别 '{name}' 未定义，跳过")
    config.SKILL_PRIORITIES = priorities


# ============================================================
# 失败自动调优：整组切换「流派」（复刻自 tuning/_loop127.py 的调优逻辑）
# 机制：失败时把运行时配置 skill_runtime.py 改写为下一流派（ENABLED_SERIES + 词条数值），
#       下一局选牌时 load_skill_config 自动重载生效；不停止、继续打同一关。
# 选牌机制核心（务必牢记，否则调优做成无用功）：
#   1) ENABLED_SERIES 不是过滤器，只是把哪些系别字典合并进 priorities；
#   2) 取分 = 精确匹配 key，否则 keyword in skill_name 部分匹配取最大值；
#   3) 决定选牌的是相对排序——必须把本流派具体词条抬高 + 通配兜底/别系压低，两手都要做。
# ============================================================
NO_WIND = ["PHYSICAL", "GENERAL", "CRIT", "SURVIVAL", "EMERGENCY"]
WITH_WIND = ["WIND", "PHYSICAL", "GENERAL", "CRIT", "SURVIVAL", "EMERGENCY"]
ELECTRIC_PHYSICAL = ["PHYSICAL", "ELECTRIC", "GENERAL", "CRIT", "SURVIVAL", "EMERGENCY"]

_NOISE = {
    "无人机": 60, "高速飞行": 60, "势不可挡": 60, "多维弹球": 60, "猛烈震荡": 60,
    "爆炸扩散": 60, "载具": 60, "重装机型": 60,
}
_WIND_DOWN = {
    "气刃": 60, "旋风加农": 60, "龙卷风": 60, "旋涡增压": 60, "风力加强": 60,
    "延长气流": 60, "压缩气刃": 60,
}
_VEHICLE_DOWN = {
    "装甲车": 60, "火车": 60, "连续出击": 60, "致残碾压": 60, "急速冲锋": 60,
    "致命冲撞": 60, "焦土策略": 60, "温压": 60, "温压弹": 60, "温压弹连发": 60,
}
_BULLET_DOWN = {
    "子弹爆炸": 60, "分裂子弹": 60, "分裂": 60, "四射": 60, "齐射": 60, "齐射+": 60,
    "连发+": 60, "连射": 60, "弹道": 60, "子弹": 60, "弹射": 60, "极速射击": 60,
    "伤害增幅": 60,
}


def _merge(*dicts):
    out = {}
    for d in dicts:
        out.update(d)
    return out


# 流派变体（V0 基线即默认配置；失败时从 V1 起整组切换，循环尝试直到通关）
VARIANTS = [
    {"name": "V0_基线", "enabled": None, "boosts": {}, "suppress": {}},

    # 139关·烈焰掌控者：生存优先 + 电系/物理双输出（首领弱点：闪电；20波BOSS一拳秒人）
    {"name": "E_139电物双流", "enabled": ["SURVIVAL", "ELECTRIC", "PHYSICAL", "EMERGENCY", "GENERAL", "CRIT"],
     "boosts": {
         "护盾": 160, "免疫": 158, "格挡": 158, "电磁穿刺": 158,
         "电极柱": 156, "子弹爆炸": 156, "紧急修复": 156,
         "电子跃迁": 154, "电磁爆炸": 154, "核能电磁": 154,
         "连发+": 154, "连发": 154, "连射": 154, "分裂子弹": 154, "齐射+": 154,
         "弹道": 152, "电磁追捕": 152, "电磁分流": 152,
         "充能电极": 152, "易损电极": 152, "额外电极+": 152, "生命虹吸": 152,
         "弹射": 150, "极速射击": 150, "电磁增伤": 150, "吸血": 150,
         "伤害增幅": 148, "电系伤害": 148, "电伤": 148, "生命": 148,
         "穿透": 146, "电击": 146, "电磁": 146, "回血": 146,
         "暴击伤害": 140},
     "suppress": _merge(_NOISE, _WIND_DOWN, _VEHICLE_DOWN, {
         "猛烈震荡": 40, "急速冲锋": 40, "致命冲撞": 40, "致残碾压": 40,
         "增伤": 100, "攻击力": 100, "攻击": 95, "攻速": 95})},


    # A：纯弹幕堆叠 —— 只吃"子弹"链路，靠同链路叠层把 DPS 顶起来
    {"name": "A_纯弹幕堆叠", "enabled": NO_WIND,
     "boosts": {
         "子弹爆炸": 160, "分裂子弹": 158, "四射": 156, "齐射+": 156, "齐射": 154,
         "连发+": 154, "连射": 154, "弹道": 152, "弹射": 150, "极速射击": 150,
         "伤害增幅": 148, "穿透": 146, "暴击伤害": 140},
     "suppress": _merge(_NOISE, _WIND_DOWN, _VEHICLE_DOWN, {
         "子弹": 118, "分裂": 118, "增伤": 100, "攻击力": 100, "攻击": 95,
         "攻速": 95, "生命": 60, "回血": 60})},

    # B：载具流 —— 装甲车→火车→焦土策略 一条链，AOE 与持续输出靠载具
    {"name": "B_载具流", "enabled": NO_WIND,
     "boosts": {
         "装甲车": 160, "火车": 158, "焦土策略": 156, "连续出击": 154, "载具": 152,
         "温压": 150, "温压弹": 148, "温压弹连发": 146, "致残碾压": 140,
         "急速冲锋": 140, "致命冲撞": 140, "猛烈震荡": 130, "穿透": 138},
     "suppress": _merge(_NOISE, _WIND_DOWN, _BULLET_DOWN, {
         "增伤": 100, "攻击力": 100, "生命": 60, "回血": 60})},

    # C：风系控场 —— 先控住再输出，用牵引/聚怪拖时间换输出窗口
    {"name": "C_风系控场", "enabled": WITH_WIND,
     "boosts": {
         "旋风加农": 160, "龙卷风": 158, "压缩气刃": 156, "气刃": 154,
         "旋涡增压": 154, "风力加强": 154, "延长气流": 150,
         "子弹爆炸": 132, "分裂子弹": 130, "穿透": 128},
     "suppress": _merge(_NOISE, _VEHICLE_DOWN, _BULLET_DOWN, {
         "增伤": 100, "攻击力": 100, "生命": 60, "回血": 60})},

    # D：生存优先 —— 先扛过"首领狂暴"，再谈输出
    {"name": "D_生存优先", "enabled": NO_WIND,
     "boosts": {
         "护盾": 160, "免疫": 158, "格挡": 158, "紧急修复": 152, "生命虹吸": 150,
         "吸血": 148, "生命": 146, "回血": 144,
         "子弹爆炸": 145, "分裂子弹": 143, "连发+": 143, "连射": 143,
         "齐射+": 142, "齐射": 142, "四射": 142, "穿透": 142, "弹射": 140},
     "suppress": _merge(_NOISE, _WIND_DOWN, _VEHICLE_DOWN, {
         "子弹": 118, "分裂": 118, "极速射击": 118, "弹道": 118, "伤害增幅": 118})},
]

_variant_base_src = None   # 启动时缓存的 skill_config.py 原始文本（用于改写时回溯，不累积）
_variant_index = 0         # 0 = 当前为基线(V0)；失败时推进到 1..len-1 循环


def _cache_base_src():
    """缓存启动时的 skill_config.py 原文，作为调优改写的回溯基线（不累积）"""
    global _variant_base_src
    if _variant_base_src is None:
        try:
            with open(SKILL_CONFIG_PATH, encoding="utf-8") as f:
                _variant_base_src = f.read()
        except Exception:
            _variant_base_src = ""


def _apply_variant_to_src(src, v):
    """把 variant 应用到 skill_config 文本：覆盖 ENABLED_SERIES + 抬高 boosts + 压低 suppress。"""
    if v.get("enabled") is not None:
        items = ", ".join(f'"{s}"' for s in v["enabled"])
        enabled_str = "ENABLED_SERIES = [\n    " + items + ",\n]"
        src, n = re.subn(r"ENABLED_SERIES = \[.*?\]", enabled_str, src, count=1, flags=re.S)
        if n == 0:
            print("⚠️ 未找到 ENABLED_SERIES，跳过启用列表覆盖")
    for group in ("boosts", "suppress"):
        for name, val in v.get(group, {}).items():
            pat = r'("' + re.escape(name) + r'":\s*)\d+'
            src, n = re.subn(pat, r'\g<1>' + str(val), src, count=0)
            if n == 0:
                print(f"⚠️ 调优：未找到词条「{name}」，跳过")
    return src


def _write_skill_config(src):
    """写回运行时配置 skill_runtime.py（非 git 托管），并强制下一局选牌重载生效"""
    with open(RUNTIME_CONFIG_PATH, "w", encoding="utf-8") as f:
        f.write(src)
    config._skill_config_mtime = None   # 下次 load_skill_config 必定重载新配置


def rotate_skill_on_defeat():
    """战斗失败后调用：整组切换到下一流派，写回 skill_config.py 热生效（下一局选牌自动重载）；
    不停止脚本，由 _on_defeat 点「再来一次」继续打同一关。

    失败一次 → 切下一个 variant（V1→V2→V3→V4→V1 循环）；通关 → reset 回 V0 基线。
    """
    global _variant_index
    n = len(VARIANTS)
    _variant_index = (_variant_index % (n - 1)) + 1   # 始终落在 1..n-1（跳过无效基线 V0）
    v = VARIANTS[_variant_index]
    _cache_base_src()
    _write_skill_config(_apply_variant_to_src(_variant_base_src, v))
    print(f"🔧 失败→切换流派「{v['name']}」，已写回 skill_runtime.py（下一局生效）")
    return v["name"]


def reset_skill_to_default():
    """通关后调用：恢复默认子弹流配置（V0 基线），并清空本局已选记录（下一关独立构建）"""
    global _variant_index
    _variant_index = 0
    _cache_base_src()
    if _variant_base_src:
        _write_skill_config(_variant_base_src)
    config.SKILL_PICKED = {}                     # 新关独立：清空上一关已选，避免跨关累积降权
    print("🔧 通关→恢复默认子弹流配置（V0 基线，写回 skill_runtime.py），已选记录已清空")


def ocr_skill_region(img):
    """对词条名称区域（SKILL_NAME_REGION，随分辨率缩放）裁剪并快速 OCR，结果存 config._skill_ocr_result"""
    if img is None:
        config._skill_ocr_result = None
        return None
    start_time = time.time()
    sx1, sy1, sx2, sy2 = scale_region(SKILL_NAME_REGION)
    if isinstance(img, Image.Image):
        cropped = img.crop((sx1, sy1, sx2, sy2))
    else:
        cropped = img[sy1:sy2, sx1:sx2, :]
        cropped = Image.fromarray(cropped)
    cropped_np = np.array(cropped)
    ocr_reader = vision.get_ocr_reader()
    result = ocr_reader.readtext(cropped_np, detail=1)
    adjusted_result = []
    for item in result:
        if len(item) >= 3:
            bbox, text, confidence = item[0], item[1], item[2]
            adjusted_bbox = [(p[0] + sx1, p[1] + sy1) for p in bbox]
            adjusted_result.append((adjusted_bbox, text, confidence))
    config._skill_ocr_result = adjusted_result
    elapsed = time.time() - start_time
    print(f"    ⚡ 词条区域裁剪OCR: {elapsed:.1f}s（{len(adjusted_result)}字）")
    return adjusted_result


def get_skill_names_from_ocr(debug=False):
    """从当前 OCR 结果中识别三个技能卡片的词条名称，返回 (left, middle, right)"""
    ocr_result = config._skill_ocr_result if config._skill_ocr_result else config._current_ocr_result
    if not ocr_result:
        if debug:
            print(f"    ⚠️  OCR结果为空")
        return "", "", ""

    left_texts = []
    middle_texts = []
    right_texts = []

    # y 过滤带与卡片 x 分界均随分辨率缩放
    _, band_y1, _, band_y2 = scale_region(SKILL_NAME_BAND)
    div1 = scale((SKILL_CARD_DIVIDERS[0], 0))[0]
    div2 = scale((SKILL_CARD_DIVIDERS[1], 0))[0]

    if debug:
        print(f"    📊 词条名称区域（y={band_y1}-{band_y2}）的OCR结果:")

    for item in ocr_result:
        if len(item) < 3:
            continue
        bbox, text, confidence = item[0], item[1], item[2]
        center_x = sum(p[0] for p in bbox) / 4
        center_y = sum(p[1] for p in bbox) / 4
        if center_y < band_y1 or center_y > band_y2:
            continue
        text_len = len(text.strip())
        if text_len > 20 or text_len < 2:
            continue
        if debug:
            print(f"       [{text}]({int(center_x)},{int(center_y)}) conf={confidence:.2f}")
        if center_x < div1:
            left_texts.append((text, confidence))
        elif center_x < div2:
            middle_texts.append((text, confidence))
        else:
            right_texts.append((text, confidence))

    def get_best_text(texts):
        if not texts:
            return ""
        MIN_CONFIDENCE = 0.2

        def is_valid_text(text):
            text = text.strip()
            if len(text) < 2 or len(text) > 15:
                return False
            if re.search(r'[@#$%^&*~|<>]', text):
                return False
            if re.match(r'^[0-9\W_]+$', text):
                return False
            if not re.search(r'[\u4e00-\u9fff]', text):
                return False
            return True

        def fix_text(text):
            text = text.strip()
            if '`' in text:
                text = text.replace('`', '弹球')
            text = text.replace('《', '').replace('》', '')
            return text.strip()

        valid_texts = [(fix_text(t), c) for t, c in texts if c >= MIN_CONFIDENCE and is_valid_text(t)]
        if not valid_texts:
            return ""
        texts_sorted = sorted(valid_texts, key=lambda x: x[1], reverse=True)
        return texts_sorted[0][0].strip()

    left_name = get_best_text(left_texts)
    middle_name = get_best_text(middle_texts)
    right_name = get_best_text(right_texts)

    if not left_name or not middle_name or not right_name:
        if debug:
            print(f"    ⚠️  部分卡片未识别到，扩大范围到600-800重试...")
        fallback_left = []
        fallback_middle = []
        fallback_right = []
        for item in ocr_result:
            if len(item) < 3:
                continue
            bbox, text, confidence = item[0], item[1], item[2]
            center_x = sum(p[0] for p in bbox) / 4
            center_y = sum(p[1] for p in bbox) / 4
            if center_y < 580 or center_y > 820:
                continue
            text_len = len(text.strip())
            if text_len > 25 or text_len < 2:
                continue
            if debug:
                print(f"       [兜底] [{text}]({int(center_x)},{int(center_y)}) conf={confidence:.2f}")
            if center_x < 360:
                fallback_left.append((text, confidence))
            elif center_x < 720:
                fallback_middle.append((text, confidence))
            else:
                fallback_right.append((text, confidence))
        if not left_name and fallback_left:
            left_name = get_best_text(fallback_left)
        if not middle_name and fallback_middle:
            middle_name = get_best_text(fallback_middle)
        if not right_name and fallback_right:
            right_name = get_best_text(fallback_right)

    if (not left_name or not middle_name or not right_name) and debug:
        missing = []
        if not left_name:
            missing.append("左")
        if not middle_name:
            missing.append("中")
        if not right_name:
            missing.append("右")
        print(f"    ❌ {('/'.join(missing))}卡片未识别到，打印所有OCR结果（共{len(ocr_result)}条）:")
        for item in ocr_result:
            if len(item) < 3:
                continue
            bbox, text, confidence = item[0], item[1], item[2]
            center_x = int(sum(p[0] for p in bbox) / 4)
            center_y = int(sum(p[1] for p in bbox) / 4)
            marker = " ⭐" if 580 <= center_y <= 820 else ""
            print(f"       [{text}]({center_x},{center_y}) conf={confidence:.2f}{marker}")

    if debug:
        print(f"    ✅ 最终识别: 左[{left_name}] 中[{middle_name}] 右[{right_name}]")

    return left_name, middle_name, right_name


def get_skill_priority(skill_name):
    """获取词条的动态优先级分数（基础分 × 已点降权 × 前置依赖降权），未配置返回 None"""
    if not skill_name:
        return None
    base = None
    matched_key = None
    if skill_name in config.SKILL_PRIORITIES:
        base = config.SKILL_PRIORITIES[skill_name]
        matched_key = skill_name
    else:
        for keyword, priority in config.SKILL_PRIORITIES.items():
            if keyword in skill_name:
                if base is None or priority > base:
                    base = priority
                    matched_key = keyword
    if base is None:
        return None
    score = float(base)
    # 已点降权：本局已点过该词条，次数越多分数越低
    picked = config.SKILL_PICKED.get(skill_name, 0)
    if picked > 0:
        score *= (config.SKILL_PICK_DECAY ** picked)
    # 前置依赖降权：依赖的核心词条本局尚未点过时，增伤类词条降权
    req = config.SKILL_REQUIRES.get(matched_key) or config.SKILL_REQUIRES.get(skill_name)
    if req:
        req_met = any(req == k or req in k or k in req for k in config.SKILL_PICKED)
        if not req_met:
            score *= config.SKILL_REQUIRE_DECAY
    return score


def do_select_skill():
    """按策略选技能卡片，返回 (pos_name, pos_coord, left, middle, right, reason[, selected, score])"""
    load_skill_config()

    # 跨关清空本局已点历史：in_battle_loop 由 False 变 True 视为新一关开始
    if config.in_battle_loop and not config._skill_picked_loop:
        # 先输出上一局汇总，再开启新一局（便于横向对比各局词条组合）
        summary = _summary_line()
        if summary:
            _append_skill_log(summary)
        config.SKILL_PICKED = {}
        _append_skill_log(f"\n=== 新一局 {time.strftime('%Y-%m-%d %H:%M:%S')} ===")
    config._skill_picked_loop = config.in_battle_loop

    if config.SKILL_STRATEGY != "priority":
        if config.SKILL_STRATEGY == "left":
            device.tap(CARD_LEFT)
            return "left", CARD_LEFT, "", "", "", "策略固定选左边", "", 0
        elif config.SKILL_STRATEGY == "right":
            device.tap(CARD_RIGHT)
            return "right", CARD_RIGHT, "", "", "", "策略固定选右边", "", 0
        elif config.SKILL_STRATEGY == "random":
            pos = random.choice([CARD_LEFT, CARD_MIDDLE, CARD_RIGHT])
            device.tap(pos)
            return "random", pos, "", "", "", "策略随机选择", "", 0
        else:
            device.tap(CARD_MIDDLE)
            return "middle", CARD_MIDDLE, "", "", "", "策略固定选中间", "", 0

    left_name, middle_name, right_name = get_skill_names_from_ocr(debug=False)
    failed_count = sum(1 for n in [left_name, middle_name, right_name] if not n)

    if failed_count > 0:
        print(f"    ⚠️  只识别到{3 - failed_count}/3个词条，重新截图确保截图正常...")
        retry_img = device.screenshot()
        if retry_img is not None:
            if config.in_battle_loop:
                vision.ocr_battle_loop(retry_img)
            else:
                vision.ocr_screenshot(retry_img)
            left_name, middle_name, right_name = get_skill_names_from_ocr(debug=False)
            failed_count = sum(1 for n in [left_name, middle_name, right_name] if not n)
            if failed_count == 0:
                print(f"    ✅ 重新截图后识别成功")
            else:
                print(f"    ⚠️  重新截图后仍有{failed_count}个词条未识别，尝试裁剪OCR兜底...")
        else:
            print(f"    ⚠️  无法获取截图，跳过重新截图")

    if failed_count > 0:
        print(f"    ⚠️  词条识别不全（{3 - failed_count}/3），尝试裁剪OCR兜底...")
        current_img = device.screenshot()
        if current_img is not None:
            ocr_skill_region(current_img)
            left_name, middle_name, right_name = get_skill_names_from_ocr(debug=False)
            failed_count = sum(1 for n in [left_name, middle_name, right_name] if not n)
            if failed_count == 0:
                print(f"    ✅ 裁剪OCR后识别成功")
            else:
                print(f"    ⚠️  裁剪OCR后仍有{failed_count}个词条未识别，使用已识别的结果继续")
        else:
            print(f"    ⚠️  无法获取截图，跳过裁剪OCR兜底")

    left_priority = get_skill_priority(left_name)
    middle_priority = get_skill_priority(middle_name)
    right_priority = get_skill_priority(right_name)

    configured = []
    if left_priority is not None:
        configured.append(("left", CARD_LEFT, left_name, left_priority))
    if middle_priority is not None:
        configured.append(("middle", CARD_MIDDLE, middle_name, middle_priority))
    if right_priority is not None:
        configured.append(("right", CARD_RIGHT, right_name, right_priority))

    if configured:
        configured.sort(key=lambda x: x[3], reverse=True)
        max_score = configured[0][3]
        top_candidates = [c for c in configured if c[3] == max_score]
        best = random.choice(top_candidates)
        device.tap(best[1])
        config.SKILL_PICKED[best[2]] = config.SKILL_PICKED.get(best[2], 0) + 1
        if len(top_candidates) > 1:
            reason = f"优先级最高({best[3]}分，{len(top_candidates)}个同分随机)，词条[{best[2]}]"
        else:
            reason = f"优先级最高({best[3]}分)，词条[{best[2]}]"
        _append_skill_log(
            f"[{time.strftime('%H:%M:%S')}] 选[{best[2]}] 分{best[3]:.1f} "
            f"| 候选[{left_name}|{middle_name}|{right_name}] | {reason}")
        return best[0], best[1], left_name, middle_name, right_name, reason, best[2], best[3]
    else:
        positions = [
            ("left", CARD_LEFT, left_name),
            ("middle", CARD_MIDDLE, middle_name),
            ("right", CARD_RIGHT, right_name),
        ]
        valid_positions = [p for p in positions if p[2]]
        if not valid_positions:
            valid_positions = positions
        chosen = random.choice(valid_positions)
        device.tap(chosen[1])
        if left_name or middle_name or right_name:
            reason = "词条均未配置，随机选择"
        else:
            reason = "OCR未识别到词条，回退随机选择"
        _append_skill_log(
            f"[{time.strftime('%H:%M:%S')}] 选[{chosen[2]}] 分0(随机) "
            f"| 候选[{left_name}|{middle_name}|{right_name}] | {reason}")
        return chosen[0], chosen[1], left_name, middle_name, right_name, reason, chosen[2], 0


# 模块加载时加载一次配置（保持原行为）
load_skill_config()
_cache_base_src()   # 缓存启动时 skill_config.py 原文，作为失败调优的回溯基线
