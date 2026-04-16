# setup-claude-code-build.ps1
# Usage: powershell -ExecutionPolicy Bypass -File ".\setup-claude-code-build.ps1"

$ROOT = "F:\Claude code src"
$SRC  = "$ROOT\src"

Write-Host ""
Write-Host "=== Claude Code Build Setup ===" -ForegroundColor Cyan
Write-Host "Root: $ROOT"

# Check src\ exists
if (-not (Test-Path $SRC)) {
    Write-Host "[ERROR] Cannot find $SRC" -ForegroundColor Red
    exit 1
}

# Step 1: Move package.json from src\ to root
$pkgInSrc  = "$SRC\package.json"
$pkgInRoot = "$ROOT\package.json"

if (Test-Path $pkgInSrc) {
    if (Test-Path $pkgInRoot) {
        Write-Host "[SKIP] $pkgInRoot already exists"
    } else {
        Move-Item $pkgInSrc $pkgInRoot
        Write-Host "[OK] Moved package.json to root" -ForegroundColor Green
    }
} elseif (Test-Path $pkgInRoot) {
    Write-Host "[OK] package.json already at root"
} else {
    Write-Host "[WARN] package.json not found" -ForegroundColor Yellow
}

# Step 2: Create scripts\ directory
$scriptsDir = "$ROOT\scripts"
if (-not (Test-Path $scriptsDir)) {
    New-Item -ItemType Directory -Path $scriptsDir | Out-Null
    Write-Host "[OK] Created scripts\" -ForegroundColor Green
}

# Step 3: scripts\defines.ts
$definesPath = "$scriptsDir\defines.ts"
if (-not (Test-Path $definesPath)) {
    $definesContent = @'
export function getMacroDefines(): Record<string, string> {
    return {
        "MACRO.VERSION": JSON.stringify("2.1.888"),
        "MACRO.BUILD_TIME": JSON.stringify(new Date().toISOString()),
        "MACRO.FEEDBACK_CHANNEL": JSON.stringify(""),
        "MACRO.ISSUES_EXPLAINER": JSON.stringify(""),
        "MACRO.NATIVE_PACKAGE_URL": JSON.stringify(""),
        "MACRO.PACKAGE_URL": JSON.stringify(""),
        "MACRO.VERSION_CHANGELOG": JSON.stringify(""),
    };
}
'@
    [System.IO.File]::WriteAllText($definesPath, $definesContent, [System.Text.Encoding]::UTF8)
    Write-Host "[OK] Created scripts\defines.ts" -ForegroundColor Green
} else {
    Write-Host "[SKIP] scripts\defines.ts exists"
}

# Step 4: scripts\dev.ts
$devPath = "$scriptsDir\dev.ts"
if (-not (Test-Path $devPath)) {
    $devContent = @'
#!/usr/bin/env bun
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { getMacroDefines } from "./defines.ts";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const projectRoot = join(__dirname, "..");
const cliPath = join(projectRoot, "src/entrypoints/cli.tsx");

const defines = getMacroDefines();
const defineArgs = Object.entries(defines).flatMap(([k, v]) => ["-d", `${k}:${v}`]);

const DEFAULT_FEATURES = [
  "BUDDY", "TRANSCRIPT_CLASSIFIER", "BRIDGE_MODE",
  "AGENT_TRIGGERS_REMOTE", "CHICAGO_MCP", "VOICE_MODE",
  "SHOT_STATS", "PROMPT_CACHE_BREAK_DETECTION", "TOKEN_BUDGET",
  "AGENT_TRIGGERS", "ULTRATHINK", "BUILTIN_EXPLORE_PLAN_AGENTS", "LODESTONE",
  "EXTRACT_MEMORIES", "VERIFICATION_AGENT", "KAIROS_BRIEF", "AWAY_SUMMARY", "ULTRAPLAN",
  "DAEMON",
];

const envFeatures = Object.entries(process.env)
    .filter(([k]) => k.startsWith("FEATURE_"))
    .map(([k]) => k.replace("FEATURE_", ""));

const allFeatures = [...new Set([...DEFAULT_FEATURES, ...envFeatures])];
const featureArgs = allFeatures.flatMap((name) => ["--feature", name]);

const inspectArgs = process.env.BUN_INSPECT
    ? ["--inspect-wait=" + process.env.BUN_INSPECT]
    : [];

const result = Bun.spawnSync(
    ["bun", ...inspectArgs, "run", ...defineArgs, ...featureArgs, cliPath, ...process.argv.slice(2)],
    { stdio: ["inherit", "inherit", "inherit"], cwd: projectRoot },
);

process.exit(result.exitCode ?? 0);
'@
    [System.IO.File]::WriteAllText($devPath, $devContent, [System.Text.Encoding]::UTF8)
    Write-Host "[OK] Created scripts\dev.ts" -ForegroundColor Green
} else {
    Write-Host "[SKIP] scripts\dev.ts exists"
}

# Step 5: scripts\dev-debug.ts
$devDebugPath = "$scriptsDir\dev-debug.ts"
if (-not (Test-Path $devDebugPath)) {
    $devDebugContent = @'
#!/usr/bin/env bun
process.env.BUN_INSPECT = process.env.BUN_INSPECT ?? "ws://localhost:8888"
import "./dev.ts"
'@
    [System.IO.File]::WriteAllText($devDebugPath, $devDebugContent, [System.Text.Encoding]::UTF8)
    Write-Host "[OK] Created scripts\dev-debug.ts" -ForegroundColor Green
}

# Step 6: build.ts
$buildPath = "$ROOT\build.ts"
if (-not (Test-Path $buildPath)) {
    $buildContent = @'
import { readdir, readFile, writeFile, cp } from 'fs/promises'
import { join } from 'path'
import { getMacroDefines } from './scripts/defines.ts'

const outdir = 'dist'

const { rmSync } = await import('fs')
rmSync(outdir, { recursive: true, force: true })

const DEFAULT_BUILD_FEATURES = [
  'AGENT_TRIGGERS_REMOTE',
  'CHICAGO_MCP',
  'VOICE_MODE',
  'SHOT_STATS',
  'PROMPT_CACHE_BREAK_DETECTION',
  'TOKEN_BUDGET',
  'AGENT_TRIGGERS',
  'ULTRATHINK',
  'BUILTIN_EXPLORE_PLAN_AGENTS',
  'LODESTONE',
  'EXTRACT_MEMORIES',
  'VERIFICATION_AGENT',
  'KAIROS_BRIEF',
  'AWAY_SUMMARY',
  'ULTRAPLAN',
  'DAEMON',
]

const envFeatures = Object.keys(process.env)
  .filter(k => k.startsWith('FEATURE_'))
  .map(k => k.replace('FEATURE_', ''))
const features = [...new Set([...DEFAULT_BUILD_FEATURES, ...envFeatures])]

const result = await Bun.build({
  entrypoints: ['src/entrypoints/cli.tsx'],
  outdir,
  target: 'bun',
  splitting: true,
  define: getMacroDefines(),
  features,
})

if (!result.success) {
  console.error('Build failed:')
  for (const log of result.logs) {
    console.error(log)
  }
  process.exit(1)
}

const files = await readdir(outdir)
const IMPORT_META_REQUIRE = 'var __require = import.meta.require;'
const COMPAT_REQUIRE = `var __require = typeof import.meta.require === "function" ? import.meta.require : (await import("module")).createRequire(import.meta.url);`

let patched = 0
for (const file of files) {
  if (!file.endsWith('.js')) continue
  const filePath = join(outdir, file)
  const content = await readFile(filePath, 'utf-8')
  if (content.includes(IMPORT_META_REQUIRE)) {
    await writeFile(filePath, content.replace(IMPORT_META_REQUIRE, COMPAT_REQUIRE))
    patched++
  }
}

console.log(`Bundled ${result.outputs.length} files to ${outdir}/ (patched ${patched} for Node.js compat)`)

try {
  const vendorDir = join(outdir, 'vendor', 'audio-capture')
  await cp('vendor/audio-capture', vendorDir, { recursive: true })
  console.log(`Copied vendor/audio-capture/ -> ${vendorDir}/`)
} catch {
  // vendor/audio-capture may not exist on Windows
}

const rgScript = await Bun.build({
  entrypoints: ['scripts/download-ripgrep.ts'],
  outdir,
  target: 'node',
})
if (!rgScript.success) {
  console.error('Failed to bundle download-ripgrep script (non-fatal)')
} else {
  console.log(`Bundled download-ripgrep script to ${outdir}/`)
}
'@
    [System.IO.File]::WriteAllText($buildPath, $buildContent, [System.Text.Encoding]::UTF8)
    Write-Host "[OK] Created build.ts" -ForegroundColor Green
} else {
    Write-Host "[SKIP] build.ts exists"
}

# Step 7: tsconfig.json
$tsconfigPath = "$ROOT\tsconfig.json"
if (-not (Test-Path $tsconfigPath)) {
    $tsconfigContent = @'
{
    "compilerOptions": {
        "target": "ESNext",
        "module": "ESNext",
        "moduleResolution": "bundler",
        "jsx": "react-jsx",
        "strict": false,
        "skipLibCheck": true,
        "noEmit": true,
        "esModuleInterop": true,
        "allowSyntheticDefaultImports": true,
        "resolveJsonModule": true,
        "types": ["bun"],
        "paths": {
            "src/*": ["./src/*"]
        }
    },
    "include": ["src/**/*.ts", "src/**/*.tsx"],
    "exclude": ["node_modules"]
}
'@
    [System.IO.File]::WriteAllText($tsconfigPath, $tsconfigContent, [System.Text.Encoding]::UTF8)
    Write-Host "[OK] Created tsconfig.json" -ForegroundColor Green
} else {
    Write-Host "[SKIP] tsconfig.json exists"
}

# Step 8: Patch package.json - remove workspace:* deps and workspaces field
Write-Host ""
Write-Host "=== Patching package.json ===" -ForegroundColor Cyan

$pkgRaw = Get-Content $pkgInRoot -Raw
$pkg = $pkgRaw | ConvertFrom-Json

$workspaceDeps = @(
    "@ant/claude-for-chrome-mcp",
    "@ant/computer-use-input",
    "@ant/computer-use-mcp",
    "@ant/computer-use-swift",
    "audio-capture-napi",
    "color-diff-napi",
    "image-processor-napi",
    "modifiers-napi",
    "url-handler-napi"
)

$modified = $false
foreach ($dep in $workspaceDeps) {
    if ($pkg.devDependencies.PSObject.Properties[$dep]) {
        $pkg.devDependencies.PSObject.Properties.Remove($dep)
        Write-Host "[PATCH] Removed workspace dep: $dep" -ForegroundColor Yellow
        $modified = $true
    }
}

if ($pkg.PSObject.Properties["workspaces"]) {
    $pkg.PSObject.Properties.Remove("workspaces")
    Write-Host "[PATCH] Removed workspaces field" -ForegroundColor Yellow
    $modified = $true
}

if ($modified) {
    $newJson = $pkg | ConvertTo-Json -Depth 10
    [System.IO.File]::WriteAllText($pkgInRoot, $newJson, [System.Text.Encoding]::UTF8)
    Write-Host "[OK] package.json updated" -ForegroundColor Green
} else {
    Write-Host "[OK] package.json no changes needed"
}

# Done
Write-Host ""
Write-Host "=== Setup complete! Now run: ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "  cd `"F:\Claude code src`""
Write-Host "  bun install"
Write-Host "  bun run build"
Write-Host ""
Write-Host "If ripgrep download is slow, set this first:"
Write-Host '  $env:RIPGREP_DOWNLOAD_BASE = "https://ghproxy.net/https://github.com/microsoft/ripgrep-prebuilt/releases/download/v15.0.1"'
Write-Host ""
