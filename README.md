# Harbor Invest · FTEC5510

前端、中台和 AI 助手共用仓库。各模块原有的入口和文档都保留在各自目录。

| 模块 | 目录 | 导入版本 |
| --- | --- | --- |
| 前端 | [`frontend/`](frontend/) | [LeoLIU1233/5510-UI `6366904`](https://github.com/LeoLIU1233/5510-UI/tree/63669046ecabf3415b2e7e43efd964ffbddd2024) |
| 中台 | [`middle-office/`](middle-office/) | [ALLE77-maker/ftec5510-middle-office `0414afc`](https://github.com/ALLE77-maker/ftec5510-middle-office/tree/0414afc5e6aada231c4def932a2de394d7469b3c) |
| AI 助手 | [`ai/`](ai/) | [phillipyang62/crypto-ai-mvp `bcfd222`](https://github.com/phillipyang62/crypto-ai-mvp/tree/bcfd2220e3c3ab1f47deb983fb3869fa692542f3) |

## 一键启动

需要 Python 3.10 或更高版本，无需安装第三方 Python 依赖。

```shell
python run_demo.py --live-market
python -X utf8 check_integration.py --live-market
```

第一条命令启动三个 HTTP 服务。打开终端打印的本机网址，通常为 `http://127.0.0.1:5510/`。初次进入会显示风险问卷，可以稍后填写。`--live-market` 读取真实现货报价，账户和订单仍在本地模拟。省略该参数即可离线演示，使用两家模拟报价来源。退出演示会清理临时数据库。第二条命令独立复测离线流程及公开行情。

模型默认用模板。用 `python run_demo.py --ollama-model <本机已安装的模型>` 接 Ollama。需要 DeepSeek 时，在当前进程环境设置 `DEEPSEEK_API_KEY` 后加 `--enable-deepseek`。同时启用时，先尝试 Ollama；远程调用沿用 AI 模块对账户数据的限制。DeepSeek 请求使用该 Key 的 API 额度。

分别启动时，在 `middle-office/` 运行 `python -m middle_office --public-market`，在 `ai/` 运行 `python -m ai_mvp`，再运行 `python frontend/UI.py --integrated --no-browser`。服务从进程环境读取 [`.env.example`](.env.example) 列出的变量。`MO_AI_READ_TOKEN` 与 `MO_API_TOKEN` 取不同值，`AI_MVP_MARKET_TOKEN` 和 `AI_MVP_TRADING_TOKEN` 使用 `MO_AI_READ_TOKEN`。启用公开行情时为 AI 设置 `AI_MVP_MARKET_ALL_SOURCES=1` 和 `AI_MVP_QUOTE_MAX_AGE_SECONDS=45`。分别启动需要先在中台创建 `HARBOR_DEMO_USER` 对应的模拟账户。

## 问卷与行情来源

- 风险问卷采用原设计的 30 道计分题和五维权重。KE2 可以多选，按最高选项得分计。后端计算 RAI、财务承载力封顶、红旗封顶与 C/R 等级，原设计样例得到 RAI 61、C3、R3。首次答卷提交后，中台与 AI 保存派生结果，原始选项留在本次表单处理内。[问卷原仓库 `6171544`](https://github.com/1242388305pj-ux/pj_questiontest/tree/6171544562dad80f70584915db41c50d48938efd)
- 问卷置信度使用直选、答题耗时（调用方提供时）、选项变更和交叉校验。原文未给交叉校验数值阈值，演示以两项评分差至少 3 或高低档组合标记待复核，分数保持原公式。浏览器记录选项变更，不采集逐题耗时和可选背景信息。
- 公开模式每 10 秒独立拉取 Binance、OKX、Kraken 的 BTC/USDT、ETH/USDT、SOL/USDT。读取公开现货接口无需账号或 API Key。买卖方向和计价币保持统一，支持按买卖一档比较。45 秒后旧报价退出比价，某一来源失败时其余来源继续刷新。Binance 和 OKX 使用接口时间字段，Kraken 该端点使用采集时间。开放状态可通过 `/api/health` 查看。[Binance 文档](https://developers.binance.com/en/docs/products/spot/faqs/market_data_only) · [OKX 文档](https://www.okx.com/docs-v5/en/#order-book-trading-market-data-get-tickers) · [Kraken 文档](https://docs.kraken.com/api-reference/market-data/get-ticker-information)

## 已接通的 API

- 浏览器 → 中台：`GET /api/market/venues?symbol=BTC%2FUSDT&quantity=0.01&side=buy` 展示币种、计价币、价格、报价来源及时间。`GET /api/account/summary` 读取同一份中台账户快照，含余额、持仓和挂单。
- 问卷结果 → 中台 → AI：`GET /api/questionnaire` 返回题库，`POST /api/questionnaire` 提交 `questionnaire_version`、`answers` 和 `consent`，按题库评分并同步。外部已评分系统仍可用 `PUT /api/profile` 导入派生结果。`GET /api/profile` 返回 AI 画像。AI 暂时不可用时，下次读画像或聊天会重新同步中台已保存的结果。
- 浏览器 → AI → 中台：`POST /api/assistant/chat` 支持多来源买卖报价、持仓与挂单。`GET /api/risk` 输出 AI 风险统计。公开模式可在聊天里输入「比较 BTC/USDT 的报价」。
- 浏览器 → 中台预览与模拟下单：`POST /api/orders/preview` 返回估算与有效期 60 秒的 `preview_id`。`POST /api/orders` 用 `{"preview_id":"..."}` 确认，中台在写账时复核。有效期内重交同一 ID 返回同一订单。`GET /api/orders/{order_id}` 查询状态，`POST /api/orders/{order_id}/cancel` 撤销挂单。

## 联调边界

- 模拟账户只供本机访问。真实登录、多人账户权限与真实交易所成交待接入。
- 公开行情展示买卖一档及数量，报价排名未纳入账户交易费、完整订单簿或滑点。数量大于一档挂单时标记深度不足。演示账本用公开报价模拟成交时将未知手续费按零处理，并在预览提示。
- AI 与前端都能看到多来源报价。持仓估值仍以新鲜参考价为基础，AI 风险统计与中台账本估值使用各自快照。历史走势、报表导出、资金划转和自选管理仍是原型功能。
- 默认 HTTP 联调验证的是模板回答和三模块数据流，Ollama 与 DeepSeek 的实际生成需在对应模型可用时分别验证。

协作约定见 [CLAUDE.md](CLAUDE.md)。
