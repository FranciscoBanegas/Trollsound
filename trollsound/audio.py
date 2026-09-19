from __future__ import annotations

import math
import struct
import threading
from array import array
from pathlib import Path

from PyQt6.QtCore import QObject, QUrl, QTimer, QBuffer, QByteArray, QIODevice, pyqtSignal
from PyQt6.QtMultimedia import (QAudio, QAudioDecoder, QAudioFormat, QAudioOutput,
                               QAudioSink, QAudioSource, QMediaPlayer)

from .devices import device_id


class Validator(QObject):
    completed = pyqtSignal(bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.decoder = QAudioDecoder(self)
        self.decoder.bufferReady.connect(self.read)
        self.decoder.finished.connect(self.finish)
        self.decoder.error.connect(lambda _: self.done(False, self.decoder.errorString()))
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(lambda: self.done(False, "Tiempo de validacion agotado"))
        self.busy = False
        self.frames = 0

    def validate(self, path: Path):
        self.cancel()
        self.frames = 0
        self.busy = True
        self.decoder.setSource(QUrl.fromLocalFile(str(path.resolve())))
        self.timer.start(60000)
        self.decoder.start()

    def read(self):
        buffer = self.decoder.read()
        if buffer.isValid():
            self.frames += buffer.frameCount()

    def finish(self):
        self.done(self.frames > 0, "" if self.frames else "El archivo no contiene audio decodificable")

    def done(self, valid, message):
        if self.busy:
            self.cancel()
            self.completed.emit(valid, message)

    def cancel(self):
        self.busy = False
        self.timer.stop()
        self.decoder.stop()


class MixerDevice(QIODevice):
    def __init__(self, audio_format, parent=None):
        super().__init__(parent)
        self.audio_format = audio_format
        self.frame_bytes = audio_format.bytesPerFrame()
        self.max_microphone = audio_format.bytesForDuration(250_000)
        self.microphone = bytearray()
        self.clip = bytearray()
        self.microphone_gain = 1.0
        self.clip_gain = 0.8
        self.lock = threading.Lock()
        self.open(QIODevice.OpenModeFlag.ReadOnly)

    def isSequential(self):
        return True

    def bytesAvailable(self):
        with self.lock:
            queued = max(len(self.microphone), len(self.clip))
        return max(self.audio_format.bytesForDuration(20_000), queued, super().bytesAvailable())

    def writeData(self, _data):
        return -1

    def push_microphone(self, data):
        with self.lock:
            self.microphone.extend(data)
            overflow = len(self.microphone) - self.max_microphone
            if overflow > 0:
                drop = overflow + (-overflow % self.frame_bytes)
                del self.microphone[:drop]

    def push_clip(self, data):
        with self.lock:
            self.clip.extend(data)

    def clear_clip(self):
        with self.lock:
            self.clip.clear()

    def clip_size(self):
        with self.lock:
            return len(self.clip)

    def set_gains(self, microphone, clip):
        with self.lock:
            self.microphone_gain = microphone
            self.clip_gain = clip

    def readData(self, max_length):
        aligned = max_length - (max_length % self.frame_bytes)
        if aligned <= 0:
            return bytes(max_length)
        with self.lock:
            microphone = bytes(self.microphone[:aligned])
            clip = bytes(self.clip[:aligned])
            del self.microphone[:len(microphone)]
            del self.clip[:len(clip)]
            microphone_gain = self.microphone_gain
            clip_gain = self.clip_gain
        microphone += bytes(aligned - len(microphone))
        clip += bytes(aligned - len(clip))
        sample_format = self.audio_format.sampleFormat()
        if sample_format == QAudioFormat.SampleFormat.Float:
            left, right = array("f"), array("f")
            left.frombytes(microphone)
            right.frombytes(clip)
            mixed = array("f", (max(-1.0, min(1.0, a * microphone_gain + b * clip_gain))
                                for a, b in zip(left, right)))
        elif sample_format == QAudioFormat.SampleFormat.Int16:
            left, right = array("h"), array("h")
            left.frombytes(microphone)
            right.frombytes(clip)
            mixed = array("h", (max(-32768, min(32767, round(a * microphone_gain + b * clip_gain)))
                                for a, b in zip(left, right)))
        else:
            return bytes(max_length)
        return mixed.tobytes() + bytes(max_length - aligned)


class Player(QObject):
    status = pyqtSignal(str)
    failure = pyqtSignal(str)
    notice = pyqtSignal(str)
    bridge_changed = pyqtSignal(bool, str, str)

    def __init__(self, devices, parent=None):
        super().__init__(parent)
        self.devices = devices
        self.key = ""
        self.source = self.sink = self.reader = self.mixer = None
        self.microphone_key = ""
        self.microphone_name = ""
        self.bridge_ready = False
        self.bridge_error = ""
        self.bridge_suspended = False
        self.decoder = None
        self.decoder_finished = False
        self.clip_timer = QTimer(self)
        self.clip_timer.setInterval(20)
        self.clip_timer.timeout.connect(self.pump_decoder)
        self.monitor_player = None
        self.monitor_output = None
        self.monitor_key = ""
        self.cable_volume = 0.8
        self.monitor_volume = 0.8
        self.microphone_volume = 1.0
        self.devices.changed.connect(self.guard)

    def select(self, key):
        if self.key == key and self.bridge_ready:
            return
        self.stop_clip()
        self.key = key
        self.restart_bridge()

    def guard(self):
        microphone = self.devices.default_input()
        microphone_key = "" if microphone is None or microphone.isNull() else device_id(microphone)
        if (not self.devices.available(self.key) or microphone_key != self.microphone_key or
                not self.bridge_ready):
            self.stop_clip()
            self.restart_bridge()

    def compatible_format(self, microphone, cable):
        candidates = [cable.preferredFormat(), microphone.preferredFormat()]
        for rate in (48000, 44100):
            for sample_format in (QAudioFormat.SampleFormat.Float, QAudioFormat.SampleFormat.Int16):
                candidate = QAudioFormat()
                candidate.setSampleRate(rate)
                candidate.setChannelCount(2)
                candidate.setSampleFormat(sample_format)
                candidates.append(candidate)
        seen = set()
        for candidate in candidates:
            identity = (candidate.sampleRate(), candidate.channelCount(), candidate.sampleFormat())
            if identity in seen:
                continue
            seen.add(identity)
            if (candidate.isValid() and candidate.sampleFormat() in
                    (QAudioFormat.SampleFormat.Float, QAudioFormat.SampleFormat.Int16)
                    and microphone.isFormatSupported(candidate) and cable.isFormatSupported(candidate)):
                return candidate
        return None

    def restart_bridge(self):
        self.stop_bridge(False)
        if self.bridge_suspended:
            self.bridge_error = "Mezcla suspendida temporalmente"
            self.bridge_changed.emit(False, self.bridge_error, "")
            return False
        if not self.key or not self.devices.available(self.key):
            self.bridge_error = "Selecciona un par VB-Cable operativo"
            self.bridge_changed.emit(False, self.bridge_error, "")
            return False
        microphone = self.devices.default_input()
        if microphone is None or microphone.isNull():
            return self.bridge_failed("No hay un microfono predeterminado disponible")
        microphone_key = device_id(microphone)
        if microphone_key == device_id(self.devices.pairs[self.key]):
            return self.bridge_failed("El microfono predeterminado no puede ser CABLE Output")
        cable = self.devices.outputs[self.key]
        audio_format = self.compatible_format(microphone, cable)
        if audio_format is None:
            return self.bridge_failed("El microfono y VB-Cable no comparten un formato de audio compatible")
        try:
            self.mixer = MixerDevice(audio_format, self)
            self.mixer.set_gains(self.microphone_volume, self.cable_volume)
            buffer_size = max(audio_format.bytesForDuration(60_000), audio_format.bytesPerFrame() * 64)
            self.source = QAudioSource(microphone, audio_format, self)
            self.source.setBufferSize(buffer_size)
            self.source.stateChanged.connect(self.check_bridge_state)
            self.reader = self.source.start()
            if self.reader is None:
                return self.bridge_failed("No se pudo abrir el microfono predeterminado")
            self.reader.readyRead.connect(self.read_microphone)
            self.sink = QAudioSink(cable, audio_format, self)
            self.sink.setBufferSize(buffer_size)
            self.sink.stateChanged.connect(self.check_bridge_state)
            self.sink.start(self.mixer)
            if any(device.error() in (QAudio.Error.OpenError, QAudio.Error.IOError,
                                      QAudio.Error.FatalError) for device in (self.source, self.sink)):
                return self.bridge_failed("No se pudo iniciar la mezcla de audio")
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            return self.bridge_failed(f"No se pudo iniciar la mezcla: {exc}")
        self.microphone_key = microphone_key
        self.microphone_name = microphone.description()
        self.bridge_error = ""
        self.bridge_ready = True
        self.bridge_changed.emit(True, "", self.microphone_name)
        return True

    def read_microphone(self):
        if self.reader and self.mixer:
            self.mixer.push_microphone(bytes(self.reader.readAll()))

    def check_bridge_state(self, _state):
        devices = (self.source, self.sink)
        if self.bridge_ready and any(device and device.error() in
                                     (QAudio.Error.OpenError, QAudio.Error.IOError, QAudio.Error.FatalError)
                                     for device in devices):
            self.stop_clip()
            self.bridge_failed("La mezcla de microfono y VB-Cable se interrumpio")

    def bridge_failed(self, message):
        self.stop_bridge(False)
        self.bridge_error = message
        self.bridge_changed.emit(False, message, "")
        return False

    def stop_bridge(self, notify=True):
        self.bridge_ready = False
        if self.reader:
            try:
                self.reader.readyRead.disconnect(self.read_microphone)
            except (TypeError, RuntimeError):
                pass
        for device in (self.source, self.sink):
            if device:
                try:
                    device.stateChanged.disconnect(self.check_bridge_state)
                except (TypeError, RuntimeError):
                    pass
                device.stop()
                device.deleteLater()
        if self.mixer:
            self.mixer.close()
            self.mixer.deleteLater()
        self.source = self.sink = self.reader = self.mixer = None
        self.microphone_key = self.microphone_name = ""
        if notify:
            self.bridge_changed.emit(False, self.bridge_error, "")

    def suspend_bridge(self):
        self.bridge_suspended = True
        self.stop_clip()
        self.stop_bridge(False)
        self.bridge_changed.emit(False, "Mezcla suspendida temporalmente", "")

    def resume_bridge(self):
        self.bridge_suspended = False
        return self.restart_bridge()

    def play(self, path):
        self.stop_clip()
        if not self.bridge_ready or not self.mixer:
            self.failure.emit(self.bridge_error or "La mezcla de audio no esta disponible")
            return False
        if not Path(path).is_file():
            self.failure.emit("El archivo de audio no existe")
            return False
        source = QUrl.fromLocalFile(str(Path(path).resolve()))
        self.decoder = QAudioDecoder(self)
        self.decoder.setAudioFormat(self.mixer.audio_format)
        self.decoder.bufferReady.connect(self.pump_decoder)
        self.decoder.finished.connect(self.decoder_done)
        self.decoder.error.connect(self.on_decoder_error)
        self.decoder.setSource(source)
        monitor_ready = self.prepare_monitor(source)
        self.decoder_finished = False
        self.decoder.start()
        self.clip_timer.start()
        if monitor_ready:
            self.monitor_player.play()
        else:
            self.notice.emit("El audio llega al juego, pero la escucha local no esta disponible")
        self.status.emit("Reproduciendo")
        return True

    def pump_decoder(self):
        if not self.decoder or not self.mixer:
            return
        high_water = self.mixer.audio_format.bytesForDuration(2_000_000)
        while self.decoder.bufferAvailable() and self.mixer.clip_size() < high_water:
            buffer = self.decoder.read()
            if buffer.isValid():
                self.mixer.push_clip(bytes(buffer.data()))
        if self.decoder_finished and self.mixer.clip_size() == 0:
            self.stop_clip()

    def decoder_done(self):
        self.decoder_finished = True
        self.pump_decoder()

    def on_decoder_error(self, _error):
        message = self.decoder.errorString() if self.decoder else "No se pudo decodificar el audio"
        self.stop_clip()
        self.failure.emit(message)

    def prepare_monitor(self, source):
        try:
            device = self.devices.default_output()
            if device is None or device.isNull():
                return False
            self.monitor_key = device_id(device)
            if self.monitor_key == self.key:
                self.monitor_key = ""
                return False
            self.monitor_output = QAudioOutput(device, self)
            self.monitor_output.setVolume(self.monitor_volume)
            self.monitor_output.deviceChanged.connect(self.check_monitor_output)
            self.monitor_player = QMediaPlayer(self)
            self.monitor_player.setAudioOutput(self.monitor_output)
            self.monitor_player.errorOccurred.connect(self.on_monitor_error)
            self.monitor_player.mediaStatusChanged.connect(self.on_monitor_status)
            self.monitor_player.setSource(source)
            return True
        except (OSError, RuntimeError, TypeError, ValueError):
            self.stop_monitor()
            return False

    def check_monitor_output(self):
        if self.monitor_output and device_id(self.monitor_output.device()) != self.monitor_key:
            self.stop_monitor()
            self.notice.emit("El audio sigue en el juego; la salida de escucha cambio")

    def on_monitor_error(self, _error, message):
        self.stop_monitor()
        self.notice.emit("El audio sigue en el juego; la escucha local fallo: " + message)

    def on_monitor_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.stop_monitor()

    def set_cable_volume(self, percent):
        self.cable_volume = percent / 100
        if self.mixer:
            self.mixer.set_gains(self.microphone_volume, self.cable_volume)

    def set_microphone_volume(self, percent):
        self.microphone_volume = percent / 100
        if self.mixer:
            self.mixer.set_gains(self.microphone_volume, self.cable_volume)

    def set_monitor_volume(self, percent):
        self.monitor_volume = percent / 100
        if self.monitor_output:
            self.monitor_output.setVolume(self.monitor_volume)

    def stop_monitor(self):
        if self.monitor_player:
            self.monitor_player.errorOccurred.disconnect(self.on_monitor_error)
            self.monitor_player.mediaStatusChanged.disconnect(self.on_monitor_status)
            self.monitor_player.stop()
            self.monitor_player.setAudioOutput(None)
            self.monitor_player.deleteLater()
            self.monitor_player = None
        if self.monitor_output:
            self.monitor_output.deviceChanged.disconnect(self.check_monitor_output)
            self.monitor_output.deleteLater()
            self.monitor_output = None
        self.monitor_key = ""

    def stop_clip(self):
        self.clip_timer.stop()
        if self.decoder:
            try:
                self.decoder.bufferReady.disconnect(self.pump_decoder)
                self.decoder.finished.disconnect(self.decoder_done)
                self.decoder.error.disconnect(self.on_decoder_error)
            except (TypeError, RuntimeError):
                pass
            self.decoder.stop()
            self.decoder.deleteLater()
            self.decoder = None
        self.decoder_finished = False
        if self.mixer:
            self.mixer.clear_clip()
        self.stop_monitor()
        self.status.emit("Detenido")

    def stop(self):
        self.stop_clip()

    def close(self):
        self.stop_clip()
        self.stop_bridge(False)


def tone_pcm(rate=48000, channels=2, seconds=2, sample_format=QAudioFormat.SampleFormat.Int16):
    data = bytearray()
    for i in range(int(rate * seconds)):
        # Two separated bursts permit detection of the actual route rather than noise.
        t = i / rate
        value = int(5000 * math.sin(2 * math.pi * 997 * t)) if 0.3 < t < 0.8 or 1.1 < t < 1.6 else 0
        if sample_format == QAudioFormat.SampleFormat.Float:
            packed = struct.pack("<f", value / 32768)
        elif sample_format == QAudioFormat.SampleFormat.Int32:
            packed = struct.pack("<i", value * 65536)
        elif sample_format == QAudioFormat.SampleFormat.UInt8:
            packed = struct.pack("<B", max(0, min(255, 128 + value // 256)))
        else:
            packed = struct.pack("<h", value)
        data.extend(packed * channels)
    return bytes(data)


def tone_detected(raw, rate=48000, channels=2, sample_format=QAudioFormat.SampleFormat.Int16):
    codes = {QAudioFormat.SampleFormat.Int16: ("h", 2, 1),
             QAudioFormat.SampleFormat.Float: ("f", 4, 32768),
             QAudioFormat.SampleFormat.Int32: ("i", 4, 1 / 65536),
             QAudioFormat.SampleFormat.UInt8: ("B", 1, 256)}
    code, width, scale = codes[sample_format]
    count = len(raw) // (width * channels)
    if count < rate // 2:
        return False
    samples = struct.unpack("<" + code * (count * channels), raw[:count * channels * width])[::channels]
    samples = [(v - (128 if code == "B" else 0)) * scale for v in samples]
    block = rate // 10
    hits, quiet = 0, 0
    for offset in range(0, len(samples) - block, block):
        window = samples[offset:offset + block]
        energy = sum(v * v for v in window) / block
        if energy < 400:
            quiet += 1
            continue
        real = sum(v * math.cos(2 * math.pi * 997 * i / rate) for i, v in enumerate(window))
        imag = sum(v * math.sin(2 * math.pi * 997 * i / rate) for i, v in enumerate(window))
        ratio = 2 * (real * real + imag * imag) / (block * block * energy)
        if ratio > 0.65:
            hits += 1
    return hits >= 5 and quiet >= 2


class Diagnostic(QObject):
    completed = pyqtSignal(bool, str)

    def __init__(self, devices, parent=None):
        super().__init__(parent)
        self.devices = devices
        self.source = self.sink = self.buffer = self.reader = None
        self.data = bytearray()
        self.key = ""
        self.running = False
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.finish)
        devices.changed.connect(self.guard)

    def guard(self):
        if self.running and not self.devices.available(self.key):
            self.abort("El cable se desconecto durante la prueba")

    def start(self, key):
        self.cancel()
        self.devices.refresh()
        if not self.devices.available(key):
            self.completed.emit(False, "No hay un par de endpoints VB-Cable disponible")
            return
        self.key = key
        output, input_device = self.devices.outputs[key], self.devices.pairs[key]
        output_format = output.preferredFormat()
        self.input_format = input_device.preferredFormat()
        if not output_format.isValid() or not self.input_format.isValid():
            self.completed.emit(False, "No se pudo determinar el formato del cable")
            return
        self.running = True
        self.data.clear()
        self.source = QAudioSource(input_device, self.input_format, self)
        self.source.stateChanged.connect(self.check_error)
        self.reader = self.source.start()
        if not self.reader:
            self.abort("No se pudo abrir CABLE Output. Revisa los permisos de microfono de Windows.")
            return
        self.reader.readyRead.connect(self.read)
        self.sink = QAudioSink(output, output_format, self)
        self.sink.stateChanged.connect(self.check_error)
        self.buffer = QBuffer(self)
        self.buffer.setData(QByteArray(tone_pcm(output_format.sampleRate(), output_format.channelCount(),
                                              sample_format=output_format.sampleFormat())))
        self.buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        self.sink.start(self.buffer)
        if self.running:
            self.timer.start(2800)

    def read(self):
        if self.reader and self.running:
            self.data.extend(bytes(self.reader.readAll()))

    def check_error(self, _state):
        if self.running and any(d and d.error() in (QAudio.Error.OpenError, QAudio.Error.IOError,
                                                    QAudio.Error.FatalError)
                                for d in (self.source, self.sink)):
            QTimer.singleShot(0, lambda: self.abort("No se pudo abrir el cable para la prueba"))

    def finish(self):
        if not self.running:
            return
        self.read()
        valid = tone_detected(self.data, self.input_format.sampleRate(), self.input_format.channelCount(),
                              self.input_format.sampleFormat())
        name = self.devices.pairs[self.key].description() if self.key in self.devices.pairs else "CABLE Output"
        self.cancel()
        self.completed.emit(valid, f"Selecciona {name} como microfono en el juego."
                            if valid else "No se recibio el tono. Revisa volumen, permisos y formato del cable.")

    def abort(self, message):
        if self.running:
            self.cancel()
            self.completed.emit(False, message)

    def cancel(self):
        self.running = False
        self.timer.stop()
        for device in (self.source, self.sink):
            if device:
                device.stop()
                device.deleteLater()
        if self.buffer:
            self.buffer.close()
            self.buffer.deleteLater()
        self.source = self.sink = self.buffer = self.reader = None
