<#
.SYNOPSIS
    Script automatizado de empacotamento do Xennex para distribuicao universal ("Normie PC").
.DESCRIPTION
    Compila o frontend, valida todos os assets, publica o C# em modo Self-Contained,
    inclui WebView2Loader.dll, copia configuracoes limpas, assina o executavel
    e compacta em um arquivo .zip pronto para o GitHub Releases.
#>

param(
    [string]$Version = "0.2.0"
)

$ErrorActionPreference = "Stop"
$rootDir = (Get-Item $PSScriptRoot).Parent.FullName
Set-Location $rootDir

Write-Host "======================================================" -ForegroundColor Cyan
Write-Host "   Xennex Release Packaging Engine (v$Version)       " -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan

# 1. Compilar Frontend
Write-Host "`n[1/6] Compilando interface React (frontend)..." -ForegroundColor Yellow
$frontendDir = Join-Path $rootDir "frontend"
Push-Location $frontendDir
try {
    npm run build
    if ($LASTEXITCODE -ne 0) {
        throw "Erro ao compilar o frontend React via npm run build."
    }
}
finally {
    Pop-Location
}

# 2. Validacao rigorosa dos arquivos em wwwroot
Write-Host "`n[2/6] Validando integridade dos assets do wwwroot..." -ForegroundColor Yellow
$wwwroot = Join-Path $rootDir "wwwroot"
$assetsDir = Join-Path $wwwroot "assets"

$indexHtml = Join-Path $wwwroot "index.html"
if (-not (Test-Path $indexHtml)) {
    throw "FALHA CRITICA: wwwroot/index.html nao foi encontrado!"
}

$jsFiles = Get-ChildItem -Path $assetsDir -Filter "index-*.js" -ErrorAction SilentlyContinue
if (-not $jsFiles -or $jsFiles.Count -eq 0) {
    throw "FALHA CRITICA: Nenhum bundle JS (index-*.js) foi encontrado em wwwroot/assets!"
}
Write-Host " -> Bundle JS verificado: $($jsFiles[0].Name) ($([math]::Round($jsFiles[0].Length / 1KB, 1)) KB)" -ForegroundColor Green

$cssFiles = Get-ChildItem -Path $assetsDir -Filter "index-*.css" -ErrorAction SilentlyContinue
if (-not $cssFiles -or $cssFiles.Count -eq 0) {
    throw "FALHA CRITICA: Nenhum bundle CSS (index-*.css) foi encontrado em wwwroot/assets!"
}
Write-Host " -> Bundle CSS verificado: $($cssFiles[0].Name) ($([math]::Round($cssFiles[0].Length / 1KB, 1)) KB)" -ForegroundColor Green

# 3. Publicar .NET Self-Contained
Write-Host "`n[3/6] Publicando executavel .NET 8 Self-Contained (Win-x64)..." -ForegroundColor Yellow
$stagingDir = Join-Path $rootDir "publish_temp_package"
if (Test-Path $stagingDir) {
    Remove-Item -Recurse -Force $stagingDir
}

dotnet publish -c Release -r win-x64 --self-contained true `
    -p:PublishSingleFile=true `
    -p:IncludeNativeLibrariesForSelfExtract=true `
    -o $stagingDir

if ($LASTEXITCODE -ne 0) {
    throw "Erro ao publicar aplicacao via dotnet publish."
}

# Remover .pdb
Get-ChildItem -Path $stagingDir -Filter "*.pdb" -Recurse | Remove-Item -Force -ErrorAction SilentlyContinue

# 4. Incluir WebView2Loader.dll, scripts e Data limpo
Write-Host "`n[4/6] Montando pacote e dependencias nativas..." -ForegroundColor Yellow

# Copiar WebView2Loader.dll para a raiz do staging
$nativeDll = Join-Path $rootDir "bin\Release\net8.0-windows\win-x64\runtimes\win-x64\native\WebView2Loader.dll"
if (Test-Path $nativeDll) {
    Copy-Item $nativeDll (Join-Path $stagingDir "WebView2Loader.dll") -Force
    Write-Host " -> WebView2Loader.dll copiado com sucesso." -ForegroundColor Green
} else {
    Write-Warning "WebView2Loader.dll nao encontrado no caminho de runtimes. Tentando buscar recursivamente..."
    $foundDll = Get-ChildItem -Path (Join-Path $rootDir "bin") -Filter "WebView2Loader.dll" -Recurse | Select-Object -First 1
    if ($foundDll) {
        Copy-Item $foundDll.FullName (Join-Path $stagingDir "WebView2Loader.dll") -Force
    }
}

# Copiar wwwroot completo
Copy-Item -Recurse -Path $wwwroot -Destination (Join-Path $stagingDir "wwwroot") -Force
Write-Host " -> Pasta wwwroot completa copiada." -ForegroundColor Green

# Copiar scripts
$scriptsDir = Join-Path $rootDir "scripts"
if (Test-Path $scriptsDir) {
    Copy-Item -Recurse -Path $scriptsDir -Destination (Join-Path $stagingDir "scripts") -Force
    Write-Host " -> Scripts copiados." -ForegroundColor Green
}

# Criar pasta Data de distribuicao sem caminhos locais do dev
$stagingData = Join-Path $stagingDir "Data"
New-Item -ItemType Directory -Path $stagingData -Force | Out-Null

$cleanConfig = @"
REAL.exe
CloseToTray=false,AutoStart=false,SidebarMonitor=0,HideSidebarPullTab=false,SidebarPosition=Right,HandMotionCameraIndex=0,WindowLeft=375,WindowTop=197,AutoHideSidebar=false,AutoHideTitlebar=false
"@
Set-Content -Path (Join-Path $stagingData "config.txt") -Value $cleanConfig -Encoding UTF8

$dataSrc = Join-Path $rootDir "Data"
if (Test-Path $dataSrc) {
    Get-ChildItem -Path $dataSrc | Where-Object { $_.Name -notlike "*.log" -and $_.Name -ne "config.txt" } | ForEach-Object {
        Copy-Item $_.FullName (Join-Path $stagingData $_.Name) -Force
    }
}
Write-Host " -> Dados limpos de configuracao montados." -ForegroundColor Green

# 5. Assinatura Authenticode
Write-Host "`n[5/6] Aplicando assinatura digital Authenticode..." -ForegroundColor Yellow
$exePath = Join-Path $stagingDir "Xennex.exe"
try {
    $cert = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert | Where-Object { $_.Subject -like "*Xennex*" } | Select-Object -First 1
    if (-not $cert) {
        $cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject "CN=Xennex (Alex Doong)" -CertStoreLocation Cert:\CurrentUser\My -NotAfter (Get-Date).AddYears(5)
    }
    Set-AuthenticodeSignature -FilePath $exePath -Certificate $cert -TimestampServer "http://timestamp.digicert.com" -ErrorAction SilentlyContinue | Out-Null
    Write-Host " -> Executavel assinado digitalmente." -ForegroundColor Green
}
catch {
    Write-Host " -> Assinatura opcional ignorada: $($_.Exception.Message)" -ForegroundColor Gray
}

# 6. Gerar ZIP de distribuicao
Write-Host "`n[6/6] Compactando versao para distribuicao..." -ForegroundColor Yellow
$backupDir = Join-Path $rootDir "Backup"
if (-not (Test-Path $backupDir)) {
    New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
}

$zipName = "Xennex-v$Version-win64.zip"
$zipPath = Join-Path $backupDir $zipName
if (Test-Path $zipPath) {
    Remove-Item -Force $zipPath
}

# Também salvar pasta descompactada para conveniência
$folderName = "Xennex-v$Version-win64"
$finalFolder = Join-Path $backupDir $folderName
if (Test-Path $finalFolder) {
    Remove-Item -Recurse -Force $finalFolder
}
Copy-Item -Recurse -Path $stagingDir -Destination $finalFolder

Compress-Archive -Path "$stagingDir\*" -DestinationPath $zipPath -CompressionLevel Optimal

# Limpar staging
Remove-Item -Recurse -Force $stagingDir

$zipItem = Get-Item $zipPath
$zipSizeMb = [math]::Round($zipItem.Length / 1MB, 1)
$hash = (Get-FileHash -Path $zipPath -Algorithm SHA256).Hash

Write-Host "`n======================================================" -ForegroundColor Green
Write-Host "   PACOTE GERADO COM SUCESSO!                        " -ForegroundColor Green
Write-Host "======================================================" -ForegroundColor Green
Write-Host " Arquivo:  $zipPath" -ForegroundColor White
Write-Host " Tamanho:  $zipSizeMb MB" -ForegroundColor White
Write-Host " SHA256:   $hash" -ForegroundColor White
Write-Host " Pasta:    $finalFolder" -ForegroundColor White
Write-Host "======================================================`n" -ForegroundColor Green
