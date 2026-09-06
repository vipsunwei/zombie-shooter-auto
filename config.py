#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全局配置与运行时状态（被所有模块共享）

约定：
- 真正的常量通过 `from config import *` 引入（见 __all__），可直接裸名使用。
- 运行时可变变量（分辨率、OCR 缓存、ADB 连接、状态机开关等）**必须通过
  `config.xxx` 访问**，不要依赖 `from config import *` 带来的副本，否则拿到的是
  模块加载时的旧值（Python 的 import 是引用拷贝，重新赋值不会同步到副本）。
"""

import os

# 项目根目录（本文件所在目录）
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ============================================================
#  用户可配置项（部分会被运行时覆盖，见下方"运行时可变状态"）
# ============================================================
EMULATOR_TYPE = "mumu"      # 运行时由 main 根据命令行参数覆盖
ADB_PATH = ""               # 运行时由 init_adb 填充
DEVICE = ""                 # 运行时由 init_adb 填充
SKILL_STRATEGY = "random"   # 运行时可能被 load_skill_config 覆盖
BATTLE_LOOP_INTERVAL = 3.0  # 游戏循环中每次检测间隔（秒）
CHECK_INTERVAL = 0.8        # 非游戏循环中每次检测间隔（秒）
CLEAN_SCREENSHOT_PER_LEVEL = True  # 每关通关后清理截图
WAVE_WHITE_THRESHOLD = 3.5  # 波次区白色像素占比阈值（判定是否在战斗中）

# 截图临时文件（模拟器内 + 本地）
SCREENSHOT_REMOTE = "/sdcard/auto_play.png"
SCREENSHOT_LOCAL = os.path.join(BASE_DIR, "_current_screen.png")

# ============================================================
#  坐标配置（基准分辨率 1080×1920，运行时自动按实际分辨率缩放）
#  注意：状态判定用的文字/颜色检测区域由各 is_* 函数内联定义（已按实际界面调优），
#  不再在此集中维护，避免出现过时且从未被引用的 REGION_* 死配置。
# ============================================================
CARD_LEFT = (173, 989)    # 左侧技能卡片中心
CARD_MIDDLE = (540, 989)  # 中间技能卡片中心
CARD_RIGHT = (907, 989)   # 右侧技能卡片中心
START_BTN = (540, 1594)  # 关卡选择「开始游戏」按钮
CLOSE_POPUP = (990, 240)  # 付费礼包弹窗右上角 ×
CLOSE_POPUP3 = (990, 170)  # 本周活动弹窗右上角 ×
BACK_BTN = (85, 1785)     # 左下角返回按钮（未知界面兜底，返回上一级）
ACTIVITY_CENTER_CLOSE_BTN = (1005, 250)  # 活动中心界面右上角 × 关闭按钮

# 各类界面点击坐标（基准 1080×1920，运行时由 device.tap 自动缩放）
LEVEL_DETAIL_CLOSE_BTN = (890, 238)    # 关卡详情弹窗右上角 ×
REWARD_BOTTOM_BTN = (100, 1750)       # 精英掉落/已激活技能弹窗左下角关闭
REWARD_CLOSE_BTN = (850, 1684)        # 奖励弹窗「确定/关闭」按钮（开始游戏按钮右侧+310/下+90）
BLANK_CLOSE_BTN = (540, 1720)         # 点击空白处关闭（巡逻/扫荡等，避开技能卡片）
LEVEL_UP_CLOSE_BTN = (540, 1844)      # 等级提升「点击屏幕继续」
RECONNECT_FAIL_BTN = (540, 1200)      # 重连失败弹窗「确定」
NEXT_LEVEL_BTN = (860, 812)           # 下一关右箭头
REWARD_POPUP_CLOSE_BTN = (540, 1750)  # 奖励展示界面关闭（点击左下/空白）
VICTORY_RETURN_FALLBACK = (754, 1695) # 通关「返回」兜底坐标
VICTORY_RETURN_REGION = (500, 1600, 1030, 1800)  # 结算页「返回」OCR 检索区域（限定右下角，防止误匹配底部导航或其他含「返回」文案）

# ============================================================
#  底部导航栏配置（硬编码位置 + 亮度判断，不依赖 OCR）
# ============================================================
BOTTOM_NAV_BUTTONS = [
    ("商城", 90, 1871),
    ("角色", 239, 1871),
    ("核心", 390, 1871),
    ("战斗", 540, 1871),
    ("基地", 690, 1871),
    ("军团", 839, 1871),
    ("征途", 989, 1871),
]

# ============================================================
#  快速巡逻模式配置（基准 1080×1920，识别后固化）
# ============================================================
PATROL_CAR_BTN = (110, 1643)                       # 战斗界面左下角"巡逻车"按钮（OCR 识别）
QUICK_PATROL_BTN_REGION = (150, 1400, 450, 1550)   # 巡逻车弹窗内"快速巡逻"按钮区域
PATROL_CLAIM_REGION = (300, 1100, 800, 1600)       # 巡逻车弹窗内"领取"按钮大致区域，实机校准时可微调
PATROL_TIME_REGION = (455, 815, 625, 870)          # 巡逻车弹窗内正计时文本区域（实测1080x1920：文本中心约(540,842)）
STAMINA_REGION = (675, 65, 825, 108)              # 顶部体力(鸡腿)数量区域（实测1080x1920：文本如 57258/50，中心约(750,86)）
STAMINA_PER_PATROL = 50                           # 一次快速巡逻消耗的鸡腿(体力)数量
OUT_OF_STAMINA_EXIT = 10                          # 体力不足时 auto_play 退出码，launcher 据此停止而非重启
BAG_FULL_EXIT = 11                                # 背包已满时 auto_play 退出码，launcher 据此停止而非重启
STOP_STAMINA_THRESHOLD = STAMINA_PER_PATROL      # 鸡腿(体力)低于此值即停止脚本；可被启动参数 --min-stamina/-s 覆盖，默认同一次巡逻消耗

SELECTED_BRIGHTNESS_THRESHOLD = 650  # 选中状态亮度阈值（选中>650，未选中<620）

# ============================================================
#  宝箱配置（基准 1080×1920）
# ============================================================
CHEST_REGIONS = {
    "成功通关": (130, 1230, 320, 1420),
    "50%血量通关": (410, 1230, 600, 1420),
    "完美通关": (690, 1230, 880, 1420),
}
CHEST_CLICK_POSITIONS = {
    "成功通关": (225, 1325),
    "50%血量通关": (505, 1325),
    "完美通关": (785, 1325),
}

# ============================================================
#  运行时可变状态（必须经由 config.xxx 读写）
# ============================================================
screen_w, screen_h = 1080, 1920   # 实际分辨率（main 连接后填充）
MODE = "battle"                    # 运行模式：battle（循环闯关，默认）/ patrol（快速巡逻）
in_battle_loop = False            # 状态机开关
_wave_miss_count = 0              # 连续未检测到波次的计数
_ocr_reader = None                # OCR 阅读器（懒加载，只初始化一次）
_current_ocr_result = None        # 当前循环 OCR 结果缓存（多个检测函数共享）
_skill_ocr_result = None          # 词条名称区域裁剪后的 OCR 结果（加速用）
_skill_config = None              # 加载后的 skill_config 模块对象
_skill_config_mtime = None        # 配置文件最后修改时间（缓存判断）
_skill_config_exists = None       # 配置文件是否存在（缓存）
SKILL_PRIORITIES = {}             # 词条优先级配置（load_skill_config 填充）
SKILL_PICKED = {}                 # 本局已点词条计数（动态降权用）
SKILL_REQUIRES = {}               # 词条前置依赖（key 依赖 value 先点过）
SKILL_PICK_DECAY = 0.5           # 已点降权系数（第 n 次分数 *= DECAY**n）
SKILL_REQUIRE_DECAY = 0.3        # 前置依赖未满足时的降权系数
_skill_picked_loop = False        # 内部：上一次 in_battle_loop 状态（用于跨关清空历史）

# ============================================================
#  坐标缩放工具（无副作用，供所有模块调用，避免 device<->vision 循环依赖）
# ============================================================
def scale(coord):
    """坐标按分辨率缩放（基准 1080×1920 → 实际分辨率）"""
    x, y = coord
    return int(x * screen_w / 1080), int(y * screen_h / 1920)


def scale_region(region):
    """区域按分辨率缩放（基准 1080×1920 → 实际分辨率）"""
    x1, y1, x2, y2 = region
    return (int(x1 * screen_w / 1080), int(y1 * screen_h / 1920),
            int(x2 * screen_w / 1080), int(y2 * screen_h / 1920))


# ============================================================
#  __all__：仅导出真正的常量（运行时可变状态不导出，强制用 config.xxx）
# ============================================================
__all__ = [
    "scale",
    "scale_region",
    "BASE_DIR",
    "BATTLE_LOOP_INTERVAL",
    "CHECK_INTERVAL",
    "CLEAN_SCREENSHOT_PER_LEVEL",
    "WAVE_WHITE_THRESHOLD",
    "SCREENSHOT_REMOTE",
    "SCREENSHOT_LOCAL",
    "CARD_LEFT",
    "CARD_MIDDLE",
    "CARD_RIGHT",
    "START_BTN",
    "CLOSE_POPUP",
    "CLOSE_POPUP3",
    "BACK_BTN",
    "ACTIVITY_CENTER_CLOSE_BTN",
    "LEVEL_DETAIL_CLOSE_BTN",
    "REWARD_BOTTOM_BTN",
    "REWARD_CLOSE_BTN",
    "BLANK_CLOSE_BTN",
    "LEVEL_UP_CLOSE_BTN",
    "RECONNECT_FAIL_BTN",
    "NEXT_LEVEL_BTN",
    "REWARD_POPUP_CLOSE_BTN",
    "VICTORY_RETURN_FALLBACK",
    "VICTORY_RETURN_REGION",
    "BOTTOM_NAV_BUTTONS",
    "SELECTED_BRIGHTNESS_THRESHOLD",
    "CHEST_REGIONS",
    "CHEST_CLICK_POSITIONS",
    "PATROL_CAR_BTN",
    "QUICK_PATROL_BTN_REGION",
    "PATROL_CLAIM_REGION",
    "PATROL_TIME_REGION",
    "STAMINA_REGION",
    "STAMINA_PER_PATROL",
    "STOP_STAMINA_THRESHOLD",
    "BAG_FULL_EXIT",
]
