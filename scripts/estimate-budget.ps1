param(
    [Parameter(Mandatory=$true)][ValidateRange(0,100000)][decimal]$ComputeUsdPerHour,
    [Parameter(Mandatory=$true)][ValidateRange(0,744)][decimal]$ComputeHours,
    [Parameter(Mandatory=$true)][ValidateRange(0,100000)][decimal]$FixedMonthlyUsd,
    [Parameter(Mandatory=$true)][ValidateRange(0,100000)][decimal]$StorageAndNetworkUsd,
    [ValidateRange(0,100000)][decimal]$AvailableUsd = 50,
    [ValidateRange(0,100000)][decimal]$ReserveUsd = 15
)
$ErrorActionPreference = 'Stop'
if ($ReserveUsd -gt $AvailableUsd) { throw 'Reserve exceeds available budget.' }
$target = $AvailableUsd - $ReserveUsd
$estimate = ($ComputeUsdPerHour * $ComputeHours) + $FixedMonthlyUsd + $StorageAndNetworkUsd
[pscustomobject]@{
    EstimatedUsd = [math]::Round($estimate, 2)
    SpendingTargetUsd = $target
    RemainingToTargetUsd = [math]::Round($target - $estimate, 2)
    FitsTarget = ($estimate -le $target)
    Note = 'Scenario only: supply verified effective rates, including tax. Not a spending cap.'
}
