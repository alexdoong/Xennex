# Optional real-model smoke test. Uses existing Ollama models only; no downloads.
param([string]$Model = 'llama3:latest')
$ErrorActionPreference = 'Stop'
$root = (Get-Item $PSScriptRoot).Parent.Parent.FullName
$ollamaExe = Join-Path $env:LOCALAPPDATA 'Programs/Ollama/ollama.exe'
if (-not (Test-Path -LiteralPath $ollamaExe)) { throw 'Ollama não encontrado no caminho padrão.' }
$previous = @{}
foreach ($name in @('OLLAMA_HOST', 'OLLAMA_CONTEXT_LENGTH', 'OLLAMA_KEEP_ALIVE', 'OLLAMA_NUM_PARALLEL')) {
    $previous[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}
$env:OLLAMA_HOST = '127.0.0.1:11435'
$env:OLLAMA_CONTEXT_LENGTH = '2048'
$env:OLLAMA_KEEP_ALIVE = '0'
$env:OLLAMA_NUM_PARALLEL = '1'
$modelProcess = $null
try {
    $listener = Get-NetTCPConnection -LocalPort 11435 -State Listen -ErrorAction SilentlyContinue
    if ($listener) { throw 'A porta 11435 já está ocupada; não reutilize um serviço desconhecido.' }
    $modelProcess = Start-Process -FilePath $ollamaExe -ArgumentList 'serve' -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $root 'bin/ollama-ai-test.stdout.log') -RedirectStandardError (Join-Path $root 'bin/ollama-ai-test.stderr.log')
    $ready = $false
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        try {
            $catalog = Invoke-RestMethod -Uri 'http://127.0.0.1:11435/api/tags' -TimeoutSec 2
            if ($Model -notin $catalog.models.name) { throw "O modelo $Model não está baixado." }
            $ready = $true; break
        } catch { Start-Sleep -Milliseconds 300 }
    }
    if (-not $ready) { throw 'Servidor temporário ou modelo local indisponível.' }
    dotnet run --project (Join-Path $root 'scripts/tests/LocalAiTests/LocalAiTests.csproj') -- --real 'http://127.0.0.1:11435/v1' $Model
    if ($LASTEXITCODE -ne 0) { throw 'Falha no teste de modelo real.' }
} finally {
    # Request unload from our test server before ending only the process we started.
    if ($modelProcess -and -not $modelProcess.HasExited) {
        try {
            $body = @{ model = $Model; keep_alive = 0 } | ConvertTo-Json -Compress
            $null = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:11435/api/generate' -ContentType 'application/json' -Body $body -TimeoutSec 10
        } catch { Write-Warning ('Não foi possível confirmar descarregamento: ' + $_.Exception.Message) }
        Stop-Process -Id $modelProcess.Id -Force
    }
    foreach ($name in $previous.Keys) { [Environment]::SetEnvironmentVariable($name, $previous[$name], 'Process') }
}
