#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
auto_play.py 热更新启动器
==========================
监控 auto_play.py 的文件变化，检测到修改后自动重启。

使用方法：
  python launcher.py

停止：Ctrl+C（会同时停止 auto_play.py）
"""

import subprocess
import sys
import time
import os

# 要监控和运行的脚本
TARGET_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "auto_play.py")
# Python解释器路径（EasyOCR安装在Python 3.12中，必须用3.12运行）
PYTHON_PATH = r"C:\Users\sunwei\AppData\Local\Programs\Python\Python312\python.exe"
# 检测间隔（秒）
CHECK_INTERVAL = 2.0
# 重启前等待文件写入完成（秒）
RESTART_DELAY = 0.5


def get_mtime():
    """获取脚本最后修改时间"""
    try:
        return os.path.getmtime(TARGET_SCRIPT)
    except OSError:
        return 0


def main():
    print("=" * 55)
    print("  热更新启动器 · 监控 auto_play.py")
    print("=" * 55)
    print(f"  目标脚本: {TARGET_SCRIPT}")
    print(f"  检测间隔: {CHECK_INTERVAL}s")
    print("  改完脚本保存后自动重启，Ctrl+C 停止")
    print("-" * 55)

    if not os.path.exists(TARGET_SCRIPT):
        print(f"❌ 找不到脚本: {TARGET_SCRIPT}")
        return

    last_mtime = get_mtime()
    proc = None
    restart_count = 0

    try:
        while True:
            # 启动子进程
            if proc is None or proc.poll() is not None:
                if proc is not None and proc.poll() is not None:
                    print(f"\n[{time.strftime('%H:%M:%S')}] ⚠ auto_play.py 已退出，重新启动...")
                print(f"\n[{time.strftime('%H:%M:%S')}] ▶ 启动 auto_play.py")
                proc = subprocess.Popen(
                    [PYTHON_PATH, TARGET_SCRIPT],
                    cwd=os.path.dirname(TARGET_SCRIPT)
                )

            # 监控文件变化
            time.sleep(CHECK_INTERVAL)
            current_mtime = get_mtime()

            if current_mtime != last_mtime and current_mtime != 0:
                # 等待文件写入完成
                time.sleep(RESTART_DELAY)
                # 再次确认时间（避免写入过程中触发）
                final_mtime = get_mtime()
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
