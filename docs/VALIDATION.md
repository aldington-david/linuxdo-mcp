# 验证记录

## 0.5.0 本地管理与登录检测（2026-09-30）

- `LinuxDo.cmd` / `Manage-LinuxDo.ps1` 已在用户本机执行安装更新，插件启用；Codex 配置文件修改前后的 SHA256 一致，没有改变其他配置。
- 7 组 Python 回归测试通过，含真实 stdio/HTTP 传输、Cookie 候选验证失败不覆盖、成功轮换保存、登录状态预检及跨进程锁。
- `tests/check_manager.ps1` 通过：PowerShell 解析、DPAPI 加密往返、空配置状态只读、Windows 启动参数、Tunnel 归属校验、隔离临时目录中的启动快捷方式创建/撤销及同名无关项目保护。未因此开启用户实际自启。
- 用户隐藏输入的 Tunnel key 经已有 Tunnel 的只读权限查询确认后加密保存。使用官方 runtimes connect 启动，官方状态显示 process_running/healthy/ready 均 true。
- 重复启动前后 PID 一致，没有重复后台进程。本地管理窗口不必保持打开。未进行实际 Windows 重启验收；登录自启默认关闭。
- 本机 stdio 的身份、单页搜索和话题读取通过；经已安装 ChatGPT 连接再次实际调用 whoami/search/get_topic，单页搜索返回 50 条，读取 3 条帖子并得到继续分页位置。
- 当前 Cookie 有效；没有声称观察到新的服务端自然轮换，轮换逻辑另由回归测试验证。空闲时不后台定时验证，使用中超过 5 分钟后的下一次请求检查身份。

下面为历史版本记录。

## 0.4.0 stdio 自动启动更新

- 本机默认插件已改为 stdio，Python 启动命令可由打包参数 `--python` 指定。
- 6 组测试通过，新增真实双进程轮换、锁等待超时、进程异常退出后锁释放；补测裸 Cookie 中的 `=`、URL 编码与空 `_t=`。
- 从本机实际安装目录读取命令并启动成功，MCP 返回 13 个工具；安装/启用状态已由 Codex CLI 确认。现有对话是否加载新工具仍须以新对话调用为准。
- Windows 中文路径下 curl_cffi 加载 CA 文件出现 curl 77；将运行环境安装到纯英文路径后 TLS 校验正常。没有关闭证书校验。
- tunnel-client 0.0.15 的 stdio 命令预检不正确处理 Windows 反斜杠及 `-X utf8`，使用正斜杠路径和 `python -m` 后初始化通过。
- 截至本节记录，真实 Tunnel 已创建且本机 `/readyz` 返回 ready；真实 Cookie 登录、搜索和读帖已通过；修复了浏览器解码值的 Cookie 编码兼容问题，并以服务器身份接口验证成功后再使用缓存。ChatGPT 已安装完整插件（Apps 1 Connected、Skills 1、版本 0.4.0），在 Work 对话中实际调用插件完成一页搜索、列出三个话题链接并读取首个话题的前三条可见帖子；调用记录明确显示搜索和话题读取两个动作。

当前未声称验证跨设备访问、长期无人值守运行或浏览器自动取 Cookie。Codex 默认使用 stdio；ChatGPT 网页调用需要 tunnel-client 保持运行。真实调用截图和对话地址仅保存在本机审计目录，不将用户对话与账户连接 ID 发布到仓库。

## 0.3.0 历史记录

以下保留初始发布时的结果；当前状态以最上面的版本记录为准。

验证日期：2026-09-29。环境：Windows、Python 3.11.7、MCP SDK 2.2.0、curl_cffi 0.16.3、Pydantic 2.13.5。

### 当时已验证

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

### 当时尚未完成的账户验收

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
