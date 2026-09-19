import os
import wave

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["QT_MEDIA_BACKEND"] = "ffmpeg"

import pytest
from PyQt6.QtCore import QByteArray, QObject, pyqtSignal
from PyQt6.QtMultimedia import QAudioFormat
from trollsound.audio import tone_pcm


class DefaultInputDevice:
    def description(self):
        return "Microphone (Test)"

    def id(self):
        return QByteArray(b"microphone-test")

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


@pytest.fixture
def wav(tmp_path):
    path = tmp_path / "tono.wav"
    with wave.open(str(path), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(48000)
        output.writeframes(tone_pcm())
    return path


class FakeDevices(QObject):
    changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.outputs = {}
        self.pairs = {}
        self.error = ""
        self.default_output_device = None
        self.default_input_device = DefaultInputDevice()

    def refresh(self):
        pass

    def available(self, key):
        return key in self.outputs and key in self.pairs

    def default_output(self):
        return self.default_output_device

    def default_input(self):
        return self.default_input_device


class FakeHotkeys(QObject):
    triggered = pyqtSignal(str, int)
    failure = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.generation = 0
        self.registered = []
        self.statuses = {}
        self.status_details = {}

    def set_window(self, hwnd):
        self.hwnd = hwnd

    def clear(self):
        self.generation += 1
        self.registered = []
        self.statuses = {}
        self.status_details = {}

    def register(self, macros):
        self.clear()
        self.registered = list(macros)
        self.statuses = {macro.id: "Registrada" for macro in macros}
        self.status_details = {macro.id: macro.hotkey for macro in macros}

    def close(self):
        self.clear()

@pytest.fixture
def fake_devices():
    return FakeDevices()


@pytest.fixture
def fake_hotkeys():
    return FakeHotkeys()
