# GitHub 第二轮调查与 Cloudflare 回退

日期：2026-09-30。用户要求再次寻找适用于 Workers 的 Chrome TLS 指纹项目；若没有合适方案，则仅回退此次实验，不影响原有业务。

## 筛选条件与结论

需要同时满足：能部署到 Cloudflare Workers 免费运行时；真正控制出站 TLS/HTTP 指纹；可用于 Linux.do；不依赖额外常开主机、外部代理或付费容器。不能把 npm/TypeScript 接口等同于纯 JavaScript，也不能把“可编译为 WASM”或“本地 workerd 测试通过”等同于云端可连接。

本轮搜索并进一步核对 README、支持矩阵和关键源码后，仍未找到满足以上条件的现成 GitHub 项目。这是对已调查项目的适用性结论，不是证明所有可能实现都不存在。本次没有安装这些候选包，也没有再次上传 Cookie 或创建云资源。

## 重点候选

| 项目 | 核查结果 | 不满足之处 |
|---|---|---|
| [lexiforest/impers](https://github.com/lexiforest/impers) | curl_cffi 作者的 Node.js 绑定；文档明确要求 libcurl-impersonate，首次启动下载本机库 | JavaScript 接口背后依赖原生 libcurl，不是 Workers 原生替代 |
| [sqdshguy/wreq-js](https://github.com/sqdshguy/wreq-js) | Rust/BoringSSL + NAPI-RS；文档列出各操作系统的预编译原生二进制 | 不能将本机 Node 原生插件直接加载到 Workers |
| [httptoolkit/node-tls-impersonate](https://github.com/httptoolkit/node-tls-impersonate) | 能构造 ClientHello，并接入 Node tls.SecureContext；依赖原生模块及现代 Node 内部能力 | Workers 的部分 Node API 兼容不提供等价的原生模块/Node 内部接口 |
| [hdbg/chromimic](https://github.com/hdbg/chromimic) | README 同时写 Chrome 模拟和 WASM；实际检查 [src/wasm/client.rs](https://github.com/hdbg/chromimic/blob/main/src/wasm/client.rs) 后，WASM 请求最终调用宿主 fetch | WASM 路径没有保留本机 TLS 模拟能力，放进 Workers 仍由平台控制出站 TLS |
| [jedisct1/boringssl-wasm](https://github.com/jedisct1/boringssl-wasm) | 构建目标是 BoringSSL 加密库 `libcrypto.a` | 并非现成的 Chrome TLS/HTTP 客户端，也没有解决 Workers 对 Linux.do 的出站网络限制 |
| [currentspace/http3](https://github.com/currentspace/http3) | quiche/BoringSSL 的 WASM 协议核心可在 workerd 验证；[WASM_RUNTIME.md](https://github.com/currentspace/http3/blob/main/docs/WASM_RUNTIME.md) 明确写尚不能部署到 Workers，缺少出站 UDP 接口 | 本地核心验证不等于云端完成连接；也不是已提供 Chrome 指纹档位的替代包 |
| [danlapid/rust-workers-quic](https://github.com/danlapid/rust-workers-quic) | Rust/WASM HTTP/3 PoC 在 Node.js 上完成真实网络请求，README 明确把云端 Workers 排除在本次实现范围外 | 名称含 Workers，实际交付仍是 Node.js PoC |

结合上轮已核对的 [subtls](https://github.com/jawj/subtls)、[@reclaimprotocol/tls](https://github.com/reclaimprotocol/tls)、[tls-client](https://github.com/bogdanfinn/tls-client) 和 [CycleTLS](https://github.com/Danny-Dasilva/CycleTLS) 路线，本轮检索仍未发现能消除既有部署/网络限制的现成 Workers 适配。外部 Python/Chrome 代理案例依赖另一处服务，不满足此次纯 Workers 条件。

两个源码复查点的 Git blob SHA：chromimic `src/wasm/client.rs` 为 `db5bb2cd846ede8f43ccb975248d590311bc49c6`；http3 `docs/WASM_RUNTIME.md` 为 `f20207768482d4c587016943ad08957946765c77`。用于标明本次实际读取版本，未来项目能力可能变化。

## 平台限制仍然存在

Cloudflare 当前官方文档仍禁止原始 TCP sockets 连接 Cloudflare IP 段。上轮 DNS 观测显示 Linux.do 位于这些网段。因此，即使自行实现 TLS，也不能直接把这一路径用于当时的 Linux.do 前端。此处沿用上轮 DNS 观测，本轮没有重新发起 Linux.do 网络测试。

来源：[TCP sockets 限制](https://developers.cloudflare.com/workers/runtime-apis/tcp-sockets/)、[Node.js 兼容范围](https://developers.cloudflare.com/workers/runtime-apis/nodejs/)、[workerd UDP 讨论](https://github.com/cloudflare/workerd/discussions/4463)。

## 实际回退结果

- 删除前确认目标是本次创建的测试 Worker，运行版本与实验记录一致；没有其他服务的 incoming 绑定、域名引用、tail 消费者或外部 Durable Object 引用。
- 用官方删除 Worker API、`force=false` 精确删除 `linuxdo-mcp-poc-20260929-k7m4`。没有使用强制删除，也没有修改其他资源。
- 云端重新列举确认：测试 Worker 已移除，它实现的 Session Durable Object namespace 已移除；账户仅剩原有 `serverless-dns` Worker，namespace 数量恢复为 0。
- 原有 `serverless-dns` 代码、完整设置、ETag 和修改时间在删除前后完全一致。账户 workers.dev 子域保持不变。未操作 Pages、DNS、域名、路由、套餐或现有 OpenAI Tunnel/ChatGPT 插件。
- 控制台复核显示只剩原有 `incites` Pages 项目和 `serverless-dns` Worker，两者仍显示既有部署时间；已留存截图。
- 撤销并删除本次独立 Wrangler OAuth profile；旧访问 token 再访问原本可读的 Workers API 返回 HTTP 401 / code 10000，验证失效。已移除本地对应测试密钥，未更改默认 Wrangler 登录配置。
- 保留源码、研究文档和受限权限的本地审计记录，不恢复旧快照覆盖用户现有配置。

此次 Cloudflare 实验已结束。真实站点搜索、读帖和 Cookie 轮换没有在 Workers 上验证通过；本地测试通过记录仍只代表程序逻辑检查。
