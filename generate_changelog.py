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
        "name": "重构",
        "keywords": ["重构", "refactor", "重写", "拆分", "提取"],
        "emoji": "🔧"
    },
    {
        "name": "修复",
        "keywords": ["修复", "bug", "解决", "fix", "bugfix", "hotfix", "修正", "修补"],
        "emoji": "🐛"
    },
    {
        "name": "优化",
        "keywords": ["优化", "改进", "提升", "perf", "performance", "调整"],
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
        "emoji": "🔨"
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


# commit message 前缀到分类名的映射（优先匹配）
PREFIX_TO_CATEGORY = {
    'feat': '新增',
    'feature': '新增',
    'fix': '修复',
    'bugfix': '修复',
    'hotfix': '修复',
    'refactor': '重构',
    'perf': '优化',
    'performance': '优化',
    'docs': '文档',
    'documentation': '文档',
    'style': '格式',
    'format': '格式',
    'test': '测试',
    'build': '构建',
    'ci': '构建',
    'cd': '构建',
    'chore': '构建',
    'release': '构建',
}


def categorize_commit(message):
    """根据 commit message 分类
    优先检查 commit message 前缀（如 feat:、fix:、refactor:），
    前缀匹配不到再用关键词匹配。
    """
    message_lower = message.lower().strip()

    # 1. 优先检查前缀（如 "feat: xxx"、"fix(scope): xxx"）
    prefix_match = re.match(r'^([a-z]+)(\([^)]*\))?\s*:', message_lower)
    if prefix_match:
        prefix = prefix_match.group(1)
        if prefix in PREFIX_TO_CATEGORY:
            cat_name = PREFIX_TO_CATEGORY[prefix]
            for category in CATEGORY_RULES:
                if category['name'] == cat_name:
                    return category

    # 2. 前缀匹配不到，再用关键词匹配
    for category in CATEGORY_RULES:
        for keyword in category['keywords']:
            if keyword.lower() in message_lower:
                return category
    return OTHER_CATEGORY


def clean_commit_message(message):
    """清理 commit message，去掉 conventional commit 前缀（如 feat:、fix:、refactor(scope):）"""
    # 匹配前缀：type(scope): 或 type:
    match = re.match(r'^[a-z]+(\([^)]*\))?\s*:\s*(.*)$', message, re.IGNORECASE)
    if match:
        return match.group(2).strip()
    return message.strip()


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
    category_order = ["新增", "重构", "修复", "优化", "文档", "格式", "测试", "构建", "其他"]
    for cat_name in category_order:
        if cat_name in categorized:
            cat = categorized[cat_name]
            lines.append(f"### {cat['emoji']} {cat_name}")
            lines.append("")
            for commit in cat['commits']:
                # 清理 commit message，去掉前缀
                clean_msg = clean_commit_message(commit['message'])
                lines.append(f"- {clean_msg} ({commit['hash']})")
            lines.append("")

    return '\n'.join(lines)


def update_changelog_file(content, version=None, date=None):
    """更新 CHANGELOG.md 文件
    查找 [未发布] 部分并替换其内容；如果不存在，则在文件头部说明之后插入
    """
    changelog_path = "CHANGELOG.md"

    # 读取现有文件
    try:
        with open(changelog_path, 'r', encoding='utf-8') as f:
            existing = f.read()
    except FileNotFoundError:
        existing = """# 更新日志

本项目所有重要变更都记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [未发布]

"""

    # 确保内容前后有空行
    content = content.strip()
    if content:
        content = "\n" + content + "\n"

    # 查找 [未发布] 标题行（行首匹配，避免匹配到链接等其他内容）
    # 匹配 ## [未发布] 后面的所有内容，直到下一个 ## [ 标题或文件结束
    pattern = r'(^## \[未发布\][ \t]*\n)(.*?)(?=^## \[|\Z)'
    match = re.search(pattern, existing, re.MULTILINE | re.DOTALL)

    if match:
        # 替换 [未发布] 部分的内容（保留标题行）
        new_content = existing[:match.start(2)] + content + existing[match.end(2):]
    else:
        # 没有找到 [未发布]，在第一个 ## [ 版本标题之前插入
        first_version_match = re.search(r'^## \[', existing, re.MULTILINE)
        if first_version_match:
            # 在第一个版本标题之前插入 [未发布] 部分
            insert_pos = first_version_match.start()
            new_content = existing[:insert_pos] + f"## [未发布]\n{content}\n" + existing[insert_pos:]
        else:
            # 没有任何版本标题，在文件末尾添加
            new_content = existing.rstrip() + f"\n\n## [未发布]\n{content}\n"

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
