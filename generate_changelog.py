#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动生成 CHANGELOG.md
=====================
基于 git commit 记录自动生成 changelog，根据关键词自动分类为新增/修复/优化/文档等。

使用方法：
  python generate_changelog.py           # 生成从上一个 tag 到现在的 changelog
  python generate_changelog.py --all     # 生成全部历史的 changelog
  python generate_changelog.py --dry-run # 只打印不写入文件
"""

import subprocess
import re
import sys
from datetime import datetime

# 分类规则：关键词 → 分类
CATEGORY_RULES = [
    {
        "name": "新增",
        "keywords": ["增加", "新增", "添加", "实现", "支持", "feat", "feature", "加了"],
        "emoji": "✨"
    },
    {
        "name": "修复",
        "keywords": ["修复", "修", "bug", "解决", "fix", "bugfix", "hotfix", "修正"],
        "emoji": "🐛"
    },
    {
        "name": "优化",
        "keywords": ["优化", "改进", "提升", "重构", "refactor", "perf", "performance", "调整"],
        "emoji": "⚡"
    },
    {
        "name": "文档",
        "keywords": ["文档", "readme", "说明", "docs", "documentation", "changelog"],
        "emoji": "📝"
    },
    {
        "name": "格式",
        "keywords": ["格式", "style", "format", "lint", "代码风格"],
        "emoji": "🎨"
    },
    {
        "name": "测试",
        "keywords": ["测试", "test", "单元测试"],
        "emoji": "✅"
    },
    {
        "name": "构建",
        "keywords": ["构建", "build", "ci", "cd", "部署", "release", "发布", "chore", "依赖"],
        "emoji": "🔧"
    },
]

# 其他分类
OTHER_CATEGORY = {
    "name": "其他",
    "emoji": "📦"
}


def run_cmd(cmd, capture_output=True):
    """执行命令，返回输出"""
    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=capture_output,
        text=True,
        encoding='utf-8'
    )
    return result.stdout.strip()


def get_last_tag():
    """获取最近的 tag"""
    return run_cmd("git describe --tags --abbrev=0 2>nul")


def get_commits_since_tag(tag=None):
    """获取从指定 tag 到现在的 commit 列表"""
    if tag:
        log_range = f"{tag}..HEAD"
    else:
        log_range = "HEAD"

    # 获取 commit 列表：hash|date|message
    output = run_cmd(f'git log {log_range} --pretty=format:"%h|%ad|%s" --date=short')

    commits = []
    for line in output.split('\n'):
        line = line.strip()
        if not line:
            continue
        parts = line.split('|', 2)
        if len(parts) == 3:
            commits.append({
                'hash': parts[0],
                'date': parts[1],
                'message': parts[2]
            })
    return commits


def categorize_commit(message):
    """根据 commit message 分类"""
    message_lower = message.lower()
    for category in CATEGORY_RULES:
        for keyword in category['keywords']:
            if keyword.lower() in message_lower:
                return category
    return OTHER_CATEGORY


def generate_changelog_content(commits, version=None, date=None):
    """生成 changelog 内容"""
    if not commits:
        return "（暂无变更）\n"

    # 按分类分组
    categorized = {}
    for commit in commits:
        category = categorize_commit(commit['message'])
        cat_name = category['name']
        if cat_name not in categorized:
            categorized[cat_name] = {
                'emoji': category['emoji'],
                'commits': []
            }
        categorized[cat_name]['commits'].append(commit)

    # 生成内容
    lines = []

    # 按固定顺序输出分类
    category_order = ["新增", "修复", "优化", "文档", "格式", "测试", "构建", "其他"]
    for cat_name in category_order:
        if cat_name in categorized:
            cat = categorized[cat_name]
            lines.append(f"### {cat['emoji']} {cat_name}")
            lines.append("")
            for commit in cat['commits']:
                lines.append(f"- {commit['message']} ({commit['hash']})")
            lines.append("")

    return '\n'.join(lines)


def update_changelog_file(content, version=None, date=None):
    """更新 CHANGELOG.md 文件"""
    changelog_path = "CHANGELOG.md"

    # 读取现有文件
    try:
        with open(changelog_path, 'r', encoding='utf-8') as f:
            existing = f.read()
    except FileNotFoundError:
        existing = """# Changelog

所有显著变更都记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [未发布]

"""

    # 生成版本标题
    if version and date:
        version_header = f"## [{version}] - {date}"
    else:
        version_header = "## [未发布]"

    # 查找 [未发布] 部分并替换
    pattern = r'## \[未发布\]\s*\n(.*?)(?=\n## \[|\Z)'
    match = re.search(pattern, existing, re.DOTALL)

    if match:
        # 替换 [未发布] 部分的内容
        new_content = existing[:match.start(1)] + "\n" + content + "\n" + existing[match.end(1):]
    else:
        # 没有找到 [未发布]，在文件开头添加
        new_content = f"## [未发布]\n\n{content}\n\n" + existing

    # 写入文件
    with open(changelog_path, 'w', encoding='utf-8') as f:
        f.write(new_content)

    return changelog_path


def main():
    # 解析参数
    dry_run = "--dry-run" in sys.argv
    show_all = "--all" in sys.argv

    print("=" * 55)
    print("  向僵尸开炮 · 自动生成 CHANGELOG")
    print("=" * 55)
    print()

    # 获取 commit 列表
    if show_all:
        print("📋 获取全部历史 commit...")
        commits = get_commits_since_tag(None)
    else:
        last_tag = get_last_tag()
        if last_tag:
            print(f"📋 获取从 tag {last_tag} 到现在的 commit...")
            commits = get_commits_since_tag(last_tag)
        else:
            print("📋 未找到 tag，获取全部历史 commit...")
            commits = get_commits_since_tag(None)

    print(f"   共 {len(commits)} 个 commit")
    print()

    if not commits:
        print("✅ 没有新的变更，无需更新 changelog")
        return

    # 生成 changelog 内容
    print("🔍 分析 commit 并分类...")
    content = generate_changelog_content(commits)
    print()

    # 打印生成的内容
    print("📝 生成的 changelog 内容：")
    print("-" * 55)
    print(content)
    print("-" * 55)
    print()

    if dry_run:
        print("🔍 dry-run 模式，未写入文件")
        return

    # 写入文件
    changelog_path = update_changelog_file(content)
    print(f"✅ 已更新 {changelog_path}")
    print()
    print("💡 提示：发版时执行 `python release.py patch` 会自动生成 changelog 并发布")


if __name__ == "__main__":
    main()
