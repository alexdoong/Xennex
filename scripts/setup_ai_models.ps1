param([ValidateSet('qwen3.5:4b','qwen2.5-coder:7b','gemma3:4b')][string[]]$Models=@('qwen3.5:4b','qwen2.5-coder:7b','gemma3:4b'))
$ErrorActionPreference='Stop'
$root=(Get-Item $PSScriptRoot).Parent.FullName
$destination=Join-Path $root 'Data/ai/models'
$ollama=Join-Path $env:LOCALAPPDATA 'Programs/Ollama/ollama.exe'
if (!(Test-Path -LiteralPath $ollama)) { throw 'Instale o Ollama antes de preparar os modelos.' }
$drive=[IO.DriveInfo]::new([IO.Path]::GetPathRoot($destination))
if ($drive.AvailableFreeSpace -lt 40GB) { throw 'Reserve 40 GiB livres no disco do projeto para modelos e cópias existentes.' }
$listener=[Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback,11437)
try { $listener.Start() } finally { $listener.Stop() }
New-Item -ItemType Directory -Path $destination -Force | Out-Null
# Preserve installed models without removing or modifying the original store.
$original=Join-Path $env:USERPROFILE '.ollama/models'
if (Test-Path -LiteralPath $original) {
    foreach ($file in Get-ChildItem -LiteralPath $original -Recurse -File) {
        $relative=$file.FullName.Substring($original.Length).TrimStart('\')
        $target=Join-Path $destination $relative
        if (Test-Path -LiteralPath $target) { continue }
        [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target)) | Out-Null
        Copy-Item -LiteralPath $file.FullName -Destination $target
    }
}
$logDir=Join-Path $root 'bin/AiModelSetup'
[IO.Directory]::CreateDirectory($logDir) | Out-Null
$variables=@('OLLAMA_HOST','OLLAMA_MODELS','OLLAMA_NO_CLOUD','OLLAMA_NUM_PARALLEL','OLLAMA_MAX_LOADED_MODELS')
$previous=@{}
foreach ($name in $variables) { $previous[$name]=[Environment]::GetEnvironmentVariable($name,'Process') }
$process=$null
try {
    $env:OLLAMA_HOST='127.0.0.1:11437'
    $env:OLLAMA_MODELS=$destination
    $env:OLLAMA_NO_CLOUD='1'
    $env:OLLAMA_NUM_PARALLEL='1'
    $env:OLLAMA_MAX_LOADED_MODELS='1'
    $process=Start-Process -FilePath $ollama -ArgumentList 'serve' -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDir 'server-out.txt') -RedirectStandardError (Join-Path $logDir 'server-err.txt')
    $ready=$false
    for ($attempt=0;$attempt -lt 40;$attempt++) {
        if ($process.HasExited) { throw 'O servidor de instalação encerrou.' }
        try { $null=Invoke-RestMethod 'http://127.0.0.1:11437/api/tags' -TimeoutSec 2; $ready=$true; break } catch { Start-Sleep -Milliseconds 250 }
    }
    if (!$ready) { throw 'O servidor de instalação não respondeu.' }
    foreach ($model in $Models) {
        Write-Output "Preparando $model em $destination"
        $log=Join-Path $logDir ($model.Replace(':','-').Replace('/','-')+'.txt')
        # Ollama verifies downloaded blobs before publishing the model manifest.
        $pull=Start-Process -FilePath $ollama -ArgumentList @('pull',$model) -WindowStyle Hidden -Wait -PassThru -RedirectStandardOutput ($log+'.out') -RedirectStandardError $log
        if ($pull.ExitCode -ne 0) { throw "Falha no download de $model. Consulte $log" }
        $catalog=Invoke-RestMethod 'http://127.0.0.1:11437/api/tags'
        if (!($catalog.models | Where-Object name -EQ $model)) { throw "Modelo não apareceu no catálogo: $model" }
        Write-Output "Instalado: $model"
    }
    $catalog.models | Select-Object name,size | ConvertTo-Json
}
finally {
    if ($process -and !$process.HasExited) { Stop-Process -Id $process.Id -Force }
    foreach ($name in $variables) { [Environment]::SetEnvironmentVariable($name,$previous[$name],'Process') }
}
