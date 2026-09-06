# 开发者文档（项目管理）

本文件供项目维护者参考，普通用户无需阅读。涵盖单元测试、版本管理与发版流程。

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

## 🔥 热更新启动（开发用）

`launcher.py` 监控整个项目目录下的 `.py` 文件（不含自身），代码一改动就自动重启主脚本，方便开发调试。

```bash
# 默认闯关模式
python launcher.py

# 指定模式（参数透传给 auto_play.py，同样支持 -e / -m / -s）
python launcher.py --mode patrol
python launcher.py -e auto -m patrol -s 80
```

> 💡 改任意子模块（config / device / vision / ...）都会触发重启；终端 Ctrl+C 退出启动器。

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
├── menu.py                  # 启动菜单（交互式模拟器/模式选择 + 体力输入）
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
