from __future__ import annotations

import json
import os
import shutil
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

EXTENSIONS = {".wav", ".mp3", ".ogg", ".flac"}


@dataclass
class Macro:
    id: str
    name: str
    hotkey: str
    audio: str
    enabled: bool = True


class Library:
    def __init__(self, root: Path | None = None):
        self.root = root or Path(os.environ["LOCALAPPDATA"]) / "Trollsound"
        self.audio_dir = self.root / "audio"
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self.config = self.root / "config.json"
        self.macros: list[Macro] = []
        self.selected_device_id = ""
        self.minimize_to_tray = True
        self.cable_volume = 80
        self.monitor_volume = 80
        self.microphone_volume = 100
        self.load_error = ""
        self.read_only = False
        self.load()

    def path(self, macro: Macro) -> Path:
        if Path(macro.audio).name != macro.audio or not macro.audio:
            raise ValueError("Ruta de audio no valida")
        path = self.audio_dir / macro.audio
        if not path.resolve().is_relative_to(self.audio_dir.resolve()):
            raise ValueError("El audio debe pertenecer a la biblioteca")
        return path

    def load(self):
        if not self.config.exists():
            return
        try:
            data = json.loads(self.config.read_text(encoding="utf-8"))
            if data.get("schema_version") not in (1, 2, 3):
                raise ValueError("Version de configuracion no compatible")
            macros = [Macro(**m) for m in data["macros"]]
            ids, hotkeys = set(), set()
            for macro in macros:
                if not all(isinstance(v, str) and v for v in
                           (macro.id, macro.name, macro.hotkey, macro.audio)):
                    raise ValueError("Macro incompleta")
                if type(macro.enabled) is not bool:
                    raise ValueError("Estado de macro no valido")
                self.path(macro)
                if macro.id in ids or macro.hotkey in hotkeys:
                    raise ValueError("Macros duplicadas")
                ids.add(macro.id)
                hotkeys.add(macro.hotkey)
            selected = data.get("selected_device_id", "")
            if not isinstance(selected, str):
                raise ValueError("Dispositivo no valido")
            self.macros = macros
            self.selected_device_id = selected
            self.minimize_to_tray = bool(data.get("minimize_to_tray", True))
            if data["schema_version"] in (2, 3):
                cable_volume = data.get("cable_volume", 80)
                monitor_volume = data.get("monitor_volume", 80)
                if (type(cable_volume) is not int or not 0 <= cable_volume <= 100 or
                        type(monitor_volume) is not int or not 0 <= monitor_volume <= 100):
                    raise ValueError("Volumen no valido")
                self.cable_volume = cable_volume
                self.monitor_volume = monitor_volume
            if data["schema_version"] == 3:
                microphone_volume = data.get("microphone_volume", 100)
                if type(microphone_volume) is not int or not 0 <= microphone_volume <= 100:
                    raise ValueError("Volumen de microfono no valido")
                self.microphone_volume = microphone_volume
        except (ValueError, TypeError, KeyError, OSError) as exc:
            self.load_error = f"No se pudo leer la biblioteca: {exc}. Se conserva el archivo original."
            self.read_only = True

    def save(self):
        if self.read_only:
            raise ValueError(self.load_error)
        data = dict(schema_version=3, selected_device_id=self.selected_device_id,
                    minimize_to_tray=self.minimize_to_tray,
                    cable_volume=self.cable_volume, monitor_volume=self.monitor_volume,
                    microphone_volume=self.microphone_volume,
                    macros=[asdict(m) for m in self.macros])
        temp = self.config.with_suffix(".tmp")
        try:
            with temp.open("w", encoding="utf-8") as stream:
                json.dump(data, stream, indent=2, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, self.config)
        finally:
            temp.unlink(missing_ok=True)

    def put(self, name: str, hotkey: str, source: Path, existing_id: str | None = None):
        if self.read_only:
            raise ValueError(self.load_error)
        if not name.strip() or not hotkey:
            raise ValueError("Completa el nombre y la combinacion")
        if any(m.hotkey == hotkey and m.id != existing_id for m in self.macros):
            raise ValueError("Esta combinacion ya pertenece a otra macro")
        if source.suffix.lower() not in EXTENSIONS or not source.is_file():
            raise ValueError("Selecciona un archivo WAV, MP3, OGG o FLAC existente")
        previous = next((m for m in self.macros if m.id == existing_id), None)
        audio = previous.audio if previous and source.resolve() == self.path(previous).resolve() else ""
        copied = not audio
        if copied:
            audio = uuid.uuid4().hex + source.suffix.lower()
            try:
                shutil.copyfile(source, self.audio_dir / audio)
            except OSError:
                (self.audio_dir / audio).unlink(missing_ok=True)
                raise
        macro = Macro(existing_id or uuid.uuid4().hex, name.strip(), hotkey, audio,
                      previous.enabled if previous else True)
        old = self.macros[:]
        if previous:
            self.macros[self.macros.index(previous)] = macro
        else:
            self.macros.append(macro)
        try:
            self.save()
        except Exception:
            self.macros = old
            if copied:
                (self.audio_dir / audio).unlink(missing_ok=True)
            raise
        if previous and copied:
            self._remove_unused(previous)
        return macro

    def _remove_unused(self, macro):
        if not any(m.audio == macro.audio for m in self.macros):
            try:
                self.path(macro).unlink(missing_ok=True)
            except OSError:
                pass  # An orphaned managed copy is safer than undoing a committed edit.

    def remove(self, macro_id):
        macro = next(m for m in self.macros if m.id == macro_id)
        old = self.macros[:]
        self.macros.remove(macro)
        try:
            self.save()
        except Exception:
            self.macros = old
            raise
        self._remove_unused(macro)

    def toggle(self, macro_id):
        macro = next(m for m in self.macros if m.id == macro_id)
        macro.enabled = not macro.enabled
        try:
            self.save()
        except Exception:
            macro.enabled = not macro.enabled
            raise
