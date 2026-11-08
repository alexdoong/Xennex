param(
    [string]$Checkpoint = 'bin/AliceMemory/native-impact-real-v1/portable.pt',
    [string]$Output = 'bin/AliceMemory/native-feedback-real-v1',
    [string]$Model = 'qwen3.5:0.8b-q8_0',
    [string]$Python = 'python',
    [ValidateSet('native_feedback_probe','native_name_probe','native_name_reply_probe','interaction_runtime_probe','interaction_report_probe','context_report_probe','reference_query_probe','panel_runtime_probe','feedback_channel_probe','dialogue_probe','dialogue_topic_probe','dialogue_model_probe','dialogue_selection_probe','dialogue_auto_probe','dialogue_evocation_probe','dialogue_learning_probe')][string]$Probe = 'native_feedback_probe'
)
$ErrorActionPreference = 'Stop'
$feedbackPort = 11438
$feedbackRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$feedbackHostFolder = Join-Path $feedbackRoot ('bin/AliceMemory/feedback-host-' + [Guid]::NewGuid().ToString('N'))
$feedbackOwnedHost = $null
$feedbackPrevious = @{}
$feedbackNames = @('OLLAMA_HOST','OLLAMA_MODELS','OLLAMA_NO_CLOUD','OLLAMA_NUM_PARALLEL','OLLAMA_MAX_LOADED_MODELS','OLLAMA_KEEP_ALIVE','PYTHONIOENCODING','ALICE_EXPERIMENT_RAM_FRACTION')
foreach ($feedbackName in $feedbackNames) { $feedbackPrevious[$feedbackName] = [Environment]::GetEnvironmentVariable($feedbackName, 'Process') }
if (Get-NetTCPConnection -LocalPort $feedbackPort -State Listen -ErrorAction SilentlyContinue) {
    throw 'Dedicated feedback port is occupied; no foreign host will be adopted.'
}
New-Item -ItemType Directory -Path $feedbackHostFolder | Out-Null
Push-Location $feedbackRoot
try {
    $env:OLLAMA_HOST = '127.0.0.1:' + $feedbackPort
    $env:OLLAMA_MODELS = Join-Path $feedbackRoot 'Data/ai/models'
    $env:OLLAMA_NO_CLOUD = '1'
    $env:OLLAMA_NUM_PARALLEL = '1'
    $env:OLLAMA_MAX_LOADED_MODELS = '1'
    $env:OLLAMA_KEEP_ALIVE = '0'
    $env:PYTHONIOENCODING = 'utf-8'
    $env:ALICE_EXPERIMENT_RAM_FRACTION = '.9'
    if (-not (Test-Path -LiteralPath (Join-Path $env:OLLAMA_MODELS 'manifests'))) { throw 'Installed model catalog unavailable; this test never downloads.' }
    $feedbackExecutable = (Get-Command ollama -ErrorAction Stop).Source
    $feedbackOwnedHost = Start-Process -FilePath $feedbackExecutable -ArgumentList 'serve' -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $feedbackHostFolder 'stdout.log') -RedirectStandardError (Join-Path $feedbackHostFolder 'stderr.log')
    @{ pid=$feedbackOwnedHost.Id; started=$feedbackOwnedHost.StartTime.ToUniversalTime().ToString('o'); port=$feedbackPort } |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $feedbackHostFolder 'owned-host.json') -Encoding UTF8
    $feedbackReady = $false
    for ($feedbackAttempt = 0; $feedbackAttempt -lt 50; $feedbackAttempt++) {
        if ($feedbackOwnedHost.HasExited) { throw 'Owned host exited at startup.' }
        try { Invoke-RestMethod -Uri ('http://127.0.0.1:' + $feedbackPort + '/api/tags') -TimeoutSec 1 | Out-Null; $feedbackReady = $true; break }
        catch { Start-Sleep -Milliseconds 100 }
    }
    if (-not $feedbackReady) { throw 'Owned host did not become ready.' }
    $feedbackListener = Get-NetTCPConnection -LocalPort $feedbackPort -State Listen -ErrorAction Stop
    if ($feedbackListener.OwningProcess -ne $feedbackOwnedHost.Id) { throw 'Host ownership mismatch.' }
    if ($Probe -eq 'panel_runtime_probe') {
        & dotnet run --no-build --project scripts/tests/LocalAiTests/LocalAiTests.csproj -c Release -- --alice-panel-real $Python $Checkpoint $Output ('http://127.0.0.1:' + $feedbackPort)
    } elseif ($Probe -eq 'dialogue_learning_probe') {
        & $Python -m scripts.alice_memory.dialogue_learning_probe --output $Output --endpoint ('http://127.0.0.1:' + $feedbackPort) --model $Model
    } else {
        & $Python -m ('scripts.alice_memory.' + $Probe) --checkpoint $Checkpoint --output $Output --endpoint ('http://127.0.0.1:' + $feedbackPort) --model $Model
    }
    $feedbackExit = $LASTEXITCODE
    if ($feedbackExit -ne 0) { throw ('Feedback trial failed with exit ' + $feedbackExit) }
} finally {
    if ($null -ne $feedbackOwnedHost -and -not $feedbackOwnedHost.HasExited) {
        try {
        $feedbackProcesses = @(Get-CimInstance Win32_Process -ErrorAction Stop)
        $feedbackOwnedIds = @($feedbackOwnedHost.Id)
        $feedbackChildren = @()
        do {
            $feedbackFound = @($feedbackProcesses | Where-Object { $_.ParentProcessId -in $feedbackOwnedIds -and $_.ProcessId -notin $feedbackOwnedIds -and $_.CreationDate -ge $feedbackOwnedHost.StartTime.AddSeconds(-1) })
            foreach ($feedbackChild in $feedbackFound) { $feedbackOwnedIds += $feedbackChild.ProcessId; $feedbackChildren += $feedbackChild }
        } while ($feedbackFound.Count -gt 0)
        [Array]::Reverse($feedbackChildren)
        foreach ($feedbackChild in $feedbackChildren) {
            $feedbackCurrent = Get-CimInstance Win32_Process -Filter ('ProcessId=' + $feedbackChild.ProcessId) -ErrorAction SilentlyContinue
            if ($null -ne $feedbackCurrent -and $feedbackCurrent.CreationDate -eq $feedbackChild.CreationDate) {
                Stop-Process -Id $feedbackChild.ProcessId -ErrorAction SilentlyContinue
            }
        }
        } catch { Write-Warning 'Descendant inventory unavailable; stopping the owned host handle.' }
        Stop-Process -Id $feedbackOwnedHost.Id -ErrorAction SilentlyContinue
        $feedbackOwnedHost.WaitForExit(5000) | Out-Null
    }
    foreach ($feedbackName in $feedbackPrevious.Keys) { [Environment]::SetEnvironmentVariable($feedbackName, $feedbackPrevious[$feedbackName], 'Process') }
    Pop-Location
}
