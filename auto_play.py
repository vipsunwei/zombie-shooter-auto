#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
向僵尸开炮 - 自动闯关脚本
==========================
基于 ADB 操作安卓模拟器（支持 MuMu / 雷电 等），自动识别界面并点击：
  - 技能选择界面 → 自动选技能（默认中间卡片）
  - 通关界面     → 自动点返回 → 进入下一关 → 点开始
  - 付费礼包弹窗 → 自动点右上角 × 关闭
  - 活动中心界面 → 自动点右上角 × 关闭
  - 其他状态     → 等待（战斗中角色自动射击）

模拟器支持：
  - 自动检测已安装的模拟器（MuMu / 雷电）
  - 也可在配置区手动指定 ADB_PATH 和 DEVICE

使用方法：
  1. 启动模拟器，打开《向僵尸开炮》，进入任意关卡
  2. 运行脚本（默认MuMu模拟器）:
       python auto_play.py
     指定雷电模拟器:
       python auto_play.py leidian
       python auto_play.py ld
     指定MuMu模拟器:
       python auto_play.py mumu
     自动检测:
       python auto_play.py auto
     查看帮助:
       python auto_play.py --help
  3. 按 Ctrl+C 停止

注意：运行脚本期间请勿手动操作模拟器，避免点击冲突。
"""

import subprocess
import time
import os
import sys
import random
import numpy as np
from PIL import Image
import easyocr

# ============================================================
#  配置区（根据需要修改）
# ============================================================

# 模拟器类型: "mumu"=MuMu模拟器（默认） | "leidian"=雷电模拟器 | "auto"=自动检测
# 也可通过命令行参数指定: python auto_play.py mumu / python auto_play.py leidian / python auto_play.py ld
EMULATOR_TYPE = "mumu"

# ADB路径（留空则自动检测，也可手动指定）
ADB_PATH = ""

# ADB设备地址（留空则自动检测，也可手动指定，如 "127.0.0.1:16384"）
DEVICE = ""

# 技能选择策略: "middle" | "left" | "right" | "random"
SKILL_STRATEGY = "middle"

# 每次循环检测间隔（秒）
CHECK_INTERVAL = 0.8

# 每关通关后清理截图（模拟器内 + 本地临时文件）
CLEAN_SCREENSHOT_PER_LEVEL = True

# 截图临时文件（模拟器内 + 本地）
SCREENSHOT_REMOTE = "/sdcard/auto_play.png"
SCREENSHOT_LOCAL  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_current_screen.png")

# ============================================================
#  命令行参数解析
# ============================================================

def parse_args():
    """解析命令行参数
    支持的用法:
      python auto_play.py              # 默认MuMu
      python auto_play.py mumu         # 指定MuMu
      python auto_play.py leidian      # 指定雷电
      python auto_play.py ld           # 指定雷电（简写）
      python auto_play.py --emulator leidian
      python auto_play.py --help       # 显示帮助
    返回: 模拟器类型字符串（内部统一用 mumu / ldplayer）
    """
    args = sys.argv[1:]
    
    # 显示帮助
    if "--help" in args or "-h" in args:
        print("""
向僵尸开炮 - 自动闯关脚本
==========================

用法:
  python auto_play.py [模拟器类型]

模拟器类型:
  mumu        MuMu模拟器（默认）
  leidian     雷电模拟器（简写: ld）
  auto        自动检测

示例:
  python auto_play.py              # 弹出选择菜单（上下箭头选择）
  python auto_play.py mumu         # 直接指定MuMu模拟器
  python auto_play.py leidian      # 直接指定雷电模拟器
  python auto_play.py ld           # 直接指定雷电模拟器（简写）
  python auto_play.py --emulator leidian

其他参数:
  --help, -h    显示此帮助信息
        """)
        sys.exit(0)
    
    # 解析 --emulator 参数
    if "--emulator" in args:
        idx = args.index("--emulator")
        if idx + 1 < len(args):
            emulator = args[idx + 1].lower()
            return _normalize_emulator(emulator)
    
    # 解析位置参数（第一个非选项参数）
    for arg in args:
        if not arg.startswith("-"):
            return _normalize_emulator(arg.lower())
    
    # 没有参数，弹出交互式选择菜单
    return select_emulator_interactive()

def _normalize_emulator(emulator):
    """将用户输入的模拟器名称规范化为内部统一格式
    支持各种别名和简写
    """
    # 雷电相关别名
    if emulator in ["leidian", "ld", "ldplayer", "雷电", "leidianplayer"]:
        return "ldplayer"
    # MuMu相关别名
    elif emulator in ["mumu", "mu", "mumuplayer", "网易", "netease"]:
        return "mumu"
    # 自动检测
    elif emulator in ["auto", "自动", "auto_detect"]:
        return "auto"
    else:
        print(f"⚠ 未知模拟器类型: {emulator}，使用默认MuMu")
        return "mumu"

def enable_ansi_escape():
    """启用Windows控制台ANSI转义码支持（用于光标移动等）"""
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        # STD_OUTPUT_HANDLE = -11, ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        return True
    except Exception:
        return False

def select_emulator_interactive():
    """交互式选择模拟器（上下箭头选择，回车确认）
    - 默认选中MuMu
    - 上下箭头切换选项
    - 回车确认选择
    - Ctrl+C 取消
    返回: 模拟器类型字符串
    """
    import msvcrt
    
    # 启用ANSI转义码支持
    enable_ansi_escape()
    
    options = [
        ("mumu", "MuMu 模拟器（默认推荐）"),
        ("ldplayer", "雷电模拟器"),
        ("auto", "自动检测"),
    ]
    
    selected = 0  # 默认选中第一个
    
    print("\n" + "=" * 45)
    print("  请选择模拟器（上下箭头选择，回车确认）")
    print("=" * 45)
    
    # 记录选项开始的行号（用于光标移动）
    menu_start_line = 4  # 上面打印了4行（空行+分隔线+提示+分隔线）
    
    while True:
        # 显示选项
        for i, (key, display) in enumerate(options):
            if i == selected:
                print(f"  ▶ {display}")
            else:
                print(f"    {display}")
        
        print("=" * 45)
        
        # 读取键盘输入
        key = msvcrt.getch()
        
        # 处理特殊键（上下箭头是两个字节：0xe0 + 方向键码）
        if key == b'\xe0':
            key = msvcrt.getch()
            if key == b'H':  # 上箭头
                selected = (selected - 1) % len(options)
            elif key == b'P':  # 下箭头
                selected = (selected + 1) % len(options)
        elif key == b'\r':  # 回车
            emulator_type = options[selected][0]
            emulator_display = options[selected][1]
            print(f"\n✅ 已选择: {emulator_display}")
            return emulator_type
        elif key == b'\x03':  # Ctrl+C
            print("\n\n已取消选择")
            sys.exit(0)
        
        # 移动光标到菜单开始位置，覆盖之前的输出
        # 向上移动 len(options)+1 行（选项数 + 分隔线）
        print(f"\033[{len(options)+1}A", end="", flush=True)

# ============================================================
#  坐标配置（基准分辨率 1080×1920，运行时自动按实际分辨率缩放）
# ============================================================

CARD_LEFT    = (173, 989)   # 左侧技能卡片中心
CARD_MIDDLE  = (540, 989)   # 中间技能卡片中心
CARD_RIGHT   = (907, 989)   # 右侧技能卡片中心
RETURN_BTN   = (540, 1747)  # 通关界面「返回」按钮
START_BTN    = (540, 1594)  # 关卡选择「开始游戏」按钮
CLOSE_POPUP  = (990, 240)   # 付费礼包弹窗右上角 ×
CLOSE_POPUP3 = (990, 170)   # 本周活动弹窗右上角 ×
TAP_BLANK    = (540, 750)   # 点击空白处（关闭精英掉落等，避开技能卡片区域）
BACK_BTN     = (85, 1785)   # 左下角返回按钮（未知界面兜底，返回上一级）
ACTIVITY_CENTER_CLOSE_BTN = (1005, 250)  # 活动中心界面右上角 × 关闭按钮

# ============================================================
#  颜色检测区域（基准 1080×1920）
# ============================================================

REGION_SKILL_TITLE = (400, 460, 680, 510)   # 「选择技能」橙色标题（精确区域）
REGION_VICTORY_TITLE = (350, 200, 730, 300)  # 「完美通关」顶部大字（通关界面唯一特征）
REGION_VICTORY_TABS = (50, 1450, 1030, 1520) # 通关结算底部「奖励总览/伤害统计/问题上报」标签（唯一特征）
REGION_RETURN_BTN  = (350, 1700, 730, 1800) # 通关「返回」黄色按钮
REGION_START_BTN   = (350, 1550, 730, 1650) # 「开始游戏」橙色按钮（单关选择界面）
REGION_LEVEL_TITLE  = (50, 80, 250, 130)     # 「关卡选择」顶部标题（关卡列表界面）
REGION_SELECT_BTN   = (350, 1700, 730, 1800) # 底部黄色「选择」按钮（关卡列表界面）
REGION_ELITE_TITLE  = (400, 1000, 680, 1070) # 精英掉落中间偏下「精英掉落」白色标题（唯一特征）
REGION_REFRESH_BTN  = (350, 1650, 730, 1750) # 精英掉落底部青色「刷新」按钮（独特特征）
REGION_CLOSE_HINT   = (350, 1840, 730, 1890) # 精英掉落最底部「点击空白处关闭」白色文字（独特特征）
REGION_BOTTOM_BTN   = (350, 1700, 730, 1800) # 底部黄色按钮区域（关卡选择有"选择"，通关有"返回"，精英掉落没有）
REGION_REWARD_TITLE = (350, 550, 730, 640)  # 「恭喜获得」奖励展示橙色标签

# 弹窗×按钮 + 下方深色遮罩（双条件精确识别，避免误判技能选择/关卡选择界面）
REGION_POPUP_X1    = (975, 225, 1005, 255) # 付费/见面豪礼弹窗 ×
REGION_POPUP_BELOW1 = (970, 260, 1010, 280) # 付费弹窗×下方深色遮罩
REGION_POPUP_X2    = (975, 155, 1005, 185) # 本周活动弹窗 ×
REGION_POPUP_BELOW2 = (970, 190, 1010, 210) # 活动弹窗×下方深色遮罩
REGION_PAUSE_BTN   = (40, 25, 110, 75)      # 左上角暂停按钮（战斗中/技能选择有，弹窗没有）

# 战斗中界面特征（用于区分战斗中和真正的未知界面）
REGION_PAUSE_BTN   = (940, 50, 990, 100)  # 战斗中右上角暂停按钮（白色||图标）
REGION_WAVE_INFO   = (20, 20, 180, 90)    # 战斗中左上角波数显示（白色文字）

# ============================================================
#  全局状态
# ============================================================

screen_w, screen_h = 1080, 1920
in_battle_loop = False  # 状态机开关：True=游戏循环中，只判断游戏循环界面；False=非游戏循环，判断其他界面

# ============================================================
#  OCR 文字识别（EasyOCR）
# ============================================================

_ocr_reader = None  # OCR阅读器（懒加载，只初始化一次）
_current_ocr_result = None  # 当前循环的OCR结果缓存（多个检测函数共享）

def get_ocr_reader():
    """获取OCR阅读器（懒加载，只初始化一次）"""
    global _ocr_reader
    if _ocr_reader is None:
        print("正在初始化OCR模型（首次运行需下载，请稍候）...")
        _ocr_reader = easyocr.Reader(['ch_sim', 'en'], gpu=False)
    return _ocr_reader

def set_current_ocr_result(result):
    """设置当前循环的OCR结果（主循环中调用一次，多个检测函数共享）"""
    global _current_ocr_result
    _current_ocr_result = result

def ocr_screenshot(img):
    """对截图进行OCR识别，返回识别结果列表，并缓存到全局变量"""
    reader = get_ocr_reader()
    result = reader.readtext(np.array(img))
    set_current_ocr_result(result)
    return result

def has_text(keyword, region=None, min_confidence=0.4):
    """从当前OCR结果中检测是否包含指定关键词
    - keyword: 关键词（支持部分匹配）
    - region: 可选，指定检测区域 (x1,y1,x2,y2)，基准1080×1920
    - min_confidence: 最低置信度（默认0.4，游戏字体有些艺术化，适当降低阈值）
    返回: True=检测到, False=未检测到
    """
    result = _current_ocr_result
    if result is None:
        return False
    for item in result:
        box, text, confidence = item
        if confidence < min_confidence:
            continue
        if keyword in text:
            if region:
                # 检查文字中心位置是否在指定区域内
                center_x = sum(p[0] for p in box) / 4
                center_y = sum(p[1] for p in box) / 4
                x1, y1, x2, y2 = scale_region(region)
                if x1 <= center_x <= x2 and y1 <= center_y <= y2:
                    return True
            else:
                return True
    return False

def find_text(keyword, min_confidence=0.4):
    """从当前OCR结果中查找关键词的位置
    返回: (center_x, center_y) 或 None
    """
    result = _current_ocr_result
    if result is None:
        return None
    for item in result:
        box, text, confidence = item
        if confidence < min_confidence:
            continue
        if keyword in text:
            center_x = int(sum(p[0] for p in box) / 4)
            center_y = int(sum(p[1] for p in box) / 4)
            return (center_x, center_y)
    return None

# ============================================================
#  底部导航栏检测（硬编码位置 + 亮度判断，不依赖OCR文字识别）
# ============================================================

# 底部导航栏7个按钮的固定位置（从左到右，基准1080×1920）
BOTTOM_NAV_BUTTONS = [
    ("商城", 90, 1871),
    ("角色", 239, 1871),
    ("核心", 390, 1871),
    ("战斗", 540, 1871),
    ("基地", 690, 1871),
    ("军团", 839, 1871),
    ("征途", 989, 1871),
]
# 选中状态亮度阈值（选中=亮白色>650，未选中=暗金色<620）
SELECTED_BRIGHTNESS_THRESHOLD = 650

def _get_pixel_brightness(cx, cy, radius=8):
    """获取指定位置最亮像素的亮度值（R+G+B）"""
    try:
        img = Image.open(SCREENSHOT_LOCAL)
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
    """获取底部导航栏所有按钮（名称 + 位置 + 亮度）
    返回: [(name, x, y, brightness), ...]
    """
    buttons = []
    for name, x, y in BOTTOM_NAV_BUTTONS:
        sx, sy = scale((x, y))
        brightness = _get_pixel_brightness(sx, sy)
        buttons.append((name, sx, sy, brightness))
    return buttons

def get_selected_bottom_nav():
    """获取底部导航栏当前选中的按钮名称
    返回: 选中的按钮名称，或None
    """
    buttons = get_bottom_nav_buttons()
    if not buttons:
        return None
    
    # 找亮度最高的按钮
    brightest = max(buttons, key=lambda b: b[3])
    if brightest[3] >= SELECTED_BRIGHTNESS_THRESHOLD:
        return brightest[0]
    return None

def click_bottom_nav(name):
    """点击底部导航栏指定按钮（直接点击固定位置，不依赖OCR）
    返回: True=点击成功, False=未找到按钮
    """
    for btn_name, x, y in BOTTOM_NAV_BUTTONS:
        if btn_name == name:
            tap((x, y))
            return True
    return False

# ============================================================
#  模拟器自动检测与ADB连接
# ============================================================

def find_files_by_name(filename, search_dirs=None, max_depth=3):
    """在指定目录下递归查找指定文件名
    - filename: 要查找的文件名（如 "adb.exe"）
    - search_dirs: 要搜索的目录列表，None则使用常见目录
    - max_depth: 最大递归深度
    返回: 找到的文件路径列表
    """
    if search_dirs is None:
        # 常见的安装目录
        search_dirs = [
            r"C:\Program Files",
            r"C:\Program Files (x86)",
            "C:\\",
            "D:\\",
            "E:\\",
            "F:\\",
        ]
    
    found = []
    for base_dir in search_dirs:
        if not os.path.exists(base_dir):
            continue
        try:
            for root, dirs, files in os.walk(base_dir):
                # 控制递归深度
                depth = root.replace(base_dir, "").count(os.sep)
                if depth > max_depth:
                    dirs.clear()
                    continue
                # 跳过系统目录和隐藏目录
                dirs[:] = [d for d in dirs if not d.startswith('$') and not d.startswith('.') 
                           and d.lower() not in ['windows', 'system32', 'syswow64', '$recycle.bin']]
                if filename in files:
                    found.append(os.path.join(root, filename))
        except (PermissionError, OSError):
            continue
    return found

def get_install_path_from_registry(reg_key, value_name="InstallPath"):
    """从Windows注册表读取软件安装路径
    - reg_key: 注册表键路径
    - value_name: 要读取的值名称
    返回: 安装路径或None
    """
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_key)
        value, _ = winreg.QueryValueEx(key, value_name)
        winreg.CloseKey(key)
        return value
    except Exception:
        pass
    
    # 尝试HKEY_CURRENT_USER
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
    """检测MuMu模拟器的ADB路径和端口（自动寻找安装路径）
    返回: (adb_path, device) 或 (None, None)
    """
    # 方法1：从注册表读取安装路径
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
                for port in [16384, 7555, 16385]:
                    return (adb_path, f"127.0.0.1:{port}")
    
    # 方法2：在常见目录下查找 adb.exe（MuMu的adb在 nx_main 目录下）
    adb_files = find_files_by_name("adb.exe", max_depth=4)
    for adb_path in adb_files:
        # MuMu的adb路径通常包含 "MuMu" 或 "Netease"
        path_lower = adb_path.lower()
        if "mumu" in path_lower or "netease" in path_lower:
            for port in [16384, 7555, 16385]:
                return (adb_path, f"127.0.0.1:{port}")
    
    return (None, None)

def detect_ldplayer_adb():
    """检测雷电模拟器的ADB路径和端口（自动寻找安装路径）
    返回: (adb_path, device) 或 (None, None)
    """
    # 方法1：从注册表读取安装路径
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
                for port in [5554, 5555, 5556, 5557, 5558]:
                    return (adb_path, f"127.0.0.1:{port}")
    
    # 方法2：在常见目录下查找 adb.exe（雷电的adb在安装根目录下）
    adb_files = find_files_by_name("adb.exe", max_depth=3)
    for adb_path in adb_files:
        # 雷电的adb路径通常包含 "leidian" 或 "ldplayer"
        path_lower = adb_path.lower()
        if "leidian" in path_lower or "ldplayer" in path_lower:
            for port in [5554, 5555, 5556, 5557, 5558]:
                return (adb_path, f"127.0.0.1:{port}")
    
    return (None, None)

def detect_emulator():
    """自动检测已安装的模拟器（在目标电脑上自动寻找）
    返回: (adb_path, device, emulator_name) 或 (None, None, None)
    优先检测MuMu，其次雷电
    """
    print("  正在自动检测模拟器...")
    
    # 先检测MuMu
    adb_path, device = detect_mumu_adb()
    if adb_path:
        return (adb_path, device, "MuMu")
    
    # 再检测雷电
    adb_path, device = detect_ldplayer_adb()
    if adb_path:
        return (adb_path, device, "雷电")
    
    return (None, None, None)

def test_adb_connection(adb_path, device, timeout=5):
    """测试ADB连接是否可用
    返回: True=连接成功, False=连接失败
    """
    try:
        # 先尝试connect
        full = f'"{adb_path}" connect {device}'
        r = subprocess.run(full, capture_output=True, text=True, shell=True, timeout=timeout)
        # 再测试get-state
        full2 = f'"{adb_path}" -s {device} get-state'
        r2 = subprocess.run(full2, capture_output=True, text=True, shell=True, timeout=timeout)
        return "device" in (r2.stdout or "")
    except Exception:
        return False

def init_adb():
    """初始化ADB连接（根据配置自动检测或使用手动配置）
    返回: (adb_path, device, emulator_name)
    """
    global ADB_PATH, DEVICE
    
    # 如果手动配置了ADB路径和设备，直接使用
    if ADB_PATH and DEVICE:
        if os.path.exists(ADB_PATH):
            print(f"  使用手动配置: {ADB_PATH}")
            print(f"  设备: {DEVICE}")
            return (ADB_PATH, DEVICE, "手动配置")
        else:
            print(f"  ⚠ 手动配置的ADB路径不存在: {ADB_PATH}，尝试自动检测...")
    
    # 根据模拟器类型检测
    if EMULATOR_TYPE == "mumu":
        adb_path, device = detect_mumu_adb()
        emulator_name = "MuMu"
    elif EMULATOR_TYPE == "ldplayer":
        adb_path, device = detect_ldplayer_adb()
        emulator_name = "雷电"
    else:  # auto
        adb_path, device, emulator_name = detect_emulator()
    
    if not adb_path:
        print(f"  ❌ 未检测到模拟器！请手动配置 ADB_PATH 和 DEVICE")
        print(f"  支持的模拟器: MuMu、雷电（LDPlayer）")
        sys.exit(1)
    
    # 测试连接
    print(f"  检测到模拟器: {emulator_name}")
    print(f"  ADB路径: {adb_path}")
    print(f"  尝试连接设备: {device} ...")
    
    if test_adb_connection(adb_path, device):
        print(f"  ✅ 连接成功!")
        ADB_PATH = adb_path
        DEVICE = device
        return (adb_path, device, emulator_name)
    else:
        # 如果自动检测的端口连不上，尝试该模拟器的其他端口
        print(f"  ⚠ 端口 {device} 连接失败，尝试其他端口...")
        if emulator_name == "MuMu":
            for port in [16384, 7555, 16385, 16386]:
                dev = f"127.0.0.1:{port}"
                if test_adb_connection(adb_path, dev):
                    print(f"  ✅ 端口 {dev} 连接成功!")
                    ADB_PATH = adb_path
                    DEVICE = dev
                    return (adb_path, dev, emulator_name)
        elif emulator_name == "雷电":
            for port in [5554, 5555, 5556, 5557, 5558, 5559, 5560]:
                dev = f"127.0.0.1:{port}"
                if test_adb_connection(adb_path, dev):
                    print(f"  ✅ 端口 {dev} 连接成功!")
                    ADB_PATH = adb_path
                    DEVICE = dev
                    return (adb_path, dev, emulator_name)
        
        print(f"  ❌ 所有端口均连接失败！请确保模拟器已启动并开启ADB调试")
        sys.exit(1)

# ============================================================
#  ADB 工具函数
# ============================================================

def run_adb(cmd, timeout=15):
    """执行 adb 命令，返回 stdout"""
    full = f'"{ADB_PATH}" -s {DEVICE} {cmd}'
    try:
        r = subprocess.run(full, capture_output=True, text=True, shell=True, timeout=timeout)
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

def scale(coord):
    """坐标按分辨率缩放"""
    x, y = coord
    return int(x * screen_w / 1080), int(y * screen_h / 1920)

def scale_region(region):
    """区域按分辨率缩放"""
    x1, y1, x2, y2 = region
    return (int(x1*screen_w/1080), int(y1*screen_h/1920),
            int(x2*screen_w/1080), int(y2*screen_h/1920))

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
    """模拟点击"""
    x, y = scale(coord)
    run_adb(f'shell input tap {x} {y}')

def close_with_verify(close_pos, check_func, name, max_retries=2):
    """
    验证式关闭弹窗：点一次→截图验证→确认关闭就停，防止误入其他界面
    - close_pos: 固定关闭位置
    - check_func: 检测该弹窗是否还存在的函数（返回True=还在）
    - name: 弹窗名称（用于日志）
    - max_retries: 最大重试次数
    返回: True=已关闭, False=多次尝试后仍未关闭
    """
    for attempt in range(1, max_retries + 1):
        print(f"    → 第{attempt}次点{name}关闭位置 {close_pos}")
        tap(close_pos)
        time.sleep(0.8)
        img = screenshot()
        if img is None:
            continue
        ocr_screenshot(img)  # 更新OCR缓存
        if not check_func(img):
            print(f"    ✅ {name}已关闭，停止操作")
            return True
        print(f"    ⚠ {name}仍在，准备重试")
    print(f"    ❌ {name}多次尝试未关闭，跳过（下轮循环再处理）")
    return False

def fallback_back():
    """
    未知界面兜底：点左下角返回按钮 → 截图验证是否回到正常游戏循环
    - 回到已知界面（战斗中/技能选择/关卡选择/弹窗等）→ 返回True
    - 仍为未知界面 → 最多重试2次
    """
    for attempt in range(1, 3):
        print(f"    → 第{attempt}次点左下角返回按钮 {BACK_BTN}")
        tap(BACK_BTN)
        time.sleep(1)
        img = screenshot()
        if img is None:
            continue
        ocr_screenshot(img)  # 更新OCR缓存
        # 验证是否回到了正常游戏循环（任意已知界面）
        if (is_battling(img) or is_skill_select(img) or is_level_select(img) or
            is_victory(img) or is_pay_popup(img) or is_activity_popup(img) or
            is_elite_drop(img) or is_reward_show(img)):
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

# ============================================================
#  界面检测（基于OCR文字识别，准确可靠）
# ============================================================

def is_skill_select(img):
    """选择技能界面：检测"选择技能"文字（位置在屏幕中上方）"""
    return has_text("选择技能", region=(300, 400, 780, 560))

def is_elite_drop(img):
    """精英掉落界面：检测"精英掉落"文字（位置在屏幕中间偏下）
    注意："精英掉落"字体较小，OCR置信度偏低（约0.38），降低阈值
    """
    return has_text("精英掉落", region=(300, 1200, 780, 1450), min_confidence=0.2)

def is_victory_settlement(img):
    """通关结算界面：检测结算页面特征文字
    特征：恭喜获得 + 伤害统计/问题上报/奖励总览 + 返回
    满足2个以上特征即认为是结算页面
    """
    # 特征1：标签栏（伤害统计/问题上报/奖励总览）
    tabs_region = (50, 1400, 1030, 1560)
    has_tabs = (has_text("伤害统计", region=tabs_region, min_confidence=0.3) or
                has_text("问题上报", region=tabs_region, min_confidence=0.3) or
                has_text("奖励总览", region=tabs_region, min_confidence=0.2) or
                has_text("奖励总笕", region=tabs_region, min_confidence=0.2))  # OCR可能识别错
    
    # 特征2：返回按钮
    has_return = has_text("返回", region=(500, 1600, 1030, 1800), min_confidence=0.5)
    
    # 特征3：恭喜获得
    has_congrats = has_text("恭喜获得", region=(300, 350, 780, 500), min_confidence=0.5)
    
    # 满足2个以上特征即认为是结算页面
    count = sum([has_tabs, has_return, has_congrats])
    return count >= 2

def get_today_remaining_count():
    """解析今日剩余双倍奖励次数
    返回: (当前次数, 总次数) 或 None
    OCR可能识别成 "今日剩余次数:3/3" 或 "今日剩余次数:313"（斜杠被识别成1）等
    """
    result = _current_ocr_result
    if result is None:
        return None
    
    import re
    for item in result:
        box, text, confidence = item
        if "今日剩余次数" in text:
            # 提取所有数字
            numbers = re.findall(r'\d+', text)
            if len(numbers) >= 2:
                return (int(numbers[0]), int(numbers[1]))
            elif len(numbers) == 1:
                # 只有一个数字，可能是"X/Y"被识别成"XY"（斜杠被识别成1或其他字符）
                # 比如"313"实际是"3/3"，取第一位为当前次数，最后一位为总次数
                num_str = numbers[0]
                if len(num_str) >= 2:
                    current = int(num_str[0])
                    total = int(num_str[-1])
                    return (current, total)
                return (int(num_str), None)
    return None

def should_click_double_reward():
    """是否应该点击双倍奖励按钮
    条件：
    1. 有"双倍奖励"按钮
    2. 今日剩余次数 > 0
    3. 有"完美通关"字样
    """
    # 条件1：检测双倍奖励按钮
    double_reward_pos = find_text("双倍奖励", min_confidence=0.3)
    if not double_reward_pos:
        return False
    
    # 条件2：检测完美通关
    if not has_text("完美通关", region=(300, 200, 780, 350), min_confidence=0.5):
        return False
    
    # 条件3：今日剩余次数 > 0
    remaining = get_today_remaining_count()
    if remaining is None:
        # 检测不到今日剩余次数，可能是OCR识别问题，保守起见不点击
        return False
    
    current_count, _ = remaining
    if current_count <= 0:
        return False
    
    return True

def is_victory(img):
    """通关界面：检测"完美通关"文字（位置在屏幕上方）"""
    return has_text("完美通关", region=(300, 150, 780, 350))

def is_level_select(img):
    """单关选择界面：检测"开始游戏"文字（位置在屏幕中下方）
    注意："开始游戏"字体较艺术化，OCR置信度偏低，降低阈值到0.1
    """
    return has_text("开始游戏", region=(300, 1480, 780, 1680), min_confidence=0.1)

def is_level_list(img):
    """关卡列表界面：检测"关卡选择"标题 + 底部"选择"按钮"""
    has_title = has_text("关卡选择", region=(50, 50, 350, 160))
    has_select_btn = has_text("选择", region=(300, 1650, 780, 1880))
    return has_title and has_select_btn

def is_battling(img):
    """战斗中界面：检测"波次"文字（位置在屏幕左上角）"""
    return has_text("波次", region=(20, 20, 250, 130))

def is_pay_popup(img):
    """付费/见面豪礼弹窗：检测弹窗区域内的特征文字（限制在屏幕中间，避免左侧活动栏误判）"""
    # 弹窗通常在屏幕中间区域：x=200~900, y=200~1500
    region = (200, 200, 900, 1500)
    return (has_text("见面豪礼", region=region) or
            has_text("付费", region=region) or
            has_text("限时礼包", region=region))

def is_activity_popup(img):
    """本周活动弹窗：检测弹窗区域内的特征文字（限制在屏幕中间）"""
    region = (200, 200, 900, 1500)
    return has_text("本周活动", region=region)

def is_reward_show(img):
    """恭喜获得/奖励展示界面：检测"恭喜获得"文字（位置在屏幕中间）"""
    return has_text("恭喜获得", region=(300, 500, 780, 700))

def is_activity_center(img):
    """活动中心界面：检测"炙热咆哮"或"超值回馈"文字（这两个OCR准确率很高）
    这是游戏的活动列表/活动中心界面，需要点击右上角×关闭
    """
    return (has_text("炙热咆哮", region=(100, 750, 500, 900), min_confidence=0.5) or
            has_text("超值回馈", region=(500, 900, 900, 1100), min_confidence=0.5))

def is_level_up(img):
    """等级提升界面：检测"等级提升"标题 或 "点击屏幕继续"提示
    这是升级后弹出的界面，需要点击屏幕任意位置继续
    """
    # 检测"等级提升"标题（屏幕上方）
    if has_text("等级提升", region=(300, 200, 780, 350), min_confidence=0.5):
        return True
    # 检测"点击屏幕继续"提示（屏幕底部）
    if has_text("点击屏幕继续", region=(300, 1750, 780, 1900), min_confidence=0.5):
        return True
    return False

def has_click_blank_hint(img):
    """检测界面上是否有"点击空白处关闭"提示（通用关闭提示）
    返回: True=有此提示, False=没有
    """
    return has_text("点击空白处关闭", region=(300, 1750, 780, 1900), min_confidence=0.3)

def click_blank_to_close():
    """通用关闭函数：找到"点击空白处关闭"文字的位置并点击
    验证式关闭：点一次截一次图，确认关闭就停
    返回: True=已关闭, False=多次尝试未关闭
    """
    # 用OCR找到"点击空白处关闭"文字的位置（动态定位，不写死坐标）
    blank_pos = find_text("点击空白处关闭", min_confidence=0.3)
    if not blank_pos:
        # 如果OCR没找到，用默认位置（底部中间）
        blank_pos = (540, 1822)
        print(f"    ⚠ OCR未找到「点击空白处关闭」，用默认位置 {blank_pos}")
    
    for attempt in range(1, 3):
        print(f"    → 第{attempt}次点击「点击空白处关闭」 {blank_pos}")
        tap(blank_pos)
        time.sleep(1)
        img = screenshot()
        if img is None:
            continue
        ocr_screenshot(img)  # 更新OCR缓存
        if not has_click_blank_hint(img):
            print(f"    ✅ 界面已关闭，停止操作")
            return True
        print(f"    ⚠ 界面仍在，准备重试")
    print(f"    ❌ 多次尝试未关闭，跳过（下轮循环再处理）")
    return False

def is_patrol(img):
    """巡逻/扫荡界面：检测"快速巡逻" 或 "点击空白处关闭"+"暂无奖励"
    这是游戏的离线收益/巡逻界面，需要点击空白处关闭
    """
    # 检测"快速巡逻"按钮（最明显的特征）
    if has_text("快速巡逻", region=(150, 1400, 450, 1550), min_confidence=0.5):
        return True
    # 检测"最长巡逻" + "点击空白处关闭"（组合判断）
    if has_text("最长巡逻", region=(300, 700, 600, 800), min_confidence=0.3):
        if has_text("点击空白处关闭", region=(300, 1750, 780, 1900), min_confidence=0.3):
            return True
    return False

def close_patrol():
    """关闭巡逻/扫荡界面：使用通用的"点击空白处关闭"逻辑"""
    return click_blank_to_close()

def close_level_up():
    """关闭等级提升界面：点击底部"点击屏幕继续"位置（避免点到中间金币弹出详情页）
    验证式关闭：点一次截一次图，确认关闭就停
    """
    tap_pos = (540, 1844)  # 底部"点击屏幕继续"文字位置
    for attempt in range(1, 3):
        print(f"    → 第{attempt}次点击底部「点击屏幕继续」 {tap_pos}")
        tap(tap_pos)
        time.sleep(1)
        img = screenshot()
        if img is None:
            continue
        ocr_screenshot(img)  # 更新OCR缓存
        if not is_level_up(img):
            print(f"    ✅ 等级提升界面已关闭，停止操作")
            return True
        print(f"    ⚠ 等级提升界面仍在，准备重试")
    print(f"    ❌ 等级提升界面多次尝试未关闭，跳过（下轮循环再处理）")
    return False

def close_activity_center():
    """关闭活动中心界面：点击右上角×关闭按钮，验证式关闭（点一次截一次图确认）"""
    for attempt in range(1, 3):
        print(f"    → 第{attempt}次点活动中心关闭按钮 {ACTIVITY_CENTER_CLOSE_BTN}")
        tap(ACTIVITY_CENTER_CLOSE_BTN)
        time.sleep(1)
        img = screenshot()
        if img is None:
            continue
        ocr_screenshot(img)  # 更新OCR缓存
        if not is_activity_center(img):
            print(f"    ✅ 活动中心已关闭，停止操作")
            return True
        print(f"    ⚠ 活动中心仍在，准备重试")
    print(f"    ❌ 活动中心多次尝试未关闭，跳过（下轮循环再处理）")
    return False

# ============================================================
#  操作逻辑
# ============================================================

def do_select_skill():
    """按策略选技能卡片"""
    if SKILL_STRATEGY == "left":
        tap(CARD_LEFT)
    elif SKILL_STRATEGY == "right":
        tap(CARD_RIGHT)
    elif SKILL_STRATEGY == "random":
        tap(random.choice([CARD_LEFT, CARD_MIDDLE, CARD_RIGHT]))
    else:
        tap(CARD_MIDDLE)

def do_victory():
    """通关流程：先判断是否需要点击双倍奖励，然后点击返回
    - 完美通关 + 有双倍奖励按钮 + 剩余次数>0 → 先点双倍奖励，再点返回
    - 其他情况（非完美/次数用完/无按钮）→ 直接点返回
    """
    # 先判断是否需要点击双倍奖励
    should_double = should_click_double_reward()
    
    if should_double:
        double_reward_pos = find_text("双倍奖励", min_confidence=0.3)
        if double_reward_pos:
            remaining = get_today_remaining_count()
            remaining_str = f"{remaining[0]}/{remaining[1]}" if remaining else "未知"
            print(f"    → 完美通关 + 双倍奖励(剩余{remaining_str})，先点击双倍奖励 {double_reward_pos}")
            tap(double_reward_pos)
            time.sleep(2)
            # 点击双倍奖励后可能跳转到广告或其他界面，重新截图识别
            img = screenshot()
            if img is not None:
                ocr_screenshot(img)
    else:
        # 不满足双倍奖励条件，输出具体原因
        if not has_text("完美通关", region=(300, 200, 780, 350), min_confidence=0.5):
            print(f"    → 非完美通关，跳过双倍奖励，直接点返回")
        else:
            remaining = get_today_remaining_count()
            if remaining and remaining[0] <= 0:
                remaining_str = f"{remaining[0]}/{remaining[1]}" if remaining[1] else str(remaining[0])
                print(f"    → 双倍奖励次数已用完({remaining_str})，跳过双倍奖励，直接点返回")
            elif not find_text("双倍奖励", min_confidence=0.3):
                print(f"    → 未检测到双倍奖励按钮，直接点返回")
            else:
                print(f"    → 不满足双倍奖励条件，直接点返回")
    
    # 点击返回
    return_pos = find_text("返回", min_confidence=0.5)
    if return_pos:
        print(f"    → OCR识别到「返回」按钮位置 {return_pos}，点击返回")
        tap(return_pos)
    else:
        # 兜底：如果OCR没识别到，用默认位置（右边）
        fallback_pos = (754, 1695)
        print(f"    ⚠ OCR未识别到「返回」按钮，用兜底位置 {fallback_pos}")
        tap(fallback_pos)
    time.sleep(2)

def close_elite_drop():
    """关闭精英掉落界面：点左下角快速结束转盘，截图确认仍在精英掉落再点第二次关闭"""
    ELITE_TAP = (100, 1750)  # 左下角空白处，统一点击位置
    
    # 第一次点左下角：快速结束转盘
    tap(ELITE_TAP)
    print(f"    → 第1次点左下角结束转盘 {ELITE_TAP}")
    time.sleep(1.5)  # 等转盘停下来
    
    # 截图 + OCR识别，确认是否还是精英掉落界面
    img = screenshot()
    if img is not None:
        ocr_screenshot(img)
    if not is_elite_drop(img):
        print(f"    ✅ 转盘结束后精英掉落已关闭，无需第二次点击")
        return True
    
    # 还是精英掉落界面，点第二次左下角关闭
    print(f"    → 确认仍在精英掉落界面，第2次点左下角关闭 {ELITE_TAP}")
    tap(ELITE_TAP)
    time.sleep(0.8)
    
    # 截图 + OCR识别，验证是否关闭
    img = screenshot()
    if img is not None:
        ocr_screenshot(img)
    if not is_elite_drop(img):
        print(f"    ✅ 精英掉落已关闭，停止操作")
        return True
    
    # 还没关闭，再点一次
    print(f"    ⚠ 精英掉落仍在，再点一次左下角")
    tap(ELITE_TAP)
    time.sleep(0.8)
    img = screenshot()
    if img is not None:
        ocr_screenshot(img)
    if not is_elite_drop(img):
        print(f"    ✅ 精英掉落已关闭，停止操作")
        return True
    
    print(f"    ❌ 精英掉落多次尝试未关闭，跳过（下轮循环再处理）")
    return False

# ============================================================
#  主循环
# ============================================================

def main():
    global screen_w, screen_h, EMULATOR_TYPE
    
    # 解析命令行参数（优先级高于配置区）
    EMULATOR_TYPE = parse_args()
    emulator_display = {"mumu": "MuMu", "ldplayer": "雷电", "auto": "自动检测"}.get(EMULATOR_TYPE, EMULATOR_TYPE)
    
    print("=" * 55)
    print("   向僵尸开炮 · 自动闯关脚本")
    print("=" * 55)
    print(f"  模拟器: {emulator_display}（可用参数: mumu / leidian）")
    print(f"  策略 : 技能选 {SKILL_STRATEGY} 卡片")
    print("  停止 : Ctrl+C")
    print("-" * 55)

    # ---- 连接 ADB（自动检测模拟器）----
    print("[1/3] 检测并连接 ADB ...")
    adb_path, device, emulator_name = init_adb()
    
    # ---- 获取分辨率 ----
    screen_w, screen_h = get_screen_size()
    print(f"[2/3] 模拟器分辨率: {screen_w}×{screen_h}")
    
    # ---- 验证截图 ----
    print("[3/3] 验证截图 ...")
    test = screenshot()
    if test is None:
        print("❌ 截图失败，请检查 ADB 连接")
        return
    print(f"      截图尺寸: {test.size}")
    print("-" * 55)
    print(f"✅ 启动成功！模拟器: {emulator_name}，开始自动闯关\n")

    skill_cnt = 0
    level_cnt = 0
    popup_cnt = 0
    unknown_cnt = 0  # 连续未知界面计数（用于兜底）
    last_status = ""
    just_started = False  # 刚点开始游戏，进入战斗加载阶段，不触发兜底
    just_start_time = 0
    global in_battle_loop
    in_battle_loop = False  # 脚本启动时走完整判断，确定当前状态

    try:
        while True:
            # 截图（统计耗时）
            t0 = time.time()
            img = screenshot()
            screenshot_time = time.time() - t0
            if img is None:
                print(f"[{time.strftime('%H:%M:%S')}] ❌ 截图失败，1秒后重试")
                time.sleep(1)
                continue

            # OCR识别（统计耗时）
            t1 = time.time()
            ocr_result = ocr_screenshot(img)
            ocr_time = time.time() - t1
            text_count = len(ocr_result) if ocr_result else 0
            print(f"[{time.strftime('%H:%M:%S')}] 📸 截图{screenshot_time:.1f}s + 🔍 OCR{ocr_time:.1f}s({text_count}字)")

            status = "战斗中"

            # ============================================================
            #  状态机自动切换：
            #  不管当前是什么状态，只要界面符合游戏循环中的任何一种情况，
            #  就自动切换到游戏循环中（不一定只有点开始游戏才切换）
            # ============================================================
            if not in_battle_loop:
                if (is_victory_settlement(img) or is_skill_select(img) or
                    is_elite_drop(img) or is_battling(img)):
                    in_battle_loop = True
                    print(f"[{time.strftime('%H:%M:%S')}] 🔄 检测到游戏循环界面，自动切换到游戏循环中")

            # ============================================================
            #  状态机：
            #  in_battle_loop = True  → 游戏循环中，只判断四种状态
            #  in_battle_loop = False → 非游戏循环，判断其他界面
            # ============================================================

            if in_battle_loop:
                # ============================================================
                #  【游戏循环中】只判断四种状态，绝不误判其他界面
                #  1. 通关结算 → 点返回，关闭开关（跳出循环）
                #  2. 选择技能 → 选中间卡片
                #  3. 精英掉落 → 点左下角停止转盘，再点左下角关闭
                #  4. 战斗中   → 什么都不做，等下一次截图
                # ============================================================

                # 1. 通关结算界面：跳出游戏循环，点返回
                if is_victory_settlement(img):
                    status = "通关结算"
                    level_cnt += 1
                    in_battle_loop = False  # 关闭开关，跳出游戏循环
                    print(f"[{time.strftime('%H:%M:%S')}] 🏆 第 {level_cnt} 关通关！→ 点击返回，跳出游戏循环")
                    do_victory()
                    if CLEAN_SCREENSHOT_PER_LEVEL:
                        clean_screenshots()
                        print(f"[{time.strftime('%H:%M:%S')}] 🧹 已清理本关截图")
                    unknown_cnt = 0

                # 2. 选择技能界面：选中间卡片
                elif is_skill_select(img):
                    status = "选择技能"
                    do_select_skill()
                    skill_cnt += 1
                    print(f"[{time.strftime('%H:%M:%S')}] ⚡ 选择技能 → 选{SKILL_STRATEGY}卡片(540,989) ({skill_cnt})")
                    time.sleep(1.2)
                    unknown_cnt = 0

                # 3. 精英掉落界面：点左下角停止转盘，再点左下角关闭
                elif is_elite_drop(img):
                    status = "精英掉落"
                    print(f"[{time.strftime('%H:%M:%S')}] 🎁 精英掉落")
                    close_elite_drop()
                    unknown_cnt = 0

                # 4. 战斗中：什么都不做，等下一次截图
                elif is_battling(img):
                    status = "战斗中"
                    unknown_cnt = 0

                else:
                    # 游戏循环中出现未知界面，可能是加载中，等一下
                    status = "游戏循环-未知"
                    unknown_cnt = 0  # 游戏循环中不触发兜底，避免误操作

            else:
                # ============================================================
                #  【非游戏循环】判断其他界面，绝不误判游戏循环界面
                #  - 关卡选择 → 点开始游戏，打开开关（进入游戏循环）
                #  - 关卡列表 → 点选择
                #  - 奖励展示 → 关闭
                #  - 付费弹窗 → 关闭
                #  - 活动弹窗 → 关闭
                #  - 通关（旧检测）→ 点返回
                # ============================================================

                if is_pay_popup(img):
                    status = "付费弹窗"
                    print(f"[{time.strftime('%H:%M:%S')}] 💰 付费/见面豪礼弹窗")
                    close_with_verify(CLOSE_POPUP, is_pay_popup, "付费弹窗")
                    popup_cnt += 1
                    unknown_cnt = 0

                elif is_activity_popup(img):
                    status = "活动弹窗"
                    print(f"[{time.strftime('%H:%M:%S')}] 📅 本周活动弹窗")
                    close_with_verify(CLOSE_POPUP3, is_activity_popup, "活动弹窗")
                    popup_cnt += 1
                    unknown_cnt = 0

                elif has_click_blank_hint(img):
                    # 通用：界面上有"点击空白处关闭"提示，直接点击该位置关闭
                    status = "点击空白关闭"
                    print(f"[{time.strftime('%H:%M:%S')}] 🖱️ 检测到「点击空白处关闭」提示 → 点击关闭")
                    click_blank_to_close()
                    unknown_cnt = 0

                elif is_activity_center(img):
                    # 活动中心界面：点击右上角×关闭按钮
                    status = "活动中心"
                    print(f"[{time.strftime('%H:%M:%S')}] 🎪 活动中心界面 → 点右上角×关闭")
                    close_activity_center()
                    unknown_cnt = 0

                elif is_level_up(img):
                    # 等级提升界面：点击屏幕任意位置继续
                    status = "等级提升"
                    print(f"[{time.strftime('%H:%M:%S')}] ⬆️ 等级提升界面 → 点击屏幕继续")
                    close_level_up()
                    unknown_cnt = 0

                elif is_patrol(img):
                    # 巡逻/扫荡界面：点击空白处关闭
                    status = "巡逻界面"
                    print(f"[{time.strftime('%H:%M:%S')}] 🚶 巡逻/扫荡界面 → 点击空白处关闭")
                    close_patrol()
                    unknown_cnt = 0

                elif is_level_list(img):
                    status = "关卡列表"
                    print(f"[{time.strftime('%H:%M:%S')}] 📋 关卡列表 → 点选择(540,1750)进入单关选择")
                    tap((540, 1750))
                    time.sleep(1.5)
                    unknown_cnt = 0

                elif is_level_select(img):
                    # 单关选择界面：点开始游戏，打开开关，进入游戏循环
                    status = "关卡选择"
                    in_battle_loop = True  # 打开开关，进入游戏循环
                    print(f"[{time.strftime('%H:%M:%S')}] ▶ 关卡选择 → 点开始游戏(540,1594)，进入游戏循环")
                    tap(START_BTN)
                    just_started = True
                    just_start_time = time.time()
                    print(f"    → 进入战斗加载阶段，3秒内不触发未知界面兜底")
                    time.sleep(3)
                    unknown_cnt = 0

                elif is_reward_show(img):
                    status = "奖励展示"
                    print(f"[{time.strftime('%H:%M:%S')}] 🎉 恭喜获得奖励展示")
                    close_with_verify((540, 1750), is_reward_show, "奖励展示")
                    unknown_cnt = 0

                elif is_victory(img):
                    status = "通关"
                    level_cnt += 1
                    print(f"[{time.strftime('%H:%M:%S')}] 🏆 第 {level_cnt} 关通关！→ 点击返回")
                    do_victory()
                    if CLEAN_SCREENSHOT_PER_LEVEL:
                        clean_screenshots()
                        print(f"[{time.strftime('%H:%M:%S')}] 🧹 已清理本关截图")
                    unknown_cnt = 0

                elif is_battling(img):
                    # 非游戏循环中检测到战斗中，说明脚本启动时已经在战斗中，直接进入游戏循环
                    status = "战斗中"
                    in_battle_loop = True
                    print(f"[{time.strftime('%H:%M:%S')}] ⚔ 检测到战斗中，自动进入游戏循环")
                    unknown_cnt = 0

                else:
                    # 刚进入战斗加载阶段（3秒内），不触发未知界面兜底，给游戏加载时间
                    if just_started and (time.time() - just_start_time < 3):
                        status = "战斗加载中"
                        unknown_cnt = 0
                    else:
                        # 超过3秒或非刚进入战斗状态，正常处理未知界面
                        just_started = False
                        
                        # ===== 底部导航栏兜底：检测选中状态，不是战斗就点击战斗 =====
                        selected_nav = get_selected_bottom_nav()
                        if selected_nav and selected_nav != "战斗":
                            status = f"底部导航-{selected_nav}"
                            print(f"[{time.strftime('%H:%M:%S')}] 🧭 底部导航当前选中「{selected_nav}」，点击「战斗」切换到战斗界面")
                            if click_bottom_nav("战斗"):
                                time.sleep(1.5)
                            unknown_cnt = 0
                        elif selected_nav == "战斗":
                            # 已经在战斗页面，但界面未知，可能是加载中
                            status = "战斗页面-加载中"
                            unknown_cnt = 0
                        else:
                            # 未检测到底部导航栏，正常未知界面处理
                            unknown_cnt += 1
                            status = f"未知界面({unknown_cnt})"
                            if unknown_cnt >= 8:
                                print(f"[{time.strftime('%H:%M:%S')}] ⚠ 连续{unknown_cnt}次未知界面，兜底点左下角返回按钮")
                                fallback_back()
                                unknown_cnt = 0

            # 检测到已知界面（非战斗加载中/未知界面），退出刚进入战斗的保护状态
            if status not in ("战斗加载中",) and not status.startswith("未知界面"):
                just_started = False

            # 状态变化时打印（战斗中不刷屏）
            if status != last_status and status not in ("战斗中",):
                pass  # 上面已经打印过了
            last_status = status

            # 根据当前状态决定截图间隔：游戏循环中3秒一次（减轻OCR压力），非游戏循环0.8秒一次
            if in_battle_loop:
                time.sleep(3.0)
            else:
                time.sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:
        print("\n" + "=" * 55)
        print("  脚本已停止")
        print(f"  本次运行: 选技能 {skill_cnt} 次 | 通关 {level_cnt} 关 | 关弹窗 {popup_cnt} 次")
        print("=" * 55)

    except Exception as e:
        print(f"\n❌ 运行出错: {e}")
        import traceback; traceback.print_exc()

    finally:
        # 清理临时截图
        if os.path.exists(SCREENSHOT_LOCAL):
            try: os.remove(SCREENSHOT_LOCAL)
            except: pass

if __name__ == "__main__":
    main()
