#!/usr/bin/env python3
"""
fix-scripts-download-ripgrep.py
修复 bun run build.ts 报错：ModuleNotFound resolving "scripts/download-ripgrep.ts" (entry point)

原因：build.ts 将 scripts/download-ripgrep.ts 作为一个 entry point 编译进 dist/，
      但这个文件不存在。

解决：创建 scripts/download-ripgrep.ts stub（no-op），让 bun build 能正常编译。

运行方式：python fix-scripts-download-ripgrep.py
"""
import os
import sys

ROOT = r"F:\Claude code src"


def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    print(f"  OK  {path}")


print("=== fix-scripts-download-ripgrep ===")
print(f"ROOT: {ROOT}")
print()

# ── scripts/download-ripgrep.ts ──────────────────────────────
# 这个脚本的真实功能：构建后下载对应平台的 ripgrep 二进制到 vendor/ripgrep/
# 由于我们在受控环境编译，不需要实际下载，创建 no-op stub 即可。
# ripgrep 找不到时 GrepTool 会自动降级到系统 rg 或 Python fallback。
print("[1/2] scripts/download-ripgrep.ts")
write(
    os.path.join(ROOT, "scripts", "download-ripgrep.ts"),
    """\
#!/usr/bin/env bun
/**
 * download-ripgrep.ts — no-op stub
 *
 * Real script: downloads ripgrep binary for the current platform into vendor/ripgrep/
 * Stub: skips download; GrepTool will fall back to system `rg` or Python regex.
 *
 * Created by fix-scripts-download-ripgrep.py
 */
console.log('[download-ripgrep] stub: skipping ripgrep download (build environment)')
process.exit(0)
"""
)

# ── dist/download-ripgrep.js（compiled output stub）─────────
# build.ts 编译后会生成 dist/download-ripgrep.js，
# 但如果 bun build 自身因 entry point 找不到而失败，就永远生成不了。
# 先手动放一个占位，保证 postinstall 也不会再报错。
print("\n[2/2] dist/download-ripgrep.js (pre-compiled stub)")
write(
    os.path.join(ROOT, "dist", "download-ripgrep.js"),
    """\
// dist/download-ripgrep.js — pre-compiled stub
// Created by fix-scripts-download-ripgrep.py
console.log('[download-ripgrep] stub: skipping ripgrep download (build environment)')
process.exit(0)
"""
)

print()
print("=== 完成！===")
print()
print("下一步：")
print("  bun run build.ts 2>&1 | Select-Object -First 80")
print()
print("如果 build.ts 里还有其他 scripts/*.ts entry point 缺失，会看到类似报错，")
print("再告诉我，继续补 stub。")
