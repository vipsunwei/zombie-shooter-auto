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
import re
import sys
import random
import numpy as np
from PIL import Image
from rapidocr_onnxruntime import RapidOCR
import importlib.util

# 从 version.py 导入版本号（专门文件，避免每次发版修改主脚本）
from version import __version__

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

# 游戏循环中每次检测间隔（秒）- 战力高词条弹出快可调小，战力低可调大减轻OCR压力
BATTLE_LOOP_INTERVAL = 3.0

# 非游戏循环中每次检测间隔（秒）
CHECK_INTERVAL = 0.8

# 每关通关后清理截图（模拟器内 + 本地临时文件）
CLEAN_SCREENSHOT_PER_LEVEL = True

# 波次区白色像素占比阈值（判定是否在战斗中）
# 实测数据：纯战斗 6.71%~9.38%，关卡选择(非战斗) 1.71%，弹窗遮挡 0%
# 取 3.5% 介于非战斗上限与战斗下限之间，上下各约2倍余量
WAVE_WHITE_THRESHOLD = 3.5

# ============================================================
#  词条优先级配置（从 skill_config.py 加载）
# ============================================================

# 全局变量：加载后的配置
_skill_config = None
_skill_config_mtime = None  # 配置文件最后修改时间（用于缓存判断）
_skill_config_exists = None  # 配置文件是否存在（缓存）
SKILL_PRIORITIES = {}

def load_skill_config():
    """加载词条优先级配置文件 skill_config.py（带缓存优化）
    - 配置文件不存在时降级使用随机选择（更像人在玩）
    - 通过文件最后修改时间判断是否需要重新加载，未修改时直接用缓存（<1ms）
    - 文件修改后自动重新加载，支持热更新
    """
    global _skill_config, _skill_config_mtime, _skill_config_exists
    global SKILL_PRIORITIES, SKILL_STRATEGY

    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skill_config.py")

    # 检查文件是否存在
    file_exists = os.path.exists(config_path)

    # 如果文件不存在，且之前也不存在，直接返回（避免重复检查）
    if not file_exists:
        if _skill_config_exists is False:
            return False
        # 文件之前存在，现在不存在了（被删除了），保留当前的 SKILL_STRATEGY
        _skill_config_exists = False
        _skill_config_mtime = None
        SKILL_PRIORITIES = {}
        # SKILL_STRATEGY 保留当前值（配置区的默认值），不强制改成 random
        return False

    # 文件存在，获取最后修改时间
    try:
        current_mtime = os.path.getmtime(config_path)
    except OSError:
        # 获取修改时间失败，保留当前的 SKILL_STRATEGY
        SKILL_PRIORITIES = {}
        # SKILL_STRATEGY 保留当前值（配置区的默认值），不强制改成 random
        return False

    # 如果文件没修改，且之前已经加载过，直接用缓存（<1ms）
    if _skill_config_exists is True and _skill_config_mtime == current_mtime and _skill_config is not None:
        return True

    # 文件修改了（或第一次加载），重新加载配置
    try:
        # 动态加载 Python 配置文件
        spec = importlib.util.spec_from_file_location("skill_config", config_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # 读取配置
        # 如果配置文件中有 strategy 就用配置文件的，否则保留当前的 SKILL_STRATEGY（配置区的默认值）
        if hasattr(module, "strategy"):
            SKILL_STRATEGY = module.strategy
        SKILL_PRIORITIES = getattr(module, "priorities", {})
        _skill_config = module
        _skill_config_mtime = current_mtime
        _skill_config_exists = True
        return True
    except Exception as e:
        print(f"⚠️  加载 skill_config.py 失败: {e}，保留当前配置")
        SKILL_PRIORITIES = {}
        # SKILL_STRATEGY 保留当前值（配置区的默认值），不强制改成 random
        _skill_config_mtime = current_mtime
        _skill_config_exists = True
        return False

# 启动时加载一次配置
load_skill_config()

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
_wave_miss_count = 0  # 连续未检测到波次的计数（用于判断是否已离开游戏界面）

# ============================================================
#  OCR 文字识别（EasyOCR）
# ============================================================

_ocr_reader = None  # OCR阅读器（懒加载，只初始化一次）
_current_ocr_result = None  # 当前循环的OCR结果缓存（多个检测函数共享）
_skill_ocr_result = None    # 词条名称区域裁剪后的OCR结果（加速用）

class RapidOCRWrapper:
    """RapidOCR包装类，接口兼容EasyOCR的readtext方法"""
    def __init__(self):
        print("正在初始化RapidOCR模型（首次运行需下载，请稍候）...")
        self.ocr = RapidOCR()
        print("✅ RapidOCR初始化完成")
    
    def readtext(self, img, detail=1):
        """兼容EasyOCR的readtext接口
        返回: [(bbox, text, confidence), ...]
        """
        result, elapse = self.ocr(img)
        if result is None:
            return []
        # 转换格式：RapidOCR返回[[box, text, confidence], ...]
        # EasyOCR返回[(bbox, text, confidence), ...]
        converted = []
        for item in result:
            if len(item) >= 3:
                box, text, confidence = item[0], item[1], item[2]
                # 转换box格式：list of list -> list of tuple
                bbox = [tuple(p) for p in box]
                converted.append((bbox, text, confidence))
        return converted

def get_ocr_reader():
    """获取OCR阅读器（懒加载，只初始化一次）"""
    global _ocr_reader
    if _ocr_reader is None:
        _ocr_reader = RapidOCRWrapper()
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

def ocr_battle_loop(img):
    """战斗循环中的四级按需OCR加速：
    - 第一级：识别区域1（y=400-750，选择技能+词条名称）
      - 如果检测到"选择技能"，只返回区域1结果（最快）
    - 第二级：识别区域2（x=430-650, y=1270-1400，精英掉落）
      - 如果检测到"精英掉落"，只返回区域2结果
    - 第三级：识别小区域（y=1650-1750，全屏宽度，检测"返回"按钮）
      - 如果没有"返回"，说明游戏还在进行中（战斗中），直接返回空结果，不检测区域3（节省时间）
      - 如果有"返回"，说明游戏结束了，继续检测区域3
    - 第四级：识别区域3（y=190-1750，通关结算，包含所有内容）
      - 返回区域3结果（通关结算）
    - 缓存结果到全局变量
    """
    global _skill_ocr_result
    _skill_ocr_result = None  # 清空词条区域裁剪OCR缓存，避免使用旧结果
    import time
    start_time = time.time()
    reader = get_ocr_reader()
    global _wave_miss_count  # 波次检测计数（在函数开头声明global）
    
    from PIL import Image
    if isinstance(img, Image.Image):
        img_pil = img
    else:
        img_pil = Image.fromarray(img)
    
    # ========== 第0级：波次检测（判断是否在战斗中） ==========
    # 波次显示在右上角，扩大区域确保覆盖到
    WAVE_X1, WAVE_X2 = 600, 1080
    WAVE_Y1, WAVE_Y2 = 0, 120
    region_wave = img_pil.crop((WAVE_X1, WAVE_Y1, WAVE_X2, WAVE_Y2))
    result_wave = reader.readtext(np.array(region_wave))
    # 调整坐标：加上裁剪的起始x和y
    adjusted_wave = []
    has_wave = False
    for item in result_wave:
        if len(item) >= 3:
            bbox, text, confidence = item[0], item[1], item[2]
            adjusted_bbox = [(p[0] + WAVE_X1, p[1] + WAVE_Y1) for p in bbox]
            adjusted_wave.append((adjusted_bbox, text, confidence))
            # 检测是否包含"波次"（降低置信度阈值到0.2）
            if confidence > 0.2 and "波次" in text:
                has_wave = True

    # 像素兜底：波次亮白时白色像素占比高（实测6.71%~9.38%），变灰/遮挡时为0%
    # 避免纯战斗帧因裁剪OCR漏检而 _wave_miss_count 误增（导致误跳出战斗循环）
    if not has_wave:
        ratio = wave_white_ratio(img)
        if ratio > WAVE_WHITE_THRESHOLD:
            has_wave = True
        else:
            # 波次变灰（弹窗遮挡）时裁剪OCR与像素都失效，整屏OCR兜底
            # 变灰帧整屏OCR能稳定识别"波次"(实测conf0.95~0.99)
            result_full = reader.readtext(np.array(img_pil))
            for item in result_full:
                if len(item) >= 3 and item[2] > 0.2 and "波次" in item[1]:
                    has_wave = True
                    break
    
    # ========== 第一级：区域1（选择技能+词条名称） ==========
    REGION1_Y1, REGION1_Y2 = 400, 750  # 350px高
    region1 = img_pil.crop((0, REGION1_Y1, 1080, REGION1_Y2))
    result1 = reader.readtext(np.array(region1))
    # 调整y坐标：加上裁剪的起始y
    adjusted1 = []
    has_select_skill = False
    for item in result1:
        if len(item) >= 3:
            bbox, text, confidence = item[0], item[1], item[2]
            adjusted_bbox = [(p[0], p[1] + REGION1_Y1) for p in bbox]
            adjusted1.append((adjusted_bbox, text, confidence))
            # 检测是否包含"选择技能"（置信度>0.5）
            if confidence > 0.5 and "选择技能" in text:
                has_select_skill = True
    
    # 第一级命中：检测到"选择技能"，返回波次+区域1结果
    if has_select_skill:
        result1 = adjusted1
        set_current_ocr_result(result1)
        _wave_miss_count = 0  # 选择技能界面，重置波次计数
        elapsed = time.time() - start_time
        print(f"    ⚡ 三级OCR[1/3] 选择技能: {elapsed:.1f}s")
        return result1
    
    # ========== 第二级：区域2（精英掉落） ==========
    # 区域2范围已确认：x=430-650, y=1270-1400（220x130px，仅2万像素）
    REGION2_X1, REGION2_X2 = 430, 650  # 宽度220px
    REGION2_Y1, REGION2_Y2 = 1270, 1400  # 高度130px
    region2 = img_pil.crop((REGION2_X1, REGION2_Y1, REGION2_X2, REGION2_Y2))
    result2 = reader.readtext(np.array(region2))
    # 调整坐标：加上裁剪的起始x和y
    adjusted2 = []
    has_elite_drop = False
    for item in result2:
        if len(item) >= 3:
            bbox, text, confidence = item[0], item[1], item[2]
            adjusted_bbox = [(p[0] + REGION2_X1, p[1] + REGION2_Y1) for p in bbox]
            adjusted2.append((adjusted_bbox, text, confidence))
            # 检测是否包含"精英掉落"（置信度>0.3，因为区域小，适当降低阈值）
            if confidence > 0.3 and "精英掉落" in text:
                has_elite_drop = True
    
    # 第二级命中：检测到"精英掉落"，返回波次+区域2结果
    if has_elite_drop:
        result2 = adjusted2
        set_current_ocr_result(result2)
        _wave_miss_count = 0  # 精英掉落界面，重置波次计数
        elapsed = time.time() - start_time
        print(f"    ⚡ 三级OCR[2/3] 精英掉落: {elapsed:.1f}s")
        return result2
    
    # ========== 第三级：小区域检测返回按钮（判断游戏是否结束） ==========
    # 小区域：x=100-980, y=1650-1750（880x100=8.8万像素，OCR很快）
    REGION_CHECK_X1, REGION_CHECK_X2 = 100, 980
    REGION_CHECK_Y1, REGION_CHECK_Y2 = 1650, 1750
    region_check = img_pil.crop((REGION_CHECK_X1, REGION_CHECK_Y1, REGION_CHECK_X2, REGION_CHECK_Y2))
    result_check = reader.readtext(np.array(region_check))
    # 调整坐标：加上裁剪的起始x和y
    adjusted_check = []
    has_return_btn = False
    for item in result_check:
        if len(item) >= 3:
            bbox, text, confidence = item[0], item[1], item[2]
            adjusted_bbox = [(p[0] + REGION_CHECK_X1, p[1] + REGION_CHECK_Y1) for p in bbox]
            adjusted_check.append((adjusted_bbox, text, confidence))
            # 检测是否包含"返回"（置信度>0.3）
            if confidence > 0.3 and "返回" in text:
                has_return_btn = True
    
    # 第三级判断：没有"返回"按钮，说明游戏还在进行中（战斗中）
    if not has_return_btn:
        # 战斗中，只有这里才检查波次计数
        if has_wave:
            _wave_miss_count = 0  # 检测到波次，重置计数
        else:
            _wave_miss_count += 1  # 检测不到波次，计数+1
        # 战斗中，返回空结果，什么都不做
        set_current_ocr_result([])
        elapsed = time.time() - start_time
        print(f"    ⚡ 三级OCR[3/3] 战斗中: {elapsed:.1f}s（波次计数:{_wave_miss_count}）")
        return []
    
    # 有"返回"按钮，说明游戏结束了，继续检测区域3
    _wave_miss_count = 0  # 检测到返回按钮，重置波次计数
    print(f"    ⚡ 三级OCR[2/3] 检测到返回按钮，继续检测结算区域...")
    
    # ========== 第四级：区域3（通关结算，包含所有内容） ==========
    REGION3_Y1, REGION3_Y2 = 190, 1750  # 1560px高
    region3 = img_pil.crop((0, REGION3_Y1, 1080, REGION3_Y2))
    result3 = reader.readtext(np.array(region3))
    # 调整y坐标：加上裁剪的起始y
    adjusted3 = []
    for item in result3:
        if len(item) >= 3:
            bbox, text, confidence = item[0], item[1], item[2]
            adjusted_bbox = [(p[0], p[1] + REGION3_Y1) for p in bbox]
            adjusted3.append((adjusted_bbox, text, confidence))
    
    # 第四级：返回波次+区域3结果（通关结算）
    result3 = adjusted3
    set_current_ocr_result(result3)
    elapsed = time.time() - start_time
    print(f"    ⚡ 三级OCR[3/3] 通关结算: {elapsed:.1f}s（{len(result3)}字）")
    
    return result3

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
            is_elite_drop(img) or is_reward_popup(img)):
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

def get_text_position(keyword, region=None, min_confidence=0.3):
    """从当前OCR结果中获取指定关键词的位置
    - keyword: 关键词（支持部分匹配）
    - region: 可选，指定检测区域 (x1,y1,x2,y2)，基准1080×1920
    - min_confidence: 最低置信度
    返回: (x, y) 中心坐标，未找到返回 None
    """
    result = _current_ocr_result
    if result is None:
        return None
    for item in result:
        if len(item) < 3:
            continue
        box, text, confidence = item
        if confidence < min_confidence:
            continue
        if keyword in text:
            if region:
                x1, y1, x2, y2 = region
                center_x = sum(p[0] for p in box) / 4
                center_y = sum(p[1] for p in box) / 4
                if not (x1 <= center_x <= x2 and y1 <= center_y <= y2):
                    continue
            center_x = int(sum(p[0] for p in box) / 4)
            center_y = int(sum(p[1] for p in box) / 4)
            return (center_x, center_y)
    return None


def is_perfect_clear(img=None):
    """检测界面上半部分是否有"完美通关"文字
    完美通关文字在关卡标题下方，大约y=330-420区域
    """
    return has_text("完美通关", region=(300, 320, 800, 430), min_confidence=0.3)


def click_next_level():
    """点击右箭头，跳到下一关
    右箭头位置大约在 (860, 812)
    """
    tap((860, 812))
    time.sleep(1.5)
    print(f"    → 点击右箭头，跳到下一关")


def click_prev_level():
    """点击左箭头，回到上一关
    左箭头位置大约在 (185, 780)
    """
    tap((185, 780))
    time.sleep(1.5)
    print(f"    → 点击左箭头，回到上一关")


def is_unclaimed_reward(img=None):
    """检测界面上是否有"未领取"按钮
    注意：OCR可能把"未"识别成"末"，需要同时检测两种情况
    """
    # 检测"未领取"或"末领取"
    if has_text("未领取", region=(0, 1300, 200, 1500), min_confidence=0.3):
        return True
    if has_text("末领取", region=(0, 1300, 200, 1500), min_confidence=0.3):
        return True
    return False


def claim_unclaimed_reward():
    """点击"未领取"按钮领取奖励
    返回: True=点击成功, False=未找到按钮
    """
    # 先找"未领取"，再找"末领取"
    pos = get_text_position("未领取", region=(0, 1300, 200, 1500), min_confidence=0.3)
    if pos is None:
        pos = get_text_position("末领取", region=(0, 1300, 200, 1500), min_confidence=0.3)
    if pos is None:
        return False
    # 点击文字位置（稍微往上一点点击宝箱图标）
    tap_x = pos[0]
    tap_y = pos[1] - 60
    print(f"    → 点击'未领取'按钮 ({tap_x}, {tap_y})")
    tap((tap_x, tap_y))
    time.sleep(2)
    return True


def is_reward_popup(img=None):
    """检测是否是奖励展示界面（"恭喜获得"）"""
    return has_text("恭喜获得", region=(300, 500, 800, 700), min_confidence=0.3)


def close_reward_popup():
    """关闭奖励界面（点击左下角）"""
    # 点击左下角空白处关闭奖励界面
    tap((100, 1750))
    time.sleep(1)
    print(f"    → 点击左下角关闭奖励界面")


def is_claimable_chest(chest_name):
    """检测指定宝箱是否可领取（通过文字位置判断）
    chest_name: "成功通关" / "50%血量通关" / "完美通关"
    返回: (x, y) 宝箱位置，未找到返回 None
    """
    # 扩大识别区域，降低置信度阈值，提高识别率
    pos = get_text_position(chest_name, region=(50, 1300, 1050, 1550), min_confidence=0.2)
    if pos is None:
        return None
    # 宝箱图标在文字上方约80像素
    return (pos[0], pos[1] - 80)


def claim_chest_reward(chest_name):
    """点击指定宝箱领取奖励
    chest_name: "成功通关" / "50%血量通关" / "完美通关"
    返回: True=点击成功, False=未找到宝箱
    """
    pos = is_claimable_chest(chest_name)
    if pos is None:
        return False
    print(f"    → 点击'{chest_name}'宝箱 ({pos[0]}, {pos[1]})")
    tap(pos)
    time.sleep(2)
    return True


def is_level_select(img):
    """单关选择界面：检测"开始游戏"文字（位置在屏幕中下方）
    注意："开始游戏"字体较艺术化，OCR置信度偏低，降低阈值到0.1
    """
    return has_text("开始游戏", region=(300, 1480, 780, 1680), min_confidence=0.1)

# 宝箱配置（1080x1920分辨率）
CHEST_REGIONS = {
    "成功通关": (130, 320, 1230, 1420),
    "50%血量通关": (410, 600, 1230, 1420),
    "完美通关": (690, 880, 1230, 1420),
}
CHEST_CLICK_POSITIONS = {
    "成功通关": (225, 1325),
    "50%血量通关": (505, 1325),
    "完美通关": (785, 1325),
}

def is_chest_glowing(img, chest_name):
    """检测指定宝箱是否发光（未领取）
    通过检测宝箱区域的金黄色像素比例判断
    chest_name: "成功通关" / "50%血量通关" / "完美通关"
    返回: True=发光(未领取), False=不发光(已领取)
    """
    if img is None or chest_name not in CHEST_REGIONS:
        return False
    
    import numpy as np
    from PIL import Image as PILImage
    
    x1, x2, y1, y2 = CHEST_REGIONS[chest_name]
    
    # 裁剪宝箱区域
    if isinstance(img, PILImage.Image):
        cropped = img.crop((x1, y1, x2, y2))
    else:
        cropped = img[y1:y2, x1:x2, :]
        cropped = PILImage.fromarray(cropped)
    
    # 转换为numpy数组
    img_np = np.array(cropped)
    
    # 检测金黄色像素: R>180, G>130, B<100
    if img_np.shape[2] == 4:
        # RGBA格式，只取RGB
        gold_mask = (img_np[:, :, 0] > 180) & (img_np[:, :, 1] > 130) & (img_np[:, :, 2] < 100)
    else:
        gold_mask = (img_np[:, :, 0] > 180) & (img_np[:, :, 1] > 130) & (img_np[:, :, 2] < 100)
    
    gold_count = np.sum(gold_mask)
    total = img_np.shape[0] * img_np.shape[1]
    ratio = gold_count / total * 100
    
    # 金黄色像素比例>15%认为发光（未领取），开口宝箱内部金黄色不算
    return ratio > 15

def get_glowing_chests(img):
    """获取所有发光（未领取）的宝箱列表
    返回: 发光宝箱名称列表，按从左到右排序
    """
    glowing = []
    for chest_name in ["成功通关", "50%血量通关", "完美通关"]:
        if is_chest_glowing(img, chest_name):
            glowing.append(chest_name)
    return glowing

def claim_all_chests(img):
    """一键领取所有未领取的通关宝箱
    点击最右边的发光宝箱，就可以一键领取所有未领取的宝箱
    - 1个发光宝箱 → 点第一个（成功通关）
    - 2个发光宝箱 → 点中间那个（50%血量通关）
    - 3个发光宝箱 → 点最后一个（完美通关）
    返回: True=点击了宝箱, False=没有发光的宝箱
    """
    glowing = get_glowing_chests(img)
    if not glowing:
        print(f"    → 没有发光的宝箱，无需领取")
        return False
    
    # 点击最右边的发光宝箱（glowing按从左到右排序，[-1]就是最右边的）
    # - 1个发光宝箱 → glowing[0]（第一个）
    # - 2个发光宝箱 → glowing[1]（中间那个）
    # - 3个发光宝箱 → glowing[2]（最后一个）
    target_chest = glowing[-1]
    click_pos = CHEST_CLICK_POSITIONS[target_chest]
    actual_pos = scale(click_pos)
    print(f"    🎁 检测到{len(glowing)}个发光宝箱: {glowing}")
    print(f"    → 点击[{target_chest}] 原始坐标{click_pos} → 实际点击坐标{actual_pos}（分辨率{screen_w}×{screen_h}）")
    tap(click_pos)
    time.sleep(1.5)
    
    # 等待奖励展示界面出现并关闭（最多等5秒）
    for wait_idx in range(5):
        img_reward = screenshot()
        if img_reward is not None and is_reward_popup(img_reward):
            print(f"    → 检测到奖励展示界面，点击关闭（第{wait_idx+1}次）")
            close_with_verify((540, 1750), is_reward_popup, "奖励展示")
            break
        time.sleep(0.5)
    else:
        print(f"    → 未检测到奖励展示界面，继续")
    
    return True

def is_level_list(img):
    """关卡列表界面：检测"关卡选择"标题 + 底部"选择"按钮"""
    has_title = has_text("关卡选择", region=(50, 50, 350, 160))
    has_select_btn = has_text("选择", region=(300, 1650, 780, 1880))
    return has_title and has_select_btn

def is_battling(img):
    """战斗中界面：双判据（波次区白色像素占比 或 OCR命中"波次"）
    - 像素判据：波次亮白时占比高(>3.5%)，零OCR开销，覆盖绝大多数战斗帧
    - OCR兜底：波次被弹窗遮挡变灰时像素为0，靠整屏OCR缓存识别"波次"字样
    """
    ratio = wave_white_ratio(img)
    if ratio > WAVE_WHITE_THRESHOLD:
        return True
    return has_text("波次", region=(600, 0, 1080, 120))

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

def is_level_detail_popup(img):
    """关卡详情弹窗：检测"本关怪物"或"本关掉落"文字
    这是点击关卡名称后弹出的详情界面，显示本关怪物和掉落奖励，需要点击右上角×关闭
    """
    # 检测"本关怪物"文字（弹窗中间）
    if has_text("本关怪物", region=(300, 400, 780, 550), min_confidence=0.5):
        return True
    # 检测"本关掉落"文字（弹窗中间）
    if has_text("本关掉落", region=(300, 750, 780, 900), min_confidence=0.5):
        return True
    return False

def close_level_detail_popup():
    """关闭关卡详情弹窗：点击右上角×按钮
    验证式关闭：点一次截一次图，确认关闭就停，最多重试2次
    返回: True=已关闭, False=多次尝试未关闭
    """
    # 右上角×按钮位置（已验证：890, 238）
    close_pos = (890, 238)
    
    for attempt in range(1, 3):
        print(f"    → 第{attempt}次点击右上角×关闭关卡详情弹窗 {close_pos}")
        tap(close_pos)
        time.sleep(1)
        img = screenshot()
        if img is None:
            continue
        ocr_screenshot(img)  # 更新OCR缓存
        if not is_level_detail_popup(img):
            print(f"    ✅ 关卡详情弹窗已关闭，停止操作")
            return True
        print(f"    ⚠ 弹窗仍在，准备重试")
    
    print(f"    ❌ 关卡详情弹窗多次尝试未关闭，跳过（下轮循环再处理）")
    return False

def has_click_blank_hint(img):
    """检测界面上是否有"点击空白处关闭"提示（通用关闭提示）
    返回: True=有此提示, False=没有
    """
    return has_text("点击空白处关闭", region=(300, 1750, 780, 1900), min_confidence=0.3)

def click_blank_to_close():
    """通用关闭函数：点击弹窗外的空白区域关闭弹窗（巡逻车/扫荡等带"点击空白处关闭"提示的界面通用）
    注意：点击的是弹窗外空白区域（实测 (540,1720) 可靠），不是"点击空白处关闭"文字本身的位置
    验证式关闭：点一次截一次图，确认关闭就停，最多重试2次
    返回: True=已关闭, False=多次尝试未关闭
    """
    # 巡逻车/扫荡弹窗的可靠关闭点（实测 (850,1594) 点不关，(540,1720) 能关）
    blank_pos = (540, 1720)
    
    for attempt in range(1, 3):
        print(f"    → 第{attempt}次点击开始按钮右侧空白区域 {blank_pos}")
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

def ocr_skill_region(img):
    """对词条名称区域（y=610-760）进行裁剪并快速OCR
    - 裁剪后图片尺寸：1080×150，只有原图的7.8%
    - OCR速度预计从5秒降到1秒以内
    - 结果存到全局变量 _skill_ocr_result
    """
    global _skill_ocr_result
    if img is None:
        _skill_ocr_result = None
        return None
    
    import time
    start_time = time.time()
    
    # 裁剪词条名称区域（y=610-760，包含一些余量）
    from PIL import Image
    if isinstance(img, Image.Image):
        cropped = img.crop((0, 610, 1080, 760))
    else:
        # numpy数组
        cropped = img[610:760, :, :]
        cropped = Image.fromarray(cropped)
    
    # 对裁剪后的小图进行OCR
    import numpy as np
    cropped_np = np.array(cropped)
    ocr_reader = get_ocr_reader()
    result = ocr_reader.readtext(cropped_np, detail=1)
    
    # 调整坐标：裁剪后的y坐标需要加上580才是原图坐标
    adjusted_result = []
    for item in result:
        if len(item) >= 3:
            bbox, text, confidence = item[0], item[1], item[2]
            adjusted_bbox = [(p[0], p[1] + 610) for p in bbox]
            adjusted_result.append((adjusted_bbox, text, confidence))
    
    _skill_ocr_result = adjusted_result
    elapsed = time.time() - start_time
    print(f"    ⚡ 词条区域裁剪OCR: {elapsed:.1f}s（{len(adjusted_result)}字）")
    return adjusted_result


def get_skill_names_from_ocr(debug=False):
    """从当前OCR结果中识别三个技能卡片的词条名称
    - 直接使用整张图OCR结果，按实际y坐标范围（640-760）过滤词条名称
    - 词条名称实际位置：y≈693（卡片顶部白色字），描述在y≈1040
    - 根据x坐标分配到三个卡片，取置信度最高的文字
    - 兜底：如果某个卡片没识别到，扩大范围到600-800再试一次
    返回: (left_name, middle_name, right_name)，识别失败返回空字符串
    """
    # 优先使用词条区域裁剪后的OCR结果（加速），如果没有则用整张图OCR结果
    ocr_result = _skill_ocr_result if _skill_ocr_result else _current_ocr_result
    if not ocr_result:
        if debug:
            print(f"    ⚠️  OCR结果为空")
        return "", "", ""
    if debug and _skill_ocr_result:
        print(f"    ⚡ 使用词条区域裁剪OCR结果（加速）")

    # 三个卡片的 x 坐标分界（基准1080×1920）
    # 左卡片: x < 360，中卡片: 360 <= x < 720，右卡片: x >= 720
    left_texts = []
    middle_texts = []
    right_texts = []

    # 调试：显示y=600-800范围内的所有文字
    if debug:
        print(f"    📊 词条名称区域（y=600-800）的OCR结果:")

    for item in ocr_result:
        if len(item) < 3:
            continue
        bbox, text, confidence = item[0], item[1], item[2]

        center_x = sum(p[0] for p in bbox) / 4
        center_y = sum(p[1] for p in bbox) / 4

        # 词条名称在y=620-780范围内（实际位置y≈693，卡片顶部白色字，可能有波动）
        if center_y < 620 or center_y > 780:
            continue

        # 过滤长度合适的文字（2-20个字）
        text_len = len(text.strip())
        if text_len > 20 or text_len < 2:
            continue

        if debug:
            print(f"       [{text}]({int(center_x)},{int(center_y)}) conf={confidence:.2f}")

        # 根据x坐标分配到对应卡片
        if center_x < 360:
            left_texts.append((text, confidence))
        elif center_x < 720:
            middle_texts.append((text, confidence))
        else:
            right_texts.append((text, confidence))

    # 取每个卡片置信度最高的文字作为词条名称
    def get_best_text(texts):
        if not texts:
            return ""
        # 最低置信度阈值：低于0.3的认为是乱码，过滤掉
        MIN_CONFIDENCE = 0.2
        # 文字质量判断：只过滤明显的乱码字符，不过滤反引号和书名号（OCR经常把正常字符识别成这些）
        def is_valid_text(text):
            text = text.strip()
            if len(text) < 2 or len(text) > 15:
                return False
            # 只过滤明显的乱码字符，不过滤+和=号（很多词条名称包含+号，如火焰子弹+）
            if re.search(r'[@#$%^&*~|<>]', text):
                return False
            # 不能是纯数字或纯符号
            if re.match(r'^[0-9\W_]+$', text):
                return False
            # 正常词条名称应该包含中文字符
            if not re.search(r'[\u4e00-\u9fff]', text):
                return False
            return True
        # 智能修正：OCR经常把"弹球"识别成反引号"`"，替换成"弹球"
        def fix_text(text):
            text = text.strip()
            # 反引号通常是"弹球"的误识别
            if '`' in text:
                text = text.replace('`', '弹球')
            # 书名号《》通常是正常字符的误识别，去掉
            text = text.replace('《', '').replace('》', '')
            return text.strip()
        # 过滤掉低置信度和质量差的文字
        valid_texts = [(fix_text(t), c) for t, c in texts if c >= MIN_CONFIDENCE and is_valid_text(t)]
        if not valid_texts:
            return ""
        # 按置信度排序，取最高的
        texts_sorted = sorted(valid_texts, key=lambda x: x[1], reverse=True)
        return texts_sorted[0][0].strip()

    left_name = get_best_text(left_texts)
    middle_name = get_best_text(middle_texts)
    right_name = get_best_text(right_texts)

    # 兜底：如果某个卡片没识别到，扩大范围到600-800再试一次
    if not left_name or not middle_name or not right_name:
        if debug:
            print(f"    ⚠️  部分卡片未识别到，扩大范围到600-800重试...")
        fallback_left = []
        fallback_middle = []
        fallback_right = []
        for item in ocr_result:
            if len(item) < 3:
                continue
            bbox, text, confidence = item[0], item[1], item[2]
            center_x = sum(p[0] for p in bbox) / 4
            center_y = sum(p[1] for p in bbox) / 4
            # 扩大范围到580-820
            if center_y < 580 or center_y > 820:
                continue
            text_len = len(text.strip())
            if text_len > 25 or text_len < 2:
                continue
            if debug:
                print(f"       [兜底] [{text}]({int(center_x)},{int(center_y)}) conf={confidence:.2f}")
            if center_x < 360:
                fallback_left.append((text, confidence))
            elif center_x < 720:
                fallback_middle.append((text, confidence))
            else:
                fallback_right.append((text, confidence))
        # 只补充没识别到的卡片
        if not left_name and fallback_left:
            left_name = get_best_text(fallback_left)
            if debug:
                print(f"    ✅ 兜底识别左卡片: [{left_name}]")
        if not middle_name and fallback_middle:
            middle_name = get_best_text(fallback_middle)
            if debug:
                print(f"    ✅ 兜底识别中卡片: [{middle_name}]")
        if not right_name and fallback_right:
            right_name = get_best_text(fallback_right)
            if debug:
                print(f"    ✅ 兜底识别右卡片: [{right_name}]")

    # 如果有任意一个卡片没识别到，打印所有OCR结果（不限制y范围）帮助调试
    if (not left_name or not middle_name or not right_name) and debug:
        missing = []
        if not left_name: missing.append("左")
        if not middle_name: missing.append("中")
        if not right_name: missing.append("右")
        print(f"    ❌ {('/'.join(missing))}卡片未识别到，打印所有OCR结果（共{len(ocr_result)}条）:")
        for item in ocr_result:
            if len(item) < 3:
                continue
            bbox, text, confidence = item[0], item[1], item[2]
            center_x = int(sum(p[0] for p in bbox) / 4)
            center_y = int(sum(p[1] for p in bbox) / 4)
            # 标记y=580-820范围内的文字（可能是词条名称）
            marker = " ⭐" if 580 <= center_y <= 820 else ""
            print(f"       [{text}]({center_x},{center_y}) conf={confidence:.2f}{marker}")

    if debug:
        print(f"    ✅ 最终识别: 左[{left_name}] 中[{middle_name}] 右[{right_name}]")

    return left_name, middle_name, right_name


def get_skill_priority(skill_name):
    """获取词条的优先级分数
    - 支持部分匹配：配置"暴击"会匹配"暴击率"、"暴击伤害"等
    - 未配置的词条返回 None（表示随机选择）
    """
    if not skill_name:
        return None

    # 精确匹配
    if skill_name in SKILL_PRIORITIES:
        return SKILL_PRIORITIES[skill_name]

    # 部分匹配：配置的关键词出现在词条名称中
    best_priority = None
    for keyword, priority in SKILL_PRIORITIES.items():
        if keyword in skill_name:
            if best_priority is None or priority > best_priority:
                best_priority = priority

    return best_priority


def do_select_skill():
    """按策略选技能卡片
    - priority: 按优先级选择（已配置的选最优，未配置的随机选）
    - middle/left/right/random: 按原策略选择
    """
    # 每次选择前重新加载配置，支持热更新
    load_skill_config()

    if SKILL_STRATEGY != "priority":
        # 非优先级策略，按原逻辑选择
        if SKILL_STRATEGY == "left":
            tap(CARD_LEFT)
            return "left", CARD_LEFT, "", "", "", "策略固定选左边"
        elif SKILL_STRATEGY == "right":
            tap(CARD_RIGHT)
            return "right", CARD_RIGHT, "", "", "", "策略固定选右边"
        elif SKILL_STRATEGY == "random":
            pos = random.choice([CARD_LEFT, CARD_MIDDLE, CARD_RIGHT])
            tap(pos)
            return "random", pos, "", "", "", "策略随机选择"
        else:
            tap(CARD_MIDDLE)
            return "middle", CARD_MIDDLE, "", "", "", "策略固定选中间"

    # 优先级策略：OCR识别三个词条名称
    # 逻辑：先确保截图正常（有3个词条），再做裁剪兜底
    # 1. 第一次识别，如果不全 → 直接重新截图（不要浪费时间裁剪）
    # 2. 重新截图后还是不全 → 裁剪OCR兜底
    # 3. 还是不全 → 用已识别的结果继续（或随机）

    # 第1次：用当前OCR结果识别
    left_name, middle_name, right_name = get_skill_names_from_ocr(debug=False)
    failed_count = sum(1 for n in [left_name, middle_name, right_name] if not n)

    # 如果识别到的词条数量 < 3，直接重新截图（确保截图正常，不要裁剪）
    if failed_count > 0:
        print(f"    ⚠️  只识别到{3-failed_count}/3个词条，重新截图确保截图正常...")
        retry_img = screenshot()
        if retry_img is not None:
            # 战斗循环中用分区域OCR，非战斗循环用整张图OCR
            global in_battle_loop
            if in_battle_loop:
                ocr_battle_loop(retry_img)
            else:
                ocr_screenshot(retry_img)
            left_name, middle_name, right_name = get_skill_names_from_ocr(debug=False)
            failed_count = sum(1 for n in [left_name, middle_name, right_name] if not n)
            if failed_count == 0:
                print(f"    ✅ 重新截图后识别成功")
            else:
                print(f"    ⚠️  重新截图后仍有{failed_count}个词条未识别，尝试裁剪OCR兜底...")
        else:
            print(f"    ⚠️  无法获取截图，跳过重新截图")

    # 如果重新截图后还是识别不全，裁剪OCR兜底（只在失败时才慢）
    if failed_count > 0:
        print(f"    ⚠️  词条识别不全（{3-failed_count}/3），尝试裁剪OCR兜底...")
        current_img = screenshot()
        if current_img is not None:
            ocr_skill_region(current_img)
            left_name, middle_name, right_name = get_skill_names_from_ocr(debug=False)
            failed_count = sum(1 for n in [left_name, middle_name, right_name] if not n)
            if failed_count == 0:
                print(f"    ✅ 裁剪OCR后识别成功")
            else:
                print(f"    ⚠️  裁剪OCR后仍有{failed_count}个词条未识别，使用已识别的结果继续")
        else:
            print(f"    ⚠️  无法获取截图，跳过裁剪OCR兜底")

    # 计算每个词条的优先级
    left_priority = get_skill_priority(left_name)
    middle_priority = get_skill_priority(middle_name)
    right_priority = get_skill_priority(right_name)

    # 收集已配置的词条（有优先级分数）
    configured = []
    if left_priority is not None:
        configured.append(("left", CARD_LEFT, left_name, left_priority))
    if middle_priority is not None:
        configured.append(("middle", CARD_MIDDLE, middle_name, middle_priority))
    if right_priority is not None:
        configured.append(("right", CARD_RIGHT, right_name, right_priority))

    if configured:
        # 有已配置的词条，选优先级最高的
        configured.sort(key=lambda x: x[3], reverse=True)
        # 同分随机：筛选出所有最高分的词条，在其中随机选一个（更像人在玩）
        max_score = configured[0][3]
        top_candidates = [c for c in configured if c[3] == max_score]
        best = random.choice(top_candidates)
        tap(best[1])
        if len(top_candidates) > 1:
            reason = f"优先级最高({best[3]}分，{len(top_candidates)}个同分随机)，词条[{best[2]}]"
        else:
            reason = f"优先级最高({best[3]}分)，词条[{best[2]}]"
        return best[0], best[1], left_name, middle_name, right_name, reason, best[2], best[3]
    else:
        # 都没有配置，随机选择（更像人在玩）
        positions = [
            ("left", CARD_LEFT, left_name),
            ("middle", CARD_MIDDLE, middle_name),
            ("right", CARD_RIGHT, right_name),
        ]
        # 过滤掉识别失败的（空名称），如果都识别失败则全部随机
        valid_positions = [p for p in positions if p[2]]
        if not valid_positions:
            valid_positions = positions

        chosen = random.choice(valid_positions)
        tap(chosen[1])
        if left_name or middle_name or right_name:
            reason = "词条均未配置，随机选择"
        else:
            reason = "OCR未识别到词条，回退随机选择"
        return chosen[0], chosen[1], left_name, middle_name, right_name, reason, chosen[2], 0

def do_victory():
    """通关流程：先领取完美通关宝箱奖励，再判断是否需要点击双倍奖励，然后点击返回
    1. 在下半部分找"完美通关"宝箱，点击领取奖励
    2. 完美通关 + 有双倍奖励按钮 + 剩余次数>0 → 先点双倍奖励，再点返回
    3. 其他情况（非完美/次数用完/无按钮）→ 直接点返回
    """
    # 1. 在下半部分（y=1350-1500）OCR识别"完美通关"文字，点击宝箱领取奖励
    print(f"    → 在下半部分检测完美通关宝箱...")
    perfect_pos = is_claimable_chest("完美通关")
    if perfect_pos:
        print(f"    → 识别到完美通关文字，宝箱位置 {perfect_pos}，点击领取")
        tap(perfect_pos)
        time.sleep(2)
        # 领取后可能弹出奖励界面，关闭它
        img = screenshot()
        if img is not None:
            ocr_screenshot(img)
            if is_reward_popup(img):
                print(f"    → 检测到奖励展示界面 → 关闭")
                close_reward_popup()
            else:
                print(f"    → 未弹出奖励界面（可能已领取）")
    else:
        print(f"    → 未在下半部分识别到完美通关文字（可能已领取或OCR未识别）")
    
    # 2. 先判断是否需要点击双倍奖励
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
        # 检查是否直接弹出了选择技能界面，如果是，直接选择词条（不用等下一次循环）
        if is_skill_select(img):
            print(f"    ✅ 精英掉落已关闭，检测到选择技能界面，直接选择词条")
            # 注意：不在这里做裁剪OCR，直接用整张图OCR结果
            # 只有当整张图OCR没识别到词条时，do_select_skill内部才会做裁剪OCR兜底
            pos_name, pos_coord, left_name, middle_name, right_name, reason = do_select_skill()
            if left_name or middle_name or right_name:
                print(f"    → 左[{left_name}] 中[{middle_name}] 右[{right_name}]")
            print(f"    → 已选择{pos_name}卡片{pos_coord}，原因：{reason}")
        else:
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

def is_auto_close_popup(img):
    """检测已激活技能弹窗（底部有"秒后自动关闭"文字）
    这是进入游戏后出现的技能提示弹窗，点击左下角可以直接关闭，不用等倒计时结束
    注意：这个函数自己独立做OCR识别，不依赖全局OCR结果（因为三级按需识别的区域3不包含这个区域）
    """
    if img is None:
        return False
    
    import time
    start_time = time.time()
    
    # 裁剪底部小区域（x=360-720, y=1735-1840），只有360x105=37800像素，OCR速度很快
    from PIL import Image as PILImage
    import numpy as np
    
    if isinstance(img, PILImage.Image):
        cropped = img.crop((360, 1735, 720, 1840))
    else:
        cropped = img[1735:1840, 360:720, :]
        cropped = PILImage.fromarray(cropped)
    
    # 对裁剪后的小图进行OCR识别
    cropped_np = np.array(cropped)
    ocr_reader = get_ocr_reader()
    result = ocr_reader.readtext(cropped_np, detail=1)
    
    elapsed = time.time() - start_time
    
    # 检查是否识别到"秒后自动关闭"文字（数字会变化，如"6秒后自动关闭"）
    for item in result:
        if len(item) >= 3:
            bbox, text, confidence = item[0], item[1], item[2]
            if "秒后自动关闭" in text or "自动关闭" in text:
                if confidence >= 0.3:
                    print(f"    ⚡ 已激活技能弹窗独立OCR: {elapsed:.1f}s，识别到[{text}] conf={confidence:.2f}")
                    return True
    
    return False

def close_auto_close_popup():
    """关闭已激活技能弹窗：点击左下角直接关闭，不用等倒计时结束
    验证式关闭：点一次截一次图，确认关闭就停
    """
    tap_pos = (100, 1750)  # 左下角位置
    for attempt in range(1, 3):
        print(f"    → 第{attempt}次点击左下角关闭已激活技能弹窗 {tap_pos}")
        tap(tap_pos)
        time.sleep(1)
        img = screenshot()
        if img is None:
            continue
        ocr_screenshot(img)  # 更新OCR缓存
        if not is_auto_close_popup(img):
            print(f"    ✅ 已激活技能弹窗已关闭，停止操作")
            return True
        print(f"    ⚠ 弹窗仍在，准备重试")
    
    print(f"    ❌ 已激活技能弹窗多次尝试未关闭，跳过（下轮循环再处理）")
    return False

def is_reconnect_failed_popup(img):
    """检测"重连失败断开连接"提示弹窗
    网络断开时会弹出这个提示，需要点击"确定"按钮关闭
    """
    # 检测是否包含"重连失败"或"断开连接"文字
    return has_text("重连失败", min_confidence=0.3) or has_text("断开连接", min_confidence=0.3)

def is_in_game_interface(img):
    """判断是否还在游戏界面（战斗中、选择技能、精英掉落、结算都算游戏界面）
    检测右上角是否有"波次"文字，如果有说明在游戏界面
    用于防止用户手动点返回后脚本卡在游戏循环
    自己独立做小区域OCR，不依赖全局OCR结果
    """
    if img is None:
        return False
    
    from PIL import Image as PILImage
    import numpy as np
    
    # 裁剪右上角小区域（x=790-950, y=20-100），检测"波次"文字
    if isinstance(img, PILImage.Image):
        cropped = img.crop((790, 20, 950, 100))
    else:
        cropped = img[20:100, 790:950, :]
        cropped = PILImage.fromarray(cropped)
    
    # 对裁剪后的小图进行OCR识别
    cropped_np = np.array(cropped)
    ocr_reader = get_ocr_reader()
    result = ocr_reader.readtext(cropped_np, detail=1)
    
    # 检查是否识别到"波次"文字
    for item in result:
        if len(item) >= 3:
            bbox, text, confidence = item[0], item[1], item[2]
            if confidence >= 0.3 and "波次" in text:
                return True
    
    return False

def wave_white_ratio(img):
    """波次区白色像素占比(R>230,G>230,B>230)，用于判定是否在战斗中。
    实测：纯战斗 6.71%~9.38%，关卡选择(非战斗) 1.71%，弹窗遮挡 0%。
    返回: 白色像素占比百分比(0~100)；img为None或异常返回0.0
    """
    if img is None:
        return 0.0
    import numpy as np
    from PIL import Image as PILImage
    x1, x2, y1, y2 = 770, 990, 10, 100
    if isinstance(img, PILImage.Image):
        cropped = img.crop((x1, y1, x2, y2))
    else:
        cropped = img[y1:y2, x1:x2, :]
        cropped = PILImage.fromarray(cropped)
    img_np = np.array(cropped)
    if img_np.shape[2] == 4:
        img_rgb = img_np[:, :, :3]
    else:
        img_rgb = img_np
    white_mask = (img_rgb[:, :, 0] > 230) & (img_rgb[:, :, 1] > 230) & (img_rgb[:, :, 2] > 230)
    return np.sum(white_mask) / (img_rgb.shape[0] * img_rgb.shape[1]) * 100

def is_wave_bright(img):
    """检测波次文字是否为亮白色（游戏正常进行中）
    亮白色波次：白色像素(R>200,G>200,B>200)比例 > 3%
    灰色波次：有弹窗遮挡，白色像素比例为0%
    返回: True=亮白色(正常游戏), False=灰色(有弹窗)
    """
    if img is None:
        return False
    
    import numpy as np
    from PIL import Image as PILImage
    
    # 裁剪波次区域（x=790-950, y=20-100）
    x1, x2, y1, y2 = 790, 950, 20, 100
    if isinstance(img, PILImage.Image):
        cropped = img.crop((x1, y1, x2, y2))
    else:
        cropped = img[y1:y2, x1:x2, :]
        cropped = PILImage.fromarray(cropped)
    
    # 转换为numpy数组
    img_np = np.array(cropped)
    if img_np.shape[2] == 4:
        img_rgb = img_np[:, :, :3]
    else:
        img_rgb = img_np
    
    # 统计白色像素比例（R>200, G>200, B>200）
    white_mask = (img_rgb[:, :, 0] > 200) & (img_rgb[:, :, 1] > 200) & (img_rgb[:, :, 2] > 200)
    white_ratio = np.sum(white_mask) / (img_rgb.shape[0] * img_rgb.shape[1]) * 100
    
    # 白色像素比例 > 3% 认为是亮白色
    return white_ratio > 3

def get_wave_progress(img):
    """获取波次进度（如"7/20"），判断是否达到20/20
    返回: (current, total)，识别失败返回(None, None)
    """
    if img is None:
        return None, None
    
    import re
    from PIL import Image as PILImage
    import numpy as np
    
    # 裁剪波次区域
    x1, x2, y1, y2 = 790, 950, 20, 100
    if isinstance(img, PILImage.Image):
        cropped = img.crop((x1, y1, x2, y2))
    else:
        cropped = img[y1:y2, x1:x2, :]
        cropped = PILImage.fromarray(cropped)
    
    # OCR识别
    cropped_np = np.array(cropped)
    ocr_reader = get_ocr_reader()
    result = ocr_reader.readtext(cropped_np, detail=1)
    
    if result:
        for item in result:
            if len(item) >= 3:
                text = item[1]
                # 匹配 "数字/数字" 格式
                match = re.search(r'(\d+)\s*/\s*(\d+)', text)
                if match:
                    current = int(match.group(1))
                    total = int(match.group(2))
                    return current, total
    
    return None, None

def close_reconnect_failed_popup():
    """关闭"重连失败断开连接"弹窗：点击"确定"按钮
    验证式关闭：点一次截一次图，确认关闭就停
    """
    tap_pos = (540, 1200)  # "确定"按钮位置（估算，需测试确认）
    for attempt in range(1, 3):
        print(f"    → 第{attempt}次点击确定按钮关闭重连失败弹窗 {tap_pos}")
        tap(tap_pos)
        time.sleep(1)
        img = screenshot()
        if img is None:
            continue
        ocr_screenshot(img)  # 更新OCR缓存
        if not is_reconnect_failed_popup(img):
            print(f"    ✅ 重连失败弹窗已关闭，停止操作")
            return True
        print(f"    ⚠ 弹窗仍在，准备重试")
    
    print(f"    ❌ 重连失败弹窗多次尝试未关闭，跳过（下轮循环再处理）")
    return False

# ============================================================
#  主循环
# ============================================================

def main():
    global screen_w, screen_h, EMULATOR_TYPE, _wave_miss_count
    
    # 解析命令行参数（优先级高于配置区）
    EMULATOR_TYPE = parse_args()
    emulator_display = {"mumu": "MuMu", "ldplayer": "雷电", "auto": "自动检测"}.get(EMULATOR_TYPE, EMULATOR_TYPE)
    
    print("=" * 55)
    print(f"   向僵尸开炮 · 自动闯关脚本 v{__version__}")
    print("=" * 55)
    print(f"  模拟器: {emulator_display}（可用参数: mumu / leidian）")
    strategy_display = SKILL_STRATEGY
    if SKILL_STRATEGY == "priority":
        strategy_display = f"priority（已配置{len(SKILL_PRIORITIES)}个词条）"
    print(f"  策略 : 技能选 {strategy_display}")
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
            # 战斗循环中使用分区域OCR加速，非战斗循环用整张图OCR
            t1 = time.time()
            if in_battle_loop:
                ocr_result = ocr_battle_loop(img)
            else:
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
                #  【游戏循环中】判断状态，绝不误判其他界面
                #  0. 游戏界面检测 → 不在游戏界面则跳出循环（防止用户手动点返回）
                #  0.5 已激活技能弹窗 → 点左下角直接关闭（不用等倒计时）
                #  0.6 重连失败弹窗 → 点确定按钮关闭
                #  1. 通关结算 → 点返回，关闭开关（跳出循环）
                #  2. 选择技能 → 选中间卡片
                #  3. 精英掉落 → 点左下角停止转盘，再点左下角关闭
                #  4. 战斗中   → 什么都不做，等下一次截图
                # ============================================================

                # 0. 波次检测：连续3次检测不到波次，说明可能已经离开了战斗场面
                # （刚进入游戏的3秒内不检查，因为波次可能还没显示出来）
                if not just_started and _wave_miss_count >= 3:
                    status = "已离开游戏界面"
                    miss_cnt = _wave_miss_count
                    in_battle_loop = False
                    _wave_miss_count = 0
                    print(f"[{time.strftime('%H:%M:%S')}] 🔄 连续{miss_cnt}次未检测到波次，自动跳出游戏循环")
                    continue
                
                # 0.5 已激活技能弹窗：点左下角直接关闭，不用等倒计时结束
                if is_auto_close_popup(img):
                    status = "已激活技能弹窗"
                    print(f"[{time.strftime('%H:%M:%S')}] ⚡ 检测到已激活技能弹窗（秒后自动关闭）→ 点击左下角直接关闭")
                    close_auto_close_popup()
                    popup_cnt += 1
                    unknown_cnt = 0

                # 0.5 重连失败弹窗：点确定按钮关闭
                elif is_reconnect_failed_popup(img):
                    status = "重连失败弹窗"
                    print(f"[{time.strftime('%H:%M:%S')}] 🔌 检测到重连失败断开连接弹窗 → 点击确定按钮关闭")
                    close_reconnect_failed_popup()
                    popup_cnt += 1
                    unknown_cnt = 0

                # 1. 通关结算界面：跳出游戏循环，点返回
                elif is_victory_settlement(img):
                    status = "通关结算"
                    level_cnt += 1
                    in_battle_loop = False  # 关闭开关，跳出游戏循环
                    print(f"[{time.strftime('%H:%M:%S')}] 🏆 第 {level_cnt} 关通关！→ 点击返回，跳出游戏循环")
                    do_victory()
                    if CLEAN_SCREENSHOT_PER_LEVEL:
                        clean_screenshots()
                        print(f"[{time.strftime('%H:%M:%S')}] 🧹 已清理本关截图")
                    unknown_cnt = 0

                # 2. 选择技能界面：按策略选卡片
                elif is_skill_select(img):
                    status = "选择技能"
                    # 注意：不在这里做裁剪OCR，直接用整张图OCR结果
                    # 只有当整张图OCR没识别到词条时，do_select_skill内部才会做裁剪OCR兜底
                    pos_name, pos_coord, left_name, middle_name, right_name, reason, selected_name, selected_score = do_select_skill()
                    skill_cnt += 1
                    # 简化日志：一行输出词条名称和选择结果
                    if left_name or middle_name or right_name:
                        if selected_score > 0:
                            print(f"[{time.strftime('%H:%M:%S')}] ⚡ 选择技能 [{left_name}|{middle_name}|{right_name}] → 选[{selected_name}]，优先级({selected_score})")
                        else:
                            print(f"[{time.strftime('%H:%M:%S')}] ⚡ 选择技能 [{left_name}|{middle_name}|{right_name}] → 选[{selected_name}]，随机选择")
                    else:
                        print(f"[{time.strftime('%H:%M:%S')}] ⚡ 选择技能 → 选[{selected_name}]，随机选择")
                    time.sleep(1.2)
                    unknown_cnt = 0

                # 3. 精英掉落界面：点左下角停止转盘，再点左下角关闭
                elif is_elite_drop(img):
                    status = "精英掉落"
                    print(f"[{time.strftime('%H:%M:%S')}] 🎁 精英掉落")
                    close_elite_drop()
                    unknown_cnt = 0

                # 4. 没有选择技能且没有精英掉落，直接检测返回按钮
                else:
                    back_pos = find_text("返回", min_confidence=0.5)
                    if not back_pos:
                        # 没有返回按钮→战斗中，什么都不做
                        status = "战斗中"
                        unknown_cnt = 0
                    else:
                        # 有返回按钮→结算界面识别逻辑
                        print(f"[{time.strftime('%H:%M:%S')}] 🏁 检测到返回按钮{back_pos}，进入结算处理")
                        if is_victory(img):
                            print(f"[{time.strftime('%H:%M:%S')}] 🏆 检测到通关结算界面，处理结算")
                            do_victory()
                            if CLEAN_SCREENSHOT_PER_LEVEL:
                                clean_screenshots()
                                print(f"[{time.strftime('%H:%M:%S')}] 🧹 已清理本关截图")
                        else:
                            # 没检测到通关结算界面（可能是挑战失败），直接点返回按钮
                            print(f"[{time.strftime('%H:%M:%S')}] ↩️  未检测到通关结算界面，直接点击返回按钮 {back_pos}")
                            tap(back_pos)
                            time.sleep(1)
                        in_battle_loop = False  # 关闭开关，跳出游戏循环
                        unknown_cnt = 0

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

                # 最高优先级：重连失败断开连接弹窗（网络断开可能在任何时候发生）
                if is_reconnect_failed_popup(img):
                    status = "重连失败弹窗"
                    print(f"[{time.strftime('%H:%M:%S')}] 🔌 检测到重连失败断开连接弹窗 → 点击确定按钮关闭")
                    close_reconnect_failed_popup()
                    popup_cnt += 1
                    unknown_cnt = 0

                elif is_pay_popup(img):
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

                elif is_level_detail_popup(img):
                    # 关卡详情弹窗：点击右上角×关闭
                    status = "关卡详情弹窗"
                    print(f"[{time.strftime('%H:%M:%S')}] 📋 关卡详情弹窗 → 点击右上角×关闭")
                    close_level_detail_popup()
                    popup_cnt += 1
                    unknown_cnt = 0

                # ===== 第一组：所有弹窗/蒙层检测（必须先关闭所有弹窗，再进行其他判断）=====
                elif is_reward_popup(img):
                    # 奖励展示界面，点击左下角关闭
                    status = "奖励展示"
                    print(f"[{time.strftime('%H:%M:%S')}] 🎉 奖励展示界面 → 点击左下角关闭")
                    close_reward_popup()
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

                # ===== 第二组：关卡操作（所有弹窗关闭后才进行）=====
                elif is_unclaimed_reward(img):
                    # 检测到"未领取"按钮，点击领取奖励
                    status = "未领取奖励"
                    print(f"[{time.strftime('%H:%M:%S')}] 🎁 检测到'未领取'按钮 → 点击领取")
                    claim_unclaimed_reward()
                    # 领取后可能弹出奖励界面，关闭它
                    img2 = screenshot()
                    if img2 is not None:
                        ocr_screenshot(img2)
                        if is_reward_popup(img2):
                            print(f"    → 检测到奖励展示界面 → 关闭")
                            close_reward_popup()
                    # 关闭奖励界面后，识别下半部分去找"完美通关"宝箱并领取奖励
                    # 增加重试机制：最多重试3次，每次重新截图识别
                    perfect_pos = None
                    for retry in range(3):
                        img3 = screenshot()
                        if img3 is not None:
                            ocr_screenshot(img3)
                            if retry == 0:
                                print(f"    → 在下半部分检测完美通关宝箱...")
                            perfect_pos = is_claimable_chest("完美通关")
                            if perfect_pos:
                                break
                            else:
                                print(f"    → 第{retry+1}次未识别到完美通关文字，{0.5 if retry < 2 else 0}秒后重试...")
                                time.sleep(0.5)
                        else:
                            break
                    
                    if perfect_pos:
                        print(f"    → 识别到完美通关文字，宝箱位置 {perfect_pos}，点击领取")
                        tap(perfect_pos)
                        time.sleep(2)
                        # 领取后可能弹出奖励界面，关闭它
                        img4 = screenshot()
                        if img4 is not None:
                            ocr_screenshot(img4)
                            if is_reward_popup(img4):
                                print(f"    → 检测到奖励展示界面 → 关闭")
                                close_reward_popup()
                            else:
                                print(f"    → 未弹出奖励界面（可能已领取）")
                    else:
                        print(f"    → 多次重试仍未识别到完美通关文字（可能已领取或OCR未识别）")
                    unknown_cnt = 0

                elif is_perfect_clear(img):
                    # 当前关卡已完美通关，点击右箭头跳到下一关
                    status = "完美通关"
                    print(f"[{time.strftime('%H:%M:%S')}] ✅ 当前关卡已完美通关 → 点击右箭头跳到下一关")
                    click_next_level()
                    unknown_cnt = 0

                elif is_level_list(img):
                    status = "关卡列表"
                    print(f"[{time.strftime('%H:%M:%S')}] 📋 关卡列表 → 点选择(540,1750)进入单关选择")
                    tap((540, 1750))
                    time.sleep(1.5)
                    unknown_cnt = 0

                elif is_level_select(img):
                    # 单关选择界面：没有完美通关才点击开始游戏
                    # （完美通关的情况已经在上面处理了，会点击右箭头跳到下一关）
                    status = "关卡选择"
                    
                    # 先检查是否有发光的宝箱（未领取的通关奖励），一键领取
                    if claim_all_chests(img):
                        # 领取了宝箱，等待奖励界面关闭后继续
                        time.sleep(1)
                        unknown_cnt = 0
                        continue
                    
                    in_battle_loop = True  # 打开开关，进入游戏循环
                    print(f"[{time.strftime('%H:%M:%S')}] ▶ 关卡选择 → 当前关卡未完美通关，点开始游戏(540,1594)，进入游戏循环")
                    tap(START_BTN)
                    just_started = True
                    just_start_time = time.time()
                    print(f"    → 进入战斗加载阶段，3秒内不触发未知界面兜底")
                    time.sleep(3)
                    
                    # 进入游戏后，先检查倒计时弹窗（已激活技能），只检查一次
                    print(f"    → 检查是否有已激活技能倒计时弹窗...")
                    img_check = screenshot()
                    if img_check is not None:
                        if is_auto_close_popup(img_check):
                            print(f"    → 检测到已激活技能弹窗，点击左下角关闭")
                            close_auto_close_popup()
                        else:
                            print(f"    → 未检测到已激活技能弹窗，继续游戏")
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

            # 根据当前状态决定截图间隔：游戏循环中用BATTLE_LOOP_INTERVAL，非游戏循环用CHECK_INTERVAL
            if in_battle_loop:
                time.sleep(BATTLE_LOOP_INTERVAL)
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
