#!/usr/bin/env python3
"""
fix-bundled-skills.py
修复 bun run build.ts 后运行 node dist/cli.js 报错：
  TypeError: Cannot read properties of undefined (reading 'match')
  at parseFrontmatter

根因：skills/bundled/verify/SKILL.md 及 examples/ 不存在，
      Bun text loader 内联时返回 undefined，导致 parseFrontmatter(undefined) 崩溃。

解决：创建这些缺失文件（stub 内容），然后重新 bun run build.ts。

运行方式：python fix-bundled-skills.py
"""
import os

ROOT = r"F:\Claude code src"


def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    print(f"  OK  {path}")


print("=== fix-bundled-skills ===")
print(f"ROOT: {ROOT}")
print()

# ── skills/bundled/verify/SKILL.md ──────────────────────────
print("[1/3] skills/bundled/verify/SKILL.md")
write(
    os.path.join(ROOT, "skills", "bundled", "verify", "SKILL.md"),
    """\
---
description: Verify a code change does what it should by running the app.
allowed-tools: Bash, Read, Write
---

# Verify

Verify that the code change you just made actually works as expected.

## Steps

1. Read the relevant code that was changed
2. Run any tests that cover the changed code
3. Run the app or a relevant subset to check behavior
4. Report whether the change works as expected

## Notes

- Focus on the specific change made, not the entire codebase
- Run only the tests relevant to the change
- If no tests exist, manually test the affected functionality
""",
)

# ── skills/bundled/verify/examples/cli.md ───────────────────
print("\n[2/3] skills/bundled/verify/examples/cli.md")
write(
    os.path.join(ROOT, "skills", "bundled", "verify", "examples", "cli.md"),
    """\
# CLI Verification Example

When verifying a CLI tool change:

1. Run `--help` to check the command still works
2. Run a simple test case
3. Check the output matches expectations
""",
)

# ── skills/bundled/verify/examples/server.md ────────────────
print("\n[3/3] skills/bundled/verify/examples/server.md")
write(
    os.path.join(ROOT, "skills", "bundled", "verify", "examples", "server.md"),
    """\
# Server Verification Example

When verifying a server change:

1. Start the server
2. Make a test request to the affected endpoint
3. Check the response matches expectations
4. Stop the server
""",
)

print()
print("=== 完成！===")
print()
print("下一步：重新编译并运行")
print("  bun run build.ts 2>&1 | Select-Object -First 20")
print("  node dist\\cli.js")
