#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""auto_play 入口辅助单元测试：模拟器名称归一化"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import auto_play


def test_normalize_emulator_ldplayer_aliases():
    assert auto_play._normalize_emulator("ld") == "ldplayer"
    assert auto_play._normalize_emulator("leidian") == "ldplayer"
    assert auto_play._normalize_emulator("ldplayer") == "ldplayer"
    assert auto_play._normalize_emulator("雷电") == "ldplayer"


def test_normalize_emulator_mumu_aliases():
    assert auto_play._normalize_emulator("mumu") == "mumu"
    assert auto_play._normalize_emulator("mu") == "mumu"
    assert auto_play._normalize_emulator("网易") == "mumu"


def test_normalize_emulator_auto():
    assert auto_play._normalize_emulator("auto") == "auto"
    assert auto_play._normalize_emulator("自动") == "auto"


def test_normalize_emulator_unknown_defaults_mumu():
    assert auto_play._normalize_emulator("unknown_xyz") == "mumu"
