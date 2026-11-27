# Harbor Invest 前端

前端、问卷表单和同源 API 网关是联调版的组成部分。启动后可使用演示账户、风险测评、跨平台比价、模拟交易和聊天助手。测评结果供聊天和下单预览读取。

## 启动

在合并仓库根目录运行：

```powershell
python run_demo.py
```

在 Windows 也可双击 `frontend/start_preview.bat`。它通过 `frontend/UI.py` 启动同一套联调服务。打开终端显示的本机地址，通常为 `http://127.0.0.1:5510/`。直接打开 `index.html` 时显示启动说明。

默认联调使用中台 Python 生成的十种动态模拟行情。需要其他币种的公开行情时，在根目录运行 `python run_demo.py --live-market`。账户、持仓和下单使用模拟账本。分开启动各服务时，按[根目录说明](../README.md)配置网关。

## 聊天助手

登录后打开右上角「模型设置」，选择 DeepSeek、OpenAI 或 Gemini 并填写对应的 API Key。回复会标明实际调用的模型。演示持仓建议需要在本次会话授权分享模拟持仓和测评。切换界面语言后，示例问题及回复使用对应语言。

## 开发入口

- `index.html` 提供页面、样式和中英文切换。
- `integration.js` 和 `questionnaire.js` 处理页面交互、同源 API 调用与风险问卷。
- `UI.py` 提供入口和同源 HTTP 服务，`bff.py` 处理会话和跨模块 API。
- 在根目录运行 `python -X utf8 check_integration.py` 验证离线流程。

接口见[三模块接口约定](docs/integration-contract.md)。分工和评审流程见[共享协作规范](../CLAUDE.md)和[团队工作流](docs/team-workflow.md)。

前端原始版本见 [LeoLIU1233/5510-UI](https://github.com/LeoLIU1233/5510-UI)。
