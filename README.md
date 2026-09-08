# 向僵尸开炮 · 自动闯关脚本

Python + ADB + RapidOCR 实现的挂机闯关脚本：自动识别游戏界面、精确点击，覆盖战斗、选技能、通关结算、各类弹窗与巡逻。

## 环境要求
- Windows 10/11，Python 3.10~3.12
- MuMu / 雷电模拟器，分辨率 **1080×1920**，游戏语言简体中文

## 安装 Python 与 pip

1. 去 [Python 官网](https://www.python.org/downloads/) 下载 **3.10~3.12** 版本（不要用 3.13+，部分库不支持）；国内网络慢可以用 [华为云镜像](https://mirrors.huaweicloud.com/python/)
2. 安装时**勾选「Add Python to PATH」**，然后点 Install Now
3. 装完后打开命令行（`Win+R` 输入 `cmd`），依次输入验证：
   ```bash
   python --version    # 显示 Python 3.10.x / 3.11.x / 3.12.x 即正常
   pip --version       # 显示 pip 版本号即正常（Python 安装包自带 pip）
   ```
4. 如果 `pip` 命令报错，执行 `python -m ensurepip --upgrade` 修复

## 安装依赖
```bash
pip install -r requirements.txt
```

## 运行

### 交互式启动（推荐新手）
直接运行，会依次弹出 **三个菜单**，每项回车即用默认值：

1. **选择模拟器** —— 默认高亮「自动检测」，回车即用 `auto`（自动寻找已连接的模拟器）
2. **选择模式** —— 默认高亮「闯关」（`battle`），回车即闯关；可选「巡逻车」（`patrol`）或「招募（酒馆十连）」（`recruit`）
3. **设置鸡腿（体力）停止阈值** —— 仅闯关/巡逻模式弹出，直接回车默认 `50`；输入数字可自定义（**只接受正整数**，非数字或 ≤0 会提示重输）。**招募模式不消耗体力，自动跳过此菜单。**

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
python auto_play.py --mode recruit            # 招募（酒馆十连，自动跳过鸡腿菜单）

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

编辑 `skill_config.py`：

- **启用/禁用系别**：改底部 `ENABLED_SERIES` 列表，加系别名即启用、删即禁用（如 `"FIRE"`、`"ICE"`）
- **调整分数**：改对应系别字典里的数值，数值越大优先级越高
- **选择策略**：改顶部 `strategy`，可选 `"priority"`（按优先级，默认）/ `"middle"` / `"random"` / `"left"` / `"right"`
- **动态降权**：`PICK_DECAY` 控制已点词条降权（1.0=关闭，0.5=每次减半），`REQUIRE_DECAY` 控制前置依赖未满足时降权

> 首次运行会自动复制 `skill_config.py` 为 `skill_runtime.py`，后续调优改 `skill_runtime.py` 即可（不影响 git 默认配置）。
> 未配置的词条随机选；支持部分匹配（如配"暴击"匹配"暴击率""暴击伤害"）。

## 锁屏挂机
电脑**不睡眠**即可，`Win+L` 锁屏不影响脚本运行。

## 常见问题
- 缺依赖报错 → `pip install -r requirements.txt`
- 连不上模拟器 → 确认分辨率 1080×1920；MuMu 端口 16384 / 雷电 5555

## 更新日志
版本变更记录见 [CHANGELOG.md](./CHANGELOG.md)。

MIT License · 发版与单元测试见 [MAINTAINER.md](./MAINTAINER.md)
