# 中控 API v1

默认服务前缀 `http://127.0.0.1:8200`。输入和输出均为 JSON。金额、价格、数量输出为十进制字符串，时间为 UTC RFC 3339。非 GET 请求使用 `Content-Type: application/json`，最大请求体 256 KiB。

配置 `MO_API_TOKEN` 后，操作请求携带 `Authorization: Bearer <MO_API_TOKEN>`。AI 使用不同的 `MO_AI_READ_TOKEN`，只允许查询报价、账户快照和只读估值分析报告。业务后端负责根据登录会话映射 `user_id`，格式为 1–64 个 ASCII 字母、数字、下划线或连字符。

| 方法及路径 | 作用 |
| --- | --- |
| GET `/health` | 服务状态和模拟模式 |
| POST `/api/accounts/{user_id}` | 一次性创建虚构账户、资金及初始模拟持仓，重复创建返回 409 |
| GET / PUT `/api/accounts/{user_id}/preferences` | 查询或更新自选与价格提醒 |
| GET / PUT `/api/accounts/{user_id}/assessment` | 查询或更新问卷端已计算的派生测评 |
| POST `/api/quotes` | 批量接收行情并驱动挂单成交及风险监测 |
| GET `/api/quotes?q=BTC%2FUSDT&limit=5` | AI 兼容的行情查询，一交易对返回一个估值来源 |
| GET `/api/quotes?q=BTC&all_sources=true&limit=50` | 查询各来源报价及新鲜度 |
| GET `/api/comparison?symbol=BTC%2FUSDT&quantity=0.01&side=buy` | 同一交易对的多平台模拟成本比较 |
| POST / GET `/api/accounts/{user_id}/orders` | 提交或查询订单，GET 可用 `?status=open` |
| POST `/api/accounts/{user_id}/orders/{order_id}/cancel` | 撤销未成交订单，发送 `{}` |
| GET `/api/accounts/{user_id}/snapshot` | AI 兼容的持仓及挂单快照 |
| GET `/api/accounts/{user_id}/analysis_snapshot` | 同次读取账户、官方估值、风险指标及实际报价依据，含快照编号 |
| GET `/api/accounts/{user_id}/portfolio` | 成本、市值、盈亏、资金预留和累计费用 |
| GET `/api/accounts/{user_id}/trades?offset=0&limit=100` | 成交流水，limit 最大 500 |
| GET `/api/accounts/{user_id}/alerts` | 查询价格、持仓风险及 AML 告警，同时重新检查当前风险 |
| POST `/api/accounts/{user_id}/alerts/{alert_id}/review` | 人工记录处理结论 |
| GET `/api/accounts/{user_id}/audit?offset=0&limit=100` | 操作和状态变化记录 |

## 创建账户

```json
{
  "valuation_currency": "USDT",
  "initial_balances": {"USDT": "10000"},
  "initial_positions": [],
  "limits": {
    "max_order_notional": "100000",
    "concentration_pct": "60",
    "loss_pct": "10",
    "aml_large_trade": "10000",
    "aml_frequency": 5,
    "aml_window_seconds": 60
  }
}
```

初始资金只使用账户的计价币。已有币种用 `initial_positions` 录入，例如 `{"symbol":"BTC/USDT","quantity":"0.1","average_cost":"60000"}`。这是创建虚构账户时的一次性初始资产，后续交易通过订单更新。

## 账户偏好

```json
{
  "watchlist": ["BTC/USDT", "USDC/USDT"],
  "price_alerts": [{"symbol":"BTC/USDT","direction":"above","price":"70000"}]
}
```

`direction` 为 `above` 或 `below`，比较含等号。持续命中的规则只产生一条活跃告警，恢复后再次命中可重新告警。

## 问卷测评

```json
{
  "questionnaire_version": "1.0.0",
  "source": "questionnaire",
  "assessment": {
    "dimensions": {"FC":62,"RA":65,"KE":75,"BD":60,"OC":55},
    "rai":63,
    "risk_level":"C3",
    "product_cap":"R3",
    "allocation_range":{"min_pct":5,"max_pct":15},
    "flags":["short_horizon"],
    "prohibitions":[]
  }
}
```

中控验证字段及 RAI、C/R 档位和财务承受能力上限的一致性，保存派生结果。问卷组负责逐题计分和计算 RAI。原始问题与答案不进入中控画像。GET 的结果可直接 PUT 到 AI 的 `/v1/profiles/{user_id}`。`dimensions.wealth_band` 可选值为 low、medium、high。

## 行情输入

```json
{
  "quotes": [
    {"symbol":"BTC/USDT","price":"68000","bid":"67999","ask":"68001",
     "source":"demo_hashkey","as_of":"2026-11-19T06:00:00Z","fee_rate":"0.001",
     "name":"Bitcoin","aliases":["比特币","大饼"]}
  ]
}
```

演示请填写当前采集时间。`symbol`、`price`、`source`、`as_of` 必填。`bid` 和 `ask` 省略时取 price，`fee_rate` 省略时为零，含义均为模拟参数。批量数据先全部校验再写入。每个交易对和来源只接受时间更晚的报价。超过未来 15 秒的时间拒收，默认超过 120 秒失效。BTC/USD 与 BTC/USDT 独立处理。

查询返回 `{ "quotes": [...] }`。未知查询返回空数组。AI 的查询按交易对合并来源，优先选新鲜报价，再选较新时间，最后用来源名称稳定排序。跨平台比较使用 `/api/comparison` 或 `all_sources=true`，保留各来源。

公开模式返回 `market_mode: "public"` 和 `ranking_basis: "bid_ask_excluding_fees"`。`bid_size`、`ask_size` 是最优档基础币数量，`quantity_covered` 表示该档能否覆盖请求数量，`timestamp_source` 区分交易所字段和采集时间。费率为空时 `fee`、`total` 为空，`notional` 是未计费的报价金额。超过保鲜期的来源出现在 `excluded_sources`，尚无可用记录的出处出现在 `missing_sources`。

## 模拟订单

```json
{"request_id":"buy_001","symbol":"BTC/USDT","side":"buy","quantity":"0.01","order_type":"market"}
```

```json
{"request_id":"limit_001","symbol":"BTC/USDT","side":"sell","quantity":"0.005","order_type":"limit","limit_price":"70000","source":"demo_hashkey"}
```

`request_id` 是该用户范围内的请求去重键。同一业务请求重试需保持原键和内容，成功重试返回同一订单。相同键对应不同内容返回 409。`source` 可选，省略时按当时有效报价及费用选择模拟平台，接受后固定来源和费用率。

订单返回 `order_id`、`status`、`reason` 及相关字段。状态为 `open`、`filled`、`rejected`、`cancelled`。业务风控拒绝返回 HTTP 200 和 `status: rejected`，前端必须检查该状态。参数格式错误返回 HTTP 400。

未达到限价的订单为 `open`。买单预留资金，卖单预留数量。行情 POST 或轮询可触发成交。成交后返回唯一 `trade_id`，同笔成交只更新账本一次。已成交／拒绝订单不能撤销，返回 409。重复撤销已撤单返回同一最终状态。

## AI 账户快照

```json
{
  "as_of":"2026-11-19T06:00:00.000000Z",
  "positions":[{"symbol":"BTC","quantity":"0.01"},{"symbol":"USDT","quantity":"9319.99"}],
  "open_orders":[{"order_id":"ord_...","symbol":"BTC/USDT","side":"sell",
                  "quantity":"0.005","limit_price":"70000","status":"open"}],
  "truncated":false
}
```

`positions` 为资产总数量，包含已被挂单预留的数量。持仓和现金按资产合并，避免重复计数。AI 快照最多各 50 行，超过时 `truncated: true`。已确认空账户返回两个空数组，未知账户返回 404。

完整的 `portfolio` 提供 `balances.total/reserved/available` 及持仓成本和盈亏。报价缺失或过期时返回 `state: partial`，对应估值和完整账户总资产为 null，保留缺失原因。GET 快照的 `as_of` 是读取账本时刻，估值价格的时间保留在 portfolio 各持仓中。

## AI 与前端共享数字

`GET /api/accounts/{user_id}/analysis_snapshot` 在一次读取事务及同一个估值时刻生成 `account`、`portfolio`、`risk`、`basis` 和 `snapshot_id`。`portfolio.valuation_quotes` 保留实际使用的报价，持仓行新增 `market_price` 字段。AI 只读凭证可以读取此报告，但仍不能单独读取 `/portfolio` 或内部告警。

两端需共享同一份返回内容及快照编号，并直接使用 `portfolio` 的官方数值；两端分别请求最新报告不保证版本相同。原 `/snapshot` 格式不变，他现有的读取代码不会自动采用新接口。详见 [一致性说明与 Python 代码](AI_NUMBER_CONSISTENCY.md)。

## 告警与人工复核

```json
{"reviewer":"operator_001","decision":"closed","note":"Reviewed against the simulated trade records"}
```

`decision` 为 `closed` 或 `escalated`。结论保留操作人、时间和理由，首次复核后相同内容可重试，不同内容返回 409。AML 告警表示规则命中待复核。

## 错误结构

```json
{"error":{"code":"account_not_found","message":"account does not exist"}}
```

主要状态码为参数错误 400、凭证错误 401、只读凭证越权 403、资源不存在 404、业务状态冲突 409、体积超限 413、JSON 类型要求 415、存储暂不可用 503。
