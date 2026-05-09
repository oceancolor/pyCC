#!/usr/bin/env python3
"""
setup-hunyuan.py
生成 Claude Code 接入混元的启动脚本（Windows PowerShell）

运行方式：python setup-hunyuan.py
然后根据提示填入 API Key，运行生成的 start-claude-hunyuan.ps1
"""
import os

ROOT = r"F:\Claude code src"
OUT_PS1 = os.path.join(ROOT, "start-claude-hunyuan.ps1")

PS1_CONTENT = r"""# start-claude-hunyuan.ps1
# 用混元模型运行 Claude Code
# 使用前请先填入你的 API Key

# ── 必填 ────────────────────────────────────────────────────────
$env:HUNYUAN_API_KEY = "YOUR_HUNYUAN_API_KEY_HERE"   # 替换为你的混元 API Key

# ── 可选（有默认值）─────────────────────────────────────────────
$env:HUNYUAN_MODEL       = "hunyuan-turbos-latest"   # 主模型（大）
$env:HUNYUAN_SMALL_MODEL = "hunyuan-lite"            # 小模型（Haiku 位置）
# $env:HUNYUAN_BASE_URL  = "https://api.hunyuan.cloud.tencent.com/v1"  # 默认，不用改

# ── 禁用 Anthropic 认证（避免报 API key 缺失错误）─────────────────
$env:ANTHROPIC_API_KEY = "hunyuan-mode-no-anthropic-key-needed"

# ── 启动 Claude Code ────────────────────────────────────────────
Write-Host "Starting Claude Code with Hunyuan model: $($env:HUNYUAN_MODEL)" -ForegroundColor Cyan
node "F:\Claude code src\dist\cli.js" $args
"""

def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(content)
    print(f"  OK  {path}")

print("=== setup-hunyuan ===")
print()
write(OUT_PS1, PS1_CONTENT)

print()
print("=== 完成！===")
print()
print("步骤：")
print(f"  1. 编辑 {OUT_PS1}")
print('     把 "YOUR_HUNYUAN_API_KEY_HERE" 替换为你的混元 API Key')
print()
print("  2. 运行：")
print(r"     powershell -ExecutionPolicy Bypass -File 'F:\Claude code src\start-claude-hunyuan.ps1'")
print()
print("  3. 或者直接在 PowerShell 里设置环境变量然后运行：")
print(r'     $env:HUNYUAN_API_KEY = "sk-xxxxx"')
print(r'     $env:ANTHROPIC_API_KEY = "placeholder"')
print(r'     node "F:\Claude code src\dist\cli.js"')
print()
print("混元 API Key 申请地址：https://hunyuan.tencent.com/")
print("  控制台 → API管理 → 创建密钥")
