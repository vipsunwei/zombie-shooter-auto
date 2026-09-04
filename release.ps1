<#
.SYNOPSIS
    一键发布脚本：升级版本号 → 更新CHANGELOG → 提交 → 打tag → 推送

.DESCRIPTION
    使用 bump2version 自动升级版本号，更新 CHANGELOG.md，提交代码，打 Git tag，然后推送到远程仓库。

.PARAMETER Type
    版本升级类型：patch（修订号）、minor（次版本号）、major（主版本号）

.EXAMPLE
    .\release.ps1 patch
    升级修订号：1.0.0 → 1.0.1

.EXAMPLE
    .\release.ps1 minor
    升级次版本号：1.0.0 → 1.1.0

.EXAMPLE
    .\release.ps1 major
    升级主版本号：1.0.0 → 2.0.0
#>

param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("patch", "minor", "major")]
    [string]$Type
)

$ErrorActionPreference = "Stop"

Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host "  向僵尸开炮 · 一键发布脚本" -ForegroundColor Cyan
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host ""

# 1. 检查是否在 git 仓库中
Write-Host "[1/4] 检查 Git 仓库状态..." -ForegroundColor Yellow
if (-not (Test-Path .git)) {
    Write-Host "❌ 错误：当前目录不是 Git 仓库" -ForegroundColor Red
    exit 1
}

# 检查是否有未提交的更改
$status = git status --porcelain
if ($status) {
    Write-Host "⚠️  警告：工作区有未提交的更改，请先提交或暂存" -ForegroundColor Yellow
    Write-Host $status
    $confirm = Read-Host "是否继续？(y/N)"
    if ($confirm -ne "y" -and $confirm -ne "Y") {
        Write-Host "已取消" -ForegroundColor Red
        exit 0
    }
}
Write-Host "✅ Git 仓库状态正常" -ForegroundColor Green
Write-Host ""

# 2. 检查 bump2version 是否安装
Write-Host "[2/4] 检查 bump2version..." -ForegroundColor Yellow
$bumpVersion = Get-Command bump2version -ErrorAction SilentlyContinue
if (-not $bumpVersion) {
    # 尝试 bumpversion（旧版本名）
    $bumpVersion = Get-Command bumpversion -ErrorAction SilentlyContinue
    if (-not $bumpVersion) {
        Write-Host "⚠️  bump2version 未安装，正在安装..." -ForegroundColor Yellow
        pip install bump2version
        Write-Host "✅ bump2version 安装完成" -ForegroundColor Green
    }
}
Write-Host "✅ bump2version 已就绪" -ForegroundColor Green
Write-Host ""

# 3. 执行版本升级
Write-Host "[3/4] 升级版本号（$Type）..." -ForegroundColor Yellow
Write-Host ""

# 执行 bump2version
bump2version $Type

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ 版本升级失败" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "✅ 版本升级完成" -ForegroundColor Green
Write-Host ""

# 显示新版本号
$newVersion = (Select-String -Path auto_play.py -Pattern '__version__ = "(.+)"').Matches.Groups[1].Value
Write-Host "📌 新版本号：v$newVersion" -ForegroundColor Cyan
Write-Host ""

# 4. 推送到远程
Write-Host "[4/4] 推送到远程仓库..." -ForegroundColor Yellow
Write-Host ""

# 推送代码和 tag
git push
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ 代码推送失败" -ForegroundColor Red
    exit 1
}

git push --tags
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Tag 推送失败" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "✅ 推送完成" -ForegroundColor Green
Write-Host ""

# 完成
Write-Host "=======================================================" -ForegroundColor Green
Write-Host "  🎉 发布完成！v$newVersion" -ForegroundColor Green
Write-Host "=======================================================" -ForegroundColor Green
Write-Host ""
Write-Host "已完成：" -ForegroundColor Cyan
Write-Host "  ✅ 升级版本号：v$newVersion"
Write-Host "  ✅ 更新 CHANGELOG.md"
Write-Host "  ✅ 提交代码"
Write-Host "  ✅ 打 Git tag：v$newVersion"
Write-Host "  ✅ 推送到远程仓库"
Write-Host ""
Write-Host "查看发布：https://github.com/vipsunwei/zombie-shooter-auto/releases/tag/v$newVersion" -ForegroundColor Cyan
