#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""config 模块单元测试：坐标缩放与常量导出"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config


def setup_function():
    # 每个用例前后都复位到基准分辨率
    config.screen_w, config.screen_h = 1080, 1920


def test_scale_identity_at_base_resolution():
    config.screen_w, config.screen_h = 1080, 1920
    assert config.scale((540, 960)) == (540, 960)


def test_scale_double_resolution():
    config.screen_w, config.screen_h = 2160, 3840
    assert config.scale((540, 960)) == (1080, 1920)


def test_scale_half_resolution():
    config.screen_w, config.screen_h = 540, 960
    assert config.scale((540, 960)) == (270, 480)


def test_scale_region():
    config.screen_w, config.screen_h = 540, 960
    assert config.scale_region((0, 0, 1080, 1920)) == (0, 0, 540, 960)


def test_runtime_var_not_exported_in_all():
    # 运行时可变状态不应经 from config import * 导出，避免拿到旧副本
    assert "screen_w" not in config.__all__
    assert "EMULATOR_TYPE" not in config.__all__


def test_constants_exported_in_all():
    assert "CARD_LEFT" in config.__all__
    assert "scale" in config.__all__
    assert "CHEST_REGIONS" in config.__all__
