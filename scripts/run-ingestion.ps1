param([Parameter(Mandatory=$true)][string]$RunToken)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'deployment-settings.ps1')
$env:DATABRICKS_HOST = $deployment.workspace_host
$env:DATABRICKS_AUTH_TYPE = 'azure-cli'
$env:ARM_TENANT_ID = (& az account show --subscription $deployment.subscription_id --query tenantId -o tsv)
if ($LASTEXITCODE -ne 0) { throw 'Azure authentication failed.' }
$runConfig = Join-Path $PSScriptRoot '../infra/ingestion-adls-run.json'
# Same token returns the same run; never generate a new token for a polling retry.
& databricks jobs submit --json "@$runConfig" --idempotency-token $RunToken --no-wait -o json
if ($LASTEXITCODE -ne 0) { throw 'Run submission failed.' }
