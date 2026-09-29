#requires -Version 7.0
[CmdletBinding()]
param(
    [ValidateSet('Menu','Setup','Install','Start','Status','Cookie','TunnelKey','Stop','EnableAutoStart','DisableAutoStart')]
    [string]$Action = 'Menu',
    [string]$PythonPath,
    [string]$TunnelClientPath,
    [string]$TunnelId,
    [string]$StateDir = (Join-Path $HOME '.cache\linuxdo-mcp\manager'),
    [switch]$Unattended
)
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$OutputEncoding = [Text.UTF8Encoding]::new($false)
if (!$IsWindows) { throw '此管理脚本用于 Windows；其他系统请参阅 docs/USAGE.md。' }
$Repo = $PSScriptRoot
$ManagerScript = $PSCommandPath
$CodexRoot = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME '.codex' }
$Creator = Join-Path $CodexRoot 'skills\.system\plugin-creator\scripts'
$Alias = 'linuxdo-personal'
$ConfigFile = Join-Path $StateDir 'settings.json'
$KeyFile = Join-Path $StateDir 'tunnel-key.xml'
$AutoStartFile = Join-Path ([Environment]::GetFolderPath('Startup')) 'LinuxDo-Tunnel.lnk'
$Settings = if (Test-Path -LiteralPath $ConfigFile) { Get-Content -LiteralPath $ConfigFile -Raw | ConvertFrom-Json -AsHashtable } else { @{} }
if ($PythonPath) { $Settings.python = $PythonPath }
if ($TunnelClientPath) { $Settings.tunnel_client = $TunnelClientPath }
if ($TunnelId) { $Settings.tunnel_id = $TunnelId }

function Run-Checked([string]$Exe, [string[]]$Arguments) {
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw ('操作未完成，退出码 ' + $LASTEXITCODE + '。请查看上方提示。') }
}
function Save-Settings {
    New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
    $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    & icacls.exe $StateDir /inheritance:r /grant:r "*${sid}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw '无法保护本机配置目录，已停止。' }
    if (!$env:LINUXDO_CACHE_DIR) {
        $cookieDir = Join-Path $HOME '.cache\linuxdo-mcp'
        New-Item -ItemType Directory -Force -Path $cookieDir | Out-Null
        & icacls.exe $cookieDir /inheritance:r /grant:r "*${sid}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' | Out-Null
        if ($LASTEXITCODE -ne 0) { throw '无法保护默认 Cookie 目录，已停止。' }
    }
    $Settings | ConvertTo-Json | Set-Content -LiteralPath ($ConfigFile + '.tmp') -Encoding utf8
    Move-Item -LiteralPath ($ConfigFile + '.tmp') -Destination $ConfigFile -Force
}
function Require-Python {
    if (!$Settings.python -or !(Test-Path -LiteralPath $Settings.python)) { throw '请先选择“安装或更新”。' }
}
function Check-Cookie {
    Require-Python
    $raw = & $Settings.python -X utf8 -m linuxdo_mcp.server --check-cookie --json
    $result = $raw | ConvertFrom-Json -AsHashtable
    Write-Host $result.message
    return $result
}
function Update-Cookie {
    Require-Python
    if ($Unattended) { throw 'Cookie 需要更新，请双击 LinuxDo.cmd，选择“更新 Cookie”。' }
    Run-Checked $Settings.python @('-X','utf8','-m','linuxdo_mcp.server','--configure-cookie') | Out-Host
}
function Install-Local {
    if (!(Get-Command codex -ErrorAction SilentlyContinue)) { throw '未找到 Codex 命令，请先安装并登录 Codex。' }
    if (!(Test-Path -LiteralPath (Join-Path $Creator 'read_marketplace_name.py'))) { throw '未找到 Codex 的 Plugin Creator 工具，请先完成 Codex 安装。' }
    $helperPython = (Get-Command python -ErrorAction Stop).Source
    $plugins = (& codex plugin list --json) | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw '无法读取 Codex 插件状态。' }
    $installed = @($plugins.installed | Where-Object pluginId -eq 'linuxdo-mcp@personal')
    $pluginDir = Join-Path $HOME 'plugins\linuxdo-mcp'
    if ($installed.Count) {
        if ($installed[0].source.source -ne 'local') { throw '现有插件不是本地来源，已停止覆盖。' }
        $pluginDir = $installed[0].source.path
        if (!$Settings.python) {
            $mcpFile = Join-Path $pluginDir '.mcp.json'
            if (Test-Path -LiteralPath $mcpFile) { $Settings.python = (Get-Content -LiteralPath $mcpFile -Raw | ConvertFrom-Json).mcpServers.linuxdo.command }
        }
    }
    if (!$Settings.python -or !(Test-Path -LiteralPath $Settings.python)) {
        $runtime = Join-Path $env:LOCALAPPDATA 'linuxdo-mcp\venv'
        if ($runtime -match '[^\x00-\x7f]') { throw 'Python 运行环境路径需为英文，请用 -PythonPath 指定已有英文路径环境。' }
        Run-Checked 'python' @('-m','venv',$runtime) | Out-Host
        $Settings.python = Join-Path $runtime 'Scripts\python.exe'
    }
    Save-Settings
    $backup = Join-Path $StateDir ('backups\' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff'))
    New-Item -ItemType Directory -Path $backup -Force | Out-Null
    foreach ($path in @((Join-Path $CodexRoot 'config.toml'), (Join-Path $HOME '.agents\plugins\marketplace.json'))) {
        if (Test-Path -LiteralPath $path) { Copy-Item -LiteralPath $path -Destination $backup }
    }
    if (Test-Path -LiteralPath $pluginDir) { Copy-Item -LiteralPath $pluginDir -Destination (Join-Path $backup 'plugin') -Recurse }
    Write-Host '正在安装或更新本机程序。'
    Run-Checked $Settings.python @('-m','pip','install','--quiet','--disable-pip-version-check',$Repo) | Out-Host
    Run-Checked $Settings.python @('-m','pip','check') | Out-Host
    & $helperPython -c 'import yaml' 2>$null
    if ($LASTEXITCODE -ne 0) {
        Run-Checked $Settings.python @('-m','pip','install','--quiet','--disable-pip-version-check','PyYAML') | Out-Host
        $helperPython = $Settings.python
    }
    if (!$installed.Count) {
        Run-Checked $Settings.python @((Join-Path $Creator 'create_basic_plugin.py'),'linuxdo-mcp','--with-marketplace','--path',(Split-Path $pluginDir)) | Out-Host
    }
    $market = Run-Checked $Settings.python @((Join-Path $Creator 'read_marketplace_name.py'))
    if ($market.Trim() -ne 'personal') { throw '默认个人市场名称不是 personal，已停止插件覆盖。' }
    $archive = Join-Path $Repo 'dist\linuxdo-mcp-local.zip'
    Run-Checked $Settings.python @((Join-Path $Repo 'scripts\package_plugin.py'),'--python',$Settings.python,'--output',$archive) | Out-Host
    Expand-Archive -LiteralPath $archive -DestinationPath $pluginDir -Force
    Run-Checked $Settings.python @((Join-Path $Creator 'update_plugin_cachebuster.py'),$pluginDir) | Out-Host
    $portablePath = Join-Path $pluginDir 'plugin.json'
    $portable = Get-Content -LiteralPath $portablePath -Raw | ConvertFrom-Json -AsHashtable
    $portable.version = (Get-Content -LiteralPath (Join-Path $pluginDir '.codex-plugin\plugin.json') -Raw | ConvertFrom-Json).version
    $portable | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $portablePath -Encoding utf8
    Run-Checked $helperPython @((Join-Path $Creator 'validate_plugin.py'),$pluginDir) | Out-Host
    Run-Checked 'codex' @('plugin','add','linuxdo-mcp@personal') | Out-Host
    Run-Checked $Settings.python @((Join-Path $Repo 'scripts\check_connection.py')) | Out-Host
    Write-Host '本地安装完成。Codex 加载插件时会自动启动；新建一个对话使用更新后的插件。'
    Write-Host ('本次安装备份：' + $backup)
    $login = Check-Cookie
    if (!$login.ok -and $login.status -in @('missing','expired') -and !$Unattended) { Update-Cookie }
    elseif (!$login.ok) { Write-Host '本地安装已完成，但登录尚未验证通过；请按提示处理。' }
}
function Require-TunnelClient {
    if ($Settings.tunnel_client -and (Test-Path -LiteralPath $Settings.tunnel_client)) { return }
    $found = @(Get-ChildItem -Path (Join-Path $env:LOCALAPPDATA 'linuxdo-mcp-tools\v*\tunnel-client.exe') -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending)
    if ($found.Count) { $Settings.tunnel_client = $found[0].FullName; Save-Settings; return }
    Write-Host '正在获取 OpenAI 官方 Tunnel 客户端。'
    $release = Invoke-RestMethod 'https://api.github.com/repos/openai/tunnel-client/releases/latest' -Headers @{ 'User-Agent'='LinuxDo-Setup' }
    $arch = if ([Runtime.InteropServices.RuntimeInformation]::OSArchitecture -eq 'Arm64') { 'arm64' } else { 'amd64' }
    $asset = @($release.assets | Where-Object name -eq "tunnel-client-$($release.tag_name)-windows-$arch.zip")
    if ($asset.Count -ne 1 -or $asset[0].digest -notmatch '^sha256:[a-f0-9]{64}$') { throw '官方安装包或校验值不完整，已停止下载。' }
    if ($asset[0].browser_download_url -notlike 'https://github.com/openai/tunnel-client/releases/download/*') { throw '下载地址不符合预期。' }
    Save-Settings
    $zip = Join-Path $StateDir 'tunnel-client.zip'
    Invoke-WebRequest $asset[0].browser_download_url -OutFile $zip
    if ((Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant() -ne $asset[0].digest.Substring(7)) { throw '官方安装包校验失败。' }
    $binDir = Join-Path $StateDir 'tunnel-bin'
    Expand-Archive -LiteralPath $zip -DestinationPath $binDir -Force
    $bins = @(Get-ChildItem -LiteralPath $binDir -Filter tunnel-client.exe -Recurse)
    if ($bins.Count -ne 1) { throw '安装包中的客户端数量异常。' }
    $Settings.tunnel_client = $bins[0].FullName
    Save-Settings
}
function Ensure-TunnelId {
    if (!$Settings.tunnel_id) {
        if ($Unattended) { throw '请先在菜单中配置 ChatGPT 通道。' }
        Write-Host '打开 https://platform.openai.com/settings/organization/tunnels，复制已有 Linux.do Tunnel ID。'
        $Settings.tunnel_id = (Read-Host 'Tunnel ID（tunnel_ 开头，不是密钥）').Trim()
    }
    if ($Settings.tunnel_id -notmatch '^tunnel_[a-f0-9]{32}$') { throw 'Tunnel ID 格式不正确。' }
    Save-Settings
}
function Get-McpCommand {
    # The Tunnel shell parser consumes backslashes; Windows also accepts forward slashes.
    return '"' + $Settings.python.Replace('\','/') + '" -m linuxdo_mcp.server'
}
function Write-Profile {
    Require-Python
    Ensure-TunnelId
    $profileDir = Join-Path $StateDir 'profiles'
    New-Item -ItemType Directory -Force -Path $profileDir | Out-Null
    # tunnel-client doctor treats the separate value in '-X utf8' as a script; inherit PYTHONUTF8 instead.
    $profile = @{ config_version=1; control_plane=@{base_url='https://api.openai.com';tunnel_id=$Settings.tunnel_id;api_key='env:CONTROL_PLANE_API_KEY'}; health=@{listen_addr='127.0.0.1:0'};admin_ui=@{open_browser=$false};mcp=@{commands=@(@{channel='main';command=(Get-McpCommand)})} }
    # JSON is valid YAML, with path quoting handled by the serializer.
    $profile | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $profileDir 'linuxdo-managed.yaml') -Encoding utf8
}
function Configure-TunnelKey {
    Require-Python
    Require-TunnelClient
    Ensure-TunnelId
    $previous = Tunnel-Status
    Check-TunnelOwner $previous
    Write-Profile
    if ($Unattended) { throw '通道密钥未配置，请双击 LinuxDo.cmd，选择“配置 ChatGPT 授权”。' }
    Write-Host '打开 https://platform.openai.com/settings/organization/tunnels，选择你的 Linux.do Tunnel。'
    Write-Host '创建或使用 Tunnels Read + Use 的 Runtime API key。密码和密钥都不要发到聊天。'
    Write-Host '此密钥将用 Windows DPAPI 加密保存，仅当前 Windows 用户在本机可解密。'
    $key = Read-Host '粘贴 Tunnel runtime API key（隐藏输入）' -AsSecureString
    if (!$key.Length) { $key.Dispose(); throw '未输入密钥。' }
    $oldEnv = $env:CONTROL_PLANE_API_KEY
    try {
        $env:CONTROL_PLANE_API_KEY = [Net.NetworkCredential]::new('', $key).Password
        $doctor = & $Settings.tunnel_client doctor --profile linuxdo-managed --profile-dir (Join-Path $StateDir 'profiles') --explain
        if ($LASTEXITCODE -ne 0) { $doctor | Out-Host; throw '本机通道配置检查未通过，旧密钥未替换。' }
        Run-Checked $Settings.tunnel_client @('admin','--json','tunnels','get',$Settings.tunnel_id) | Out-Null
        $key | Export-Clixml -LiteralPath ($KeyFile + '.tmp')
        Move-Item -LiteralPath ($KeyFile + '.tmp') -Destination $KeyFile -Force
        Write-Host '授权检查通过，密钥已加密保存。以后启动不用再次粘贴。'
        if ($previous -and $previous.process_running) {
            Run-Checked $Settings.tunnel_client @('runtimes','stop',$Alias) | Out-Null
            Start-Tunnel
        }
    } finally { $env:CONTROL_PLANE_API_KEY = $oldEnv; $key.Dispose() }
}
function Tunnel-Status {
    if (!$Settings.tunnel_client -or !(Test-Path -LiteralPath $Settings.tunnel_client)) { return $null }
    $raw = & $Settings.tunnel_client runtimes status $Alias --json 2>$null
    if ($LASTEXITCODE -ne 0) { return $null }
    return ($raw | ConvertFrom-Json -AsHashtable)
}
function Show-TunnelStatus($State) {
    if (!$State -or !$State.process_running) { Write-Host 'ChatGPT 通道未运行。'; return }
    if ($State.healthy -and $State.ready) { Write-Host 'ChatGPT 通道正在后台运行，健康检查通过，可以接收调用。' }
    else { Write-Host 'ChatGPT 通道进程已启动，但尚未就绪；请稍后再次检查状态。' }
}
function Check-TunnelOwner($State) {
    if ($State -and $State.tunnel_id -ne $Settings.tunnel_id) { throw '同名后台通道属于另一个 Tunnel，已停止操作，不会覆盖或关闭它。' }
}
function Start-Tunnel {
    Require-Python
    Require-TunnelClient
    Ensure-TunnelId
    $existing = Tunnel-Status
    Check-TunnelOwner $existing
    $login = Check-Cookie
    if (!$login.ok) {
        if ($login.status -in @('missing','expired') -and !$Unattended) { Update-Cookie }
        else { throw $login.message }
    }
    if (!(Test-Path -LiteralPath $KeyFile)) { Configure-TunnelKey }
    $oldEnv = $env:CONTROL_PLANE_API_KEY
    $key = Import-Clixml -LiteralPath $KeyFile
    if ($key -isnot [Security.SecureString]) { throw '本机加密密钥格式异常，请选择“配置 ChatGPT 授权”重新保存。' }
    try {
        $env:CONTROL_PLANE_API_KEY = [Net.NetworkCredential]::new('', $key).Password
        $command = Get-McpCommand
        $connected = & $Settings.tunnel_client runtimes connect --alias $Alias --tunnel-id $Settings.tunnel_id --profile linuxdo-managed --profile-dir (Join-Path $StateDir 'profiles') --runtime-api-key env:CONTROL_PLANE_API_KEY --mcp-command $command --json
        $connectExit = $LASTEXITCODE
        $connected | Set-Content -LiteralPath (Join-Path $StateDir 'last-connect-result.json') -Encoding utf8
        if ($connectExit -ne 0) { throw '通道启动未完成，诊断已保存在 manager/last-connect-result.json；无需因此更新 Cookie。' }
        $status = Tunnel-Status
        for ($attempt = 0; $attempt -lt 5 -and $status -and $status.process_running -and !$status.ready; $attempt++) {
            Start-Sleep -Seconds 2
            $status = Tunnel-Status
        }
        $status | ConvertTo-Json -Depth 15 | Set-Content -LiteralPath (Join-Path $StateDir 'last-tunnel-status.json') -Encoding utf8
        Show-TunnelStatus $status
        if (!$status -or !$status.process_running -or !$status.healthy -or !$status.ready) { throw '通道尚未通过就绪检查，详情已保存到本机 last-tunnel-status.json。' }
        if (Test-Path -LiteralPath (Join-Path $StateDir 'last-error.json')) { Remove-Item -LiteralPath (Join-Path $StateDir 'last-error.json') }
    } finally { $env:CONTROL_PLANE_API_KEY = $oldEnv; $key.Dispose() }
}
function Set-AutoStart([bool]$Enabled) {
    $shell = New-Object -ComObject WScript.Shell
    if (Test-Path -LiteralPath $AutoStartFile) {
        $oldShortcut = $shell.CreateShortcut($AutoStartFile)
        if (!$oldShortcut.Arguments.Contains('"' + $ManagerScript + '"') -or !$oldShortcut.Arguments.Contains('-StateDir "' + $StateDir + '"')) {
            throw '已有同名启动项不属于当前管理脚本，已停止操作。'
        }
    }
    if ($Enabled) {
        if (!(Test-Path -LiteralPath $KeyFile)) { throw '请先成功配置并启动 ChatGPT 通道。' }
        $shortcut = $shell.CreateShortcut($AutoStartFile)
        $shortcut.TargetPath = (Get-Process -Id $PID).Path
        $shortcut.Arguments = '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $ManagerScript + '" -Action Start -Unattended -StateDir "' + $StateDir + '"'
        $shortcut.WorkingDirectory = $Repo
        $shortcut.WindowStyle = 7
        $shortcut.Save()
        Write-Host '已启用当前 Windows 用户登录后自动启动 ChatGPT 通道。'
    } else {
        if (Test-Path -LiteralPath $AutoStartFile) { Remove-Item -LiteralPath $AutoStartFile }
        Write-Host '已关闭登录后自启；Codex 的 stdio 自动启动不受影响。'
    }
}
function Invoke-Action([string]$Selected) {
    switch ($Selected) {
        'Setup' { Install-Local; Start-Tunnel }
        'Install' { Install-Local }
        'Cookie' { Update-Cookie }
        'TunnelKey' { Configure-TunnelKey }
        'Start' { Start-Tunnel }
        'Status' {
            if ($Settings.python) { $null = Check-Cookie } else { Write-Host '本地环境尚未安装。' }
            Show-TunnelStatus (Tunnel-Status)
            Write-Host ('Windows 登录后自启：' + (Test-Path -LiteralPath $AutoStartFile))
            if (Test-Path -LiteralPath (Join-Path $StateDir 'last-error.json')) { $last = Get-Content -LiteralPath (Join-Path $StateDir 'last-error.json') -Raw | ConvertFrom-Json; Write-Host ('上次未完成的操作：' + $last.error) }
        }
        'Stop' { $state = Tunnel-Status; Check-TunnelOwner $state; if ($state) { Run-Checked $Settings.tunnel_client @('runtimes','stop',$Alias) | Out-Host } else { Write-Host '没有需要停止的本地通道。' } }
        'EnableAutoStart' { Set-AutoStart $true }
        'DisableAutoStart' { Set-AutoStart $false }
    }
}
try {
    if ($Action -ne 'Menu') { Invoke-Action $Action }
    else {
        do {
            Write-Host "`nLinux.do 阅读助手"
            Write-Host '1 一键安装、授权并启动   2 启动已配置的 ChatGPT 通道   3 检查状态'
            Write-Host '4 更新 Cookie   5 配置 ChatGPT 授权   6 停止 ChatGPT 通道'
            Write-Host '7 Windows 登录后自动启动   8 关闭登录后自启   9 仅安装/更新本机 Codex   0 退出'
            $choice = Read-Host '请选择'
            $choices = @{ '1'='Setup';'2'='Start';'3'='Status';'4'='Cookie';'5'='TunnelKey';'6'='Stop';'7'='EnableAutoStart';'8'='DisableAutoStart';'9'='Install' }
            if ($choices.ContainsKey($choice)) { try { Invoke-Action $choices[$choice] } catch { Write-Host $_.Exception.Message -ForegroundColor Yellow } }
        } while ($choice -ne '0')
    }
} catch {
    if (Test-Path -LiteralPath $StateDir) { [ordered]@{time=[DateTime]::UtcNow.ToString('o');action=$Action;error=$_.Exception.Message} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $StateDir 'last-error.json') -Encoding utf8 }
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
