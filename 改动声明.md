# Harbor Invest 账户版改动声明

本文对比原集成版 [`3127d75`](https://github.com/phillipyang62/ftec5510-integrated/commit/3127d756cf91a29f9f292787a77dd42060e38e41) 和账户版 [`81c8ecc`](https://github.com/ALLE77-maker/ftec5510-integrated/commit/81c8ecc99aa9562849e464eccb430908d83ed90e)。除本声明外，账户版相对原集成版修改了 10 个文件，没有新增、删除或移动模块。

## 两版行为对比

| 项目 | 原集成版 | 账户版 |
| --- | --- | --- |
| 打开网站 | 直接进入工作台；首次使用显示风险问卷 | 先输入演示账户名，再进入工作台；未测评的账户仍会看到风险问卷 |
| 创建账户 | 一键演示启动时创建固定的 `student_demo` | 首次输入某个账户名时，通过现有中台接口创建模拟账户 |
| 使用和切换账户 | 浏览器共用固定账户 | 顶部显示当前账户；点击「切换账户」退出当前会话，可输入另一个账户名 |
| 账户数据 | 所有浏览器操作均指向同一个演示账户 | 余额、持仓、订单和风险画像按账户区分；同一次一键演示运行内，重新输入同名可继续使用原账户 |

## 改动范围

- **前端与网关**：`frontend/index.html`、`frontend/integration.js` 增加登录页面和切换入口；`frontend/UI.py`、`frontend/bff.py` 增加会话、首次创建账户及按会话选择账户；`frontend/questionnaire.js` 调整为登录后读取当前账户的画像，未修改评分公式或题库。
- **启动与验证**：`run_demo.py` 将模拟初始数据的建立从启动时移到首次登录；`.env.example` 移除固定账户配置；`check_integration.py` 增加登录、退出、切换和不同账户的数据隔离检查。
- **文档**：`README.md` 和 `frontend/docs/integration-contract.md` 补充用法和会话接口。

**三模块结构不变**：前端、中台和 AI 仍分别运行，浏览器仍通过前端网关访问两个后端。`middle-office/` 和 `ai/` 的源文件与原集成版完全一致。问卷评分、公开行情采集、模拟交易和 AI 的业务逻辑未改；账户版的变化是先建立会话，再按当前账户调用原有功能。

此功能仅用于本机演示，不验证账户名的所有权。请勿输入真实账号、密码或敏感信息。一键演示使用临时数据库，退出演示后不会保留账户数据。

## 已验证

- 浏览器实测两个演示账户均可登录和切换。
- 中台 38 项、AI 54 项单元测试通过；离线及实时行情联调通过，覆盖问卷、账户隔离、模拟订单和 AI。
- 本地复验：`python3 -X utf8 check_integration.py`；需要一并检查公开行情时，加 `--live-market`。

[查看两版完整代码差异](https://github.com/ALLE77-maker/ftec5510-integrated/compare/3127d756cf91a29f9f292787a77dd42060e38e41...81c8ecc99aa9562849e464eccb430908d83ed90e)
