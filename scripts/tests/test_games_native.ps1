# Run after packaging. Uses only a new isolated copy under bin/; never user Data/.
$ErrorActionPreference = 'Stop'
$root = (Get-Item $PSScriptRoot).Parent.Parent.FullName
$destination = Join-Path $root ('bin/GameNativeSmoke-' + [Guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($destination) | Out-Null
foreach ($name in @('Xennex.exe', 'WebView2Loader.dll')) {
    Copy-Item -LiteralPath (Join-Path $root $name) -Destination (Join-Path $destination $name)
}
$web = Join-Path $destination 'wwwroot'
[IO.Directory]::CreateDirectory($web) | Out-Null
Copy-Item -Path (Join-Path $root 'wwwroot/*') -Destination $web -Recurse
$oldArguments = $env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS
$env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = '--remote-debugging-port=9231'
try {
    foreach ($phase in @('write', 'read')) {
        $process = Start-Process -FilePath (Join-Path $destination 'Xennex.exe') -WorkingDirectory $destination -WindowStyle Hidden -PassThru
        try {
            & node (Join-Path $root 'frontend/tests/games-native.test.cjs') $phase
            if ($LASTEXITCODE -ne 0) { throw "Native Games test failed: $phase" }
            if (-not $process.WaitForExit(10000)) { throw 'Test instance did not exit.' }
        }
        finally {
            if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force }
        }
    }
}
finally { $env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = $oldArguments }
Write-Host "Native Games test directory: $destination"
