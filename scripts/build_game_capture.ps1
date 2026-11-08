param([string]$ToolDirectory = 'bin/GameCaptureTools', [switch]$PrepareTools, [switch]$SignPrototype, [string]$OutputDirectory = 'bin/GameCaptureNative')
$ErrorActionPreference = 'Stop'
$root = (Get-Item $PSScriptRoot).Parent.FullName
$tools = Join-Path $root $ToolDirectory
$compiler = Join-Path $tools 'zig-x86_64-windows-0.17.0/zig.exe'
$minhook = Join-Path $root 'src/CaptureWorker/Native/ThirdParty/MinHook'
if ($PrepareTools -and -not (Test-Path -LiteralPath $compiler)) {
    New-Item -ItemType Directory -Force -Path $tools | Out-Null
    $archive = Join-Path $tools 'zig-0.17.0.zip'
    Invoke-WebRequest -UseBasicParsing -Uri 'https://ziglang.org/download/0.17.0/zig-x86_64-windows-0.17.0.zip' -OutFile $archive
    if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne 'B5663F69581DCF391293FBF16C06CB80D81D806545CE618B4D0BAB7F0EB8C428') {
        throw 'Zig archive hash differs from the pinned official release.'
    }
    Expand-Archive -LiteralPath $archive -DestinationPath $tools -Force
}
if (-not (Test-Path -LiteralPath $compiler) -or -not (Test-Path -LiteralPath (Join-Path $minhook 'LICENSE.txt'))) {
    throw 'Zig0.17.0 portable is missing; run scripts/build_game_capture.ps1 -PrepareTools. MinHook source must be present in Native/ThirdParty.'
}
if ((& $compiler version).Trim() -ne '0.17.0') { throw 'Unexpected Zig compiler version.' }
$native = Join-Path $root 'src/CaptureWorker/Native'
$output = Join-Path $root $OutputDirectory
New-Item -ItemType Directory -Force -Path $output | Out-Null
$env:ZIG_GLOBAL_CACHE_DIR = Join-Path $tools 'cache'
foreach ($arch in @('x86', 'x86_64')) {
    $suffix = if ($arch -eq 'x86') { '32' } else { '64' }
    $target = "$arch-windows-gnu"
    & $compiler cc -target $target -O2 -shared -Werror -Wall -I (Join-Path $minhook 'include') `
        (Join-Path $native 'GameHook.c') (Join-Path $minhook 'src/hook.c') (Join-Path $minhook 'src/buffer.c') `
        (Join-Path $minhook 'src/trampoline.c') (Join-Path $minhook 'src/hde/hde32.c') (Join-Path $minhook 'src/hde/hde64.c') `
        -lopengl32 -lgdi32 -luser32 -o (Join-Path $output "Xennex.GameHook$suffix.dll")
    if ($LASTEXITCODE -ne 0) { throw "GameHook$suffix build failed." }
    & $compiler cc -target $target -O2 -Werror -Wall -municode (Join-Path $native 'GameInjector.c') `
        -ladvapi32 -luser32 -o (Join-Path $output "Xennex.GameInjector$suffix.exe")
    if ($LASTEXITCODE -ne 0) { throw "GameInjector$suffix build failed." }
    & $compiler cc -target $target -O2 -Werror -Wall (Join-Path $root 'scripts/tests/CaptureWorkerTests/OpenGlFixture.c') `
        -lopengl32 -lgdi32 -luser32 -o (Join-Path $output "Xennex.OpenGlFixture$suffix.exe")
    if ($LASTEXITCODE -ne 0) { throw "OpenGlFixture$suffix build failed." }
}
New-Item -ItemType Directory -Force -Path (Join-Path $output 'licenses') | Out-Null
Copy-Item -LiteralPath (Join-Path $minhook 'LICENSE.txt') -Destination (Join-Path $output 'licenses/MinHook.txt') -Force
foreach ($name in @('Zig-runtime.txt','MinGW-runtime.txt')) {
    Copy-Item -LiteralPath (Join-Path $root "assets/licenses/$name") -Destination (Join-Path $output "licenses/$name") -Force
}
if ($SignPrototype) {
    . (Join-Path $PSScriptRoot 'lib/ReleaseValidation.ps1')
    $publisher = (Get-Content -LiteralPath (Join-Path $root 'assets/publisher-thumbprint.txt') -Raw).Trim()
    $certificate = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert | Where-Object { $_.Thumbprint -eq $publisher -and $_.HasPrivateKey } | Select-Object -First 1
    if (-not $certificate) { throw 'Existing Xennex publisher certificate unavailable; no identity will be created.' }
    foreach ($file in Get-ChildItem -LiteralPath $output -File | Where-Object { $_.Name -match '^Xennex.Game(Hook|Injector)(32|64)\.(dll|exe)$' }) {
        Set-AuthenticodeSignature -LiteralPath $file.FullName -Certificate $certificate -ErrorAction Stop | Out-Null
        Assert-XennexSignature -Path $file.FullName -ExpectedThumbprint $publisher
    }
}
Write-Host "Native capture prototype built in $output. Not packaged or enabled in the app. SignPrototype=$SignPrototype"
