#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Changelog 工具函数
==================
被 release.py 和 preview_changelog.py 共同引用，确保预览和真实发版的逻辑完全一致。
"""

import re
import os
from datetime import datetime


def get_current_version():
    """从 version.py 读取当前版本号"""
    version_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'version.py')
    with open(version_path, 'r', encoding='utf-8') as f:
        content = f.read()
    match = re.search(r'__version__\s*=\s*"([^"]+)"', content)
    if match:
        return match.group(1)
    return "0.0.0"


def calculate_new_version(current_version, version_type):
    """计算新版本号"""
    major, minor, patch = map(int, current_version.split('.'))
    if version_type == 'major':
        major += 1
        minor = 0
        patch = 0
    elif version_type == 'minor':
        minor += 1
        patch = 0
    else:  # patch
        patch += 1
    return f"{major}.{minor}.{patch}"


def clean_commit_message(message):
    """清理 commit message，去掉 conventional commit 前缀（如 feat:、fix:、refactor(scope):）"""
    match = re.match(r'^[a-z]+(\([^)]*\))?\s*:\s*(.*)$', message, re.IGNORECASE)
    if match:
        return match.group(2).strip()
    return message.strip()


def update_changelog_version(new_version, changelog_path=None):
    """手动更新 CHANGELOG.md 的版本号（不依赖 bump2version）
    把 ## [未发布] 改成 ## [新版本号 - 日期]，并在上面添加新的空的 ## [未发布]

    返回: (success: bool, message: str)
    """
    if changelog_path is None:
        changelog_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'CHANGELOG.md')

    today = datetime.now().strftime('%Y-%m-%d')

    # 读取现有文件
    try:
        with open(changelog_path, 'r', encoding='utf-8') as f:
            existing = f.read()
    except FileNotFoundError:
        return False, "CHANGELOG.md 不存在"

    # 查找 ## [未发布] 标题行
    pattern = r'(^## \[未发布\][ \t]*\n)(.*?)(?=^## \[|\Z)'
    match = re.search(pattern, existing, re.MULTILINE | re.DOTALL)

    if not match:
        return False, "未找到 ## [未发布] 标题，无法更新版本号"

    # 获取 [未发布] 下面的内容
    unreleased_content = match.group(2).strip()

    # 如果 [未发布] 下面没有内容（只有"暂无变更"），则新版本号下面也显示"暂无变更"
    if not unreleased_content or unreleased_content == "（暂无变更）":
        unreleased_content = "（暂无变更）"

    # 构造新的 changelog：
    # 新的空的 ## [未发布] + 新版本号标题 + 原来的内容
    new_unreleased = "## [未发布]\n\n（暂无变更）\n\n"
    version_section = f"## [{new_version}] - {today}\n\n{unreleased_content}\n\n"

    # 替换正文部分
    new_content = existing[:match.start(1)] + new_unreleased + version_section + existing[match.end(2):]

    # 更新底部的链接定义
    # 1. 获取当前版本号（用于更新 [未发布] 的 compare 链接）
    current_version = get_current_version()
    # 2. 更新 [未发布] 的链接：把 compare/v{current}...HEAD 改成 compare/v{new}...HEAD
    old_unreleased_link = f"[未发布]: https://github.com/vipsunwei/zombie-shooter-auto/compare/v{current_version}...HEAD"
    new_unreleased_link = f"[未发布]: https://github.com/vipsunwei/zombie-shooter-auto/compare/v{new_version}...HEAD"
    if old_unreleased_link in new_content:
        new_content = new_content.replace(old_unreleased_link, new_unreleased_link)
    # 3. 在 [未发布] 链接下面添加新版本号的链接定义
    new_version_link = f"[{new_version}]: https://github.com/vipsunwei/zombie-shooter-auto/releases/tag/v{new_version}"
    if new_version_link not in new_content:
        # 在 [未发布] 链接后面插入
        new_content = new_content.replace(
            new_unreleased_link,
            f"{new_unreleased_link}\n{new_version_link}"
        )

    # 写入文件
    with open(changelog_path, 'w', encoding='utf-8') as f:
        f.write(new_content)

    # 验证：检查新版本号标题和链接定义是否存在
    title_ok = f"## [{new_version}] - {today}" in new_content
    link_ok = f"[{new_version}]: https://github.com/vipsunwei/zombie-shooter-auto/releases/tag/v{new_version}" in new_content
    if title_ok and link_ok:
        return True, f"CHANGELOG 版本号更新成功：## [{new_version}] - {today}（含链接定义）"
    else:
        return False, "CHANGELOG 版本号更新失败，验证不通过"


def simulate_changelog_update(new_version, changelog_path=None, unreleased_content=None):
    """模拟更新 CHANGELOG.md 的版本号（不修改文件，只返回预览内容）
    用于 release.py --dry-run 预览

    参数:
        new_version: 新版本号
        changelog_path: CHANGELOG.md 路径（可选，默认自动查找）
        unreleased_content: 预先生成的 [未发布] 内容（可选，提供则用此内容替换当前 [未发布]）

    返回: (success: bool, preview_content: str, message: str)
    """
    if changelog_path is None:
        changelog_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'CHANGELOG.md')

    today = datetime.now().strftime('%Y-%m-%d')

    # 读取现有文件
    try:
        with open(changelog_path, 'r', encoding='utf-8') as f:
            existing = f.read()
    except FileNotFoundError:
        return False, "", "CHANGELOG.md 不存在"

    # 查找 ## [未发布] 标题行
    pattern = r'(^## \[未发布\][ \t]*\n)(.*?)(?=^## \[|\Z)'
    match = re.search(pattern, existing, re.MULTILINE | re.DOTALL)

    if not match:
        return False, existing, "未找到 ## [未发布] 标题"

    # 获取 [未发布] 下面的内容
    if unreleased_content is not None:
        # 使用预先生成的内容
        unreleased_content = unreleased_content.strip()
    else:
        # 读取当前 [未发布] 下面的内容
        unreleased_content = match.group(2).strip()

    # 如果 [未发布] 下面没有内容（只有"暂无变更"），则新版本号下面也显示"暂无变更"
    if not unreleased_content or unreleased_content == "（暂无变更）":
        unreleased_content = "（暂无变更）"

    # 构造新的 changelog：
    # 新的空的 ## [未发布] + 新版本号标题 + 原来的内容
    new_unreleased = "## [未发布]\n\n（暂无变更）\n\n"
    version_section = f"## [{new_version}] - {today}\n\n{unreleased_content}\n\n"

    # 替换正文部分（不写入文件）
    new_content = existing[:match.start(1)] + new_unreleased + version_section + existing[match.end(2):]

    # 模拟更新底部的链接定义（和 update_changelog_version 保持一致）
    current_version = get_current_version()
    old_unreleased_link = f"[未发布]: https://github.com/vipsunwei/zombie-shooter-auto/compare/v{current_version}...HEAD"
    new_unreleased_link = f"[未发布]: https://github.com/vipsunwei/zombie-shooter-auto/compare/v{new_version}...HEAD"
    if old_unreleased_link in new_content:
        new_content = new_content.replace(old_unreleased_link, new_unreleased_link)
    new_version_link = f"[{new_version}]: https://github.com/vipsunwei/zombie-shooter-auto/releases/tag/v{new_version}"
    if new_version_link not in new_content:
        new_content = new_content.replace(
            new_unreleased_link,
            f"{new_unreleased_link}\n{new_version_link}"
        )

    return True, new_content, f"模拟版本号更新成功：## [{new_version}] - {today}（含链接定义）"
