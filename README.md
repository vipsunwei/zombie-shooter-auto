# 向僵尸开炮 · 自动闯关脚本

基于 Python + ADB + RapidOCR 的《向僵尸开炮》自动闯关脚本，自动识别游戏界面并精确点击，解放双手。

## ✨ 功能特点

- **OCR文字识别**：基于 RapidOCR（OnnxRuntime 引擎，本地运行、无需 torch、启动更快）准确识别游戏界面文字，不靠颜色猜测
- **状态机架构**：游戏循环 / 非游戏循环分离，避免误判误操作
- **多模拟器支持**：自动检测 MuMu / 雷电模拟器，也可手动指定
- **交互式选择**：启动时弹出菜单，上下箭头选择模拟器
- **验证式操作**：每次点击后截图验证，确认成功才继续，防止乱点
- **热更新支持**：配合 launcher.py，修改任意模块后自动重启（监控整个项目目录的 .py 文件）
- **自动清理截图**：每关通关后自动清理本关截图
- **智能词条选择**：支持按优先级选择最优词条，未配置的随机选择（更像人在玩）
- **快速巡逻模式**：`--mode patrol` 自动快速巡逻，满12小时自动领取奖励，体力(鸡腿)不足(<50)或背包已满自动停止并回到战斗-关卡选择

## 🎮 支持的游戏界面

### 游戏循环中
- **选择技能**：自动选择技能卡片（默认选中间）
- **精英掉落**：自动点击结束转盘并关闭
- **通关结算**：自动识别完美通关，优先领取双倍奖励，然后点击返回
- **战斗中**：不操作，等待下一次截图

### 非游戏循环
- **底部导航**：自动识别当前选中项，非战斗界面自动切换到战斗
- **关卡选择**：自动点击开始游戏
- **付费弹窗**：自动关闭见面豪礼等付费弹窗
- **活动弹窗**：自动关闭本周活动弹窗
- **活动中心**：自动关闭活动中心界面
- **等级提升**：自动点击屏幕继续
- **巡逻/扫荡**：自动点击空白处关闭
- **通用关闭**：识别"点击空白处关闭"提示，自动点击关闭
- **未知界面兜底**：连续未知界面自动点击左下角返回按钮

## 🔧 环境要求

- **操作系统**：Windows 10 / 11
- **Python**：3.10 ~ 3.12（推荐 3.12，RapidOCR 兼容性最好）
- **模拟器**：MuMu 模拟器 或 雷电模拟器
- **游戏分辨率**：1080×1920（竖屏）

## 📦 安装步骤

### 1. 安装 Python

下载并安装 Python 3.12：
- 官网下载：https://www.python.org/downloads/
- 安装时**务必勾选** "Add Python to PATH"

验证安装：
```bash
python --version
# 输出类似: Python 3.12.x
```

### 2. 安装模拟器

#### MuMu 模拟器（推荐）
- 官网下载：https://mumu.163.com/
- 安装后启动模拟器，设置分辨率为 **1080×1920（竖屏）**

#### 雷电模拟器
- 官网下载：https://www.ldmnq.com/
- 安装后启动模拟器，设置分辨率为 **1080×1920（竖屏）**

### 3. 安装游戏

在模拟器中安装《向僵尸开炮》，登录账号，进入游戏主界面。

### 4. 下载脚本

```bash
git clone https://github.com/vipsunwei/zombie-shooter-auto.git
cd zombie-shooter-auto
```

或者直接下载 ZIP 解压。

### 5. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

> ⚠️ RapidOCR 基于 OnnxRuntime，无需下载 torch（约2GB），安装更轻量。如果下载慢，可以使用国内镜像：
> ```bash
> pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
> ```

## 🚀 使用方法

### 快速开始

1. 启动模拟器，打开《向僵尸开炮》，进入任意关卡或主界面
2. 运行脚本：
   ```bash
   python auto_play.py
   ```
3. 弹出选择菜单，用**上下箭头**选择模拟器，**回车**确认
4. 脚本自动开始闯关，按 `Ctrl+C` 停止

### 命令行参数

```bash
# 弹出选择菜单（默认 battle 闯关模式，需手动选择模拟器）
python auto_play.py

# 指定 MuMu 模拟器
python auto_play.py --emulator mumu

# 指定雷电模拟器
python auto_play.py --emulator leidian
# 或简写
python auto_play.py --emulator ld

# 自动检测模拟器
python auto_play.py --emulator auto

# 快速巡逻模式（自动巡逻 + 满12小时领取 + 体力不足停止）
python auto_play.py --mode patrol
# 短选项等价写法
python auto_play.py -m patrol
# 自动检测模拟器 + 快速巡逻
python auto_play.py --emulator auto --mode patrol
# 短选项等价写法
python auto_play.py -e auto -m patrol
# 自定义鸡腿停止阈值（剩 80 鸡腿即停，长/短选项均可）
python auto_play.py -m patrol --min-stamina 80
python auto_play.py -m patrol -s 80

# 显式指定闯关模式（默认就是 battle，可省略）
python auto_play.py --mode battle

# 查看帮助
python auto_play.py --help
```

### 巡逻模式（--mode patrol）

自动快速巡逻：循环点击「快速巡逻」，界面出现「领取」按钮（累计巡逻满 12 小时）时自动领取奖励。

- **满 12 小时判定**：巡逻计时为**正计时**（从 `00:00:00` 累加），小时数 ≥ 11（即 `11:xx:xx` ~ `12:xx:xx`）即视为可领取，兼容 OCR 半角/全角冒号、点号误识。
- **体力(鸡腿)不足自动停止**：每轮检测顶部体力，剩余 `< 自定义阈值`（默认 50，可用 `--min-stamina`/`-s` 调整，见上方示例）时自动回到「战斗-关卡选择」界面并停止脚本（退出码 `10`），不会卡在巡逻弹窗。
- **背包已满自动停止**：点击「快速巡逻」后核对鸡腿是否真的减少（正常每次消耗约 50）。背包满时点击会被拦截、鸡腿不减少；连续 3 次点击后鸡腿均未明显减少（消耗差值 < 30）即判定背包已满，关闭巡逻弹窗并停止脚本（退出码 `11`）。该判断基于鸡腿消耗差值，不依赖一闪即逝的「背包已满」提示文字，避免漏判。
- 停止方式与闯关模式一致：`Ctrl+C` 手动停止，或体力耗尽（退出码 `10`）/背包已满（退出码 `11`）自动停止。

> 💡 巡逻弹窗关闭后即为战斗-关卡选择界面，与闯关模式的停止位置相同。

### 热更新模式（开发用）

修改任意模块后自动重启，无需手动停止：

```bash
# 默认 battle 闯关模式
python launcher.py

# 快速巡逻模式（--mode 透传给 auto_play.py）
python launcher.py --mode patrol
```

- 监控项目目录下**所有 `.py` 文件**变化（含 `auto_play.py` 及各子模块 `config/device/vision/states/popups/skills/rewards`）
- 修改任意模块保存后自动重启脚本
- 按 `Ctrl+C` 停止

> 💡 **开发提示**：launcher.py 默认传入 `auto` 参数（自动检测模拟器），不会弹出选择菜单，热更新重启后能直接继续运行。如需指定模拟器，编辑 launcher.py 顶部的 `EMULATOR_ARG` 变量即可。

> 🛑 **智能停止（退出码契约）**：launcher 依据子进程退出码决定是否重启——
> - `0`（正常结束 / `Ctrl+C` 手动停止）、`10`（体力不足自动停止）或 `11`（背包已满自动停止）→ **停止，不重启**
> - 其它非0（运行时崩溃）→ **自动重启**（热更新容错）
>
> 无论用 `launcher.py` 还是直接 `python auto_play.py --mode xxx`，停止判定都一致。

## 🧪 单元测试

项目包含 pytest 单元测试，覆盖坐标缩放、OCR 文字检索、波次像素判定、宝箱发光判定、剩余次数解析、模拟器名归一化等纯函数（不依赖真实模拟器/截图）。

```bash
# 安装测试依赖（已写入 requirements.txt）
pip install -r requirements.txt

# 运行全部测试
python -m pytest tests/ -q

# 运行单个测试文件
python -m pytest tests/test_vision.py -q
```

> 💡 测试在内存中注入假 OCR 结果或合成图片，无需连接模拟器，可在任何环境快速验证重构是否破坏既有行为。

## ⚙️ 配置说明

编辑 `config.py` 顶部的「用户可配置项」区（坐标、检测区域、颜色阈值等也都集中在 `config.py`）：

```python
# 模拟器类型: "mumu"=MuMu | "ldplayer"=雷电 | "auto"=自动检测（运行时由命令行参数覆盖）
EMULATOR_TYPE = "mumu"

# 技能选择策略: "left"=左 | "middle"=中 | "right"=右 | "random"=随机（可被 skill_config.py 覆盖）
SKILL_STRATEGY = "middle"

# 游戏循环中每次检测间隔（秒）
# 战力高、词条弹出快 → 调小（如1.5~2.0），响应更快
# 战力低、词条弹出慢 → 调大（如3.0~5.0），减轻OCR压力
BATTLE_LOOP_INTERVAL = 3.0

# 非游戏循环中每次检测间隔（秒）
CHECK_INTERVAL = 0.8

# 每关通关后是否自动清理截图（模拟器内 + 本地临时文件）
CLEAN_SCREENSHOT_PER_LEVEL = True

# 波次区白色像素占比阈值（判定是否处于战斗中）
WAVE_WHITE_THRESHOLD = 3.5
```

## 🎯 词条优先级配置（推荐）

脚本支持智能选择词条，不再是固定选中间。通过编辑 `skill_config.py` 配置词条优先级，脚本会自动选择最优词条。

### 配置文件位置

```
zombie-shooter-auto/
├── auto_play.py          # 主入口
├── config.py             # 全局配置/坐标
├── skill_config.py       # 词条优先级配置文件（可选）
└── ...
```

### 选择策略

在 `skill_config.py` 中修改 `strategy` 字段：

| 策略 | 说明 | 推荐场景 |
|---|---|---|
| `priority` | 按优先级选择（已配置选最优，未配置随机选） | ⭐ 推荐，最智能 |
| `middle` | 始终选中间卡片 | 简单稳定 |
| `random` | 随机选择左/中/右 | 最像人在玩 |
| `left` | 始终选左边卡片 | 特定需求 |
| `right` | 始终选右边卡片 | 特定需求 |

> 💡 **降级策略**：如果没有提供 `skill_config.py` 配置文件，脚本会自动降级使用 `random`（随机选择），更像人在玩，不会被游戏检测到是脚本。

### 词条优先级配置

在 `skill_config.py` 的 `priorities` 字典中配置词条优先级：

```python
priorities = {
    # ===== 输出类（优先级最高）=====
    "暴击": 100,
    "暴击伤害": 95,
    "暴击率": 92,
    "伤害": 90,
    "攻击力": 88,
    "攻速": 85,
    "穿透": 82,

    # ===== 防御类（优先级中等）=====
    "生命": 60,
    "护甲": 55,
    "减伤": 50,
    "回血": 45,

    # ===== 功能类（优先级较低）=====
    "移速": 30,
    "金币": 20,
    "经验": 15,
    "拾取范围": 10,
}
```

### 配置规则

1. **数字越大，优先级越高**：脚本会选择三个词条中优先级最高的
2. **支持部分匹配**：配置"暴击"会匹配"暴击率"、"暴击伤害"等包含"暴击"的词条
3. **未配置的词条随机选择**：如果三个词条都不在配置中，会随机选择一个（更像人在玩）
4. **想禁用某个词条**：设为 0 或负数即可
5. **热更新支持**：修改配置后保存即可，不需要重启脚本

### 日志输出示例

选择技能时，脚本会输出识别到的三个词条名称和选择结果：

```
[21:38:05] ⚡ 选择技能 → 左[暴击率] 中[攻击力] 右[移速]
    → 选择left卡片(173,989) (1)
```

如果三个词条都没配置（随机选择）：

```
[21:38:05] ⚡ 选择技能 → 左[未知词条A] 中[未知词条B] 右[未知词条C]
    → 随机选择middle卡片(540,989) (1)
```

### 自定义配置建议

根据你的角色 build 和当前关卡难度调整优先级：

| 场景 | 推荐优先级 |
|---|---|
| **输出型 build** | 暴击 > 暴击伤害 > 伤害 > 攻速 > 穿透 |
| **防御型 build** | 生命 > 护甲 > 减伤 > 回血 > 防御 |
| **高难度关卡** | 生命 > 减伤 > 护甲 > 伤害 > 暴击 |
| **低难度关卡** | 暴击 > 伤害 > 攻速 > 金币 > 经验 |
| **刷金币/经验** | 金币 > 经验 > 拾取范围 > 伤害 > 移速 |

## 📋 操作位置说明（基准 1080×1920）

| 操作 | 位置 | 说明 |
|---|---|---|
| 技能卡片-左 | (173, 989) | 选择技能时 |
| 技能卡片-中 | (540, 989) | 默认选择 |
| 技能卡片-右 | (907, 989) | 选择技能时 |
| 开始游戏 | (540, 1594) | 关卡选择界面 |
| 巡逻车/通用空白关闭 | (540, 1720) | 带"点击空白处关闭"提示的弹窗（巡逻车/扫荡等） |
| 双倍奖励 | OCR动态识别 | 通关结算界面（约在左侧） |
| 返回按钮 | OCR动态识别 | 通关结算界面（约在右侧） |
| 底部导航-战斗 | (540, 1871) | 主界面切换 |
| 精英掉落关闭 | (100, 1750) | 左下角 |
| 付费弹窗× | (990, 240) | 右上角 |
| 活动中心× | (1005, 250) | 右上角 |

## ❓ 常见问题

### Q: 提示 "No module named 'rapidocr_onnxruntime'"
A: 依赖未安装，运行 `pip install -r requirements.txt`

### Q: OCR 识别很慢
A: RapidOCR 基于 OnnxRuntime 运行，首次加载模型需要下载（约几十MB）。每次识别约1-2秒，属于正常现象。

### Q: 模拟器连接失败
A: 
1. 确认模拟器已启动
2. 确认模拟器分辨率为 1080×1920
3. 尝试重启模拟器的 ADB 服务
4. MuMu 默认端口 16384，雷电默认端口 5555

### Q: 脚本乱点导致进入未知界面
A: 
1. 确认游戏分辨率为 1080×1920
2. 确认游戏语言为简体中文
3. 脚本有未知界面兜底机制，会自动点击左下角返回
4. 如果持续异常，手动停止脚本，恢复到正常界面后重新运行

### Q: 精英掉落识别不准确
A: 精英掉落文字较小，OCR 置信度偏低。脚本已降低阈值并优化检测区域，如果仍有问题，可以手动关闭精英掉落界面，脚本会继续正常运行。

### Q: 双倍奖励不领取
A: 双倍奖励需要同时满足三个条件：
1. 界面上有"双倍奖励"按钮
2. 有"完美通关"字样
3. 今日剩余次数 > 0

不满足条件时会直接点击返回，日志会输出具体原因。

## 💻 后台运行与锁屏说明

脚本通过 ADB 连接模拟器操作，**电脑锁屏不影响脚本运行**，但需要注意电源设置。

### 锁屏影响分析

| 场景 | 脚本是否继续运行 | 说明 |
|---|---|---|
| 手动锁屏（Win+L），电脑不睡眠 | ✅ 正常运行 | 只是关闭显示器显示 |
| 自动关闭显示器，电脑不睡眠 | ✅ 正常运行 | 省电，不影响脚本 |
| 电脑进入睡眠 | ❌ 脚本暂停 | 唤醒后从断点继续 |
| 模拟器被手动关闭 | ❌ 脚本报错停止 | 需重启模拟器和脚本 |

### 推荐设置（重要）

#### 1. 电源设置（最关键）

设置电脑**接通电源时永不睡眠**：

**方法一：图形界面**
- 按 Win + R，输入 powercfg.cpl 回车
- 选择「高性能」或「平衡」电源计划
- 点击「更改计划设置」
- 「关闭显示器」可设为 5~10 分钟（省电）
- 「使计算机进入睡眠状态」**设为「从不」**

**方法二：命令行（一键设置）**
```powershell
# 接通电源时永不睡眠
powercfg /change standby-timeout-ac 0
# 接通电源时永不休眠
powercfg /change hibernate-timeout-ac 0
```

#### 2. 模拟器设置

确认模拟器开启「后台运行不暂停」：
- **MuMu 模拟器**：右上角设置 → 性能设置 → 开启「后台运行时不暂停」
- **雷电模拟器**：右上角设置 → 性能设置 → 开启「后台运行保持活跃」

#### 3. 推荐锁屏方式

出门前用 **Win + L 手动锁屏**，既安全又不影响脚本运行。关闭显示器可以省电，但不要让电脑进入睡眠。

### 总结

> 💡 **只要电脑不进入睡眠状态，锁屏完全不影响脚本自动闯关。** 设置好电源选项后，可以放心锁屏去做别的事，脚本会一直在后台自动玩游戏。

## ⚠️ 注意事项

1. **分辨率必须为 1080×1920**，否则点击位置会偏移
2. **游戏语言必须为简体中文**，OCR 针对中文优化
3. 运行脚本时**不要操作模拟器**，避免干扰
4. 建议在**战斗力足够高**时使用，确保能快速通关
5. 脚本仅供学习交流使用，请遵守游戏用户协议

## 📝 更新日志

完整的版本更新记录请查看 [CHANGELOG.md](./CHANGELOG.md)。

## 📄 许可证

MIT License

## 🔖 版本管理

本项目使用 [语义化版本](https://semver.org/lang/zh-CN/) 和 [bump2version](https://github.com/c4urself/bump2version) 进行版本管理。

### 版本号格式

```
主版本号.次版本号.修订号
   │       │       │
   │       │       └─ 修订号：bug修复，不影响功能（如 1.0.0 → 1.0.1）
   │       └─ 次版本号：新增功能，向后兼容（如 1.0.0 → 1.1.0）
   └─ 主版本号：不兼容的API变更（如 1.0.0 → 2.0.0）
```

### 发布新版本（推荐：一键发布脚本）

使用 `tools/release.py` 一键完成：升级版本号 → 更新CHANGELOG → 提交 → 打tag → 推送。

**⚠️ 重要：发版前请先预览，确认 changelog 内容正确！**

```bash
# 预览模式：只显示将生成的 changelog 内容，不修改任何文件
python tools/release.py patch --dry-run

# 确认无误后，真正发版
python tools/release.py patch
```

**升级版本类型：**

```bash
# 升级修订号：1.0.0 → 1.0.1（修bug）
python tools/release.py patch

# 升级次版本号：1.0.0 → 1.1.0（加功能）
python tools/release.py minor

# 升级主版本号：1.0.0 → 2.0.0（大改不兼容）
python tools/release.py major
```

脚本会自动完成：
1. 检查 Git 仓库状态
2. 检查并安装 bump2version（如未安装）
3. 在内存中生成 changelog 内容（基于 git commit 自动分类）
4. 手动更新 CHANGELOG.md 版本号（不依赖 bump2version，更可靠）
5. 自动更新底部链接定义（`[未发布]` compare 链接 + `[新版本号]` release 链接）
6. 执行 bump2version 升级版本号（只修改 version.py，自动提交、打tag）
7. 自动探测代理并推送到远程仓库（代码 + tag）

### 手动发布（不使用脚本）

```bash
# 1. 安装 bump2version（只需安装一次）
pip install bump2version

# 2. 升级版本号（自动修改代码、更新CHANGELOG、提交、打tag）
bump2version patch    # 修订号+1：1.0.0 → 1.0.1
bump2version minor    # 次版本号+1：1.0.0 → 1.1.0
bump2version major    # 主版本号+1：1.0.0 → 2.0.0

# 3. 推送到远程（包含tag）
git push && git push --tags
```

### CHANGELOG 自动生成

不需要手动写 changelog！`tools/generate_changelog.py` 会基于 git commit 记录自动生成，根据关键词自动分类：

| 分类 | 匹配关键词 |
|---|---|
| ✨ 新增 | 增加、新增、添加、实现、支持、feat |
| 🔧 重构 | 重构、refactor、重写、拆分、提取 |
| 🐛 修复 | 修复、bug、解决、fix、bugfix、hotfix、修正、修补 |
| ⚡ 优化 | 优化、改进、提升、perf、performance、调整 |
| 📝 文档 | 文档、README、说明、docs、changelog |
| 🎨 格式 | 格式、style、format、lint、代码风格 |
| ✅ 测试 | 测试、test、单元测试 |
| 🔨 构建 | 构建、build、ci、cd、部署、release、发布、chore、依赖 |
| 📦 其他 | 不匹配以上关键词 |

> 💡 **分类优先级**：优先匹配 commit message 前缀（如 `feat:`、`fix:`、`refactor:`），前缀匹配不到再用关键词匹配。自动去掉 commit message 中的前缀，保持 changelog 简洁。

**手动生成 changelog（不发版）：**

```bash
# 生成从上一个 tag 到现在的 changelog
python tools/generate_changelog.py

# 只预览不写入文件
python tools/generate_changelog.py --dry-run

# 生成全部历史的 changelog
python tools/generate_changelog.py --all
```

**发版时自动生成：**

执行 `python tools/release.py patch` 时会自动调用 `tools/generate_changelog.py` 生成 changelog，然后再升级版本号。

### 版本号存放位置

- `version.py` 中的 `__version__` 变量（独立文件，避免每次发版修改主脚本）
- `.bumpversion.cfg` 配置文件（bump2version 使用，只修改 version.py）
- `tools/changelog_utils.py` changelog 公共函数库（版本号读取、计算、更新）
- `tools/generate_changelog.py` changelog 自动生成脚本（基于 git commit）
- `tools/release.py` 一键发布脚本（含 `--dry-run` 预览模式）
- `CHANGELOG.md` 版本变更记录

### 项目文件结构

```
zombie-shooter-auto/
├── auto_play.py              # 主入口（main 主循环 + 命令行参数解析）
├── config.py                 # 全局配置/坐标/REGION/运行时状态/坐标缩放（所有模块共享）
├── device.py                 # 设备控制：ADB/截图/tap/模拟器检测/底部导航/兜底返回/清理
├── vision.py                 # OCR 封装 + 文字检索 + 波次像素辅助
├── states.py                 # 界面判定（所有 is_* 纯判定，不依赖设备操作）
├── popups.py                 # 弹窗关闭（所有 close_* + 点击空白关闭）
├── skills.py                 # 词条配置热加载与智能选择
├── rewards.py                # 奖励/宝箱/胜利结算/关卡切换
├── skill_config.py           # 词条优先级配置文件（可选，缺失时降级随机）
├── launcher.py               # 热更新启动器（监控整目录 .py 自动重启）
├── tools/                    # 发布工具
│   ├── release.py            #   一键发布脚本（含 --dry-run 预览模式）
│   ├── generate_changelog.py #   changelog 自动生成脚本（基于 git commit）
│   └── changelog_utils.py    #   changelog 公共函数库（版本号读取、计算、更新）
├── tests/                    # 单元测试（pytest）
│   ├── test_config.py
│   ├── test_vision.py
│   ├── test_states.py
│   ├── test_rewards.py
│   └── test_auto_play.py
├── version.py                # 版本号独立文件（避免每次发版修改主脚本）
├── .bumpversion.cfg          # bump2version 配置
├── .gitignore                # Git 忽略规则
├── README.md                 # 项目说明文档
├── CHANGELOG.md              # 版本变更记录
└── requirements.txt          # Python 依赖包列表
```

> 📐 **模块化设计**：代码从单文件巨石 `auto_play.py` 拆分为扁平多模块。全局共享状态集中在 `config.py`；常量用 `from config import *` 裸名访问，运行时可变变量（如分辨率、OCR 缓存、状态机开关）必须经由 `config.xxx` 读写，避免 import 副本失效。`auto_play.py` 只负责组合各模块并运行主循环。

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

**如果这个脚本对你有帮助，欢迎给个 Star ⭐**
