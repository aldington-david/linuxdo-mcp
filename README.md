# Linux.do 阅读助手

基于 [mrsxs/linuxdo-mcp](https://github.com/mrsxs/linuxdo-mcp) 的个人只读插件：让 ChatGPT / Codex 搜索 Linux.do、阅读完整话题与回复，并引用原帖。

本 fork 保留上游的 `curl_cffi`、独立 Cookie、轮换续期和 13 个工具，新增 Streamable HTTP、插件清单、检索 Skill、安全边界校验及测试。默认 stdio 仍可用。上游基线为 `d4c007aab787fe5d3d2d2f5d52197533fb469a35`。

推荐个人使用方式：

```text
ChatGPT → Secure MCP Tunnel → 本机 http://127.0.0.1:8787/mcp → Linux.do
Codex 本机插件 ───────────────→ 同一个本机 MCP
```

Cookie 保存在本机；查询及读取到的帖子内容会作为工具结果传给调用方。HTTP 入口只允许监听回环地址，没有多用户鉴权，不能直接作为公网服务发布。

## 开始使用

在 Windows PowerShell 中进入仓库根目录：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\python.exe -m linuxdo_mcp.server --configure-cookie
.\.venv\Scripts\python.exe -m linuxdo_mcp.server --transport streamable-http
```

第四步会隐藏输入，只在本机终端粘贴独立 `_t`，不要发到聊天。服务启动后保持窗口运行。另开终端检查：

```powershell
.\.venv\Scripts\python.exe scripts/check_connection.py
.\.venv\Scripts\python.exe scripts/check_connection.py --live
```

第一条只检查 MCP 握手和工具发现；第二条才会登录、搜索并在有结果时读帖。完整的 Cookie 获取、Tunnel、ChatGPT 安装、Skill 绑定和常见故障见 [使用文档](docs/USAGE.md)。

## 工具

| 工具 | 用途 / 默认参数 |
|---|---|
| `whoami` | 当前账号与信任等级，不返回 Cookie |
| `search` / `format_search` | 搜索；`query`，`page=1`，`pages=1`（最多 5 页） |
| `get_topic` / `format_topic` | 话题正文；`topic_id` 支持 ID 或 Linux.do HTTPS 链接，`posts=20`（最多 100），`start=1` |
| `list_categories` / `list_tags` | 板块和标签 |
| `category_topics` / `tag_topics` | 板块或标签的话题，`page=0` |
| `latest_topics` / `top_topics` | 最新 / 热门，`page=0`；热门默认 `period=weekly` |
| `user_info` / `user_actions` | 用户资料 / 发帖回复活动，活动默认 `limit=20`（最多 30） |

`format_*` 返回 Markdown，其余返回结构化 JSON。搜索支持 `order:latest`、`after:YYYY-MM-DD`、`before:YYYY-MM-DD`、`in:title`、`#分类`、`@用户`、`tags:标签`。分页时用 `get_topic.next_start`；`start` 是可见帖子的位置，不一定等于实际楼号 `floor`。`next_start=null` 表示结束。

## 插件文件与打包

- `plugin.json`、`mcp.json`：Agent Plugins 1.0.0 入口和本机连接。
- `.codex-plugin/plugin.json`、`.mcp.json`：OpenAI 展示信息及旧客户端兼容配置。
- `skills/linuxdo-research/`：检索、读正文、分页和引用规则。
- `scripts/package_plugin.py`：按允许列表打包，不包含源码环境、Cookie 或 Git 历史。

```powershell
.\.venv\Scripts\python.exe scripts/package_plugin.py
# ChatGPT 注册连接后，用自己的真实技术 ID 生成绑定包：
.\.venv\Scripts\python.exe scripts/package_plugin.py --app-id plugin_asdk_app_YOUR_REAL_ID
```

本机包输出到 `dist/linuxdo-mcp-local.zip`；绑定包为 `dist/linuxdo-mcp-chatgpt.zip`。前者需要同机 MCP 已启动；后者使用注册的 ChatGPT 连接，不会尝试访问 ChatGPT 云端的 localhost。包本身不部署服务器，也不创建 Tunnel。

## 验证与维护

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pip wheel --no-deps . --wheel-dir dist
```

测试使用隔离的临时 Cookie 目录和虚拟帖子数据；真实 stdio / HTTP 传输照常启动。测试不会读取浏览器或联系 Linux.do。当前验收边界见 [验证记录](docs/VALIDATION.md)，升级和停用见 [使用文档](docs/USAGE.md)，撤销本次改动见 [回滚文档](docs/ROLLBACK.md)。

## 来源与规范

本 fork 的 Python 包版本为 `0.3.0`，使用 MCP Python SDK `>=2.2.0,<3`。没有实现 UI、OAuth、多账号托管或写入操作。

- [OpenAI 插件打包规范](https://developers.openai.com/plugins/build/plugins)
- [OpenAI MCP 工具开发规范](https://developers.openai.com/plugins/build/mcp-server)
- [Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)
- [隐私与数据流](docs/PRIVACY.md)
- [开发操作记录](docs/OPERATIONS.md)
- [上游 README 原文存档](docs/UPSTREAM_README.md)

截至本次开发，上游没有声明许可证。本 fork 保留来源，不擅自标注 MIT 或 Apache 许可；这里提供个人使用实现，没有提交到公开插件目录。不是 Linux.do 或 OpenAI 官方插件。
