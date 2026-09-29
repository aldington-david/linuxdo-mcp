#requires -Version 7.0
# Offline checks: no real key, Cookie, plugin, or Tunnel changes.
$ErrorActionPreference = 'Stop'
$script = Join-Path (Split-Path $PSScriptRoot) 'Manage-LinuxDo.ps1'
$tokens = $null; $errors = $null
[void][Management.Automation.Language.Parser]::ParseFile($script,[ref]$tokens,[ref]$errors)
if ($errors.Count) { throw 'Manager syntax check failed' }
$testDir = Join-Path ([IO.Path]::GetTempPath()) ('linuxdo-manager-test-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testDir | Out-Null
try {
    $xml = Join-Path $testDir 'key.xml'
    $sample = ConvertTo-SecureString 'only-a-test-secret' -AsPlainText -Force
    $sample | Export-Clixml -LiteralPath $xml
    if ((Get-Content -LiteralPath $xml -Raw).Contains('only-a-test-secret')) { throw 'Secret stored as plaintext' }
    $loaded = Import-Clixml -LiteralPath $xml
    if ([Net.NetworkCredential]::new('', $loaded).Password -ne 'only-a-test-secret') { throw 'DPAPI roundtrip failed' }
    $loaded.Dispose(); $sample.Dispose()
    $output = & (Get-Process -Id $PID).Path -NoProfile -File $script -Action Status -StateDir (Join-Path $testDir 'empty')
    if ($LASTEXITCODE -ne 0) { throw 'Empty-state status failed' }
    if (Test-Path -LiteralPath (Join-Path $testDir 'empty\settings.json')) { throw 'Status unexpectedly changed configuration' }
    . $script -Action Status -StateDir (Join-Path $testDir 'empty') | Out-Null
    $Settings.python = 'C:\path with spaces\python.exe'
    if ((Get-McpCommand) -ne '"C:/path with spaces/python.exe" -m linuxdo_mcp.server') { throw 'Tunnel Python command is not portable' }
    $Settings.tunnel_id = 'tunnel_expected'
    $rejected = $false
    try { Check-TunnelOwner @{tunnel_id='tunnel_unrelated'} } catch { $rejected=$true }
    if (!$rejected) { throw 'Unrelated tunnel was accepted' }
    $AutoStartFile = Join-Path $testDir 'startup-test.lnk'
    $KeyFile = $xml
    Set-AutoStart $true
    $link = (New-Object -ComObject WScript.Shell).CreateShortcut($AutoStartFile)
    if (!$link.Arguments.Contains('-Action Start -Unattended')) { throw 'Startup shortcut is not unattended' }
    Set-AutoStart $false
    if (Test-Path -LiteralPath $AutoStartFile) { throw 'Owned shortcut was not removed' }
    $link.Arguments = 'unrelated-app'
    $link.Save()
    $rejected = $false
    try { Set-AutoStart $false } catch { $rejected=$true }
    if (!$rejected -or !(Test-Path -LiteralPath $AutoStartFile)) { throw 'Unrelated shortcut was modified' }
    Write-Host 'PASS: parser, DPAPI, status, Windows command, ownership guards, isolated startup shortcut.'
} finally {
    # Only remove the exact newly created test directory, after checking its parent.
    $resolved = (Resolve-Path -LiteralPath $testDir).Path
    if ((Split-Path $resolved) -ne ([IO.Path]::GetTempPath()).TrimEnd('\')) { throw 'Unexpected cleanup path' }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
