# Build frontend and bin/LocalAiDev before running. Never changes personal skins or Data.
param([string]$BuildDirectory = 'bin/LocalAiDev')
$ErrorActionPreference = 'Stop'
$root = (Get-Item $PSScriptRoot).Parent.Parent.FullName
$source = Join-Path $root $BuildDirectory
$destination = Join-Path $root ('bin/SkinsNative-' + [Guid]::NewGuid().ToString('N'))
if (Get-Process Xennex -ErrorAction SilentlyContinue) { throw 'Feche o Xennex antes do teste nativo.' }
[IO.Directory]::CreateDirectory($destination) | Out-Null
Get-ChildItem -LiteralPath $source | Where-Object { $_.Name -notin @('Data', 'wwwroot', 'Xennex.exe.WebView2') } | Copy-Item -Destination $destination -Recurse
$web = Join-Path $destination 'wwwroot'
[IO.Directory]::CreateDirectory($web) | Out-Null
Get-ChildItem -LiteralPath (Join-Path $root 'wwwroot') | Where-Object { $_.Name -ne 'skins' } | Copy-Item -Destination $web -Recurse
[IO.Directory]::CreateDirectory((Join-Path $web 'skins')) | Out-Null
Copy-Item -LiteralPath (Join-Path $root 'wwwroot/skins/default') -Destination (Join-Path $web 'skins/default') -Recurse
$oldArguments = $env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS
$env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = '--remote-debugging-port=9233'
try {
    foreach ($phase in @('write', 'read')) {
        $process = Start-Process -FilePath (Join-Path $destination 'Xennex.exe') -WorkingDirectory $destination -WindowStyle Hidden -PassThru
        try {
            & node (Join-Path $root 'frontend/tests/skins-native.test.cjs') $phase 9233
            if ($LASTEXITCODE -ne 0) { throw "Native skin test failed: $phase" }
            if (-not $process.WaitForExit(10000)) { throw 'Test instance did not exit.' }
        }
        finally { if (-not $process.HasExited) { Stop-Process -Id $process.Id -Force } }
    }
}
finally { $env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = $oldArguments }
Write-Host "Native skins test directory: $destination"
