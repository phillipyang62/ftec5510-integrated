# 数字资产 AI 助手 MVP

## 项目分工

- **前端**直接获取和展示行情等信息，也负责展示 AI 返回的对话和风险结果。
- **中台**从上游抓取币种及市场报价，并提供用户持仓和挂单的查询。
- **AI**读取问卷打分、币价和中台数据，提供投教、模拟投资建议和持仓风险摘要。

AI 可以使用前端已获取的行情，也可以接入中台抓取的行情。联调时以现有数据入口为准。各模块需要交换的信息和当前 API 示例见 [接口联调](接口联调.md)。

## 本地启动

需要 Python 3.10 或更新版本，只使用 Python 标准库。在项目目录打开两个 PowerShell 窗口。第一个窗口启动服务。

```powershell
python -m ai_mvp
```

第二个窗口运行演示。演示会写入两份虚构测评和两条模拟报价，再调用对话和模拟建议接口。演示使用本地推送的行情，运行前请清除 `AI_MVP_MARKET_URL` 配置。

```powershell
python -X utf8 -m ai_mvp.demo
```

默认监听 `127.0.0.1:8000`，测评保存在 `.ai_mvp/profiles.sqlite3`。可通过 `--port` 和 `--db` 指定端口和数据库。推送行情存于进程内，服务重启后重新推送。对话历史由调用方按需传入。

## 模型调用

对话生成使用显式配置的 API 模型。通道不可用时，接口通过 `model_status` 返回调用状态和中英文提示。资产匹配和风险统计继续使用后端测评规则。

每次聊天生成前，助手读取最新的测评总分、风险等级、产品上限和五维得分，并附上稳定币、主流波动资产、公链与协议代币及投机性较强的代币的特点。模型用和问题最相关的维度调整讲解深度和例子。问到产品或模拟方案时，模型围绕后端计算的结论解释。

问到自己的持仓时，助手读取中台的非零持仓，逐个对照产品档位和五维门槛。已授权的会话 API 会根据模拟持仓、测评和最新行情生成风险建议，并使用提问语言。服务通过中台快照确认持仓属于模拟账本。回复中的数量、报价和产品档位来自已核实的数据。

### 第三方 API 模型

联调页面的「模型设置」支持 DeepSeek、OpenAI 和 Gemini。选择平台后填写其 API Key，并确认该平台的用量计费规则。聊天服务使用对应的官方接口。命令行启动 AI 服务时，远程通道按下面的 DeepSeek 或兼容网关配置使用。

### DeepSeek 命令行配置

远程通道默认使用 DeepSeek 官方接口和 `deepseek-flash`。DeepSeek Key 放在服务端环境变量 `DEEPSEEK_API_KEY`。DeepSeek API 由 DeepSeek 按 token 单独计费。[DeepSeek API 文档](https://api-docs.deepseek.com/) · [DeepSeek 定价](https://api-docs.deepseek.com/quick_start/pricing/)

下面的命令会隐藏输入 Key，并用 DeepSeek API 启动普通对话。

```powershell
$apiSecret = Read-Host 'DeepSeek API key' -AsSecureString
try {
    $env:DEEPSEEK_API_KEY = [Net.NetworkCredential]::new('', $apiSecret).Password
    python -m ai_mvp --enable-remote
} finally {
    Remove-Item Env:DEEPSEEK_API_KEY -ErrorAction SilentlyContinue
    $apiSecret.Dispose()
}
```

向 `/v1/chat` 发一条普通对话时，`generation: remote_model` 表示已收到 API 模型的回答。也可设置 `AI_MVP_REMOTE_ENABLED=1` 显式启用该配置。默认超时为 30 秒，可用 `AI_MVP_REMOTE_TIMEOUT_SECONDS` 调整。持仓建议需要在联调页面配置当次会话的模型，并授权分享模拟持仓和测评。

如果通过自建网关接 DeepSeek，设置 `AI_MVP_REMOTE_BASE_URL`、`AI_MVP_REMOTE_MODEL` 和网关自己的 `AI_MVP_REMOTE_API_KEY`。网关需支持 HTTPS 上的 `/v1/chat/completions`。使用 DeepSeek 官方地址时直接用 `DEEPSEEK_API_KEY`。

## 联调入口

- AI 用 `AI_MVP_MARKET_URL` 连接前端或中台现有的币价入口，按需配置 `AI_MVP_MARKET_TOKEN`。也可以由数据提供方推送报价。
- AI 用 `AI_MVP_TRADING_URL` 连接中台只读账户接口，按需配置 `AI_MVP_TRADING_TOKEN`。
- 对应用户的问卷打分同步到 AI 的画像接口。问卷和中台数据用双方约定的用户标识关联。

AI 提供的接口如下，完整 JSON 示例见 [接口联调](接口联调.md)。

- `GET /health` 查看服务是否运行、各通道是否已配置。
- `PUT /v1/profiles/{user_id}` 和 `GET /v1/profiles/{user_id}` 写入或读取当前画像。
- `POST /v1/chat` 进行对话。传 `include_simulation: true` 可请求模拟建议。
- `GET /v1/risk/{user_id}?quote_currency=USDT` 获取结合币价和持仓计算的风险摘要。
- `GET /v1/market/quotes` 查询报价，`POST /v1/market/quotes` 接收推送报价。

跨机器联调时用 `--host` 指定 AI 机器的内网 IPv4，并设置 `AI_MVP_API_TOKEN`。配置该凭证后，除 `/health` 外的请求附带 `Authorization: Bearer <token>`。接中台时同样要设置这个服务凭证，由可信后端根据登录会话确认用户身份后代发请求。

## 测试

```powershell
python -B -m unittest discover -s tests -v
```

测试使用模拟的模型和上游响应。
