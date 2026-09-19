# Guia tecnica de compilacion y versionado

## Alcance

Esta guia produce Trollsound para Windows 10/11 x64 con Python 3.12, PyQt6, PyInstaller `onedir` e Inno Setup. El resultado principal es un instalador por maquina y sin firma digital.

## Herramientas requeridas

- Windows x64.
- Python 3.12 x64 disponible como `python` o mediante una ruta absoluta.
- PowerShell 5.1 o posterior.
- Inno Setup 6.7.3 con `ISCC.exe`.
- Acceso a PyPI al preparar por primera vez el entorno.
- VB-Cable y un microfono para las pruebas reales; no son necesarios para las pruebas unitarias simuladas.

Las versiones Python estan bloqueadas en `requirements.txt` y `requirements-build.txt`. No actualices dependencias dentro de una publicacion sin volver a ejecutar todas las pruebas.

## Estructura relevante

```text
trollsound/                 Aplicacion, audio, hotkeys, persistencia e interfaz
tests/                      Pruebas unitarias y Qt
scripts/build.ps1           Pipeline reproducible de compilacion
scripts/package_source.py   ZIP de fuentes
scripts/package_release.ps1 Carpeta final de publicacion
scripts/verify_live.py      Validacion real de audio y formatos
scripts/verify_hotkeys.py   Validacion interactiva de atajos
packaging/Trollsound.iss    Instalador Inno Setup
packaging/version.txt       Metadatos del ejecutable de Windows
packaging/app.manifest      Manifiesto del ejecutable
Trollsound.spec             Bundle PyInstaller
docs/                       Documentacion distribuible
```

## Preparar el entorno

Desde la raiz del proyecto:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
```

Comprueba la arquitectura y la version:

```powershell
.\.venv\Scripts\python.exe -c "import struct,sys; print(sys.version); print(struct.calcsize('P') * 8)"
```

La salida debe indicar Python 3.12 y 64 bits.

## Ejecutar y probar en desarrollo

```powershell
.\.venv\Scripts\python.exe launcher.py
.\.venv\Scripts\python.exe -m pytest -q -o cache_dir=build/pytest-cache
```

Las pruebas automatizadas simulan dispositivos y validan persistencia, migraciones, filtrado estricto de VB-Cable, atajos nativos, estados de interfaz, mezcla PCM, saturacion, limites de buffer y politicas de interrupcion. No sustituyen la prueba con hardware real.

Pruebas interactivas:

```powershell
.\.venv\Scripts\python.exe -m scripts.verify_hotkeys
.\.venv\Scripts\python.exe -m scripts.verify_live
```

`verify_hotkeys` comprueba una activacion visible, oculta y minimizada. `verify_live` genera WAV, MP3, OGG y FLAC, envia voz y clip al cable, captura `CABLE Output` y valida la escucha local.

## Compilar todo

El pipeline crea el entorno si falta, instala dependencias, ejecuta pruebas, genera el bundle `onedir`, compila el instalador, empaqueta fuentes y prepara la carpeta de publicacion:

```powershell
.\scripts\build.ps1 `
  -Python 'C:\ruta\a\python.exe' `
  -InnoCompiler 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
```

Si `.venv` ya contiene exactamente las dependencias bloqueadas:

```powershell
.\scripts\build.ps1 -SkipDependencies
```

Salidas esperadas:

```text
dist/Trollsound/                         Bundle portable completo
dist/Trollsound-Setup-x64.exe            Instalador generado por Inno Setup
dist/Trollsound-<version>-source.zip      Fuentes publicables
release/Trollsound-v<version>/            Entrega final para publicar
```

No distribuyas `dist/Trollsound/Trollsound.exe` por separado: necesita el directorio `_internal`. Para usuarios finales distribuye el instalador `.exe` de la carpeta `release`.

## Que hace el pipeline

1. Verifica Python 3.12 x64.
2. Instala las dependencias bloqueadas.
3. Ejecuta `pytest` y detiene el build ante cualquier fallo.
4. Ejecuta PyInstaller con `Trollsound.spec`, incluyendo Qt Multimedia, FFmpeg, plugins, manifiesto, licencias y metadatos.
5. Inno Setup empaqueta el bundle y la carpeta `docs`.
6. Genera el ZIP de fuentes sin `.venv`, binarios, caches, datos de usuario ni controladores descargados.
7. Copia los artefactos publicables y calcula `SHA256SUMS.txt`.

VB-Cable no se redistribuye. El instalador comprueba el controlador y, con consentimiento, abre el flujo oficial de descarga e instalacion. Su asistente debe permanecer visible para aceptar sus terminos.

## Versionado

Trollsound usa versionado semantico `MAJOR.MINOR.PATCH`:

- `PATCH`: correccion compatible sin cambios de contrato.
- `MINOR`: funcionalidad compatible nueva.
- `MAJOR`: cambio incompatible de configuracion, comportamiento o plataforma.

El `schema_version` de `config.json` es independiente de la version del producto. Solo debe incrementarse cuando cambia el formato persistido, y toda subida requiere una migracion y pruebas desde los esquemas soportados.

Para preparar una version, actualiza de forma coherente:

- `trollsound/__init__.py`: `__version__`.
- `packaging/Trollsound.iss`: `AppVersion`.
- `packaging/version.txt`: `FileVersion` y `ProductVersion`.
- `packaging/app.manifest`: `assemblyIdentity version`, con cuarto componente `.0`.
- `scripts/package_source.py`: nombre del ZIP.
- `scripts/package_release.ps1`: valor predeterminado de `Version`.
- `docs/README.md`, notas de version, `README.md` y `VALIDATION.md`.

Busca residuos de la version anterior antes del build:

```powershell
rg -n "1\.0\.3|schema_version" . `
  -g '!dist/**' -g '!build/**' -g '!release/**' -g '!.venv/**'
```

Sustituye `1.0.3` por la version que estas retirando. Revisa cada coincidencia: no cambies historiales de migracion o notas antiguas que deban conservarse.

## Lista de publicacion

1. Actualiza version y notas.
2. Ejecuta las pruebas automatizadas.
3. Compila con `scripts/build.ps1`.
4. Ejecuta sobre el bundle:

```powershell
.\dist\Trollsound\Trollsound.exe --check-vb-cable
.\dist\Trollsound\Trollsound.exe --smoke-test
.\dist\Trollsound\Trollsound.exe --verify-audio (Resolve-Path .\build\verification)
```

5. Prueba el instalador en una cuenta o VM limpia sin Python.
6. Confirma voz y clip simultaneos en una llamada real, con la ventana visible, minimizada y en bandeja.
7. Actualiza `VALIDATION.md` separando resultados ejecutados de pruebas pendientes.
8. Vuelve a empaquetar las fuentes y la entrega si cambiaste documentacion despues del build:

```powershell
.\.venv\Scripts\python.exe -m scripts.package_source
.\scripts\package_release.ps1
```

9. Verifica los hashes publicados:

```powershell
Get-FileHash .\release\Trollsound-v1.0.3\Trollsound-Setup-v1.0.3-x64.exe -Algorithm SHA256
```

10. Publica todos los archivos de `release\Trollsound-v<version>` y marca el instalador `.exe` como descarga recomendada.

## Firma y seguridad

El instalador actual no esta firmado y puede activar SmartScreen. Para una distribucion publica estable, usa un certificado de firma de codigo y firma primero `dist\Trollsound\Trollsound.exe` y despues el instalador final. Conserva las claves privadas fuera del repositorio y del pipeline local.

Nunca publiques `%LOCALAPPDATA%\Trollsound`, archivos de audio del usuario, `.venv`, `.tools`, `build`, dumps, logs ni el ZIP extraido de VB-Cable. Publica siempre `SHA256SUMS.txt` junto a los binarios.

## Publicar en un proveedor

La carpeta de release es independiente del proveedor. En GitHub Releases, crea una etiqueta `v<version>`, usa el contenido de `RELEASE_NOTES.md` como descripcion y adjunta el `.exe`, el ZIP de fuentes y `SHA256SUMS.txt`. En otro alojamiento, conserva los mismos nombres y ofrece el hash al lado del enlace de descarga.
