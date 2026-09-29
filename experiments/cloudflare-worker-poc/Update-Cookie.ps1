param(
    [Parameter(Mandatory=$true)][string]$ClientConfig
)
$ErrorActionPreference = 'Stop'
$client = Get-Content -LiteralPath $ClientConfig -Raw | ConvertFrom-Json
if ($client.url -notmatch '^https://[a-z0-9-]+\.[a-z0-9-]+\.workers\.dev$') { throw '测试地址与本次实验不一致，已停止。' }
Write-Host '请新开一个独立/隐身浏览器会话，打开 https://linux.do/login 并登录。'
Write-Host '在同一窗口打开 https://linux.do/session/current.json，确认能看到 current_user。'
Write-Host '按 F12 → Application（应用程序）/存储 → Cookies → https://linux.do。'
Write-Host '复制名称为 _t 的 Value，只粘贴一次。不要复制完整 Cookie 头。'
Write-Host '本次值仅发送到新建的测试 Worker，用于验证 Linux.do 登录，不会覆盖本机插件 Cookie。'
$secure = Read-Host 'Linux.do 独立 _t（隐藏输入，粘贴后回车）' -AsSecureString
$pointer = [IntPtr]::Zero
try {
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    $cookie = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    if ([string]::IsNullOrWhiteSpace($cookie)) { throw '未输入 Cookie，已取消。' }
    $reply = Invoke-WebRequest -Uri ($client.url + '/cookie') -Method Post -ContentType 'application/json' -Body (@{ cookie=$cookie } | ConvertTo-Json -Compress) -Headers @{ Authorization='Bearer ' + $client.token } -SkipHttpErrorCheck
    $result = $reply.Content | ConvertFrom-Json
    $record = [ordered]@{ time=[DateTime]::UtcNow.ToString('o'); http_status=[int]$reply.StatusCode; result=$result }
    $record | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path (Split-Path $ClientConfig) 'cookie-import-result.json') -Encoding utf8
    if ($result.ok) { Write-Host '登录验证成功，Cookie 已保存到独立测试 Worker。' -ForegroundColor Green }
    elseif ($result.error -eq 'cloudflare_challenge') { Write-Host 'Linux.do 的 Cloudflare 防护返回 403 验证页。本次 Cookie 未保存；这不能证明 Cookie 已失效。' -ForegroundColor Yellow }
    else { Write-Host ('验证未通过，旧配置未覆盖。错误：' + $result.error + '；上游状态：' + $result.upstream_status) -ForegroundColor Yellow }
} catch {
    Write-Host '更新未完成。请确认网络、测试服务和输入格式；凭证内容未输出。' -ForegroundColor Red
} finally {
    if ($pointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
    $cookie = $null
    $secure.Dispose()
}
