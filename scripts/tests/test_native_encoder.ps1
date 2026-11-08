param([ValidateRange(5,120)][int]$TimeoutSeconds = 30, [switch]$Encode, [switch]$CpuControl, [switch]$Bgra, [switch]$Color, [switch]$Amf, [ValidateRange(0,31)][int]$Candidate = 0,
    [ValidateRange(0,15)][int]$Adapter = 0, [ValidateRange(16,4096)][int]$Width = 640, [ValidateRange(16,2160)][int]$Height = 360,
    [ValidateRange(1,120)][int]$Fps = 30, [ValidateRange(8,240)][int]$Frames = 8)
$ErrorActionPreference = 'Stop'
if ($Amf -and (-not $Encode -or $CpuControl -or -not ($Bgra -or $Color))) { throw 'AMF requires an explicit encode with BGRA input.' }
$encoderRoot = (Get-Item $PSScriptRoot).Parent.Parent.FullName
$encoderProject = Join-Path $encoderRoot 'scripts/tests/NativeEncoderTests/NativeEncoderTests.csproj'
& dotnet build $encoderProject -c Release --no-restore
if ($LASTEXITCODE -ne 0) { throw 'Native encoder prototype build failed.' }
$encoderDll = Join-Path $encoderRoot 'bin/NativeEncoderTests/net8.0-windows10.0.19041.0/NativeEncoderTests.dll'
$encoderReport = Join-Path $encoderRoot $(if ($Encode) { 'bin/native-encoder-texture.json' } else { 'bin/native-encoder-probe.json' })
$encoderErrors = Join-Path $encoderRoot $(if ($Encode) { 'bin/native-encoder-texture.stderr.log' } else { 'bin/native-encoder-probe.stderr.log' })
$encoderInfo = New-Object System.Diagnostics.ProcessStartInfo
$encoderInfo.FileName = (Get-Command dotnet).Source
$encoderInfo.Arguments = '"' + $encoderDll + '" ' + $(if ($Encode) { '--encode' } else { '--probe' })
if ($CpuControl) { $encoderInfo.Arguments += ' --cpu-control' }
if ($Bgra -or $Color) { $encoderInfo.Arguments += ' --bgra' }
if ($Color) { $encoderInfo.Arguments += ' --color' }
if ($Amf) { $encoderInfo.Arguments += ' --amf' }
if ($Encode) { $encoderInfo.Arguments += " --candidate $Candidate --adapter $Adapter --width $Width --height $Height --fps $Fps --frames $Frames" }
$encoderInfo.WorkingDirectory = $encoderRoot
$encoderInfo.UseShellExecute = $false
$encoderInfo.CreateNoWindow = $true
$encoderInfo.RedirectStandardOutput = $true
$encoderInfo.RedirectStandardError = $true
$encoderProcess = New-Object System.Diagnostics.Process
$encoderProcess.StartInfo = $encoderInfo
$null = $encoderProcess.Start()
$encoderOutputTask = $encoderProcess.StandardOutput.ReadToEndAsync()
$encoderErrorTask = $encoderProcess.StandardError.ReadToEndAsync()
try {
    if (-not $encoderProcess.WaitForExit($TimeoutSeconds * 1000)) {
        Stop-Process -Id $encoderProcess.Id -Force -ErrorAction SilentlyContinue
        throw 'Encoder inventory exceeded its deadline; only the isolated probe was stopped.'
    }
    $encoderProcess.WaitForExit()
    Set-Content -LiteralPath $encoderReport -Value $encoderOutputTask.GetAwaiter().GetResult() -Encoding UTF8
    Set-Content -LiteralPath $encoderErrors -Value $encoderErrorTask.GetAwaiter().GetResult() -Encoding UTF8
    if ($encoderProcess.ExitCode -ne 0) { throw "Native encoder probe failed; inspect $encoderErrors." }
    $encoderResult = Get-Content -LiteralPath $encoderReport -Raw | ConvertFrom-Json
    if ($Encode) {
        if ($encoderResult.Schema -ne 'xennex-native-gpu-encode-v1' -or $encoderResult.Result.Encoded -ne $Frames -or -not $encoderResult.Result.Validation.AlternatingPattern) { throw 'GPU encode/decode did not validate all expected synthetic samples.' }
        $encoderResult.Result | ConvertTo-Json
        Write-Host 'Synthetic encode and independent software decode verified. Capture integration and WebRTC delivery remain separate work.'
        return
    }
    if ($encoderResult.Schema -ne 'xennex-native-encoder-inventory-v1') { throw 'Unexpected inventory report schema.' }
    $encoderResult.Adapters | ForEach-Object {
        [pscustomobject]@{ Adapter=$_.Adapter; Name=$_.Name; Codec=$_.Codec; Status=$_.Status; Candidates=@($_.Candidates).Count }
    } | Format-Table -AutoSize
    Write-Host 'Inventory only: no profile, encoding or GPU zero-copy claim. Local report: bin/native-encoder-probe.json'
}
finally { $encoderProcess.Dispose() }
