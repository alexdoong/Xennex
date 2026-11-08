$ErrorActionPreference = 'Stop'
$projectRoot = (Get-Item $PSScriptRoot).Parent.Parent.FullName
. (Join-Path $projectRoot 'scripts/lib/ReleaseValidation.ps1')
$testRoot = Join-Path $projectRoot ('bin/release-tests-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testRoot -Force | Out-Null

function Write-Fixture {
    param([string]$Path, [string]$Content)
    New-Item -ItemType Directory -Path (Split-Path $Path) -Force | Out-Null
    [IO.File]::WriteAllText($Path, $Content)
}
function Assert-Equal {
    param($Actual, $Expected, [string]$Message)
    if ($Actual -ne $Expected) { throw $Message }
}
function Assert-Rejected {
    param([scriptblock]$Action, [string]$Message)
    $rejected = $false
    try { & $Action } catch { $rejected = $true }
    if (-not $rejected) { throw $Message }
}

try {
    $package = Join-Path $testRoot 'package'
    $web = Join-Path $package 'wwwroot'
    Write-Fixture (Join-Path $web 'index.html') '<script src="/assets/index-test.js"></script><link href="/assets/index-test.css">'
    Write-Fixture (Join-Path $web 'assets/index-test.js') ('x' * 51201)
    Write-Fixture (Join-Path $web 'assets/index-test.css') 'body{}'
    Write-Fixture (Join-Path $web 'skins/default/skin.json') 'new default'
    Write-Fixture (Join-Path $package 'Data/config.txt') 'new config'
    foreach ($name in @('Xennex.exe', 'Xennex.CaptureWorker.exe', 'WebView2Loader.dll',
        'GameCapture/Xennex.GameHook32.dll', 'GameCapture/Xennex.GameHook64.dll', 'GameCapture/Xennex.GameInjector32.exe', 'GameCapture/Xennex.GameInjector64.exe', 'licenses/MinHook.txt',
        'licenses/Zig-runtime.txt', 'licenses/MinGW-runtime.txt',
        'alexdoong.cer', 'instalar_certificado_alexdoong.cmd', 'scripts/hand_motion.py', 'scripts/Xennex.GesturesWorker.exe', 'scripts/setup_gestures.ps1', 'scripts/requirements-gestures.txt',
        'scripts/gestures/capture.py', 'scripts/gestures/smoothing.py', 'scripts/gestures/action_errors.py',
        'scripts/gestures/__init__.py', 'scripts/gestures/features.py', 'scripts/gestures/recognition.py',
        'scripts/gestures/recording.py', 'scripts/gestures/control.py', 'scripts/gestures/tracking.py',
        'scripts/gestures/windows_actions.py', 'scripts/gestures/runtime.py')) {
        Write-Fixture (Join-Path $package $name) 'fixture'
    }
    Assert-XennexPackage $package
    $gestureModule = Join-Path $package 'scripts/gestures/control.py'
    [IO.File]::Move($gestureModule, "$gestureModule.saved")
    Assert-Rejected { Assert-XennexPackage $package } 'Modulo de controle ausente deve ser recusado.'
    [IO.File]::Move("$gestureModule.saved", $gestureModule)
    Write-Fixture (Join-Path $web 'assets/index-test.js') ('x' * 51200)
    Assert-Rejected { Assert-XennexFrontend $web } 'JS de 50 KB deve ser recusado.'
    Write-Fixture (Join-Path $web 'assets/index-test.js') ('x' * 51201)
    $css = Join-Path $web 'assets/index-test.css'
    [IO.File]::Move($css, "$css.saved")
    Assert-Rejected { Assert-XennexFrontend $web } 'CSS ausente deve ser recusado.'
    [IO.File]::Move("$css.saved", $css)
    New-Item -ItemType Directory -Path (Join-Path $web 'wwwroot') | Out-Null
    Assert-Rejected { Assert-XennexFrontend $web } 'wwwroot aninhado deve ser recusado.'
    Remove-XennexBuildDirectory (Join-Path $web 'wwwroot') $testRoot
    Write-Fixture (Join-Path $package 'Data/config.txt') 'E:\dev\personal.exe'
    Assert-Rejected { Assert-XennexPackage $package } 'Caminho local deve ser recusado.'
    Write-Fixture (Join-Path $package 'Data/config.txt') 'new config'
    Write-Fixture (Join-Path $web 'skins/custom/skin.json') 'incoming custom'
    Assert-Rejected { Assert-XennexPackage $package } 'Skin pessoal deve ser recusada.'
    $version = Get-XennexReleaseVersion (Join-Path $projectRoot 'Xennex.csproj')
    Assert-Rejected { Get-XennexReleaseVersion (Join-Path $projectRoot 'Xennex.csproj') '999.0.0' } 'Versao divergente deve ser recusada.'
    Assert-Rejected { Remove-XennexBuildDirectory $projectRoot $testRoot } 'Limpeza fora do staging deve ser recusada.'

    # Load only the copy function: never run the updater, processes or downloads.
    $tokens = $null; $parseErrors = $null
    $updater = Join-Path $projectRoot 'src/Services/Updates/install_update.ps1'
    $ast = [Management.Automation.Language.Parser]::ParseFile($updater, [ref]$tokens, [ref]$parseErrors)
    if ($parseErrors.Count) { throw ($parseErrors | Out-String) }
    $function = $ast.Find({ param($node)
        $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Copy-XennexUpdate'
    }, $true)
    if (-not $function) { throw 'Funcao de copia do atualizador nao encontrada.' }
    . ([scriptblock]::Create($function.Extent.Text))
    $installed = Join-Path $testRoot 'installed'
    Write-Fixture (Join-Path $installed 'Data/config.txt') 'my config'
    Write-Fixture (Join-Path $installed 'Data/wuwa_build.txt') 'my build'
    Write-Fixture (Join-Path $installed 'wwwroot/skins/custom/skin.json') 'my custom'
    Write-Fixture (Join-Path $installed 'wwwroot/skins/default/skin.json') 'old default'
    Write-Fixture (Join-Path $package 'Data/gestures.json') '{}'
    1..2 | ForEach-Object { Copy-XennexUpdate $package $installed }
    Assert-Equal (Get-Content (Join-Path $installed 'Data/config.txt') -Raw) 'my config' 'Config sobrescrita.'
    Assert-Equal (Get-Content (Join-Path $installed 'Data/wuwa_build.txt') -Raw) 'my build' 'Build pessoal alterada.'
    Assert-Equal (Get-Content (Join-Path $installed 'Data/gestures.json') -Raw) '{}' 'Novo dado padrao nao instalado.'
    Assert-Equal (Get-Content (Join-Path $installed 'wwwroot/skins/custom/skin.json') -Raw) 'my custom' 'Skin pessoal sobrescrita.'
    Assert-Equal (Get-Content (Join-Path $installed 'wwwroot/skins/default/skin.json') -Raw) 'new default' 'Skin default nao atualizada.'
    Assert-XennexFrontend (Join-Path $installed 'wwwroot')
    Assert-Equal (Test-Path (Join-Path $installed 'wwwroot/skins/default/default')) $false 'Skin aninhada apos duas atualizacoes.'
    Write-Host "PASS: integridade do pacote, versao $version e preservacao de dados em duas atualizacoes."
}
finally {
    Remove-XennexBuildDirectory $testRoot (Join-Path $projectRoot 'bin')
}
