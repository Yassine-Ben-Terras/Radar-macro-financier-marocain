$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'deployment-settings.ps1')
$env:DATABRICKS_HOST = $deployment.workspace_host
$env:DATABRICKS_AUTH_TYPE = 'azure-cli'
# ARM workspace ID loaded from deployment-settings.ps1
$env:ARM_TENANT_ID = (& az account show --subscription $deployment.subscription_id --query tenantId -o tsv)
if ($LASTEXITCODE -ne 0) { throw 'Azure authentication failed.' }
& databricks current-user me -o json
if ($LASTEXITCODE -ne 0) { throw 'Workspace access unavailable; import stopped.' }
$projectRoot = Split-Path $PSScriptRoot -Parent
$target = '/Shared/radar-macro'
foreach ($folder in @('notebooks', 'sql')) {
    & databricks workspace mkdirs "$target/$folder"
    if ($LASTEXITCODE -ne 0) { throw "Cannot create folder: $folder" }
    foreach ($source in Get-ChildItem (Join-Path $projectRoot $folder) -File) {
        if ($folder -eq 'notebooks' -and $source.Extension -eq '.py') {
            & databricks workspace import "$target/$folder/$($source.BaseName)" --file $source.FullName --format SOURCE --language PYTHON
        } elseif ($source.Extension -eq '.sql') {
            & databricks workspace import "$target/$folder/$($source.Name)" --file $source.FullName --format RAW
        } else { continue }
        if ($LASTEXITCODE -ne 0) { throw "Import failed: $($source.Name)" }
    }
}
& databricks workspace mkdirs "$target/radar"
if ($LASTEXITCODE -ne 0) { throw 'Cannot create module folder.' }
foreach ($module in Get-ChildItem (Join-Path $projectRoot 'radar') -Filter '*.py' -File) {
    & databricks workspace import "$target/radar/$($module.Name)" --file $module.FullName --format RAW
    if ($LASTEXITCODE -ne 0) { throw "Module import failed: $($module.Name)" }
}
& databricks workspace mkdirs "$target/config"
if ($LASTEXITCODE -ne 0) { throw 'Cannot create config folder.' }
foreach ($file in @('ingestion.json', 'sources.json', 'assistant-evaluation.json', 'deployment.local.json')) {
    & databricks workspace import "$target/config/$file" --file (Join-Path $projectRoot "config/$file") --format RAW
    if ($LASTEXITCODE -ne 0) { throw "Import failed: $file" }
}
& databricks workspace list "$target/notebooks" -o json
if ($LASTEXITCODE -ne 0) { throw 'Import verification failed.' }
# No compute is started. repo_root widget: /Workspace/Shared/radar-macro
