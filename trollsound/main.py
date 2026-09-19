import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys

from PyQt6.QtCore import QLockFile, QTimer, Qt
from PyQt6.QtWidgets import QApplication, QMessageBox

from .devices import Devices


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Trollsound")
    app.setOrganizationName("Trollsound")
    app.setQuitOnLastWindowClosed(True)
    if "--check-vb-cable" in sys.argv:
        devices = Devices()
        code = devices.check_code()
        if sys.stdout:
            print(json.dumps({"code": code, "outputs": list(devices.outputs), "error": devices.error}))
        return code
    if "--install-vb-cable" in sys.argv:
        from .installer import offer_install
        return offer_install()
    if "--verify-audio" in sys.argv:
        from .verification import verify_bundle
        index = sys.argv.index("--verify-audio")
        if len(sys.argv) <= index + 1:
            return 2
        return verify_bundle(Devices(), sys.argv[index + 1])
    root = Path(os.environ["LOCALAPPDATA"]) / "Trollsound"
    root.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(root / "instance.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        QMessageBox.information(None, "Trollsound", "Trollsound ya esta abierto. Buscalo en la bandeja de Windows.")
        return 0
    handler = RotatingFileHandler(root / "trollsound.log", maxBytes=1024 * 1024, backupCount=2, encoding="utf-8")
    logging.basicConfig(handlers=[handler], level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    def exception_hook(kind, value, trace):
        logging.error("Error no controlado", exc_info=(kind, value, trace))
        QMessageBox.critical(None, "Trollsound", f"Error: {value}")

    sys.excepthook = exception_hook
    from .ui import Window
    from .theme import apply_theme
    apply_theme(app)
    window = Window()
    app.aboutToQuit.connect(window.cleanup)
    window.show()
    if "--smoke-test" in sys.argv:
        QTimer.singleShot(1000, window.shutdown)
    result = app.exec()
    lock.unlock()
    return result
