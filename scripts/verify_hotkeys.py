"""Exercise RegisterHotKey while its Qt window is visible, hidden and minimized."""
import ctypes
import json
from pathlib import Path
import subprocess
import sys

from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication, QLabel

from trollsound.hotkeys import Hotkeys
from trollsound.storage import Macro

COMBINATION = "Ctrl+Alt+Shift+F11"
VK_CONTROL, VK_MENU, VK_SHIFT, VK_F11 = 0x11, 0x12, 0x10, 0x7A
KEYEVENTF_KEYUP = 0x0002


def sender():
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    for key in (VK_CONTROL, VK_MENU, VK_SHIFT, VK_F11):
        user32.keybd_event(key, 0, 0, 0)
    for key in (VK_F11, VK_SHIFT, VK_MENU, VK_CONTROL):
        user32.keybd_event(key, 0, KEYEVENTF_KEYUP, 0)
    return 0


def wait_for_sender(app, events):
    before = len(events)
    child = subprocess.Popen([sys.executable, "-m", "scripts.verify_hotkeys", "--sender"])
    loop = QEventLoop()
    timer = QTimer()
    timer.setInterval(50)
    timer.timeout.connect(lambda: loop.quit() if child.poll() is not None and len(events) > before else None)
    timer.start()
    QTimer.singleShot(3000, loop.quit)
    loop.exec()
    child.wait(timeout=5)
    app.processEvents()
    return child.returncode == 0 and len(events) == before + 1


def main():
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    window = QLabel("Ventana aislada para verificar atajos de Trollsound")
    window.setWindowTitle("Trollsound - Verificacion de atajos")
    window.resize(480, 100)
    hooks = Hotkeys()
    hooks.set_window(int(window.winId()))
    events = []
    hooks.triggered.connect(lambda macro_id, generation: events.append((macro_id, generation)))
    hooks.register([Macro("test", "Prueba", COMBINATION, "unused.wav")])
    results = {}
    window.show()
    app.processEvents()
    results["visible"] = wait_for_sender(app, events)
    window.hide()
    app.processEvents()
    results["hidden"] = wait_for_sender(app, events)
    window.showMinimized()
    app.processEvents()
    results["minimized"] = wait_for_sender(app, events)
    generation = hooks.generation
    hooks.clear()
    results["released"] = not hooks.handles and hooks.generation != generation
    hooks.close()
    results["events"] = len(events)
    results["passed"] = all(results[name] for name in ("visible", "hidden", "minimized", "released"))
    path = Path("build/verification/hotkeys.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results))
    return 0 if results["passed"] else 1


if __name__ == "__main__":
    sys.exit(sender() if "--sender" in sys.argv else main())
