from __future__ import annotations

import re
import winreg
from dataclasses import dataclass

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtMultimedia import QAudioDevice, QMediaDevices

BASE = r"SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio"
DESCRIPTION = "{a45c254e-df1c-4efd-8020-67d146a850e0},2"
INTERFACE = "{b3f8fa53-0004-438e-9003-51a46e139bfc},6"
INF = "{a8b865dd-2e3d-4094-ad97-e593a70c75d6},5"


def cable_family(name, direction):
    match = re.fullmatch(r"CABLE(?:-([ABCD]))? " + direction +
                         r"(?: \(VB-Audio [^()]*Cable[^()]*\))?", name, re.I)
    return (match.group(1) or "standard").upper() if match else None


@dataclass
class Endpoint:
    guid: str
    direction: str
    family: str
    active: bool


def native_endpoints():
    result = []
    for flow, direction in (("Render", "Input"), ("Capture", "Output")):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, BASE + "\\" + flow) as root:
                for i in range(winreg.QueryInfoKey(root)[0]):
                    guid = winreg.EnumKey(root, i)
                    try:
                        with winreg.OpenKey(root, guid) as device:
                            state = winreg.QueryValueEx(device, "DeviceState")[0]
                            with winreg.OpenKey(device, "Properties") as props:
                                def value(key):
                                    try:
                                        return str(winreg.QueryValueEx(props, key)[0])
                                    except OSError:
                                        return ""
                                family = cable_family(value(DESCRIPTION), direction)
                                driver = value(INTERFACE).lower()
                                inf = value(INF).lower()
                                trusted = ("vb-audio" in driver and "cable" in driver
                                           and "voicemeeter" not in driver)
                                # Never trust the user-editable endpoint display name alone.
                                if family and trusted and ("vbmme" in inf or "vbaudio" in inf or "oem" in inf):
                                    result.append(Endpoint(guid.lower(), flow, family, state == 1))
                    except OSError:
                        continue
        except FileNotFoundError:
            continue
    return result


def device_id(device):
    return bytes(device.id()).hex()


def endpoint_for(device, endpoints, flow):
    native_id = bytes(device.id()).decode("utf-8", errors="replace").lower()
    direction = "Input" if flow == "Render" else "Output"
    for endpoint in endpoints:
        if (endpoint.direction == flow and endpoint.active and endpoint.guid in native_id
                and cable_family(device.description(), direction) == endpoint.family):
            return endpoint
    return None


class Devices(QObject):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.media = QMediaDevices(self)
        self.outputs: dict[str, QAudioDevice] = {}
        self.pairs: dict[str, QAudioDevice] = {}
        self.installed = False
        self.error = ""
        self.default_input_key = ""
        self.media.audioOutputsChanged.connect(self.refresh)
        self.media.audioInputsChanged.connect(self.refresh)
        self.timer = QTimer(self)
        self.timer.setInterval(1500)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()

    def refresh(self):
        old = (tuple(self.outputs), tuple((k, device_id(v)) for k, v in self.pairs.items()),
               self.default_input_key, self.error)
        self.outputs, self.pairs = {}, {}
        try:
            endpoints = native_endpoints()
            self.installed = bool(endpoints)
            inputs = [(d, endpoint_for(d, endpoints, "Capture")) for d in self.media.audioInputs()]
            for device in self.media.audioOutputs():
                endpoint = endpoint_for(device, endpoints, "Render")
                if endpoint is not None:
                    key = device_id(device)
                    self.outputs[key] = device
                    matches = [d for d, e in inputs if e and e.family == endpoint.family]
                    if len(matches) == 1:
                        self.pairs[key] = matches[0]
            self.error = ""
            microphone = self.media.defaultAudioInput()
            self.default_input_key = "" if microphone.isNull() else device_id(microphone)
        except OSError as exc:
            self.error = f"No se pueden verificar los dispositivos: {exc}"
        new = (tuple(self.outputs), tuple((k, device_id(v)) for k, v in self.pairs.items()),
               self.default_input_key, self.error)
        if old != new:
            self.changed.emit()

    def available(self, key):
        return key in self.outputs and key in self.pairs

    def default_output(self):
        return self.media.defaultAudioOutput()

    def default_input(self):
        return self.media.defaultAudioInput()

    def check_code(self):
        self.refresh()
        if any(self.available(k) for k in self.outputs):
            return 0
        return 11 if self.installed or self.error else 10
