#!/usr/bin/env bash
# One Linux/VPS operator entry point. Secrets are read from /dev/tty, never argv.
set +x
set -Eeuo pipefail
umask 077
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
DEPLOY="$ROOT/deploy/linux"
STATE="$ROOT/.local/vps"
CONFIG="$STATE/deploy.env"
PROJECT=linuxdo-mcp-vps
die() { printf '%s\n' "$*" >&2; exit 1; }
trap 'printf "操作未完成。数据卷未删除；可运行 ./linuxdo.sh status 或 logs 查看原因。\n" >&2' ERR
get_setting() { local key value; while IFS='=' read -r key value; do [[ "$key" != "$1" ]] || { printf '%s' "$value"; return; }; done < "$CONFIG"; }
need_tty() { [[ -r /dev/tty && -t 1 ]] || die '请在交互 SSH 终端运行（可用 ssh -t）；不要用 curl | bash 输入凭证。'; }
need_docker() {
    command -v docker >/dev/null || die '请先安装 Docker Engine 和 Compose v2：https://docs.docker.com/engine/install/'
    docker compose version >/dev/null || die '未找到 Docker Compose v2。'
    docker info >/dev/null 2>&1 || die 'Docker 未运行或当前用户没有 Docker 权限。'
}
load_config() {
    [[ -f "$CONFIG" ]] || die '请先运行 ./linuxdo.sh setup。'
    MODE=$(get_setting LINUXDO_MODE)
    TUNNEL=$(get_setting LINUXDO_TUNNEL)
    PUBLIC_URL=$(get_setting LINUXDO_PUBLIC_URL)
    [[ "$MODE" == https || "$MODE" == proxy || "$MODE" == private ]] || die '部署模式无效。'
    [[ "$TUNNEL" == 0 || "$TUNNEL" == 1 ]] || die 'Tunnel 开关无效。'
    DC=(docker compose --project-name "$PROJECT" --env-file "$CONFIG" -f "$DEPLOY/compose.yaml")
    [[ "$MODE" != proxy ]] || DC+=(-f "$DEPLOY/compose.proxy.yaml")
    [[ "$MODE" != https ]] || DC+=(--profile https)
    [[ "$TUNNEL" != 1 ]] || DC+=(--profile tunnel)
}
dc() { "${DC[@]}" "$@"; }
guard_project() {
    local id location
    while IFS= read -r id; do
        [[ -n "$id" ]] || continue
        location=$(docker inspect --format '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}' "$id")
        [[ "$location" == "$DEPLOY" ]] || die '发现同名 Docker 项目位于其他目录，已停止，避免改动已有服务。'
    done < <(docker ps -aq --filter "label=com.docker.compose.project=$PROJECT")
}
running() { [[ -n "$(dc ps --status running -q "$1")" ]]; }
operator() {
    local service=$1; shift
    if running "$service"; then dc exec -T "$service" "$@";
    else dc run --rm -T --no-deps "$service" "$@"; fi
}
configure() {
    [[ ! -f "$CONFIG" ]] || return
    need_tty
    if docker volume inspect "${PROJECT}_data" >/dev/null 2>&1; then
        die '已有同名数据卷，但本目录没有部署记录。请找回原部署目录，不能盲目覆盖。'
    fi
    printf '1 自带 HTTPS（需要域名和空闲的 80/443）\n2 复用已有 HTTPS 反代（后端仅绑定本机）\n3 仅用私有 Tunnel（不开放公网 MCP 端口）\n'
    read -r -p '选择 [1]: ' mode </dev/tty
    mode=${mode:-1}
    local domain url port=19878 tunnel=0
    case "$mode" in
        1|2)
            read -r -p 'MCP 域名（不带 https:// 和路径）: ' domain </dev/tty
            domain=${domain,,}
            [[ ${#domain} -le 253 && "$domain" =~ ^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$ && "$domain" == *.* ]] || die '域名格式不正确。'
            [[ ! "$domain" =~ ^[0-9.]+$ ]] || die '自带 HTTPS 请使用域名；只有 IP 时可以先选私有 Tunnel。'
            url="https://$domain"
            if [[ "$mode" == 1 ]]; then MODE=https; else
                MODE=proxy
                read -r -p '本机反代端口 [19878]: ' port </dev/tty
                port=${port:-19878}
                [[ "$port" =~ ^[0-9]{4,5}$ && "$port" -ge 1024 && "$port" -le 65535 ]] || die '端口须为 1024–65535。'
            fi
            read -r -p '同时连接 ChatGPT 私有 Tunnel？[y/N]: ' answer </dev/tty
            [[ "$answer" != y && "$answer" != Y ]] || tunnel=1
            ;;
        3) MODE=private; domain=localhost; url=https://localhost; tunnel=1 ;;
        *) die '请选择 1、2 或 3。' ;;
    esac
    mkdir -p "$STATE"
    printf 'LINUXDO_MODE=%s\nLINUXDO_DOMAIN=%s\nLINUXDO_PUBLIC_URL=%s\nLINUXDO_LOOPBACK_PORT=%s\nLINUXDO_TUNNEL=%s\n' "$MODE" "$domain" "$url" "$port" "$tunnel" > "$CONFIG"
    printf '部署配置已保存；此文件不包含 Cookie 或访问密钥。\n'
    printf '# 回退\n\n运行 ./linuxdo.sh stop 只停止本项目并保留数据卷。不要使用 down -v 或 docker system prune。\n更新前的配置和镜像记录在 backups/。不要用旧 Cookie 覆盖已经轮换的会话。\n' > "$STATE/ROLLBACK.md"
}
cookie() {
    need_tty
    printf '\n请在自己的电脑上新开独立/隐身窗口，打开 https://linux.do/login 并登录。\n'
    printf '同一窗口打开 https://linux.do/session/current.json，确认有 current_user。\n'
    printf 'F12 → Application/存储 → Cookies → https://linux.do → 复制 _t 的 Value。\n'
    printf 'VPS 请用新独立会话，不要复用正在被本机插件使用的 Cookie。只粘贴一次，不要点退出登录。\n'
    local secret
    IFS= read -r -s -p '粘贴 _t（隐藏输入），回车: ' secret </dev/tty
    printf '\n' >/dev/tty
    printf '%s' "$secret" | operator mcp python -m linuxdo_mcp.server --configure-cookie --cookie-stdin
    unset secret
}
tunnel_key() {
    [[ "$TUNNEL" == 1 ]] || die '此部署未启用 Tunnel；请按文档调整部署配置。'
    need_tty
    printf '打开 https://platform.openai.com/settings/organization/tunnels。\n'
    printf '为 VPS 使用独立 Tunnel；若迁移旧 Tunnel，先停用电脑上的旧通道，避免两个后端竞争。\n'
    printf '准备对应的 Tunnel ID，以及仅有 Tunnels Read + Use 的 Runtime API key。\n'
    local id secret
    read -r -p 'Tunnel ID（tunnel_ 开头）: ' id </dev/tty
    [[ "$id" =~ ^tunnel_[a-f0-9]{32}$ ]] || die 'Tunnel ID 格式不正确。'
    IFS= read -r -s -p '粘贴 Runtime API key（隐藏输入）: ' secret </dev/tty
    printf '\n' >/dev/tty
    printf '%s' "$secret" | operator tunnel python -m linuxdo_mcp.vps_admin tunnel-key --tunnel-id "$id"
    unset secret
    if running tunnel; then dc restart tunnel; fi
}
start() {
    local code
    if operator mcp python -m linuxdo_mcp.server --check-cookie; then :
    else
        code=$?
        if [[ "$code" == 2 ]]; then cookie; else die '论坛登录暂时无法验证。请先解决网络、防护或限流问题，不要反复更换 Cookie。'; fi
    fi
    if [[ "$TUNNEL" == 1 ]]; then
        if operator tunnel python -m linuxdo_mcp.vps_admin check-tunnel; then :
        else
            code=$?
            if [[ "$code" == 2 ]]; then tunnel_key; else die 'Tunnel 验证失败，旧密钥已保留。检查网络或运行 ./linuxdo.sh tunnel-key 更新授权。'; fi
        fi
    fi
    dc up -d --wait --wait-timeout 180
    printf '容器已启动。Cookie 已验证；公网 HTTPS 证书和客户端连通性还需按下方说明核对。\n'
    [[ "$MODE" != https ]] || printf '请确认域名已解析到本机，入站 TCP 80/443 已放行；不要开放后端 8787。\n'
    [[ "$MODE" != proxy ]] || printf '请让现有 HTTPS 反代把 /mcp 转发到 http://127.0.0.1:%s/mcp，并保留 Host、Authorization。\n' "$(get_setting LINUXDO_LOOPBACK_PORT)"
}
show_client() {
    [[ "$MODE" != private ]] || { printf '私有模式不提供公网 MCP 地址；在 ChatGPT 中连接刚配置的 Tunnel。\n'; return; }
    need_tty
    running mcp || die '请先启动服务，再显示客户端密钥。'
    local token
    # docker exec output does not enter the service container's stdout log.
    token=$(dc exec -T mcp python -m linuxdo_mcp.vps_admin show-token)
    printf '\nMCP 地址：%s/mcp\n访问密钥（只交给自己的客户端）：%s\n' "$PUBLIC_URL" "$token"
    unset token
    printf 'Codex 用 Bearer token 连接；ChatGPT 不支持直接填写此密钥，请用私有 Tunnel。\n'
}
main() {
    local action=${1:-menu}
    need_docker
    if [[ "$action" == menu ]]; then
        printf '1 一键部署/更新  2 启动  3 状态  4 更新 Cookie  5 更新 Tunnel 授权\n6 显示客户端配置  7 轮换 MCP 密钥  8 日志  9 停止（保留数据）  0 退出\n'
        read -r -p '选择: ' selection </dev/tty
        case "$selection" in 1) action=setup;;2) action=start;;3) action=status;;4) action=cookie;;5) action=tunnel-key;;6) action=client;;7) action=rotate-token;;8) action=logs;;9) action=stop;;0) return;;*) die '无效选择';; esac
    fi
    [[ "$action" != setup ]] || configure
    load_config
    guard_project
    case "$action" in
        setup)
            backup="$STATE/backups/$(date -u +%Y%m%d-%H%M%S)"
            mkdir -p "$backup"
            cp -- "$CONFIG" "$backup/deploy.env"
            dc images > "$backup/images.txt"
            dc build --pull
            operator mcp python -m linuxdo_mcp.vps_admin init
            start
            show_client
            ;;
        start) start ;;
        cookie) cookie ;;
        tunnel-key) tunnel_key ;;
        status) dc ps; operator mcp python -m linuxdo_mcp.server --check-cookie ;;
        client) show_client ;;
        rotate-token) operator mcp python -m linuxdo_mcp.vps_admin rotate-token; printf '旧 MCP 密钥已失效。请运行 ./linuxdo.sh client 获取新值并更新客户端。\n' ;;
        logs) dc logs --tail=100 ;;
        stop) dc --profile '*' down; printf '本项目已停止，Cookie、密钥和证书数据卷均保留。\n' ;;
        *) die '用法：./linuxdo.sh [setup|start|status|cookie|tunnel-key|client|rotate-token|logs|stop]' ;;
    esac
    mkdir -p "$STATE"
    printf '%s %s completed\n' "$(date -u +%FT%TZ)" "$action" >> "$STATE/operations.log"
}
main "$@"
