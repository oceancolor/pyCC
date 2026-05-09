# Claude Code 混元模型接入 Patch

## 概述

让 Claude Code 支持混元大模型后端，通过设置环境变量即可切换。

## 文件清单

| 文件 | 操作 | 目标路径（相对项目根） |
|------|------|----------------------|
| `hunyuan.ts` | **新增** | `services/api/hunyuan.ts` |
| `providers.ts` | **覆盖** | `utils/model/providers.ts` |
| `client.ts` | **覆盖** | `services/api/client.ts` |

`auth.ts` 和 `model.ts` 改动较小，**手动编辑**（见下方）。

---

## 快速应用（Windows PowerShell）

```powershell
# 在项目根目录执行
$root = "."  # 改成你的 claude-code 项目根路径

# 1. 新增 hunyuan.ts
Copy-Item hunyuan.ts "$root/services/api/hunyuan.ts"

# 2. 覆盖 providers.ts
Copy-Item providers.ts "$root/utils/model/providers.ts"

# 3. 覆盖 client.ts
Copy-Item client.ts "$root/services/api/client.ts"
```

---

## 手动编辑：utils/auth.ts（2 处）

### 改动 1：`isAnthropicAuthEnabled()` 函数开头加一行

找到这个函数（搜索 `export function isAnthropicAuthEnabled`），在函数体第一行插入：

```typescript
export function isAnthropicAuthEnabled(): boolean {
  // 混元模式：不需要 Anthropic OAuth，直接返回 false 跳过所有登录检查
  if (process.env.HUNYUAN_API_KEY) return false   // ← 插入这两行

  // --bare: API-key-only, never OAuth.
  if (isBareMode()) return false
  // ...后续原有代码不变
```

### 改动 2：`getAnthropicApiKey()` 函数开头加一行

找到这个函数（搜索 `export function getAnthropicApiKey`），在函数体第一行插入：

```typescript
export function getAnthropicApiKey(): null | string {
  // 混元模式：返回混元 key，让调用方有 key 值可用（实际 API 调用不走这里）
  if (process.env.HUNYUAN_API_KEY) return process.env.HUNYUAN_API_KEY   // ← 插入这两行

  const { key } = getAnthropicApiKeyWithSource()
  // ...后续原有代码不变
```

---

## 手动编辑：utils/model/model.ts（3 处）

### 改动 1：顶部 import 区加一行

在 import 区域加入（放在其他 import 附近即可）：

```typescript
import { HUNYUAN_DEFAULT_MODEL, HUNYUAN_SMALL_MODEL } from '../../services/api/hunyuan.js'
```

### 改动 2：`getSmallFastModel()` 函数开头加一行

找到 `export function getSmallFastModel()`，在第一行插入：

```typescript
export function getSmallFastModel(): ModelName {
  // 混元模式：使用混元小模型
  if (process.env.HUNYUAN_API_KEY) return process.env.ANTHROPIC_SMALL_FAST_MODEL || HUNYUAN_SMALL_MODEL   // ← 插入

  return process.env.ANTHROPIC_SMALL_FAST_MODEL || getDefaultHaikuModel()
```

### 改动 3：`getDefaultSonnetModel()` 函数内加一行

找到 `export function getDefaultSonnetModel()`，在 `if (process.env.ANTHROPIC_DEFAULT_SONNET_MODEL)` 块之后插入：

```typescript
export function getDefaultSonnetModel(): ModelName {
  if (process.env.ANTHROPIC_DEFAULT_SONNET_MODEL) {
    return process.env.ANTHROPIC_DEFAULT_SONNET_MODEL
  }
  // 混元模式：使用混元主力模型
  if (process.env.HUNYUAN_API_KEY) return HUNYUAN_DEFAULT_MODEL   // ← 插入

  // Default to Sonnet 4.5 for 3P since they may not have 4.6 yet
  // ...后续原有代码不变
```

---

## 环境变量

设置以下环境变量启用混元模式：

```bash
HUNYUAN_API_KEY=你的混元API密钥          # 必填，设置后自动启用混元模式
HUNYUAN_MODEL=hunyuan-turbos-latest     # 可选，默认 hunyuan-turbos-latest
HUNYUAN_SMALL_MODEL=hunyuan-lite        # 可选，默认 hunyuan-lite
HUNYUAN_BASE_URL=https://api.hunyuan.cloud.tencent.com/v1  # 可选
```

Windows 设置方式：
```powershell
$env:HUNYUAN_API_KEY = "your_key_here"
```

---

## 构建 & 测试

```bash
# 安装依赖
bun install

# 构建
bun run build

# 启动（混元模式）
$env:HUNYUAN_API_KEY="your_key" ; claude
```

---

## 工作原理

```
用户输入 → Claude Code
    ↓
getAPIProvider()  →  检测 HUNYUAN_API_KEY  →  返回 'hunyuan'
    ↓
getAnthropicClient()  →  isHunyuanEnabled() = true
    ↓
createHunyuanClient()  →  返回伪 Anthropic 客户端
    ↓
beta.messages.create(Anthropic格式)
    ↓
convertMessages() + convertTools()  →  OpenAI 兼容格式
    ↓
fetch → api.hunyuan.cloud.tencent.com/v1/chat/completions
    ↓
openAIStreamToAnthropicEvents()  →  转回 Anthropic SSE 事件
    ↓
Claude Code 正常消费事件流
```

---

## 已知限制

- `thinking` 参数（Extended Thinking）被忽略，混元不支持
- 图片/文档 block 转换为 `[image]` / `[document]` 占位文本
- cost 统计基于字符数估算，非精确 token 计数
