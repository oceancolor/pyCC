#!/usr/bin/env python3
"""
fix-color-diff.py
用 stub 替换 colorDiff.ts，解决 color-diff-napi 私有包缺失问题
运行方式：python fix-color-diff.py
"""
import os, shutil

ROOT = r"F:\Claude code src"

def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    print(f"  OK {path}")

# ── 1. 备份原始文件 ──────────────────────────────────────────
src = os.path.join(ROOT, "src", "components", "StructuredDiff", "colorDiff.ts")
bak = src + ".bak"

if not os.path.exists(bak):
    shutil.copy2(src, bak)
    print(f"  备份 -> {bak}")
else:
    print(f"  备份已存在，跳过")

# ── 2. 写入 stub ─────────────────────────────────────────────
print("\n[1/1] src/components/StructuredDiff/colorDiff.ts (stub)")
write(src, """\
/**
 * colorDiff.ts — stub for Windows build
 *
 * The real implementation imports from 'color-diff-napi' (private Rust native addon).
 * On Windows local builds that package is unavailable, so all functions return null,
 * which causes HighlightedCode to fall back to HighlightedCodeFallback (plain ANSI).
 */

export type ColorModuleUnavailableReason = 'env' | 'native'

export type SyntaxTheme = Record<string, unknown>

// Minimal shape matching color-diff-napi's ColorDiff class
export type ColorDiffClass = new (oldText: string, newText: string) => {
  render(theme: SyntaxTheme, width: number): string[]
}

// Minimal shape matching color-diff-napi's ColorFile class
export type ColorFileClass = new (code: string, filePath: string) => {
  render(theme: SyntaxTheme, width: number, dim?: boolean): string[]
}

export function getColorModuleUnavailableReason(): ColorModuleUnavailableReason {
  return 'native'
}

export function expectColorDiff(): ColorDiffClass | null {
  return null
}

export function expectColorFile(): ColorFileClass | null {
  return null
}

export function getSyntaxTheme(_themeName: string): SyntaxTheme | null {
  return null
}
""")

print("\n=== 修复完成！===")
print("下一步：")
print("  bun run build.ts 2>&1 | Select-Object -First 50")
print("")
print("如需恢复原文件：")
print(f"  copy \"{bak}\" \"{src}\"")
