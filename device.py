#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
设备控制层（ADB 连接、截图、点击、模拟器检测、底部导航、兜底返回、清理）

依赖：config（常量与运行时状态）、vision（OCR 缓存更新）、states（兜底验证）。
"""

import subprocess
import os
import time
import sys
from PIL import Image

import config
from config import *
import vision
import states


# ============================================================
#  底部导航栏检测（硬编码位置 + 亮度判断，不依赖 OCR 文字）
# ============================================================

def _get_pixel_brightness(cx, cy, radius=8):
    """获取指定位置最亮像素的亮度值（R+G+B）"""
    try:
        with Image.open(SCREENSHOT_LOCAL) as img:
            max_bright = 0
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    px, py = cx + dx, cy + dy
                    if 0 <= px < img.width and 0 <= py < img.height:
                        p = img.getpixel((px, py))
                        bright = p[0] + p[1] + p[2]
                        if bright > max_bright:
                            max_bright = bright
            return max_bright
    except Exception:
        return 0


def get_bottom_nav_buttons():
    """获取底部导航栏所有按钮（名称 + 位置 + 亮度）"""
    buttons = []
    for name, x, y in BOTTOM_NAV_BUTTONS:
        sx, sy = scale((x, y))
        brightness = _get_pixel_brightness(sx, sy)
        buttons.append((name, sx, sy, brightness))
    return buttons


def get_selected_bottom_nav():
    """获取底部导航栏当前选中的按钮名称，或 None"""
    buttons = get_bottom_nav_buttons()
    if not buttons:
        return None
    brightest = max(buttons, key=lambda b: b[3])
    if brightest[3] >= SELECTED_BRIGHTNESS_THRESHOLD:
        return brightest[0]
    return None


def click_bottom_nav(name):
    """点击底部导航栏指定按钮（直接点击固定位置，不依赖 OCR）"""
    for btn_name, x, y in BOTTOM_NAV_BUTTONS:
        if btn_name == name:
            tap((x, y))
            return True
    return False


# ============================================================
#  模拟器自动检测与 ADB 连接
# ============================================================

def _default_search_dirs():
    """返回本机常见搜索根目录（动态生成，不写死盘符/路径）。

    - 程序目录取环境变量（兼容系统盘非 C 的情况）；
    - 系统盘根目录取 %SystemDrive%；
    - 探测所有实际存在的盘符（跳过软驱 A:/B:）。
    """
    dirs = []
    for env in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
        p = os.environ.get(env)
        if p and os.path.isdir(p):
            dirs.append(p)
    sysdrive = os.environ.get("SystemDrive", "C:") + os.sep
    if os.path.isdir(sysdrive):
        dirs.append(sysdrive)
    for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        root = letter + ":\\"
        if root != sysdrive and os.path.exists(root):
            dirs.append(root)
    return dirs


def find_files_by_name(filename, search_dirs=None, max_depth=3):
    """在指定目录下递归查找指定文件名（默认扫描本机常见安装目录）"""
    if search_dirs is None:
        search_dirs = _default_search_dirs()
    found = []
    for base_dir in search_dirs:
        if not os.path.exists(base_dir):
            continue
        try:
            for root, dirs, files in os.walk(base_dir):
                depth = root.replace(base_dir, "").count(os.sep)
                if depth > max_depth:
                    dirs.clear()
                    continue
                dirs[:] = [d for d in dirs if not d.startswith('$') and not d.startswith('.')
                           and d.lower() not in ['windows', 'system32', 'syswow64', '$recycle.bin']]
                if filename in files:
                    found.append(os.path.join(root, filename))
        except (PermissionError, OSError):
            continue
    return found


def get_install_path_from_registry(reg_key, value_name="InstallPath"):
    """从 Windows 注册表读取软件安装路径"""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_key)
        value, _ = winreg.QueryValueEx(key, value_name)
        winreg.CloseKey(key)
        return value
    except Exception:
        pass
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_key)
        value, _ = winreg.QueryValueEx(key, value_name)
        winreg.CloseKey(key)
        return value
    except Exception:
        pass
    return None


def detect_mumu_adb():
    """检测 MuMu 模拟器的 ADB 路径和端口"""
    reg_paths = [
        r"SOFTWARE\Netease\MuMu",
        r"SOFTWARE\Netease\MuMuPlayer",
        r"SOFTWARE\WOW6432Node\Netease\MuMu",
        r"SOFTWARE\WOW6432Node\Netease\MuMuPlayer",
    ]
    for reg_key in reg_paths:
        install_path = get_install_path_from_registry(reg_key)
        if install_path:
            adb_path = os.path.join(install_path, "nx_main", "adb.exe")
            if os.path.exists(adb_path):
                # 默认端口 16384；旧版可能用 7555/16385，连不上时用 -e 手动指定
                return (adb_path, "127.0.0.1:16384")
    adb_files = find_files_by_name("adb.exe", max_depth=4)
    for adb_path in adb_files:
        path_lower = adb_path.lower()
        if "mumu" in path_lower or "netease" in path_lower:
            return (adb_path, "127.0.0.1:16384")
    return (None, None)


def detect_ldplayer_adb():
    """检测雷电模拟器的 ADB 路径和端口"""
    reg_paths = [
        r"SOFTWARE\leidian\LDPlayer",
        r"SOFTWARE\leidian\LDPlayer9",
        r"SOFTWARE\leidian\LDPlayer4",
        r"SOFTWARE\WOW6432Node\leidian\LDPlayer",
        r"SOFTWARE\WOW6432Node\leidian\LDPlayer9",
        r"SOFTWARE\WOW6432Node\leidian\LDPlayer4",
    ]
    for reg_key in reg_paths:
        install_path = get_install_path_from_registry(reg_key)
        if install_path:
            adb_path = os.path.join(install_path, "adb.exe")
            if os.path.exists(adb_path):
                # 默认端口 5554；其他实例可能用 5555~5558，连不上时用 -e 手动指定
                return (adb_path, "127.0.0.1:5554")
    adb_files = find_files_by_name("adb.exe", max_depth=3)
    for adb_path in adb_files:
        path_lower = adb_path.lower()
        if "leidian" in path_lower or "ldplayer" in path_lower:
            return (adb_path, "127.0.0.1:5554")
    return (None, None)


def detect_emulator():
    """自动检测已安装的模拟器（优先 MuMu，其次雷电）"""
    print("  正在自动检测模拟器...")
    adb_path, device = detect_mumu_adb()
    if adb_path:
        return (adb_path, device, "MuMu")
    adb_path, device = detect_ldplayer_adb()
    if adb_path:
        return (adb_path, device, "雷电")
    return (None, None, None)


def test_adb_connection(adb_path, device, timeout=5):
    """测试 ADB 连接是否可用"""
    try:
        full = f'"{adb_path}" connect {device}'
        r = subprocess.run(full, capture_output=True, text=True, shell=True, timeout=timeout, encoding='utf-8', errors='replace')
        full2 = f'"{adb_path}" -s {device} get-state'
        r2 = subprocess.run(full2, capture_output=True, text=True, shell=True, timeout=timeout, encoding='utf-8', errors='replace')
        return "device" in (r2.stdout or "")
    except Exception:
        return False


def init_adb():
    """初始化 ADB 连接（自动检测或使用手动配置），返回 (adb_path, device, emulator_name)"""
    if config.ADB_PATH and config.DEVICE:
        if os.path.exists(config.ADB_PATH):
            print(f"  使用手动配置: {config.ADB_PATH}")
            print(f"  设备: {config.DEVICE}")
            return (config.ADB_PATH, config.DEVICE, "手动配置")
        else:
            print(f"  ⚠ 手动配置的ADB路径不存在: {config.ADB_PATH}，尝试自动检测...")

    if config.EMULATOR_TYPE == "mumu":
        adb_path, device = detect_mumu_adb()
        emulator_name = "MuMu"
    elif config.EMULATOR_TYPE == "ldplayer":
        adb_path, device = detect_ldplayer_adb()
        emulator_name = "雷电"
    else:  # auto
        adb_path, device, emulator_name = detect_emulator()

    if not adb_path:
        print(f"  ❌ 未检测到模拟器！请手动配置 ADB_PATH 和 DEVICE")
        print(f"  支持的模拟器: MuMu、雷电（LDPlayer）")
        sys.exit(1)

    print(f"  检测到模拟器: {emulator_name}")
    print(f"  ADB路径: {adb_path}")
    print(f"  尝试连接设备: {device} ...")

    if test_adb_connection(adb_path, device):
        print(f"  ✅ 连接成功!")
        config.ADB_PATH = adb_path
        config.DEVICE = device
        return (adb_path, device, emulator_name)
    else:
        print(f"  ⚠ 端口 {device} 连接失败，尝试其他端口...")
        if emulator_name == "MuMu":
            for port in [16384, 7555, 16385, 16386]:
                dev = f"127.0.0.1:{port}"
                if test_adb_connection(adb_path, dev):
                    print(f"  ✅ 端口 {dev} 连接成功!")
                    config.ADB_PATH = adb_path
                    config.DEVICE = dev
                    return (adb_path, dev, emulator_name)
        elif emulator_name == "雷电":
            for port in [5554, 5555, 5556, 5557, 5558, 5559, 5560]:
                dev = f"127.0.0.1:{port}"
                if test_adb_connection(adb_path, dev):
                    print(f"  ✅ 端口 {dev} 连接成功!")
                    config.ADB_PATH = adb_path
                    config.DEVICE = dev
                    return (adb_path, dev, emulator_name)

        print(f"  ❌ 所有端口均连接失败！请确保模拟器已启动并开启ADB调试")
        sys.exit(1)


# ============================================================
#  ADB 工具函数
# ============================================================

def run_adb(cmd, timeout=15):
    """执行 adb 命令，返回 stdout"""
    full = f'"{config.ADB_PATH}" -s {config.DEVICE} {cmd}'
    try:
        r = subprocess.run(full, capture_output=True, text=True, shell=True, timeout=timeout, encoding='utf-8', errors='replace')
        return (r.stdout or "").strip()
    except subprocess.TimeoutExpired:
        return ""


def get_screen_size():
    """获取模拟器实际分辨率"""
    out = run_adb("shell wm size")
    if "x" in out:
        s = out.split(":")[-1].strip()
        w, h = map(int, s.split("x"))
        return w, h
    return 1080, 1920


def screenshot():
    """截图 → 拉到本地 → 返回 PIL.Image"""
    run_adb(f'shell screencap -p {SCREENSHOT_REMOTE}')
    run_adb(f'pull {SCREENSHOT_REMOTE} "{SCREENSHOT_LOCAL}"')
    if os.path.exists(SCREENSHOT_LOCAL):
        try:
            return Image.open(SCREENSHOT_LOCAL)
        except Exception:
            return None
    return None


def tap(coord):
    """模拟点击（按实际分辨率缩放）"""
    x, y = scale(coord)
    run_adb(f'shell input tap {x} {y}')


def close_with_verify(close_pos, check_func, name, max_retries=2):
    """验证式关闭弹窗：点一次→截图验证→确认关闭就停，防止误入其他界面"""
    for attempt in range(1, max_retries + 1):
        print(f"    → 第{attempt}次点{name}关闭位置 {close_pos}")
        tap(close_pos)
        time.sleep(0.8)
        img = screenshot()
        if img is None:
            continue
        vision.ocr_screenshot(img)
        if not check_func(img):
            print(f"    ✅ {name}已关闭，停止操作")
            return True
        print(f"    ⚠ {name}仍在，准备重试")
    print(f"    ❌ {name}多次尝试未关闭，跳过（下轮循环再处理）")
    return False


def fallback_back():
    """未知界面兜底：点左下角返回按钮 → 截图验证是否回到正常游戏循环"""
    for attempt in range(1, 3):
        print(f"    → 第{attempt}次点左下角返回按钮 {BACK_BTN}")
        tap(BACK_BTN)
        time.sleep(1)
        img = screenshot()
        if img is None:
            continue
        vision.ocr_screenshot(img)
        if (states.is_battling(img) or states.is_skill_select(img) or states.is_level_select(img) or
                states.is_victory(img) or states.is_pay_popup(img) or states.is_activity_popup(img) or
                states.is_elite_drop(img) or states.is_reward_popup(img)):
            print(f"    ✅ 已回到正常游戏循环")
            return True
        print(f"    ⚠ 仍为未知界面，准备重试")
    print(f"    ❌ 多次返回后仍为未知界面，下轮循环继续尝试")
    return False


def clean_screenshots():
    """清理截图文件（模拟器内 + 本地临时文件）"""
    run_adb(f'shell rm -f {SCREENSHOT_REMOTE}')
    if os.path.exists(SCREENSHOT_LOCAL):
        try:
            os.remove(SCREENSHOT_LOCAL)
        except Exception:
            pass
