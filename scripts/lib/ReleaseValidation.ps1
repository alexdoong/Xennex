function Assert-XennexSignature {
    param([string]$Path, [string]$ExpectedThumbprint)
    $signature = Get-AuthenticodeSignature -LiteralPath $Path
    if (-not $ExpectedThumbprint -or -not $signature.SignerCertificate -or $signature.SignerCertificate.Thumbprint -ne $ExpectedThumbprint) {
        throw "Assinante ausente ou incorreto: $Path"
    }
    if (-not ('Xennex.Build.AuthenticodeVerification' -as [type])) {
        Add-Type -Path (Join-Path $PSScriptRoot 'AuthenticodeVerification.cs')
    }
    $status = [Xennex.Build.AuthenticodeVerification]::Check((Resolve-Path -LiteralPath $Path).Path)
    # Our self-signed distribution certificate is shipped with the installer.
    # Accept only the specific trust-root error, never an arbitrary UnknownError.
    if ($status -ne 0 -and $status -ne [uint32]2148204809) {
        throw ('Assinatura invalida: {0} (WinVerifyTrust 0x{1:X8})' -f $Path, $status)
    }
    if ($status -ne 0) { Write-Host " -> Assinatura integra; certificado local ainda nao confiavel no Windows: $Path" -ForegroundColor Yellow }
}

function Get-XennexReleaseVersion {
    param([string]$ProjectPath, [string]$RequestedVersion)
    [xml]$project = Get-Content -LiteralPath $ProjectPath -Raw
    $version = [string]$project.Project.PropertyGroup.Version | Where-Object { $_ }
    if ($version -notmatch '^\d+\.\d+\.\d+$') {
        throw 'Xennex.csproj deve definir uma versao Major.Minor.Patch.'
    }
    if ($RequestedVersion -and $RequestedVersion -ne $version) {
        throw "A versao solicitada ($RequestedVersion) difere do Xennex.csproj ($version). Atualize o projeto primeiro."
    }
    return $version
}

function Assert-XennexFrontend {
    param([string]$Directory)
    if (Test-Path -LiteralPath (Join-Path $Directory 'wwwroot')) {
        throw 'Aninhamento wwwroot/wwwroot detectado.'
    }
    $html = Get-Content -LiteralPath (Join-Path $Directory 'index.html') -Raw -ErrorAction Stop
    foreach ($reference in [regex]::Matches($html, '(?:src|href)="/assets/([^"/\\]+)"')) {
        $referencedPath = Join-Path (Join-Path $Directory 'assets') $reference.Groups[1].Value
        if (-not (Test-Path -LiteralPath $referencedPath -PathType Leaf)) { throw "Asset referenciado ausente: $referencedPath" }
    }
    foreach ($extension in @('js', 'css')) {
        $pattern = '(?:src|href)="/assets/(index-[^"/\\]+\.' + $extension + ')"'
        if ($html -notmatch $pattern) { throw "index.html nao referencia o bundle $extension." }
        $asset = Join-Path (Join-Path $Directory 'assets') $Matches[1]
        if (-not (Test-Path -LiteralPath $asset -PathType Leaf)) { throw "Bundle ausente: $asset" }
        $size = (Get-Item -LiteralPath $asset).Length
        if ($size -eq 0 -or ($extension -eq 'js' -and $size -le 50KB)) {
            throw "Bundle invalido ou pequeno demais: $asset ($size bytes)"
        }
    }
}

function Assert-XennexPackage {
    param([string]$Directory)
    Assert-XennexFrontend (Join-Path $Directory 'wwwroot')
    foreach ($name in @('Xennex.exe', 'Xennex.CaptureWorker.exe', 'WebView2Loader.dll',
        'alexdoong.cer', 'instalar_certificado_alexdoong.cmd', 'scripts/hand_motion.py')) {
        $path = Join-Path $Directory $name
        if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or (Get-Item -LiteralPath $path).Length -eq 0) {
            throw "Arquivo obrigatorio ausente ou vazio: $name"
        }
    }
    $allowedData = @('config.txt', 'gestures.json', 'swipe_config.json', 'team_config.txt')
    $dataDir = Join-Path $Directory 'Data'
    if (-not (Test-Path -LiteralPath (Join-Path $dataDir 'config.txt') -PathType Leaf)) {
        throw 'Data/config.txt ausente.'
    }
    foreach ($file in Get-ChildItem -LiteralPath $dataDir -Force) {
        if ($file.PSIsContainer -or $file.Name -notin $allowedData) { throw "Data nao permitido: $($file.Name)" }
        if ((Get-Content -LiteralPath $file.FullName -Raw) -match '(?i)[a-z]:[\\/]|\\\\[^\\\s]+\\') {
            throw "Caminho absoluto em Data/$($file.Name)."
        }
    }
    $skins = Join-Path $Directory 'wwwroot/skins'
    if (-not (Test-Path -LiteralPath (Join-Path $skins 'default') -PathType Container)) {
        throw 'Skin default ausente.'
    }
    if (Get-ChildItem -LiteralPath $skins -Force | Where-Object { $_.Name -ne 'default' }) {
        throw 'O pacote contem skins pessoais.'
    }
    if (Get-ChildItem -LiteralPath $Directory -Recurse -File -Force |
        Where-Object { $_.Extension -in '.log', '.pdb', '.pfx', '.p12' -or $_.Name -like '*_log.txt' }) {
        throw 'O pacote contem logs, arquivos de debug ou chaves privadas.'
    }
}

function Remove-XennexBuildDirectory {
    param([string]$Path, [string]$AllowedRoot)
    $fullPath = [IO.Path]::GetFullPath($Path).TrimEnd('\', '/')
    $root = [IO.Path]::GetFullPath($AllowedRoot).TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
    if (-not $fullPath.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Limpeza fora do diretorio autorizado: $fullPath"
    }
    if (Test-Path -LiteralPath $fullPath) {
        if ((Get-Item -LiteralPath $fullPath -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw "Limpeza recusada para link de diretorio: $fullPath"
        }
        Remove-Item -LiteralPath $fullPath -Recurse -Force
    }
}
