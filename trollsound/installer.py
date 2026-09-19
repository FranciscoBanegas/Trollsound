from __future__ import annotations

import ctypes
from ctypes import wintypes
import hashlib
from pathlib import Path
import tempfile
import urllib.request
import zipfile

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout

from .devices import native_endpoints

DRIVER_URL = "https://download.vb-audio.com/Download_CABLE/VBCABLE_Driver_Pack45.zip"
DRIVER_SHA256 = "b950e39f01af1d04ea623c8f6d8eb9b6ea5c477c637295fabf20631c85116bfb"


def download_driver(destination, progress=lambda _: None):
    digest = hashlib.sha256()
    request = urllib.request.Request(DRIVER_URL, headers={"User-Agent": "Trollsound/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response, destination.open("wb") as output:
        if not response.url.startswith("https://download.vb-audio.com/"):
            raise ValueError("La descarga redirigio fuera del servidor oficial")
        size = 0
        while chunk := response.read(65536):
            size += len(chunk)
            if size > 20 * 1024 * 1024:
                raise ValueError("El paquete supera el tamano previsto")
            output.write(chunk)
            digest.update(chunk)
            progress(f"Descargando VB-Cable: {size // 1024} KB")
    if digest.hexdigest() != DRIVER_SHA256:
        raise ValueError("El paquete no coincide con la version verificada. No se ejecutara.")


def extract_driver(archive, destination):
    with zipfile.ZipFile(archive) as package:
        if sum(member.file_size for member in package.infolist()) > 50 * 1024 * 1024:
            raise ValueError("Paquete demasiado grande")
        for member in package.infolist():
            target = (destination / member.filename).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise ValueError("El paquete contiene una ruta no valida")
        package.extractall(destination)
    setup = destination / "VBCABLE_Setup_x64.exe"
    if not setup.is_file():
        raise ValueError("No se encontro el instalador x64")
    return setup


def run_elevated(setup):
    class ShellExecuteInfo(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("fMask", wintypes.ULONG),
                    ("hwnd", wintypes.HWND), ("lpVerb", wintypes.LPCWSTR),
                    ("lpFile", wintypes.LPCWSTR), ("lpParameters", wintypes.LPCWSTR),
                    ("lpDirectory", wintypes.LPCWSTR), ("nShow", ctypes.c_int),
                    ("hInstApp", wintypes.HINSTANCE), ("lpIDList", ctypes.c_void_p),
                    ("lpClass", wintypes.LPCWSTR), ("hkeyClass", wintypes.HKEY),
                    ("dwHotKey", wintypes.DWORD), ("hIcon", wintypes.HANDLE),
                    ("hProcess", wintypes.HANDLE)]
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    shell.ShellExecuteExW.argtypes = [ctypes.POINTER(ShellExecuteInfo)]
    shell.ShellExecuteExW.restype = wintypes.BOOL
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    info = ShellExecuteInfo()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = 0x40 | 0x100  # Keep process handle and report errors instead of shell dialogs.
    info.lpVerb = "runas"
    info.lpFile = str(setup)
    info.lpDirectory = str(setup.parent)
    info.nShow = 1
    if not shell.ShellExecuteExW(ctypes.byref(info)):
        raise ctypes.WinError(ctypes.get_last_error())
    if not info.hProcess:
        raise OSError("No se pudo supervisar el instalador del controlador")
    try:
        kernel.WaitForSingleObject(info.hProcess, 0xFFFFFFFF)
        code = wintypes.DWORD()
        if not kernel.GetExitCodeProcess(info.hProcess, ctypes.byref(code)):
            raise ctypes.WinError(ctypes.get_last_error())
        return code.value
    finally:
        kernel.CloseHandle(info.hProcess)


class InstallWorker(QThread):
    progress = pyqtSignal(str)
    result = pyqtSignal(bool, str)

    def run(self):
        try:
            with tempfile.TemporaryDirectory(prefix="Trollsound-VBCable-") as folder:
                root = Path(folder)
                archive = root / "driver.zip"
                download_driver(archive, self.progress.emit)
                setup = extract_driver(archive, root / "driver")
                self.progress.emit("Completa el asistente de VB-Audio y luego cierralo.")
                code = run_elevated(setup)
                if code not in (0, 3010):
                    raise OSError(f"El instalador devolvio el codigo {code}")
                if not native_endpoints():
                    raise OSError("El controlador no se detecta. Si lo instalaste, reinicia Windows y vuelve a comprobar.")
            self.result.emit(True, "VB-Cable detectado. Reinicia Windows antes de usar Trollsound.")
        except Exception as exc:
            self.result.emit(False, f"No se pudo completar la instalacion: {exc}")


class InstallDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Instalar VB-Cable")
        self.setMinimumWidth(500)
        self.code = 12
        self.worker = None
        layout = QVBoxLayout(self)
        self.label = QLabel("VB-Cable es un controlador de VB-Audio. Se descargara desde su sitio oficial "
                            "y se abrira su asistente con permisos de administrador. "
                            "La instalacion requiere reiniciar Windows.")
        self.label.setWordWrap(True)
        layout.addWidget(self.label)
        link = QLabel('<a href="https://vb-audio.com/Cable/">VB-Audio: licencia, descarga y donaciones</a>')
        link.setOpenExternalLinks(True)
        layout.addWidget(link)
        self.install = QPushButton("Descargar e instalar VB-Cable")
        self.install.clicked.connect(self.start)
        layout.addWidget(self.install)
        self.close_button = QPushButton("Ahora no")
        self.close_button.clicked.connect(self.reject)
        layout.addWidget(self.close_button)

    def start(self):
        self.install.setEnabled(False)
        self.close_button.setEnabled(False)
        self.worker = InstallWorker(self)
        self.worker.progress.connect(self.label.setText)
        self.worker.result.connect(self.result)
        self.worker.finished.connect(self.finished_work)
        self.worker.start()

    def result(self, success, message):
        self.code = 20 if success else 13
        self.label.setText(message)

    def finished_work(self):
        self.install.setEnabled(self.code != 20)
        self.close_button.setText("Cerrar")
        self.close_button.setEnabled(True)

    def reject(self):
        if not self.worker or not self.worker.isRunning():
            super().reject()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            event.ignore()
        else:
            event.accept()


def offer_install(parent=None):
    dialog = InstallDialog(parent)
    dialog.exec()
    return dialog.code
