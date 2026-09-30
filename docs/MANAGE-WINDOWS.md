# Windows 一键管理

双击仓库根目录 `LinuxDo.cmd` 即可。需要已安装 Codex、Python 3.10+ 和 PowerShell 7；本机运行环境已存在时脚本会复用。脚本只管理 Linux.do 插件和名为 linuxdo-personal 的本地 Tunnel，不操作 Cloudflare。

## 第一次使用

1. 选 **1 一键安装、授权并启动**：准备 Python 环境、安装程序、备份当前插件配置、更新本地 Codex 插件，并验证 MCP 连接和 Linux.do 登录，然后继续配置和启动 ChatGPT 通道。新开一个 Codex 对话加载更新后的插件。只用本机 Codex 时选 9。
2. 如果 Cookie 缺失或失效，按终端提示取一次 `_t`，粘贴到隐藏输入处即可。验证成功才保存。
3. 已有 Tunnel 会继续复用，不新建远程 Tunnel。首次按提示提供已有 Tunnel ID 和 Runtime API key。以后 Codex 加载插件会自动启动/复用 Tunnel；菜单 **2 启动已配置的 ChatGPT 通道** 可用于手动恢复。
4. key 来自 `https://platform.openai.com/settings/organization/tunnels`，只需 Tunnels Read + Use。账号登录、验证码和平台必要授权由用户在官方页面完成；脚本不接管密码，也不索取账户管理密钥。

Tunnel key 用 Windows DPAPI 加密保存，只能由当前 Windows 用户在本机解密。以后无需每次输入，key 过期或撤销时选 **5 配置 ChatGPT 授权** 更新。程序读取 key 后只通过环境变量交给官方客户端，不放在命令行参数、Git 或插件 ZIP 中。

## 平时怎么用

| 菜单 | 用途 |
|---|---|
| 1 一键安装、授权并启动 | 完成安装、凭证检查/引导和后台启动；不清空已有有效 Cookie |
| 2 启动已配置的 ChatGPT 通道 | 先检查登录，再用官方 tunnel-client 管理后台进程 |
| 3 检查状态 | 实际检查 Cookie，并查看 Tunnel 状态 |
| 4 更新 Cookie | 显示取值步骤，隐藏输入，验证后替换 |
| 5 配置 ChatGPT 授权 | 更新加密保存的 Tunnel runtime key |
| 6 停止 ChatGPT 通道 | 停止本地通道；不删除远程 Tunnel，不影响 Codex stdio |
| 7 Windows 登录后自动启动 | 创建当前用户的启动快捷方式，无需管理员权限 |
| 8 关闭登录后自启 | 仅删除本脚本创建的启动快捷方式 |
| 9 仅安装/更新本机 Codex | 只安装本地插件，不要求 ChatGPT Tunnel key |

Codex 本机插件使用合规的程序名和插件内相对启动脚本，实际 Python 路径存在随包的 runtime.json 中。安装程序创建或更新同一个 `LinuxDo-Codex-Tunnel-<部署标识>` 按需任务：当前用户、普通权限，没有时间表和登录触发器。未保存 Tunnel key 时只启动本地 MCP，不弹输入框。

0.6.2 起，插件加载时只向本机 `127.0.0.1` 的 `/readyz` 做一次最长 0.5 秒的检查；通道已就绪就直接继续，不启动 PowerShell，也不访问论坛。没有后台定时轮询。任务入口也做同样检查，兼容尚未重启、仍反复触发任务的旧客户端。

真正需要启动时，任务通过 `pythonw.exe` 无控制台入口运行，管理 PowerShell 使用 `CREATE_NO_WINDOW`，标准输入/输出/错误都不连接终端。后台成功信息不弹窗，失败原因保存在已有的 last-error.json 中，菜单 3 可查看。手动打开 LinuxDo.cmd 时仍正常显示操作结果。

按需任务调用管理脚本，使用互斥锁和官方 runtime 状态防止重复启动。Windows 任务负责后台进程的生命周期，避免 MCP 连接关闭时连带清理 Tunnel；Tunnel 启动失败也不会阻止本地 MCP 握手。正常启动约需数秒，网络较慢时更久。

关闭管理窗口、结束一次对话或退出 Codex 后，已经启动的 Tunnel 会继续运行；停止用菜单 6。下次加载本地插件会再启动它。电脑关机、休眠或断网期间，云端 ChatGPT 无法访问本机。

Windows 登录自启与上述 Codex 联动分开，默认关闭。后台不会弹出凭证输入；遇到失效会停止启动并保存原因，打开管理菜单检查处理。这不是锁屏前就运行的系统服务，也不承诺断网、凭证过期时仍可用。

## Cookie 会不会失效

会。网站可以撤销会话；退出登录、账号安全变更或长期不用都可能使凭证失效。缓存默认 30 天只是本地保留上限，不是网站承诺的有效期。正常响应返回新的 `_t` 时程序会自动保存轮换值，但不能保证永久登录。

- 启动管理脚本的检查/启动动作会实际访问身份接口。
- 首次工具调用前验证身份；持续使用时，离上次成功验证超过 5 分钟的下一次请求重新验证。收到明确的登录无效响应会立即报错。
- 没有使用时不定时访问论坛，也不保证在 Cookie 刚失效的瞬间弹桌面通知。
- Cloudflare 验证页、403 权限限制、429 限流和网络故障分别提示，不能因此断言 Cookie 已过期。

更新步骤固定为：新开独立/隐身窗口 → `https://linux.do/login` 登录 → 同一窗口打开 `https://linux.do/session/current.json` 确认 `current_user` → F12 → Application/存储 → Cookies → `https://linux.do` → 复制 `_t` 的 Value → 在脚本隐藏输入处粘贴一次并回车。

不要复制整个 Cookie 头，不要发到聊天。复制后可关闭独立窗口，不要点退出登录，也不要继续共用这个会话浏览。候选值验证失败时旧凭证保留；成功后所有使用同一缓存的新请求立即生效，无需重启。

## 本地文件和撤销

管理配置默认在 `~/.cache/linuxdo-mcp/manager/`；Cookie 在相邻的 `cookie.json`。管理目录 ACL 限定当前用户和 SYSTEM，Tunnel key 文件是 `tunnel-key.xml`。Cookie 仍是 ACL 保护的本地明文，不能传到 Git 或 OneDrive。

每次安装会在 manager/backups 下备份 Codex 配置、个人 marketplace、本插件源码和已有按需任务定义。任务执行的管理脚本放在私有管理目录的 codex-startup 中，不依赖插件缓存一直保留。安装时解析 Windows 商店应用的真实文件路径，确保在 Codex 外也能找到同一个 Tunnel 客户端。

备份不是让你覆盖整个现有配置的指令；回退时仅处理本插件，保留其他插件和并发修改，不要恢复已经被网站轮换的旧 Cookie。要彻底撤销 Codex 联动，在任务计划程序中确认该任务的操作路径指向自己的 manager/codex-startup 后删除它，并停用本地插件；不要删除其他任务。

命令行也可运行 `./Manage-LinuxDo.ps1 -Action Setup`、`-Action Install`、`-Action Start`、`-Action Status`、`-Action Cookie`、`-Action Stop`。本脚本只自动化本地安装和已存在的 Tunnel；新的 ChatGPT 插件安装/工作区授权仍须在官方页面完成。
