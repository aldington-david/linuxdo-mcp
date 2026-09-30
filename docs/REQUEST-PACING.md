# Linux.do 请求间隔与限流

适用版本：0.6.4。调研日期：2026 年 10 月 1 日。

默认已启用实际论坛请求的随机间隔。本地 Codex、OpenAI Tunnel 和 VPS 中的服务器都使用同一实现；同一台机器上，使用同一个 Cookie 缓存目录的进程（包括同一 Docker 部署内共享数据卷的容器），共用一份节奏与冷却状态。

## 默认值

| 项目 | 默认行为 |
|---|---|
| 所有论坛请求 | 两次请求开始时间至少相隔一次随机抽取的 **1.0–1.8 秒** |
| 搜索请求 | 两次 `/search.json` 请求开始时间还须相隔随机抽取的 **2.2–3.2 秒** |
| 空闲后的第一条请求 | 没有未结束的冷却时，不额外等待 |
| 请求本身已经很慢 | 网络耗时计入间隔，不再额外完整等待一遍 |
| 429 | 立即结束当前请求并共享冷却；优先遵循 `Retry-After`，缺失或无效时默认 60 秒 |
| Cloudflare 验证页 | 停止继续访问，默认共享暂停 120 秒；不会自动尝试解验证或换身份 |

搜索限制与普通限制取较晚的可发送时间，不相加。原来搜索翻页的 0.6 秒、补读批次的 0.4 秒等待已移除，避免叠加。登录检查、Cookie 候选验证和网络错误后的重试，也经过同一个底层入口。

冷却期间的后续调用会直接说明剩余等待时间，不占着工具等一分钟，也不会偷偷再发请求。收到 429 或验证页不会因此清除 Cookie、要求更换密钥或自动重试。冷却结束只代表可以再次尝试，不保证站点会放行。

## 为什么选这个范围

上游 `mrsxs/linuxdo-mcp` 当前基线仍只有搜索翻页 0.6 秒、补读批次 0.4 秒，以及请求异常的重试等待，没有覆盖所有实际请求的全局节流。[上游实现](https://github.com/mrsxs/linuxdo-mcp/blob/d4c007aab787fe5d3d2d2f5d52197533fb469a35/src/linuxdo_mcp/server.py)

Discourse 默认将已登录用户的搜索限制设为每分钟 30 次。因此本项目把连续搜索单独放慢到平均约 2.7 秒一次，给这个默认值留出余量。**这不是 Linux.do 当前配置的证明**；管理员可以调整限制，同账号浏览器或其他程序的搜索也可能消耗服务端额度。[默认设置](https://raw.githubusercontent.com/discourse/discourse/main/config/site_settings.yml) · [搜索限制实现](https://raw.githubusercontent.com/discourse/discourse/main/app/controllers/search_controller.rb)

没有查到 Linux.do 公开承诺的“最佳类人间隔”。普通请求的 1.0–1.8 秒是本项目兼顾使用速度与减少突发流量的工程默认值，不是经过全站压测得到的最优值。随机等待只能平滑请求；Cloudflare 还会参考请求头、会话和浏览器信号，不能把随机间隔当作真人证明或放行保证。[Cloudflare 检测说明](https://developers.cloudflare.com/bots/concepts/bot-score/)

429 表示服务端认为请求过多；其 `Retry-After` 应优先于本地默认值。本实现支持秒数和 HTTP 日期，并在有 `Date` 响应头时用服务端时间差减少时钟偏差。[429 官方说明](https://developers.cloudflare.com/support/troubleshooting/http-status-codes/4xx-client-error/error-429/)

速度示例：假设每个 HTTP 请求耗时 0.3 秒、间隔取区间中点，空闲后的一页搜索仍约 0.3 秒；连续五页搜索约 11.1 秒；从首批 20 条补齐到 100 条帖子约 5.9 秒。这是说明机制的计算示例，不是对实际网络耗时的承诺。日常先搜一页、只读相关话题，通常不需要等待多页抓取。

## 如何调整

默认值直接生效，不必设置环境变量。需要调整时，在实际 Cookie 缓存目录中创建 `request-policy.json`，内容参考 [默认模板](request-policy.example.json)：

- Windows 默认路径：`%USERPROFILE%\.cache\linuxdo-mcp\request-policy.json`。
- VPS 容器默认路径：`/data/request-policy.json`，由现有数据卷保存。
- 设置了 `LINUXDO_CACHE_DIR` 时，文件放在该目录中。

```json
{
  "min_seconds": 1.0,
  "max_seconds": 1.8,
  "search_min_seconds": 2.2,
  "search_max_seconds": 3.2,
  "rate_limit_cooldown_seconds": 60.0,
  "challenge_cooldown_seconds": 120.0
}
```

可以只填写想调整的字段，其他字段沿用默认值。普通间隔允许 0.2–30 秒，搜索下限不能低于普通下限，两组上限均须不小于各自下限；冷却配置允许 1–3600 秒。降低数值不表示论坛允许相应频率。服务器明确要求的更长 `Retry-After` 不会被本地冷却配置截短。

Windows 可以将模板复制到上述目录后编辑。VPS 可将编辑好的文件复制到当前部署的 MCP 容器 `/data/request-policy.json`，确保运行用户可读；HTTP 服务与 Tunnel 共享数据卷时会读到同一文件。保存后，已运行的 **0.6.4 及更新版本**在下一个请求读取新配置；不用重填 Cookie。配置错误会明确停止请求，不会悄悄退回无间隔访问。

`request-state.json` 是自动维护的时间戳状态，不含 Cookie、搜索词或帖子内容。不要把它当成配置编辑，也不要通过删除它跳过服务端冷却。原来的凭证锁同时协调发送顺序，不增加常驻进程、系统任务或新的外网检查。

首次从旧版本升级，需要让 MCP 进程重新加载：本地可重启 Codex，Tunnel 重启其已有 runtime，VPS 运行部署脚本重新构建。仅更新磁盘上的程序不会改变仍在运行的旧进程；上述“保存配置即生效”适用于已经运行 0.6.4 的进程。

## 与 VPS 入口限流的区别

VPS 的 `LINUXDO_REQUESTS_PER_MINUTE` 和 `LINUXDO_MAX_INFLIGHT` 限制客户端调用 HTTP MCP；本节控制的是服务器实际访问 Linux.do 的请求，包含 stdio 和 Tunnel 路径。两层同时生效，职责不同。

不同电脑或 VPS、不同缓存目录之间不自动共享预算；本插件也无法限制浏览器或其他程序的流量。不要把同一登录会话复制到多个独立部署。需要更保守时提高间隔，而不是并行增加客户端抵消等待。
