param([switch]$BuildOnly, [switch]$StreamingPreview)

$ErrorActionPreference = 'Stop'
$projectRoot = (Get-Item $PSScriptRoot).Parent.FullName
Push-Location $projectRoot
try {
    Push-Location (Join-Path $projectRoot 'frontend')
    try {
        npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'Falha no frontend.' }
    }
    finally { Pop-Location }
    $output = Join-Path $projectRoot 'bin/Release/net8.0-windows'
    if ($StreamingPreview) { $output = Join-Path $projectRoot 'bin/StreamingPreview/net8.0-windows' }
    dotnet build Xennex.csproj -c Release -o $output
    if ($LASTEXITCODE -ne 0) { throw 'Falha no aplicativo.' }
    dotnet build src/CaptureWorker/Xennex.CaptureWorker.csproj -c Release
    if ($LASTEXITCODE -ne 0) { throw 'Falha no CaptureWorker.' }
    Write-Host "Build local pronto: $output"
    Write-Host 'As configuracoes deste build ficam em Data dentro da pasta de saida.'
    if (-not $BuildOnly) {
        Start-Process -FilePath (Join-Path $output 'Xennex.exe') -WorkingDirectory $output -WindowStyle Hidden
    }
}
finally { Pop-Location }
