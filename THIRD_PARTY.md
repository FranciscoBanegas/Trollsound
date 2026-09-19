# Dependencias y distribucion

Trollsound usa PyQt6 (GPL v3 o licencia comercial de Riverbank), Qt 6 (LGPL/GPL o licencia comercial), Python (PSF) y el bootloader de PyInstaller (GPL con excepcion de distribucion). Las bibliotecas FFmpeg de Qt se distribuyen dinamicamente. Los atajos usan la API nativa de Windows; no se incluyen keyboard ni playsound.

Esta entrega incluye el codigo fuente de Trollsound y los scripts de construccion junto al instalador. Para redistribuir, conserva los avisos y cumple las licencias de PyQt6 y las bibliotecas incluidas. Una distribucion cerrada requiere resolver la licencia comercial de PyQt6.

Trollsound se entrega bajo GPL-3.0. Los textos completos de GPL, LGPL, Python, SIP y PyInstaller estan en licenses. Las bibliotecas dinamicas se conservan separadas en _internal/PyQt6/Qt6/bin y pueden reemplazarse por versiones compatibles. Los paquetes fuente de las versiones usadas estan disponibles en https://pypi.org/project/PyQt6/6.8.1/#files, https://download.qt.io/archive/qt/6.8/6.8.2/single/ y https://ffmpeg.org/releases/ (FFmpeg 7.1). Para redistribucion publica, conservar tambien el acceso al codigo fuente correspondiente de las dependencias, sus parches y avisos aplicables.

Fuentes de licencias:

- https://www.riverbankcomputing.com/software/pyqt/intro
- https://doc.qt.io/qt-6/licensing.html
- https://doc.qt.io/qt-6/qtmultimedia-index.html#licenses-and-attributions
- https://pyinstaller.org/en/stable/license.html

VB-Cable pertenece a VB-Audio y no se incluye en los binarios ni en el archivo fuente. Se descarga del sitio oficial solo con consentimiento. Sus condiciones y donaciones estan en https://vb-audio.com/Cable/ y https://vb-audio.com/Services/licensing.htm. La desinstalacion de Trollsound no elimina el controlador compartido.
