# 向僵尸开炮 · 自动闯关脚本

Python + ADB + RapidOCR 实现的挂机闯关脚本：自动识别游戏界面、精确点击，覆盖战斗、选技能、通关结算、各类弹窗与巡逻。

## 环境要求
- Windows 10/11，Python 3.10~3.12
- MuMu / 雷电模拟器，分辨率 **1080×1920**，游戏语言简体中文

## 安装
```bash
pip install -r requirements.txt
```

## 运行

### 交互式启动（推荐新手）
直接运行，会依次弹出 **三个菜单**，每项回车即用默认值：

1. **选择模拟器** —— 默认高亮「自动检测」，回车即用 `auto`（自动寻找已连接的模拟器）
2. **选择模式** —— 默认高亮「闯关」（`battle`），回车即闯关；可选「巡逻车」（`patrol`）
3. **设置鸡腿（体力）停止阈值** —— 直接回车默认 `50`；输入数字可自定义（**只接受正整数**，非数字或 ≤0 会提示重输）

```bash
python auto_play.py
```

> 模拟器 / 模式菜单用 **↑↓ 箭头**移动高亮项、**回车**确认；中途按 **Ctrl+C** 可取消退出。
> 体力输入是文本框，直接打字后回车。

### 命令行免交互（适合定时任务 / 脚本）
命令行显式指定某参数，就**跳过对应菜单**；没指定的仍会弹菜单。三者可任意组合：

```bash
# 模拟器（--emulator / -e）
python auto_play.py --emulator auto          # 自动检测（默认高亮）
python auto_play.py --emulator mumu          # MuMu
python auto_play.py --emulator leidian        # 雷电（简写 -e ld）

# 模式（--mode / -m）
python auto_play.py --mode battle             # 闯关（默认）
python auto_play.py --mode patrol             # 巡逻车

# 鸡腿停止阈值（--min-stamina / -s，默认 50）
python auto_play.py --min-stamina 80          # 鸡腿 <80 即停

# 组合：三项都指定 → 不弹任何菜单，直接开跑
python auto_play.py -e auto -m patrol -s 80
```

> 支持 `--xxx value` 与 `--xxx=value` 两种写法，短选项 `-e / -m / -s` 同理。
> 例：`python auto_play.py -m patrol` → 跳过模式菜单，仍会弹模拟器与体力菜单。

### 查看全部参数
```bash
python auto_play.py --help
```

## 高级 · 自定义词条优先级
编辑 `skill_config.py`：在 `ENABLED_SERIES` 列表里加系别名启用、删则禁用（如 `"FIRE"`）。默认按优先级智能选最优，未配置的词条随机选。

## 锁屏挂机
电脑**不睡眠**即可，`Win+L` 锁屏不影响脚本运行。

## 常见问题
- 缺依赖报错 → `pip install -r requirements.txt`
- 连不上模拟器 → 确认分辨率 1080×1920；MuMu 端口 16384 / 雷电 5555

MIT License · 发版与单元测试见 [MAINTAINER.md](./MAINTAINER.md)
