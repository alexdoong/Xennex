$ErrorActionPreference = 'Stop'
$root = (Get-Item $PSScriptRoot).Parent.Parent.FullName
. (Join-Path $root 'scripts/lib/ReleaseValidation.ps1')
$fixture = Join-Path $root ('bin/update-security-' + [Guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($fixture) | Out-Null
$tokens = $null; $errors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile((Join-Path $root 'src/Services/Updates/install_update.ps1'), [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw ($errors | Out-String) }
foreach ($name in @('Assert-XennexUpdateHash', 'Expand-XennexVerifiedArchive', 'Assert-XennexUpdatePublisher')) {
    $function = $ast.Find({ param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name }, $true)
    . ([scriptblock]::Create($function.Extent.Text))
}
function Reject { param([scriptblock]$Action, [string]$Name)
    try { & $Action } catch { Write-Host "PASS: $Name"; return }
    throw "Accepted invalid input: $Name"
}
function New-FixtureZip { param([string[]]$Entries)
    $path = Join-Path $fixture ([Guid]::NewGuid().ToString('N') + '.zip')
    $archive = [IO.Compression.ZipFile]::Open($path, 'Create')
    try { foreach ($name in $Entries) { $entry = $archive.CreateEntry($name); $writer = [IO.StreamWriter]::new($entry.Open()); $writer.Write('synthetic'); $writer.Dispose() } }
    finally { $archive.Dispose() }
    return $path
}
Add-Type -AssemblyName System.IO.Compression.FileSystem
try {
    $base = 'Xennex-v0.2.4-win64'
    $valid = New-FixtureZip @("$base/Xennex.exe", "$base/wwwroot/index.html")
    $hash = (Get-FileHash -LiteralPath $valid -Algorithm SHA256).Hash
    Assert-XennexUpdateHash $valid $hash
    Reject { Assert-XennexUpdateHash $valid ('0' * 64) } 'wrong hash'
    Reject { Assert-XennexUpdateHash $valid '' } 'missing hash'
    $source = Expand-XennexVerifiedArchive $valid (Join-Path $fixture 'valid') $base
    if (-not (Test-Path -LiteralPath (Join-Path $source 'wwwroot/index.html'))) { throw 'Valid ZIP failed.' }
    Reject { Assert-XennexUpdatePublisher $source ('0' * 40) } 'unsigned update executable'
    foreach ($entries in @(
        @("$base/Xennex.exe", "$base/../../escaped.txt"),
        @("$base/Xennex.exe", 'C:/escaped.txt'),
        @("$base/Xennex.exe", "$base/xennex.EXE"),
        @("$base/Xennex.exe", "$base/file:stream"),
        @("$base/Xennex.exe", "$base/.. /escaped.txt"),
        @("$base/Xennex.exe", 'other/file.txt')
    )) {
        $malicious = New-FixtureZip $entries
        Reject { Expand-XennexVerifiedArchive $malicious (Join-Path $fixture ([Guid]::NewGuid().ToString('N'))) $base } 'unsafe ZIP entry'
    }
    if (Test-Path -LiteralPath (Join-Path $fixture 'escaped.txt')) { throw 'ZIP escaped extraction directory.' }
    Write-Host 'PASS: valid hash/archive accepted; tampering, missing digest, unsigned executable and unsafe ZIP entries rejected.'
}
finally { Remove-XennexBuildDirectory $fixture (Join-Path $root 'bin') }
