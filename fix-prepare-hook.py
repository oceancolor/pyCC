#!/usr/bin/env python3
"""
fix-prepare-hook.py
修复 bun install 因 prepare script 里 git config 命令在非 git 目录失败（exit 128）的问题。

问题：prepare script = "node dist/download-ripgrep.js || ... && git config core.hooksPath .githooks"
      第二条 git config 在非 git 仓库目录下会 fatal exit 128，导致 bun install 中断。

解决：把 prepare script 里每条命令都加上 || true，或直接替换为 exit 0 的 no-op。

运行方式：python fix-prepare-hook.py
"""
import json
import os
import re
import sys

ROOT = r"F:\Claude code src"
PKG = os.path.join(ROOT, "package.json")

print("=== fix-prepare-hook ===")

# 读 package.json（支持 UTF-8 / GBK）
content = None
used_enc = None
for enc in ("utf-8", "gbk", "utf-8-sig"):
    try:
        with open(PKG, "r", encoding=enc) as f:
            content = f.read()
        used_enc = enc
        break
    except Exception:
        continue

if content is None:
    print("ERR: 无法读取 package.json")
    sys.exit(1)

print(f"  读取编码: {used_enc}")

try:
    pkg = json.loads(content)
except json.JSONDecodeError as e:
    print(f"ERR: JSON 解析失败: {e}")
    sys.exit(1)

scripts = pkg.setdefault("scripts", {})
old_prepare = scripts.get("prepare", "")
print(f"\n  原 prepare:\n    {old_prepare}\n")

if not old_prepare:
    print("  prepare 为空，无需修改")
    sys.exit(0)

# 策略：把整个 prepare 替换为最简 no-op，仅保留 download-ripgrep（已有 stub）
# git config 在非 git 目录无意义，直接跳过
new_prepare = "node dist/download-ripgrep.js || true"
scripts["prepare"] = new_prepare

print(f"  新 prepare:\n    {new_prepare}\n")

# 写回（统一 UTF-8，保留 2-space indent）
new_content = json.dumps(pkg, indent=2, ensure_ascii=False) + "\n"
with open(PKG, "w", encoding="utf-8", newline="\n") as f:
    f.write(new_content)

print(f"  OK  package.json 已更新（UTF-8）")
print()
print("=== 完成！===")
print()
print("下一步：")
print("  bun install")
print("  bun run build.ts 2>&1 | Select-Object -First 80")
