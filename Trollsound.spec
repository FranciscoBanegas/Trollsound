from pathlib import Path
from PyQt6.QtCore import QLibraryInfo

root = Path(SPECPATH)
qt_bin = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.BinariesPath))
ffmpeg = [(str(dll), 'PyQt6/Qt6/bin') for pattern in
          ('avcodec-*.dll', 'avformat-*.dll', 'avutil-*.dll', 'swresample-*.dll', 'swscale-*.dll')
          for dll in qt_bin.glob(pattern)]
a = Analysis(
    [str(root / 'launcher.py')], pathex=[str(root)],
    binaries=ffmpeg,
    datas=[(str(root / 'README.md'), '.'), (str(root / 'THIRD_PARTY.md'), '.'),
           (str(root / 'licenses'), 'licenses'), (str(root / 'LICENSE'), '.')],
    hiddenimports=['PyQt6.QtMultimedia'],
    excludes=['PyQt6.QtWebEngineCore', 'PyQt6.QtWebEngineWidgets', 'tkinter'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='Trollsound',
          debug=False, strip=False, upx=False, console=False,
          version=str(root / 'packaging' / 'version.txt'),
          manifest=str(root / 'packaging' / 'app.manifest'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='Trollsound')
