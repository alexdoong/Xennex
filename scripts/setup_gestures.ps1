$ErrorActionPreference = 'Stop'
$root = (Get-Item $PSScriptRoot).Parent.FullName
$environment = Join-Path $root '.venv'
if (-not (Test-Path (Join-Path $environment 'Scripts/python.exe'))) {
    py -3.11 -m venv $environment
    if ($LASTEXITCODE -ne 0) { throw 'Instale Python 3.11 x64 para criar o ambiente de Gestures.' }
}
& (Join-Path $environment 'Scripts/python.exe') -m pip install -r (Join-Path $PSScriptRoot 'requirements-gestures.txt')
if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar as dependencias de Gestures.' }
& (Join-Path $environment 'Scripts/python.exe') (Join-Path $PSScriptRoot 'hand_motion.py') --config unused --check
if ($LASTEXITCODE -ne 0) { throw 'Runtime incompativel.' }
Write-Host 'Gestures pronto. A verificacao nao abriu a camera.'
