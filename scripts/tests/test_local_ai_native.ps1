# Build frontend + app into bin/LocalAiDev before running. Test data stays under bin/.
param([string]$BuildDirectory = 'bin/LocalAiDev', [string]$TestScript = 'frontend/tests/local-ai-native.test.cjs')
$ErrorActionPreference = 'Stop'
$root = (Get-Item $PSScriptRoot).Parent.Parent.FullName
$source = Join-Path $root $BuildDirectory
$destination = Join-Path $root ('bin/LocalAiNative-' + [Guid]::NewGuid().ToString('N'))
if (Get-Process Xennex -ErrorAction SilentlyContinue) { throw 'Feche o Xennex antes do teste nativo para respeitar a instância única.' }
[IO.Directory]::CreateDirectory($destination) | Out-Null
Get-ChildItem -LiteralPath $source | Where-Object { $_.Name -notin @('Data', 'wwwroot', 'Xennex.exe.WebView2') } | Copy-Item -Destination $destination -Recurse
$web = Join-Path $destination 'wwwroot'
[IO.Directory]::CreateDirectory($web) | Out-Null
Copy-Item -Path (Join-Path $root 'wwwroot/*') -Destination $web -Recurse
$oldArguments = $env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS
$env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = '--remote-debugging-port=9232'
try {
    foreach ($phase in @('write', 'read')) {
        $process = Start-Process -FilePath (Join-Path $destination 'Xennex.exe') -WorkingDirectory $destination -WindowStyle Hidden -PassThru
        try {
            & node (Join-Path $root $TestScript) $phase 9232
            if ($LASTEXITCODE -ne 0) { throw "Native AI test failed: $phase" }
            if (-not $process.WaitForExit(10000)) { throw 'Test instance did not exit.' }
        }
        finally { if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force } }
    }
}
finally { $env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = $oldArguments }
Write-Host "Native AI test directory: $destination"
