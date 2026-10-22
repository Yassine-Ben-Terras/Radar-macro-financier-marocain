# Dot-source this file after param() in Azure scripts. No cloud call is made here.
$deploymentPath = Join-Path $PSScriptRoot '../config/deployment.local.json'
if (-not (Test-Path -LiteralPath $deploymentPath)) {
    throw 'Copy config/deployment.example.json to config/deployment.local.json and configure your deployment.'
}
$deployment = Get-Content -LiteralPath $deploymentPath -Raw | ConvertFrom-Json
if ($deployment.subscription_id -notmatch '^[0-9a-fA-F-]{36}$') { throw 'Invalid subscription ID.' }
if ($deployment.workspace_host -notmatch '^https://adb-[0-9.]+\.azuredatabricks\.net$') { throw 'Invalid workspace host.' }
if ($deployment.storage_account -notmatch '^[a-z0-9]{3,24}$') { throw 'Invalid storage account.' }
$env:DATABRICKS_HOST = $deployment.workspace_host
$env:DATABRICKS_AZURE_RESOURCE_ID = "/subscriptions/$($deployment.subscription_id)/resourceGroups/$($deployment.resource_group)/providers/Microsoft.Databricks/workspaces/$($deployment.workspace_name)"
