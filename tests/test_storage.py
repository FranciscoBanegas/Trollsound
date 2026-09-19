import json
import hashlib
import os
import zipfile
from pathlib import Path
import pytest
from trollsound.storage import Library, Macro


def test_import_survives_original_deleted_and_persists(tmp_path, wav):
    lib = Library(tmp_path / "library")
    macro = lib.put("Hola", "ctrl+alt+1", wav)
    wav.unlink()
    restored = Library(lib.root)
    assert restored.macros == [macro]
    assert restored.path(macro).is_file()
    restored.remove(macro.id)
    assert not restored.path(macro).exists()
    assert not Library(lib.root).macros


def test_duplicate_rejected_edit_keeps_id(tmp_path, wav):
    lib = Library(tmp_path / "library")
    first = lib.put("Uno", "ctrl+1", wav)
    with pytest.raises(ValueError):
        lib.put("Dos", "ctrl+1", wav)
    edited = lib.put("Editada", "ctrl+2", lib.path(first), first.id)
    assert edited.id == first.id and edited.audio == first.audio
    lib.toggle(first.id)
    assert not Library(lib.root).macros[0].enabled


def test_failed_save_rolls_back_import(tmp_path, wav, monkeypatch):
    lib = Library(tmp_path / "library")
    def fail(*args):
        raise OSError("disk full")
    monkeypatch.setattr("trollsound.storage.os.replace", fail)
    with pytest.raises(OSError):
        lib.put("Uno", "ctrl+1", wav)
    assert lib.macros == []
    assert list(lib.audio_dir.iterdir()) == []


@pytest.mark.parametrize("content", ['{', '{"schema_version": 99}', json.dumps({
    "schema_version": 1, "macros": [dict(id="a", name="x", hotkey="ctrl+1", audio="../outside.wav")]
})])
def test_corrupt_or_unsafe_config_is_preserved(tmp_path, content):
    (tmp_path / "config.json").write_text(content)
    lib = Library(tmp_path)
    assert lib.read_only and lib.load_error
    with pytest.raises(ValueError):
        lib.save()
    assert lib.config.read_text() == content


def test_missing_audio_does_not_destroy_macro(tmp_path, wav):
    lib = Library(tmp_path / "library")
    macro = lib.put("Uno", "ctrl+1", wav)
    lib.path(macro).unlink()
    assert len(Library(lib.root).macros) == 1


def test_schema_one_migrates_with_default_volumes(tmp_path):
    root = tmp_path / "library"
    root.mkdir()
    (root / "config.json").write_text(json.dumps({
        "schema_version": 1,
        "selected_device_id": "cable-id",
        "minimize_to_tray": False,
        "macros": [],
    }), encoding="utf-8")

    lib = Library(root)

    assert lib.selected_device_id == "cable-id"
    assert not lib.minimize_to_tray
    assert (lib.cable_volume, lib.monitor_volume, lib.microphone_volume) == (80, 80, 100)
    lib.cable_volume, lib.monitor_volume, lib.microphone_volume = 65, 35, 90
    lib.save()
    saved = json.loads(lib.config.read_text(encoding="utf-8"))
    assert saved["schema_version"] == 4
    assert (saved["cable_volume"], saved["monitor_volume"]) == (65, 35)
    assert saved["microphone_volume"] == 90
    restored = Library(root)
    assert (restored.cable_volume, restored.monitor_volume, restored.microphone_volume) == (65, 35, 90)


@pytest.mark.parametrize("field,value", [("cable_volume", -1), ("monitor_volume", 101),
                                          ("monitor_volume", True)])
def test_schema_two_rejects_invalid_volumes(tmp_path, field, value):
    data = {"schema_version": 2, "selected_device_id": "", "minimize_to_tray": True,
            "cable_volume": 80, "monitor_volume": 80, "macros": []}
    data[field] = value
    (tmp_path / "config.json").write_text(json.dumps(data), encoding="utf-8")
    assert Library(tmp_path).read_only


def test_schema_two_migrates_microphone_volume(tmp_path):
    data = {"schema_version": 2, "selected_device_id": "", "minimize_to_tray": True,
            "cable_volume": 70, "monitor_volume": 30, "macros": []}
    (tmp_path / "config.json").write_text(json.dumps(data), encoding="utf-8")
    lib = Library(tmp_path)
    assert (lib.cable_volume, lib.monitor_volume, lib.microphone_volume) == (70, 30, 100)
    assert lib.stop_hotkey == ""


@pytest.mark.parametrize("value", [-1, 101, True])
def test_schema_three_rejects_invalid_microphone_volume(tmp_path, value):
    data = {"schema_version": 3, "selected_device_id": "", "minimize_to_tray": True,
            "cable_volume": 80, "monitor_volume": 80, "microphone_volume": value, "macros": []}
    (tmp_path / "config.json").write_text(json.dumps(data), encoding="utf-8")
    assert Library(tmp_path).read_only


def test_schema_three_migrates_and_persists_stop_hotkey(tmp_path, wav):
    data = {"schema_version": 3, "selected_device_id": "", "minimize_to_tray": True,
            "cable_volume": 80, "monitor_volume": 80, "microphone_volume": 95,
            "macros": []}
    (tmp_path / "config.json").write_text(json.dumps(data), encoding="utf-8")
    lib = Library(tmp_path)
    lib.set_stop_hotkey("Ctrl+Alt+X")

    restored = Library(tmp_path)
    assert restored.stop_hotkey == "Ctrl+Alt+X"
    assert json.loads(lib.config.read_text(encoding="utf-8"))["schema_version"] == 4
    with pytest.raises(ValueError):
        restored.put("Conflicto", "Ctrl+Alt+X", wav)


def test_stop_hotkey_rejects_existing_macro(tmp_path, wav):
    lib = Library(tmp_path / "library")
    lib.put("Uno", "Ctrl+Alt+X", wav)
    with pytest.raises(ValueError):
        lib.set_stop_hotkey("Ctrl+Alt+X")


def test_package_round_trip_preserves_macros_shared_audio_and_stop_hotkey(tmp_path, wav):
    source = Library(tmp_path / "source")
    first = source.put("Uno", "Ctrl+1", wav)
    source.macros.append(Macro("second", "Dos", "Alt+2", first.audio, False))
    source.set_stop_hotkey("Ctrl+Alt+X")
    package = tmp_path / "atajos.zip"

    source.export_package(package)
    with zipfile.ZipFile(package) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert len(manifest["audio_files"]) == 1
        assert len(archive.namelist()) == 2
    source.path(first).unlink()

    destination = Library(tmp_path / "destination")
    old = destination.put("Anterior", "Ctrl+9", wav)
    destination.selected_device_id = "local-cable"
    destination.cable_volume = 42
    summary = destination.inspect_package(package)
    destination.import_package(package)

    assert summary.macro_count == 2 and summary.stop_hotkey == "Ctrl+Alt+X"
    assert [(m.id, m.name, m.hotkey, m.enabled) for m in destination.macros] == [
        (first.id, "Uno", "Ctrl+1", True), ("second", "Dos", "Alt+2", False)]
    assert destination.macros[0].audio == destination.macros[1].audio
    assert destination.path(destination.macros[0]).read_bytes() == wav.read_bytes()
    assert destination.stop_hotkey == "Ctrl+Alt+X"
    assert destination.selected_device_id == "local-cable" and destination.cable_volume == 42
    assert not destination.path(old).exists()


def write_package(path, manifest, files=None):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        for name, content in (files or {}).items():
            archive.writestr(name, content)


def package_manifest(audio=b"sound", **changes):
    digest = hashlib.sha256(audio).hexdigest()
    path = f"audio/{digest}.wav"
    manifest = {
        "package_version": 1,
        "app_version": "1.0.5",
        "stop_hotkey": "Ctrl+Alt+X",
        "macros": [{"id": "one", "name": "Uno", "hotkey": "Ctrl+1",
                    "audio": path, "enabled": True}],
        "audio_files": [{"path": path, "size": len(audio), "sha256": digest}],
    }
    manifest.update(changes)
    return manifest, {path: audio}


@pytest.mark.parametrize("variant", ["corrupt", "traversal", "hash", "duplicate_hotkey", "missing"])
def test_invalid_packages_are_rejected_without_changes(tmp_path, wav, variant):
    library = Library(tmp_path / "library")
    original = library.put("Original", "Ctrl+9", wav)
    package = tmp_path / "invalid.zip"
    manifest, files = package_manifest()
    if variant == "corrupt":
        package.write_bytes(b"not a zip")
    elif variant == "traversal":
        write_package(package, manifest, {**files, "../outside.wav": b"bad"})
    elif variant == "hash":
        files[next(iter(files))] = b"changed"
        write_package(package, manifest, files)
    elif variant == "duplicate_hotkey":
        manifest["macros"].append({**manifest["macros"][0], "id": "two"})
        write_package(package, manifest, files)
    else:
        write_package(package, manifest)

    with pytest.raises(ValueError):
        library.inspect_package(package)
    assert library.macros == [original] and library.path(original).is_file()
    assert not (tmp_path / "outside.wav").exists()


def test_import_rolls_back_copied_audio_when_config_save_fails(tmp_path, wav, monkeypatch):
    source = Library(tmp_path / "source")
    source.put("Nueva", "Ctrl+1", wav)
    package = tmp_path / "atajos.zip"
    source.export_package(package)
    destination = Library(tmp_path / "destination")
    original = destination.put("Original", "Ctrl+9", wav)
    existing_files = set(destination.audio_dir.iterdir())
    real_replace = os.replace

    def fail_config(source_path, destination_path):
        if Path(destination_path) == destination.config:
            raise OSError("disk full")
        return real_replace(source_path, destination_path)

    monkeypatch.setattr("trollsound.storage.os.replace", fail_config)
    with pytest.raises(ValueError, match="disk full"):
        destination.import_package(package)

    assert destination.macros == [original]
    assert set(destination.audio_dir.iterdir()) == existing_files
    assert Library(destination.root).macros == [original]
