param([switch]$PrepareTools)
$ErrorActionPreference = 'Stop'
$amfRoot = (Get-Item $PSScriptRoot).Parent.FullName
$amfSdk = Join-Path $amfRoot 'bin/NativeAmfTools/amf-sdk-1.5.3'
$amfCommit = '57ee0cfb0e1a08d9041f77435653794c1b012be0'
$amfCompiler = Join-Path $amfRoot 'bin/GameCaptureTools/zig-x86_64-windows-0.17.0/zig.exe'
$amfOutput = Join-Path $amfRoot 'bin/NativeAmf'
if ($PrepareTools -and -not(Test-Path -LiteralPath (Join-Path $amfSdk '.git'))) {
    & git -c credential.helper= clone --depth 1 --filter=blob:none --sparse --branch v1.5.3 https://github.com/GPUOpen-LibrariesAndSDKs/AMF.git $amfSdk
    if ($LASTEXITCODE -ne 0) { throw 'Pinned AMF source unavailable.' }
    & git -C $amfSdk sparse-checkout set amf/public/include
    if ($LASTEXITCODE -ne 0) { throw 'Pinned AMF headers unavailable.' }
}
if (-not(Test-Path -LiteralPath $amfCompiler) -or -not(Test-Path -LiteralPath (Join-Path $amfSdk 'LICENSE.txt'))) { throw 'Prepare pinned Zig and AMF headers first.' }
if ((& $amfCompiler version).Trim() -ne '0.17.0' -or (& git -C $amfSdk rev-parse HEAD).Trim() -ne $amfCommit) { throw 'Unexpected AMF compiler/source version.' }
& git -C $amfSdk diff --quiet HEAD --
if ($LASTEXITCODE -ne 0) { throw 'AMF source has tracked modifications.' }
New-Item -ItemType Directory -Force -Path $amfOutput | Out-Null
$env:ZIG_GLOBAL_CACHE_DIR = Join-Path $amfRoot 'bin/NativeAmfTools/zig-cache'
$amfLibrary = Join-Path $amfOutput 'Xennex.AmfProbe.dll'
& $amfCompiler cc -target x86_64-windows-gnu -std=c11 -O2 -shared -Wall -Werror -I (Join-Path $amfSdk 'amf/public/include') `
    (Join-Path $amfRoot 'scripts/tests/NativeEncoderTests/Native/AmfEncoder.c') -o $amfLibrary -luser32 -lole32
if ($LASTEXITCODE -ne 0) { throw 'Own AMF C ABI adapter build failed.' }
Copy-Item -LiteralPath (Join-Path $amfSdk 'LICENSE.txt') -Destination (Join-Path $amfOutput 'AMF-SDK-LICENSE.txt')
[ordered]@{ schema='xennex-amf-probe-build-v1'; purpose='prototype-only'; sdk='1.5.3'; commit=$amfCommit; compiler='Zig0.17.0';
    minimumRuntime='1.4.0.0'; sha256=(Get-FileHash -LiteralPath $amfLibrary -Algorithm SHA256).Hash } |
    ConvertTo-Json | Set-Content -LiteralPath (Join-Path $amfOutput 'build-info.json') -Encoding UTF8
Write-Host 'AMF adapter built under bin/NativeAmf; driver DLL is loaded from System32 at runtime, never copied or installed.'
