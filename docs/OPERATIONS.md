# 开发操作记录

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
