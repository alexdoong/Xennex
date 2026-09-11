<#
.SYNOPSIS
    Gera o Certificado Digital de Assinatura de Código para alexdoong,
    exporta a chave pública alexdoong.cer e assina os executáveis do Xennex.
#>

$ErrorActionPreference = "Stop"

Write-Host "======================================================" -ForegroundColor Cyan
Write-Host "   Certificado Digital Oficial: alexdoong              " -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan

$subject = "CN=alexdoong, O=alexdoong, OU=Xennex Project, C=BR"
$cert = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert | Where-Object { $_.Subject -like "*alexdoong*" } | Select-Object -First 1

if (-not $cert) {
    Write-Host "`n[1/3] Gerando novo Certificado de Assinatura de Codigo (10 anos)..." -ForegroundColor Yellow
    $cert = New-SelfSignedCertificate -Type CodeSigningCert `
        -Subject $subject `
        -FriendlyName "alexdoong Authenticode Certificate" `
        -CertStoreLocation "Cert:\CurrentUser\My" `
        -NotAfter (Get-Date).AddYears(10) `
        -KeyUsage DigitalSignature `
        -KeySpec Signature
    Write-Host " -> Certificado gerado: $($cert.Thumbprint)" -ForegroundColor Green
} else {
    Write-Host "`n[1/3] Certificado existente de alexdoong encontrado: $($cert.Thumbprint)" -ForegroundColor Green
}

# 2. Exportar o certificado publico (.cer)
Write-Host "`n[2/3] Exportando certificado publico (alexdoong.cer)..." -ForegroundColor Yellow
$scriptDir = $PSScriptRoot
if (-not $scriptDir) { $scriptDir = "E:\Projetos e apps\Xennex\scripts" }
$cerPath = Join-Path $scriptDir "alexdoong.cer"

Export-Certificate -Cert $cert -FilePath $cerPath -Force | Out-Null
Write-Host " -> Exportado para: $cerPath" -ForegroundColor Green

# 3. Assinar executaveis do Xennex
Write-Host "`n[3/3] Assinando executaveis com a identidade 'alexdoong'..." -ForegroundColor Yellow
$rootDir = (Get-Item $scriptDir).Parent.FullName
$targets = @(
    (Join-Path $rootDir "Xennex.exe"),
    (Join-Path $rootDir "bin\Debug\net8.0-windows\Xennex.exe"),
    (Join-Path $rootDir "bin\Release\net8.0-windows\win-x64\Xennex.exe"),
    (Join-Path $rootDir "bin\Debug\net8.0-windows\Xennex.CaptureWorker.exe"),
    (Join-Path $rootDir "bin\Release\net8.0-windows\win-x64\Xennex.CaptureWorker.exe")
)

foreach ($t in $targets) {
    if (Test-Path $t) {
        $tName = Split-Path $t -Leaf
        try {
            $res = Set-AuthenticodeSignature -FilePath $t -Certificate $cert -TimestampServer "http://timestamp.digicert.com"
            Write-Host " -> Assinado: $tName (Status: $($res.Status))" -ForegroundColor Green
        } catch {
            Write-Host " -> Erro ao assinar $tName : $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }
}

Write-Host "`nConcluido! Executaveis assinados com o distribuidor oficial 'alexdoong'.`n" -ForegroundColor Cyan
