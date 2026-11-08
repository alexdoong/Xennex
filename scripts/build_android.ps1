param([string]$ToolsRoot = (Join-Path $PSScriptRoot '../bin/AndroidTools'))
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
$ToolsRoot = [IO.Path]::GetFullPath($ToolsRoot)
$javaRoot = Get-ChildItem (Join-Path $ToolsRoot 'java') -Directory | Select-Object -First 1
$gradle = Join-Path $ToolsRoot 'gradle-8.11.1/bin/gradle.bat'
if (!$javaRoot -or !(Test-Path $gradle) -or !(Test-Path (Join-Path $ToolsRoot 'sdk/platforms/android-35/android.jar'))) {
    throw 'Prepare JDK 17, Gradle 8.11.1 e SDK 35 conforme docs/ANDROID_STREAMING.md.'
}
$oldJava = $env:JAVA_HOME; $oldSdk = $env:ANDROID_HOME; $oldGradle = $env:GRADLE_USER_HOME
try {
    $env:JAVA_HOME = $javaRoot.FullName
    $env:ANDROID_HOME = Join-Path $ToolsRoot 'sdk'
    $env:GRADLE_USER_HOME = Join-Path $ToolsRoot 'gradle-home'
    & $gradle -p (Join-Path $repoRoot 'src/Android') --no-daemon --console=plain :app:assembleDebug :app:testDebugUnitTest :app:lintDebug
    if ($LASTEXITCODE -ne 0) { throw "Android build/checks failed: $LASTEXITCODE" }
    $apk = Join-Path $repoRoot 'src/Android/app/build/outputs/apk/debug/app-debug.apk'
    Get-Item $apk | Select-Object FullName,Length
    Get-FileHash $apk -Algorithm SHA256
} finally {
    $env:JAVA_HOME = $oldJava; $env:ANDROID_HOME = $oldSdk; $env:GRADLE_USER_HOME = $oldGradle
}
