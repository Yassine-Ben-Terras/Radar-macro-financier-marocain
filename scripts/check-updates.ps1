param([switch]$Apply, [switch]$Retry)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$python = if ($env:RADAR_PYTHON) { $env:RADAR_PYTHON } else { 'python' }
Push-Location $projectRoot
try {
    $options = @('-m', 'radar.refresh')
    if ($Apply) { $options += '--apply' }
    if ($Retry) { $options += '--retry' }
    & $python @options
    if ($LASTEXITCODE -ne 0) { throw "Refresh controller failed with exit code $LASTEXITCODE" }
} finally { Pop-Location }
