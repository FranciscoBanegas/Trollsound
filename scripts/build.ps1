param(
    [string]$Python = 'python',
    [string]$InnoCompiler = "$PSScriptRoot\..\.tools\inno\ISCC.exe",
    [switch]$SkipDependencies
)
$ErrorActionPreference = 'Stop'
$project = (Resolve-Path "$PSScriptRoot\..").Path
Push-Location $project
try {
    $buildTemp = Join-Path $project 'build\temp'
    New-Item -ItemType Directory -Force -Path $buildTemp | Out-Null
    $env:TEMP = $buildTemp
    $env:TMP = $buildTemp
    if (-not (Test-Path '.venv\Scripts\python.exe')) {
        & $Python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear el entorno Python 3.12.' }
    }
    $interpreter = Join-Path $project '.venv\Scripts\python.exe'
    & $interpreter -c 'import sys,struct; assert sys.version_info[:2] == (3,12) and struct.calcsize("P") == 8, "Se requiere Python 3.12 x64"'
    if ($LASTEXITCODE -ne 0) { throw 'Python incompatible.' }
    if (-not $SkipDependencies) {
        & $interpreter -m pip install -r requirements-build.txt
        if ($LASTEXITCODE -ne 0) { throw 'No se pudieron instalar las dependencias.' }
    }
    & $interpreter -m pytest -q -o "cache_dir=build/pytest-cache"
    if ($LASTEXITCODE -ne 0) { throw 'Las pruebas fallaron.' }
    & $interpreter -m PyInstaller --noconfirm Trollsound.spec
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller fallo.' }
    if (-not (Test-Path $InnoCompiler)) { throw 'Indica -InnoCompiler con la ruta de ISCC.exe (Inno Setup 6.7.3).' }
    & $InnoCompiler packaging\Trollsound.iss
    if ($LASTEXITCODE -ne 0) { throw 'Inno Setup fallo.' }
    & $interpreter -m scripts.package_source
    if ($LASTEXITCODE -ne 0) { throw 'No se pudieron empaquetar las fuentes.' }
    & "$PSScriptRoot\package_release.ps1"
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo preparar la carpeta de publicacion.' }
    Get-FileHash 'dist\Trollsound-Setup-x64.exe' -Algorithm SHA256
} finally {
    Pop-Location
}
