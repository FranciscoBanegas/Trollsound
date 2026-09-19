from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import logging
import time

from PyQt6.QtCore import QAbstractNativeEventFilter, QCoreApplication, QObject, Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence

WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000
FIRST_HOTKEY_ID = 0x1000
STOP_HOTKEY_ID = FIRST_HOTKEY_ID - 1
STOP_ACTION_ID = "__stop_audio__"
DEBOUNCE_NS = 75_000_000

_ALIASES = {
    "control": "Ctrl", "ctrl": "Ctrl", "left ctrl": "Ctrl", "right ctrl": "Ctrl",
    "alt": "Alt", "left alt": "Alt", "right alt": "Alt",
    "shift": "Shift", "left shift": "Shift", "right shift": "Shift",
    "escape": "Esc", "page up": "PgUp", "page down": "PgDown",
    "enter": "Return", "return": "Return", "space": "Space", "delete": "Del",
    "insert": "Ins", "backspace": "Backspace", "plus": "+", "comma": ",",
}

_SPECIAL_VK = {
    Qt.Key.Key_Backspace.value: 0x08,
    Qt.Key.Key_Tab.value: 0x09,
    Qt.Key.Key_Return.value: 0x0D,
    Qt.Key.Key_Enter.value: 0x0D,
    Qt.Key.Key_Pause.value: 0x13,
    Qt.Key.Key_Escape.value: 0x1B,
    Qt.Key.Key_Space.value: 0x20,
    Qt.Key.Key_PageUp.value: 0x21,
    Qt.Key.Key_PageDown.value: 0x22,
    Qt.Key.Key_End.value: 0x23,
    Qt.Key.Key_Home.value: 0x24,
    Qt.Key.Key_Left.value: 0x25,
    Qt.Key.Key_Up.value: 0x26,
    Qt.Key.Key_Right.value: 0x27,
    Qt.Key.Key_Down.value: 0x28,
    Qt.Key.Key_Insert.value: 0x2D,
    Qt.Key.Key_Delete.value: 0x2E,
}


@dataclass(frozen=True)
class NativeHotkey:
    canonical: str
    modifiers: int
    virtual_key: int


class WinHotkeyApi:
    def __init__(self):
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        self.user32.RegisterHotKey.restype = wintypes.BOOL
        self.user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        self.user32.UnregisterHotKey.restype = wintypes.BOOL
        self.user32.GetKeyboardLayout.argtypes = [wintypes.DWORD]
        self.user32.GetKeyboardLayout.restype = wintypes.HKL
        self.user32.VkKeyScanExW.argtypes = [wintypes.WCHAR, wintypes.HKL]
        self.user32.VkKeyScanExW.restype = ctypes.c_short

    def register(self, hwnd, identifier, modifiers, virtual_key):
        ctypes.set_last_error(0)
        ok = bool(self.user32.RegisterHotKey(hwnd, identifier, modifiers, virtual_key))
        return ok, ctypes.get_last_error()

    def unregister(self, hwnd, identifier):
        return bool(self.user32.UnregisterHotKey(hwnd, identifier))

    def scan_character(self, character):
        return int(self.user32.VkKeyScanExW(character, self.user32.GetKeyboardLayout(0)))


def _portable_text(text):
    parts = [part.strip() for part in text.strip().split("+")]
    if len(parts) > 1 and parts[-1] == "":
        parts[-1] = "+"
    return "+".join(_ALIASES.get(part.lower(), part) for part in parts)


def parse_hotkey(text, api=None):
    if not isinstance(text, str) or not text.strip() or "," in text:
        raise ValueError("Usa una sola combinacion simultanea")
    sequence = QKeySequence.fromString(text.strip(), QKeySequence.SequenceFormat.PortableText)
    if sequence.isEmpty() or sequence[0].key() == Qt.Key.Key_unknown:
        sequence = QKeySequence.fromString(_portable_text(text), QKeySequence.SequenceFormat.PortableText)
    if sequence.isEmpty() or sequence.count() != 1:
        raise ValueError("Combinacion no reconocida; vuelve a capturarla")
    combination = sequence[0]
    key = combination.key().value
    modifiers = combination.keyboardModifiers()
    allowed = (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier |
               Qt.KeyboardModifier.ShiftModifier)
    if modifiers & ~allowed:
        raise ValueError("Solo se admiten Ctrl, Alt y Shift como modificadores")
    qt_to_native = {
        Qt.KeyboardModifier.ControlModifier: MOD_CONTROL,
        Qt.KeyboardModifier.AltModifier: MOD_ALT,
        Qt.KeyboardModifier.ShiftModifier: MOD_SHIFT,
    }
    native_modifiers = MOD_NOREPEAT
    for qt_modifier, native_modifier in qt_to_native.items():
        if modifiers & qt_modifier:
            native_modifiers |= native_modifier
    if Qt.Key.Key_F1.value <= key <= Qt.Key.Key_F35.value:
        number = key - Qt.Key.Key_F1.value + 1
        if number == 12:
            raise ValueError("F12 esta reservada por Windows")
        if number > 24:
            raise ValueError("Windows solo admite las teclas F1 a F24")
        virtual_key = 0x70 + number - 1
    elif key in _SPECIAL_VK:
        virtual_key = _SPECIAL_VK[key]
    elif ord("A") <= key <= ord("Z") or ord("0") <= key <= ord("9"):
        virtual_key = key
    elif 0x20 <= key <= 0x10FFFF:
        scanner = api or WinHotkeyApi()
        character = chr(key).lower() if chr(key).isalpha() else chr(key)
        scanned = scanner.scan_character(character)
        if scanned == -1:
            raise ValueError("La tecla no existe en la distribucion actual del teclado")
        virtual_key = scanned & 0xFF
        implicit = (scanned >> 8) & 0xFF
        if implicit & 1:
            native_modifiers |= MOD_SHIFT
        if implicit & 2:
            native_modifiers |= MOD_CONTROL
        if implicit & 4:
            native_modifiers |= MOD_ALT
    else:
        raise ValueError("Tecla no compatible con los atajos globales de Windows")
    is_function = Qt.Key.Key_F1.value <= key <= Qt.Key.Key_F35.value
    if not is_function and not (native_modifiers & (MOD_CONTROL | MOD_ALT | MOD_SHIFT)):
        raise ValueError("Agrega Ctrl, Alt o Shift a la tecla")
    canonical = sequence.toString(QKeySequence.SequenceFormat.PortableText)
    reserved = {"Alt+F4", "Alt+Tab", "Ctrl+Esc", "Ctrl+Shift+Esc", "Ctrl+Alt+Del"}
    if canonical in reserved:
        raise ValueError("Esta combinacion esta reservada por Windows")
    return NativeHotkey(canonical, native_modifiers, virtual_key)


def normalize_hotkey(text):
    return parse_hotkey(text).canonical


class _NativeFilter(QAbstractNativeEventFilter):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner

    def nativeEventFilter(self, event_type, message):
        try:
            msg = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG)).contents
            if msg.message == WM_HOTKEY:
                self.owner.dispatch(int(msg.wParam))
        except (TypeError, ValueError, OSError):
            logging.exception("No se pudo procesar WM_HOTKEY")
        return False, 0


class Hotkeys(QObject):
    triggered = pyqtSignal(str, int)
    failure = pyqtSignal(str)

    def __init__(self, parent=None, api=None):
        super().__init__(parent)
        self.api = api or WinHotkeyApi()
        self.hwnd = None
        self.handles = {}
        self.statuses = {}
        self.status_details = {}
        self.last_activation = {}
        self.generation = 0
        self.closed = False
        self.filter = _NativeFilter(self)
        app = QCoreApplication.instance()
        if app is None:
            raise RuntimeError("Hotkeys requiere una aplicacion Qt activa")
        app.installNativeEventFilter(self.filter)

    def set_window(self, hwnd):
        hwnd = wintypes.HWND(int(hwnd))
        if self.hwnd and self.hwnd.value != hwnd.value:
            self.clear()
        self.hwnd = hwnd

    def clear(self):
        self.generation += 1
        if self.hwnd:
            for identifier in tuple(self.handles):
                if not self.api.unregister(self.hwnd, identifier):
                    logging.warning("Windows no pudo liberar el atajo %s", identifier)
        self.handles.clear()
        self.last_activation.clear()
        self.statuses.clear()
        self.status_details.clear()

    def register(self, macros, stop_hotkey=""):
        self.clear()
        generation = self.generation
        if not self.hwnd:
            for macro in macros:
                self.statuses[macro.id] = "Error de registro"
                self.status_details[macro.id] = "La ventana nativa aun no esta disponible"
            return
        if stop_hotkey:
            try:
                parsed = parse_hotkey(stop_hotkey, self.api)
                ok, error = self.api.register(self.hwnd, STOP_HOTKEY_ID,
                                              parsed.modifiers, parsed.virtual_key)
                if ok:
                    self.handles[STOP_HOTKEY_ID] = (STOP_ACTION_ID, generation)
                    self.statuses[STOP_ACTION_ID] = "Registrada"
                    self.status_details[STOP_ACTION_ID] = parsed.canonical
                else:
                    self.statuses[STOP_ACTION_ID] = "Conflicto"
                    self.status_details[STOP_ACTION_ID] = (
                        "Windows rechazo la combinacion de detener audio; "
                        f"probablemente ya esta en uso (error {error})")
                    logging.warning("Atajo de detencion rechazado; error Win32 %s", error)
            except ValueError as exc:
                self.statuses[STOP_ACTION_ID] = "Reasignar teclas"
                self.status_details[STOP_ACTION_ID] = str(exc)
        for offset, macro in enumerate(macros):
            identifier = FIRST_HOTKEY_ID + offset
            try:
                parsed = parse_hotkey(macro.hotkey, self.api)
            except ValueError as exc:
                self.statuses[macro.id] = "Reasignar teclas"
                self.status_details[macro.id] = str(exc)
                continue
            ok, error = self.api.register(self.hwnd, identifier, parsed.modifiers, parsed.virtual_key)
            if not ok:
                self.statuses[macro.id] = "Conflicto"
                self.status_details[macro.id] = ("Windows rechazo la combinacion; probablemente ya esta en uso "
                                                 f"(error {error})")
                logging.warning("Atajo rechazado para macro %s; error Win32 %s", macro.id, error)
                continue
            self.handles[identifier] = (macro.id, generation)
            self.statuses[macro.id] = "Registrada"
            self.status_details[macro.id] = parsed.canonical

    def dispatch(self, identifier):
        registered = self.handles.get(identifier)
        if registered is None:
            return
        now = time.monotonic_ns()
        if now - self.last_activation.get(identifier, 0) < DEBOUNCE_NS:
            return
        self.last_activation[identifier] = now
        macro_id, generation = registered
        if generation != self.generation:
            return
        if macro_id == STOP_ACTION_ID:
            logging.info("Atajo de detencion activado")
        else:
            logging.info("Macro activada: %s", macro_id)
        self.triggered.emit(macro_id, generation)

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.clear()
        app = QCoreApplication.instance()
        if app is not None:
            app.removeNativeEventFilter(self.filter)
