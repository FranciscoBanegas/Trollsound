import json
import pytest
from trollsound.storage import Library


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
    assert saved["schema_version"] == 3
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


@pytest.mark.parametrize("value", [-1, 101, True])
def test_schema_three_rejects_invalid_microphone_volume(tmp_path, value):
    data = {"schema_version": 3, "selected_device_id": "", "minimize_to_tray": True,
            "cable_volume": 80, "monitor_volume": 80, "microphone_volume": value, "macros": []}
    (tmp_path / "config.json").write_text(json.dumps(data), encoding="utf-8")
    assert Library(tmp_path).read_only
