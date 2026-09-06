#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cli 入口辅助单元测试：模拟器名称归一化"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cli


def test_normalize_emulator_ldplayer_aliases():
    assert cli._normalize_emulator("ld") == "ldplayer"
    assert cli._normalize_emulator("leidian") == "ldplayer"
    assert cli._normalize_emulator("ldplayer") == "ldplayer"
    assert cli._normalize_emulator("雷电") == "ldplayer"


def test_normalize_emulator_mumu_aliases():
    assert cli._normalize_emulator("mumu") == "mumu"
    assert cli._normalize_emulator("mu") == "mumu"
    assert cli._normalize_emulator("网易") == "mumu"


def test_normalize_emulator_auto():
    assert cli._normalize_emulator("auto") == "auto"
    assert cli._normalize_emulator("自动") == "auto"


def test_normalize_emulator_unknown_defaults_mumu():
    assert cli._normalize_emulator("unknown_xyz") == "mumu"
