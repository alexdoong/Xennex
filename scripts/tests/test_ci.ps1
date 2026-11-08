# Deterministic checks only: no camera, personal Data, model downloads, app instance or signing key.
$ErrorActionPreference = 'Stop'
$root = (Get-Item $PSScriptRoot).Parent.Parent.FullName
Push-Location $root
try {
    foreach ($project in @('SecurityTests', 'StreamingTests', 'CaptureWorkerTests', 'SkinTests', 'GameAnalyticsTests', 'AssetLibraryTests', 'VrTests', 'LocalAiTests')) {
        & dotnet run --project "scripts/tests/$project/$project.csproj" -c Release
        if ($LASTEXITCODE -ne 0) { throw "$project failed." }
    }
    & dotnet run --project scripts/tests/NativeEncoderTests/NativeEncoderTests.csproj -c Release -- --contract-tests
    if ($LASTEXITCODE -ne 0) { throw 'Native encoder contract tests failed.' }
    & dotnet run --project scripts/tests/CompactTests/CompactTests.csproj -c Release -- --geometry-only
    if ($LASTEXITCODE -ne 0) { throw 'Compact geometry tests failed.' }
    $testPython = (& python -c "import sys; print(sys.executable)").Trim()
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $testPython)) { throw 'Python executable unavailable.' }
    & dotnet run --project scripts/tests/GestureTests/GestureTests.csproj -c Release -- $testPython
    if ($LASTEXITCODE -ne 0) { throw 'Gesture supervisor tests failed.' }
    & python scripts/tests/test_gestures.py
    if ($LASTEXITCODE -ne 0) { throw 'Gesture landmark tests failed.' }
    & powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/test_release.ps1
    if ($LASTEXITCODE -ne 0) { throw 'Release tests failed.' }
    & powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/test_update_security.ps1
    if ($LASTEXITCODE -ne 0) { throw 'Updater security tests failed.' }
}
finally { Pop-Location }
