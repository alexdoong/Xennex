<#
.SYNOPSIS
    Script automatizado e infalivel de empacotamento do Xennex para distribuicao universal ("Normie PC").
.DESCRIPTION
    Compila o frontend, valida o bundle JS exato referenciado pelo index.html, publica o C#
    em modo Self-Contained, garante a copia plana (sem aninhamento wwwroot\wwwroot),
    inclui WebView2Loader.dll, assina digitalmente e compacta em ZIP.
#>

param(
    [string]$Version
)

$ErrorActionPreference = "Stop"
$rootDir = (Get-Item $PSScriptRoot).Parent.FullName
Set-Location $rootDir
. (Join-Path $PSScriptRoot "lib\ReleaseValidation.ps1")
$projectPath = Join-Path $rootDir "Xennex.csproj"
$Version = Get-XennexReleaseVersion -ProjectPath $projectPath -RequestedVersion $Version

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

# O visualizador web usa o mesmo codigo React do aplicativo.
Push-Location $frontendDir
try {
    cmd /c "npm run build:web"
    if ($LASTEXITCODE -ne 0) { throw "Falha no build web do streaming." }
}
finally { Pop-Location }

# 2. Validacao rigorosa dos arquivos em wwwroot
Write-Host "`n[2/6] Validando integridade dos assets do wwwroot..." -ForegroundColor Yellow
$wwwroot = Join-Path $rootDir "wwwroot"
Assert-XennexFrontend $wwwroot

# 3. Publicar .NET Self-Contained
Write-Host "`n[3/6] Publicando executavel .NET 8 Self-Contained (Win-x64)..." -ForegroundColor Yellow
$stagingDir = Join-Path $rootDir "publish_temp_package"
if (Test-Path $stagingDir) {
    Remove-XennexBuildDirectory $stagingDir $rootDir
}

dotnet publish $projectPath -c Release -r win-x64 --self-contained true `
    -p:PublishSingleFile=true `
    -p:IncludeNativeLibrariesForSelfExtract=true `
    -o $stagingDir

if ($LASTEXITCODE -ne 0) {
    throw "Erro ao publicar aplicacao via dotnet publish."
}


# 3.1 Publicar Xennex.CaptureWorker (GPU WGC Engine)
Write-Host " -> Publicando Xennex.CaptureWorker (GPU WGC Engine)..." -ForegroundColor Yellow
$workerProj = Join-Path $rootDir "src\CaptureWorker\Xennex.CaptureWorker.csproj"
dotnet publish $workerProj -p:Version=$Version -c Release -r win-x64 --self-contained true `
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
if (-not (Test-Path -LiteralPath $nativeDll -PathType Leaf)) {
    throw "WebView2Loader.dll win-x64 ausente: $nativeDll"
}
Copy-Item -LiteralPath $nativeDll -Destination (Join-Path $stagingDir "WebView2Loader.dll") -Force

# Limpar qualquer wwwroot residual criado pelo dotnet publish no staging
$stagingWwwroot = Join-Path $stagingDir "wwwroot"
if (Test-Path $stagingWwwroot) {
    Remove-XennexBuildDirectory $stagingWwwroot $stagingDir
}
New-Item -ItemType Directory -Path $stagingWwwroot -Force | Out-Null

# Copiar conteudo do wwwroot para staging\wwwroot
Copy-Item -Recurse -Path "$wwwroot\*" -Destination "$stagingWwwroot\" -Force

# Somente a skin distribuivel; nunca carregar skins pessoais no ZIP.
$stagingSkins = Join-Path $stagingWwwroot "skins"
Remove-XennexBuildDirectory $stagingSkins $stagingDir
New-Item -ItemType Directory -Path $stagingSkins -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $wwwroot "skins\default") -Destination $stagingSkins -Recurse -Force
Assert-XennexFrontend $stagingWwwroot

# Distribuir somente os scripts necessarios ao usuario final.
$stagingScripts = Join-Path $stagingDir "scripts"
Remove-XennexBuildDirectory $stagingScripts $stagingDir
New-Item -ItemType Directory -Path $stagingScripts -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "hand_motion.py") -Destination $stagingScripts -Force

# Criar pasta Data de distribuicao com whitelist estrita (zero vazamento de dados locais/pessoais)
$stagingData = Join-Path $stagingDir "Data"
Remove-XennexBuildDirectory $stagingData $stagingDir
New-Item -ItemType Directory -Path $stagingData -Force | Out-Null

# 1. Config.txt padrao limpo
$cleanConfig = @"
REAL.exe
CloseToTray=false,AutoStart=false,SidebarMonitor=0,HideSidebarPullTab=false,SidebarPosition=Right,HandMotionCameraIndex=0,WindowLeft=375,WindowTop=197,AutoHideSidebar=false,AutoHideTitlebar=false
"@
Set-Content -Path (Join-Path $stagingData "config.txt") -Value $cleanConfig -Encoding UTF8

# 2. Whitelist estrita de arquivos publicos permitidos em Data/
# Bloqueio absoluto de dados de usuario (ex: wuwa_build.txt, logs *.txt/*.log, configs locais)
$allowedDataFiles = @("gestures.json", "swipe_config.json", "team_config.txt")
$dataSrc = Join-Path $rootDir "assets\defaults"
if (Test-Path $dataSrc) {
    foreach ($fileName in $allowedDataFiles) {
        $sourceFile = Join-Path $dataSrc $fileName
        if (Test-Path $sourceFile) {
            Copy-Item $sourceFile (Join-Path $stagingData $fileName) -Force
            Write-Host "    + Incluido template publico em Data: $fileName" -ForegroundColor Gray
        }
    }
}
Write-Host " -> Dados limpos de configuracao montados (whitelist estrita aplicada)." -ForegroundColor Green

# 5. Assinatura Authenticode Oficial (alexdoong)
Write-Host "`n[5/6] Aplicando assinatura digital Authenticode oficial (alexdoong)..." -ForegroundColor Yellow
$exePath = Join-Path $stagingDir "Xennex.exe"
$workerPath = Join-Path $stagingDir "Xennex.CaptureWorker.exe"
try {
    $cert = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert | Where-Object { $_.Subject -like "*alexdoong*" } | Select-Object -First 1
    if (-not $cert) {
        $cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject "CN=alexdoong, O=alexdoong, OU=Xennex Project, C=BR" -CertStoreLocation Cert:\CurrentUser\My -NotAfter (Get-Date).AddYears(10) -KeyUsage DigitalSignature -KeySpec Signature
    }
    Set-AuthenticodeSignature -FilePath $exePath -Certificate $cert -TimestampServer "http://timestamp.digicert.com" -ErrorAction Stop | Out-Null
    if (Test-Path $workerPath) {
        Set-AuthenticodeSignature -FilePath $workerPath -Certificate $cert -TimestampServer "http://timestamp.digicert.com" -ErrorAction Stop | Out-Null
    }

    foreach ($binary in @($exePath, $workerPath)) {
        Assert-XennexSignature -Path $binary -ExpectedThumbprint $cert.Thumbprint
    }

    # Incluir o certificado publico (.cer) e o instalador de 1 clique na raiz do pacote
    $cerPath = Join-Path $stagingDir "alexdoong.cer"
    Export-Certificate -Cert $cert -FilePath $cerPath -Force | Out-Null
    $batchSrc = Join-Path $rootDir "scripts\instalar_certificado_alexdoong.cmd"
    if (Test-Path $batchSrc) {
        Copy-Item $batchSrc (Join-Path $stagingDir "instalar_certificado_alexdoong.cmd") -Force
    }
    Write-Host " -> Executaveis assinados com o distribuidor oficial 'alexdoong' e certificado anexado." -ForegroundColor Green
}
catch {
    throw "Falha na assinatura obrigatoria: $($_.Exception.Message)"
}

# Validar o pacote completo antes de compactar.
Get-ChildItem -LiteralPath $stagingDir -Recurse -File |
    Where-Object { $_.Extension -in '.pdb', '.log' -or $_.Name -like '*_log.txt' } |
    Remove-Item -Force
Assert-XennexPackage $stagingDir

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
    Remove-XennexBuildDirectory $finalFolder $backupDir
}
Copy-Item -Recurse -Path $stagingDir -Destination $finalFolder

Assert-XennexPackage $finalFolder
Compress-Archive -LiteralPath $finalFolder -DestinationPath $zipPath -CompressionLevel Optimal

# Atualizar executavel e dependencias na raiz do projeto se nao estiver em execucao
try {
    Copy-Item (Join-Path $stagingDir "Xennex.exe") (Join-Path $rootDir "Xennex.exe") -Force
    if (Test-Path (Join-Path $stagingDir "Xennex.CaptureWorker.exe")) { Copy-Item (Join-Path $stagingDir "Xennex.CaptureWorker.exe") (Join-Path $rootDir "Xennex.CaptureWorker.exe") -Force }
    Write-Host " -> Xennex.exe da raiz atualizado com sucesso!" -ForegroundColor Green
} catch {
    Write-Host " -> [AVISO] Xennex.exe na raiz esta em execucao e nao pode ser sobrescrito." -ForegroundColor Yellow
}

# Limpar staging
Remove-XennexBuildDirectory $stagingDir $rootDir

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
