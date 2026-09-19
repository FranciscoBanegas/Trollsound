"""Opt-in acceptance check for a frozen bundle using known tone fixtures."""
import json
from pathlib import Path

from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtMultimedia import QAudioSource

from .audio import Diagnostic, Player, Validator, tone_detected


def verify_bundle(devices, folder):
    folder = Path(folder).resolve()
    keys = [key for key in devices.outputs if devices.available(key)]
    if not keys:
        return 10
    key = keys[0]
    loop = QEventLoop()
    result = {}
    diagnostic = Diagnostic(devices)

    def diagnosed(valid, message):
        result["diagnostic"] = dict(passed=valid, message=message)
        loop.quit()

    diagnostic.completed.connect(diagnosed)
    diagnostic.start(key)
    if diagnostic.running:
        loop.exec()
    fmt = devices.pairs[key].preferredFormat()
    result["formats"] = {}
    monitor = devices.default_output()
    result["monitor"] = {
        "device": "" if monitor is None or monitor.isNull() else monitor.description(),
        "formats": {},
    }
    result["mix"] = {"microphone": "", "formats": {}}
    for extension in ("wav", "mp3", "ogg", "flac"):
        path = folder / ("tone." + extension)
        if not path.is_file():
            result["formats"][extension] = False
            continue
        capture = QAudioSource(devices.pairs[key], fmt)
        reader = capture.start()
        if reader is None:
            result["formats"][extension] = False
            continue
        data = bytearray()
        reader.readyRead.connect(lambda r=reader, d=data: d.extend(bytes(r.readAll())))
        player = Player(devices)
        player.select(key)
        result["mix"]["microphone"] = player.microphone_name
        result["mix"]["formats"][extension] = player.bridge_ready
        player.play(path)
        result["monitor"]["formats"][extension] = player.monitor_player is not None
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        timer.start(3200)
        loop.exec()
        data.extend(bytes(reader.readAll()))
        player.close()
        capture.stop()
        result["formats"][extension] = tone_detected(data, fmt.sampleRate(), fmt.channelCount(), fmt.sampleFormat())
    (folder / "bundle-audio.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    passed = (result["diagnostic"]["passed"] and all(result["formats"].values())
              and all(result["monitor"]["formats"].values())
              and all(result["mix"]["formats"].values()))
    return 0 if passed else 1
