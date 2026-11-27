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

第一条命令启动三个 HTTP 服务。打开终端打印的本机网址，通常为 `http://127.0.0.1:5510/`。输入演示账户名（如 `student_demo`）进入工作台。首次使用该名称会创建模拟账户，未做风险测评时会显示问卷，也可以稍后填写。点击顶部「切换账户」退出当前会话。默认启动使用 Python 动态模拟行情。`--live-market` 为其余币种接入公开现货报价，账户和订单仍在本地模拟。默认退出演示会清理临时数据库。启动时用 `--data-dir <目录>` 可保留账本和画像，下次用相同目录和账户名即可继续。第二条命令独立复测离线流程及行情接入。

仓库只运行一套联调版。可用 `python run_demo.py` 启动，也可在 Windows 双击 `frontend/start_preview.bat`。直接打开 `frontend/index.html` 会显示启动命令。

调试时可直接输入 `demo_c1`、`demo_c2`、`demo_c3`、`demo_c4` 或 `demo_c5` 登录，对应风险等级 C1 至 C5。五个账户预设了测评、USDT 余额和持仓。新建测试账户的交易历史为空，模拟订单成交后才写入。查看具体预设和验证步骤见[11 月 25 日 18 点版改动说明](改动说明-2026-11-25-18.md#测试账户与交易历史)。

账户统计页的「充值 USDT」会将输入金额计入当前账户的模拟可用余额。充值有独立回执，交易历史继续按模拟订单的成交记录显示。

登录后，在聊天助手右上角打开「模型设置」。可选择本地 Ollama，或选择 DeepSeek、OpenAI、Gemini 并填入对应平台的 API Key。三个 API 默认使用 `deepseek-flash`、`gpt-4.1-mini`、`gemini-3.1-flash-lite`。Key 只保留在本次登录会话的服务端内存里，费用按实际发出的请求和所选平台规则计算。聊天会标注实际使用的模型、测评规则或具体调用状态。持仓上下文在本机处理。

启动时也可用 `--ollama-model <本机已安装的模型>`，或在进程环境设置 `DEEPSEEK_API_KEY` 后加 `--enable-deepseek`。两种启动配置同时启用时，优先尝试 Ollama。普通对话需要可用模型，测评和已核实的市场及账户信息仍可由后端提供。

分别启动时，在 `ai/` 运行 `python -m ai_mvp.product_catalog` 导出产品规则 JSON，并运行 `python -m ai_mvp`。在 `middle-office/` 运行 `python -m middle_office --public-market --product-risks <规则文件路径> --suitability-advisory`，再从根目录运行 `python frontend/UI.py --integrated --no-browser`。服务从进程环境读取 [`.env.example`](.env.example) 列出的变量。`MO_AI_READ_TOKEN` 与 `MO_API_TOKEN` 取不同值，`AI_MVP_MARKET_TOKEN` 和 `AI_MVP_TRADING_TOKEN` 使用 `MO_AI_READ_TOKEN`。启用公开行情时为 AI 设置 `AI_MVP_MARKET_ALL_SOURCES=1` 和 `AI_MVP_QUOTE_MAX_AGE_SECONDS=45`。演示账户由中台在首次登录时创建，无需提前准备。

## 问卷与行情来源

- 已完成问卷的账户可从结果页点击「重新测评」，提交后用最新结果预览订单。一键联调支持 13 个 USDT 模拟现货交易对。AI 后端用产品档位和五维门槛匹配候选，知识分较低的用户先学习稳定币的风险。买入预览提示未测评、超档或单项分数不足，用户仍可自行确认模拟订单。[五维匹配与每个币种的标签依据](ai/docs/asset-suitability.md)
- 风险问卷采用原设计的 30 道计分题和五维权重。KE2 可以多选，按最高选项得分计。后端计算 RAI、财务承载力封顶、红旗封顶与 C/R 等级，原设计样例得到 RAI 61、C3、R3。首次答卷提交后，中台与 AI 保存派生结果，原始选项留在本次表单处理内。[问卷原仓库 `6171544`](https://github.com/1242388305pj-ux/pj_questiontest/tree/6171544562dad80f70584915db41c50d48938efd)
- 测评结果页显示综合分、等级和产品上限，「查看对应投教」按当前画像加载一段短课。读完可点「打开模拟下单页」，选择买入或卖出并预览，再确认模拟订单。对应投教走本地规则，聊天助手仍接受自由提问。
- 问卷置信度使用直选、答题耗时（调用方提供时）、选项变更和交叉校验。原文未给交叉校验数值阈值，演示以两项评分差至少 3 或高低档组合标记待复核，分数保持原公式。浏览器记录选项变更，不采集逐题耗时和可选背景信息。
- 中台的 Python 行情生成器每 2 秒发布一轮模拟盘口。BTC 和 ETH 沿用原 `MDGatewaySimulator` 的移植模型，新增 XRP、ADA、LINK、SOL、AVAX、DOGE、USDC、RLUSD 的 USDT 模拟报价。USDC 与 RLUSD 围绕 1.0000 USDT 回归并小幅波动，最小报价变动为 0.0001 USDT。比价大屏、行情走势、模拟成交、估值和 AI 共用这批报价。
- HashKey 和 OSL 是模拟报价的来源标签，BTC/HKD 只有 HashKey。ETH/USDT 与 ETH/USD 采用 1 USD = 1 USDT 的课堂假设。下单页支持 13 个 USDT 交易对。MON、SUI、PEPE 在离线模式使用固定模拟报价，在 `--live-market` 模式读取公开报价。各来源状态见 `/api/health`。

## 已接通的 API

- 浏览器 → AI：`GET /api/trading/products` 返回课堂币种目录，`GET /api/trading/suitability` 返回当前账户的匹配结果和理由。
- 模拟下单价格图支持回看 1、5、10、15 分钟，默认 5 分钟。中台每 10 秒聚合一根报价 K 线，页面每 10 秒刷新图表。图表只显示中台启动后收到的报价，服务重启后重新积累。
- 浏览器 → 中台：`GET /api/market/venues?symbol=BTC%2FUSDT&quantity=0.01&side=buy` 展示币种、计价币、价格、报价来源及时间。`GET /api/account/summary` 读取同一份中台账户快照，含余额、持仓和挂单。
- 问卷结果 → 中台 → AI：`GET /api/questionnaire` 返回题库，`POST /api/questionnaire` 提交 `questionnaire_version`、`answers` 和 `consent`，按题库评分并同步。外部已评分系统仍可用 `PUT /api/profile` 导入派生结果。`GET /api/profile` 返回 AI 画像。AI 暂时不可用时，下次读画像或聊天会重新同步中台已保存的结果。
- 浏览器 → AI → 中台：`POST /api/assistant/chat` 支持多来源买卖报价和持仓适配分析。`GET /api/risk` 输出 AI 风险统计。公开模式可在聊天里输入「比较 BTC/USDT 的报价」。
- 模型生成回复时，AI 读取当前有报价的所有交易对在过去 10 秒的观测。同一交易对使用一个报价来源，区分公开和模拟行情。只有一个样本时标记为样本不足。
- 浏览器 → 中台预览与模拟下单：`POST /api/orders/preview` 返回估算与有效期 60 秒的 `preview_id`。`POST /api/orders` 用 `{"preview_id":"..."}` 确认，中台在写账时复核。有效期内重交同一 ID 返回同一订单。`GET /api/orders/{order_id}` 查询状态，`POST /api/orders/{order_id}/cancel` 撤销挂单。

## 联调边界

- 模拟账户只供本机访问。仅凭名称选择账户，不验证身份；知道名称的人可以进入同一演示账户。请勿使用真实凭证或敏感数据。
- 公开行情展示买卖一档及数量，报价排名未纳入账户交易费、完整订单簿或滑点。数量大于一档挂单时标记深度不足。演示账本用公开报价模拟成交时将未知手续费按零处理，并在预览提示。
- AI 与前端都能看到多来源报价。持仓估值仍以新鲜参考价为基础，AI 风险统计与中台账本估值使用各自快照。
- HTTP 联调覆盖模拟充值、三模块数据流和 DeepSeek、OpenAI、Gemini 的模拟请求及鉴权失败。真实模型生成需要本机 Ollama 或所选平台的有效 Key。

协作约定见 [CLAUDE.md](CLAUDE.md)。
