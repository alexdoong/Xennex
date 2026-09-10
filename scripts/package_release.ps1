<#
.SYNOPSIS
    Script automatizado e infalivel de empacotamento do Xennex para distribuicao universal ("Normie PC").
.DESCRIPTION
    Compila o frontend, valida o bundle JS exato referenciado pelo index.html, publica o C#
    em modo Self-Contained, garante a copia plana (sem aninhamento wwwroot\wwwroot),
    inclui WebView2Loader.dll, assina digitalmente e compacta em ZIP.
#>

param(
    [string]$Version = "0.2.2"
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
    cmd /c "npm run build"
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
$indexHtml = Join-Path $wwwroot "index.html"
if (-not (Test-Path $indexHtml)) {
    throw "FALHA CRITICA: wwwroot/index.html nao foi encontrado!"
}

$htmlContent = Get-Content $indexHtml -Raw
if ($htmlContent -notmatch 'src="/assets/(index-[^"]+\.js)"') {
    throw "FALHA CRITICA: index.html nao contem referencia para /assets/index-*.js!"
}
$expectedJs = $matches[1]

if ($htmlContent -notmatch 'href="/assets/(index-[^"]+\.css)"') {
    throw "FALHA CRITICA: index.html nao contem referencia para /assets/index-*.css!"
}
$expectedCss = $matches[1]

$jsPath = Join-Path (Join-Path $wwwroot "assets") $expectedJs
if (-not (Test-Path $jsPath)) {
    throw "FALHA CRITICA: O arquivo JavaScript '$expectedJs' referenciado pelo index.html nao existe em wwwroot/assets!"
}
$jsSizeKb = [math]::Round((Get-Item $jsPath).Length / 1KB, 1)
if ($jsSizeKb -lt 50) {
    throw "FALHA CRITICA: O bundle JavaScript '$expectedJs' parece corrompido (tamanho $jsSizeKb KB < 50 KB)!"
}
Write-Host " -> Bundle JS verificado: $expectedJs ($jsSizeKb KB)" -ForegroundColor Green

$cssPath = Join-Path (Join-Path $wwwroot "assets") $expectedCss
if (-not (Test-Path $cssPath)) {
    throw "FALHA CRITICA: O arquivo CSS '$expectedCss' nao existe em wwwroot/assets!"
}
$cssSizeKb = [math]::Round((Get-Item $cssPath).Length / 1KB, 1)
Write-Host " -> Bundle CSS verificado: $expectedCss ($cssSizeKb KB)" -ForegroundColor Green

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


# 3.1 Publicar Xennex.CaptureWorker (GPU WGC Engine)
Write-Host " -> Publicando Xennex.CaptureWorker (GPU WGC Engine)..." -ForegroundColor Yellow
$workerProj = Join-Path $rootDir "src\CaptureWorker\Xennex.CaptureWorker.csproj"
dotnet publish $workerProj -c Release -r win-x64 --self-contained true `
    -p:PublishSingleFile=true `
    -p:IncludeNativeLibrariesForSelfExtract=true `
    -o $stagingDir

if ($LASTEXITCODE -ne 0) {
    throw "Erro ao publicar Xennex.CaptureWorker via dotnet publish."
}

# Remover .pdb
Get-ChildItem -Path $stagingDir -Filter "*.pdb" -Recurse | Remove-Item -Force -ErrorAction SilentlyContinue

# 4. Montar pacote de forma plana e limpa (sem aninhamento wwwroot\wwwroot)
Write-Host "`n[4/6] Montando pacote e dependencias nativas..." -ForegroundColor Yellow

# Copiar WebView2Loader.dll para a raiz do staging
$nativeDll = Join-Path $rootDir "bin\Release\net8.0-windows\win-x64\runtimes\win-x64\native\WebView2Loader.dll"
if (Test-Path $nativeDll) {
    Copy-Item $nativeDll (Join-Path $stagingDir "WebView2Loader.dll") -Force
    Write-Host " -> WebView2Loader.dll copiado com sucesso." -ForegroundColor Green
} else {
    $foundDll = Get-ChildItem -Path (Join-Path $rootDir "bin") -Filter "WebView2Loader.dll" -Recurse | Select-Object -First 1
    if ($foundDll) {
        Copy-Item $foundDll.FullName (Join-Path $stagingDir "WebView2Loader.dll") -Force
        Write-Host " -> WebView2Loader.dll encontrado e copiado." -ForegroundColor Green
    }
}

# Limpar qualquer wwwroot residual criado pelo dotnet publish no staging
$stagingWwwroot = Join-Path $stagingDir "wwwroot"
if (Test-Path $stagingWwwroot) {
    Remove-Item -Recurse -Force $stagingWwwroot
}
New-Item -ItemType Directory -Path $stagingWwwroot -Force | Out-Null

# Copiar conteudo do wwwroot para staging\wwwroot
Copy-Item -Recurse -Path "$wwwroot\*" -Destination "$stagingWwwroot\" -Force

# Validar que NAO existe aninhamento wwwroot\wwwroot
if (Test-Path (Join-Path $stagingWwwroot "wwwroot")) {
    throw "FALHA CRITICA: Ocorreu aninhamento indevido de wwwroot\wwwroot no pacote de distribuicao!"
}

# Validar que o JS e CSS estao fisicamente presentes no staging
$stagingJs = Join-Path (Join-Path $stagingWwwroot "assets") $expectedJs
if (-not (Test-Path $stagingJs)) {
    throw "FALHA CRITICA: O arquivo JavaScript '$expectedJs' nao foi encontrado no staging de distribuicao!"
}
Write-Host " -> wwwroot validado com sucesso no pacote final ($expectedJs presente)." -ForegroundColor Green

# Copiar scripts
$scriptsDir = Join-Path $rootDir "scripts"
if (Test-Path $scriptsDir) {
    $stagingScripts = Join-Path $stagingDir "scripts"
    New-Item -ItemType Directory -Path $stagingScripts -Force | Out-Null
    Copy-Item -Recurse -Path "$scriptsDir\*" -Destination "$stagingScripts\" -Force
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

$folderName = "Xennex-v$Version-win64"
$finalFolder = Join-Path $backupDir $folderName
if (Test-Path $finalFolder) {
    Remove-Item -Recurse -Force $finalFolder
}
Copy-Item -Recurse -Path $stagingDir -Destination $finalFolder

Compress-Archive -Path "$stagingDir\*" -DestinationPath $zipPath -CompressionLevel Optimal

# Atualizar executavel e dependencias na raiz do projeto se nao estiver em execucao
try {
    Copy-Item (Join-Path $stagingDir "Xennex.exe") (Join-Path $rootDir "Xennex.exe") -Force
    if (Test-Path (Join-Path $stagingDir "Xennex.CaptureWorker.exe")) { Copy-Item (Join-Path $stagingDir "Xennex.CaptureWorker.exe") (Join-Path $rootDir "Xennex.CaptureWorker.exe") -Force }
    Write-Host " -> Xennex.exe da raiz atualizado com sucesso!" -ForegroundColor Green
} catch {
    Write-Host " -> [AVISO] Xennex.exe na raiz esta em execucao e nao pode ser sobrescrito." -ForegroundColor Yellow
}

# Limpar staging
Remove-Item -Recurse -Force $stagingDir

$zipItem = Get-Item $zipPath
$zipSizeMb = [math]::Round($zipItem.Length / 1MB, 1)
$hash = (Get-FileHash -Path $zipPath -Algorithm SHA256).Hash

Write-Host "`n======================================================" -ForegroundColor Green
Write-Host "   PACOTE GERADO E VALIDADO COM SUCESSO!             " -ForegroundColor Green
Write-Host "======================================================" -ForegroundColor Green
Write-Host " Arquivo:  $zipPath" -ForegroundColor White
Write-Host " Tamanho:  $zipSizeMb MB" -ForegroundColor White
Write-Host " SHA256:   $hash" -ForegroundColor White
Write-Host " Pasta:    $finalFolder" -ForegroundColor White
Write-Host "======================================================`n" -ForegroundColor Green
