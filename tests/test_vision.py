#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""vision 模块单元测试：OCR 缓存检索与波次像素辅助（合成图片，无需真 OCR/截图）"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from PIL import Image

import config
import vision


def _set(boxes):
    config._current_ocr_result = boxes


def test_has_text_match():
    _set([([(100, 100), (200, 100), (200, 150), (100, 150)], "选择技能", 0.9)])
    assert vision.has_text("选择技能") is True
    assert vision.has_text("波次") is False


def test_has_text_region_filter():
    _set([([(100, 100), (200, 100), (200, 150), (100, 150)], "返回", 0.9)])
    # 该框中心(150,125)不在区域(500,1600,1030,1800)
    assert vision.has_text("返回", region=(500, 1600, 1030, 1800)) is False
    assert vision.has_text("返回") is True


def test_has_text_confidence_threshold():
    _set([([(100, 100), (200, 100), (200, 150), (100, 150)], "开始游戏", 0.05)])
    assert vision.has_text("开始游戏", min_confidence=0.5) is False


def test_find_text():
    _set([([(100, 100), (200, 100), (200, 150), (100, 150)], "双倍奖励", 0.8)])
    assert vision.find_text("双倍奖励") == (150, 125)
    assert vision.find_text("不存在") is None


def test_get_text_position_region():
    _set([([(100, 100), (200, 100), (200, 150), (100, 150)], "完美通关", 0.7)])
    # 中心(150,125)不在 region(300,320,800,430)
    assert vision.get_text_position("完美通关", region=(300, 320, 800, 430)) is None
    assert vision.get_text_position("完美通关") == (150, 125)


def test_wave_white_ratio_white():
    img = Image.new("RGB", (1080, 1920), (255, 255, 255))
    assert vision.wave_white_ratio(img) > 3.5


def test_wave_white_ratio_black():
    img = Image.new("RGB", (1080, 1920), (0, 0, 0))
    assert vision.wave_white_ratio(img) == 0.0


def test_is_wave_bright():
    white = Image.new("RGB", (1080, 1920), (255, 255, 255))
    black = Image.new("RGB", (1080, 1920), (0, 0, 0))
    assert vision.is_wave_bright(white) is True
    assert vision.is_wave_bright(black) is False


def test_wave_white_ratio_none_returns_zero():
    assert vision.wave_white_ratio(None) == 0.0
