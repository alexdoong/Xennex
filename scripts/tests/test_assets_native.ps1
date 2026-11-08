# Isolated WebView2/COM smoke. Never copies or changes personal Data/.
$ErrorActionPreference = 'Stop'
$root = (Get-Item $PSScriptRoot).Parent.Parent.FullName
$destination = Join-Path $root ('bin/AssetNativeSmoke-' + [Guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($destination) | Out-Null
& dotnet publish (Join-Path $root 'Xennex.csproj') -c Release -r win-x64 --self-contained false -o $destination
if ($LASTEXITCODE -ne 0) { throw 'Asset native publish failed.' }
if (Test-Path -LiteralPath (Join-Path $destination 'Data')) { throw 'Publish unexpectedly included Data/. Fixture setup aborted.' }
$web = Join-Path $destination 'wwwroot'
[IO.Directory]::CreateDirectory($web) | Out-Null
Copy-Item -Path (Join-Path $root 'wwwroot/*') -Destination $web -Recurse -Force
Push-Location $root
try {
    & dotnet run --project scripts/tests/AssetLibraryTests/AssetLibraryTests.csproj -c Release -- --prepare-native $destination
    if ($LASTEXITCODE -ne 0) { throw 'Asset fixture setup failed.' }
}
finally { Pop-Location }
$oldArguments = $env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS
$env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = '--remote-debugging-port=9232'
try {
    foreach ($phase in @('write', 'read')) {
        $process = Start-Process -FilePath (Join-Path $destination 'Xennex.exe') -WorkingDirectory $destination -WindowStyle Hidden -PassThru
        try {
            & node (Join-Path $root 'frontend/tests/assets-native.test.cjs') $phase
            if ($LASTEXITCODE -ne 0) { throw "Asset native test failed: $phase" }
            if (-not $process.WaitForExit(10000)) { throw 'Asset native instance did not exit.' }
        }
        finally { if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force } }
    }
}
finally { $env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = $oldArguments }
Write-Host "Asset native smoke: $destination"
