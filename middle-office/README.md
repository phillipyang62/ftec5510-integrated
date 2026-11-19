# FTEC5510 Group 20 Middle Office

完整的六模块中控课程原型，使用 Python 3.10+ 标准库和 SQLite。默认地址为 `http://127.0.0.1:8200`。

| 模块 | 已实现内容 |
| --- | --- |
| M1 账户与偏好 | 模拟账户、虚拟资金、初始模拟持仓、自选币、价格提醒、派生问卷测评保存 |
| M2 行情处理 | 多来源报价接收、可选上游轮询、交易对规范化、来源和时间校验、跨平台费用比较 |
| M3 持仓与盈亏 | 成交入账、加权平均成本、已实现和未实现盈亏、费用统计、有效报价估值 |
| M4 订单与模拟成交 | 市价和限价、买卖、挂单、撤单、资金及持仓预留、请求去重、唯一成交记录 |
| M5 交易与持仓风控 | 余额、可卖量、订单限额、可配置产品风险等级校验、集中度和浮亏预警 |
| M6 交易监测与反洗钱 | 大额及高频规则、告警证据、人工复核、关闭或升级、操作审计 |

## 启动与演示

在仓库根目录打开终端。Windows 使用 `python`，macOS 可以使用 `python3`。

```sh
python -m middle_office
```

另一个终端运行完整六模块演示。脚本新建 `demo_` 开头的虚构账户，使用模拟报价和虚拟资金。

```sh
python -m middle_office.demo
```

演示包括保存问卷与偏好、双平台比价、买入、挂单、撤单、余额不足拒绝、查询盈亏，以及反洗钱告警复核。数据库默认保存在 `.middle_office/ledger.sqlite3`，重启继续保留。使用 `--db` 指定独立演示数据库。

测试命令如下。

```sh
python -B -m unittest discover -s tests -v
```

## 分工和接口

- [完整接口说明](docs/API.md)
- [组员协调事项与 AI 重合分析](docs/INTEGRATION.md)
- [业务规则与演示假设](docs/RULES.md)
- [对接杨昊岳：持仓与挂单](对接杨昊岳.md)
- [中台记账、风控及 AI 数字一致性的 Python 代码](docs/AI_NUMBER_CONSISTENCY.md)

这次实现采用独立 HTTP 中控服务，便于 C++/Qt、网页和 AI 服务分别调用。原 `dev.zip` 的 C++ 项目作为上游接入对象。`examples/qt/MiddleOfficeClient.h` 提供异步 Qt 网络调用示例，组员将其接入 BusinessEngine。该示例尚未在 Qt 编译环境验证。

## AI 接口兼容

已对照并联调杨昊岳的 [crypto-ai-mvp](https://github.com/phillipyang62/crypto-ai-mvp)，基准提交为 `bcfd2220e3c3ab1f47deb983fb3869fa692542f3`。

- `GET /api/quotes?q=BTC%2FUSDT&limit=5` 返回币种、价格、计价交易对、来源及时间。
- `GET /api/accounts/{user_id}/analysis_snapshot` 返回同一次读取的账户、官方估值、风险指标和报价依据。AI 侧示例见 `examples/ai/consistent_analysis.py`；需要他另行接入新路径，详见一致性说明。
- `GET /api/accounts/{user_id}/snapshot` 返回持仓和未完成订单。
- 问卷使用相同 `user_id` 和派生 `assessment` 字段，可由问卷或业务后端分别提交到两端。

同机联调的环境变量见 `docs/INTEGRATION.md`。在杨的仓库已下载到本地后，可运行真实适配器和 AI HTTP 服务的独立检查。检查使用临时数据库及模拟报价，无需模型密钥。

```sh
python scripts/check_ai_integration.py --ai-source ../crypto-ai-mvp
```

## 跨机器访问

默认仅监听本机。跨机器运行时设置 `MO_API_TOKEN`（可信业务后端的写入凭证）和另一个不同的 `MO_AI_READ_TOKEN`（AI 只读凭证），再指定内网 IPv4。凭证通过环境变量设置，示例值应替换为组内随机生成的值。

PowerShell 示例。

```powershell
$env:MO_API_TOKEN = 'replace-with-operator-token'
$env:MO_AI_READ_TOKEN = 'replace-with-different-reader-token'
python -m middle_office --host 192.168.1.20 --port 8200
```

服务凭证由可信后端持有，用户身份由该后端的登录会话确认。此服务按账户分离记录，尚未提供终端用户登录系统。局域网的普通 HTTP 适合受控课程演示，正式部署需要 HTTPS 接入层。

## 上游行情

支持 Gateway 通过 `POST /api/quotes` 推送，也支持轮询约定的 HTTP 报价地址。

```sh
python -m middle_office --market-url http://127.0.0.1:8300/quotes --market-interval 5
```

上游返回 `{ "quotes": [...] }`，字段见 API 文档。`MO_MARKET_TOKEN` 为可选上游 Bearer 凭证。服务保留采集时间，上游失败时旧报价按原时间自然过期。

使用 `python -m middle_office --public-market` 可独立轮询 Binance、OKX、Kraken 的公开现货 ticker，无需 API Key。公开模式默认使用单独的 SQLite 文件，行情保鲜期为 45 秒。比价以买卖一档参考价排序并标注该档数量，成交和费用仍按模拟规则记账。[来源和启动方式](../README.md#问卷与行情来源)

## 原型范围

市价单和限价单是课堂模拟。默认按照新鲜的模拟买卖报价整笔成交。公开模式还检查一档数量，预览会标注无法取得账户费率时采用的零费率假设。每个账户以一种计价币管理交易和成本，金额及数量最多保留 8 位小数，使用 Decimal 与 SQLite 事务处理。

部分成交、真实交易所下单、充值提现、自动法定可疑交易报告和生产级登录系统需要后续单独开发。价格和风险阈值均为课堂演示参数，具体说明在 `docs/RULES.md`。
