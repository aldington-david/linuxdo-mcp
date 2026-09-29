# 回滚与停用

## 0.6.0 VPS 停用与回退

运行 `bash linuxdo.sh stop` 仅停止当前项目，保留 Cookie、密钥和证书卷。不要使用 `down -v` 或全局 `docker system prune`。脚本遇到同名项目来自其他目录会停止，避免修改别的部署。

`.local/vps/backups/` 保存更新前部署配置和镜像记录。代码/镜像回退不应恢复旧 Cookie；服务器可能已经轮换会话。真正撤销访问需轮换 MCP key，并在对应平台撤销论坛会话/Tunnel key。

本版本没有自动迁移现有 Windows 安装；若只是尝试 VPS，不需要回退电脑上的插件。

## 0.5.0 管理脚本的停用

在 LinuxDo.cmd 中选“停止 ChatGPT 通道”，只停止本地 linuxdo-personal runtime；不删除远程 Tunnel 或 ChatGPT 插件。若启用了登录自启，再选“关闭登录后自启”，只移除本脚本对应的当前用户启动快捷方式。

加密运行密钥在用户目录 `.cache/linuxdo-mcp/manager/tunnel-key.xml`，删除后下次需重新输入；要撤销凭证本身，应在 Platform 撤销对应 key。此操作不影响 Codex stdio。

每次安装备份位于 `.cache/linuxdo-mcp/manager/backups/`。若回退插件，只恢复本插件并重新安装，不能整份覆盖 Codex 或 marketplace 配置。Cookie 已可能轮换，不恢复旧 token；新增 validated_at 字段可以被旧版忽略。

## 0.4.0 本机安装的回滚

本次后续安装已创建 personal marketplace、启用插件，并配置了私有 Tunnel。先停止对应 Tunnel 并禁用/卸载 `linuxdo-mcp@personal`；如移除 marketplace 条目，只移除此插件，不要覆盖后续其他条目。Python 运行环境与源代码目录分离，删除环境前先确认没有客户端使用。

立即安装前的配置、Git bundle、缓存目录 ACL、安装日志与详细回滚说明在 `%USERPROFILE%/.codex/installation-records/linuxdo-stdio-20260929-185358/`。不要用旧配置覆盖后来修改；需要撤销凭证时，分别在 Linux.do 和 Platform 撤销，而不只是删本地文件。跨进程锁文件不能在仍有请求运行时删除。

撤销 GitHub 本次更新使用 `git revert` 对应 stdio 更新提交，不强制推送。下面为初始创建时的回滚说明。

本文只提供按需执行的操作。本次开发没有对用户的 Codex 全局配置、个人 marketplace 或真实 Cookie 做写入，因此没有需要恢复的全局配置备份。

## 停止使用

1. 在运行 MCP 和 tunnel-client 的终端分别 Ctrl+C。
2. 在 ChatGPT / Codex 中禁用或卸载自己安装的插件。若使用本文的默认 personal marketplace，可按当前 CLI 使用 `codex plugin remove linuxdo-mcp@personal`；其他 marketplace 使用实际名称。
3. 从个人 marketplace 仅移除该插件条目，保留其他插件；如果从未登记过则无需修改。
4. 在 Linux.do 中撤销独立登录会话；需要清除本机凭证时，仅删除实际 `LINUXDO_CACHE_DIR` 下的 `cookie.json`（默认用户目录 `.cache/linuxdo-mcp/cookie.json`）。缓存删除不会自动撤销站点会话。
5. 在 Platform 停用对应真实 Tunnel / 撤销仅为此用途创建的 runtime key。关闭本机终端并不撤销平台密钥。

## 撤销 GitHub 上的本次代码提交

先在仓库执行 `git status`，保存尚未提交的个人修改，再找到本次提交：

```powershell
git log --oneline --grep='feat: add personal ChatGPT plugin'
git revert <上一步找到的提交ID>
git push origin main
```

这样增加一条撤销提交，不重写远端历史，不影响之后的其他提交。不要用 `reset --hard` 或强制推送代替。

如果撤销后仍需使用上游 stdio 版本，在虚拟环境重新 `pip install .`。上游没有本 fork 的 HTTP 入口和新增防护；先停掉旧进程。

## 从编辑前备份恢复到独立目录

备份是仓库相邻 `linuxdo-mcp-records/20260929/before-plugin.bundle`，基线为 `d4c007aab787fe5d3d2d2f5d52197533fb469a35`。不要覆盖现有工作目录。

```powershell
git bundle verify ..\linuxdo-mcp-records\20260929\before-plugin.bundle
git clone ..\linuxdo-mcp-records\20260929\before-plugin.bundle ..\linuxdo-mcp-before-plugin
```

该 bundle 的 SHA256 在 [操作记录](OPERATIONS.md) 中。备份仅含 Git 历史，不包含凭证、虚拟环境或生成的 ZIP。

## 清理本次开发产物

仓库中的 `.venv/` 与 `dist/` 都是生成物；确认没有进程依赖后可手动删除。官方 tunnel-client 校验用文件在 `%LOCALAPPDATA%\linuxdo-mcp-tools\`，其中 `validation-profile/linuxdo-validation.yaml` 只有全零测试 ID；未注册真实云端 Tunnel。目录若以后被用户用于真实运行，先保留其中真实配置，再决定是否清理。

本次开发中对虚拟环境安装方式的调整（editable 改为普通安装）已记录在 OPERATIONS.md；没有恢复或覆盖任何用户已有环境。
