# 隐私与数据流

本插件供单个用户在自己的设备和账户中使用，没有开发者托管的数据服务或遥测上传接口。

- 本机 MCP 使用独立 Linux.do `_t` 发起只读 GET，请求固定发送到 `https://linux.do`，不跟随重定向。不会把 Cookie 放进工具结果。
- Cookie 缓存是本机明文文件，默认位于用户目录 `.cache/linuxdo-mcp/cookie.json`。轮换时原子替换，默认不读取浏览器；Windows 文件访问权限由 NTFS ACL 决定。
- 搜索词、读取到的帖子、用户名、楼层与账号等级等，会在调用相关工具时返回 ChatGPT / Codex。Cookie 留在本机不代表帖子内容也留在本机。调用方及 Linux.do 自身仍按各自政策处理请求和内容。
- Secure MCP Tunnel 使用单独的 OpenAI runtime API key；本服务不需要该 key。Tunnel 只负责传输，其访问控制、日志与账户关联由 OpenAI 平台负责。
- Windows 管理脚本将 Tunnel key 以 DPAPI 加密保存在本机用户专用目录，运行时通过环境变量传给官方 tunnel-client。首次/过期更新需要用户本地隐藏输入；不自动读取浏览器密码。登录后自启为可选，不默认启用。
- Cookie 更新会先请求 Linux.do 身份接口，成功后才替换旧值；首次工具请求及使用期间超过 5 分钟后的下一次请求会重新验证身份，空闲期间不后台轮询。
- 默认 stdio 由本机客户端自动启动；共享缓存以系统文件锁保护整个请求周期。
- 可选 HTTP 仅监听回环地址，但本机其他进程仍可能访问它。它不是多用户隔离服务，也没有公网 OAuth 或 Bearer-token 验证。
- 插件 ZIP 使用固定文件允许列表，不包含 `.venv`、Git 历史、Cookie 或 `.env`；个人连接映射只在指定 `--app-id` 时写入生成的绑定包。

不要将缓存迁入 Git 仓库或 OneDrive。日志及测试材料不要记录真实凭证。停用后可撤销独立站点会话、删除 Cookie 缓存，并在 ChatGPT / Platform 停用对应插件和 Tunnel。已经进入调用方对话的数据，需要按该产品的数据管理方式处理。

这份说明描述本 fork 的行为，不代表 Linux.do 或 OpenAI 的官方隐私政策。
