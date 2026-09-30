# 开发操作记录

## 0.6.5 整次调用时间预算（2026-10-01）

基线 5a61387。以客户端 60 秒为设计基准，统一设置 45 秒工作预算和 50 秒返回保护；使用现有 MCP 依赖中的工作线程机制与标准库单调时钟、上下文变量，不增加常驻进程或新的服务。所有 13 个工具共用同一包装入口，凭证锁、预检、分页、间隔与重试继承同一个截止时间，HTTP 超时不超过剩余预算。

搜索和读帖在正常预算耗尽时返回已取得的部分内容与续读位置，Markdown 同步提示。读帖只推进连续的已处理区间，兼容已删除帖子和非连续缓存；预算耗尽不会被分类缓存的降级逻辑吞掉。客户端取消或返回保护触发后，工作线程恢复时不得继续发起后续请求。

安装前保存并核对现有插件、启动脚本和任务备份，更新本机 0.6.5。没有修改 Cookie、Tunnel key、远程 Tunnel、Codex 全局超时、随机间隔默认值或 Windows 自启策略。完整回归与真实 45 秒离线调用结果见 VALIDATION.md。

## 0.6.4 论坛请求节奏（2026-10-01）

基线 8d254c9。核对上游 d4c007a 的固定等待、Discourse 默认搜索限制及 Cloudflare 的 429/多信号检测说明后，设置普通请求 1.0–1.8 秒、搜索之间 2.2–3.2 秒的工程默认值。未声称知道 Linux.do 私有配置或存在可保证放行的最佳间隔。

节流放在唯一论坛 HTTP 入口，复用已有 Cookie 跨进程锁；节奏文件只记录截止时间，不记录 Cookie、搜索词或正文。移除旧的分页固定等待，计入网络耗时，空闲首条直接发送。429 尊重 Retry-After 并共享冷却，验证页暂停，均不自动继续尝试；正常 JSON 文本不按验证页处理。

已备份本机插件与启动配置，安装 0.6.4、重载已有 Tunnel，更新 Docker 镜像标签及可复制配置模板。未改 TLS 指纹、代理、论坛凭证、Cloudflare 账户设置或其他服务。旧 Codex 会话需重载；详细验证见 VALIDATION.md。

## 0.6.3 凭证失效提醒（2026-09-30）

基线 b803a1a。按用户要求，将“确认凭证失效”设为静默运行的唯一自动交互例外。复用现有按需任务打开隐藏输入向导，使用不含凭证的独占提醒标记防止反复弹窗；成功更新后清除标记，关闭窗口则保持安静。

Tunnel key 检测复用官方 v0.0.15 的本机 /api/logs/stream 事件，监听线程位于原有 Tunnel MCP 进程内，不新建外部轮询或守护服务。事件连接中断只重连本机接口。Cookie 检测仍随正常使用进行。仅启动失败时进行一次只读鉴权诊断，确认 401 才请求提示。

安装查询缩小到 personal 市场，避免无关远程市场拖慢更新。已备份任务和插件，受控重启原有 Tunnel 以加载监听；没有更换真实 Cookie、API key 或创建新云资源。

## 0.6.2 无窗口入口与健康时短路（2026-09-30）

基线 d08181e。保留唯一的既有 Windows 按需任务，将入口从 pwsh 改为同一虚拟环境的 pythonw。复用 launch_local.py 作为任务启动器，不增加常驻守护进程、定时轮询或登录启动项。

插件入口和任务入口共用一次有界的本机就绪检查，通道正常时不启动 PowerShell，也不访问论坛；失败才由无控制台子进程调用原管理脚本。后台成功输出静默，失败仍写既有诊断文件。补充 Windows 控制台句柄检查和真实任务重复触发验证；本次没有停止正在运行的真实 Tunnel。

## 0.6.1 Windows Codex 启动修复（2026-09-30）

基线 db59050。修复便携 MCP 清单的绝对 command 和不合规 cwd，改为程序名、`./` 工作目录及随包的轻量启动脚本。打包测试覆盖实际生成的清单；连接检查增加 `--plugin-dir`，不再只测直接运行 Python。

Windows 插件启动时触发单独的按需任务，由当前用户普通权限运行现有管理脚本。任务不使用定时或登录触发器；后台管理用互斥锁和已有 runtime 就绪状态避免重复实例。采用 Windows 自带任务管理，避免 MCP 客户端关闭进程组时连带杀死 Tunnel。

同步修复隐藏 PowerShell 的 UTF-8 JSON 解码、商店版 Codex 文件虚拟化导致的客户端路径差异，以及 Windows execv 无法保留父进程归属的问题。管理脚本不再依赖已从当前 Codex 安装中移除的 plugin-creator 辅助文件，改用现有原生 plugin CLI 和 JSON 操作。

实际安装前保存并校验了当前配置与插件备份；清理了本次验证中旧启动器留下的已确认进程。没有修改其他插件、创建新云资源或改写现有论坛凭证。验证与限制见 VALIDATION.md。

## 0.6.0 VPS 容器版本（2026-09-30）

以 c1d0a79 为基线，新增独立 HTTP 保护入口、Docker/Compose、HTTPS 代理、可选官方 Tunnel 镜像和 Linux 操作脚本；原 stdio/回环 HTTP 保持兼容，未自动升级用户电脑上已安装的 0.5.0。

公开入口必须有访问密钥，身份校验先于 MCP 处理；使用既有 SDK 的 Host/Origin 与请求体检查。公开 Cookie 管理接口未提供，运维通过 SSH 脚本标准输入完成。浏览器读取依赖改为可选，避免 VPS 安装无用的桌面依赖。

本机 Docker 原未启动，为测试启动了已有 Docker Desktop；启动后运行容器列表为空。验证资源均属于 linuxdo-vps-verify-01a0ec47。初次 Caddy 最小权限执行失败源于二进制 file capability，已去除不需要的特权并使用容器高端口。测试网络 internal 设置在 Docker 27 下不发布端口，已仅调整测试网络，所有宿主映射仍限于回环地址。

验证范围及限制见 VALIDATION.md。没有修改 VPS、DNS、Cloudflare、现有防火墙或本机运行凭证。目标机首次部署仍需用户提供独立 Cookie、域名或反代条件，以及可选 Tunnel 授权。

## 0.5.0 统一管理脚本（2026-09-30）

增加 Windows 菜单入口，自动安装/更新本机插件、检查登录、配置加密 Tunnel key、通过官方 runtimes 管理后台通道，并提供可选登录自启。继续复用已有远程 Tunnel 和 ChatGPT 连接，没有新建云服务。真实密钥不进入源码、ZIP 或 Git。

Cookie 设置改为验证候选后原子替换；失败保留原凭证。首次没有近期身份验证结果时预检，持续使用每 5 分钟后的下一次请求重新验证。401/身份接口未登录与防护、权限、限流、网络错误分开处理。

首次安装验证器缺少 PyYAML，改为优先复用已安装的 Python/YAML 环境；Tunnel 检查器把分离的 `-X utf8` 误作脚本路径，改为环境变量 PYTHONUTF8。实际启动发现原生命令解析器吞掉 Windows 反斜线，统一使用带引号的正斜线路径并加入回归检查。两类失败均未扩大权限或替换 Cookie。用户在修正后重新输入 key，权限检查与加密保存通过。

本机审计与回退文档保存在用户安装记录目录 linuxdo-manager-20260930。Codex 全局配置哈希前后一致；默认不开 Windows 自启。真实启动、重复启动、登录、搜索、读帖结果见 VALIDATION.md。

## 0.4.0 后续安装与 stdio 配置

2026-09-29，用户选择由 Codex 自动拉起，并授权本机安装及接入 ChatGPT。编辑前再次导出 Git bundle，备份并校验当前 Codex 配置；本机审计目录为 `%USERPROFILE%/.codex/installation-records/linuxdo-stdio-20260929-185358/`。

改动包括默认 stdio、打包时指定 Python、跨进程 Cookie 请求锁、裸 token 的等号兼容和更清晰的未登录错误。Cookie 配置命令也使用同一个文件锁。未增加依赖、开机任务或常驻 HTTP 服务。

用官方 scaffold 创建此前不存在的 personal marketplace，并通过 CLI 安装 `linuxdo-mcp@personal`。配置结构比较确认只新增此插件的 enabled 项，没有覆盖其他设置。运行环境因中文 CA 路径问题迁到本机纯英文目录，重新生成本机包并用官方 cachebuster 流程重装；portable 根清单同步同一版本后再安装。

用户自行输入 Cookie；初次裸 token 的等号被错误拒绝，已修复并回归测试。用户自行登录 Platform、确认创建私有 Tunnel，并在本机输入仅有 Tunnels Read/Use 权限的运行密钥。密钥没有写入源码或聊天；Tunnel profile 仅保存环境变量引用。账户 ID、真实 Tunnel ID、截图及密钥输入脚本只保存在本机审计目录，不进仓库。ChatGPT 已成功安装含连接与 Skill 的完整包，真实 Work 对话完成搜索及读帖；当前实测范围见 VALIDATION.md。

下文为 0.3.0 初始创建记录。

日期：2026-09-29。范围：在用户指定的工作目录创建插件和文档，验证后提交到 `aldington-david/linuxdo-mcp`。未修改 Codex 全局配置或现有个人 marketplace，未创建公网服务或真实 Tunnel。

## 基线与备份

- 上游：`mrsxs/linuxdo-mcp`，基线 `d4c007aab787fe5d3d2d2f5d52197533fb469a35`。
- 用户 fork：`aldington-david/linuxdo-mcp`，克隆时 `main` 与上游 HEAD 一致，工作区干净。
- 编辑前导出完整 Git bundle 并通过 `git bundle verify`。
- 本机备份位于仓库相邻的 `linuxdo-mcp-records/20260929/before-plugin.bundle`。
- 备份 SHA256：`8A76F3173B6C19710810779A455C4840C681219E3E15AFAB18E7F59614680E3D`。
- 原始 README 保存在 `docs/UPSTREAM_README.md`，推广声明仍归原作者，不作为本 fork 的承诺。

## 实施

1. 核对 OpenAI 的插件打包、MCP、Skill、个人连接和 Secure MCP Tunnel 文档。保留可移植入口和兼容清单；没有生成虚假的 ChatGPT 连接 ID。
2. 用 plugin-creator 生成基础清单，按 skill-creator 规则创建 `linuxdo-research`。代码复用上游请求与内容处理，仅增加接入和运行必需的修改。
3. 保留 stdio，增加仅回环地址的 Streamable HTTP；沿用 SDK 的 Host/Origin 防护。
4. 完成 13 个工具的名称、描述、只读标注、输入限制和结构化结果。MCP 2.2 对裸 `dict` 不会生成所需输出 schema，改成 `dict[str, Any]`；预期错误使用 SDK `ToolError`，避免登录/限流原因被隐藏。
5. 修正列表从 0 页开始、搜索标签兼容字符串/对象、严格解析话题链接、话题分页位置与楼号的区别。保留实际楼号并返回每楼链接。
6. 将带凭证请求限定为站内路径并禁止重定向；同进程串行保护 Cookie 轮换。缓存原子替换，写入失败明确报错；401 清缓存，403 保留缓存。增加本机隐藏输入命令。
7. 在仓库 `.venv` 安装依赖；初始 pip 的证书链校验失败，通过系统信任链下载新版 pip wheel 并校验 PyPI SHA256 后更新虚拟环境内 pip，未关闭 TLS 校验，未更改全局 Python。
8. 为避免本机 Python 3.11 对中文目录 editable `.pth` 的读取问题，改用普通 wheel 安装。MCP 最低版本设为实际使用的 2.2.0，未声称继续支持 MCP 1.x。
9. 用官方 `tunnel-client` Windows v0.0.15 验证 `init --mcp-server-url` 命令。二进制在本机 LocalAppData，未进仓库；校验后的 ZIP SHA256 为 `3B53133A1E24D43F63088D843860CB1701A4C3ED6390DE2E19F69089E43BDDC1`。仅生成含全零测试 ID 的临时 profile，没有调用真实隧道的 run 或注册云资源。
10. 编写并执行离线单元/协议回归、清单校验与包构建。Windows 测试进程通过明确的子进程 PID 终止整个进程树，避免解释器子进程残留和日志句柄占用。

生成产物放在被 Git 忽略的 `dist/`；源码中没有 Cookie、API key、个人 `.app.json` 或 Tunnel profile。当前验证范围见 [VALIDATION.md](VALIDATION.md)，回滚操作单独列在 [ROLLBACK.md](ROLLBACK.md)。

## 推送

提交说明为 `feat: add personal ChatGPT plugin and secure local MCP transport`，目标为用户 fork 的 `main`，不向上游推送。具体提交 ID 以 Git 历史为准；推送后的本机确认记录保存在相邻 `linuxdo-mcp-records/20260929/PUSH.md`。
