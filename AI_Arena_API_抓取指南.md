# 🔍 AI Arena API 抓取实战指南

## 步骤详解

### 第一步：准备工作
1. 用 **Chrome** 或 **Edge** 浏览器访问 https://ai-arena.qq.com
2. **登录**你的账号
3. 按 **F12** 打开开发者工具
4. 点击 **Network（网络）** 标签
5. ✅ 勾选 **Preserve log**（保留日志）- 防止页面跳转时清空记录

### 第二步：过滤设置
在 Network 标签的过滤框中：
- 输入：`api` 或选择 `Fetch/XHR` 类型
- 这样只显示 API 请求

### 第三步：执行操作并抓包

**🎯 关键操作清单：**

| 操作 | 预期 API | 需记录的信息 |
|------|---------|------------|
| 1️⃣ 刷新页面（登录后） | 用户信息接口 | URL, Method, Headers |
| 2️⃣ 点击"迷宫游戏" | 游戏详情/赛季接口 | URL, Method, Response |
| 3️⃣ 查看排行榜 | 排行榜接口 | URL, Params, Response |
| 4️⃣ 查看自己的排名 | 个人统计接口 | URL, Response 结构 |
| 5️⃣ 查看对战记录 | 对战历史接口 | URL, Params |
| 6️⃣ 提交代码（如果有） | 代码提交接口 | URL, Method, Payload |

### 第四步：记录 API 详情

点击任一 API 请求后，右侧会显示详细信息：

#### ✅ 必须记录的内容：

**1. General（常规）**
```
Request URL: https://ai-arena.qq.com/api/xxx
Request Method: GET / POST
Status Code: 200
```

**2. Request Headers（请求头）**
```
重点关注：
- Authorization: XXX（认证方式）
- Cookie: XXX（Session）
- X-Csrf-Token: XXX（CSRF 保护）
- Content-Type: application/json
```

**3. Request Payload / Query Params**
```json
GET 请求：查看 Query String Parameters
POST 请求：查看 Request Payload

示例：
{
  "game_type": "maze",
  "season_id": "2024_q1",
  "page": 1,
  "limit": 50
}
```

**4. Response（响应）**
```json
记录响应的数据结构，示例：
{
  "code": 0,
  "message": "success",
  "data": {
    "rankings": [...],
    "total": 1234
  }
}
```

### 第五步：使用 Copy as cURL（最快方法！⚡）

**这是最简单的方法：**

1. 在 Network 面板中，右键点击任一 API 请求
2. 选择 **Copy** → **Copy as cURL (bash)**
3. 粘贴到文本编辑器或直接发给我

示例输出：
```bash
curl 'https://ai-arena.qq.com/api/leaderboard?game=maze&season=current' \
  -H 'authority: ai-arena.qq.com' \
  -H 'authorization: Bearer abc123...' \
  -H 'content-type: application/json' \
  --compressed
```

这样你就得到了：
- ✅ 完整的 URL
- ✅ 所有请求头
- ✅ 认证方式

### 第六步：整理成文档

创建一个文档，格式如下：

```markdown
## API 1: 获取用户信息
- URL: GET /api/user/profile
- Headers: 
  - Authorization: Bearer {token}
- Response:
  {
    "username": "xxx",
    "avatar": "..."
  }

## API 2: 获取排行榜
- URL: GET /api/leaderboard
- Params:
  - game: maze/soccer/starcraft
  - season: current
  - limit: 50
- Response:
  {
    "rankings": [...]
  }
```

---

## 🎯 快捷技巧

### 技巧 1：导出全部请求（推荐！）
- 在 Network 面板中右键
- 选择 **Save all as HAR with content**
- 保存为 `.har` 文件（包含所有请求的完整信息）
- 用文本编辑器打开即可查看 JSON 格式的所有请求
- **直接把 HAR 文件发给我，我来帮你解析！**

### 技巧 2：使用浏览器扩展
安装 **Postman Interceptor** 或 **HTTP Toolkit**：
- 自动捕获所有请求
- 直接导入到 Postman 进行测试

### 技巧 3：查看 WebSocket（如果有实时功能）
- 在 Network 中筛选 `WS` 类型
- 查看实时通信的消息格式

---

## 📤 如何给我提供抓取结果

完成后，选择以下任一方式：

### 方式 1：最简单（推荐）
把操作过程中的 **3-5 个核心 API 的 cURL 命令** 发给我：
1. 右键 API 请求 → Copy as cURL
2. 粘贴到聊天框
3. 同时复制对应的 **Response** 内容

### 方式 2：最完整
导出 **HAR 文件**并发送给我：
- Network 面板右键 → Save all as HAR with content
- 把 `.har` 文件通过企业微信发给我

### 方式 3：手动整理
按照"第六步"的格式，整理成 Markdown 文档发给我

---

## 我会帮你完成的工作

收到你的抓包结果后，我会：

1. ✅ 解析 API 结构和认证方式
2. ✅ 更新 `ai_arena_api.py` 中的所有端点
3. ✅ 调整请求/响应的数据结构
4. ✅ 测试 API 调用是否正常
5. ✅ 重新打包 skill，让它真正可用！

---

## ⚠️ 注意事项

- **隐私保护**：不要分享完整的 Token（可以用 `xxx...` 代替中间部分）
- **Cookie 处理**：如果 API 需要 Cookie 认证，记得记录
- **CSRF Token**：有些网站需要 CSRF Token，在请求头中查找

---

## 📸 截图示例

如果你不确定操作是否正确，可以截图 Network 面板发给我，我来指导！

**关键位置：**
- Network 标签页
- 过滤框（输入 `api`）
- 请求列表（左侧）
- 请求详情（右侧）

---

## ❓ 常见问题

**Q: 找不到 API 请求？**
A: 确保勾选了 "Preserve log" 并刷新页面

**Q: API 请求太多怎么办？**
A: 只记录与游戏相关的 API（忽略统计、埋点类请求）

**Q: 响应是乱码怎么办？**
A: 点击 Response 标签，如果是 gzip 压缩的，浏览器会自动解压显示

---

准备好了吗？🚀

**现在就去操作吧！完成后把结果发给我，我会立即帮你更新 skill！**
