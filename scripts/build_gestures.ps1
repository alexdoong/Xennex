$ErrorActionPreference = 'Stop'
$root = (Get-Item $PSScriptRoot).Parent.FullName
$python = Join-Path $root '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Execute scripts/setup_gestures.ps1 antes de compilar Gestures.' }
& $python -m pip install -r (Join-Path $PSScriptRoot 'requirements-gestures-build.txt') --disable-pip-version-check
if ($LASTEXITCODE -ne 0) { throw 'Falha ao preparar o empacotador de Gestures.' }
$dist = Join-Path $root 'bin/GesturesWorker'
$work = Join-Path $root 'bin/GesturesWorkerBuild'
New-Item -ItemType Directory -Force -Path $dist, $work | Out-Null
& $python -m PyInstaller --noconfirm --onefile --console --noupx --log-level WARN `
    --name Xennex.GesturesWorker --icon (Join-Path $root 'assets/icon.ico') `
    --distpath $dist --workpath $work --specpath $work `
    --collect-data mediapipe --copy-metadata mediapipe `
    --exclude-module jax --exclude-module jaxlib --exclude-module tensorflow `
    --exclude-module mediapipe.tasks.python.genai.converter `
    (Join-Path $PSScriptRoot 'hand_motion.py')
if ($LASTEXITCODE -ne 0) { throw 'Falha ao compilar Gestures.' }
$worker = Join-Path $dist 'Xennex.GesturesWorker.exe'
& $worker --config unused --check
if ($LASTEXITCODE -ne 0) { throw 'O motor compilado falhou ao carregar o modelo de maos.' }
Write-Host "Gestures compilado e validado sem abrir a camera: $worker"
