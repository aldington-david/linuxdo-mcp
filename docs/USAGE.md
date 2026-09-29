# 使用文档

## 1. 安装本机服务

需要 Python 3.10+，建议 3.11+。命令在仓库根目录运行；插件包不包含 Python 运行环境。Windows 不必激活虚拟环境，因此也不必修改 PowerShell 执行策略。

```powershell
git clone https://github.com/aldington-david/linuxdo-mcp.git
cd linuxdo-mcp
$runtime = Join-Path $env:LOCALAPPDATA 'linuxdo-mcp\venv'
python -m venv $runtime
$pythonPath = Join-Path $runtime 'Scripts\python.exe'
& $pythonPath -m pip install --upgrade pip
& $pythonPath -m pip install .
```

Windows 若仓库路径含中文，建议把虚拟环境放在 `%LOCALAPPDATA%/linuxdo-mcp/venv` 等纯英文路径；实测 curl_cffi 在中文证书文件路径下可能报 curl 77。为该环境安装本项目，打包时传入它的 Python 绝对路径即可，不要关闭证书校验。

macOS/Linux 可以 `python3 -m venv .venv` 后用 `.venv/bin/python` 代替本文的 `& $pythonPath`。本文使用普通安装；改过源码后需要重新 `pip install .`。下文沿用 `$pythonPath`；重开 PowerShell 后先执行 `$pythonPath = Join-Path $env:LOCALAPPDATA 'linuxdo-mcp\venv\Scripts\python.exe'`。Windows 中文目录下的某些 Python 3.11 环境可能无法正确加载 editable 安装的 `.pth`，故不建议在这里使用 `pip install -e .`。

## 2. 配置独立 Cookie

用独立浏览器 profile 或隐身窗口登录 Linux.do，在开发者工具的 Application / Storage → Cookies → `https://linux.do` 找到 `_t`。只复制该值，不需要整串 Cookie。不要从持续使用的主浏览器会话取值；浏览器和 MCP 共用滚动凭证可能互相顶掉登录。导出后不要继续使用该独立会话，也不要点击“退出登录”主动撤销它。

在本机终端执行：

```powershell
& $pythonPath -m linuxdo_mcp.server --configure-cookie
```

隐藏输入支持裸 token 或 `_t=...`，也支持浏览器展示的解码值；程序会保留已有转义并补齐 Cookie 的 URL 编码。输入不回显，请只粘贴一次后回车；写入后立即退出，不发网络请求。缓存默认在 `%USERPROFILE%\.cache\linuxdo-mcp\cookie.json`，不在仓库或 OneDrive 内。不要把 Cookie 放进聊天、GitHub、插件 ZIP 或共享配置。

此文件是明文凭证。Unix 上使用目录 700 / 文件 600；Windows 的实际访问权限取决于 NTFS ACL，`chmod(600)` 不等于设置 Windows ACL。需要限制为当前 Windows 用户时，可在缓存生成后执行：

```powershell
$cookieDir = Join-Path $env:USERPROFILE '.cache\linuxdo-mcp'
$currentSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
icacls $cookieDir /inheritance:r /grant:r "*${currentSid}:(OI)(CI)F"
```

如果指定了 `LINUXDO_CACHE_DIR`，应对实际目录设置权限。同一电脑的多个新版 MCP 进程可共用此缓存。每个请求持有跨进程锁直到轮换或失效处理结束，等锁超过 30 秒会明确报忙；进程退出后系统释放锁。不要在服务运行时删除 `cookie.lock`，也不要让仍在使用的浏览器共用这个独立登录。

凭证优先级为：有效缓存 → `LINUXDO_COOKIE` 环境变量 → 显式开启的浏览器读取。缓存优先是为了继续使用轮换后的新 token。更新失效凭证时可双击根目录 LinuxDo.cmd 选择“更新 Cookie”，或用 `--configure-cookie`；只有身份验证成功才替换缓存，下次请求立即使用新值，无需重启。仅修改环境变量不会覆盖仍有效的缓存。Windows 安装、授权、后台启动和自启见 [统一管理脚本说明](MANAGE-WINDOWS.md)。

自动读取浏览器是可选功能，默认关闭。Windows 不支持自动解密 Chrome 系 Cookie；可手动配置，或在确认使用专用会话后设置 `LINUXDO_READ_BROWSER=1`、`LINUXDO_BROWSER=firefox`。macOS/Linux 的 Chrome profile 用 `LINUXDO_CHROME_PROFILE` 选择。手动配置不需要打开这些选项。

## 3. Codex 自动启动与本机验证

默认插件使用 stdio。Codex 初始化 MCP 时会启动 Python 子进程，进程随客户端会话管理，无需开服务器终端、监听端口或配置开机任务。先验证已安装的 Python 包：

```powershell
& $pythonPath scripts/check_connection.py
& $pythonPath scripts/check_connection.py --live --query 'Codex order:latest'
```

脚本默认自动启动 stdio 服务。第一条只初始化并发现工具；第二条才会调用 `whoami`、`search`，有结果时再用 `get_topic` 读前三条可见帖子。它不输出 Cookie 或帖子正文。

生成适用于本机的插件包时，将虚拟环境 Python 的绝对路径写入包内配置，避免 Codex 找到另一个 Python：

```powershell
$pythonPath = Join-Path $env:LOCALAPPDATA 'linuxdo-mcp\venv\Scripts\python.exe'
& $pythonPath scripts/package_plugin.py --python $pythonPath
```

按第 6 节安装后，新对话会使用插件配置自动启动进程；配置了插件不代表现有对话已加载。不要再额外注册一份同名 HTTP MCP。若移动或删除虚拟环境，需重新打包并安装。Cookie 与插件安装目录分开，更新插件不需要重填仍有效的 Cookie。

HTTP 仍保留用于需要它的客户端，但不是默认路径：

```powershell
& $pythonPath -m linuxdo_mcp.server --transport streamable-http
# 另一个终端：
& $pythonPath scripts/check_connection.py --url http://127.0.0.1:8787/mcp
```

`--host` 只接受回环地址，`--port` 默认 8787，SDK 的 Host/Origin 检查仍然保留。

## 4. 连接 Secure MCP Tunnel

ChatGPT 网页不能直接访问你电脑的 `127.0.0.1`。个人使用推荐官方 Secure MCP Tunnel：本机主动建立出站连接，无需开放路由器入站端口。它支持 stdio 和 HTTP，这里使用与 Codex 相同的 stdio 入口。[官方说明](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)

必需条件是：ChatGPT 开发者模式可用；Platform 中能够创建或使用 Tunnel；Tunnel 与目标 ChatGPT workspace 关联；准备运行 Tunnel 的 runtime API key。Platform 的 Tunnel 权限与 ChatGPT 开发者权限分开，不能只凭订阅名称推断账户已经具备这些权限。

1. 在 [Platform Tunnels](https://platform.openai.com/settings/organization/tunnels) 创建 Tunnel 并取得真实 `tunnel_id`。
2. 从该页面或 [官方最新发行版](https://github.com/openai/tunnel-client/releases/latest) 下载适合系统的 `tunnel-client`，按发布的 SHA256SUMS 核对文件。不要把二进制或 API key 放进仓库。
3. 在 PowerShell 终端运行下列命令。Tunnel 客户端会启动自己的 stdio MCP，不需要另开 HTTP 服务。

```powershell
# 先把 tunnel-client.exe 所在目录加入当前终端 PATH，或用绝对路径调用。
tunnel-client help quickstart
$secureKey = Read-Host 'Tunnel runtime API key' -AsSecureString
$env:CONTROL_PLANE_API_KEY = [Net.NetworkCredential]::new('', $secureKey).Password

$pythonPath = Join-Path $env:LOCALAPPDATA 'linuxdo-mcp\venv\Scripts\python.exe'
$mcpCommand = '"' + $pythonPath.Replace('\', '/') + '" -m linuxdo_mcp.server'
tunnel-client init --sample sample_mcp_stdio_local --profile linuxdo --tunnel-id YOUR_TUNNEL_ID --mcp-command $mcpCommand --health-listen-addr 127.0.0.1:8788
tunnel-client doctor --profile linuxdo --explain
tunnel-client run --profile linuxdo
```

把 `YOUR_TUNNEL_ID` 换成平台给出的 ID。API key 在当前进程环境中，不写到命令历史；不要使用 `setx` 或提交到配置文件。`init` 写入的是 `env:CONTROL_PLANE_API_KEY` 引用。已有同名 profile 时先检查原配置，不要直接加 `--force` 覆盖。

Windows 的 tunnel-client 0.0.15 会把命令里的反斜杠当作转义，因此上面的命令转为正斜杠；其预检还会误把 `-X utf8` 中的 `utf8` 当脚本，所以 Tunnel 使用 `python -m`，如需 UTF-8 则在运行前设置 `PYTHONUTF8=1`。

本地管理页是 `http://127.0.0.1:8788/ui`；`/healthz`、`/readyz` 可辅助诊断。能打开管理页只表示本机进程可访问，还要确认连接就绪。保持 `run` 运行，否则 ChatGPT 工具发现和调用会失败。

## 5. 在 ChatGPT 创建个人插件

按 [官方连接与测试步骤](https://developers.openai.com/plugins/deploy/connect-chatgpt)：打开 Settings → Security and login → Developer mode，再进入 [ChatGPT Plugins](https://chatgpt.com/plugins)，点加号新建连接。

- 名称：`Linux.do 阅读助手`。
- 描述：`搜索和阅读本人有权访问的 Linux.do 帖子与回复，返回原帖链接，仅供个人使用。`
- Connection：选择 Tunnel，选择已关联 Tunnel 或输入 `tunnel_id`。
- 本机 MCP 没有实现 OAuth，不要给它配置一个不存在的 OAuth 服务；Linux.do 登录由本机独立 Cookie 完成，Tunnel 访问受平台权限控制。

创建后检查是否发现全部 13 个工具。从个人插件列表安装，打开新的 Work 对话，用 `@` 选择插件。先让它调用 `whoami`，确认账号；再搜索和读帖。创建连接并不等于完成网站登录测试。[个人插件 Quickstart](https://developers.openai.com/plugins/quickstart)

如果账户没有 Tunnel 或开发者入口，应先解决对应权限。本实现没有公网 OAuth；不要直接用 ngrok 暴露这个带个人 Cookie 的无鉴权服务来绕过权限问题。

## 6. 绑定 Skill 和安装本机插件包

服务本身通过 MCP `instructions` 提供基础搜索、读帖、分页和引用规则；只有连接 MCP 也能使用。打包的 `linuxdo-research` Skill 还包含何时触发、如何处理分歧、提示注入及权限失败。

ChatGPT 注册连接后，从插件页面 URL 复制技术 ID，官方示例以 `plugin_asdk_app` 开头。这不是 Tunnel ID，也不是 API key。[官方打包规范](https://developers.openai.com/plugins/build/plugins)

```powershell
& $pythonPath scripts/package_plugin.py --app-id plugin_asdk_app_YOUR_REAL_ID
```

如果更新的是 ChatGPT 自动创建的现有插件，先在详情页的 More actions → Download plugin ZIP 下载当前包，从其中 `.codex-plugin/plugin.json` 读取 `name`，再保留这个技术名称打包：

```powershell
& $pythonPath scripts/package_plugin.py --app-id plugin_asdk_app_YOUR_REAL_ID --plugin-name dev-existing-id
```

`dev-existing-id` 要换成下载包里的真实 `name`，不是界面显示名称。随后在原插件详情页选择 More actions → Upload new version，上传生成的 ZIP；这是已实际验证的网页更新入口。若浏览器扩展没有本地文件访问权限，可直接手动选择 ZIP，不必扩大扩展权限。`plugin_asdk_app_...` 会自动转换为连接映射需要的 `asdk_app_...`。

生成的 ZIP 包含 `.app.json` 连接映射、Skill 和清单，移除了本机 stdio MCP 配置。连接 ID 没有写回源码。不要把别人创建的 ID 或测试 ID 当作自己的连接；打包程序只校验格式，无法证明此 ID 在账户中有效。

本机 Codex 使用下面的包，由 Codex 管理 stdio 进程：

```powershell
& $pythonPath scripts/package_plugin.py --python $pythonPath
```

安装带 Skill 的本地包使用个人 marketplace。若已有个人 marketplace，先备份，再追加条目，不能覆盖原文件。可以在 Codex 使用 `$plugin-creator`，或 ChatGPT Work 使用 `@plugin-creator`，让它把解压后的现有插件登记进个人 marketplace；提供插件目录，明确要求保留现有插件内容。只有 ChatGPT 注册连接的绑定包用于云端 Work；本机包里的 Python 路径必须在执行插件的电脑上存在。

手动安装的新环境可以按以下结构放置（不要把它直接覆盖到已有配置）：

```text
用户目录/
├─ .agents/plugins/marketplace.json
└─ plugins/linuxdo-mcp/       ← 将所选 ZIP 解压到此处
   ├─ plugin.json
   ├─ .codex-plugin/plugin.json
   └─ skills/...
```

全新 `marketplace.json` 示例：

```json
{
  "name": "personal",
  "interface": {"displayName": "Personal"},
  "plugins": [{
    "name": "linuxdo-mcp",
    "source": {"source": "local", "path": "./plugins/linuxdo-mcp"},
    "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
    "category": "Productivity"
  }]
}
```

`source.path` 相对于 marketplace 根目录（这里是用户目录），不是 `.agents/plugins`。默认个人 marketplace 会自动发现，无需 `marketplace add`。重启桌面应用，在插件目录选择 Personal 来源并安装，再用新对话验证。可用当前 Codex CLI 的 `codex plugin add linuxdo-mcp@personal` 安装。网页端直接创建的 MCP 个人插件与本机 marketplace 是不同入口，不能声称 GitHub push 后网页就会自动安装 Skill。

## 7. 日常使用与环境变量

可以这样提问：

- “去 L 站查一下过去一个月 Codex 长上下文的实际体验，读正文和关键回复，区分版本差异并附来源。”
- “读这个话题，继续翻页，分别列出楼主结论和有证据的反对意见。”
- “看看 L 站本周热门讨论，保留完整标题、分类和链接。”

搜索不是全站爬取；每次优先 1 页，找到候选后再读帖。搜索页码从 1 开始，话题列表从 0 开始。`get_topic` 的 `start` 指可见帖子流位置，按 `next_start` 继续；真实楼号在 `floor` 和每条 `url` 中。

| 环境变量 | 用途 |
|---|---|
| `LINUXDO_COOKIE` | 首次导入独立 `_t`；有效缓存优先 |
| `LINUXDO_CACHE_DIR` | 缓存目录，默认用户目录下 `.cache/linuxdo-mcp`；保持在仓库和同步盘之外 |
| `LINUXDO_COOKIE_TTL` | 缓存有效期，默认 2592000 秒（30 天） |
| `LINUXDO_READ_BROWSER` | 默认 0；明确置 1 才读取浏览器 |
| `LINUXDO_BROWSER` | 默认 chrome，可选 chromium / brave / slack / firefox；平台支持不同 |
| `LINUXDO_CHROME_PROFILE` | macOS/Linux 的 Chrome 系 profile 目录名或显示名 |
| `LINUXDO_IMPERSONATE` | curl_cffi 模拟的指纹，默认 chrome；具体支持值取决于所装版本 |
| `CONTROL_PLANE_API_KEY` | 仅供 tunnel-client 使用，不是 Linux.do Cookie |

项目不会自动读取 `.env`。环境变量要在启动服务前设置；环境变更后重启。续期不保证永久有效，站点撤销会话、账号退出、缓存过期等仍需要重新配置。

## 8. 排错、更新与停用

| 现象 | 处理 |
|---|---|
| 未配置 Cookie / 401 | 本机运行 `--configure-cookie`；401 会清失效缓存 |
| 403 | 可能是账号等级不足或站点策略；保留缓存，不连续重试 |
| Cloudflare 拦截 | 内部最多尝试 3 次；停止连续调用，检查站点和网络，不保证指纹模拟必然通过 |
| 429 | 已被限流，降低频率，稍后再试 |
| MCP 可连接，ChatGPT 不可用 | 检查 Tunnel 就绪、workspace 关联、权限与客户端持续运行情况 |
| HTTP 421 / Origin 403 | 核对是否通过正确 localhost 地址转发；不要关闭 Host/Origin 防护 |
| `pip` 证书验证失败 | 使用可信的系统证书 / 组织 CA；更新虚拟环境内 pip，不用关闭 TLS 验证 |
| 更新后看不到新工具 | 重新安装 Python 包、重启 MCP，在 ChatGPT 连接中 Refresh，并开新对话 |

升级前先保存自己的修改：`git status` 确认工作区，再 `git pull --ff-only`；运行 `pip install .` 和测试。插件包需要重新生成和安装；更新已安装本机插件时，可用 `$plugin-creator` 的 cachebuster / 重装流程。更新服务器不会自动更新已打包的 Skill。

停用时禁用 Codex 插件并结束其会话；若运行了 Tunnel，则 Ctrl+C 结束它，关闭终端以释放当前环境变量；在 ChatGPT 或 Codex 禁用/移除插件。需要撤销登录时在 Linux.do 的账号会话管理中撤销独立会话，再删除实际缓存目录里的 `cookie.json`；不要删除其他浏览器会话。具体版本回滚见 [ROLLBACK.md](ROLLBACK.md)。
