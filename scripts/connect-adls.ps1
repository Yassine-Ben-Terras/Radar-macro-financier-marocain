$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'deployment-settings.ps1')
$env:DATABRICKS_HOST = $deployment.workspace_host
$env:DATABRICKS_AUTH_TYPE = 'azure-cli'
$env:ARM_TENANT_ID = (& az account show --subscription $deployment.subscription_id --query tenantId -o tsv)
if ($LASTEXITCODE -ne 0) { throw 'Azure authentication failed.' }
function Invoke-Db([string[]]$Arguments) {
    $result = & databricks @Arguments -o json
    if ($LASTEXITCODE -ne 0) { throw "Databricks failed: $($Arguments[0..1] -join ' ')" }
    if ($result) { return ($result -join "`n" | ConvertFrom-Json -Depth 100) }
}
$credentialName = 'radar_adls_identity'
$connectorId = "/subscriptions/$($deployment.subscription_id)/resourceGroups/$($deployment.resource_group)/providers/Microsoft.Databricks/accessConnectors/$($deployment.access_connector)"
@{ name=$credentialName; azure_managed_identity=@{access_connector_id=$connectorId} } | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $PSScriptRoot '../config/adls-storage-credential.json') -Encoding utf8
foreach ($container in @('raw','lakehouse')) {
    @{name="radar_adls_$container"; url="abfss://$container@$($deployment.storage_account).dfs.core.windows.net/"; credential_name=$credentialName; enable_file_events=$false} | ConvertTo-Json | Set-Content (Join-Path $PSScriptRoot "../config/adls-location-$container.json") -Encoding utf8
}

$credentialFile = Join-Path $PSScriptRoot '../config/adls-storage-credential.json'
$expected = Get-Content $credentialFile -Raw | ConvertFrom-Json
$credentials = Invoke-Db @('storage-credentials','list')
$credential = $credentials | Where-Object name -eq $credentialName
if (-not $credential) { $credential = Invoke-Db @('storage-credentials','create','--json',"@$credentialFile") }
if ($credential.azure_managed_identity.access_connector_id -ne $expected.azure_managed_identity.access_connector_id) { throw 'Unexpected identity; stopped.' }
$locations = Invoke-Db @('external-locations','list')
foreach ($container in @('raw','lakehouse')) {
    $url = "abfss://$container@$($deployment.storage_account).dfs.core.windows.net/"
    $name = "radar_adls_$container"
    $location = $locations | Where-Object name -eq $name
    if (-not $location) { $location = Invoke-Db @('external-locations','create','--json',"@$(Join-Path $PSScriptRoot "../config/adls-location-$container.json")") }
    if ($location.url.TrimEnd('/') -ne $url.TrimEnd('/') -or $location.credential_name -ne $credentialName) { throw 'Unexpected external location; stopped.' }
    $location = Invoke-Db @('external-locations','update',$name,'--json',"@$(Join-Path $PSScriptRoot '../config/adls-disable-events.json')")
    $validation = Invoke-Db @('storage-credentials','validate','--storage-credential-name',$credentialName,'--external-location-name',$name)
    $validation | ConvertTo-Json -Depth 10
    if (@($validation.results | Where-Object result -ne 'PASS').Count -gt 0) { throw 'Storage validation did not pass.' }
}
$root = "abfss://lakehouse@$($deployment.storage_account).dfs.core.windows.net/catalogs/radar_adls"
$catalog = (Invoke-Db @('catalogs','list')) | Where-Object name -eq 'radar_adls'
if (-not $catalog) { $catalog = Invoke-Db @('catalogs','create','radar_adls','--storage-root',$root) }
if ($catalog.storage_root.TrimEnd('/') -ne $root) { throw 'Unexpected catalog storage root; stopped.' }
$null = Invoke-Db @('catalogs','update','radar_adls','--enable-predictive-optimization','DISABLE')
$schemas = Invoke-Db @('schemas','list','radar_adls')
foreach ($schema in @('radar_bronze','radar_silver','radar_gold')) {
    if (-not ($schemas | Where-Object name -eq $schema)) { $null = Invoke-Db @('schemas','create',$schema,'radar_adls') }
}
$volumes = Invoke-Db @('volumes','list','radar_adls','radar_bronze')
$volume = $volumes | Where-Object name -eq 'raw_files'
$raw = "abfss://raw@$($deployment.storage_account).dfs.core.windows.net/"
if (-not $volume) { $volume = Invoke-Db @('volumes','create','radar_adls','radar_bronze','raw_files','EXTERNAL','--storage-location',$raw) }
if ($volume.volume_type -ne 'EXTERNAL' -or $volume.storage_location.TrimEnd('/') -ne $raw.TrimEnd('/')) { throw 'Unexpected volume storage; stopped.' }
$volume | ConvertTo-Json -Depth 10
