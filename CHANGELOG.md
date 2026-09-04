

### ✨ 新增

- feat: 增加changelog自动生成脚本，发版时自动生成changelog (5da54da)

### 🐛 修复

- fix: 修复release.py自动生成changelog后工作区不干净导致bump2version失败的问题 (fb95003)

### ⚡ 优化

- perf: 优化精英掉落处理，关闭后如检测到选择技能直接选择词条，节省一次循环 (341bb5e)


# 更新日志

本项目所有重要变更都记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。



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

[未发布]: https://github.com/vipsunwei/zombie-shooter-auto/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/vipsunwei/zombie-shooter-auto/releases/tag/v1.0.0
