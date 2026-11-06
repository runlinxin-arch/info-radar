# Install InfoRadar as Windows Scheduled Tasks (app + Cloudflare tunnel).
#
# Why scheduled tasks instead of the Startup folder / Start-Process:
#   - Startup-folder shortcuts proved unreliable (2026-11-06: neither process
#     started after boot).
#   - Processes launched with Start-Process from an AI session are children of
#     that session; a session restart kills them (2026-11-06: 17 minutes down).
#   - Scheduled tasks are launched by the Task Scheduler service, so they are
#     not attached to any terminal session.
#
# Behaviour:
#   - Registered as a per-user task; no administrator rights required.
#   - Watchdog: TWO triggers.
#       * LogonTrigger  -> start immediately when the user logs in
#       * TimeTrigger   -> repeat every 1 minute, indefinitely
#     Combined with MultipleInstancesPolicy=IgnoreNew this means
#     "if it is not running, start it; if it is running, do nothing".
#   - Two things did NOT work and must not be reintroduced (verified 2026-11-06):
#       1. <RestartOnFailure> alone: a killed interactive-token task reported
#          result 0xFFFFFFFF and never restarted.
#       2. <Repetition> attached to a LogonTrigger: it registers with an empty
#          Duration and never fires.
#     The TimeTrigger + Repetition combination is the one that actually works.
#   - No execution time limit; battery restrictions disabled.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File deploy\windows\install_tasks.ps1
#
# NOTE: this file is intentionally ASCII-only. Windows PowerShell 5.1 parses
# .ps1 files as ANSI unless they carry a UTF-8 BOM, so any non-ASCII character
# here can break parsing on a clean machine. Chinese documentation lives in
# deploy/windows/README.md instead.
#
# LIMITATION: LogonTrigger means "someone must log in". If the machine boots
# and nobody logs in, nothing starts. Removing that limit requires admin rights
# (SYSTEM/BootTrigger) or moving to a cloud server.

$ErrorActionPreference = 'Stop'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$User = "$env:USERDOMAIN\$env:USERNAME"

# ---------- locate pythonw.exe ----------
$Pythonw = $null
$candidates = Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python3*\pythonw.exe" -ErrorAction SilentlyContinue |
    Sort-Object FullName -Descending
if ($candidates) { $Pythonw = @($candidates)[0].FullName }
if (-not $Pythonw) {
    $cmd = Get-Command pythonw.exe -ErrorAction SilentlyContinue
    if ($cmd) { $Pythonw = $cmd.Source }
}
if (-not $Pythonw) { throw "pythonw.exe not found; install Python 3 first" }

# ---------- locate cloudflared.exe ----------
$Cloudflared = @(
    'C:\Program Files (x86)\cloudflared\cloudflared.exe',
    'C:\Program Files\cloudflared\cloudflared.exe'
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $Cloudflared) {
    $cmd = Get-Command cloudflared.exe -ErrorAction SilentlyContinue
    if ($cmd) { $Cloudflared = $cmd.Source }
}
if (-not $Cloudflared) { throw "cloudflared.exe not found" }

Write-Host "repo        : $RepoRoot"
Write-Host "pythonw     : $Pythonw"
Write-Host "cloudflared : $Cloudflared"
Write-Host "run as      : $User (interactive logon)"
Write-Host ""

# Build the task XML. Both tasks share the same structure, only the action differs.
function New-TaskXml {
    param(
        [string]$Description,
        [string]$Command,
        [string]$Arguments,
        [string]$WorkingDirectory
    )
    return @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>$Description</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <UserId>$User</UserId>
    </LogonTrigger>
    <TimeTrigger>
      <Repetition>
        <Interval>PT1M</Interval>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
      <StartBoundary>2020-01-01T00:00:00</StartBoundary>
      <Enabled>true</Enabled>
    </TimeTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>$User</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <RestartOnFailure>
      <Interval>PT1M</Interval>
      <Count>999</Count>
    </RestartOnFailure>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>$Command</Command>
      <Arguments>$Arguments</Arguments>
      <WorkingDirectory>$WorkingDirectory</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"@
}

function Register-InfoRadarTask {
    param([string]$Name, [string]$Xml)

    $tmp = Join-Path $env:TEMP "$Name.xml"
    # Scheduled-task XML must be UTF-16
    Set-Content -Path $tmp -Value $Xml -Encoding Unicode

    $out = & schtasks /create /tn $Name /xml $tmp /f 2>&1
    $code = $LASTEXITCODE
    Remove-Item $tmp -ErrorAction SilentlyContinue
    if ($code -ne 0) { throw "failed to register task ${Name}: $out" }
    Write-Host "  [OK] registered $Name"
}

$appXml = New-TaskXml `
    -Description 'InfoRadar app (FastAPI on 127.0.0.1:7100, includes periodic crawl loop)' `
    -Command $Pythonw `
    -Arguments "$RepoRoot\run.py" `
    -WorkingDirectory $RepoRoot

$tunnelXml = New-TaskXml `
    -Description 'InfoRadar Cloudflare Tunnel (inforadar.xin -> 127.0.0.1:7100)' `
    -Command $Cloudflared `
    -Arguments 'tunnel run inforadar' `
    -WorkingDirectory $RepoRoot

Write-Host "Registering tasks:"
Register-InfoRadarTask -Name 'InfoRadar-App' -Xml $appXml
Register-InfoRadarTask -Name 'InfoRadar-Tunnel' -Xml $tunnelXml

Write-Host ""
Write-Host "Starting tasks:"
foreach ($n in @('InfoRadar-App', 'InfoRadar-Tunnel')) {
    $out = & schtasks /run /tn $n 2>&1
    if ($LASTEXITCODE -eq 0) { Write-Host "  [OK] started $n" }
    else { Write-Host "  [FAIL] $n : $out" }
}

Write-Host ""
Write-Host "log    : $RepoRoot\docs\audit\app.log"
Write-Host "remove : powershell -ExecutionPolicy Bypass -File deploy\windows\uninstall_tasks.ps1"
