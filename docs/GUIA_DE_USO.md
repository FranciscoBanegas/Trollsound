# Guia de uso de Trollsound 1.0.3

## Que hace Trollsound

Trollsound mezcla continuamente el microfono predeterminado de Windows con los clips asignados a macros y envia el resultado a VB-Cable:

```text
Microfono de Windows + clip de macro -> CABLE Input -> CABLE Output -> Discord o juego
```

La voz sigue pasando aunque no haya ningun clip. La escucha local reproduce solamente el clip en los auriculares o altavoces predeterminados; nunca reproduce directamente el microfono.

## Requisitos

- Windows 10 version 2004 o posterior, o Windows 11, ambos x64.
- VB-Cable de VB-Audio instalado y un reinicio posterior a la instalacion del controlador.
- Un microfono predeterminado habilitado en Windows.
- Auriculares recomendados para evitar que el microfono vuelva a captar los clips.

No es necesario instalar Python para usar el instalador.

## Instalacion

1. Ejecuta `Trollsound-Setup-v1.0.3-x64.exe` como administrador.
2. Si SmartScreen aparece porque el instalador no esta firmado, revisa que el SHA-256 coincida con `SHA256SUMS.txt`, selecciona **Mas informacion** y luego **Ejecutar de todas formas**.
3. Si VB-Cable no esta listo, acepta abrir el flujo oficial de VB-Audio. Completa su asistente visible y reinicia Windows.
4. Vuelve a abrir Trollsound despues del reinicio.

Trollsound no incluye ni redistribuye el controlador de VB-Cable. Desinstalar Trollsound tampoco elimina VB-Cable, la configuracion ni la biblioteca de audios.

## Configuracion inicial

1. En Windows, deja tu microfono fisico como dispositivo de entrada predeterminado.
2. En Trollsound, selecciona `CABLE Input (VB-Audio Virtual Cable)` en el selector de cable.
3. Comprueba que el nombre de tu microfono aparezca en el estado del puente.
4. Pulsa **Probar conexion**. El diagnostico usa solo el cable y muestra el nombre exacto de la entrada emparejada.
5. En Discord, juego o aplicacion de voz, selecciona una sola vez `CABLE Output` como microfono.

No selecciones `CABLE Output` como microfono predeterminado de Windows: Trollsound necesita capturar el microfono fisico y enviar la mezcla al cable. Tampoco selecciones `CABLE Input` como salida predeterminada, porque la escucha local debe ir a auriculares o altavoces.

## Crear y usar macros

1. Pulsa **Agregar**.
2. Escribe un nombre descriptivo.
3. Pulsa el control de combinacion y presiona los modificadores y la tecla principal. Se admiten `Ctrl`, `Alt` y `Shift` mas una tecla, y teclas de funcion independientes salvo `F12`.
4. Selecciona un archivo WAV, MP3, OGG o FLAC.
5. Guarda la macro.

El audio se copia a `%LOCALAPPDATA%\Trollsound\audio`; el original puede moverse o eliminarse despues. Una nueva macro interrumpe el clip anterior, pero el puente del microfono sigue activo. El boton de reproduccion permite probar una macro sin usar el atajo.

Windows reserva los atajos registrados para Trollsound. Si otra aplicacion ya posee una combinacion, la fila mostrara **Conflicto** y las demas macros continuaran funcionando. Algunos juegos elevados o sistemas antitrampas pueden bloquear atajos globales; prueba ejecutar ambas aplicaciones con el mismo nivel de privilegios antes de reasignar la macro.

## Volumenes

- **Microfono**: ganancia de la voz enviada a `CABLE Input`.
- **Sonido**: ganancia del clip enviado al juego o aplicacion de voz.
- **Escucha**: volumen del clip en la salida predeterminada de Windows.

Si la mezcla satura, baja primero **Microfono** y **Sonido**. La salida se limita para evitar desbordamientos, pero una suma demasiado alta puede sonar comprimida o distorsionada.

## Segundo plano y bandeja

Minimizar o cerrar la ventana mantiene Trollsound en la bandeja, conserva el puente del microfono y deja activos los atajos. Desde el icono de bandeja puedes abrir la ventana, pausar macros, detener el clip o salir.

- **Pausar macros** libera temporalmente los atajos y detiene el clip, pero mantiene la voz.
- **Detener audio** detiene solo el clip actual.
- **Salir** detiene el puente, libera los atajos y termina el proceso.

Si el sistema no ofrece bandeja, cerrar la ventana termina la aplicacion limpiamente.

## Estados de una macro

- **Registrada**: el atajo esta activo.
- **Desactivada**: la macro fue deshabilitada por el usuario.
- **Pausada**: todas las macros estan pausadas.
- **Conflicto**: Windows no pudo reservar esa combinacion.
- **Combinacion incompatible**: debe editarse y asignarse de nuevo.
- **Audio ausente**: falta la copia administrada del archivo.

La desaparicion del cable o un fallo del microfono detiene la mezcla y desregistra las macros. Trollsound nunca sustituye VB-Cable por una salida fisica.

## Solucion de problemas

### Se oye el clip localmente, pero no llega a Discord

Confirma que Trollsound tenga seleccionado `CABLE Input`, que el puente figure activo y que Discord use `CABLE Output` como entrada. Revisa tambien pulsar-para-hablar, puerta de ruido y supresion de ruido.

### El clip llega a Discord, pero yo no lo oigo

Comprueba que Windows tenga unos auriculares o altavoces fisicos como salida predeterminada y sube **Escucha**. Si la salida predeterminada coincide con VB-Cable, Trollsound omite el monitor para evitar un bucle.

### Los demas oyen el clip, pero no mi voz

Selecciona el microfono fisico correcto como entrada predeterminada de Windows, concede permiso de microfono a aplicaciones de escritorio y reinicia Trollsound. No uses `CABLE Output` como entrada predeterminada de Windows.

### Hay eco o el clip se reproduce dos veces

Usa auriculares. No actives la opcion de Windows **Escuchar este dispositivo** para VB-Cable y evita monitorizar `CABLE Output` con otra aplicacion.

### El atajo no responde

Mira el estado de la macro. Cambia las combinaciones en conflicto, evita `F12` y prueba con Trollsound y el juego al mismo nivel de privilegios. La activacion sucede al presionar y no se repite por mantener la tecla pulsada.

### Donde estan los datos

- Configuracion: `%LOCALAPPDATA%\Trollsound\config.json`
- Audios administrados: `%LOCALAPPDATA%\Trollsound\audio`
- Registro de diagnostico: `%LOCALAPPDATA%\Trollsound\trollsound.log`

La configuracion se escribe atomicamente. Una configuracion invalida se conserva para no perder la biblioteca; con Trollsound cerrado, renombrala para iniciar una configuracion nueva.
