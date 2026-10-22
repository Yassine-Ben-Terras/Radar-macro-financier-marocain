param(
    [ValidateSet('Validate', 'WhatIf', 'Deploy')]
    [string]$Action = 'Validate'
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'deployment-settings.ps1')
$subscriptionId = $deployment.subscription_id
$resourceGroup = $deployment.resource_group
$templatePath = Join-Path $PSScriptRoot '../infra/workspace.json'
# The subscription and spending limit are never changed by this script.
# Resource provider registration and the empty resource group are prerequisites.
$arguments = @('--subscription', $subscriptionId, '--resource-group', $resourceGroup,
    '--name', 'radar-serverless', '--template-file', $templatePath,
    '--parameters', "workspaceName=$($deployment.workspace_name)")
& az deployment group validate @arguments
if ($LASTEXITCODE -ne 0) { throw 'Azure validation failed; deployment stopped.' }
if ($Action -eq 'WhatIf') {
    & az deployment group what-if @arguments
    if ($LASTEXITCODE -ne 0) { throw 'Azure what-if failed.' }
}
if ($Action -eq 'Deploy') {
    & az deployment group create @arguments
    if ($LASTEXITCODE -ne 0) { throw 'Azure deployment failed.' }
}
