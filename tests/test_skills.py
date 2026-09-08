#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""skills 模块单元测试：选卡日志记录与局末汇总"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import device
import skills


def test_do_select_skill_logs_configured_branch(tmp_path, monkeypatch):
    """按优先级选择分支：必须能正常返回且写入日志（reason 已赋值后才写）"""
    log_path = tmp_path / "p1.log"
    monkeypatch.setattr(config, "SKILL_PICK_LOG", str(log_path), raising=False)
    monkeypatch.setattr(device, "tap", lambda coord: None)
    monkeypatch.setattr(skills, "get_skill_names_from_ocr",
                        lambda debug=False: ("子弹爆炸", "连射", "分裂"))

    result = skills.do_select_skill()
    assert result[6] in ("子弹爆炸", "连射", "分裂")   # selected 词条名
    assert "选[" in log_path.read_text(encoding="utf-8")


def test_do_select_skill_logs_random_branch(tmp_path, monkeypatch):
    """全未配置走随机分支：同样必须先有 reason 再写日志"""
    log_path = tmp_path / "p2.log"
    monkeypatch.setattr(config, "SKILL_PICK_LOG", str(log_path), raising=False)
    monkeypatch.setattr(device, "tap", lambda coord: None)
    monkeypatch.setattr(skills, "get_skill_names_from_ocr",
                        lambda debug=False: ("未知甲", "未知乙", "未知丙"))

    result = skills.do_select_skill()
    assert result[6] in ("未知甲", "未知乙", "未知丙")
    assert "随机" in log_path.read_text(encoding="utf-8")


def test_summary_line(tmp_path, monkeypatch):
    """局末汇总：统计次数并按次数降序"""
    monkeypatch.setattr(config, "SKILL_PICKED", {"子弹爆炸": 3, "齐射+": 2}, raising=False)
    line = skills._summary_line()
    assert "共选 5 次" in line
    assert "子弹爆炸×3" in line and "齐射+×2" in line
    # 次数多的排前面
    assert line.index("子弹爆炸") < line.index("齐射+")


def test_summary_line_empty(monkeypatch):
    """未点过任何词条时不生成汇总"""
    monkeypatch.setattr(config, "SKILL_PICKED", {}, raising=False)
    assert skills._summary_line() == ""


def test_append_skill_log_writes_line(tmp_path, monkeypatch):
    # 把日志指向临时目录，避免污染仓库
    log_path = tmp_path / "skill_picks.log"
    monkeypatch.setattr(config, "SKILL_PICK_LOG", str(log_path), raising=False)

    skills._append_skill_log("[00:00:01] 选[子弹爆炸] 分139.0 | 优先级最高")

    assert log_path.exists()
    content = log_path.read_text(encoding="utf-8")
    assert "子弹爆炸" in content
    assert "139.0" in content


def test_append_skill_log_never_raises(tmp_path, monkeypatch):
    # 路径不可写时也必须静默失败，不能影响主流程
    bad_path = tmp_path / "no_such_dir" / "x.log"
    monkeypatch.setattr(config, "SKILL_PICK_LOG", str(bad_path), raising=False)

    skills._append_skill_log("任意内容")  # 不应抛异常
