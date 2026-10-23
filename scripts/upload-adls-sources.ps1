$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'deployment-settings.ps1')
$env:DATABRICKS_HOST = $deployment.workspace_host
$env:DATABRICKS_AUTH_TYPE = 'azure-cli'
$env:ARM_TENANT_ID = (& az account show --subscription $deployment.subscription_id --query tenantId -o tsv)
if ($LASTEXITCODE -ne 0) { throw 'Azure authentication failed.' }
$projectRoot = Split-Path $PSScriptRoot -Parent
$remoteRoot = 'dbfs:/Volumes/radar_adls/radar_bronze/raw_files'
$verificationRoot = Join-Path $projectRoot ('outputs/adls-verification/' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $verificationRoot -Force | Out-Null
foreach ($folder in @('bronze','documents')) {
    $source = Join-Path $projectRoot "data/$folder"
    & databricks fs cp $source "$remoteRoot/$folder" --recursive
    if ($LASTEXITCODE -ne 0) { throw "Upload failed: $folder" }
    $download = Join-Path $verificationRoot $folder
    & databricks fs cp "$remoteRoot/$folder" $download --recursive
    if ($LASTEXITCODE -ne 0) { throw "Verification download failed: $folder" }
    foreach ($file in Get-ChildItem $source -File -Recurse) {
        $relative = [IO.Path]::GetRelativePath($source, $file.FullName)
        $actual = Join-Path $download $relative
        if ((Get-FileHash $file.FullName -Algorithm SHA256).Hash -ne (Get-FileHash $actual -Algorithm SHA256).Hash) {
            throw "SHA256 mismatch: $relative"
        }
        Write-Output "SHA256 verified: $folder/$relative"
    }
}
