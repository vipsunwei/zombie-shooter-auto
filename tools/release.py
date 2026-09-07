#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
向僵尸开炮 · 一键发布脚本
==========================
使用 bump2version 自动升级版本号，更新 CHANGELOG.md，提交代码，打 Git tag，然后推送到远程仓库。

使用方法（在项目根目录执行）：
  python tools/release.py patch    # 升级修订号：1.0.0 → 1.0.1（修bug）
  python tools/release.py minor    # 升级次版本号：1.0.0 → 1.1.0（加功能）
  python tools/release.py major    # 升级主版本号：1.0.0 → 2.0.0（大改不兼容）

路径说明：本文件位于 tools/ 下，同级引用 changelog_utils / generate_changelog；
version.py 与 CHANGELOG.md 在项目根目录（tools 的父目录），由 changelog_utils 处理。
"""

import sys
import os
import socket
import subprocess
import re
import configparser

# tools 目录（本文件所在目录），用于定位同级的 generate_changelog.py
TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
# 项目根目录（tools 的父目录），version.py / CHANGELOG.md 在此
ROOT_DIR = os.path.dirname(TOOLS_DIR)
# 显式将 tools 目录加入 sys.path，确保 `from changelog_utils / generate_changelog import`
# 在 `python tools/release.py` 与 `python -m tools.release` 等不同调用方式下都能成功
sys.path.insert(0, TOOLS_DIR)

# 从 changelog_utils 导入公共函数，确保预览和真实发版逻辑完全一致
from changelog_utils import (
    get_current_version,
    calculate_new_version,
    update_changelog_version,
    simulate_changelog_update,
)

# 从 generate_changelog 导入函数，用于 --dry-run 模式下在内存中生成 changelog
from generate_changelog import (
    get_last_tag as get_last_tag_changelog,
    get_commits_since_tag,
    generate_changelog_content,
    update_changelog_file,
)

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


# 常见代理端口（Clash、V2Ray、Shadowsocks等）
COMMON_PROXY_PORTS = [7897, 7890, 1080, 10809, 8080, 3128, 20171, 9090]

def detect_proxy():
    """自动探测本地是否有可用的代理
    返回: 代理地址（如 "http://127.0.0.1:7897"）或 None
    """
    for port in COMMON_PROXY_PORTS:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)  # 超时0.5秒，快速探测
            result = sock.connect_ex(("127.0.0.1", port))
            sock.close()
            if result == 0:
                return f"http://127.0.0.1:{port}"
        except Exception:
            continue
    return None


def run_cmd(cmd, check=True, capture_output=False):
    """执行命令，返回结果"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            check=check,
            capture_output=capture_output,
            text=True,
            encoding='utf-8', errors='replace'
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
    print_color("[1/7] 检查 Git 仓库状态...", Color.YELLOW)

    result = run_cmd("git rev-parse --is-inside-work-tree", capture_output=True, check=False)
    if getattr(result, 'returncode', 1) != 0:
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
    print_color("[2/7] 检查 bump2version...", Color.YELLOW)

    # 用模块导入方式检查（最可靠，bump2version 不支持 --version 参数）
    result = subprocess.run(
        [sys.executable, "-c", "import bumpversion; print('installed')"],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print_color("✅ bump2version 已就绪", Color.GREEN)
    else:
        print_color("⚠️  bump2version 未安装，正在安装...", Color.YELLOW)
        run_cmd(f'"{sys.executable}" -m pip install bump2version')
        print_color("✅ bump2version 安装完成", Color.GREEN)


def check_version_sync():
    """校验 version.py 与 .bumpversion.cfg 的版本号一致（双源真值必须同步）

    bump2version 以 cfg 里的 current_version 做 search/replace，
    release.py 的 CHANGELOG 更新以 version.py 为准。两者不同步时
    bump2version 必失败，且此时 CHANGELOG 已被修改，留下半完成状态。
    """
    print_color("[3/7] 校验版本号一致性...", Color.YELLOW)

    cfg_path = os.path.join(ROOT_DIR, '.bumpversion.cfg')
    parser = configparser.ConfigParser()
    parser.read(cfg_path, encoding='utf-8')
    cfg_version = parser['bumpversion']['current_version'].strip()
    py_version = get_current_version()
    if cfg_version != py_version:
        print_color(f"❌ 版本号不同步：version.py={py_version}，.bumpversion.cfg={cfg_version}", Color.RED)
        print_color("   请先手动统一两者后再发版", Color.RED)
        sys.exit(1)
    print_color(f"✅ 版本号一致：v{py_version}", Color.GREEN)

def generate_changelog():
    """自动生成 changelog（进程内直接调用 generate_changelog 模块函数）

    不再以子进程方式运行 generate_changelog.py：子进程在 Windows 管道下
    默认按 GBK 输出中文，而父进程按 utf-8 解码，遇到中文输出会直接
    UnicodeDecodeError，或字符串匹配失败导致 git add 被跳过、changelog
    改动丢失。进程内调用彻底消除编码握手问题。
    """
    print()
    print_color("[4/7] 自动生成 CHANGELOG...", Color.YELLOW)
    print()

    try:
        last_tag = get_last_tag_changelog()
        if last_tag:
            print_color(f"📋 获取从 tag {last_tag} 到现在的 commit...", Color.CYAN)
            commits = get_commits_since_tag(last_tag)
        else:
            print_color("📋 未找到 tag，获取全部历史 commit...", Color.CYAN)
            commits = get_commits_since_tag(None)
    except Exception as e:
        print_color(f"⚠️  changelog 生成失败，跳过（不影响发版）：{e}", Color.YELLOW)
        return

    print_color(f"   共 {len(commits)} 个 commit", Color.CYAN)
    if not commits:
        print_color("ℹ️  没有新的变更，changelog 无需更新", Color.CYAN)
        return

    content = generate_changelog_content(commits)
    update_changelog_file(content)
    print_color("✅ CHANGELOG.md 已自动更新", Color.GREEN)
    # git add CHANGELOG.md，让 bump2version 提交时包含这个修改
    run_cmd(f'git add "{os.path.join(ROOT_DIR, "CHANGELOG.md")}"')


def bump_version(version_type):
    """执行版本升级"""
    print()
    print_color(f"[6/7] 升级版本号（{version_type}）...", Color.YELLOW)
    print()

    # 用当前解释器执行 bump2version（与 check_bump2version 的检查环境一致，
    # 避免 shell PATH 中的 bump2version 属于另一个 Python 环境的问题）
    run_cmd(f'"{sys.executable}" -m bumpversion {version_type} --allow-dirty')

    print()
    print_color("✅ 版本升级完成", Color.GREEN)
    print()

    # 读取新版本号（从 version.py）
    version_path = os.path.join(ROOT_DIR, 'version.py')
    with open(version_path, 'r', encoding='utf-8') as f:
        version_content = f.read()
    match = re.search(r'__version__\s*=\s*"([^"]+)"', version_content)
    if match:
        new_version = match.group(1)
        print_color(f"📌 新版本号：v{new_version}", Color.CYAN)
        return new_version
    return "unknown"

def push_to_remote(new_version):
    """推送到远程仓库（自动探测代理，只推送当前分支与本次发版 tag）"""
    print()
    print_color("[7/7] 推送到远程仓库...", Color.YELLOW)
    print()

    tag_name = f"v{new_version}"
    # Windows 版 Git 默认用 schannel 做 SSL 后端，与 Clash 等本地代理的
    # MITM 握手不兼容，会报 schannel: SEC_E_ILLEGAL_MESSAGE。
    # 统一改用 openssl 后端（非 Windows / 无 schannel 时该参数被忽略，无副作用）。
    ssl_args = "-c http.sslBackend=openssl"
    # 自动探测代理
    proxy = detect_proxy()
    if proxy:
        print_color(f"🔍 检测到可用代理: {proxy}", Color.CYAN)
        proxy_args = f"-c http.proxy={proxy} -c https.proxy={proxy}"
        push_cmd = f"git {ssl_args} {proxy_args} push"
        push_tag_cmd = f"git {ssl_args} {proxy_args} push origin {tag_name}"
    else:
        print_color("ℹ️  未检测到代理，直接推送", Color.CYAN)
        push_cmd = f"git {ssl_args} push"
        push_tag_cmd = f"git {ssl_args} push origin {tag_name}"

    # 推送代码
    print(f"→ {push_cmd}")
    run_cmd(push_cmd)

    # 只推送本次发版的 tag（push --tags 会把本地所有陈旧 tag 一起推上去）
    print(f"→ {push_tag_cmd}")
    run_cmd(push_tag_cmd)

    print()
    print_color("✅ 推送完成", Color.GREEN)

def main():
    # 检查参数
    args = sys.argv[1:]
    dry_run = '--dry-run' in args
    # 移除 --dry-run 参数，只保留版本类型
    version_args = [a for a in args if a != '--dry-run']

    if len(version_args) != 1 or version_args[0] not in ['patch', 'minor', 'major']:
        print_header("向僵尸开炮 · 一键发布脚本")
        print("使用方法：")
        print(f"  python {sys.argv[0]} patch              # 真正发版：升级修订号 1.0.0 → 1.0.1")
        print(f"  python {sys.argv[0]} patch --dry-run    # 预览模式：只显示将生成的内容，不修改文件")
        print(f"  python {sys.argv[0]} minor              # 升级次版本号：1.0.0 → 1.1.0（加功能）")
        print(f"  python {sys.argv[0]} major              # 升级主版本号：1.0.0 → 2.0.0（大改不兼容）")
        print()
        sys.exit(1)

    version_type = version_args[0]

    # 锚定工作目录到项目根：.bumpversion.cfg 里的 version.py 相对路径、
    # git status/add 与 changelog 生成中的 git 命令都按 cwd 解析，
    # 锚定后无论从哪个目录启动（如 tools/）都能正确运行
    os.chdir(ROOT_DIR)

    if dry_run:
        print_header("向僵尸开炮 · 发布预览（--dry-run，不修改文件）")
        # 预览模式：直接走简化流程，不需要检查 git 状态和 bump2version
        print_color("[1/3] 读取版本号...", Color.YELLOW)
        print()

        current_version = get_current_version()
        new_version_pre = calculate_new_version(current_version, version_type)
        print_color(f"📌 当前版本：v{current_version} → 新版本：v{new_version_pre}", Color.CYAN)
        print()

        # 在内存中生成 changelog 内容（不修改文件）
        print_color("[2/3] 在内存中生成 changelog 内容...", Color.YELLOW)
        print()

        last_tag = get_last_tag_changelog()
        commits = get_commits_since_tag(last_tag)
        print_color(f"📝 从 {last_tag} 到现在共 {len(commits)} 个 commit", Color.CYAN)
        if commits:
            for commit in commits:
                print(f"  [{commit['hash']}] {commit['message']}")
            print()
            changelog_content = generate_changelog_content(commits)
            print_color("✅ changelog 内容已生成（内存中，不写入文件）", Color.GREEN)
        else:
            changelog_content = None
            print_color("ℹ️  没有新的 commit", Color.CYAN)
        print()

        # 模拟更新，不修改文件
        print_color("[3/3] 模拟更新 CHANGELOG 版本号...", Color.YELLOW)
        print()

        sim_ok, preview_content, sim_msg = simulate_changelog_update(
            new_version_pre,
            unreleased_content=changelog_content
        )
        if sim_ok:
            print_color(f"✅ {sim_msg}", Color.GREEN)
            print()
            print_color("=" * 55, Color.CYAN)
            print_color("  📋 预览：发版后的 CHANGELOG.md（前 60 行）", Color.CYAN)
            print_color("=" * 55, Color.CYAN)
            print()
            lines = preview_content.split('\n')
            for i, line in enumerate(lines[:60]):
                print(line)
            if len(lines) > 60:
                print(f"... (共 {len(lines)} 行，已省略后 {len(lines)-60} 行)")
            print()
            print_color("=" * 55, Color.CYAN)
            print_color("  ✅ 预览完成！以上内容不会写入文件", Color.CYAN)
            print_color(f"  确认无误后运行：python tools/release.py {version_type}", Color.CYAN)
            print_color("=" * 55, Color.CYAN)
            print()
        else:
            print_color(f"❌ {sim_msg}", Color.RED)
            sys.exit(1)
        return  # 预览模式结束

    # 以下是真实发版模式
    print_header("向僵尸开炮 · 一键发布脚本")

    # 1. 检查 Git 仓库
    check_git_repo()

    # 2. 检查 bump2version
    check_bump2version()

    # 2.5 校验 version.py 与 .bumpversion.cfg 版本号同步（双源不一致时 bump2version 必失败）
    check_version_sync()

    # 3. 自动生成 changelog
    generate_changelog()

    # 3.5 手动更新 CHANGELOG 版本号（不依赖 bump2version，更可靠）
    print()
    print_color("[5/7] 手动更新 CHANGELOG 版本号...", Color.YELLOW)
    print()
    # 读取当前版本号（从 changelog_utils）
    current_version = get_current_version()
    new_version_pre = calculate_new_version(current_version, version_type)
    print_color(f"📌 当前版本：v{current_version} → 新版本：v{new_version_pre}", Color.CYAN)

    # 真实发版模式：手动更新 CHANGELOG 版本号
    changelog_ok, changelog_msg = update_changelog_version(new_version_pre)
    if changelog_ok:
        print_color(f"✅ {changelog_msg}", Color.GREEN)
    else:
        print_color(f"❌ {changelog_msg}，终止发版", Color.RED)
        sys.exit(1)
    # git add CHANGELOG.md，让 bump2version 的 commit 包含这个修改
    run_cmd(f'git add "{os.path.join(ROOT_DIR, "CHANGELOG.md")}"')
    print_color("✅ CHANGELOG.md 已暂存", Color.GREEN)

    # 4. 升级版本号（bump2version 只修改 version.py，自动 commit 和打 tag）
    new_version = bump_version(version_type)

    # 5. 推送到远程
    push_to_remote(new_version)

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
