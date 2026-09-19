# Trollsound

Macros de audio para Windows 10 (2004 o posterior) y Windows 11 x64.

Documentacion completa: [guia de uso](docs/GUIA_DE_USO.md), [compilacion y versionado](docs/COMPILACION_Y_VERSIONADO.md) y [notas de Trollsound 1.0.4](docs/RELEASE_NOTES_1.0.4.md).

## Uso

Ejecuta `Trollsound-Setup-x64.exe`. Si falta VB-Cable, acepta su descarga y completa el asistente de VB-Audio; reinicia Windows antes de reproducir. El instalador no contiene el controlador. La aplicacion funciona sin Python instalado.

Selecciona `CABLE Input (VB-Audio Virtual Cable)` en Trollsound y pulsa **Probar conexion**. Selecciona una sola vez el `CABLE Output` indicado como microfono dentro del juego o aplicacion de voz. Trollsound mantendra un puente continuo desde el microfono predeterminado de Windows y mezclara los sonidos encima de la voz, por lo que no es necesario alternar dispositivos para seguir hablando. Comprueba tambien permisos de microfono, pulsar-para-hablar y supresion de ruido del juego. No se cambian los dispositivos predeterminados de Windows.

Agrega una macro con nombre, combinacion y archivo WAV, MP3, OGG o FLAC. El archivo se valida y copia a `%LOCALAPPDATA%\Trollsound\audio`. Al activarse, el clip reemplaza al anterior sin cortar el microfono. Hay volumen independiente para voz, sonido enviado al juego y escucha local. La escucha local contiene solo el clip, nunca el microfono; usa auriculares para evitar que el microfono vuelva a captar el sonido de los altavoces. Windows reserva cada combinacion para Trollsound y la activa al presionarla, sin repeticion por mantenerla pulsada. Cerrar la ventana la deja en la bandeja y tanto el puente como los atajos siguen activos; **Salir** los libera. No hay arranque automatico con Windows.

En **Configuracion** se muestra el nombre del programa, la version, el creador y el acceso para donar mediante Cafecito. Alli tambien puede asignarse una combinacion global para **Detener audio**; corta solamente el clip en reproduccion y mantiene abierto el microfono.

La pausa libera temporalmente los atajos y detiene clips, pero mantiene el paso del microfono. El boton de reproduccion sigue disponible para una prueba manual. La columna Estado muestra si cada macro esta registrada, pausada, desactivada, en conflicto o necesita otra combinacion. Si falla el microfono o se desconecta el cable, la mezcla y las macros se detienen para impedir una ruta incompleta.

La configuracion versionada se guarda atomicamente en `%LOCALAPPDATA%\Trollsound\config.json`; la version 4 conserva los tres volumenes y el atajo de detencion, y migra automaticamente configuraciones anteriores. Los errores inesperados quedan en `trollsound.log`. Una configuracion invalida se conserva sin sobrescribirla. Repara o renombra ese archivo con la aplicacion cerrada para recuperar la biblioteca. Desinstalar conserva los audios, la configuracion y VB-Cable.

## Compilacion

Requiere Python 3.12 x64 e Inno Setup 6.7.3 en Windows. Ejecuta:

```powershell
.\scripts\build.ps1 -Python 'C:\ruta\python.exe' -InnoCompiler 'C:\ruta\ISCC.exe'
```

Las dependencias estan fijadas en `requirements-build.txt`. El resultado queda en `dist\Trollsound-Setup-x64.exe`; el bundle portatil `dist\Trollsound` debe conservarse completo. La entrega para publicar queda en `release\Trollsound-v1.0.4`. El instalador es sin firma; Windows puede mostrar SmartScreen. No se incluye un certificado privado.

Para desarrollo: `.\.venv\Scripts\python.exe launcher.py`. Pruebas: `.\.venv\Scripts\python.exe -m pytest -q`.

## Diagnostico para instaladores

`Trollsound.exe --check-vb-cable` devuelve 0 si existe un par activo, 10 si falta, 11 si esta presente pero no disponible o no puede verificarse. La comprobacion no reproduce audio: **Probar conexion** valida la ruta efectiva. `--install-vb-cable` abre el asistente compartido y devuelve 20 si se detecto el controlador tras ejecutar su instalador (requiere reinicio), 12 si se cancelo y 13 si fallo. Un codigo de deteccion correcto no confirma que el juego haya seleccionado la entrada correcta.

El paquete oficial se fija por URL y SHA-256 en `trollsound/installer.py`. Una modificacion del paquete causa un error cerrado; para actualizarlo, verificar el archivo oficial, revisar el cambio y actualizar el hash. Se rechazan archivos extraidos fuera de la carpeta temporal y descargas mayores a 20 MB.

Para comprobar los codecs del ejecutable empaquetado, genera las muestras con `python -m scripts.verify_live` y ejecuta `Trollsound.exe --verify-audio RUTA_ABSOLUTA_A_BUILD_VERIFICATION`. Este modo explicito envia los cuatro archivos `tone.*` por VB-Cable y por la escucha local, captura la senal del extremo virtual y escribe `bundle-audio.json` con el dispositivo de monitor utilizado. No cambia la biblioteca del usuario.

## Verificacion manual de entrega

- Instalar en Windows limpio sin Python, con y sin VB-Cable; probar el rechazo de instalacion, UAC cancelado, red desconectada, reinicio y desinstalacion.
- Probar la conexion y los cuatro formatos con un receptor que grabe CABLE Output. Confirmar que los altavoces fisicos no reciben audio.
- Cambiar el dispositivo predeterminado y desconectar/deshabilitar VB-Cable durante un clip; comprobar parada y ausencia de fallback.
- Probar combinaciones desde otra aplicacion, pausa, bandeja, edicion, eliminacion y reinicio de Trollsound.
- Verificar Windows 10 y 11 x64; comprobar escalado 100%, 150% y 200%.

Consulta `VALIDATION.md` para los resultados efectivamente ejecutados, separados de esta lista de aceptacion.
