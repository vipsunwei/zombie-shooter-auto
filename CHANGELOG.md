# 更新日志

本项目所有重要变更都记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [未发布]

（暂无变更）

## [2.0.1] - 2026-09-07

### 🔧 重构

- _wave_miss_count 封装为访问器，消除私有变量直接访问 (e831cb0)
- 检测区域坐标全部接入分辨率缩放 (f5311c4)
- handlers.py 13 处裸 print 统一替换为 _log与其他日志保持一致的时间戳格式，便于排查问题 (74bd405)
- close_reward_popup 改为验证式关闭原实现连点两次关闭区且不验证，第二次点击可能在弹窗已关闭后误触其他界面；改为 device.close_with_verify，与其他 close_* 风格统一 (dfaa20f)

### 🐛 修复

- 鸡腿识别放大3倍+停机前复核，防止OCR误读导致提前停止 (1564320)
- 战斗兜底的「返回」检测限定到结算页右下区域 (d20ffcb)
- do_victory 的「返回」检索限定到结算页右下区域，防止误点 (8f5f0c6)
- 修正 rewards.py 中 close_with_verify 的模块归属错误该方法定义在 device 模块，误写为 popups.close_with_verify，运行到宝箱领取流程时会抛 AttributeError (d7c1e73)
- 修正 CHEST_REGIONS 元组顺序为 (x1, y1, x2, y2)原配置实际是 (x1, x2, y1, y2) 顺序，与 states.py 的解包约定及全项目其他区域配置不一致，导致宝箱检测区被裁剪到 y 320~925，完全覆盖不到宝箱图标（y 1230~1420），发光判定永远失效。- config.py: 三个区域归位为 (x1, y1, x2, y2) 约定- tests/test_states.py: 修正过时的重叠关系注释 (1681d54)

### 🔨 构建

- 清理 device/vision 小问题（死代码、图片句柄、端口死循环） (412de3a)

## [2.0.0] - 2026-09-06

### ✨ 新增

- 新增启动交互菜单并拆分 menu 模块，补充运行文档 (4ca2714)
- 新增快速巡逻模式（自动巡逻/满12h领取/背包满停止/自定义鸡腿阈值/奖励弹窗校验式重试关闭） (552d604)

### 🔧 重构

- 主循环改为表驱动分派并拆分 cli/handlers 模块 (c45847a)

### ⚡ 优化

- 优化词条优先级配置文件及优先级算法逻辑 (1e1dad5)

### 📝 文档

- README 补充更新日志链接 (752fecf)

## [1.0.9] - 2026-09-06

### 🔧 重构

- 拆分 auto_play 为扁平多模块并修复审查崩溃 bug (43ea426)

### 🐛 修复

- 修复 release.py f-string 嵌套引号语法错误 (8a9cea7)
- 修复巡逻车弹窗关闭点、优化战斗判定并同步文档 (1ea1337)
- 修复check_bump2version误报未安装的问题，改用模块导入检查方式 (72238cb)

## [1.0.8] - 2026-09-05

### 🐛 修复

- 修复CHANGELOG底部链接定义缺失问题，发版时自动更新链接定义 (01318db)

### 📝 文档

- 更新README，增加--dry-run预览模式说明、重构分类、项目文件结构 (ecbae04)

## [1.0.7] - 2026-09-05

### ✨ 新增

- release.py增加--dry-run预览模式，重构CHANGELOG版本号处理逻辑，新增changelog_utils公共函数库 (66b97a4)

### 🐛 修复

- 修正CHANGELOG v1.0.6内容，补充版本号标题并去掉commit前缀 (5017ee5)

## [1.0.6] - 2026-09-05

### 🔧 重构
- 优化generate_changelog分类规则，增加重构分类，修复refactor误分类问题 (286074f)

### 🐛 修复
- 修正CHANGELOG，补充v1.0.5版本记录 (8626842)

## [1.0.5] - 2026-09-05

### 🔧 重构
- 版本号提取到独立文件 version.py，避免每次发版修改主脚本 (64d1b9c)

### 🐛 修复
- 修正 CHANGELOG，补充 v1.0.4 版本记录 (8e859ac)

## [1.0.4] - 2026-09-05

### ✨ 新增
- release.py 增加自动探测代理功能，有可用代理自动使用代理推送 (edd3f62)

### 🐛 修复
- 修正 CHANGELOG 结构混乱，补充 v1.0.3 版本记录 (dc02407)

## [1.0.3] - 2026-09-05

### 🐛 修复
- 修复 CHANGELOG 结构混乱和 generate_changelog 替换逻辑不健壮的问题 (2f2fb53)

## [1.0.2] - 2026-09-05

### ✨ 新增
- 增加 changelog 自动生成脚本，发版时自动生成 changelog (5da54da)

### 🐛 修复
- 修复 release.py 自动生成 changelog 后工作区不干净导致 bump2version 失败的问题 (fb95003)

### ⚡ 优化
- 优化精英掉落处理，关闭后如检测到选择技能直接选择词条，节省一次循环 (341bb5e)

## [1.0.1] - 2026-09-05

### 新增
- 游戏循环截图间隔改为可配置 `BATTLE_LOOP_INTERVAL`，适应不同战力用户
- launcher.py 增加 `EMULATOR_ARG` 配置，热更新重启不再弹出选择菜单
- README 增加后台运行与锁屏说明，指导用户设置电源选项

### 修复
- 修正 README 中的 git clone 地址
- 修正 README 配置变量名与脚本实际一致（`CHECK_INTERVAL`、`CLEAN_SCREENSHOT_PER_LEVEL`）
- 双倍奖励位置说明改为 OCR 动态识别
- 修复 README 中 powershell 代码块格式（单个反引号改为三个反引号）

## [1.0.0] - 2026-09-05

### 新增
- 初始版本发布
- 支持 MuMu / 雷电模拟器自动检测
- 基于 EasyOCR 的文字识别，不靠颜色猜测
- 状态机架构：游戏循环 / 非游戏循环分离
- 交互式模拟器选择菜单（上下箭头选择）
- 热更新支持：launcher.py 监控文件变化自动重启
- 自动清理截图：每关通关后清理模拟器内和本地临时文件
- 验证式操作：每次点击后截图验证，确认成功才继续
- 未知界面兜底：连续未知界面自动点击左下角返回按钮

### 支持的游戏界面

**游戏循环中：**
- 选择技能：自动选择技能卡片（默认选中间）
- 精英掉落：自动点击结束转盘并关闭
- 通关结算：自动识别完美通关，优先领取双倍奖励，然后点击返回
- 战斗中：不操作，等待下一次截图

**非游戏循环：**
- 底部导航：自动识别当前选中项，非战斗界面自动切换到战斗
- 关卡选择：自动点击开始游戏
- 付费弹窗：自动关闭见面豪礼等付费弹窗
- 活动弹窗：自动关闭本周活动弹窗
- 活动中心：自动关闭活动中心界面
- 等级提升：自动点击屏幕继续
- 巡逻/扫荡：自动点击空白处关闭
- 通用关闭：识别"点击空白处关闭"提示，自动点击关闭

---

[未发布]: https://github.com/vipsunwei/zombie-shooter-auto/compare/v2.0.1...HEAD
[2.0.1]: https://github.com/vipsunwei/zombie-shooter-auto/releases/tag/v2.0.1
[2.0.0]: https://github.com/vipsunwei/zombie-shooter-auto/releases/tag/v2.0.0
[1.0.9]: https://github.com/vipsunwei/zombie-shooter-auto/releases/tag/v1.0.9
[1.0.8]: https://github.com/vipsunwei/zombie-shooter-auto/releases/tag/v1.0.8
[1.0.7]: https://github.com/vipsunwei/zombie-shooter-auto/releases/tag/v1.0.7
[1.0.6]: https://github.com/vipsunwei/zombie-shooter-auto/releases/tag/v1.0.6
[1.0.5]: https://github.com/vipsunwei/zombie-shooter-auto/releases/tag/v1.0.5
[1.0.4]: https://github.com/vipsunwei/zombie-shooter-auto/releases/tag/v1.0.4
[1.0.3]: https://github.com/vipsunwei/zombie-shooter-auto/releases/tag/v1.0.3
[1.0.2]: https://github.com/vipsunwei/zombie-shooter-auto/releases/tag/v1.0.2
[1.0.1]: https://github.com/vipsunwei/zombie-shooter-auto/releases/tag/v1.0.1
[1.0.0]: https://github.com/vipsunwei/zombie-shooter-auto/releases/tag/v1.0.0
