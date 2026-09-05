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


def load_skill_config():
    """加载词条优先级配置文件 skill_config.py（带缓存优化，支持热更新）"""
    config_path = os.path.join(config.BASE_DIR, "skill_config.py")
    file_exists = os.path.exists(config_path)

    if not file_exists:
        if config._skill_config_exists is False:
            return False
        config._skill_config_exists = False
        config._skill_config_mtime = None
        config.SKILL_PRIORITIES = {}
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
        spec = importlib.util.spec_from_file_location("skill_config", config_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if hasattr(module, "strategy"):
            config.SKILL_STRATEGY = module.strategy
        config.SKILL_PRIORITIES = getattr(module, "priorities", {})
        config._skill_config = module
        config._skill_config_mtime = current_mtime
        config._skill_config_exists = True
        return True
    except Exception as e:
        print(f"⚠️  加载 skill_config.py 失败: {e}，保留当前配置")
        config.SKILL_PRIORITIES = {}
        config._skill_config_mtime = current_mtime
        config._skill_config_exists = True
        return False


def ocr_skill_region(img):
    """对词条名称区域（y=610-760）进行裁剪并快速 OCR，结果存 config._skill_ocr_result"""
    if img is None:
        config._skill_ocr_result = None
        return None
    start_time = time.time()
    if isinstance(img, Image.Image):
        cropped = img.crop((0, 610, 1080, 760))
    else:
        cropped = img[610:760, :, :]
        cropped = Image.fromarray(cropped)
    cropped_np = np.array(cropped)
    ocr_reader = vision.get_ocr_reader()
    result = ocr_reader.readtext(cropped_np, detail=1)
    adjusted_result = []
    for item in result:
        if len(item) >= 3:
            bbox, text, confidence = item[0], item[1], item[2]
            adjusted_bbox = [(p[0], p[1] + 610) for p in bbox]
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

    if debug:
        print(f"    📊 词条名称区域（y=600-800）的OCR结果:")

    for item in ocr_result:
        if len(item) < 3:
            continue
        bbox, text, confidence = item[0], item[1], item[2]
        center_x = sum(p[0] for p in bbox) / 4
        center_y = sum(p[1] for p in bbox) / 4
        if center_y < 620 or center_y > 780:
            continue
        text_len = len(text.strip())
        if text_len > 20 or text_len < 2:
            continue
        if debug:
            print(f"       [{text}]({int(center_x)},{int(center_y)}) conf={confidence:.2f}")
        if center_x < 360:
            left_texts.append((text, confidence))
        elif center_x < 720:
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
    """获取词条的优先级分数（支持部分匹配），未配置返回 None"""
    if not skill_name:
        return None
    if skill_name in config.SKILL_PRIORITIES:
        return config.SKILL_PRIORITIES[skill_name]
    best_priority = None
    for keyword, priority in config.SKILL_PRIORITIES.items():
        if keyword in skill_name:
            if best_priority is None or priority > best_priority:
                best_priority = priority
    return best_priority


def do_select_skill():
    """按策略选技能卡片，返回 (pos_name, pos_coord, left, middle, right, reason[, selected, score])"""
    load_skill_config()

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
        if len(top_candidates) > 1:
            reason = f"优先级最高({best[3]}分，{len(top_candidates)}个同分随机)，词条[{best[2]}]"
        else:
            reason = f"优先级最高({best[3]}分)，词条[{best[2]}]"
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
        return chosen[0], chosen[1], left_name, middle_name, right_name, reason, chosen[2], 0


# 模块加载时加载一次配置（保持原行为）
load_skill_config()
