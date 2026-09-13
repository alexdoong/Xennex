$ErrorActionPreference = 'Stop'
$root = (Get-Item $PSScriptRoot).Parent.Parent.FullName
. (Join-Path $root 'scripts/lib/ReleaseValidation.ps1')
$cert = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert | Where-Object { $_.Subject -like '*alexdoong*' -and $_.HasPrivateKey } | Select-Object -First 1
if (-not $cert) { throw 'Certificado de assinatura do projeto indisponivel.' }
$directory = Join-Path $root ('bin/signature-test-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $directory | Out-Null
try {
    $file = Join-Path $directory 'fixture.ps1'
    Set-Content -LiteralPath $file -Value "Write-Output 'fixture'" -Encoding UTF8
    Set-AuthenticodeSignature -FilePath $file -Certificate $cert | Out-Null
    Assert-XennexSignature $file $cert.Thumbprint
    $rejected = $false
    try { Assert-XennexSignature $file 'WRONG_SIGNER' } catch { $rejected = $true }
    if (-not $rejected) { throw 'Assinante incorreto foi aceito.' }
    $content = [IO.File]::ReadAllText($file).Replace("'fixture'", "'tampered'")
    [IO.File]::WriteAllText($file, $content, [Text.UTF8Encoding]::new($true))
    $rejected = $false
    try { Assert-XennexSignature $file $cert.Thumbprint } catch { $rejected = $true }
    if (-not $rejected) { throw 'Arquivo adulterado foi aceito.' }
    Write-Host 'PASS: assinatura integra aceita; assinante incorreto e adulteracao rejeitados.'
} finally { Remove-XennexBuildDirectory $directory $root }
