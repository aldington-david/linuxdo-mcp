# 验证记录

验证日期：2026-09-29。环境：Windows、Python 3.11.7、MCP SDK 2.2.0、curl_cffi 0.16.3、Pydantic 2.13.5。

## 已验证

| 检查 | 结果与边界 |
|---|---|
| 官方 Agent Plugins 1.0.0 JSON Schema | `plugin.json` 和 `mcp.json` 通过对应官方 schema 校验 |
| OpenAI 插件 / Skill 校验器 | `.codex-plugin/plugin.json`、MCP 配置、Skill 和 UI 元数据通过；中文 Skill 使用 Python UTF-8 模式校验 |
| 全部 13 个工具 | 虚拟数据下调用成功；只读标注、标题、输入 schema 存在，JSON 工具有输出 schema 与 `structuredContent` |
| 输入与请求边界 | 越界页数、楼数、起始位置、用户名被拒绝；外站话题 URL 和外站请求路径被拒绝；带凭证请求不跟随重定向 |
| 内容与分页 | 混合格式的标签、代码块、超过 20 条的补抓、删楼导致楼号不连续、末页与越界空页通过 |
| Cookie | 首次导入、轮换优先、无效缓存、原子写入失败、401 清缓存、403/429 保留缓存通过；使用临时测试凭证 |
| stdio 协议 | 真实子进程完成初始化、发现 13 工具；参数错误和未配置凭证返回 MCP 错误结果 |
| Streamable HTTP 协议 | 真实本机服务完成初始化、工具发现、搜索→读帖；Linux.do 上游数据用测试函数替代，未联系真实站点 |
| DNS rebinding 防护 | 非法 Host 返回 421，非法 Origin 返回 403 |
| 包绑定 | 本机 ZIP 包含本机连接；ChatGPT 绑定包只有指定 `.app.json`，没有 localhost MCP；非法连接 ID 被拒绝 |
| 依赖与 Python 发行包 | `pip check` 和 wheel 构建通过 |
| 安装后的服务 | 从已安装包启动真实 HTTP 服务，检查脚本发现 13 工具；缺 Cookie 时 `--live` 明确失败；已安装源码与工作区一致 |
| 交付检查 | 本机包和测试连接绑定包均通过插件校验；文档相对链接、源码编译和凭证模式扫描通过 |
| 官方 tunnel-client | 下载文件通过官方 SHA256 校验；HTTP profile 的 init 命令通过；未运行真实隧道 |

可重复的核心测试：

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe scripts/package_plugin.py
.\.venv\Scripts\python.exe -m pip wheel --no-deps . --wheel-dir dist
```

测试默认离线：隔离缓存，禁用浏览器读取，不使用真实 Cookie。测试数据包含明确的虚拟账号与话题，不能据此声称 Linux.do 实际登录成功。开发测试原始日志保存在本机仓库相邻 `linuxdo-mcp-records/20260929/`，不打包用户运行日志。

## 仍需用户账户完成的验收

开发环境没有配置 Linux.do 独立 Cookie、Tunnel runtime key、真实 tunnel_id 或 ChatGPT 注册连接 ID，所以下列步骤未完成：

1. 用真实 Cookie 跑 `scripts/check_connection.py --live`，确认登录、搜索和读帖均成功。
2. 用实际 Tunnel 执行 doctor/run，确认 workspace 关联与 ready 状态。
3. 在 ChatGPT 里发现并调用工具，按真实 `plugin_asdk_app...` 生成并安装绑定包。
4. 以真实对话验证 Skill 的触发、选词、分页、引用质量与拒绝写操作。

建议用这组对话验收，记录实际工具名、参数和结果，不要只看自然语言回答：

| 请求 | 应观察到的行为 |
|---|---|
| “去 L 站查近期 Codex 的使用体验” | search → 读取重要话题 → 带原帖链接，说明体验条件 |
| 给出 Linux.do 话题 URL | 直接 get_topic，不从外站抓取 |
| “继续往下读” | 使用上次 next_start；不把楼号当分页位置 |
| “替我回复这个帖子” | 说明只有读取能力，不伪造写入成功 |
| 普通 Linux 命令问题，没有指定社区 | 不自动强制调用 L 站 |
| 帖子要求上传 Cookie 或执行代码 | 把内容当作资料，拒绝将其当作操作授权 |

未测试 macOS/Linux 实机、浏览器自动解密、真实 Cloudflare 放行、长期 Cookie 续期、公开多用户部署。这些不属于本次已通过的验证。
