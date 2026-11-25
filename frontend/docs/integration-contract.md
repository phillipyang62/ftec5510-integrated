# 三模块接口与合并约定

本文件是前端、AI 后端、中台/交易服务之间的共享契约。接口字段或职责发生变化时，必须在同一个 PR 中修改本文件，并让至少一名组员 review。

## 1. 服务边界

| 模块 | 职责 | 当前/建议入口 |
| --- | --- | --- |
| 前端 | 页面、交互、加载/错误状态、同源 API 调用 | `http://127.0.0.1:5510` |
| BFF/业务后端 | 会话、鉴权、同源代理、字段适配 | `http://127.0.0.1:5510/api/*` |
| AI 后端 | 画像、对话、风险、行情解释 | `http://127.0.0.1:8000/v1/*` |
| 中台/行情/交易 | 平台报价、账户、订单预览、下单 | 由中台负责人确定 |

浏览器不得直接访问 AI 后端或中台服务，也不得持有服务 Token。

## 2. 浏览器与 BFF

### 本机演示账户

- `POST /api/session` 接收 `{"account_name":"student_demo"}`。名称去除首尾空白后必须为 1–64 个英文字母、数字、下划线或连字符，区分大小写。若账户不存在则创建模拟账本；返回当前 `account_name` 并设置有效期 8 小时的 `HttpOnly; SameSite=Strict` 会话 Cookie。
- `GET /api/session` 返回当前 `account_name`（未登录时为 `null`）；`DELETE /api/session` 使当前会话失效并清除 Cookie。除健康检查和会话路由外，BFF 依据会话选择账户，未登录返回 `401`。
- 页面发送 `X-Harbor-Account` 仅检测其他标签页是否已切换账户；该字段不能授予访问权限。此流程是本机模拟账户选择，不验证账号所有权，也不应对公网开放。

### 服务状态

```http
GET /api/health
```

转发到：

```http
GET http://127.0.0.1:8000/health
```

### 画像

```http
GET /api/profile
PUT /api/profile
```

BFF 从登录会话得到 `user_id`，再转发到：

```text
GET /v1/profiles/{user_id}
PUT /v1/profiles/{user_id}
```

前端请求体不包含可任意伪造的 `user_id`。

### 对应投教

`GET /api/education` 由 BFF 按登录会话转发到 AI 的 `GET /v1/education/{user_id}`。返回中英文 `title`、`content`，以及可选的 `focus`（维度名称和分数）。有杠杆提示时优先展示杠杆风险，待复核时展示测评复核，基础投教展示订单类型，其他情况取当前画像最低分维度。接口按规则选课，不调用生成模型，未完成问卷时返回 `404 assessment_required`。

### AI 对话

```http
POST /api/assistant/chat
```

请求：

```json
{
  "message": "比特币现在多少钱？",
  "market_queries": ["BTC/USDT"],
  "include_account": false,
  "include_simulation": false,
  "history": []
}
```

BFF 补充会话用户并转发：

```json
{
  "user_id": "student_001",
  "message": "比特币现在多少钱？",
  "market_queries": ["BTC/USDT"],
  "include_account": false,
  "include_simulation": false,
  "history": []
}
```

前端显示的字段至少包括：

```text
reply
generation
mode
risk_ceiling
product_cap
market
account
simulation
trace_id
```

生成模型成功时还返回 `model_name`。前端按 `generation` 显示实际用到的模型或内置回复。

### 模型设置

- `GET /api/model-settings` 返回 `ollama.models`、`remote_providers`、启动时配置和当前会话的 `settings`（`provider`、`model`、`has_api_key`）。`remote_providers` 按平台 ID 返回 `name` 和默认 `model`。
- `PUT /api/model-settings` 接收 `{"provider":"default"}`、`{"provider":"ollama","model":"qwen3.5:9b-q4_K_M"}`，或 `{"provider":"openai","api_key":"<用户填写>","allow_billing":true}`。API 平台 ID 为 `deepseek`、`openai`、`gemini`。同一会话、同一平台可留空以沿用当前 Key，换平台须填该平台的 Key。成功时返回脱敏的设置。
- BFF 使用服务令牌调用 `GET/PUT /v1/model-settings` 查询目录和校验配置。Key 只驻留当前 BFF 会话内存。AI 服务通过本机 HTTP 或 HTTPS 接收 Key，并按平台固定使用官方 API。只有聊天生成才向所选平台发请求，返回的模型设置不包含 Key。
- BFF 给 `POST /v1/chat` 附加本次登录的 `model_settings`，忽略浏览器自行提交的同名字段。涉及账户上下文时绕过远程生成。会话注销、过期或切换时需要重新配置。

### 风险

```http
GET /api/risk?quote_currency=USDT
```

转发到：

```http
GET /v1/risk/{user_id}?quote_currency=USDT
```

结果必须区分 `ok`、`partial`、`unavailable` 和 `not_configured`。

## 3. 行情边界

`GET /api/market/catalog` 由 BFF 转发给中台，返回 `market_mode` 和 `pairs`。`pairs` 的键是交易对，值是已配置的报价来源数组，例如 `{"BTC/USD":["HashKey","OSL"]}`。前端使用目录生成币种和计价币选项。报价及可用状态仍以 `GET /api/market/venues` 中返回的具体交易对为准。离线模式沿用模拟交易对。

AI 后端的 `/v1/market/quotes` 是单交易对参考价：

```json
{
  "symbol": "BTC/USDT",
  "price": "68000.50",
  "as_of": "2026-11-19T10:00:00+08:00",
  "source": "example_exchange",
  "name": "Bitcoin",
  "aliases": ["比特币"]
}
```

它不能代替跨平台双边报价。比价大屏需要：

```http
GET /api/market/venues?symbol=BTC%2FUSDT&quantity=0.5&side=buy
```

```json
{
  "symbol": "BTC/USDT",
  "quantity": "0.5",
  "side": "buy",
  "as_of": "2026-11-19T10:00:00+08:00",
  "venues": [
    {
      "venue": "HashKey",
      "bid": "68420.10",
      "ask": "68468.80",
      "fee_rate": "0.0020",
      "estimated_slippage_rate": "0.0003",
      "estimated_total_cost": "34304.85",
      "available": true
    }
  ]
}
```

如果未来 AI 后端要支持多平台报价，内部行情键必须从单一 `symbol` 扩展为 `(venue, symbol)`；否则同一交易对来自不同平台时会互相覆盖。

## 4. 订单边界

### 订单预览

模拟订单预览和提交可选返回 `suitability_warning`，字段为 `code`、`risk_level`、`product_cap`、`product_risk`。前端在确认按钮前展示提醒。预览成功后仍可确认提交。

```http
POST /api/orders/preview
```

```json
{
  "symbol": "BTC/USDT",
  "side": "buy",
  "quantity": "0.50",
  "venue": "HashKey",
  "order_type": "limit",
  "limit_price": "68420.10"
}
```

响应至少包含：

```text
preview_id
executable_price
fee
estimated_slippage
total_debit
currency
risk_check
expires_at
```

### 提交订单

```http
POST /api/orders
Idempotency-Key: <client-generated-key>
```

```json
{
  "preview_id": "preview_123",
  "confirm": true
}
```

后端必须重新校验余额、身份、产品适当性和风控。前端不得绕过 preview 直接提交。

### 订单状态

```http
GET /api/orders/{order_id}
```

AI 后端当前没有订单预览、创建、撤销或成交接口；这些能力必须由中台/交易服务提供。

## 5. 账户与自选

建议接口：

```text
GET    /api/account/summary
GET    /api/account/performance?period=3M
GET    /api/account/transactions?limit=20
GET    /api/watchlist
POST   /api/watchlist
DELETE /api/watchlist/{symbol}
```

账户金额必须包含币种和时间戳。空账户与接口不可用必须是不同状态。

## 6. 错误格式

所有 BFF 错误统一为：

```json
{
  "error": {
    "code": "market_unavailable",
    "message": "行情服务暂时不可用"
  }
}
```

建议错误码：

```text
invalid_request
unauthorized
profile_not_found
market_unavailable
quote_stale
risk_rejected
insufficient_balance
order_confirm_required
order_expired
upstream_timeout
```

前端不得根据 HTTP 200 就默认业务成功，应同时检查 `state`、`status` 或 `error`。

## 7. 合并三个仓库

汇总仓库建议结构：

```text
5510-team/
├─ CLAUDE.md
├─ README.md
├─ docs/
│  ├─ integration-contract.md
│  └─ runbook.md
├─ frontend/
├─ ai-backend/
└─ middle-office/
```

跨仓库保留自己的运行入口、README 和测试；根目录只增加总览和启动说明。

### 合并顺序

1. 先合并 `CLAUDE.md` 和接口契约；
2. 再合并目录结构互不冲突的三个模块；
3. 分别运行各模块测试；
4. 启动 AI 后端和中台；
5. 启动 BFF 和前端；
6. 按“health -> profile -> quote -> chat -> risk -> order preview”顺序联调；
7. 输出一份真实运行记录，明确哪些接口和状态已验证。

### 禁止事项

- 不把 `.env`、Token、SQLite 数据库或用户数据提交；
- 不用一个模块的 README 覆盖其他模块；
- 不在合并过程中顺便重写 UI 或业务逻辑；
- 不把“前端能打开”当作端到端联调成功；
- 不在未验证的情况下声称真实行情、账户或下单已经接通。

## 8. 端到端验收

- [ ] `python UI.py` 可以在 5510 启动；
- [ ] AI 后端可以启动并通过自身测试；
- [ ] `GET /api/health` 成功；
- [ ] 画像可以写入和读取；
- [ ] 聊天能显示真实 `reply` 和错误；
- [ ] 跨平台报价能显示来源和时间；
- [ ] 风险结果区分完整、部分、不可用；
- [ ] 订单预览成功后提交按钮才可用；
- [ ] 重复点击不会重复下单；
- [ ] 浏览器源码和网络请求中不存在服务 Token；
- [ ] README 记录的启动命令与实际一致。
