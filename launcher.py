#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
auto_play.py 热更新启动器
==========================
监控 auto_play.py 的文件变化，检测到修改后自动重启。

使用方法：
  python launcher.py                 # 默认 battle 模式
  python launcher.py --mode patrol   # 快速巡逻模式（--mode 透传给 auto_play.py）
  python launcher.py --mode=patrol   # 等价写法

配置说明：
  编辑下方 EMULATOR_ARG 变量，指定传给 auto_play.py 的模拟器（作为 --emulator 参数的值）：
  - "auto"    = 自动检测模拟器（默认，推荐开发用）
  - "mumu"    = 指定MuMu模拟器
  - "leidian" = 指定雷电模拟器
  - "ld"      = 指定雷电模拟器（简写）
  - ""        = 弹出选择菜单（不推荐，热更新重启后会卡住等待输入）

停止：Ctrl+C（会同时停止 auto_play.py）

退出码约定（auto_play.py 与启动器据此判断「停止」还是「重启」）：
  - 0                          = 正常结束 / 用户手动停止(Ctrl+C)  → 停止，不重启
  - config.OUT_OF_STAMINA_EXIT = 体力(鸡腿)不足，自动停止          → 停止，不重启
  - config.BAG_FULL_EXIT       = 背包已满，自动停止                → 停止，不重启
  - 其它非0                    = 运行时异常崩溃                    → 重启(热更新容错)
无论用本启动器还是 `python auto_play.py --mode xxx` 直接运行，停止逻辑都一致。
"""

import subprocess
import sys
import time
import os

import config

# 要监控和运行的脚本
TARGET_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "auto_play.py")
# 使用运行本启动器的同一个 Python 解释器来启动子进程（sys.executable）。
# 不要写死绝对路径——clone 到别的机器 / 虚拟环境后路径就失效了；
# 谁用哪个 python 跑 launcher.py，launcher 就用哪个 python 跑 auto_play.py。
PYTHON = sys.executable
# 传给auto_play.py的模拟器参数（避免每次重启弹出选择菜单）
# 可选: "auto"=自动检测 | "mumu"=MuMu | "leidian"=雷电 | "ld"=雷电简写
# 留空字符串 "" 则会弹出选择菜单（不推荐，热更新重启后会卡住等待输入）
EMULATOR_ARG = "auto"
# 检测间隔（秒）
CHECK_INTERVAL = 2.0
# 重启前等待文件写入完成（秒）
RESTART_DELAY = 0.5


# 监控范围内需要排除的文件（改自身会递归重启，排除掉）
EXCLUDE = {"launcher.py"}


def parse_launcher_args(argv):
    """从 launcher 命令行参数中提取需要透传给 auto_play.py 的参数。

    目前支持 --mode <mode> 与 --mode=<mode> 两种写法；其余参数忽略
    （模拟器仍由上方 EMULATOR_ARG 常量控制）。返回透传参数列表，例如
    ["--mode", "patrol"] 或 ["--mode=patrol"]。
    """
    passthrough = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--mode":
            # --mode <value>
            passthrough.append(a)
            if i + 1 < len(argv):
                passthrough.append(argv[i + 1])
                i += 2
            else:
                i += 1
            continue
        if a.startswith("--mode="):
            passthrough.append(a)
            i += 1
            continue
        # 其它参数忽略，保持向后兼容
        i += 1
    return passthrough


def get_latest_mtime():
    """获取监控目录下所有 .py 文件中最晚的修改时间（支持子模块热更新）"""
    watch_dir = os.path.dirname(os.path.abspath(__file__))
    latest = 0
    try:
        for name in os.listdir(watch_dir):
            if name.endswith(".py") and name not in EXCLUDE:
                try:
                    m = os.path.getmtime(os.path.join(watch_dir, name))
                    if m > latest:
                        latest = m
                except OSError:
                    pass
    except OSError:
        pass
    return latest


def main():
    print("=" * 55)
    print("  热更新启动器 · 监控项目目录所有 .py 模块")
    print("=" * 55)
    print(f"  Python: {PYTHON}")
    print(f"  目标脚本: {TARGET_SCRIPT}")
    print(f"  模拟器参数: {EMULATOR_ARG if EMULATOR_ARG else '(弹出选择菜单)'}")
    MODE_ARGS = parse_launcher_args(sys.argv[1:])
    print(f"  透传参数: {' '.join(MODE_ARGS) if MODE_ARGS else '(无，默认 battle 模式)'}")
    print(f"  检测间隔: {CHECK_INTERVAL}s")
    print("  改完脚本保存后自动重启，Ctrl+C 停止")
    print("-" * 55)

    if not os.path.exists(TARGET_SCRIPT):
        print(f"❌ 找不到脚本: {TARGET_SCRIPT}")
        return

    last_mtime = get_latest_mtime()
    proc = None
    restart_count = 0

    try:
        while True:
            # 启动子进程
            if proc is None or proc.poll() is not None:
                if proc is not None and proc.poll() is not None:
                    rc = proc.returncode
                    # 退出码 0（正常/手动停止）或 10（体力不足）都应停止，不重启；
                    # 其它非0 视为运行时崩溃，借热更新机制自动重启。
                    if rc == 0 or rc == config.OUT_OF_STAMINA_EXIT or rc == config.BAG_FULL_EXIT:
                        if rc == 0:
                            reason = "正常结束/手动停止"
                        elif rc == config.OUT_OF_STAMINA_EXIT:
                            reason = "体力不足"
                        else:
                            reason = "背包已满"
                        print(f"\n[{time.strftime('%H:%M:%S')}] 🛑 {reason}，停止启动器（不再重启）")
                        return
                    print(f"\n[{time.strftime('%H:%M:%S')}] ⚠ auto_play.py 异常退出(码{rc})，重新启动...")
                print(f"\n[{time.strftime('%H:%M:%S')}] ▶ 启动 auto_play.py")
                # 构建命令：EMULATOR_ARG 作为 --emulator 传入；为空则不传（弹出选择菜单）
                cmd = [PYTHON, TARGET_SCRIPT]
                if EMULATOR_ARG:
                    cmd.extend(["--emulator", EMULATOR_ARG])
                cmd.extend(MODE_ARGS)
                proc = subprocess.Popen(
                    cmd,
                    cwd=os.path.dirname(TARGET_SCRIPT)
                )

            # 监控文件变化
            time.sleep(CHECK_INTERVAL)
            current_mtime = get_latest_mtime()

            if current_mtime != last_mtime and current_mtime != 0:
                # 等待文件写入完成
                time.sleep(RESTART_DELAY)
                # 再次确认时间（避免写入过程中触发）
                final_mtime = get_latest_mtime()
                if final_mtime == current_mtime:
                    restart_count += 1
                    last_mtime = final_mtime
                    print(f"\n[{time.strftime('%H:%M:%S')}] 🔄 检测到脚本变化，自动重启（第 {restart_count} 次）")
                    print("-" * 55)

                    # 终止旧进程
                    if proc and proc.poll() is None:
                        proc.terminate()
                        try:
                            proc.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                            proc.wait()

                    # 重启
                    proc = None  # 下一轮循环启动

    except KeyboardInterrupt:
        print(f"\n\n[{time.strftime('%H:%M:%S')}] 停止启动器...")
        if proc and proc.poll() is None:
            print("正在停止 auto_play.py ...")
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        print(f"共自动重启 {restart_count} 次")
        print("已停止")


if __name__ == "__main__":
    main()
