param([switch]$PrepareTools, [switch]$BuildFixture, [ValidateRange(1,8)][int]$Jobs = 2)
$ErrorActionPreference = 'Stop'
$rtcRoot = (Get-Item $PSScriptRoot).Parent.FullName
$rtcTools = Join-Path $rtcRoot 'bin/NativeWebRtcTools'
$rtcOutput = Join-Path $rtcRoot 'bin/NativeWebRtc'
$rtcZig = Join-Path $rtcRoot 'bin/GameCaptureTools/zig-x86_64-windows-0.17.0/zig.exe'
if (-not (Test-Path -LiteralPath $rtcZig)) { throw 'Pinned Zig0.17.0 is required; prepare the existing game capture tools first.' }
if ((& $rtcZig version).Trim() -ne '0.17.0') { throw 'Unexpected Zig compiler version.' }
New-Item -ItemType Directory -Force -Path $rtcTools,$rtcOutput | Out-Null

function Get-RtcArchive([string]$Uri,[string]$Hash,[string]$Name,[string]$Destination) {
    $archive = Join-Path $rtcTools $Name
    if (-not (Test-Path -LiteralPath $archive)) { Invoke-WebRequest -UseBasicParsing -Uri $Uri -OutFile $archive }
    if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $Hash) { throw "Pinned archive digest differs: $Name" }
    Expand-Archive -LiteralPath $archive -DestinationPath $Destination -Force
}
function Get-RtcSource([string]$Uri,[string]$Tag,[string]$Commit,[string]$Path) {
    if (-not (Test-Path -LiteralPath (Join-Path $Path '.git'))) {
        & git -c credential.helper= clone --depth 1 --branch $Tag $Uri $Path
        if ($LASTEXITCODE -ne 0) { throw "Cannot obtain pinned source: $Tag" }
    }
    $actual = (& git -C $Path rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $actual -ne $Commit) { throw "Unexpected source commit: $Tag" }
}

$rtcCmake = Join-Path $rtcTools 'cmake-4.4.5-windows-x86_64/bin/cmake.exe'
$rtcNinja = Join-Path $rtcTools 'ninja/ninja.exe'
$rtcSource = Join-Path $rtcTools 'libdatachannel'
$rtcTls = Join-Path $rtcTools 'mbedtls-3.6.7'
if ($PrepareTools) {
    if (-not (Test-Path -LiteralPath $rtcCmake)) {
        Get-RtcArchive 'https://github.com/Kitware/CMake/releases/download/v4.4.5/cmake-4.4.5-windows-x86_64.zip' `
            '326C826486D46A23CF9D5A1C9EE3A567D427BDD02C4A34071937A2A675CFF004' 'cmake-4.4.5.zip' $rtcTools
    }
    if (-not (Test-Path -LiteralPath $rtcNinja)) {
        Get-RtcArchive 'https://github.com/ninja-build/ninja/releases/download/v1.13.2/ninja-win.zip' `
            '07FC8261B42B20E71D1720B39068C2E14FFCEE6396B76FB7A795FB460B78DC65' 'ninja-1.13.2.zip' (Join-Path $rtcTools 'ninja')
    }
    Get-RtcSource 'https://github.com/paullouisageneau/libdatachannel.git' 'v0.24.6' '6b1e2e620f1e37f0eafeee702eaea0043cb305fd' $rtcSource
    & git -C $rtcSource -c credential.helper= submodule update --init --depth 1 deps/plog deps/usrsctp deps/libjuice deps/libsrtp
    if ($LASTEXITCODE -ne 0) { throw 'Pinned WebRTC submodules unavailable.' }
    Get-RtcSource 'https://github.com/Mbed-TLS/mbedtls.git' 'v3.6.7' '068ff080b369adfac81509f9b57b2afabaf82dc5' $rtcTls
    & git -C $rtcTls -c credential.helper= submodule update --init --recursive --depth 1
    if ($LASTEXITCODE -ne 0) { throw 'Pinned Mbed TLS submodules unavailable.' }
}
if (-not (Test-Path -LiteralPath $rtcCmake) -or -not (Test-Path -LiteralPath $rtcNinja) -or -not (Test-Path -LiteralPath (Join-Path $rtcSource 'deps/libsrtp/CMakeLists.txt'))) {
    throw 'Native WebRTC tools/sources missing. Use -PrepareTools to download pinned portable tools and sources under bin/.'
}
if ((& $rtcNinja --version).Trim() -ne '1.13.2') { throw 'Unexpected Ninja version.' }
foreach ($rtcPin in @(@($rtcSource,'6b1e2e620f1e37f0eafeee702eaea0043cb305fd'),@($rtcTls,'068ff080b369adfac81509f9b57b2afabaf82dc5'))) {
    $rtcHead = (& git -C $rtcPin[0] rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $rtcHead -ne $rtcPin[1]) { throw 'Unexpected native dependency commit.' }
    & git -C $rtcPin[0] diff --quiet HEAD --
    if ($LASTEXITCODE -ne 0) { throw 'Pinned native dependency has tracked modifications.' }
}
$rtcAr = Join-Path $rtcTools 'zig-ar.cmd'
$rtcRanlib = Join-Path $rtcTools 'zig-ranlib.cmd'
Set-Content -LiteralPath $rtcAr -Encoding ASCII -Value ('@echo off' + "`r`n" + '"' + $rtcZig + '" ar %*')
Set-Content -LiteralPath $rtcRanlib -Encoding ASCII -Value ('@echo off' + "`r`n" + '"' + $rtcZig + '" ranlib %*')
$rtcToolchain = Join-Path $rtcTools 'zig-windows.cmake'
$rtcCompilerPath = $rtcZig.Replace('\','/')
$rtcArPath = $rtcAr.Replace('\','/')
$rtcRanlibPath = $rtcRanlib.Replace('\','/')
@"
set(CMAKE_SYSTEM_NAME Windows)
set(CMAKE_C_COMPILER "$rtcCompilerPath")
set(CMAKE_C_COMPILER_ARG1 cc)
set(CMAKE_CXX_COMPILER "$rtcCompilerPath")
set(CMAKE_CXX_COMPILER_ARG1 c++)
set(CMAKE_C_COMPILER_TARGET x86_64-windows-gnu)
set(CMAKE_CXX_COMPILER_TARGET x86_64-windows-gnu)
set(CMAKE_AR "$rtcArPath")
set(CMAKE_RANLIB "$rtcRanlibPath")
# Compile the TLS library and all consumers with the same DTLS-SRTP layout.
add_compile_definitions(MBEDTLS_SSL_DTLS_SRTP)
"@ | Set-Content -LiteralPath $rtcToolchain -Encoding ASCII
$env:ZIG_GLOBAL_CACHE_DIR = Join-Path $rtcTools 'zig-cache'
$rtcTlsBuild = Join-Path $rtcTools 'mbedtls-3.6.7-build'
$rtcTlsInstall = Join-Path $rtcTools 'mbedtls-3.6.7-install'
$rtcBuild = Join-Path $rtcTools 'webrtc-build-tls3.6.7'
$rtcCommon = @('-G','Ninja',"-DCMAKE_MAKE_PROGRAM=$rtcNinja","-DCMAKE_TOOLCHAIN_FILE=$rtcToolchain",'-DCMAKE_BUILD_TYPE=Release','-DCMAKE_POLICY_VERSION_MINIMUM=3.5')
Write-Host 'Configuring pinned Mbed TLS3.6.7 LTS; no global installation.'
& $rtcCmake -S $rtcTls -B $rtcTlsBuild @rtcCommon "-DCMAKE_INSTALL_PREFIX=$rtcTlsInstall" -DENABLE_PROGRAMS=OFF -DENABLE_TESTING=OFF -DUSE_SHARED_MBEDTLS_LIBRARY=OFF -DUSE_STATIC_MBEDTLS_LIBRARY=ON
if ($LASTEXITCODE -ne 0) { throw 'Mbed TLS configuration failed.' }
& $rtcCmake --build $rtcTlsBuild --target install --parallel $Jobs
if ($LASTEXITCODE -ne 0) { throw 'Mbed TLS build failed.' }
Write-Host 'Configuring native WebRTC media transport; P2P, no hosted relay.'
# Upstream libsrtp treats Windows GNU u_long format diagnostics as errors.
# Keep diagnostics visible without patching the pinned third-party source.
& $rtcCmake -S $rtcSource -B $rtcBuild @rtcCommon "-DCMAKE_INSTALL_PREFIX=$rtcOutput" "-DCMAKE_PREFIX_PATH=$rtcTlsInstall" `
    -DUSE_MBEDTLS=ON -DBUILD_SHARED_LIBS=ON -DBUILD_SHARED_DEPS_LIBS=OFF -DNO_EXAMPLES=ON -DNO_TESTS=ON -DNO_WEBSOCKET=ON -DNO_MEDIA=OFF -DCAPI_STDCALL=OFF `
    -DENABLE_WARNINGS_AS_ERRORS=OFF
if ($LASTEXITCODE -ne 0) { throw 'libdatachannel configuration failed.' }
& $rtcCmake --build $rtcBuild --target install --parallel $Jobs
if ($LASTEXITCODE -ne 0) { throw 'libdatachannel build failed.' }
$rtcLibrary = Join-Path $rtcOutput 'bin/libdatachannel.dll'
$rtcManifest = [ordered]@{
    schema = 'xennex-native-webrtc-build-v1'
    purpose = 'prototype-only'
    datachannel = [ordered]@{ version = '0.24.6'; commit = (& git -C $rtcSource rev-parse HEAD).Trim() }
    tls = [ordered]@{ version = '3.6.7'; commit = (& git -C $rtcTls rev-parse HEAD).Trim() }
    compiler = 'Zig0.17.0'; ninja = '1.13.2'; cmake = '4.4.5'
    library = 'bin/libdatachannel.dll'
    sha256 = (Get-FileHash -LiteralPath $rtcLibrary -Algorithm SHA256).Hash
}
$rtcManifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $rtcOutput 'build-info.json') -Encoding UTF8
if ($BuildFixture) {
    $rtcFixtures = Join-Path $rtcRoot 'bin/NativeEncoderFixtures'
    New-Item -ItemType Directory -Force -Path $rtcFixtures | Out-Null
    & $rtcZig cc -target x86_64-windows-gnu -O2 -Wall -Werror (Join-Path $rtcRoot 'scripts/tests/CaptureWorkerTests/OpenGlFixture.c') `
        -o (Join-Path $rtcFixtures 'Xennex.OpenGlFixture64.exe') -luser32 -lgdi32 -lopengl32
    if ($LASTEXITCODE -ne 0) { throw 'Own WGC/OpenGL fixture build failed.' }
}
Write-Host "Native WebRTC prototype built under $rtcOutput; not packaged or activated in the app."
