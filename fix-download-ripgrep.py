#!/usr/bin/env python3
"""
fix-download-ripgrep.py
修复 bun install prepare hook 报错：dist/download-ripgrep.js 不存在
原因：package.json 的 prepare script 调用 dist/download-ripgrep.js，
      但 dist/ 目录在编译前不存在，导致 bun install exit 128。
解决方案：创建一个空操作的 dist/download-ripgrep.js，让 prepare 顺利通过。

运行方式（Windows）：
  python fix-download-ripgrep.py
"""
import os
import json
import sys

ROOT = r"F:\Claude code src"


def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    print(f"  OK  {path}")


print("=== fix-download-ripgrep ===")
print(f"ROOT: {ROOT}")
print()

# ── 1. 创建 dist/download-ripgrep.js（空操作 stub）──────────
print("[1/3] dist/download-ripgrep.js")
dist_dir = os.path.join(ROOT, "dist")
rg_js = os.path.join(dist_dir, "download-ripgrep.js")

write(rg_js, """\
#!/usr/bin/env node
// stub: download-ripgrep.js
// This is a no-op stub created by fix-download-ripgrep.py.
// The real script downloads ripgrep binaries, but since we're building from source
// in an offline/controlled environment, we skip the download.
// ripgrep is used by GrepTool as a fast search backend; if not available,
// the Python fallback (grep / re module) will be used instead.
console.log('[download-ripgrep] stub: skipping ripgrep download (build environment)');
process.exit(0);
""")

# ── 2. 检查并修复 package.json prepare script（可选）──────────
print("\n[2/3] 检查 package.json prepare script")
pkg_path = os.path.join(ROOT, "package.json")

if not os.path.exists(pkg_path):
    print(f"  WARN package.json 不存在：{pkg_path}，跳过")
else:
    # 尝试多种编码读取（源码可能是 GBK）
    pkg_content = None
    for enc in ("utf-8", "gbk", "utf-8-sig"):
        try:
            with open(pkg_path, "r", encoding=enc) as f:
                pkg_content = f.read()
            break
        except (UnicodeDecodeError, Exception):
            continue

    if pkg_content is None:
        print("  WARN 无法读取 package.json，跳过 prepare 检查")
    else:
        try:
            pkg = json.loads(pkg_content)
            scripts = pkg.get("scripts", {})
            prepare = scripts.get("prepare", "")
            print(f"  当前 prepare: {prepare!r}")

            # 如果 prepare 包含 download-ripgrep，添加 || true 让失败不阻塞
            if "download-ripgrep" in prepare and "|| true" not in prepare:
                new_prepare = prepare + " || true"
                pkg["scripts"]["prepare"] = new_prepare
                new_content = json.dumps(pkg, indent=2, ensure_ascii=False) + "\n"
                with open(pkg_path, "w", encoding="utf-8", newline="\n") as f:
                    f.write(new_content)
                print(f"  OK  prepare 已追加 '|| true'")
                print(f"  新  prepare: {new_prepare!r}")
            elif "download-ripgrep" in prepare:
                print("  -> 已有 '|| true'，跳过")
            else:
                print("  -> prepare 不含 download-ripgrep，无需修改")
        except json.JSONDecodeError as e:
            print(f"  WARN JSON 解析失败（{e}），跳过 prepare 检查")

# ── 3. 检查 .npmrc / bunfig.toml（忽略 prepare 的另一种方式）──
print("\n[3/3] 提示：如果以上仍然不够，可用 --ignore-scripts 跳过所有 hooks")
print("  bun install --ignore-scripts")
print("  （但会同时跳过所有 postinstall，可能影响其他 stub 链接）")

print()
print("=== 完成！===")
print()
print("下一步：")
print("  1. 运行: python fix-download-ripgrep.py")
print("  2. 然后: bun install")
print("  3. 如果 bun install 还报其他 prepare 错误，改用:")
print("        bun install --ignore-scripts")
print("  4. 最后: bun run build.ts 2>&1 | Select-Object -First 80")
