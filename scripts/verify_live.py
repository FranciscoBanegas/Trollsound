"""Explicit hardware acceptance test; sends tones only through verified VB-Cable."""
import json
from pathlib import Path
import subprocess
import sys
import wave

import imageio_ffmpeg
from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication
from PyQt6.QtMultimedia import QAudioFormat, QAudioSource

from trollsound.audio import Diagnostic, Player, tone_pcm, tone_detected
from trollsound.devices import Devices


def main():
    app = QApplication([])
    devices = Devices()
    keys = [k for k in devices.outputs if devices.available(k)]
    if not keys:
        print("No VB-Cable operativo")
        return 10
    key = keys[0]
    result = {"output": devices.outputs[key].description(), "input": devices.pairs[key].description()}
    loop = QEventLoop()
    diagnostic = Diagnostic(devices)

    def diagnosed(valid, message):
        result["diagnostic"] = {"passed": valid, "message": message}
        loop.quit()

    diagnostic.completed.connect(diagnosed)
    diagnostic.start(key)
    if diagnostic.running:
        loop.exec()
    folder = Path("build/verification")
    folder.mkdir(parents=True, exist_ok=True)
    wav = folder / "tone.wav"
    with wave.open(str(wav), "wb") as stream:
        stream.setnchannels(2)
        stream.setsampwidth(2)
        stream.setframerate(48000)
        stream.writeframes(tone_pcm())
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
        if extension != "wav":
            subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-y", "-i", str(wav), str(path)],
                           check=True, creationflags=subprocess.CREATE_NO_WINDOW)
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
        QTimer.singleShot(3200, loop.quit)
        loop.exec()
        data.extend(bytes(reader.readAll()))
        player.close()
        capture.stop()
        result["formats"][extension] = tone_detected(data, fmt.sampleRate(), fmt.channelCount(), fmt.sampleFormat())
    (folder / "live-audio.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    passed = (result["diagnostic"]["passed"] and all(result["formats"].values())
              and all(result["monitor"]["formats"].values())
              and all(result["mix"]["formats"].values()))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
