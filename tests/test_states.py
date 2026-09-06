#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""states 模块单元测试：宝箱发光像素判定（合成图片，无需真截图）"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from PIL import Image

import config
import states


def test_is_chest_glowing_gold():
    img = Image.new("RGB", (1080, 1920), (0, 0, 0))
    arr = np.array(img)
    x1, y1, x2, y2 = config.CHEST_REGIONS["完美通关"]
    arr[y1:y2, x1:x2] = (255, 200, 50)  # 整块填金
    gold_img = Image.fromarray(arr)
    assert states.is_chest_glowing(gold_img, "完美通关") is True


def test_is_chest_glowing_black():
    black = Image.new("RGB", (1080, 1920), (0, 0, 0))
    assert states.is_chest_glowing(black, "完美通关") is False


def test_is_chest_glowing_unknown_name():
    img = Image.new("RGB", (1080, 1920), (255, 200, 50))
    assert states.is_chest_glowing(img, "不存在的宝箱") is False


def test_get_glowing_chests():
    # 三个宝箱检测区水平排列互不重叠，
    # 逐个构造纯黑图、仅把对应宝箱区涂成金色，验证各自能被正确识别为发光
    for name in ["成功通关", "50%血量通关", "完美通关"]:
        img = Image.new("RGB", (1080, 1920), (0, 0, 0))
        arr = np.array(img)
        x1, y1, x2, y2 = config.CHEST_REGIONS[name]
        arr[y1:y2, x1:x2] = (255, 200, 50)
        gold_img = Image.fromarray(arr)
        glowing = states.get_glowing_chests(gold_img)
        assert name in glowing, f"{name} 应被识别为发光，实际: {glowing}"
