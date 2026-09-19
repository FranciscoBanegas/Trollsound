import ctypes
from ctypes import wintypes

import pytest
from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtMultimedia import QAudioFormat

from trollsound.devices import Endpoint, cable_family, endpoint_for
from trollsound.hotkeys import (DEBOUNCE_NS, FIRST_HOTKEY_ID, MOD_ALT, MOD_CONTROL,
                                MOD_NOREPEAT, MOD_SHIFT, WM_HOTKEY, Hotkeys,
                                parse_hotkey)
from trollsound.storage import Macro


class Device:
    def __init__(self, name, identifier=b"{0.0.0.00000000}.{abc}"):
        self.name, self.identifier = name, identifier

    def description(self):
        return self.name

    def id(self):
        return QByteArray(self.identifier)

    def isNull(self):
        return False

    def preferredFormat(self):
        audio_format = QAudioFormat()
        audio_format.setSampleRate(48000)
        audio_format.setChannelCount(2)
        audio_format.setSampleFormat(QAudioFormat.SampleFormat.Float)
        return audio_format

    def isFormatSupported(self, audio_format):
        return audio_format.isValid()


class FakeHotkeyApi:
    def __init__(self, rejected=None):
        self.rejected = set(rejected or [])
        self.registrations = []
        self.unregistered = []

    def scan_character(self, character):
        return {"+": (1 << 8) | 0xBB, "ñ": 0xBA}.get(character, -1)

    def register(self, hwnd, identifier, modifiers, virtual_key):
        self.registrations.append((hwnd.value, identifier, modifiers, virtual_key))
        return (False, 1409) if identifier in self.rejected else (True, 0)

    def unregister(self, hwnd, identifier):
        self.unregistered.append((hwnd.value, identifier))
        return True


@pytest.mark.parametrize("name, expected", [
    ("CABLE Input (VB-Audio Virtual Cable)", "STANDARD"),
    ("CABLE-A Input (VB-Audio Cable A)", "A"),
    ("Speakers (Realtek)", None),
    ("VoiceMeeter Input (VB-Audio VoiceMeeter VAIO)", None),
    ("CABLE Output (VB-Audio Virtual Cable)", None),
    ("Fake CABLE Input", None),
])
def test_filter(name, expected):
    assert cable_family(name, "Input") == expected


def test_native_identity_required():
    device = Device("CABLE Input (VB-Audio Virtual Cable)")
    assert endpoint_for(device, [], "Render") is None
    assert endpoint_for(device, [Endpoint("{different}", "Render", "STANDARD", True)], "Render") is None
    assert endpoint_for(device, [Endpoint("{abc}", "Render", "STANDARD", False)], "Render") is None
    assert endpoint_for(device, [Endpoint("{abc}", "Render", "STANDARD", True)], "Render")


def test_existing_hotkey_is_translated_to_native():
    parsed = parse_hotkey("ALT+CTRL+a", FakeHotkeyApi())
    assert parsed.canonical == "Ctrl+Alt+A"
    assert parsed.modifiers == MOD_CONTROL | MOD_ALT | MOD_NOREPEAT
    assert parsed.virtual_key == ord("A")


def test_spanish_layout_and_implicit_shift():
    enye = parse_hotkey("ctrl+ñ", FakeHotkeyApi())
    plus = parse_hotkey("ctrl+plus", FakeHotkeyApi())
    assert enye.virtual_key == 0xBA
    assert plus.virtual_key == 0xBB
    assert plus.modifiers & MOD_SHIFT
    assert parse_hotkey(plus.canonical, FakeHotkeyApi()) == plus


@pytest.mark.parametrize("value", ["", "ctrl", "a", "ctrl+a, b", "alt+f4", "f12", "meta+a"])
def test_invalid_hotkeys(value):
    with pytest.raises(ValueError):
        parse_hotkey(value, FakeHotkeyApi())


def test_native_registration_conflicts_dispatch_and_release(qtbot):
    api = FakeHotkeyApi(rejected={FIRST_HOTKEY_ID + 1})
    hooks = Hotkeys(api=api)
    hooks.set_window(1234)
    first = Macro("one", "Uno", "ctrl+1", "one.wav")
    second = Macro("two", "Dos", "ctrl+2", "two.wav")
    hooks.register([first, second])
    generation = hooks.generation
    assert hooks.statuses == {"one": "Registrada", "two": "Conflicto"}
    assert api.registrations[0][2] & MOD_NOREPEAT
    with qtbot.waitSignal(hooks.triggered) as signal:
        hooks.dispatch(FIRST_HOTKEY_ID)
    assert signal.args == ["one", generation]
    hooks.dispatch(FIRST_HOTKEY_ID + 1)
    hooks.clear()
    assert api.unregistered == [(1234, FIRST_HOTKEY_ID)]
    hooks.close()


def test_native_event_filter_discards_stale_events(qtbot):
    api = FakeHotkeyApi()
    hooks = Hotkeys(api=api)
    hooks.set_window(1234)
    hooks.register([Macro("one", "Uno", "ctrl+1", "one.wav")])
    hits = []
    hooks.triggered.connect(lambda *args: hits.append(args))
    message = wintypes.MSG()
    message.message = WM_HOTKEY
    message.wParam = FIRST_HOTKEY_ID
    hooks.filter.nativeEventFilter(b"windows_generic_MSG", ctypes.addressof(message))
    assert len(hits) == 1
    hooks.clear()
    hooks.filter.nativeEventFilter(b"windows_generic_MSG", ctypes.addressof(message))
    assert len(hits) == 1
    hooks.close()


def test_dispatch_deduplicates_immediate_native_events(qtbot, monkeypatch):
    api = FakeHotkeyApi()
    hooks = Hotkeys(api=api)
    hooks.set_window(1234)
    hooks.register([Macro("one", "Uno", "ctrl+1", "one.wav")])
    hits = []
    hooks.triggered.connect(lambda *args: hits.append(args))
    clock = iter((1_000_000_000, 1_000_000_001, 1_000_000_000 + DEBOUNCE_NS))
    monkeypatch.setattr("trollsound.hotkeys.time.monotonic_ns", lambda: next(clock))

    hooks.dispatch(FIRST_HOTKEY_ID)
    hooks.dispatch(FIRST_HOTKEY_ID)
    hooks.dispatch(FIRST_HOTKEY_ID)

    assert [args[0] for args in hits] == ["one", "one"]
    hooks.close()
