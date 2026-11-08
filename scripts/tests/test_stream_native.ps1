param([string]$BuildDirectory, [string]$WorkerDirectory, [switch]$DecoderBenchmark, [switch]$GameCapture, [switch]$Background)
$ErrorActionPreference = 'Stop'
$root = (Get-Item $PSScriptRoot).Parent.Parent.FullName
if (-not $BuildDirectory) {
    [xml]$project = Get-Content -LiteralPath (Join-Path $root 'Xennex.csproj') -Raw
    $version = @($project.Project.PropertyGroup.Version | Where-Object { $_ })[0]
    if (-not $version) { throw 'Versão do projeto indisponível.' }
    $BuildDirectory = "Backup/Xennex-v$version-win64"
}
if (Get-Process Xennex -ErrorAction SilentlyContinue) { throw 'Feche o Xennex antes do teste isolado.' }
$source = Join-Path $root $BuildDirectory
$destination = Join-Path $root ('bin/StreamNative-' + [Guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($destination) | Out-Null
# Copy code/frontend, never personal Data. Official packages contain only the default skin.
foreach ($name in @('Xennex.exe', 'wwwroot')) {
    Copy-Item -LiteralPath (Join-Path $source $name) -Destination $destination -Recurse
}
# Development builds also require their managed/native dependencies. Copy code only.
Get-ChildItem -LiteralPath $source -File -Filter '*.dll' | Copy-Item -Destination $destination
foreach ($name in @('Xennex.deps.json', 'Xennex.runtimeconfig.json', 'runtimes')) {
    $dependency = Join-Path $source $name
    if (Test-Path -LiteralPath $dependency) { Copy-Item -LiteralPath $dependency -Destination $destination -Recurse }
}
$workerSource = if ($WorkerDirectory) { Join-Path $root $WorkerDirectory } else { $source }
foreach ($name in @('Xennex.CaptureWorker.exe', 'Xennex.CaptureWorker.dll', 'Xennex.CaptureWorker.deps.json',
    'Xennex.CaptureWorker.runtimeconfig.json', 'WinRT.Runtime.dll', 'Microsoft.Windows.SDK.NET.dll',
    'Vortice.D3DCompiler.dll', 'Vortice.Direct3D11.dll', 'Vortice.DXGI.dll', 'Vortice.DirectX.dll', 'Vortice.Mathematics.dll',
    'SharpGen.Runtime.dll', 'SharpGen.Runtime.COM.dll', 'System.Text.Json.dll', 'System.Text.Encodings.Web.dll', 'System.IO.Pipelines.dll')) {
    $dependency = Join-Path $workerSource $name
    if (Test-Path -LiteralPath $dependency) { Copy-Item -LiteralPath $dependency -Destination $destination }
}
$gameRuntime = Join-Path $workerSource 'GameCapture'
if (Test-Path -LiteralPath $gameRuntime) {
    $testGameRuntime = Join-Path $destination 'GameCapture'
    New-Item -ItemType Directory -Force -Path $testGameRuntime | Out-Null
    foreach ($name in @('Xennex.GameHook32.dll','Xennex.GameHook64.dll','Xennex.GameInjector32.exe','Xennex.GameInjector64.exe')) {
        Copy-Item -LiteralPath (Join-Path $gameRuntime $name) -Destination (Join-Path $testGameRuntime $name)
    }
}
if (-not (Test-Path -LiteralPath (Join-Path $destination 'Xennex.CaptureWorker.exe'))) { throw 'CaptureWorker ausente no build de teste.' }
$oldArguments = $env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS
$oldHandle = $env:XENNEX_TEST_HWND
$oldPid = $env:XENNEX_TEST_PID
$oldDirectory = $env:XENNEX_TEST_DIRECTORY
$oldGameFixture = $env:XENNEX_GAME_FIXTURE
$env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = '--remote-debugging-port=9236'
$process = $null
try {
    $process = Start-Process -FilePath (Join-Path $destination 'Xennex.exe') -WorkingDirectory $destination -WindowStyle Hidden -PassThru
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        $process.Refresh()
        if ($process.HasExited) { throw 'Instância de teste encerrou antes de inicializar.' }
        if ($process.MainWindowHandle -ne [IntPtr]::Zero) { break }
        Start-Sleep -Milliseconds 500
    }
    $env:XENNEX_TEST_HWND = $process.MainWindowHandle.ToInt64().ToString()
    $env:XENNEX_TEST_PID = $process.Id.ToString()
    $env:XENNEX_TEST_DIRECTORY = $destination
    $env:XENNEX_GAME_FIXTURE = Join-Path $root 'bin/GameCaptureIntegrated/Xennex.OpenGlFixture64.exe'
    $testFile = if ($Background) { 'frontend/tests/capture-background-native.mjs' } elseif ($GameCapture) { 'frontend/tests/game-capture-native.mjs' } elseif ($DecoderBenchmark) { 'frontend/tests/capture-decoder-benchmark.mjs' } else { 'frontend/tests/stream-capture-native.mjs' }
    & node (Join-Path $root $testFile)
    if ($LASTEXITCODE -ne 0) { throw 'Falha no teste de captura nativa.' }
}
finally {
    $env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = $oldArguments
    $env:XENNEX_TEST_HWND = $oldHandle
    $env:XENNEX_TEST_PID = $oldPid
    $env:XENNEX_TEST_DIRECTORY = $oldDirectory
    $env:XENNEX_GAME_FIXTURE = $oldGameFixture
    if ($process -and -not $process.HasExited) {
        if (-not $process.WaitForExit(5000)) { Stop-Process -Id $process.Id -Force }
    }
}
Write-Host "Native capture test directory: $destination"
