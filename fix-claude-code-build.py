#!/usr/bin/env python3
"""
fix-claude-code-build.py
修复 Claude Code Windows 本地编译问题
运行方式：python fix-claude-code-build.py
"""
import os, json, re, sys

ROOT = r"F:\Claude code src"

def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    print(f"  OK {path}")

print("=== Claude Code 编译修复脚本 ===")

# ── 1. src/ink/global.d.ts ──────────────────────────────────
print("\n[1/6] src/ink/global.d.ts")
write(os.path.join(ROOT, "src", "ink", "global.d.ts"), "export {}\n")

# ── 2. @ant/computer-use-input stub ─────────────────────────
print("\n[2/6] stubs/ant-computer-use-input")
d = os.path.join(ROOT, "stubs", "ant-computer-use-input")

write(os.path.join(d, "package.json"), json.dumps({
    "name": "@ant/computer-use-input",
    "version": "0.0.0-stub",
    "type": "module",
    "main": "./index.ts"
}, indent=2) + "\n")

write(os.path.join(d, "index.ts"), """\
type MouseButton = 'left' | 'right' | 'middle'
type MouseAction = 'press' | 'release' | 'click'
type ScrollAxis = 'vertical' | 'horizontal'

export type FrontmostAppInfo = { bundleId?: string; appName?: string }

export type ComputerUseInputAPI = {
  moveMouse(x: number, y: number, smooth?: boolean): Promise<void>
  mouseLocation(): Promise<{ x: number; y: number }>
  key(key: string, action?: 'press' | 'release' | 'click'): Promise<void>
  keys(keys: string[]): Promise<void>
  leftClick(): Promise<void>
  rightClick(): Promise<void>
  doubleClick(): Promise<void>
  middleClick(): Promise<void>
  dragMouse(x: number, y: number): Promise<void>
  scroll(x: number, y: number): Promise<void>
  type(text: string): Promise<void>
  mouseButton(button: MouseButton, action?: MouseAction, count?: number): Promise<void>
  mouseScroll(amount: number, axis?: ScrollAxis): Promise<void>
  typeText(text: string): Promise<void>
  getFrontmostAppInfo(): FrontmostAppInfo | null
}

export type ComputerUseInput =
  | ({ isSupported: false } & Partial<ComputerUseInputAPI>)
  | ({ isSupported: true } & ComputerUseInputAPI)

let cursor = { x: 0, y: 0 }
async function noOp(): Promise<void> {}

const stub: ComputerUseInput = {
  isSupported: false,
  async moveMouse(x: number, y: number) { cursor = { x, y } },
  async mouseLocation() { return cursor },
  async key() { await noOp() },
  async keys() { await noOp() },
  async leftClick() { await noOp() },
  async rightClick() { await noOp() },
  async doubleClick() { await noOp() },
  async middleClick() { await noOp() },
  async dragMouse(x: number, y: number) { cursor = { x, y } },
  async scroll() { await noOp() },
  async type() { await noOp() },
  async mouseButton() { await noOp() },
  async mouseScroll() { await noOp() },
  async typeText() { await noOp() },
  getFrontmostAppInfo() { return null },
}

export default stub
""")

# ── 3. @ant/computer-use-mcp stub ───────────────────────────
print("\n[3/6] stubs/ant-computer-use-mcp")
d = os.path.join(ROOT, "stubs", "ant-computer-use-mcp")

write(os.path.join(d, "package.json"), json.dumps({
    "name": "@ant/computer-use-mcp",
    "version": "0.0.0-stub",
    "type": "module",
    "main": "./index.ts",
    "exports": {
        ".": "./index.ts",
        "./types": "./types.ts",
        "./sentinelApps": "./sentinelApps.ts"
    }
}, indent=2) + "\n")

write(os.path.join(d, "index.ts"), """\
export { DEFAULT_GRANT_FLAGS } from './types.js'
export type { CuPermissionRequest, CuPermissionResponse, ScreenshotDims, ComputerUseSessionContext, CuCallToolResult } from './types.js'

export const API_RESIZE_PARAMS = {}

export function targetImageSize(width: number, height: number) {
  return [width, height] as const
}

export function buildComputerUseTools() {
  return [] as Array<{ name: string }>
}

export function bindSessionContext() {
  return async () => ({
    is_error: true,
    content: [{ type: 'text', text: 'Computer use is not supported on this platform.' }],
  })
}
""")

write(os.path.join(d, "types.ts"), """\
export type CoordinateMode = 'pixels' | 'normalized'

export type CuSubGates = {
  pixelValidation?: boolean
  clipboardPasteMultiline?: boolean
  mouseAnimation?: boolean
  hideBeforeAction?: boolean
  autoTargetDisplay?: boolean
  clipboardGuard?: boolean
}

export const DEFAULT_GRANT_FLAGS = {
  accessibility: false,
  screenRecording: false,
}

export type CuPermissionRequest = Record<string, unknown>
export type CuPermissionResponse = {
  granted: string[]
  denied: string[]
  flags: typeof DEFAULT_GRANT_FLAGS
}

export type ScreenshotDims = {
  width: number
  height: number
  displayWidth?: number
  displayHeight?: number
  displayId?: number
  originX?: number
  originY?: number
}

export type CuCallToolResult = {
  is_error?: boolean
  content?: Array<{ type: string; text?: string }>
  telemetry?: Record<string, unknown>
}

export type ComputerUseSessionContext = Record<string, unknown>
""")

write(os.path.join(d, "sentinelApps.ts"), """\
export type SentinelCategory = 'shell' | 'filesystem' | 'system_settings'

export function getSentinelCategory(_bundleId?: string): SentinelCategory | null {
  return null
}
""")

# ── 4. @ant/claude-for-chrome-mcp stub ──────────────────────
print("\n[4/6] stubs/ant-claude-for-chrome-mcp")
d = os.path.join(ROOT, "stubs", "ant-claude-for-chrome-mcp")

write(os.path.join(d, "package.json"), json.dumps({
    "name": "@ant/claude-for-chrome-mcp",
    "version": "0.0.0-stub",
    "type": "module",
    "main": "./index.ts"
}, indent=2) + "\n")

write(os.path.join(d, "index.ts"), """\
export type PermissionMode = 'ask' | 'skip_all_permission_checks' | 'follow_a_plan'

export type Logger = {
  info(message: string): void
  warn(message: string): void
  error(message: string): void
}

export type ClaudeForChromeContext = { serverName?: string; logger?: Logger }

export const BROWSER_TOOLS: Array<{ name: string }> = [
  { name: 'javascript_tool' },
  { name: 'read_page' },
  { name: 'find' },
  { name: 'form_input' },
  { name: 'computer' },
  { name: 'navigate' },
  { name: 'resize_window' },
  { name: 'gif_creator' },
  { name: 'upload_image' },
  { name: 'get_page_text' },
  { name: 'tabs_context_mcp' },
  { name: 'tabs_create_mcp' },
  { name: 'update_plan' },
  { name: 'read_console_messages' },
  { name: 'read_network_requests' },
  { name: 'shortcuts_list' },
  { name: 'shortcuts_execute' },
]

export function createClaudeForChromeMcpServer(_context: ClaudeForChromeContext) {
  return {
    async connect() {},
    setRequestHandler() {},
    async close() {},
  }
}
""")

# ── 5. src/services/contextCollapse/ ────────────────────────
print("\n[5/6] src/services/contextCollapse")
d = os.path.join(ROOT, "src", "services", "contextCollapse")

write(os.path.join(d, "index.ts"), """\
type Stats = {
  collapsedSpans: number
  stagedSpans: number
  health: { totalErrors: number; totalEmptySpawns: number; emptySpawnWarningEmitted: boolean }
}

const stats: Stats = {
  collapsedSpans: 0,
  stagedSpans: 0,
  health: { totalErrors: 0, totalEmptySpawns: 0, emptySpawnWarningEmitted: false },
}

const listeners = new Set<() => void>()

export function initContextCollapse(): void {}

export function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function getStats(): Stats { return stats }
export function isContextCollapseEnabled(): boolean { return false }
export function resetContextCollapse(): void {}

export async function applyCollapsesIfNeeded<T>(
  messages: T,
  _toolUseContext?: unknown,
  _querySource?: unknown,
): Promise<{ messages: T; changed: boolean }> {
  return { messages, changed: false }
}

export function isWithheldPromptTooLong(
  _message?: unknown,
  _isPromptTooLong?: unknown,
  _querySource?: unknown,
): boolean { return false }

export function recoverFromOverflow<T>(
  messages: T,
  _querySource?: unknown,
): { messages: T; committed: number } {
  return { messages, committed: 0 }
}
""")

write(os.path.join(d, "persist.ts"), """\
export function restoreFromEntries(
  _commits?: unknown[],
  _snapshot?: unknown,
): void {}
""")

write(os.path.join(d, "operations.ts"), """\
export function projectView<T>(messages: T): T { return messages }
export function summarizeContextCollapseState(): null { return null }
export function getContextCollapsePreview(): unknown[] { return [] }
""")

# ── 6. package.json ──────────────────────────────────────────
print("\n[6/6] package.json")
pkg_path = os.path.join(ROOT, "package.json")
with open(pkg_path, "r", encoding="utf-8") as f:
    pkg_content = f.read()

needle = "@ant/computer-use-input"
entry = '    "@ant/computer-use-input": "file:./stubs/ant-computer-use-input",'

if needle not in pkg_content:
    pkg_content = re.sub(
        r'("dependencies"\s*:\s*\{)',
        r'\1\n' + entry,
        pkg_content
    )
    if '"overrides"' in pkg_content:
        pkg_content = re.sub(
            r'("overrides"\s*:\s*\{)',
            r'\1\n' + entry,
            pkg_content
        )
    with open(pkg_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(pkg_content)
    print(f"  OK @ant/computer-use-input 已注册")
else:
    print("  -> 已存在，跳过")

print("\n=== 全部修复完成！===")
print("下一步：")
print("  bun install")
print("  bun run build.ts 2>&1 | Select-Object -First 50")
