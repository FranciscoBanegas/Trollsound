param(
    [string]$Version = '1.0.3'
)

$ErrorActionPreference = 'Stop'
$project = (Resolve-Path "$PSScriptRoot\..").Path
$installer = Join-Path $project 'dist\Trollsound-Setup-x64.exe'
$sources = Join-Path $project "dist\Trollsound-$Version-source.zip"
$notes = Join-Path $project "docs\RELEASE_NOTES_$Version.md"
$releaseDir = Join-Path $project "release\Trollsound-v$Version"

foreach ($required in ($installer, $sources, $notes)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Falta el artefacto requerido: $required"
    }
}

New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null
Get-ChildItem -LiteralPath $releaseDir -Force | Remove-Item -Recurse -Force

$releaseInstaller = Join-Path $releaseDir "Trollsound-Setup-v$Version-x64.exe"
Copy-Item -LiteralPath $installer -Destination $releaseInstaller
Copy-Item -LiteralPath $sources -Destination $releaseDir
Copy-Item -LiteralPath $notes -Destination (Join-Path $releaseDir 'RELEASE_NOTES.md')
Copy-Item -LiteralPath (Join-Path $project 'docs') -Destination $releaseDir -Recurse

$artifacts = @(
    $releaseInstaller,
    (Join-Path $releaseDir "Trollsound-$Version-source.zip")
)
$hashLines = foreach ($artifact in $artifacts) {
    $hash = Get-FileHash -LiteralPath $artifact -Algorithm SHA256
    '{0}  {1}' -f $hash.Hash, (Split-Path -Leaf $artifact)
}
$hashPath = Join-Path $releaseDir 'SHA256SUMS.txt'
Set-Content -LiteralPath $hashPath -Value $hashLines -Encoding ascii

$distHashLines = foreach ($artifact in ($installer, $sources)) {
    $hash = Get-FileHash -LiteralPath $artifact -Algorithm SHA256
    '{0}  {1}' -f $hash.Hash, (Split-Path -Leaf $artifact)
}
Set-Content -LiteralPath (Join-Path $project 'dist\SHA256SUMS.txt') -Value $distHashLines -Encoding ascii

Write-Host "Release preparado en $releaseDir"
Get-ChildItem -LiteralPath $releaseDir | Select-Object Name, Length
