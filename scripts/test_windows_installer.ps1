# Exercise the generated installer in an isolated user-data directory on Windows.
[CmdletBinding()]
param(
    [string]$Installer,
    [string]$OutputDirectory
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if (-not $IsWindows) { throw 'This installer test must run on Windows.' }
$projectRoot = Split-Path $PSScriptRoot -Parent
if (-not $Installer) { $Installer = Join-Path $projectRoot 'dist/SlideVoice-Windows-x64-Setup.exe' }
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $projectRoot '.desktop-build/windows-installer-test' }
$Installer = (Resolve-Path $Installer).Path
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$OutputDirectory = (Resolve-Path $OutputDirectory).Path
$release = Get-Content (Join-Path $projectRoot '.desktop-build/resources/desktop-release.json') -Raw | ConvertFrom-Json
$sandbox = Join-Path ([IO.Path]::GetTempPath()) ('SlideVoice installer test ' + [guid]::NewGuid().ToString('N'))
$installation = Join-Path $sandbox 'Installed app'
$previousLocalAppData = $env:LOCALAPPDATA
$env:LOCALAPPDATA = Join-Path $sandbox 'User data'
New-Item -ItemType Directory -Path $env:LOCALAPPDATA -Force | Out-Null

function Invoke-CheckedProcess {
    param([string]$File, [string[]]$Arguments, [int]$TimeoutSeconds = 180)
    $process = Start-Process -FilePath $File -ArgumentList $Arguments -PassThru
    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        & taskkill.exe /PID $process.Id /T /F | Out-Null
        throw "Process timed out: $File"
    }
    $process.Refresh()
    if ($process.ExitCode -ne 0) { throw "Process failed ($($process.ExitCode)): $File" }
}

try {
    Invoke-CheckedProcess $Installer @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/TASKS=""',
        "/DIR=`"$installation`"", "/LOG=`"$(Join-Path $OutputDirectory 'install.log')`"")
    $executable = Join-Path $installation 'SlideVoice.exe'
    if (-not (Test-Path $executable)) { throw 'The installer did not install SlideVoice.exe.' }
    $info = (Get-Item $executable).VersionInfo
    if ($info.ProductName -ne 'SlideVoice' -or $info.ProductVersion -ne $release.version) {
        throw 'The installed executable has incorrect product/version metadata.'
    }
    $installedIcon = Join-Path $installation '_internal/app/static/branding/slidevoice.png'
    $masterIcon = Join-Path $projectRoot 'app/static/branding/slidevoice.png'
    if ((Get-FileHash $installedIcon).Hash -ne (Get-FileHash $masterIcon).Hash) {
        throw 'The installed app does not contain the current SlideVoice icon.'
    }
    # This also verifies Gemini-only settings and presentation assets over HTTP.
    Invoke-CheckedProcess $executable @('--smoke-test')
    $dataDirectory = Join-Path $env:LOCALAPPDATA 'SlideVoice/data'
    $marker = Join-Path $dataDirectory 'installer-preservation-check.txt'
    Set-Content $marker 'Preserve user projects when upgrading or uninstalling.'
    Invoke-CheckedProcess $Installer @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/TASKS=""',
        "/DIR=`"$installation`"", "/LOG=`"$(Join-Path $OutputDirectory 'upgrade.log')`"")
    if (-not (Test-Path $marker)) { throw 'Reinstalling removed user data.' }
    Invoke-CheckedProcess $executable @('--smoke-test')
    Invoke-CheckedProcess (Join-Path $installation 'unins000.exe') @('/VERYSILENT',
        '/SUPPRESSMSGBOXES', '/NORESTART', "/LOG=`"$(Join-Path $OutputDirectory 'uninstall.log')`"")
    if (Test-Path $executable) { throw 'Uninstalling left the installed executable behind.' }
    if (-not (Test-Path $marker)) { throw 'Uninstalling removed user data.' }
    @{status='passed'; version=$release.version; checks=@('install', 'branding',
        'packaged-backend', 'upgrade', 'uninstall', 'preserved-user-data')} |
        ConvertTo-Json | Set-Content (Join-Path $OutputDirectory 'result.json')
    Write-Output 'Windows installer, upgrade, packaged backend and data-preservation checks passed.'
} finally {
    $logs = Join-Path $env:LOCALAPPDATA 'SlideVoice/data/logs'
    if (Test-Path $logs) { Copy-Item $logs (Join-Path $OutputDirectory 'app-logs') -Recurse -Force }
    $env:LOCALAPPDATA = $previousLocalAppData
    # Only remove this test-created sandbox, never an actual installation or user-data directory.
    if (Test-Path $sandbox) { Remove-Item $sandbox -Recurse -Force }
}
