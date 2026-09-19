# Trollsound 1.0.5

## Novedades

- Exportacion portable de todas las macros desde **Configuracion**.
- Cada paquete ZIP conserva nombres, combinaciones, estados, identificadores y sonidos.
- El atajo global de **Detener audio** tambien se incluye en la copia.
- Importacion con validacion de estructura, rutas, tamaños y hashes SHA-256 antes de reemplazar la biblioteca.
- Reemplazo transaccional: un paquete invalido o un fallo de guardado mantiene intactos los atajos existentes.
- La importacion conserva los ajustes locales de VB-Cable, microfono, volumenes y bandeja.

## Formato portable

El ZIP contiene un `manifest.json` con version de formato independiente y una carpeta `audio` con una sola copia de cada sonido referenciado. Puede trasladarse a otro equipo sin conservar los archivos originales ni sus rutas.

## Descargas

- `Trollsound-Setup-v1.0.5-x64.exe`: instalador recomendado para Windows 10/11 x64.
- `Trollsound-1.0.5-source.zip`: fuentes y scripts reproducibles.
- `SHA256SUMS.txt`: hashes para comprobar integridad.

## Notas

Importar un paquete reemplaza las macros y el atajo global de detencion actuales despues de pedir confirmacion. Los demas ajustes permanecen locales.

VB-Cable no se incluye en el instalador. Si falta, Trollsound ofrece abrir la descarga e instalacion oficial. El instalador de Trollsound no esta firmado, por lo que Windows puede mostrar SmartScreen.
