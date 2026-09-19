from unittest.mock import MagicMock
from array import array
import pytest
from PyQt6.QtCore import QByteArray, QObject, pyqtSignal
from PyQt6.QtMultimedia import QAudio, QAudioFormat
from PyQt6.QtWidgets import QFileDialog, QLabel, QMessageBox
from trollsound.audio import MixerDevice, Player, Validator, tone_pcm, tone_detected
from trollsound.devices import device_id
from trollsound.storage import Library
from trollsound.hotkeys import STOP_ACTION_ID
from trollsound.ui import Window, MacroDialog, SettingsDialog
from test_devices_hotkeys import Device
import subprocess
import imageio_ffmpeg


class FakeReader(QObject):
    readyRead = pyqtSignal()

    def readAll(self):
        return QByteArray()


class FakeAudioStream(QObject):
    stateChanged = pyqtSignal(object)

    def __init__(self, device, audio_format, source=False):
        super().__init__()
        self.device = device
        self.audio_format = audio_format
        self.source = source
        self.reader = FakeReader() if source else None
        self.started_with = None
        self.stopped = False

    def setBufferSize(self, value):
        self.buffer_size = value

    def start(self, device=None):
        self.started_with = device
        return self.reader

    def stop(self):
        self.stopped = True

    def isNull(self):
        return False

    def error(self):
        return QAudio.Error.NoError


@pytest.fixture(autouse=True)
def audio_bridge(monkeypatch):
    sources, sinks = [], []

    def source_factory(device, audio_format, _parent=None):
        stream = FakeAudioStream(device, audio_format, True)
        sources.append(stream)
        return stream

    def sink_factory(device, audio_format, _parent=None):
        stream = FakeAudioStream(device, audio_format)
        sinks.append(stream)
        return stream

    monkeypatch.setattr("trollsound.audio.QAudioSource", source_factory)
    monkeypatch.setattr("trollsound.audio.QAudioSink", sink_factory)
    return sources, sinks


def test_tone_detector_rejects_silence_and_continuous_tone():
    pcm = tone_pcm()
    assert tone_detected(pcm)
    assert not tone_detected(bytes(len(pcm)))
    assert not tone_detected(pcm[48000 * 4 // 3:48000 * 4 // 2] * 12)


@pytest.mark.parametrize("sample_format", [QAudioFormat.SampleFormat.Float, QAudioFormat.SampleFormat.Int32,
                                          QAudioFormat.SampleFormat.UInt8])
def test_tone_native_formats(sample_format):
    assert tone_detected(tone_pcm(sample_format=sample_format), sample_format=sample_format)


def test_validator_decodes_without_audio_output(qtbot, wav):
    validator = Validator()
    with qtbot.waitSignal(validator.completed, timeout=15000) as result:
        validator.validate(wav)
    assert result.args == [True, ""]


@pytest.mark.parametrize("extension", ["mp3", "ogg", "flac"])
def test_compressed_formats_decode(qtbot, wav, extension):
    path = wav.with_suffix("." + extension)
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-y", "-i", str(wav), str(path)],
                   check=True, creationflags=subprocess.CREATE_NO_WINDOW)
    validator = Validator()
    with qtbot.waitSignal(validator.completed, timeout=15000) as result:
        validator.validate(path)
    assert result.args == [True, ""]


def test_validator_rejects_invalid_audio(qtbot, tmp_path):
    path = tmp_path / "broken.mp3"
    path.write_bytes(b"not audio")
    validator = Validator()
    with qtbot.waitSignal(validator.completed, timeout=15000) as result:
        validator.validate(path)
    assert result.args[0] is False


def audio_format(sample_format=QAudioFormat.SampleFormat.Float):
    result = QAudioFormat()
    result.setSampleRate(48000)
    result.setChannelCount(2)
    result.setSampleFormat(sample_format)
    return result


def test_mixer_combines_float_streams_and_saturates():
    mixer = MixerDevice(audio_format())
    mixer.set_gains(1.0, 0.5)
    microphone = array("f", [0.25, -0.25, 0.9, -0.9]).tobytes()
    clip = array("f", [0.5, -0.5, 0.5, -0.5]).tobytes()
    mixer.push_microphone(microphone)
    mixer.push_clip(clip)
    result = array("f")
    result.frombytes(mixer.readData(len(microphone)))
    assert list(result) == pytest.approx([0.5, -0.5, 1.0, -1.0])


def test_mixer_handles_silence_overflow_clear_and_int16():
    fmt = audio_format(QAudioFormat.SampleFormat.Int16)
    mixer = MixerDevice(fmt)
    mixer.max_microphone = fmt.bytesPerFrame() * 2
    mixer.push_microphone(array("h", [100, 100, 200, 200, 300, 300]).tobytes())
    mixer.push_clip(array("h", [1000, 1000]).tobytes())
    mixer.clear_clip()
    result = array("h")
    result.frombytes(mixer.readData(fmt.bytesPerFrame() * 3))
    assert list(result) == [200, 200, 300, 300, 0, 0]


def test_bridge_uses_default_microphone_and_explicit_cable(
        qtbot, fake_devices, audio_bridge):
    cable = Device("CABLE Input (VB-Audio Virtual Cable)", b"cable")
    cable_output = Device("CABLE Output (VB-Audio Virtual Cable)", b"cable-output")
    key = device_id(cable)
    fake_devices.outputs[key] = cable
    fake_devices.pairs[key] = cable_output
    player = Player(fake_devices)

    player.select(key)

    sources, sinks = audio_bridge
    assert player.bridge_ready
    assert sources[-1].device is fake_devices.default_input_device
    assert sinks[-1].device is cable
    assert sinks[-1].started_with is player.mixer


def test_stop_clip_and_pause_keep_microphone_bridge(qtbot, fake_devices, audio_bridge):
    cable = Device("CABLE Input (VB-Audio Virtual Cable)", b"cable")
    cable_output = Device("CABLE Output (VB-Audio Virtual Cable)", b"cable-output")
    key = device_id(cable)
    fake_devices.outputs[key] = cable
    fake_devices.pairs[key] = cable_output
    player = Player(fake_devices)
    player.select(key)
    source, sink = player.source, player.sink

    player.stop_clip()

    assert player.bridge_ready
    assert player.source is source and player.sink is sink
    player.suspend_bridge()
    assert not player.bridge_ready
    player.resume_bridge()
    assert player.bridge_ready


def test_default_microphone_change_restarts_bridge(qtbot, fake_devices, audio_bridge):
    cable = Device("CABLE Input (VB-Audio Virtual Cable)", b"cable")
    cable_output = Device("CABLE Output (VB-Audio Virtual Cable)", b"cable-output")
    key = device_id(cable)
    fake_devices.outputs[key] = cable
    fake_devices.pairs[key] = cable_output
    player = Player(fake_devices)
    player.select(key)
    previous_source = player.source
    replacement = Device("Microphone (USB)", b"microphone-usb")
    fake_devices.default_input_device = replacement

    fake_devices.changed.emit()

    assert previous_source.stopped
    assert player.bridge_ready
    assert player.microphone_name == "Microphone (USB)"


def test_player_uses_monitor_only_for_clip_with_independent_volumes(
        qtbot, fake_devices, wav, monkeypatch):
    cable = Device("CABLE Input (VB-Audio Virtual Cable)", b"cable")
    cable_output = Device("CABLE Output (VB-Audio Virtual Cable)", b"cable-output")
    speakers = Device("Speakers (Realtek)", b"speakers")
    key = device_id(cable)
    fake_devices.outputs[key] = cable
    fake_devices.pairs[key] = cable_output
    fake_devices.default_output_device = speakers
    monitor_output, monitor_player = MagicMock(), MagicMock()
    output_factory = MagicMock(return_value=monitor_output)
    player_factory = MagicMock(return_value=monitor_player)
    monkeypatch.setattr("trollsound.audio.QAudioOutput", output_factory)
    monkeypatch.setattr("trollsound.audio.QMediaPlayer", player_factory)
    player = Player(fake_devices)
    player.set_microphone_volume(90)
    player.set_cable_volume(70)
    player.set_monitor_volume(25)
    player.select(key)

    assert player.play(wav)

    assert output_factory.call_args.args[0] is speakers
    monitor_output.setVolume.assert_called_with(0.25)
    monitor_player.play.assert_called_once()
    assert player.mixer.microphone_gain == 0.9
    assert player.mixer.clip_gain == 0.7
    player.on_monitor_error(None, "sin auriculares")
    assert player.bridge_ready and player.monitor_player is None


def test_volume_controls_persist_independently(window, qtbot):
    window.microphone_volume.setValue(91)
    window.cable_volume.setValue(61)
    window.monitor_volume.setValue(27)
    window.persist_volumes()
    restored = Library(window.library.root)
    assert (restored.microphone_volume, restored.cable_volume, restored.monitor_volume) == (91, 61, 27)


def test_settings_persists_stop_hotkey_and_shows_product(window, qtbot):
    dialog = SettingsDialog(window.library, parent=window)
    qtbot.addWidget(dialog)
    dialog.stop_combo.setText("Ctrl+Alt+X")
    dialog.submit()

    restored = Library(window.library.root)
    assert restored.stop_hotkey == "Ctrl+Alt+X"
    assert "Trollsound" in [label.text() for label in dialog.findChildren(QLabel)]


def test_settings_exports_and_imports_after_confirmation(window, qtbot, wav, tmp_path, monkeypatch):
    window.library.put("Actual", "Ctrl+9", wav)
    exported = tmp_path / "exported.zip"
    dialog = SettingsDialog(window.library, parent=window)
    qtbot.addWidget(dialog)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(exported), ""))
    dialog.export_package()
    assert exported.is_file() and "exportados" in dialog.message.text()

    replacement = Library(tmp_path / "replacement")
    replacement.put("Importada", "Ctrl+1", wav)
    replacement.set_stop_hotkey("Ctrl+Alt+X")
    package = tmp_path / "replacement.zip"
    replacement.export_package(package)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(package), ""))
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No)
    dialog.import_package()
    assert [macro.name for macro in window.library.macros] == ["Actual"]

    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *args: QMessageBox.StandardButton.Ok)
    dialog.import_package()
    assert dialog.imported
    assert [macro.name for macro in window.library.macros] == ["Importada"]
    assert window.library.stop_hotkey == "Ctrl+Alt+X"


def test_window_refreshes_and_stops_after_settings_import(window, wav, tmp_path, monkeypatch):
    replacement = Library(tmp_path / "replacement")
    replacement.put("Importada", "Ctrl+1", wav)
    replacement.set_stop_hotkey("Ctrl+Alt+X")
    package = tmp_path / "replacement.zip"
    replacement.export_package(package)
    stop = MagicMock()
    monkeypatch.setattr(window.player, "stop_clip", stop)

    class ImportedSettings:
        def __init__(self, library, *args, **kwargs):
            library.import_package(package)
            self.imported = True

        def exec(self):
            return 0

        def deleteLater(self):
            pass

    monkeypatch.setattr("trollsound.ui.SettingsDialog", ImportedSettings)
    window.open_settings()

    assert window.table.rowCount() == 1
    assert window.table.item(0, 0).text() == "Importada"
    assert window.hotkeys.statuses[STOP_ACTION_ID] == "Registrada"
    stop.assert_called_once()


def test_stop_hotkey_stops_only_clip(window, monkeypatch):
    stop = MagicMock()
    monkeypatch.setattr(window.player, "stop_clip", stop)
    generation = window.hotkeys.generation

    window.trigger(STOP_ACTION_ID, generation)

    stop.assert_called_once()


@pytest.fixture
def window(qtbot, tmp_path, fake_devices, fake_hotkeys):
    window = Window(Library(tmp_path / "library"), fake_devices, fake_hotkeys)
    qtbot.addWidget(window)
    yield window
    window.quitting = True
    window.cleanup()


def test_dialog_add_edit_and_delete(qtbot, window, wav, monkeypatch):
    dialog = MacroDialog(window.library, window.hotkeys, parent=window)
    qtbot.addWidget(dialog)
    dialog.name.setText("Hola")
    dialog.combo.setText("CTRL+ALT+1")
    dialog.source = wav
    with qtbot.waitSignal(dialog.accepted, timeout=15000):
        dialog.submit()
    assert window.library.macros[0].name == "Hola"
    macro = window.library.macros[0]
    edit = MacroDialog(window.library, window.hotkeys, macro, window)
    qtbot.addWidget(edit)
    edit.name.setText("Editada")
    with qtbot.waitSignal(edit.accepted, timeout=15000):
        edit.submit()
    assert window.library.macros[0].name == "Editada"
    window.refresh_table()
    window.table.selectRow(0)
    window.toggle_macro()
    assert not window.library.macros[0].enabled
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    window.delete_macro()
    assert not window.library.macros and window.table.rowCount() == 0


def test_missing_cable_missing_file_pause_reconnect(window, wav):
    macro = window.library.put("Hola", "ctrl+1", wav)
    window.sync_hotkeys()
    assert window.hotkeys.registered == []
    device = Device("CABLE Input (VB-Audio Virtual Cable)")
    key = device_id(device)
    window.devices.outputs[key] = window.devices.pairs[key] = device
    window.library.selected_device_id = key
    window.refresh_devices()
    assert window.hotkeys.registered == [macro]
    bridge = (window.player.source, window.player.sink)
    window.pause.setChecked(True)
    assert window.hotkeys.registered == []
    assert window.player.bridge_ready and (window.player.source, window.player.sink) == bridge
    window.pause.setChecked(False)
    assert window.hotkeys.registered == [macro]
    window.devices.outputs.clear()
    window.devices.changed.emit()
    assert window.paused and window.hotkeys.registered == []
    window.devices.outputs[key] = device
    window.devices.changed.emit()
    assert window.paused and window.hotkeys.registered == []
    window.library.path(macro).unlink()
    window.pause.setChecked(False)
    window.refresh_table()
    assert window.hotkeys.registered == []
    assert window.table.item(0, 3).text() == "Archivo ausente"


def test_registered_status_and_conflict_are_visible(window, wav):
    macro = window.library.put("Hola", "ctrl+1", wav)
    device = Device("CABLE Input (VB-Audio Virtual Cable)")
    key = device_id(device)
    window.devices.outputs[key] = window.devices.pairs[key] = device
    window.library.selected_device_id = key
    window.refresh_devices()
    window.refresh_table()
    assert window.table.item(0, 3).text() == "Registrada"
    window.hotkeys.statuses[macro.id] = "Conflicto"
    window.hotkeys.status_details[macro.id] = "Windows la rechazo"
    window.update_macro_states()
    assert window.table.item(0, 3).text() == "Conflicto"
    assert window.table.item(0, 3).toolTip() == "Windows la rechazo"


def test_stale_queued_hotkey_is_ignored(window, wav, monkeypatch):
    macro = window.library.put("Hola", "ctrl+1", wav)
    play = MagicMock()
    monkeypatch.setattr(window.player, "play", play)
    old_generation = window.hotkeys.generation
    window.hotkeys.clear()
    window.trigger(macro.id, old_generation)
    play.assert_not_called()


def test_close_hides_to_tray_without_releasing_hotkeys(window, wav, monkeypatch):
    macro = window.library.put("Hola", "ctrl+1", wav)
    device = Device("CABLE Input (VB-Audio Virtual Cable)")
    key = device_id(device)
    window.devices.outputs[key] = window.devices.pairs[key] = device
    window.library.selected_device_id = key
    window.refresh_devices()
    assert window.hotkeys.registered == [macro]
    bridge = (window.player.source, window.player.sink)
    monkeypatch.setattr(window.tray, "isVisible", lambda: True)
    window.show()
    window.close()
    assert not window.isVisible() and not window.quitting
    assert window.hotkeys.registered == [macro]
    assert window.player.bridge_ready and (window.player.source, window.player.sink) == bridge
