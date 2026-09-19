"""Render the real Qt widgets with an isolated fixture library for layout review."""
from pathlib import Path
import tempfile
import wave

from PyQt6.QtWidgets import QApplication
from trollsound.audio import tone_pcm
from trollsound.devices import Devices
from trollsound.storage import Library
from trollsound.ui import Window, MacroDialog, SettingsDialog
from trollsound.hotkeys import Hotkeys
from trollsound.theme import apply_theme


def main():
    app = QApplication([])
    apply_theme(app)
    directory = Path("build/verification")
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        wav = root / "Saludos.wav"
        with wave.open(str(wav), "wb") as stream:
            stream.setnchannels(2)
            stream.setsampwidth(2)
            stream.setframerate(48000)
            stream.writeframes(tone_pcm())
        library = Library(root / "library")
        library.put("Saludos", "ctrl+alt+1", wav)
        library.put("Aplausos", "ctrl+alt+2", wav)
        window = Window(library)
        window.paused = True
        window.show()
        app.processEvents()
        window.grab().save(str(directory / "window.png"))
        window.resize(720, 460)
        app.processEvents()
        window.grab().save(str(directory / "window-small.png"))
        dialog = MacroDialog(library, window.hotkeys, library.macros[0], window)
        dialog.show()
        app.processEvents()
        dialog.grab().save(str(directory / "macro-dialog.png"))
        dialog.reject()
        settings = SettingsDialog(library, "Registrada", "Ctrl+Alt+X", window)
        settings.stop_combo.setText("Ctrl+Alt+X")
        settings.show()
        app.processEvents()
        settings.grab().save(str(directory / "settings-dialog.png"))
        settings.reject()
        window.quitting = True
        window.close()


if __name__ == "__main__":
    main()
