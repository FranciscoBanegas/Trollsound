# Verificacion de Trollsound 1.0.4

Fecha: 2026-09-18. Entorno real: Windows 11 x64, build 26200; Python 3.12.14; PyQt6 6.8.1 / Qt 6.8.2; PyInstaller 6.16.0; Inno Setup 6.7.3.

## Artefactos finales

- `dist/Trollsound-Setup-x64.exe`: instalador sin firma, 34.121.826 bytes; incluye `docs`.
- `dist/Trollsound-1.0.4-source.zip`: fuentes, pruebas, instrucciones, scripts y licencias.
- `dist/Trollsound/Trollsound.exe`: ejecutable portable 1.0.4; debe conservarse junto a `_internal`.
- `release/Trollsound-v1.0.4`: carpeta publicable con instalador versionado, fuentes, documentacion, notas y hashes.
- SHA-256 del instalador: `A2CF83B0358C266638E86B1CDC3831B035C102F36D2B2BD90A83E7B35D18B375`.

## Pruebas ejecutadas

- **65 pruebas automatizadas aprobadas**: mezcla Float e Int16, saturacion, ganancias, silencio, limites de buffer, interrupcion, puente persistente, cambio de microfono, pausa, bandeja, migracion de esquemas 1/2/3 a 4, formatos, atajos e instalador simulado.
- El atajo global de detencion se registra como accion independiente, detecta conflictos y corta solamente el clip. La configuracion rechaza duplicados con las macros.
- El motor mantiene `QAudioSource -> MixerDevice -> QAudioSink` de forma continua. Pausar macros, detener un clip y cerrar hacia la bandeja conservan la misma fuente y sink del microfono.
- El mezclador limita el buffer de voz a 250 ms, solicita buffers de dispositivo de 60 ms y mantiene como maximo dos segundos de audio decodificado por delante.
- **Prueba real desde fuentes**: `Micrófono (MU900)` y `CABLE Input` negociaron 48 kHz, estereo, Float. WAV, MP3, OGG y FLAC llegaron a CABLE Output y se monitorizaron por `Altavoces (MU900)`.
- **Prueba real del bundle 1.0.3**: los cuatro formatos aprobaron captura por CABLE Output, puente de microfono y escucha local. Resultado: `build/verification/bundle-audio.json`. El motor de audio no cambio en 1.0.4.
- `--check-vb-cable` y `--smoke-test` devuelven 0; el smoke test cerro el puente y termino sin dejar procesos.
- **Prueba global real** con `Ctrl+Alt+Shift+F11`: una activacion visible, una oculta y una minimizada, tres eventos totales y liberacion correcta. Resultado: `build/verification/hotkeys.json`.
- La interfaz se renderizo a 960x600 y 720x460, y el dialogo de configuracion se verifico con nombre, creador, atajo y donacion, sin solapamientos.
- PyInstaller e Inno Setup completaron correctamente con Qt Multimedia, FFmpeg y plugins de Windows.
- La documentacion de uso, compilacion y versionado se incorporo al instalador y al paquete fuente; el pipeline genero la carpeta de publicacion y comprobo sus hashes.

## Limites de la validacion

- La apertura del microfono y el paso de buffers por el mezclador estan comprobados. Confirmar que una voz humana y el clip son recibidos simultaneamente por otros participantes requiere una llamada real de Discord.
- Discord debe quedar seleccionado una vez en `CABLE Output`. Trollsound no modifica configuraciones privadas de Discord, pulsar-para-hablar, supresion de ruido ni puertas de ruido.
- Con altavoces, el microfono puede recapturar acusticamente el clip monitorizado; se recomiendan auriculares.
- No se dispuso de Windows 10 ni de una cuenta o VM completamente limpia. El bundle se ejecuto con su interprete incluido en Windows 11.
- El instalador 1.0.4 se compilo correctamente, pero no se completo una nueva instalacion elevada aislada en esta ronda. Una version anterior cubrio instalacion, ejecucion y desinstalacion.
- Algunos juegos elevados o antitrampas pueden bloquear o reservar combinaciones.

## Reproducir

- Pruebas: `.\.venv\Scripts\python.exe -m pytest -q`.
- Atajos globales: `.\.venv\Scripts\python.exe -m scripts.verify_hotkeys`.
- Mezcla y formatos reales: `.\.venv\Scripts\python.exe -m scripts.verify_live`.
- Compilacion: `.\scripts\build.ps1`.
- Bundle: `Trollsound.exe --verify-audio RUTA_ABSOLUTA_A_BUILD_VERIFICATION`.

El instalador es sin firma y Windows puede mostrar SmartScreen y UAC.
