# Harbor Invest · FTEC5510

前端、中台和 AI 助手共用仓库。各模块原有的入口和文档都保留在各自目录。

| 模块 | 目录 | 导入版本 |
| --- | --- | --- |
| 前端 | [`frontend/`](frontend/) | [LeoLIU1233/5510-UI `6366904`](https://github.com/LeoLIU1233/5510-UI/tree/63669046ecabf3415b2e7e43efd964ffbddd2024) |
| 中台 | [`middle-office/`](middle-office/) | [ALLE77-maker/ftec5510-middle-office `0414afc`](https://github.com/ALLE77-maker/ftec5510-middle-office/tree/0414afc5e6aada231c4def932a2de394d7469b3c) |
| AI 助手 | [`ai/`](ai/) | [phillipyang62/crypto-ai-mvp `bcfd222`](https://github.com/phillipyang62/crypto-ai-mvp/tree/bcfd2220e3c3ab1f47deb983fb3869fa692542f3) |

## 一键启动

需要 Python 3.10 或更高版本。OSL 的公开行情使用 WebSocket，首次使用前安装可选客户端 `python -m pip install -r requirements-live.txt`。

```shell
python run_demo.py --live-market
python -X utf8 check_integration.py --live-market
```

第一条命令启动三个 HTTP 服务。打开终端打印的本机网址，通常为 `http://127.0.0.1:5510/`。输入演示账户名（如 `student_demo`）进入工作台。首次使用该名称会创建模拟账户，未做风险测评时会显示问卷，也可以稍后填写。点击顶部「切换账户」退出当前会话。`--live-market` 读取真实现货报价，账户和订单仍在本地模拟。省略该参数即可离线演示，使用两家模拟报价来源。默认退出演示会清理临时数据库。启动时用 `--data-dir <目录>` 可保留账本和画像，下次用相同目录和账户名即可继续。第二条命令独立复测离线流程及公开行情。

仓库只运行一套联调版。可用 `python run_demo.py` 启动，也可在 Windows 双击 `frontend/start_preview.bat`。直接打开 `frontend/index.html` 会显示启动命令。

登录后，在聊天助手右上角打开「模型设置」。可选择本地 Ollama，或选择 DeepSeek、OpenAI、Gemini 并填入对应平台的 API Key。三个 API 默认使用 `deepseek-flash`、`gpt-4.1-mini`、`gemini-3.1-flash-lite`。Key 只保留在本次登录会话的服务端内存里，费用按实际发出的请求和所选平台规则计算。聊天会标注实际使用的模型或内置回复。涉及持仓或挂单的账户上下文只用于本机处理。

启动时也可用 `--ollama-model <本机已安装的模型>`，或在进程环境设置 `DEEPSEEK_API_KEY` 后加 `--enable-deepseek`。两种启动配置同时启用时，优先尝试 Ollama。未配置模型时使用内置回复。

分别启动时，在 `middle-office/` 运行 `python -m middle_office --public-market`，在 `ai/` 运行 `python -m ai_mvp`，再运行 `python frontend/UI.py --integrated --no-browser`。服务从进程环境读取 [`.env.example`](.env.example) 列出的变量。`MO_AI_READ_TOKEN` 与 `MO_API_TOKEN` 取不同值，`AI_MVP_MARKET_TOKEN` 和 `AI_MVP_TRADING_TOKEN` 使用 `MO_AI_READ_TOKEN`。启用公开行情时为 AI 设置 `AI_MVP_MARKET_ALL_SOURCES=1` 和 `AI_MVP_QUOTE_MAX_AGE_SECONDS=45`。演示账户由中台在首次登录时创建，无需提前准备。

## 问卷与行情来源

- 已完成问卷的账户可从结果页点击「重新测评」，提交后用最新结果预览订单。一键演示将 BTC/USDT、ETH/USDT、SOL/USDT 分别设为 R4、R3、R5。档位是课程演示参数。未测评或买入超过产品上限时，预览会提示风险，用户仍可自行确认。单独启动中台时，可组合 `--product-risks` 和 `--suitability-advisory` 启用同样的提醒。
- 风险问卷采用原设计的 30 道计分题和五维权重。KE2 可以多选，按最高选项得分计。后端计算 RAI、财务承载力封顶、红旗封顶与 C/R 等级，原设计样例得到 RAI 61、C3、R3。首次答卷提交后，中台与 AI 保存派生结果，原始选项留在本次表单处理内。[问卷原仓库 `6171544`](https://github.com/1242388305pj-ux/pj_questiontest/tree/6171544562dad80f70584915db41c50d48938efd)
- 测评结果页显示综合分、等级和产品上限，「查看对应投教」按当前画像加载一段短课。读完可点「打开模拟下单页」，选择买入或卖出并预览，再确认模拟订单。对应投教走本地规则，聊天助手仍接受自由提问。
- 问卷置信度使用直选、答题耗时（调用方提供时）、选项变更和交叉校验。原文未给交叉校验数值阈值，演示以两项评分差至少 3 或高低档组合标记待复核，分数保持原公式。浏览器记录选项变更，不采集逐题耗时和可选背景信息。
- 公开模式支持 48 个币种、71 个交易对，包括 XRP、LINK、DOGE、ADA、AVAX 和多种稳定币。比价页根据中台目录展示币种和计价币，按同一计价币比较买卖一档。45 秒后旧报价退出比价，行情源独立刷新。Binance 和 OKX 使用接口时间字段，Kraken 使用采集时间。各来源状态可通过 `/api/health` 查看。[Binance 文档](https://developers.binance.com/en/docs/products/spot/faqs/market_data_only) · [OKX 文档](https://www.okx.com/docs-v5/en/#order-book-trading-market-data-get-tickers) · [Kraken 文档](https://docs.kraken.com/api-reference/market-data/get-ticker-information)
- 比价页默认展示 BTC/USD 的 HashKey 与 OSL 香港站行情。也可切换 LINK/USD、USDT/USD、USDT/HKD 等两家共同覆盖的交易对。HashKey 使用公开 REST，OSL 使用公开 WebSocket。未安装可选客户端时，OSL 在 `/api/health` 中显示 `dependency_missing`。模拟下单仍使用 BTC/USDT、ETH/USDT 和 SOL/USDT。[HashKey 香港行情文档](https://docs.hashkey.com/hk/en/index.html#public-market-data-spot-amp-futures) · [OSL Ticker 字段](https://osl.com/reference/market-data)

## 已接通的 API

- 浏览器 → 中台：`GET /api/market/venues?symbol=BTC%2FUSDT&quantity=0.01&side=buy` 展示币种、计价币、价格、报价来源及时间。`GET /api/account/summary` 读取同一份中台账户快照，含余额、持仓和挂单。
- 问卷结果 → 中台 → AI：`GET /api/questionnaire` 返回题库，`POST /api/questionnaire` 提交 `questionnaire_version`、`answers` 和 `consent`，按题库评分并同步。外部已评分系统仍可用 `PUT /api/profile` 导入派生结果。`GET /api/profile` 返回 AI 画像。AI 暂时不可用时，下次读画像或聊天会重新同步中台已保存的结果。
- 浏览器 → AI → 中台：`POST /api/assistant/chat` 支持多来源买卖报价、持仓与挂单。`GET /api/risk` 输出 AI 风险统计。公开模式可在聊天里输入「比较 BTC/USDT 的报价」。
- 浏览器 → 中台预览与模拟下单：`POST /api/orders/preview` 返回估算与有效期 60 秒的 `preview_id`。`POST /api/orders` 用 `{"preview_id":"..."}` 确认，中台在写账时复核。有效期内重交同一 ID 返回同一订单。`GET /api/orders/{order_id}` 查询状态，`POST /api/orders/{order_id}/cancel` 撤销挂单。

## 联调边界

- 模拟账户只供本机访问。仅凭名称选择账户，不验证身份；知道名称的人可以进入同一演示账户。请勿使用真实凭证或敏感数据。
- 公开行情展示买卖一档及数量，报价排名未纳入账户交易费、完整订单簿或滑点。数量大于一档挂单时标记深度不足。演示账本用公开报价模拟成交时将未知手续费按零处理，并在预览提示。
- AI 与前端都能看到多来源报价。持仓估值仍以新鲜参考价为基础，AI 风险统计与中台账本估值使用各自快照。历史走势、报表导出、资金划转和自选管理仍是原型功能。
- HTTP 联调覆盖内置回复、三模块数据流和模拟的 DeepSeek、OpenAI、Gemini 请求。真实模型生成需要本机 Ollama 或所选平台的有效 Key。

协作约定见 [CLAUDE.md](CLAUDE.md)。
