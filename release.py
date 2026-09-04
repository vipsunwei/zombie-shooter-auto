#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
向僵尸开炮 · 一键发布脚本
==========================
使用 bump2version 自动升级版本号，更新 CHANGELOG.md，提交代码，打 Git tag，然后推送到远程仓库。

使用方法：
  python release.py patch    # 升级修订号：1.0.0 → 1.0.1（修bug）
  python release.py minor    # 升级次版本号：1.0.0 → 1.1.0（加功能）
  python release.py major    # 升级主版本号：1.0.0 → 2.0.0（大改不兼容）
"""

import sys
import os
import subprocess

# 颜色输出
class Color:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    END = '\033[0m'

def print_color(text, color):
    print(f"{color}{text}{Color.END}")

def print_header(text):
    print()
    print_color("=" * 55, Color.CYAN)
    print_color(f"  {text}", Color.CYAN)
    print_color("=" * 55, Color.CYAN)
    print()

def run_cmd(cmd, check=True, capture_output=False):
    """执行命令，返回结果"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            check=check,
            capture_output=capture_output,
            text=True,
            encoding='utf-8'
        )
        return result
    except subprocess.CalledProcessError as e:
        if check:
            print_color(f"❌ 命令执行失败: {cmd}", Color.RED)
            if e.stdout:
                print(e.stdout)
            if e.stderr:
                print(e.stderr)
            sys.exit(1)
        return e

def check_git_repo():
    """检查是否在 git 仓库中"""
    print_color("[1/4] 检查 Git 仓库状态...", Color.YELLOW)

    if not os.path.exists('.git'):
        print_color("❌ 错误：当前目录不是 Git 仓库", Color.RED)
        sys.exit(1)

    # 检查是否有未提交的更改
    result = run_cmd("git status --porcelain", capture_output=True)
    if result.stdout.strip():
        print_color("⚠️  警告：工作区有未提交的更改：", Color.YELLOW)
        print(result.stdout)
        confirm = input("是否继续？(y/N): ").strip().lower()
        if confirm != 'y':
            print_color("已取消", Color.RED)
            sys.exit(0)

    print_color("✅ Git 仓库状态正常", Color.GREEN)

def check_bump2version():
    """检查 bump2version 是否安装，未安装则自动安装"""
    print()
    print_color("[2/4] 检查 bump2version...", Color.YELLOW)

    # 检查 bump2version 或 bumpversion
    result = subprocess.run("bump2version --version", shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        result = subprocess.run("bumpversion --version", shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            print_color("⚠️  bump2version 未安装，正在安装...", Color.YELLOW)
            run_cmd("pip install bump2version")
            print_color("✅ bump2version 安装完成", Color.GREEN)
        else:
            print_color("✅ bumpversion 已就绪（旧版本名）", Color.GREEN)
    else:
        print_color("✅ bump2version 已就绪", Color.GREEN)

def generate_changelog():
    """自动生成 changelog"""
    print()
    print_color("[3/5] 自动生成 CHANGELOG...", Color.YELLOW)
    print()

    # 调用 generate_changelog.py 生成 changelog
    result = subprocess.run(
        [sys.executable, "generate_changelog.py"],
        capture_output=True,
        text=True,
        encoding='utf-8'
    )

    if result.returncode != 0:
        print_color("⚠️  changelog 生成失败，跳过（不影响发版）", Color.YELLOW)
        if result.stderr:
            print(result.stderr)
        return

    # 打印生成结果的关键部分
    output = result.stdout
    if "已更新 CHANGELOG.md" in output:
        print_color("✅ CHANGELOG.md 已自动更新", Color.GREEN)
        # git add CHANGELOG.md，让 bump2version 提交时包含这个修改
        run_cmd("git add CHANGELOG.md")
    elif "没有新的变更" in output:
        print_color("ℹ️  没有新的变更，changelog 无需更新", Color.CYAN)
    else:
        print(output)


def bump_version(version_type):
    """执行版本升级"""
    print()
    print_color(f"[4/5] 升级版本号（{version_type}）...", Color.YELLOW)
    print()

    # 执行 bump2version（--allow-dirty 允许工作区有已暂存的 changelog 修改）
    run_cmd(f"bump2version {version_type} --allow-dirty")

    print()
    print_color("✅ 版本升级完成", Color.GREEN)
    print()

    # 读取新版本号
    with open('auto_play.py', 'r', encoding='utf-8') as f:
        content = f.read()
    import re
    match = re.search(r'__version__\s*=\s*"([^"]+)"', content)
    if match:
        new_version = match.group(1)
        print_color(f"📌 新版本号：v{new_version}", Color.CYAN)
        return new_version
    return "unknown"

def push_to_remote():
    """推送到远程仓库"""
    print()
    print_color("[5/5] 推送到远程仓库...", Color.YELLOW)
    print()

    # 推送代码
    print("→ git push")
    run_cmd("git push")

    # 推送 tag
    print("→ git push --tags")
    run_cmd("git push --tags")

    print()
    print_color("✅ 推送完成", Color.GREEN)

def main():
    # 检查参数
    if len(sys.argv) != 2 or sys.argv[1] not in ['patch', 'minor', 'major']:
        print_header("向僵尸开炮 · 一键发布脚本")
        print("使用方法：")
        print(f"  python {sys.argv[0]} patch    # 升级修订号：1.0.0 → 1.0.1（修bug）")
        print(f"  python {sys.argv[0]} minor    # 升级次版本号：1.0.0 → 1.1.0（加功能）")
        print(f"  python {sys.argv[0]} major    # 升级主版本号：1.0.0 → 2.0.0（大改不兼容）")
        print()
        sys.exit(1)

    version_type = sys.argv[1]

    print_header("向僵尸开炮 · 一键发布脚本")

    # 1. 检查 Git 仓库
    check_git_repo()

    # 2. 检查 bump2version
    check_bump2version()

    # 3. 自动生成 changelog
    generate_changelog()

    # 4. 升级版本号
    new_version = bump_version(version_type)

    # 5. 推送到远程
    push_to_remote()

    # 完成
    print()
    print_color("=" * 55, Color.GREEN)
    print_color(f"  🎉 发布完成！v{new_version}", Color.GREEN)
    print_color("=" * 55, Color.GREEN)
    print()
    print_color("已完成：", Color.CYAN)
    print(f"  ✅ 升级版本号：v{new_version}")
    print(f"  ✅ 更新 CHANGELOG.md")
    print(f"  ✅ 提交代码")
    print(f"  ✅ 打 Git tag：v{new_version}")
    print(f"  ✅ 推送到远程仓库")
    print()
    print_color(f"查看发布：https://github.com/vipsunwei/zombie-shooter-auto/releases/tag/v{new_version}", Color.CYAN)
    print()

if __name__ == "__main__":
    main()
