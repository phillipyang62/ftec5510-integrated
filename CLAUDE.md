# Harbor Invest · FTEC5510

## 技术栈

- 前端使用 HTML、CSS、原生 JavaScript 与本地 Lucide 图标。用 Python 3.10+ 标准库提供同源 API。
- 五维问卷由后端用版本化题库评分。发送给中台和 AI 的内容限于派生结果，原始选择仅用于本次评分。
- 中台和 AI 使用 Python 3.10+、标准库 HTTP 服务及各自的 SQLite。AI 支持本地 Ollama 和显式启用的 DeepSeek。

## 目录与负责人

- `frontend/` 由前端组（`LeoLIU1233`）维护，负责页面、浏览器请求和同源网关。
- `middle-office/` 由中台组（`ALLE77-maker`）维护，负责行情采集接入、账本、模拟订单、持仓与中台风险规则。
- `ai/` 由 AI 组（`phillipyang62`）维护，负责问卷导出的五维画像、模型路由、教育、模拟配置与风险解释。
- 根目录的接口、演示、联调用例和本文件由三方共同维护。修改跨模块契约时，在同一 PR 更新受影响的实现和联调用例。

## 代码规范

- Python 用 `snake_case` 和四空格。JavaScript 用 `camelCase` 和双空格缩进。保持现有模块的格式。
- 金额、币价、数量在 HTTP 中使用十进制字符串，时间使用带时区的 RFC 3339 字符串。前端使用相对 `/api/...` 路径，不保存服务凭证。
- 中台是订单、持仓与资金的账本。AI 通过独立只读凭证访问中台。任何订单写入由中台校验与记账。
- 保留 `frontend/lucide.min.js` 和模块原有启动入口。跨模块变更需要一起检查旧调用与新调用。

## 常用命令

- 根目录用 `python run_demo.py` 启动三个模块，用 `python -X utf8 check_integration.py` 跑 HTTP 联调。两条命令加 `--live-market` 启用公开报价。
- 在 `ai/` 或 `middle-office/` 内用 `python -m unittest discover -s tests` 跑各自的测试。
- 根目录可用 `node --check frontend/integration.js` 检查浏览器脚本语法。

## 分支与 Review

1. 从 `main` 建 `feat/<名字>/<功能>`，保持 `main` 可运行。
2. 提 PR 前执行 `git pull --rebase origin main`，解决冲突并重跑相关验证。
3. 用 AI 先审分支差异并起草 commit message 和 PR 描述，再请另一位同学 review。涉及冲突解决时由同学检查最终 diff。
4. 通过 review 后合并并删除功能分支。`CLAUDE.md` 的更改也必须通过 PR，由其他模块负责人一同看过。

## 配置与密钥

- `.env.example` 仅记录变量名。真实环境值、模型密钥、账号信息、SQLite 文件及运行日志不要提交。
- 联调默认使用模拟数据和模板回复。只有明确指定 `--enable-deepseek` 才由演示启动器启用 API 模型。
