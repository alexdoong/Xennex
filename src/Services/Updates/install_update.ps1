param(
    [int]$TargetPid,
    [string]$UpdateFile,
    [string]$AppDir,
    [string]$ExePath,
    [string]$ExpectedSha256,
    [string]$ExpectedRoot,
    [string]$ExpectedPublisher,
    [string]$ReadyFile
)

$ErrorActionPreference = 'Stop'


# Existing user data is immutable during an update; only the default skin is managed.
function Copy-XennexUpdate {
    param([string]$SourceDir, [string]$AppDir)
    foreach ($item in Get-ChildItem -LiteralPath $SourceDir) {
        $dest = Join-Path $AppDir $item.Name
        if ($item.PSIsContainer -and $item.Name -eq 'Data') {
            New-Item -ItemType Directory -Path $dest -Force | Out-Null
            foreach ($file in Get-ChildItem -LiteralPath $item.FullName -File) {
                $fileDest = Join-Path $dest $file.Name
                if (-not (Test-Path -LiteralPath $fileDest)) {
                    Copy-Item -LiteralPath $file.FullName -Destination $fileDest
                }
            }
            continue
        }
        if ($item.PSIsContainer -and $item.Name -eq 'wwwroot') {
            New-Item -ItemType Directory -Path $dest -Force | Out-Null
            foreach ($child in Get-ChildItem -LiteralPath $item.FullName) {
                if ($child.PSIsContainer -and $child.Name -eq 'skins') {
                    $defaultSkin = Join-Path $child.FullName 'default'
                    if (Test-Path -LiteralPath $defaultSkin -PathType Container) {
                        $skinDest = Join-Path $dest 'skins/default'
                        New-Item -ItemType Directory -Path $skinDest -Force | Out-Null
                        Get-ChildItem -LiteralPath $defaultSkin | ForEach-Object {
                            Copy-Item -LiteralPath $_.FullName -Destination $skinDest -Recurse -Force
                        }
                    }
                    continue
                }
                Copy-Item -LiteralPath $child.FullName -Destination $dest -Recurse -Force
            }
            continue
        }
        Copy-Item -LiteralPath $item.FullName -Destination $AppDir -Recurse -Force
    }
}

function Assert-XennexUpdateHash {
    param([string]$Path, [string]$Hash)
    if ($Hash -notmatch '^[A-Fa-f0-9]{64}$' -or [IO.Path]::GetExtension($Path) -ne '.zip') { throw 'Pacote ou SHA-256 invalido.' }
    if ((Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash -ne $Hash) { throw 'SHA-256 da atualizacao diverge da release.' }
}

function Expand-XennexVerifiedArchive {
    param([string]$Path, [string]$Destination, [string]$RootName)
    if ($RootName -notmatch '^Xennex-v\d+\.\d+\.\d+-win64$') { throw 'Raiz de pacote invalida.' }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::OpenRead($Path)
    try {
        $seen = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
        $total = 0L
        if ($archive.Entries.Count -gt 10000) { throw 'Pacote tem arquivos demais.' }
        foreach ($entry in $archive.Entries) {
            $name = $entry.FullName.Replace('\', '/')
            if (-not $name.StartsWith($RootName + '/', [StringComparison]::Ordinal) -or
                $name.Contains(':') -or $name.Contains([char]0) -or
                ($name.Split('/') | Where-Object { $_ -eq '..' -or $_ -eq '.' -or $_.EndsWith(' ') -or $_.EndsWith('.') }) -or
                (($entry.ExternalAttributes -shr 16) -band 0xF000) -eq 0xA000 -or
                -not $seen.Add($name.TrimEnd('/'))) { throw 'Entrada de ZIP nao permitida.' }
            $total += $entry.Length
            if ($total -gt 2GB) { throw 'Pacote expandido excede limite.' }
        }
        # The destination is newly created for this invocation; validated entries stay below it.
        [IO.Compression.ZipFile]::ExtractToDirectory($Path, $Destination)
    }
    finally { $archive.Dispose() }
    $source = Join-Path $Destination $RootName
    if (-not (Test-Path -LiteralPath (Join-Path $source 'Xennex.exe') -PathType Leaf)) { throw 'Executavel ausente.' }
    return $source
}

function Assert-XennexUpdatePublisher {
    param([string]$Source, [string]$Publisher)
    if ($Publisher -notmatch '^[A-Fa-f0-9]{40}$') { throw 'Identidade do publicador ausente.' }
    $binaries = @('Xennex.exe', 'Xennex.CaptureWorker.exe', 'scripts/Xennex.GesturesWorker.exe')
    if (Test-Path -LiteralPath (Join-Path $Source 'GameCapture')) {
        $binaries += @('GameCapture/Xennex.GameHook32.dll', 'GameCapture/Xennex.GameHook64.dll', 'GameCapture/Xennex.GameInjector32.exe', 'GameCapture/Xennex.GameInjector64.exe')
    }
    foreach ($name in $binaries) {
        $path = Join-Path $Source $name
        $signature = Get-AuthenticodeSignature -LiteralPath $path
        if (-not $signature.SignerCertificate -or $signature.SignerCertificate.Thumbprint -ne $Publisher) { throw 'Assinante incorreto na atualizacao.' }
        $status = [Xennex.Build.AuthenticodeVerification]::Check($path)
        # Pinned self-signed key is accepted without importing it into the user's Root store.
        if ($status -ne 0 -and $status -ne [uint32]2148204809) { throw 'Assinatura alterada ou invalida.' }
    }
}

# Replaced with the embedded verifier by UpdateService, never downloaded from the frontend.
# XENNEX_AUTHENTICODE_TYPE
$extractDir = Join-Path $env:TEMP ('Xennex_Extract_' + [Guid]::NewGuid().ToString('N'))
try {
    Assert-XennexUpdateHash -Path $UpdateFile -Hash $ExpectedSha256
    $sourceDir = Expand-XennexVerifiedArchive -Path $UpdateFile -Destination $extractDir -RootName $ExpectedRoot
    Assert-XennexUpdatePublisher -Source $sourceDir -Publisher $ExpectedPublisher
    if ([string]::IsNullOrWhiteSpace($ReadyFile)) { throw 'Canal de confirmacao ausente.' }
    [IO.File]::WriteAllText(($ReadyFile + '.pending'), 'verified')
    [IO.File]::Move(($ReadyFile + '.pending'), $ReadyFile)
    if ($TargetPid -gt 0 -and (Get-Process -Id $TargetPid -ErrorAction SilentlyContinue)) {
        Wait-Process -Id $TargetPid -Timeout 30 -ErrorAction Stop
    }
    Copy-XennexUpdate -SourceDir $sourceDir -AppDir $AppDir
    Start-Process -FilePath $ExePath -WindowStyle Hidden
}
catch {
    Set-Content -LiteralPath (Join-Path $env:TEMP 'xennex_update_error.log') -Value $_.Exception.ToString()
    exit 1
}
finally {
    $tempRoot = [IO.Path]::GetFullPath($env:TEMP).TrimEnd('\') + '\'
    $resolvedExtract = [IO.Path]::GetFullPath($extractDir)
    if ($resolvedExtract.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase) -and (Test-Path -LiteralPath $resolvedExtract)) {
        Remove-Item -LiteralPath $resolvedExtract -Recurse -Force
    }
    # Delete only the random package created by UpdateService, never an arbitrary caller path.
    $resolvedPackage = [IO.Path]::GetFullPath($UpdateFile)
    if ($resolvedPackage.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase) -and
        [IO.Path]::GetFileName($resolvedPackage) -match '^Xennex_Update_[a-f0-9]{32}\.zip$') {
        Remove-Item -LiteralPath $resolvedPackage -Force -ErrorAction SilentlyContinue
    }
}
