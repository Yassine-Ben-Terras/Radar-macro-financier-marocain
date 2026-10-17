$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$destination = Join-Path $root 'data/documents'
New-Item -ItemType Directory -Force -Path $destination | Out-Null
$config = Get-Content -Raw (Join-Path $root 'config/sources.json') | ConvertFrom-Json
foreach ($source in $config.sources) {
    if ($source.PSObject.Properties.Name -notcontains 'format' -or $source.format -ne 'pdf') { continue }
    if ($source.id -notmatch '^[a-z0-9_]+$' -or ([uri]$source.url).Host -ne 'www.bkam.ma') {
        throw 'Unexpected source identifier or host'
    }
    $tempPath = Join-Path $destination ($source.id + '.download')
    Invoke-WebRequest -Uri $source.url -OutFile $tempPath -TimeoutSec 90
    $bytes = [System.IO.File]::ReadAllBytes($tempPath)
    if ($bytes.Length -lt 5 -or [System.Text.Encoding]::ASCII.GetString($bytes,0,5) -ne '%PDF-') {
        throw 'Response is not a PDF'
    }
    $sha = (Get-FileHash -LiteralPath $tempPath -Algorithm SHA256).Hash.ToLower()
    $archive = Join-Path $destination ('archive/' + $source.id + '/' + $sha)
    New-Item -ItemType Directory -Force -Path $archive | Out-Null
    $archivedFile = Join-Path $archive 'source.pdf'
    if (-not (Test-Path -LiteralPath $archivedFile)) {
        Copy-Item -LiteralPath $tempPath -Destination $archivedFile
        @{ source_id=$source.id; source_url=$source.url; file_sha256=$sha;
           retrieved_at=[DateTime]::UtcNow.ToString('o') } |
            ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $archive 'manifest.json')
    }
    # Preserve previous snapshots before replacing the local current copy.
    $current = Join-Path $destination ($source.id + '.pdf')
    if (Test-Path -LiteralPath $current) {
        $previousHash = (Get-FileHash -LiteralPath $current -Algorithm SHA256).Hash.ToLower()
        $previousArchive = Join-Path $destination ('archive/' + $source.id + '/' + $previousHash)
        New-Item -ItemType Directory -Force -Path $previousArchive | Out-Null
        if (-not (Test-Path -LiteralPath (Join-Path $previousArchive 'source.pdf'))) {
            Copy-Item -LiteralPath $current -Destination (Join-Path $previousArchive 'source.pdf')
        }
    }
    Copy-Item -LiteralPath $tempPath -Destination $current -Force
    Write-Output ($source.id + ' SHA256=' + $sha)
}
