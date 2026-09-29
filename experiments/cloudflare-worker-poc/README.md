# Workers TLS 调查与最小云端实验

研究与测试：2026-09-29 至 2026-09-30（新加坡时间）。

**2026-09-30 更新：第二轮 GitHub 调查仍未找到合适的现成替代，已按用户要求撤除本次 Cloudflare 测试 Worker、独立存储及测试授权。既有业务核对未变。源码保留用于复查，不代表当前有在线测试服务。** 详见 [第二轮调查与回退结果](GITHUB-FOLLOWUP.md)。

## 结论

未找到能在纯 Cloudflare Workers 中直接替代 `curl_cffi`、并适用于 Linux.do 的成熟 Chrome TLS 指纹模拟方案。已新建真正的云端 Worker 进行验证；部署、鉴权和独立 SQLite Durable Object 运行正常，但原生 `fetch` 的匿名请求和携带独立 `_t` 的登录验证请求均被 Linux.do 的 Cloudflare 防护拦截。

因此，目前不能把纯 Workers 方案当作已经可用的免费替代。没有迁移 ChatGPT 插件或改动现有 OpenAI Tunnel。不能把这次 403 解释为 Cookie 已失效，也不能仅凭 403 认定原因一定是 TLS 指纹。

## TLS 方案调查

| 路线 | 结论与证据 |
|---|---|
| `curl_cffi` / curl-impersonate | Python CFFI 绑定本机 libcurl；现有发行包不能原样放入 Workers Python/Pyodide。它能模拟 TLS 与 HTTP/2，但不是纯 JavaScript 库。[项目说明](https://github.com/lexiforest/curl_cffi) |
| Workers `fetch` / `node:https` | 没有 Chrome 指纹档位。`node:https` 基于平台 `fetch`，不能用 Agent 获得等价于本机 Node 的底层 TLS 控制。[官方说明](https://developers.cloudflare.com/workers/runtime-apis/nodejs/https/) |
| Workers `node:tls` | 现在支持部分客户端 API，包括 connect/TLSSocket；不能笼统说完全不支持 TLS。支持 TLS 连接本身不等于提供 curl-impersonate 的 Chrome ClientHello。[官方说明](https://developers.cloudflare.com/workers/runtime-apis/nodejs/tls/) |
| `subtls` | 纯 TypeScript TLS 1.3 实现，可作为研究基础；只有有限算法组合，作者明确标为实验、未满足完整协议及生产使用要求，不是现成 Chrome 模拟器。[项目说明](https://github.com/jawj/subtls) |
| `@reclaimprotocol/tls` | 支持 TypeScript/WebCrypto 的 TLS 1.2/1.3，并允许指定密码套件；仍需由调用者提供底层网络读写，未找到开箱即用的 Chrome 档位承诺。[项目及用法](https://github.com/reclaimprotocol/tls) |
| `tls-client` / CycleTLS | 具备浏览器指纹能力，但核心是 Go 客户端/运行组件，不能因提供 JavaScript 调用入口就认为它是 Workers 原生库。[tls-client](https://github.com/bogdanfinn/tls-client)、[CycleTLS](https://github.com/Danny-Dasilva/CycleTLS) |

自实现 TLS 还遇到一个更直接的限制：Workers 的原始 TCP sockets 禁止连接 Cloudflare IP 段。本次本机 DNS 查询 Linux.do 得到 `104.20.16.234` 和 `172.66.166.61`，均落在官方 Cloudflare 地址段。即使移植纯 JS TLS，也不能通过这条原始 TCP 路径直接连到当前 Linux.do 前端。增加外部 TCP/HTTP 代理会引入另一台服务，不再满足“只用 Worker、没有常开电脑或外部主机”的条件。

来源：[TCP 限制](https://developers.cloudflare.com/workers/runtime-apis/tcp-sockets/)、[官方 IP 地址段](https://www.cloudflare.com/ips-v4)。DNS 是本次观测，未来可能变化；本次没有在云端尝试绕过 TCP 限制。

## 云端实测

本次使用已有账户的 Workers Free 套餐；页面明确显示“免费 / 当前套餐”。新建独立 Worker 和只属于它的一个 SQLite Durable Object。只使用 workers.dev，未绑定域名、路由、定时任务、外部代理或付费服务。

| 检查 | 实际结果 |
|---|---|
| Wrangler 打包、部署 | 通过，最终上传包约 7.41 KiB，启动时间 2 ms |
| 无 Bearer 密钥调用 | HTTP 401，未进入存储及上游请求 |
| 有密钥读取状态 | HTTP 200，`configured:false` |
| 匿名读取 Linux.do `/site.json` | 上游 HTTP 403，`cf-mitigated: challenge`，HTML |
| 独立 `_t` 验证 `/session/current.json` | 上游 HTTP 403，`cf-mitigated: challenge`，HTML；候选 Cookie 未保存 |
| 只换 Chrome User-Agent 的匿名对照 | 同样 HTTP 403 + challenge；更改 User-Agent 不等于模拟 TLS |
| 登录后单页搜索、指定话题 | 因登录前置步骤被拦截，未执行真实账号搜索/读帖；接口已实现，但不能标为线上通过 |
| Cookie 轮换 | 串行处理、模拟 Set-Cookie 轮换、失败不覆盖和实例重建读取均通过本地测试；没有观察到 Linux.do 的真实轮换，不能标为真实轮换通过 |

已留存一个 `check.mjs` 可运行断言检查：缺失/错误密钥、输入边界、失败更新不覆盖、挑战分类、并发请求串行化、后续请求使用轮换 token、重建对象实例读取已保存状态。另用 Wrangler 本地 workerd 验证了 SQLite DO 创建、鉴权和 `/status`。

## 隔离与凭证

- 操作前后已核对原有 `serverless-dns`：代码内容、设置、ETag、修改时间均未变化。下载代码的 multipart 随机边界不同，去除该传输包装差异后内容完全相同。
- 原有 Pages 项目仍在；未申请 Pages、DNS 或路由写入权限，未调用这些资源的写入接口。
- 只新增一个测试 Worker 和它的 Session namespace。现有本机插件 Cookie、OpenAI Tunnel、ChatGPT 连接均未修改。
- 所有测试入口需要随机 256 位 Bearer 密钥；Cookie 只允许固定 Linux.do 路径，不接受任意代理地址，不跟随重定向，不返回 Cookie 或上游 HTML。
- 鉴权密钥及独立 OAuth profile 只保存在用户 ACL 保护的本地记录目录；项目和 Git 内没有凭证。
- Worker 最终状态为未配置 Cookie、轮换计数 0。它没有后台轮询或定时任务。

## 更新 Cookie 的操作体验

`Update-Cookie.ps1` 已提供隐藏输入：提示用户打开登录页与身份确认页，然后从开发者工具复制 `_t` 的 Value，粘贴一次即可。失败不会覆盖旧会话；防护挑战单独报告，不让用户反复换 Cookie。

本次保存的是探索性 PoC，不是可用 MCP 替代部署包。若继续追求免费云端运行，应优先验证可运行现有 `curl_cffi` 的免费环境；也需实测其出口，因为保留 Chrome 模拟并不保证云端出口被站点接受。

## 复查代码和测试

在此目录使用 Node.js 22 或以上版本运行 `npm ci`，再执行 `npm test`。测试使用模拟响应，不会访问 Linux.do，也不需要真实 Cookie。

`worker.mjs` 是 Worker 源码；`wrangler.example.jsonc` 只保留配置模板，必须填入自己的账户 ID 和一个全新的 Worker 名称，另存为 `wrangler.jsonc`。不要填已有业务名称。免费套餐下使用 SQLite Durable Objects；不要升级套餐，不要添加路由或已有资源绑定。

实际测试接口均使用 POST 和 `Authorization: Bearer <POC_TOKEN>`：

| 路径 | 请求体 | 作用 |
|---|---|---|
| `/status` | `{}` | 仅返回是否配置、验证时间及轮换计数 |
| `/probe` | `{}` 或 `{"browser_headers":true}` | 无 Cookie 请求固定的 `/site.json`；后者只替换 User-Agent |
| `/cookie` | `{"cookie":"仅 _t 的值"}` | 验证候选会话，成功才保存 |
| `/whoami` | `{}` | 验证已保存的会话 |
| `/search` | `{"q":"codex"}` | 只搜索第一页，最多返回 10 个话题 |
| `/topic` | `{"id":12345}` | 读取指定话题，最多返回前 3 条帖子；此处用实际话题 ID 替换示例 |

不要把真实 Cookie 放到命令行。更新时用 PowerShell 7 执行 `./Update-Cookie.ps1 -ClientConfig <本机配置文件路径>`，配置文件包含 `url`（自己的 workers.dev HTTPS 地址）和 `token`（与 Worker Secret POC_TOKEN 一致的随机密钥），应放在项目外并限制本机用户访问。脚本会隐藏 Cookie 输入，只记录脱敏后的验证结果。

尚未提供一键正式迁移脚本：此次云端访问前提未通过，自动迁移现有可用插件会使服务不可用。
