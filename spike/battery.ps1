# Spike-2 Stage C -- battery-gate measurement (ASCII-only for cp1252 safety).
# Usage:  powershell -File battery.ps1 start   (cable PLUGGED, before the walk)
#         ...unplug, walk 30-60 min with tracking ON...
#         powershell -File battery.ps1 stop     (right after plugging cable back)
param([Parameter(Mandatory)][ValidateSet("start", "stop")] $mode)

$adb = "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe"
$startFile = "$PSScriptRoot\battery_start.txt"

function Get-Level {
    $out = & $adb shell dumpsys battery
    foreach ($l in $out) { if ($l -match "level:\s*(\d+)") { return [int]$matches[1] } }
    return -1
}
function Get-Epoch { return [long]((& $adb shell date +%s).Trim()) }

if ($mode -eq "start") {
    & $adb shell dumpsys batterystats --reset | Out-Null
    $lvl = Get-Level; $t = Get-Epoch
    "$lvl,$t" | Set-Content $startFile
    Write-Output "START: level=$lvl% (batterystats reset)."
    Write-Output ">> NOW: unplug cable -> open Streif -> Start walk -> walk 30-60 min (screen may be off)."
}
else {
    if (-not (Test-Path $startFile)) { Write-Output "No battery_start.txt -- run 'start' first."; return }
    $s = (Get-Content $startFile).Split(","); $lvl0 = [int]$s[0]; $t0 = [long]$s[1]
    $lvl1 = Get-Level; $t1 = Get-Epoch
    $dLvl = $lvl0 - $lvl1
    $mins = [math]::Round(($t1 - $t0) / 60.0, 0)
    $hrs = ($t1 - $t0) / 3600.0
    $perHr = if ($hrs -gt 0) { [math]::Round($dLvl / $hrs, 1) } else { 0 }
    Write-Output "===== BATTERY-GATE RESULT ====="
    Write-Output "level: $lvl0% -> $lvl1%  (drop $dLvl%)  over ~$mins min"
    Write-Output "DRAIN: ~$perHr %/hour"
    Write-Output "--- batterystats (mAh since reset) ---"
    & $adb shell dumpsys batterystats --charged no.streif.spike 2>&1 |
        Select-String -Pattern "^\s*Discharge:|Screen off discharge:|Screen on discharge:|Estimated battery capacity:"
    & $adb shell dumpsys battery reset | Out-Null
    Write-Output "(gate ref: ~8-12 %/hour screen-off on Pixel 9; repeat 2-3x, start charge 60-80%)"
}
