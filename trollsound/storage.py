from __future__ import annotations

import json
import hashlib
import os
import shutil
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile

from . import __version__
from .hotkeys import normalize_hotkey

EXTENSIONS = {".wav", ".mp3", ".ogg", ".flac"}
PACKAGE_VERSION = 1
MANIFEST_NAME = "manifest.json"
MANIFEST_LIMIT = 1024 * 1024


@dataclass
class Macro:
    id: str
    name: str
    hotkey: str
    audio: str
    enabled: bool = True


@dataclass(frozen=True)
class PackageSummary:
    macro_count: int
    stop_hotkey: str


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
        self.stop_hotkey = ""
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
            if data.get("schema_version") not in (1, 2, 3, 4):
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
            if data["schema_version"] in (2, 3, 4):
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
            if data["schema_version"] == 4:
                microphone_volume = data.get("microphone_volume", 100)
                stop_hotkey = data.get("stop_hotkey", "")
                if type(microphone_volume) is not int or not 0 <= microphone_volume <= 100:
                    raise ValueError("Volumen de microfono no valido")
                if not isinstance(stop_hotkey, str) or stop_hotkey in hotkeys:
                    raise ValueError("Atajo de detencion no valido o duplicado")
                self.microphone_volume = microphone_volume
                self.stop_hotkey = stop_hotkey
        except (ValueError, TypeError, KeyError, OSError) as exc:
            self.load_error = f"No se pudo leer la biblioteca: {exc}. Se conserva el archivo original."
            self.read_only = True

    def save(self):
        if self.read_only:
            raise ValueError(self.load_error)
        data = dict(schema_version=4, selected_device_id=self.selected_device_id,
                    minimize_to_tray=self.minimize_to_tray,
                    cable_volume=self.cable_volume, monitor_volume=self.monitor_volume,
                    microphone_volume=self.microphone_volume,
                    stop_hotkey=self.stop_hotkey,
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

    @staticmethod
    def _digest(path: Path) -> tuple[int, str]:
        size = 0
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                size += len(chunk)
                digest.update(chunk)
        return size, digest.hexdigest()

    @staticmethod
    def _safe_member(name: str) -> bool:
        path = PurePosixPath(name)
        return (bool(name) and "\\" not in name and ":" not in name and not path.is_absolute()
                and all(part not in ("", ".", "..") for part in path.parts))

    @staticmethod
    def _canonical_hotkey(value: str, field: str) -> str:
        if not isinstance(value, str) or not value:
            raise ValueError(f"{field} no valido")
        try:
            return normalize_hotkey(value)
        except ValueError as exc:
            raise ValueError(f"{field} no valido: {exc}") from exc

    def export_package(self, destination: Path):
        destination = Path(destination)
        if not destination.parent.is_dir():
            raise ValueError("La carpeta de destino no existe")
        temp = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
        audio_files: dict[str, dict] = {}
        audio_refs: dict[str, str] = {}
        package_macros = []
        try:
            for macro in self.macros:
                source = self.path(macro)
                if not source.is_file():
                    raise ValueError(f"Falta el audio de la macro {macro.name}")
                if macro.audio not in audio_refs:
                    size, digest = self._digest(source)
                    archive_path = f"audio/{digest}{source.suffix.lower()}"
                    audio_refs[macro.audio] = archive_path
                    audio_files.setdefault(archive_path, {
                        "path": archive_path,
                        "size": size,
                        "sha256": digest,
                        "source": source,
                    })
                package_macros.append({
                    "id": macro.id,
                    "name": macro.name,
                    "hotkey": macro.hotkey,
                    "audio": audio_refs[macro.audio],
                    "enabled": macro.enabled,
                })
            manifest = {
                "package_version": PACKAGE_VERSION,
                "app_version": __version__,
                "stop_hotkey": self.stop_hotkey,
                "macros": package_macros,
                "audio_files": [
                    {key: value[key] for key in ("path", "size", "sha256")}
                    for value in audio_files.values()
                ],
            }
            with ZipFile(temp, "w", ZIP_DEFLATED) as archive:
                archive.writestr(MANIFEST_NAME, json.dumps(
                    manifest, indent=2, ensure_ascii=False).encode("utf-8"))
                for value in audio_files.values():
                    archive.write(value["source"], value["path"])
            self.inspect_package(temp)
            os.replace(temp, destination)
        except (OSError, BadZipFile) as exc:
            raise ValueError(f"No se pudo exportar el paquete: {exc}") from exc
        finally:
            temp.unlink(missing_ok=True)

    def _load_package(self, source: Path) -> dict:
        source = Path(source)
        if not source.is_file():
            raise ValueError("El paquete seleccionado no existe")
        try:
            with ZipFile(source, "r") as archive:
                infos = archive.infolist()
                names = [info.filename for info in infos]
                if len(names) != len(set(names)):
                    raise ValueError("El paquete contiene entradas duplicadas")
                for info in infos:
                    kind = (info.external_attr >> 16) & 0o170000
                    if (info.is_dir() or info.flag_bits & 0x1 or kind == 0o120000
                            or not self._safe_member(info.filename)):
                        raise ValueError("El paquete contiene una ruta no segura")
                if MANIFEST_NAME not in names:
                    raise ValueError("El paquete no contiene manifest.json")
                manifest_info = archive.getinfo(MANIFEST_NAME)
                if manifest_info.file_size > MANIFEST_LIMIT:
                    raise ValueError("El manifiesto es demasiado grande")
                try:
                    manifest = json.loads(archive.read(manifest_info).decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise ValueError("El manifiesto JSON no es valido") from exc
                self._validate_manifest(manifest, archive, set(names))
                return manifest
        except BadZipFile as exc:
            raise ValueError("El archivo no es un paquete ZIP valido") from exc
        except (RuntimeError, NotImplementedError) as exc:
            raise ValueError(f"El paquete usa una compresion no compatible: {exc}") from exc
        except OSError as exc:
            raise ValueError(f"No se pudo leer el paquete: {exc}") from exc

    def _validate_manifest(self, manifest: dict, archive: ZipFile, names: set[str]):
        if not isinstance(manifest, dict) or manifest.get("package_version") != PACKAGE_VERSION:
            raise ValueError("Version de paquete no compatible")
        if not isinstance(manifest.get("app_version"), str):
            raise ValueError("Version de aplicacion no valida")
        macros = manifest.get("macros")
        audio_files = manifest.get("audio_files")
        stop_hotkey = manifest.get("stop_hotkey")
        if not isinstance(macros, list) or not isinstance(audio_files, list):
            raise ValueError("Estructura de paquete no valida")
        if not isinstance(stop_hotkey, str):
            raise ValueError("Atajo de detencion no valido")

        metadata = {}
        for item in audio_files:
            if not isinstance(item, dict):
                raise ValueError("Metadatos de audio no validos")
            path = item.get("path")
            size = item.get("size")
            digest = item.get("sha256")
            if (not isinstance(path, str) or not path.startswith("audio/")
                    or not self._safe_member(path) or Path(path).suffix.lower() not in EXTENSIONS
                    or type(size) is not int or size < 0
                    or not isinstance(digest, str) or len(digest) != 64
                    or any(char not in "0123456789abcdef" for char in digest)):
                raise ValueError("Metadatos de audio no validos")
            if path in metadata:
                raise ValueError("El manifiesto contiene audios duplicados")
            metadata[path] = item

        ids, hotkeys, referenced = set(), set(), set()
        for item in macros:
            if not isinstance(item, dict):
                raise ValueError("Macro importada no valida")
            macro_id = item.get("id")
            name = item.get("name")
            hotkey = item.get("hotkey")
            audio = item.get("audio")
            enabled = item.get("enabled")
            if (not isinstance(macro_id, str) or not macro_id
                    or not isinstance(name, str) or not name.strip()
                    or not isinstance(audio, str) or type(enabled) is not bool):
                raise ValueError("Macro importada no valida")
            canonical = self._canonical_hotkey(hotkey, "Combinacion de macro")
            if macro_id in ids or canonical in hotkeys:
                raise ValueError("El paquete contiene macros duplicadas")
            if audio not in metadata:
                raise ValueError("Una macro referencia un audio ausente")
            ids.add(macro_id)
            hotkeys.add(canonical)
            referenced.add(audio)

        if stop_hotkey:
            canonical_stop = self._canonical_hotkey(stop_hotkey, "Atajo de detencion")
            if canonical_stop in hotkeys:
                raise ValueError("El atajo de detencion coincide con una macro")
        if referenced != set(metadata):
            raise ValueError("El paquete contiene audios sin referencia")
        if names != {MANIFEST_NAME, *metadata}:
            raise ValueError("El paquete contiene archivos no declarados")

        for path, item in metadata.items():
            info = archive.getinfo(path)
            if info.file_size != item["size"]:
                raise ValueError(f"El tamaño de {path} no coincide")
            size = 0
            digest = hashlib.sha256()
            with archive.open(info, "r") as stream:
                while chunk := stream.read(1024 * 1024):
                    size += len(chunk)
                    digest.update(chunk)
            if size != item["size"] or digest.hexdigest() != item["sha256"]:
                raise ValueError(f"La integridad de {path} no coincide")

    def inspect_package(self, source: Path) -> PackageSummary:
        manifest = self._load_package(source)
        return PackageSummary(len(manifest["macros"]), manifest["stop_hotkey"])

    def import_package(self, source: Path):
        if self.read_only:
            raise ValueError(self.load_error)
        source = Path(source)
        manifest = self._load_package(source)
        targets: dict[str, str] = {}
        created: list[Path] = []
        temp_files: list[Path] = []
        metadata = {item["path"]: item for item in manifest["audio_files"]}
        try:
            with ZipFile(source, "r") as archive:
                for archive_path, item in metadata.items():
                    filename = uuid.uuid4().hex + Path(archive_path).suffix.lower()
                    destination = self.audio_dir / filename
                    temp = destination.with_suffix(destination.suffix + ".tmp")
                    temp_files.append(temp)
                    size = 0
                    digest = hashlib.sha256()
                    with archive.open(archive_path, "r") as input_stream, temp.open("wb") as output:
                        while chunk := input_stream.read(1024 * 1024):
                            size += len(chunk)
                            digest.update(chunk)
                            output.write(chunk)
                        output.flush()
                        os.fsync(output.fileno())
                    if size != item["size"] or digest.hexdigest() != item["sha256"]:
                        raise ValueError(f"La integridad de {archive_path} cambio durante la importacion")
                    os.replace(temp, destination)
                    created.append(destination)
                    targets[archive_path] = filename

            imported = [Macro(item["id"], item["name"], item["hotkey"],
                              targets[item["audio"]], item["enabled"])
                        for item in manifest["macros"]]
            previous_macros = self.macros
            previous_stop = self.stop_hotkey
            self.macros = imported
            self.stop_hotkey = manifest["stop_hotkey"]
            try:
                self.save()
            except Exception:
                self.macros = previous_macros
                self.stop_hotkey = previous_stop
                raise
            imported_audio = {macro.audio for macro in imported}
            for audio in {macro.audio for macro in previous_macros} - imported_audio:
                try:
                    (self.audio_dir / audio).unlink(missing_ok=True)
                except OSError:
                    pass
        except BadZipFile as exc:
            raise ValueError("El archivo dejo de ser un paquete ZIP valido") from exc
        except (RuntimeError, NotImplementedError) as exc:
            raise ValueError(f"El paquete usa una compresion no compatible: {exc}") from exc
        except OSError as exc:
            raise ValueError(f"No se pudo importar el paquete: {exc}") from exc
        finally:
            for path in temp_files:
                path.unlink(missing_ok=True)
            if 'imported' not in locals() or self.macros is not imported:
                for path in created:
                    path.unlink(missing_ok=True)

    def put(self, name: str, hotkey: str, source: Path, existing_id: str | None = None):
        if self.read_only:
            raise ValueError(self.load_error)
        if not name.strip() or not hotkey:
            raise ValueError("Completa el nombre y la combinacion")
        if any(m.hotkey == hotkey and m.id != existing_id for m in self.macros):
            raise ValueError("Esta combinacion ya pertenece a otra macro")
        if hotkey == self.stop_hotkey:
            raise ValueError("Esta combinacion se usa para detener el audio")
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

    def set_stop_hotkey(self, hotkey: str):
        if self.read_only:
            raise ValueError(self.load_error)
        if hotkey and any(m.hotkey == hotkey for m in self.macros):
            raise ValueError("Esta combinacion ya pertenece a una macro")
        previous = self.stop_hotkey
        self.stop_hotkey = hotkey
        try:
            self.save()
        except Exception:
            self.stop_hotkey = previous
            raise

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
