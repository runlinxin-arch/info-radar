# Remove the InfoRadar scheduled tasks (app + tunnel).
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File deploy\windows\uninstall_tasks.ps1
#
# Stops and deletes the tasks only. Code, database and cloudflared config are
# left untouched.
#
# ASCII-only on purpose: Windows PowerShell 5.1 reads BOM-less .ps1 files as
# ANSI, so non-ASCII characters can break parsing. See README.md.

$ErrorActionPreference = 'Continue'

foreach ($n in @('InfoRadar-App', 'InfoRadar-Tunnel')) {
    & schtasks /end /tn $n 2>$null | Out-Null
    $out = & schtasks /delete /tn $n /f 2>&1
    if ($LASTEXITCODE -eq 0) { Write-Host "  [OK] deleted $n" }
    else { Write-Host "  [skip] $n : $out" }
}

Write-Host ""
Write-Host "Tasks removed. To run manually:"
Write-Host "  pythonw run.py                      (app)"
Write-Host '  cloudflared tunnel run inforadar    (tunnel)'
