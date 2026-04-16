# fix-claude-code-build.ps1
# 运行方式：Set-ExecutionPolicy Bypass -Scope Process; .\fix-claude-code-build.ps1

$Root = "F:\Claude code src"
Set-Location $Root
$Q = [char]39   # 单引号 '
$nl = "`n"

function WriteFile($path, $lines) {
    $dir = Split-Path $path
    if ($dir) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    $content = ($lines -join $nl) + $nl
    [System.IO.File]::WriteAllText($path, $content, [System.Text.Encoding]::UTF8)
    Write-Host "  OK $path" -ForegroundColor Green
}

Write-Host "=== Claude Code 编译修复脚本 ===" -ForegroundColor Cyan

# ── 1. src/ink/global.d.ts ──────────────────────────────────
Write-Host "`n[1/6] src\ink\global.d.ts" -ForegroundColor Yellow
WriteFile (Join-Path $Root "src\ink\global.d.ts") @("export {}")

# ── 2. @ant/computer-use-input stub ─────────────────────────
Write-Host "`n[2/6] stubs\ant-computer-use-input" -ForegroundColor Yellow
$d = Join-Path $Root "stubs\ant-computer-use-input"

WriteFile "$d\package.json" @(
    "{",
    "  " + $Q + "name" + $Q + ": " + $Q + "@ant/computer-use-input" + $Q + ",",
    "  " + $Q + "version" + $Q + ": " + $Q + "0.0.0-stub" + $Q + ",",
    "  " + $Q + "type" + $Q + ": " + $Q + "module" + $Q + ",",
    "  " + $Q + "main" + $Q + ": " + $Q + "./index.ts" + $Q,
    "}"
)

WriteFile "$d\index.ts" @(
    "type MouseButton = $Q`left$Q | $Q`right$Q | $Q`middle$Q",
    "type MouseAction = $Q`press$Q | $Q`release$Q | $Q`click$Q",
    "type ScrollAxis = $Q`vertical$Q | $Q`horizontal$Q",
    "",
    "export type FrontmostAppInfo = { bundleId?: string; appName?: string }",
    "",
    "export type ComputerUseInputAPI = {",
    "  moveMouse(x: number, y: number, smooth?: boolean): Promise<void>",
    "  mouseLocation(): Promise<{ x: number; y: number }>",
    "  key(key: string, action?: $Q`press$Q | $Q`release$Q | $Q`click$Q): Promise<void>",
    "  keys(keys: string[]): Promise<void>",
    "  leftClick(): Promise<void>",
    "  rightClick(): Promise<void>",
    "  doubleClick(): Promise<void>",
    "  middleClick(): Promise<void>",
    "  dragMouse(x: number, y: number): Promise<void>",
    "  scroll(x: number, y: number): Promise<void>",
    "  type(text: string): Promise<void>",
    "  mouseButton(button: MouseButton, action?: MouseAction, count?: number): Promise<void>",
    "  mouseScroll(amount: number, axis?: ScrollAxis): Promise<void>",
    "  typeText(text: string): Promise<void>",
    "  getFrontmostAppInfo(): FrontmostAppInfo | null",
    "}",
    "",
    "export type ComputerUseInput =",
    "  | ({ isSupported: false } & Partial<ComputerUseInputAPI>)",
    "  | ({ isSupported: true } & ComputerUseInputAPI)",
    "",
    "let cursor = { x: 0, y: 0 }",
    "async function noOp(): Promise<void> {}",
    "",
    "const stub: ComputerUseInput = {",
    "  isSupported: false,",
    "  async moveMouse(x: number, y: number) { cursor = { x, y } },",
    "  async mouseLocation() { return cursor },",
    "  async key() { await noOp() },",
    "  async keys() { await noOp() },",
    "  async leftClick() { await noOp() },",
    "  async rightClick() { await noOp() },",
    "  async doubleClick() { await noOp() },",
    "  async middleClick() { await noOp() },",
    "  async dragMouse(x: number, y: number) { cursor = { x, y } },",
    "  async scroll() { await noOp() },",
    "  async type() { await noOp() },",
    "  async mouseButton() { await noOp() },",
    "  async mouseScroll() { await noOp() },",
    "  async typeText() { await noOp() },",
    "  getFrontmostAppInfo() { return null },",
    "}",
    "",
    "export default stub"
)

# ── 3. @ant/computer-use-mcp stub ───────────────────────────
Write-Host "`n[3/6] stubs\ant-computer-use-mcp" -ForegroundColor Yellow
$d = Join-Path $Root "stubs\ant-computer-use-mcp"

WriteFile "$d\package.json" @(
    "{",
    "  " + $Q + "name" + $Q + ": " + $Q + "@ant/computer-use-mcp" + $Q + ",",
    "  " + $Q + "version" + $Q + ": " + $Q + "0.0.0-stub" + $Q + ",",
    "  " + $Q + "type" + $Q + ": " + $Q + "module" + $Q + ",",
    "  " + $Q + "main" + $Q + ": " + $Q + "./index.ts" + $Q + ",",
    "  " + $Q + "exports" + $Q + ": {",
    "    " + $Q + "." + $Q + ": " + $Q + "./index.ts" + $Q + ",",
    "    " + $Q + "./types" + $Q + ": " + $Q + "./types.ts" + $Q + ",",
    "    " + $Q + "./sentinelApps" + $Q + ": " + $Q + "./sentinelApps.ts" + $Q,
    "  }",
    "}"
)

WriteFile "$d\index.ts" @(
    "export { DEFAULT_GRANT_FLAGS } from $Q./types.js$Q",
    "export type { CuPermissionRequest, CuPermissionResponse, ScreenshotDims, ComputerUseSessionContext, CuCallToolResult } from $Q./types.js$Q",
    "",
    "export const API_RESIZE_PARAMS = {}",
    "",
    "export function targetImageSize(width: number, height: number) {",
    "  return [width, height] as const",
    "}",
    "",
    "export function buildComputerUseTools() {",
    "  return [] as Array<{ name: string }>",
    "}",
    "",
    "export function bindSessionContext() {",
    "  return async () => ({",
    "    is_error: true,",
    "    content: [{ type: $Q`text$Q, text: $Q`Computer use is not supported on this platform.$Q }],",
    "  })",
    "}"
)

WriteFile "$d\types.ts" @(
    "export type CoordinateMode = $Q`pixels$Q | $Q`normalized$Q",
    "",
    "export type CuSubGates = {",
    "  pixelValidation?: boolean",
    "  clipboardPasteMultiline?: boolean",
    "  mouseAnimation?: boolean",
    "  hideBeforeAction?: boolean",
    "  autoTargetDisplay?: boolean",
    "  clipboardGuard?: boolean",
    "}",
    "",
    "export const DEFAULT_GRANT_FLAGS = {",
    "  accessibility: false,",
    "  screenRecording: false,",
    "}",
    "",
    "export type CuPermissionRequest = Record<string, unknown>",
    "export type CuPermissionResponse = {",
    "  granted: string[]",
    "  denied: string[]",
    "  flags: typeof DEFAULT_GRANT_FLAGS",
    "}",
    "",
    "export type ScreenshotDims = {",
    "  width: number",
    "  height: number",
    "  displayWidth?: number",
    "  displayHeight?: number",
    "  displayId?: number",
    "  originX?: number",
    "  originY?: number",
    "}",
    "",
    "export type CuCallToolResult = {",
    "  is_error?: boolean",
    "  content?: Array<{ type: string; text?: string }>",
    "  telemetry?: Record<string, unknown>",
    "}",
    "",
    "export type ComputerUseSessionContext = Record<string, unknown>"
)

WriteFile "$d\sentinelApps.ts" @(
    "export type SentinelCategory = $Q`shell$Q | $Q`filesystem$Q | $Q`system_settings$Q",
    "",
    "export function getSentinelCategory(_bundleId?: string): SentinelCategory | null {",
    "  return null",
    "}"
)

# ── 4. @ant/claude-for-chrome-mcp stub ──────────────────────
Write-Host "`n[4/6] stubs\ant-claude-for-chrome-mcp" -ForegroundColor Yellow
$d = Join-Path $Root "stubs\ant-claude-for-chrome-mcp"

WriteFile "$d\package.json" @(
    "{",
    "  " + $Q + "name" + $Q + ": " + $Q + "@ant/claude-for-chrome-mcp" + $Q + ",",
    "  " + $Q + "version" + $Q + ": " + $Q + "0.0.0-stub" + $Q + ",",
    "  " + $Q + "type" + $Q + ": " + $Q + "module" + $Q + ",",
    "  " + $Q + "main" + $Q + ": " + $Q + "./index.ts" + $Q,
    "}"
)

WriteFile "$d\index.ts" @(
    "export type PermissionMode = $Q`ask$Q | $Q`skip_all_permission_checks$Q | $Q`follow_a_plan$Q",
    "",
    "export type Logger = {",
    "  info(message: string): void",
    "  warn(message: string): void",
    "  error(message: string): void",
    "}",
    "",
    "export type ClaudeForChromeContext = { serverName?: string; logger?: Logger }",
    "",
    "export const BROWSER_TOOLS: Array<{ name: string }> = [",
    "  { name: $Q`javascript_tool$Q },",
    "  { name: $Q`read_page$Q },",
    "  { name: $Q`find$Q },",
    "  { name: $Q`form_input$Q },",
    "  { name: $Q`computer$Q },",
    "  { name: $Q`navigate$Q },",
    "  { name: $Q`resize_window$Q },",
    "  { name: $Q`gif_creator$Q },",
    "  { name: $Q`upload_image$Q },",
    "  { name: $Q`get_page_text$Q },",
    "  { name: $Q`tabs_context_mcp$Q },",
    "  { name: $Q`tabs_create_mcp$Q },",
    "  { name: $Q`update_plan$Q },",
    "  { name: $Q`read_console_messages$Q },",
    "  { name: $Q`read_network_requests$Q },",
    "  { name: $Q`shortcuts_list$Q },",
    "  { name: $Q`shortcuts_execute$Q },",
    "]",
    "",
    "export function createClaudeForChromeMcpServer(_context: ClaudeForChromeContext) {",
    "  return {",
    "    async connect() {},",
    "    setRequestHandler() {},",
    "    async close() {},",
    "  }",
    "}"
)

# ── 5. src/services/contextCollapse/ ────────────────────────
Write-Host "`n[5/6] src\services\contextCollapse" -ForegroundColor Yellow
$d = Join-Path $Root "src\services\contextCollapse"

WriteFile "$d\index.ts" @(
    "type Stats = {",
    "  collapsedSpans: number",
    "  stagedSpans: number",
    "  health: { totalErrors: number; totalEmptySpawns: number; emptySpawnWarningEmitted: boolean }",
    "}",
    "",
    "const stats: Stats = {",
    "  collapsedSpans: 0,",
    "  stagedSpans: 0,",
    "  health: { totalErrors: 0, totalEmptySpawns: 0, emptySpawnWarningEmitted: false },",
    "}",
    "",
    "const listeners = new Set<() => void>()",
    "",
    "export function initContextCollapse(): void {}",
    "",
    "export function subscribe(listener: () => void): () => void {",
    "  listeners.add(listener)",
    "  return () => listeners.delete(listener)",
    "}",
    "",
    "export function getStats(): Stats { return stats }",
    "export function isContextCollapseEnabled(): boolean { return false }",
    "export function resetContextCollapse(): void {}",
    "",
    "export async function applyCollapsesIfNeeded<T>(",
    "  messages: T,",
    "  _toolUseContext?: unknown,",
    "  _querySource?: unknown,",
    "): Promise<{ messages: T; changed: boolean }> {",
    "  return { messages, changed: false }",
    "}",
    "",
    "export function isWithheldPromptTooLong(",
    "  _message?: unknown,",
    "  _isPromptTooLong?: unknown,",
    "  _querySource?: unknown,",
    "): boolean { return false }",
    "",
    "export function recoverFromOverflow<T>(",
    "  messages: T,",
    "  _querySource?: unknown,",
    "): { messages: T; committed: number } {",
    "  return { messages, committed: 0 }",
    "}"
)

WriteFile "$d\persist.ts" @(
    "export function restoreFromEntries(",
    "  _commits?: unknown[],",
    "  _snapshot?: unknown,",
    "): void {}"
)

WriteFile "$d\operations.ts" @(
    "export function projectView<T>(messages: T): T { return messages }",
    "export function summarizeContextCollapseState(): null { return null }",
    "export function getContextCollapsePreview(): unknown[] { return [] }"
)

# ── 6. package.json ──────────────────────────────────────────
Write-Host "`n[6/6] package.json" -ForegroundColor Yellow
$pkgPath = Join-Path $Root "package.json"
$pkgContent = [System.IO.File]::ReadAllText($pkgPath, [System.Text.Encoding]::UTF8)
$needle = "@ant/computer-use-input"
$entry = "    " + $Q + "@ant/computer-use-input" + $Q + ": " + $Q + "file:./stubs/ant-computer-use-input" + $Q + ","

if ($pkgContent.IndexOf($needle) -lt 0) {
    $pkgContent = [regex]::Replace($pkgContent, '("dependencies"\s*:\s*\{)', '$1' + $nl + $entry)
    if ($pkgContent -match '"overrides"\s*:') {
        $pkgContent = [regex]::Replace($pkgContent, '("overrides"\s*:\s*\{)', '$1' + $nl + $entry)
    }
    [System.IO.File]::WriteAllText($pkgPath, $pkgContent, [System.Text.Encoding]::UTF8)
    Write-Host "  OK @ant/computer-use-input 已注册" -ForegroundColor Green
} else {
    Write-Host "  -> 已存在，跳过" -ForegroundColor Gray
}

# ── 完成 ─────────────────────────────────────────────────────
Write-Host "`n=== 全部修复完成！===" -ForegroundColor Cyan
Write-Host "下一步：" -ForegroundColor White
Write-Host "  bun install" -ForegroundColor Yellow
Write-Host "  bun run build.ts 2>&1 | Select-Object -First 50" -ForegroundColor Yellow
