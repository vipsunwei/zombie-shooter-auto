#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OCR 文字识别与波次像素辅助（RapidOCR 封装）

职责：
- RapidOCR 懒加载与 readtext 兼容封装
- 整图 / 战斗循环四级按需 OCR，结果缓存到 config._current_ocr_result
- 从 OCR 缓存中检索文字（has_text / find_text / get_text_position）
- 波次区像素统计（wave_white_ratio / is_wave_bright）与波次进度（get_wave_progress）

所有运行时可变状态通过 config.xxx 读写；常量通过 from config import * 使用。
"""

import time
import re
import numpy as np
from PIL import Image
from rapidocr_onnxruntime import RapidOCR

import config
from config import *


class RapidOCRWrapper:
    """RapidOCR 包装类，接口兼容 EasyOCR 的 readtext 方法"""

    def __init__(self):
        print("正在初始化RapidOCR模型（首次运行需下载，请稍候）...")
        self.ocr = RapidOCR()
        print("✅ RapidOCR初始化完成")

    def readtext(self, img, detail=1):
        """兼容 EasyOCR 的 readtext 接口，返回 [(bbox, text, confidence), ...]"""
        result, elapse = self.ocr(img)
        if result is None:
            return []
        converted = []
        for item in result:
            if len(item) >= 3:
                box, text, confidence = item[0], item[1], item[2]
                bbox = [tuple(p) for p in box]
                converted.append((bbox, text, confidence))
        return converted


def get_ocr_reader():
    """获取 OCR 阅读器（懒加载，只初始化一次）"""
    if config._ocr_reader is None:
        config._ocr_reader = RapidOCRWrapper()
    return config._ocr_reader


def set_current_ocr_result(result):
    """设置当前循环的 OCR 结果（主循环中调用一次，多个检测函数共享）"""
    config._current_ocr_result = result


def ocr_screenshot(img):
    """对截图进行 OCR 识别，返回识别结果列表，并缓存到全局变量"""
    reader = get_ocr_reader()
    result = reader.readtext(np.array(img))
    set_current_ocr_result(result)
    return result


def ocr_battle_loop(img):
    """战斗循环中的四级按需 OCR 加速（详见原实现注释）"""
    config._skill_ocr_result = None  # 清空词条区域裁剪 OCR 缓存，避免使用旧结果
    start_time = time.time()
    reader = get_ocr_reader()

    if isinstance(img, Image.Image):
        img_pil = img
    else:
        img_pil = Image.fromarray(img)

    # ========== 第0级：波次检测（判断是否在战斗中） ==========
    WAVE_X1, WAVE_X2 = 600, 1080
    WAVE_Y1, WAVE_Y2 = 0, 120
    region_wave = img_pil.crop((WAVE_X1, WAVE_Y1, WAVE_X2, WAVE_Y2))
    result_wave = reader.readtext(np.array(region_wave))
    adjusted_wave = []
    has_wave = False
    for item in result_wave:
        if len(item) >= 3:
            bbox, text, confidence = item[0], item[1], item[2]
            adjusted_bbox = [(p[0] + WAVE_X1, p[1] + WAVE_Y1) for p in bbox]
            adjusted_wave.append((adjusted_bbox, text, confidence))
            if confidence > 0.2 and "波次" in text:
                has_wave = True

    # 像素兜底：波次亮白时白色像素占比高，变灰/遮挡时为 0%
    if not has_wave:
        ratio = wave_white_ratio(img)
        if ratio > WAVE_WHITE_THRESHOLD:
            has_wave = True
        else:
            result_full = reader.readtext(np.array(img_pil))
            for item in result_full:
                if len(item) >= 3 and item[2] > 0.2 and "波次" in item[1]:
                    has_wave = True
                    break

    # ========== 第一级：区域1（选择技能 + 词条名称） ==========
    REGION1_Y1, REGION1_Y2 = 400, 750
    region1 = img_pil.crop((0, REGION1_Y1, 1080, REGION1_Y2))
    result1 = reader.readtext(np.array(region1))
    adjusted1 = []
    has_select_skill = False
    for item in result1:
        if len(item) >= 3:
            bbox, text, confidence = item[0], item[1], item[2]
            adjusted_bbox = [(p[0], p[1] + REGION1_Y1) for p in bbox]
            adjusted1.append((adjusted_bbox, text, confidence))
            if confidence > 0.5 and "选择技能" in text:
                has_select_skill = True

    if has_select_skill:
        result1 = adjusted1
        set_current_ocr_result(result1)
        config._wave_miss_count = 0
        elapsed = time.time() - start_time
        print(f"    ⚡ 四级OCR[1/4] 选择技能: {elapsed:.1f}s")
        return result1

    # ========== 第二级：区域2（精英掉落） ==========
    REGION2_X1, REGION2_X2 = 430, 650
    REGION2_Y1, REGION2_Y2 = 1270, 1400
    region2 = img_pil.crop((REGION2_X1, REGION2_Y1, REGION2_X2, REGION2_Y2))
    result2 = reader.readtext(np.array(region2))
    adjusted2 = []
    has_elite_drop = False
    for item in result2:
        if len(item) >= 3:
            bbox, text, confidence = item[0], item[1], item[2]
            adjusted_bbox = [(p[0] + REGION2_X1, p[1] + REGION2_Y1) for p in bbox]
            adjusted2.append((adjusted_bbox, text, confidence))
            if confidence > 0.3 and "精英掉落" in text:
                has_elite_drop = True

    if has_elite_drop:
        result2 = adjusted2
        set_current_ocr_result(result2)
        config._wave_miss_count = 0
        elapsed = time.time() - start_time
        print(f"    ⚡ 四级OCR[2/4] 精英掉落: {elapsed:.1f}s")
        return result2

    # ========== 第三级：小区域检测返回按钮（判断游戏是否结束） ==========
    REGION_CHECK_X1, REGION_CHECK_X2 = 100, 980
    REGION_CHECK_Y1, REGION_CHECK_Y2 = 1650, 1750
    region_check = img_pil.crop((REGION_CHECK_X1, REGION_CHECK_Y1, REGION_CHECK_X2, REGION_CHECK_Y2))
    result_check = reader.readtext(np.array(region_check))
    adjusted_check = []
    has_return_btn = False
    for item in result_check:
        if len(item) >= 3:
            bbox, text, confidence = item[0], item[1], item[2]
            adjusted_bbox = [(p[0] + REGION_CHECK_X1, p[1] + REGION_CHECK_Y1) for p in bbox]
            adjusted_check.append((adjusted_bbox, text, confidence))
            if confidence > 0.3 and "返回" in text:
                has_return_btn = True

    if not has_return_btn:
        if has_wave:
            config._wave_miss_count = 0
        else:
            config._wave_miss_count += 1
        set_current_ocr_result([])
        elapsed = time.time() - start_time
        print(f"    ⚡ 三级OCR[3/3] 战斗中: {elapsed:.1f}s（波次计数:{config._wave_miss_count}）")
        return []

    config._wave_miss_count = 0
    print(f"    ⚡ 四级OCR[3/4] 检测到返回按钮，继续检测结算区域...")

    # ========== 第四级：区域3（通关结算） ==========
    REGION3_Y1, REGION3_Y2 = 190, 1750
    region3 = img_pil.crop((0, REGION3_Y1, 1080, REGION3_Y2))
    result3 = reader.readtext(np.array(region3))
    adjusted3 = []
    for item in result3:
        if len(item) >= 3:
            bbox, text, confidence = item[0], item[1], item[2]
            adjusted_bbox = [(p[0], p[1] + REGION3_Y1) for p in bbox]
            adjusted3.append((adjusted_bbox, text, confidence))

    result3 = adjusted3
    set_current_ocr_result(result3)
    elapsed = time.time() - start_time
    print(f"    ⚡ 四级OCR[4/4] 通关结算: {elapsed:.1f}s（{len(result3)}字）")
    return result3


def has_text(keyword, region=None, min_confidence=0.4):
    """从当前 OCR 结果中检测是否包含指定关键词（支持部分匹配）"""
    result = config._current_ocr_result
    if result is None:
        return False
    for item in result:
        box, text, confidence = item
        if confidence < min_confidence:
            continue
        if keyword in text:
            if region:
                center_x = sum(p[0] for p in box) / 4
                center_y = sum(p[1] for p in box) / 4
                x1, y1, x2, y2 = scale_region(region)
                if x1 <= center_x <= x2 and y1 <= center_y <= y2:
                    return True
            else:
                return True
    return False


def find_text(keyword, min_confidence=0.4):
    """从当前 OCR 结果中查找关键词的位置，返回 (center_x, center_y) 或 None"""
    result = config._current_ocr_result
    if result is None:
        return None
    for item in result:
        box, text, confidence = item
        if confidence < min_confidence:
            continue
        if keyword in text:
            center_x = int(sum(p[0] for p in box) / 4)
            center_y = int(sum(p[1] for p in box) / 4)
            return (center_x, center_y)
    return None


def get_text_position(keyword, region=None, min_confidence=0.3):
    """从当前 OCR 结果中获取指定关键词的中心坐标，未找到返回 None"""
    result = config._current_ocr_result
    if result is None:
        return None
    for item in result:
        if len(item) < 3:
            continue
        box, text, confidence = item
        if confidence < min_confidence:
            continue
        if keyword in text:
            if region:
                x1, y1, x2, y2 = scale_region(region)
                center_x = sum(p[0] for p in box) / 4
                center_y = sum(p[1] for p in box) / 4
                if not (x1 <= center_x <= x2 and y1 <= center_y <= y2):
                    continue
            center_x = int(sum(p[0] for p in box) / 4)
            center_y = int(sum(p[1] for p in box) / 4)
            return (center_x, center_y)
    return None


# ============================================================
#  波次区像素 / 进度辅助（不依赖整图 OCR，零开销判定）
# ============================================================

def wave_white_ratio(img):
    """波次区白色像素占比（R>230,G>230,B>230），用于判定是否在战斗中。
    实测：纯战斗 6.71%~9.38%，关卡选择 1.71%，弹窗遮挡 0%。
    返回: 白色像素占比百分比(0~100)；img 为 None 或异常返回 0.0
    """
    if img is None:
        return 0.0
    x1, x2, y1, y2 = 770, 990, 10, 100
    if isinstance(img, Image.Image):
        cropped = img.crop((x1, y1, x2, y2))
    else:
        cropped = img[y1:y2, x1:x2, :]
        cropped = Image.fromarray(cropped)
    img_np = np.array(cropped)
    if img_np.shape[2] == 4:
        img_rgb = img_np[:, :, :3]
    else:
        img_rgb = img_np
    white_mask = (img_rgb[:, :, 0] > 230) & (img_rgb[:, :, 1] > 230) & (img_rgb[:, :, 2] > 230)
    return float(np.sum(white_mask) / (img_rgb.shape[0] * img_rgb.shape[1]) * 100)


def is_wave_bright(img):
    """检测波次文字是否为亮白色（游戏正常进行中）。
    亮白：白色像素(R>200,G>200,B>200)比例 > 3%；灰色（弹窗遮挡）：0%。
    """
    if img is None:
        return False
    x1, x2, y1, y2 = 790, 950, 20, 100
    if isinstance(img, Image.Image):
        cropped = img.crop((x1, y1, x2, y2))
    else:
        cropped = img[y1:y2, x1:x2, :]
        cropped = Image.fromarray(cropped)
    img_np = np.array(cropped)
    if img_np.shape[2] == 4:
        img_rgb = img_np[:, :, :3]
    else:
        img_rgb = img_np
    white_mask = (img_rgb[:, :, 0] > 200) & (img_rgb[:, :, 1] > 200) & (img_rgb[:, :, 2] > 200)
    white_ratio = np.sum(white_mask) / (img_rgb.shape[0] * img_rgb.shape[1]) * 100
    return bool(white_ratio > 3)


def get_wave_progress(img):
    """获取波次进度（如"7/20"），返回 (current, total)，识别失败返回 (None, None)"""
    if img is None:
        return None, None
    x1, x2, y1, y2 = 790, 950, 20, 100
    if isinstance(img, Image.Image):
        cropped = img.crop((x1, y1, x2, y2))
    else:
        cropped = img[y1:y2, x1:x2, :]
        cropped = Image.fromarray(cropped)
    cropped_np = np.array(cropped)
    ocr_reader = get_ocr_reader()
    result = ocr_reader.readtext(cropped_np, detail=1)
    if result:
        for item in result:
            if len(item) >= 3:
                text = item[1]
                match = re.search(r'(\d+)\s*/\s*(\d+)', text)
                if match:
                    return int(match.group(1)), int(match.group(2))
    return None, None
