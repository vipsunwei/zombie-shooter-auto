#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rewards 模块单元测试：今日剩余次数解析（注入假 OCR 结果）"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import rewards


def test_today_remaining_count_full():
    config._current_ocr_result = [
        ([(1, 1), (2, 1), (2, 2), (1, 2)], "今日剩余次数3/3", 0.9)
    ]
    assert rewards.get_today_remaining_count() == (3, 3)


def test_today_remaining_count_zero():
    config._current_ocr_result = [
        ([(1, 1), (2, 1), (2, 2), (1, 2)], "今日剩余次数0/3", 0.9)
    ]
    assert rewards.get_today_remaining_count() == (0, 3)


def test_today_remaining_count_none():
    config._current_ocr_result = None
    assert rewards.get_today_remaining_count() is None


def test_today_remaining_count_no_match():
    config._current_ocr_result = [
        ([(1, 1), (2, 1), (2, 2), (1, 2)], "其他文字", 0.9)
    ]
    assert rewards.get_today_remaining_count() is None
