param(
    [string]$Model = 'gemma3:4b',
    [string]$Checkpoint = 'bin/AliceMemory/stream-pilot-seed17/weights.pt',
    [string]$Audio = 'bin/AliceMemory/stream-pilot-seed17/examples/meal.wav',
    [ValidateSet('rls', 'episodic', 'grounded', 'grounded-loop', 'expectation', 'expectation-loop')][string]$Source = 'rls',
    [string]$Image,
    [string]$Questions,
    [ValidateLength(1, 4000)][string]$Question,
    [Nullable[double]]$WindowStart,
    [Nullable[double]]$WindowEnd,
    [string]$TaskModel,
    [ValidateSet('cpu', 'gpu')][string]$Device = 'cpu',
    [ValidateRange(10, 120)][int]$LoopSeconds = 30
)

$ErrorActionPreference = 'Stop'
if ($Source -eq 'expectation' -and (-not $Question -or -not (Test-Path -LiteralPath $Checkpoint -PathType Leaf))) {
    throw 'Expectation inference requires an existing grounded checkpoint and one question.'
}
if ($Question -and $Source -ne 'expectation') {
    throw 'Question requires the expectation source.'
}
if ($Source -eq 'expectation-loop' -and (-not $TaskModel -or -not (Test-Path -LiteralPath $TaskModel -PathType Leaf) -or
    -not (Test-Path -LiteralPath $Checkpoint -PathType Leaf))) {
    throw 'Expectation loop requires an existing grounded checkpoint and validated task model.'
}
$aliceRepo = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$aliceModels = Join-Path $aliceRepo 'Data/ai/models'
$aliceProbe = Join-Path $aliceRepo ('bin/AliceMemory/language-probe-' + [Guid]::NewGuid().ToString('N'))
$aliceServerFolder = Join-Path $aliceRepo ('bin/AliceMemory/language-host-' + [Guid]::NewGuid().ToString('N'))
$alicePort = 11438
$aliceOwnedHost = $null
$alicePreviousEnvironment = @{}
foreach ($aliceEnvironmentName in @('OLLAMA_HOST', 'OLLAMA_MODELS', 'OLLAMA_NO_CLOUD', 'OLLAMA_NUM_PARALLEL',
    'OLLAMA_MAX_LOADED_MODELS', 'OLLAMA_KEEP_ALIVE', 'PYTHONIOENCODING')) {
    $alicePreviousEnvironment[$aliceEnvironmentName] = [Environment]::GetEnvironmentVariable($aliceEnvironmentName, 'Process')
}

if (Get-NetTCPConnection -LocalPort $alicePort -State Listen -ErrorAction SilentlyContinue) {
    throw 'The dedicated Alice test port is already in use; no external server will be adopted.'
}
if (-not (Test-Path -LiteralPath (Join-Path $aliceModels 'manifests'))) {
    throw 'The local model catalog is unavailable. This probe never downloads weights.'
}
New-Item -ItemType Directory -Path $aliceServerFolder | Out-Null
$aliceEvidence = Join-Path $aliceServerFolder 'evidence.json'
$aliceModule = 'scripts.alice_memory.language_probe'
Push-Location $aliceRepo
try {
    if ($Source -eq 'expectation-loop') {
        $aliceModule = 'scripts.alice_memory.expectation_loop_experiment'
    } elseif ($Source -eq 'expectation') {
        $aliceModule = 'scripts.alice_memory.expectation_language'
    } elseif ($Source -in @('grounded', 'grounded-loop')) {
        if (-not $Questions -or -not (Test-Path -LiteralPath $Questions -PathType Leaf) -or
            -not (Test-Path -LiteralPath $Checkpoint -PathType Leaf)) {
            throw 'Grounded inference requires an existing checkpoint and controlled question bundle.'
        }
        $aliceModule = 'scripts.alice_memory.grounded_language'
        if ($Source -eq 'grounded-loop') { $aliceModule = 'scripts.alice_memory.language_loop_experiment' }
    } elseif ($Source -eq 'episodic') {
        if (-not $Image -or (($null -eq $WindowStart) -ne ($null -eq $WindowEnd))) {
            throw 'Episodic extraction requires an image and both or neither time bounds.'
        }
        $aliceModule = 'scripts.alice_memory.episodic_language'
        $aliceExtractArguments = @('-m', $aliceModule, '--extract-only', '--checkpoint', $Checkpoint,
            '--image', $Image, '--output', $aliceEvidence)
        if ($null -ne $WindowStart) {
            $aliceExtractArguments += @('--window-start', $WindowStart.ToString([Globalization.CultureInfo]::InvariantCulture),
                '--window-end', $WindowEnd.ToString([Globalization.CultureInfo]::InvariantCulture))
        }
        python @aliceExtractArguments
    } else {
        python -m $aliceModule --extract-only --checkpoint $Checkpoint --audio $Audio --output $aliceEvidence
    }
    if ($TaskModel -and ($Source -notin @('grounded-loop', 'expectation-loop') -or -not (Test-Path -LiteralPath $TaskModel -PathType Leaf))) {
        throw 'A neural task model requires grounded-loop and an existing gated task model file.'
    }
    if ($LoopSeconds -ne 30 -and $Source -notin @('grounded-loop', 'expectation-loop')) {
        throw 'LoopSeconds requires the grounded-loop source.'
    }
    if ($Device -ne 'cpu' -and $Source -notin @('grounded-loop', 'expectation-loop')) {
        throw 'GPU mode currently requires the finite grounded-loop source.'
    }
    if ($Source -notin @('grounded', 'grounded-loop', 'expectation', 'expectation-loop') -and $LASTEXITCODE -ne 0) { throw 'Synthetic memory evidence extraction failed.' }
} finally { Pop-Location }

try {
    $env:OLLAMA_HOST = '127.0.0.1:' + $alicePort
    $env:OLLAMA_MODELS = $aliceModels
    $env:OLLAMA_NO_CLOUD = '1'
    $env:OLLAMA_NUM_PARALLEL = '1'
    $env:OLLAMA_MAX_LOADED_MODELS = '1'
    $env:OLLAMA_KEEP_ALIVE = '0'
    $env:PYTHONIOENCODING = 'utf-8'
    $aliceExecutable = (Get-Command ollama -ErrorAction Stop).Source
    $aliceOwnedHost = Start-Process -FilePath $aliceExecutable -ArgumentList 'serve' -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $aliceServerFolder 'stdout.log') `
        -RedirectStandardError (Join-Path $aliceServerFolder 'stderr.log')
    @{ pid = $aliceOwnedHost.Id; started = $aliceOwnedHost.StartTime.ToUniversalTime().ToString('o');
        port = $alicePort; model = $Model; source = $Source; loopSeconds = $LoopSeconds; device = $Device } |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $aliceServerFolder 'owned-host.json') -Encoding UTF8
    $aliceReady = $false
    for ($aliceAttempt = 0; $aliceAttempt -lt 50; $aliceAttempt++) {
        if ($aliceOwnedHost.HasExited) { throw 'Owned Ollama test process exited during startup.' }
        try {
            Invoke-RestMethod -Uri ('http://127.0.0.1:' + $alicePort + '/api/tags') -TimeoutSec 1 | Out-Null
            $aliceReady = $true
            break
        } catch { Start-Sleep -Milliseconds 100 }
    }
    if (-not $aliceReady) { throw 'Owned Ollama test server did not become ready.' }
    $aliceListener = Get-NetTCPConnection -LocalPort $alicePort -State Listen -ErrorAction Stop
    if ($aliceListener.OwningProcess -ne $aliceOwnedHost.Id) { throw 'Test port is not owned by the process launched here.' }
    Push-Location $aliceRepo
    try {
        $aliceInferenceArguments = @('-m', $aliceModule, '--endpoint', ('http://127.0.0.1:' + $alicePort),
            '--model', $Model, '--output', $aliceProbe)
        if ($Source -eq 'expectation-loop') {
            $aliceInferenceArguments += @('--checkpoint', $Checkpoint, '--task-model', $TaskModel,
                '--seconds', $LoopSeconds.ToString([Globalization.CultureInfo]::InvariantCulture),
                '--backend', 'installed', '--device', $Device)
        } elseif ($Source -eq 'expectation') {
            New-Item -ItemType Directory -Path $aliceProbe | Out-Null
            $aliceQuestionFile = Join-Path $aliceProbe 'question.txt'
            [IO.File]::WriteAllText($aliceQuestionFile, $Question, [Text.UTF8Encoding]::new($false))
            $aliceInferenceArguments = @('-m', $aliceModule, '--endpoint', ('http://127.0.0.1:' + $alicePort),
                '--model', $Model, '--checkpoint', $Checkpoint, '--question-file', $aliceQuestionFile,
                '--output', (Join-Path $aliceProbe 'report.json'))
        } elseif ($Source -in @('grounded', 'grounded-loop')) {
            $aliceInferenceArguments += @('--checkpoint', $Checkpoint, '--questions', $Questions)
            if ($TaskModel) { $aliceInferenceArguments += @('--task-model', $TaskModel) }
            if ($Source -eq 'grounded-loop') { $aliceInferenceArguments += @('--seconds', $LoopSeconds.ToString([Globalization.CultureInfo]::InvariantCulture), '--device', $Device) }
        } else {
            $aliceInferenceArguments += @('--evidence', $aliceEvidence)
        }
        python @aliceInferenceArguments
        $aliceExitCode = $LASTEXITCODE
    } finally { Pop-Location }
    if ($aliceExitCode -ne 0) { throw ('Language probe failed with exit code ' + $aliceExitCode) }
} finally {
    if ($null -ne $aliceOwnedHost -and -not $aliceOwnedHost.HasExited) {
        Stop-Process -Id $aliceOwnedHost.Id -ErrorAction SilentlyContinue
        $aliceOwnedHost.WaitForExit(5000) | Out-Null
    }
    foreach ($aliceEnvironmentName in $alicePreviousEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($aliceEnvironmentName, $alicePreviousEnvironment[$aliceEnvironmentName], 'Process')
    }
}
