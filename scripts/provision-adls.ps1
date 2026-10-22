param([ValidateSet('Validate', 'WhatIf', 'Deploy')][string]$Action = 'Validate')
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'deployment-settings.ps1')
$subscriptionId = $deployment.subscription_id
$templatePath = Join-Path $PSScriptRoot '../infra/adls.json'
$arguments = @('--subscription', $subscriptionId, '--resource-group', $deployment.resource_group,
    '--name', 'radar-adls', '--template-file', $templatePath,
    '--parameters', "storageName=$($deployment.storage_account)", "connectorName=$($deployment.access_connector)")
# No subscription upgrade, compute launch, or resource deletion.
& az deployment group validate @arguments
if ($LASTEXITCODE -ne 0) { throw 'ADLS validation failed; stopped.' }
if ($Action -eq 'WhatIf') {
    & az deployment group what-if @arguments
    if ($LASTEXITCODE -ne 0) { throw 'ADLS what-if failed.' }
}
if ($Action -eq 'Deploy') {
    & az deployment group create @arguments
    if ($LASTEXITCODE -ne 0) { throw 'ADLS deployment failed.' }
}
