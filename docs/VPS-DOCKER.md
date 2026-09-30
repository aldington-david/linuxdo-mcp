# Linux VPS / Docker 部署（服务器 0.6.5）

这是独立的 VPS 部署入口；不会自动切换电脑上已安装的 Windows 版本。保留 curl_cffi 的 Chrome TLS 模拟、原有 13 个只读工具和 Cookie 轮换缓存。

## 先了解边界

| 项目 | 限制与实际含义 |
|---|---|
| OpenAI API | 本服务只读 Linux.do，不调用模型生成 API。ChatGPT/Codex 的模型和工具用量仍受各自套餐限制；不能承诺 Tunnel 无限调用或固定免费额度。 |
| 论坛访问 | 只能读取 Cookie 所属账号有权访问的内容。VPS 出口仍可能触发 Cloudflare、防刷规则或 429；保留 Chrome 模拟不保证云端放行。没有依据承诺一个固定的 Linux.do 官方调用额度。 |
| 单次查询 | 最多连续搜索 5 页；每次读帖最多 100 条，需要按 next_start 分页。一次 MCP 调用可能产生多次论坛请求。 |
| 公网 MCP | 固定 Bearer 密钥；默认每分钟 60 个已授权 HTTP 请求、最多 4 个并发，请求体约 64 KB。初始化和工具发现也计入 HTTP 请求数。此限制不代表论坛允许同等频率。 |
| 多用户/扩容 | 每个部署共用一个论坛账号，适合个人使用。密钥持有人可使用该账号的读取权限；没有多用户隔离，不支持把同一会话跨多个 VPS 横向扩容。 |
| Cookie 有效期 | 网站可随时撤销会话；本地默认 30 天缓存上限不是网站承诺。使用中接收轮换值会保存，真正失效后仍需重新登录取值。 |
| 自动检查 | 部署、脚本启动/状态检查会验证；持续使用中，距上次验证超过 5 分钟后的下一次请求检查身份。空闲不定时访问论坛，Docker 健康检查只检查进程。 |
| 防滥用范围 | 未授权请求不会到达论坛；密钥、限流和资源上限不能代替供应商的防火墙或抗 DDoS 服务。VPS root / Docker 管理员仍可读取数据卷。 |

服务器 0.6.4 起，HTTP 和 Tunnel 的实际论坛请求还共享随机间隔与冷却：普通请求 1.0–1.8 秒，搜索之间 2.2–3.2 秒。这与上表的公网 MCP 入口限流分开。配置文件位于共享数据卷的 `/data/request-policy.json`，详见 [请求节奏说明](REQUEST-PACING.md)。

0.6.5 起，每次 MCP 调用共用 45 秒工作预算，另有 50 秒返回保护，以客户端 60 秒为设计基准。分页预算不足时保留已取得的结果，并返回 `partial` 与 `next_page` / `next_start`；反向代理超时更长不会延长工具自身预算。

**ChatGPT 不能直接填写这里生成的固定 API key。** 受保护的公网 ChatGPT MCP 需要 OAuth；本版不自建 OAuth 登录系统。Codex 等支持 Bearer header 的客户端可直接连接 HTTPS，ChatGPT 则通过可选 OpenAI Secure MCP Tunnel 接入。[OpenAI 授权规范](https://developers.openai.com/plugins/build/auth)、[Codex MCP 配置](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)、[私有 Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)

## 选择部署方式

| 模式 | 需要准备 | 对外入口 |
|---|---|---|
| 自带 HTTPS | 域名 A/AAAA 正确指向 VPS，Docker/Compose，空闲 TCP 80/443 | Caddy 自动申请、续期证书，公网 `/mcp` 需要密钥 |
| 已有 HTTPS 反向代理 | 已有域名、证书及代理；添加下方 `/mcp` 转发 | 后端只映射 `127.0.0.1:19878`，公网继续用原 HTTPS |
| 仅私有 Tunnel | 有效 Tunnel ID、Runtime key、允许出站 HTTPS | 不开放公网 MCP 端口，也不要求域名 |

HTTPS 模式也可以同时启用 Tunnel。若只有公网 IP，本脚本先推荐私有 Tunnel；没有实现自动申请 IP 地址证书。已有反代模式不会替你修改 Nginx、网站或防火墙。

Docker 发布端口可能绕过 UFW 的常规过滤，不能只看 UFW 的 deny 规则。自带 HTTPS 时后端 8787 不发布到宿主机；不要额外映射为 `0.0.0.0:8787`。云安全组和宿主机防火墙都应检查。较旧 Docker 的 localhost 端口发布也有额外限制，建议保持引擎更新。[Docker 官方说明](https://docs.docker.com/engine/network/packet-filtering-firewalls/)

## 首次部署

VPS 需要 Bash、Docker Engine 和 Compose v2。脚本不自动改装 Docker 或调整系统防火墙，避免影响已有业务。首次构建还需能访问 Docker Hub、PyPI，以及启用 Tunnel 时的 GitHub 下载地址。

在交互 SSH 终端执行；不要通过 `curl | bash` 传入凭证：

```bash
git clone https://github.com/aldington-david/linuxdo-mcp.git
cd linuxdo-mcp
bash linuxdo.sh setup
```

脚本会依次询问入口模式、域名、是否启用 ChatGPT Tunnel，构建需要的镜像，初始化访问密钥，检查/引导 Cookie，最后启动容器。除初次浏览器登录/平台授权外，不需要进入容器编辑配置。

使用自带 HTTPS 时放行 **入站 TCP 80、443**，保留正常 SSH 管理端口；不需要公网开放 8787、8788 或 Caddy 管理端口。Caddy 在容器里以非 root 用户监听 8080/8443，由 Docker 映射到外部 80/443。[Caddy HTTPS 机制](https://caddyserver.com/docs/quick-starts/https)

`up --wait` 成功表示容器进程就绪，不等于公开证书、VPS 外部网络和 ChatGPT 调用已全部验收。若证书尚未就绪，检查 DNS、80/443 和 Caddy 日志。

工程资源建议：单入口可从 1 GB 内存评估；MCP＋HTTPS＋Tunnel 三个服务建议预留约 2 GB，更稳妥。默认容器内存上限分别为 512/256/512 MB，不是官方最低需求，也不是实际常驻占用。

## Cookie：只在 SSH 终端隐藏粘贴

首次需要凭证时脚本会提示；以后更新只运行：

```bash
bash linuxdo.sh cookie
```

1. 在自己的电脑新开独立/隐身窗口，打开 `https://linux.do/login` 登录。
2. 在同一窗口打开 `https://linux.do/session/current.json`，确认有 `current_user`。
3. F12 → Application（应用程序）/存储 → Cookies → `https://linux.do`。
4. 复制 `_t` 的 **Value**，在 SSH 提示处只粘贴一次并回车。不复制整串 Cookie，不发到聊天。

VPS 必须使用独立于仍在运行的电脑插件的新会话。取值后可关闭窗口，不要点“退出登录”，也不要继续用这个会话浏览。

宿主机脚本隐藏输入，通过标准输入传入 `docker compose exec -T` 或一次性维护容器；容器内部不需要 TTY，不会把值作为命令参数。候选 Cookie 会先访问身份接口，成功才原子替换；失败保留旧值。更新后新请求立即生效，无需重启服务。

Cloudflare 验证页、普通 403、429 和网络错误会分别提示；它们不等于 Cookie 失效。VPS 访问被防护拦截时不要反复换 Cookie。

## 连接 Codex

运行 `bash linuxdo.sh client`，在终端查看 HTTPS MCP 地址和访问密钥。密钥只在此显式操作时显示，使用 `docker exec` 输出，不写入服务日志。

在运行 Codex 的电脑设置 `LINUXDO_VPS_TOKEN`，然后添加连接：

```bash
codex mcp add linuxdo-vps --url https://你的域名/mcp --bearer-token-env-var LINUXDO_VPS_TOKEN
```

Windows 可在 PowerShell 隐藏输入并保存为当前用户环境变量（此环境变量不是加密存储，需要保护本机账户）：

```powershell
$secret = Read-Host '粘贴 VPS MCP 访问密钥' -AsSecureString
[Environment]::SetEnvironmentVariable('LINUXDO_VPS_TOKEN', [Net.NetworkCredential]::new('', $secret).Password, 'User')
$secret.Dispose()
```

随后重启 Codex 以读取新环境变量，并在新对话测试 whoami、search、get_topic。不要把密钥放进 URL、公开插件 ZIP 或 Git。若决定完全迁移，再停用旧本机连接，避免两个同类入口混用；本脚本不修改你电脑的现有插件。

## 可选：连接 ChatGPT

在 `https://platform.openai.com/settings/organization/tunnels` 为 VPS 准备独立 Tunnel，并关联自己的目标工作区；生成仅需 Tunnels Read + Use 的 Runtime key。首次平台登录、工作区授权和创建连接仍由用户完成，不能用一个运行密钥代替这些权限。

已有电脑 Tunnel 仍在运行时，不要给 VPS 填同一个 ID。若要迁移旧 ID，先停电脑通道再启动 VPS；否则请求可能落到不同后端。

脚本提示时粘贴 ID 和 key，或以后运行：

```bash
bash linuxdo.sh tunnel-key
```

key 先通过只读元数据查询验证，再保存到数据卷的私有文件；这还不能代替实际调用验收。启用的通道容器重启后读取新 key。然后在 ChatGPT 个人插件连接中选择该 Tunnel，实际调用 whoami、搜索一页并读一个话题。

Tunnel 容器通过 stdio 使用原 MCP，入口由 OpenAI 组织/工作区授权保护；公网 HTTP 的 60 请求/分钟限制不作用于这条私有通道。它与 HTTP 服务在同一 VPS 上共享 Cookie 数据卷和文件锁。Tunnel 适用于个人/私有连接，不能当作公开插件目录发布方案。

## 日常维护与回退

| 命令 | 作用 |
|---|---|
| `bash linuxdo.sh` | 显示菜单 |
| `bash linuxdo.sh setup` | 构建/更新并启动，保留已有有效凭证 |
| `bash linuxdo.sh start` | 检查登录和通道后启动 |
| `bash linuxdo.sh status` | 查看容器并实际检查论坛登录 |
| `bash linuxdo.sh cookie` | 隐藏粘贴新 Cookie，验证后保存 |
| `bash linuxdo.sh tunnel-key` | 更新可选 Tunnel key |
| `bash linuxdo.sh client` | 显示客户端 URL 和 MCP 密钥 |
| `bash linuxdo.sh rotate-token` | 轮换公网 MCP 密钥，旧值不再接受新请求 |
| `bash linuxdo.sh logs` | 查看最近 100 行服务日志 |
| `bash linuxdo.sh stop` | 只停止本项目，保留数据卷 |

先保存自己的源码改动，再 `git pull --ff-only`，运行 setup 更新。脚本在 `.local/vps/backups/` 留存部署配置与原镜像记录，在 operations.log 记动作；不会自动更新所有 Docker 项目，也不会运行 system prune。

Cookie、MCP key、Tunnel key 放在本项目 `data` 命名卷，文件权限为 0600，进程 UID 为 10001。Linux 这里是权限保护的明文文件，不是 Windows DPAPI 加密；备份数据卷相当于备份凭证，不能公开上传。容器重建/重启不会删除它们。

默认设置：只读根文件系统、临时目录 tmpfs、cap_drop=ALL、禁止提权、CPU/内存/PID 上限、日志轮转、关闭浏览器 Cookie 读取。公开入口没有更新 Cookie、执行命令或读取文件的管理接口。

停止不用 `down -v`，不要把旧 Cookie 备份恢复覆盖已轮换会话。HTTPS 证书卷也应保留，避免重复签发触及 CA 额度。真正撤销论坛会话和 Tunnel key，要到对应网站操作。

## 已有 Nginx 的转发示例

只添加到你选定域名的现有 HTTPS server 中，勿整段覆盖现有网站配置：

```nginx
location = /mcp {
    client_max_body_size 64k;
    client_body_timeout 20s;
    proxy_pass http://127.0.0.1:19878/mcp;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header Authorization $http_authorization;
    proxy_buffering off;
    proxy_read_timeout 180s;
}
```

## 验证范围

本次在本机 Docker Linux/amd64 环境测试。HTTP 与启用证书校验的 HTTPS 使用合成密钥和虚拟论坛数据验证，测试 CA 只交给测试客户端，没有安装到系统信任库。没有用真实 Cookie 冒充目标 VPS 登录测试。

真实 VPS 的出口、域名 DNS、公有 CA 签发、工作区关联和实际 ChatGPT 调用，需要在目标机部署后验收。Dockerfile 提供 amd64/arm64 的依赖和官方 Tunnel 下载选择，但本次没有声称完成 arm64 运行验收。
