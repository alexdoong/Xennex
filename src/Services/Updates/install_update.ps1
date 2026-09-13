param(
    [int]$TargetPid,
    [string]$UpdateFile,
    [string]$AppDir,
    [string]$ExePath
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

# 1. Aguardar o encerramento suave do Xennex
if ($TargetPid -gt 0) {
    try {
        Wait-Process -Id $TargetPid -Timeout 15 -ErrorAction SilentlyContinue
    } catch {}
}
Start-Sleep -Seconds 1

# 2. Garantir que nao haja processos filhos residuais bloqueando os arquivos
$attempts = 0
while ((Get-Process Xennex -ErrorAction SilentlyContinue) -and $attempts -lt 10) {
    Start-Sleep -Milliseconds 500
    $attempts++
}

if ($UpdateFile.EndsWith('.zip', [System.StringComparison]::OrdinalIgnoreCase)) {
    $extractDir = Join-Path $env:TEMP ('Xennex_Extract_' + [System.Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $extractDir -Force | Out-Null

    try {
        Expand-Archive -Path $UpdateFile -DestinationPath $extractDir -Force

        # Se o zip tiver uma subpasta unica (ex: Xennex-v0.2.2-win64), detectar
        $items = Get-ChildItem -Path $extractDir
        $sourceDir = $extractDir
        if ($items.Count -eq 1 -and $items[0].PSIsContainer -and (Test-Path (Join-Path $items[0].FullName 'Xennex.exe'))) {
            $sourceDir = $items[0].FullName
        }

        Copy-XennexUpdate -SourceDir $sourceDir -AppDir $AppDir
        Start-Process -FilePath $ExePath

    }
    catch {
        Set-Content -Path (Join-Path $env:TEMP 'xennex_update_error.log') -Value $_.Exception.ToString()
    }
    finally {
        Remove-Item -Recurse -Force $extractDir -ErrorAction SilentlyContinue
        Remove-Item -Force $UpdateFile -ErrorAction SilentlyContinue
    }

} elseif ($UpdateFile.EndsWith('.exe', [System.StringComparison]::OrdinalIgnoreCase)) {
    Start-Process -FilePath $UpdateFile
}
