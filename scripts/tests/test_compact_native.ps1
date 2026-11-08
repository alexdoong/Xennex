# Run after npm run build and dotnet build -c Release -o bin/CompactDev.
param([string]$BuildDirectory = 'bin/CompactDev')
$ErrorActionPreference = 'Stop'
$root = (Get-Item $PSScriptRoot).Parent.Parent.FullName
$source = Join-Path $root $BuildDirectory
$destination = Join-Path $root ('bin/CompactNative-' + [Guid]::NewGuid().ToString('N'))
if (Get-Process Xennex -ErrorAction SilentlyContinue) { throw 'Feche o Xennex antes do teste nativo.' }
[IO.Directory]::CreateDirectory($destination) | Out-Null
Get-ChildItem -LiteralPath $source | Where-Object { $_.Name -notin @('Data', 'wwwroot', 'Xennex.exe.WebView2') } | Copy-Item -Destination $destination -Recurse
$web = Join-Path $destination 'wwwroot'
[IO.Directory]::CreateDirectory($web) | Out-Null
Get-ChildItem -LiteralPath (Join-Path $root 'wwwroot') | Where-Object { $_.Name -ne 'skins' } | Copy-Item -Destination $web -Recurse
[IO.Directory]::CreateDirectory((Join-Path $web 'skins')) | Out-Null
Copy-Item -LiteralPath (Join-Path $root 'wwwroot/skins/default') -Destination (Join-Path $web 'skins/default') -Recurse
Add-Type -AssemblyName System.Windows.Forms
$cursorBefore = [Windows.Forms.Cursor]::Position
$area = [Windows.Forms.Screen]::PrimaryScreen.WorkingArea
[Windows.Forms.Cursor]::Position = New-Object Drawing.Point(($area.Right - 80), ($area.Bottom - 40))
$oldArguments = $env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS
$env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = '--remote-debugging-port=9235'
$process = $null
try {
    $process = Start-Process -FilePath (Join-Path $destination 'Xennex.exe') -WorkingDirectory $destination -WindowStyle Hidden -PassThru
    & node (Join-Path $root 'frontend/tests/compact-native.test.cjs') 9235
    if ($LASTEXITCODE -ne 0) { throw 'Native compact test failed.' }
    if (-not $process.WaitForExit(10000)) { throw 'Test instance did not exit.' }
}
finally {
    if ($process -and -not $process.HasExited) { Stop-Process -Id $process.Id -Force }
    $env:WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS = $oldArguments
    [Windows.Forms.Cursor]::Position = $cursorBefore
}
Write-Host "Native compact test directory: $destination"
