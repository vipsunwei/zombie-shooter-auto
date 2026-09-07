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


# ============================================================
#  stamina_below_confirmed（体力阈值复核，防 OCR 误读误停）
# ============================================================

def _patch_reads(monkeypatch, reads):
    it = iter(reads)
    monkeypatch.setattr(states, "get_stamina", lambda img: next(it))
    return lambda: None  # recheck_fn 桩，不再触发真实截图


def test_stamina_above_threshold_no_recheck(monkeypatch):
    # 首读达标 → 直接不停止，且不触发复核
    called = []
    monkeypatch.setattr(states, "get_stamina", lambda img: 44436)
    recheck = lambda: called.append(1)
    low, val = states.stamina_below_confirmed(None, 44000, recheck)
    assert low is False and val == 44436 and not called


def test_stamina_misread_corrected_by_recheck(monkeypatch):
    # 首读 4436（OCR 丢位误读），复核读回 44436 → 不停止
    recheck = _patch_reads(monkeypatch, [4436, 44436])
    low, val = states.stamina_below_confirmed(None, 44000, recheck)
    assert low is False and val == 44436


def test_stamina_confirmed_low_stops(monkeypatch):
    # 首读与两次复核均低于阈值 → 确认不足
    recheck = _patch_reads(monkeypatch, [4436, 4420, 4410])
    low, val = states.stamina_below_confirmed(None, 44000, recheck)
    assert low is True and val == 4436


def test_stamina_recheck_none_inconclusive(monkeypatch):
    # 复核读不到（None）→ 视为不确定，不停止，留待下轮再判
    recheck = _patch_reads(monkeypatch, [4436, None])
    low, val = states.stamina_below_confirmed(None, 44000, recheck)
    assert low is False and val == 4436


# ============================================================
#  get_stamina（拆块检测：宁可返回 None 也不返回缺位的低值）
# ============================================================

def _fake_reader(blocks):
    """构造假的 OCR 阅读器：blocks = [(x_min, x_max, text), ...]"""
    class _Reader:
        def readtext(self, img, detail=1):
            result = []
            for x_min, x_max, text in blocks:
                bbox = [(x_min, 0), (x_max, 0), (x_max, 10), (x_min, 10)]
                result.append((bbox, text, 0.99))
            return result
    return _Reader()


def _blank_img():
    from PIL import Image
    return Image.new("RGB", (1080, 1920), (0, 0, 0))


def test_get_stamina_single_block(monkeypatch):
    # 正常识别为单个文本块 '45139/50' → 取最大值 45139
    monkeypatch.setattr(states, "get_ocr_reader", lambda: _fake_reader([(0, 100, "45139/50")]))
    assert states.get_stamina(_blank_img()) == 45139


def test_get_stamina_split_blocks_returns_none(monkeypatch):
    # 实测故障：'45139/50' 被拆成横向重叠的 '4513' 与 '139/50'，
    # 取最大值会得到缺位的 4513 → 必须判定不可信，返回 None
    monkeypatch.setattr(
        states, "get_ocr_reader",
        lambda: _fake_reader([(25, 229, "4513"), (169, 441, "139/50")]))
    assert states.get_stamina(_blank_img()) is None


def test_get_stamina_adjacent_no_overlap(monkeypatch):
    # 两个不重叠的文本块（如数字与其右侧独立文字）不应被误判为拆分
    monkeypatch.setattr(
        states, "get_ocr_reader",
        lambda: _fake_reader([(0, 50, "45139"), (300, 380, "50")]))
    assert states.get_stamina(_blank_img()) == 45139


# ============================================================
#  is_patrol_claimable（满时间文案 / 时间正则）
# ============================================================

def _set_ocr(monkeypatch, text, x=(414, 651), y=(822, 854), conf=0.99):
    """把 config._current_ocr_result 设为单个文本块（坐标取自实机截图）"""
    box = [(x[0], y[0]), (x[1], y[0]), (x[1], y[1]), (x[0], y[1])]
    monkeypatch.setattr(config, "_current_ocr_result", [(box, text, conf)], raising=False)


def test_patrol_claimable_when_full_time(monkeypatch):
    # 满时间：游戏显示「已达到最大巡逻时间！」而非 HH:MM:SS，必须识别为可领取
    _set_ocr(monkeypatch, "已达到最大巡逻时间！")
    assert states.is_patrol_claimable() is True


def test_patrol_claimable_by_time_regex(monkeypatch):
    # 11 小时以上的正计时仍走原时间正则
    _set_ocr(monkeypatch, "11:30:00", x=(455, 625), y=(815, 870))
    assert states.is_patrol_claimable() is True

    _set_ocr(monkeypatch, "05:30:00", x=(455, 625), y=(815, 870))
    assert states.is_patrol_claimable() is False


def test_patrol_claimable_not_fooled_by_hint_text(monkeypatch):
    # 提示语「最长巡逻12小时…」含"巡逻"但不含"最大巡逻"，且在计时区之外，不应误判
    _set_ocr(monkeypatch, "最长巡逻12小时，章节越高，收益越大", x=(304, 788), y=(737, 770))
    assert states.is_patrol_claimable() is False
