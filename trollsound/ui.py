from pathlib import Path
import logging

from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices, QKeySequence
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow,
    QKeySequenceEdit, QMenu, QMessageBox, QPushButton, QSlider, QStyle, QSystemTrayIcon, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget)

from .audio import Diagnostic, Player, Validator
from .devices import Devices
from .hotkeys import STOP_ACTION_ID, Hotkeys, normalize_hotkey
from .storage import Library
from . import __version__

DONATION_URL = "https://cafecito.app/franciscobanegas"
CREATOR_NAME = "Francisco Banegas"


class HotkeyEdit(QKeySequenceEdit):
    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self.setMaximumSequenceLength(1)
        self.setClearButtonEnabled(True)
        if text:
            try:
                self.setKeySequence(QKeySequence(normalize_hotkey(text)))
            except ValueError:
                pass

    def text(self):
        return self.keySequence().toString(QKeySequence.SequenceFormat.PortableText)

    def setText(self, text):
        self.setKeySequence(QKeySequence.fromString(text, QKeySequence.SequenceFormat.PortableText))


class MacroDialog(QDialog):
    def __init__(self, library, hotkeys, macro=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Editar macro" if macro else "Agregar macro")
        self.setMinimumWidth(480)
        self.library, self.hotkeys, self.macro = library, hotkeys, macro
        self.source = library.path(macro) if macro else None
        self.validator = Validator(self)
        self.validator.completed.connect(self.validated)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(macro.name if macro else "")
        self.name.setMaxLength(100)
        self.combo = HotkeyEdit(macro.hotkey if macro else "")
        self.capture = QPushButton("Capturar teclas")
        self.capture.clicked.connect(self.capture_keys)
        keys = QHBoxLayout()
        keys.addWidget(self.combo, 1)
        keys.addWidget(self.capture)
        self.file_label = QLineEdit(str(self.source) if self.source else "")
        self.file_label.setReadOnly(True)
        self.browse = QPushButton("Seleccionar audio")
        self.browse.clicked.connect(self.choose_file)
        audio = QHBoxLayout()
        audio.addWidget(self.file_label, 1)
        audio.addWidget(self.browse)
        form.addRow("Nombre", self.name)
        form.addRow("Combinacion", keys)
        form.addRow("Archivo", audio)
        layout.addLayout(form)
        self.message = QLabel("")
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText("Guardar")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        self.buttons.accepted.connect(self.submit)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.finished.connect(self.cleanup)
        if macro and not self.combo.text():
            self.message.setText("La combinacion guardada no es compatible; vuelve a capturarla.")

    def choose_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Seleccionar audio", "", "Audio (*.wav *.mp3 *.ogg *.flac)")
        if path:
            self.source = Path(path)
            self.file_label.setText(path)
            if not self.name.text():
                self.name.setText(self.source.stem)

    def capture_keys(self):
        self.combo.clear()
        self.combo.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.message.setText("Pulsa la combinacion; se guardara una sola secuencia.")

    def submit(self):
        try:
            hotkey = normalize_hotkey(self.combo.text())
            if not self.name.text().strip() or self.source is None or not self.source.is_file():
                raise ValueError("Completa el nombre y selecciona un audio existente")
            if any(m.hotkey == hotkey and (not self.macro or m.id != self.macro.id)
                   for m in self.library.macros):
                raise ValueError("La combinacion ya pertenece a otra macro")
            self.combo.setText(hotkey)
            self.set_busy(True)
            self.message.setText("Validando audio...")
            self.validator.validate(self.source)
        except (OSError, ValueError) as exc:
            self.message.setText(str(exc))

    def set_busy(self, busy):
        for widget in (self.name, self.combo, self.browse, self.capture,
                       self.buttons.button(QDialogButtonBox.StandardButton.Save)):
            widget.setEnabled(not busy)

    def validated(self, valid, message):
        self.set_busy(False)
        if not valid:
            self.message.setText("Audio no valido: " + message)
            return
        try:
            self.library.put(self.name.text(), self.combo.text(), self.source,
                             self.macro.id if self.macro else None)
            self.accept()
        except (OSError, ValueError) as exc:
            self.message.setText(str(exc))

    def cleanup(self, _result):
        self.validator.cancel()


class SettingsDialog(QDialog):
    def __init__(self, library, stop_status="", stop_detail="", parent=None):
        super().__init__(parent)
        self.library = library
        self.setWindowTitle("Configuracion")
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.addRow("Programa", QLabel("Trollsound"))
        form.addRow("Version", QLabel(__version__))
        form.addRow("Creador", QLabel(CREATOR_NAME))
        self.stop_combo = HotkeyEdit(library.stop_hotkey)
        form.addRow("Detener audio", self.stop_combo)
        layout.addLayout(form)
        self.stop_state = QLabel("Estado del atajo: " + (stop_status or "Sin asignar"))
        self.stop_state.setToolTip(stop_detail)
        self.stop_state.setWordWrap(True)
        layout.addWidget(self.stop_state)
        donate = QPushButton("Donar con Cafecito")
        donate.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(DONATION_URL)))
        layout.addWidget(donate)
        self.message = QLabel("")
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Guardar")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        buttons.accepted.connect(self.submit)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def submit(self):
        try:
            text = self.stop_combo.text().strip()
            hotkey = normalize_hotkey(text) if text else ""
            self.library.set_stop_hotkey(hotkey)
            self.accept()
        except (OSError, ValueError) as exc:
            self.message.setText(str(exc))


class Window(QMainWindow):
    def __init__(self, library=None, devices=None, hotkeys=None):
        super().__init__()
        self.library = library or Library()
        self.devices = devices or Devices(self)
        self.hotkeys = hotkeys or Hotkeys(self)
        self.player = Player(self.devices, self)
        self.diagnostic = Diagnostic(self.devices, self)
        self.paused = False
        self.editing = False
        self.quitting = False
        self.ready_before = False
        self.volume_save_timer = QTimer(self)
        self.volume_save_timer.setSingleShot(True)
        self.volume_save_timer.setInterval(300)
        self.volume_save_timer.timeout.connect(self.persist_volumes)
        self.setWindowTitle("Trollsound")
        self.resize(960, 600)
        self.setMinimumSize(720, 460)
        self.setWindowIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaVolume))
        if hasattr(self.hotkeys, "set_window"):
            self.hotkeys.set_window(int(self.winId()))
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)
        top = QHBoxLayout()
        title = QLabel("Trollsound")
        title.setStyleSheet("font-size: 24px; font-weight: 600; color: #146B61;")
        top.addWidget(title)
        top.addStretch()
        self.settings_button = QPushButton("Configuracion")
        self.settings_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView))
        self.settings_button.clicked.connect(self.open_settings)
        top.addWidget(self.settings_button)
        self.pause = QCheckBox("Pausar macros")
        self.pause.toggled.connect(self.set_paused)
        top.addWidget(self.pause)
        layout.addLayout(top)
        cable = QHBoxLayout()
        cable.addWidget(QLabel("Cable virtual"))
        self.selector = QComboBox()
        self.selector.setMinimumWidth(300)
        self.selector.currentIndexChanged.connect(self.select_device)
        cable.addWidget(self.selector, 1)
        self.test_button = QPushButton("Probar conexion")
        self.test_button.clicked.connect(self.test_route)
        cable.addWidget(self.test_button)
        self.install_button = QPushButton("Instalar VB-Cable")
        self.install_button.clicked.connect(self.install_cable)
        cable.addWidget(self.install_button)
        layout.addLayout(cable)
        self.connection = QLabel()
        self.connection.setWordWrap(True)
        layout.addWidget(self.connection)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Nombre", "Combinacion", "Audio", "Estado"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.doubleClicked.connect(lambda _: self.edit_macro())
        self.table.itemSelectionChanged.connect(self.update_buttons)
        layout.addWidget(self.table, 1)
        toolbar = QHBoxLayout()
        self.add_button = QPushButton("Agregar macro")
        self.add_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogNewFolder))
        self.add_button.clicked.connect(lambda: self.edit_macro(new=True))
        toolbar.addWidget(self.add_button)
        self.edit_button = QPushButton("Editar")
        self.edit_button.clicked.connect(self.edit_macro)
        toolbar.addWidget(self.edit_button)
        self.toggle_button = QPushButton("Activar / desactivar")
        self.toggle_button.clicked.connect(self.toggle_macro)
        toolbar.addWidget(self.toggle_button)
        self.delete_button = self.icon_button(QStyle.StandardPixmap.SP_TrashIcon, "Eliminar macro", self.delete_macro)
        toolbar.addWidget(self.delete_button)
        toolbar.addStretch()
        self.play_button = self.icon_button(QStyle.StandardPixmap.SP_MediaPlay, "Probar macro", self.preview)
        toolbar.addWidget(self.play_button)
        toolbar.addWidget(self.icon_button(QStyle.StandardPixmap.SP_MediaStop, "Detener audio", self.stop_audio))
        layout.addLayout(toolbar)
        self.playback = QLabel("Detenido")
        layout.addWidget(self.playback)
        bottom = QHBoxLayout()
        bottom.addWidget(QLabel("Micrófono"))
        self.microphone_volume = QSlider(Qt.Orientation.Horizontal)
        self.microphone_volume.setRange(0, 100)
        self.microphone_volume.setValue(self.library.microphone_volume)
        self.microphone_volume.setFixedWidth(110)
        self.microphone_volume.setAccessibleName("Volumen del microfono en la mezcla")
        self.microphone_volume.valueChanged.connect(self.change_microphone_volume)
        self.player.set_microphone_volume(self.library.microphone_volume)
        bottom.addWidget(self.microphone_volume)
        bottom.addWidget(QLabel("Sonido"))
        self.cable_volume = QSlider(Qt.Orientation.Horizontal)
        self.cable_volume.setRange(0, 100)
        self.cable_volume.setValue(self.library.cable_volume)
        self.cable_volume.setFixedWidth(110)
        self.cable_volume.setAccessibleName("Volumen del sonido enviado al juego")
        self.cable_volume.valueChanged.connect(self.change_cable_volume)
        self.player.set_cable_volume(self.library.cable_volume)
        bottom.addWidget(self.cable_volume)
        bottom.addWidget(QLabel("Escucha"))
        self.monitor_volume = QSlider(Qt.Orientation.Horizontal)
        self.monitor_volume.setRange(0, 100)
        self.monitor_volume.setValue(self.library.monitor_volume)
        self.monitor_volume.setFixedWidth(110)
        self.monitor_volume.setAccessibleName("Volumen de escucha local")
        self.monitor_volume.valueChanged.connect(self.change_monitor_volume)
        self.player.set_monitor_volume(self.library.monitor_volume)
        bottom.addWidget(self.monitor_volume)
        layout.addLayout(bottom)
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip("Trollsound")
        menu = QMenu(self)
        menu.addAction("Abrir Trollsound", self.reveal)
        menu.addAction("Configuracion", self.open_settings)
        self.pause_action = menu.addAction("Pausar macros")
        self.pause_action.setCheckable(True)
        self.pause_action.toggled.connect(self.pause.setChecked)
        menu.addAction("Detener audio", self.stop_audio)
        menu.addSeparator()
        menu.addAction("Salir", self.shutdown)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.reveal() if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None)
        tray_available = QSystemTrayIcon.isSystemTrayAvailable()
        QApplication.instance().setQuitOnLastWindowClosed(not tray_available)
        if tray_available:
            self.tray.show()
        self.hotkeys.triggered.connect(self.trigger)
        self.hotkeys.failure.connect(self.hotkey_error)
        self.player.status.connect(self.playback.setText)
        self.player.failure.connect(self.show_error)
        self.player.notice.connect(lambda message: self.statusBar().showMessage(message, 8000))
        self.player.bridge_changed.connect(self.bridge_changed)
        self.diagnostic.completed.connect(self.diagnosed)
        self.devices.changed.connect(self.refresh_devices)
        self.refresh_table()
        self.refresh_devices()
        if self.library.load_error:
            QTimer.singleShot(0, lambda: self.show_error(self.library.load_error))

    def icon_button(self, icon, tooltip, callback):
        button = QPushButton(self.style().standardIcon(icon), "")
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.setFixedSize(36, 32)
        button.clicked.connect(callback)
        return button

    def change_cable_volume(self, value):
        self.player.set_cable_volume(value)
        self.library.cable_volume = value
        self.volume_save_timer.start()

    def change_microphone_volume(self, value):
        self.player.set_microphone_volume(value)
        self.library.microphone_volume = value
        self.volume_save_timer.start()

    def change_monitor_volume(self, value):
        self.player.set_monitor_volume(value)
        self.library.monitor_volume = value
        self.volume_save_timer.start()

    def persist_volumes(self, notify=True):
        if self.library.read_only:
            return
        try:
            self.library.save()
        except (OSError, ValueError) as exc:
            if notify:
                self.show_error(str(exc))
            else:
                logging.warning("No se pudieron guardar los volumenes: %s", exc)

    def selected_macro(self):
        row = self.table.currentRow()
        return self.library.macros[row] if 0 <= row < len(self.library.macros) else None

    def refresh_table(self):
        selected = self.selected_macro()
        self.table.setRowCount(len(self.library.macros))
        for row, macro in enumerate(self.library.macros):
            state, detail = self.macro_state(macro)
            for col, text in enumerate((macro.name, macro.hotkey, self.library.path(macro).name, state)):
                item = QTableWidgetItem(text)
                item.setToolTip(detail if col == 3 else text)
                self.table.setItem(row, col, item)
            if selected and selected.id == macro.id:
                self.table.selectRow(row)
        self.update_buttons()

    def macro_state(self, macro):
        if not self.library.path(macro).is_file():
            return "Archivo ausente", "La copia administrada del audio no existe"
        if not macro.enabled:
            return "Desactivada", "La macro esta desactivada"
        if self.paused:
            return "Pausada", "Las macros estan pausadas"
        if self.editing or self.diagnostic.running:
            return "Suspendida", "Los atajos se suspenden durante esta operacion"
        if not self.devices.available(self.library.selected_device_id):
            return "Sin cable", "Selecciona un par VB-Cable operativo"
        if not self.player.bridge_ready:
            return "Sin micrófono", self.player.bridge_error or "La mezcla de audio no esta activa"
        status = self.hotkeys.statuses.get(macro.id, "No registrada")
        return status, self.hotkeys.status_details.get(macro.id, status)

    def update_buttons(self):
        selected = self.selected_macro() is not None
        writable = not self.library.read_only
        self.add_button.setEnabled(writable)
        for button in (self.edit_button, self.toggle_button, self.delete_button):
            button.setEnabled(selected and writable)
        self.play_button.setEnabled(selected and self.player.bridge_ready
                                    and not self.diagnostic.running)

    def refresh_devices(self):
        key = self.library.selected_device_id
        self.selector.blockSignals(True)
        self.selector.clear()
        self.selector.addItem("Seleccionar cable..." if self.devices.outputs else "VB-Cable no disponible", "")
        for device_key, device in self.devices.outputs.items():
            self.selector.addItem(device.description(), device_key)
        index = self.selector.findData(key)
        self.selector.setCurrentIndex(max(index, 0))
        self.selector.blockSignals(False)
        ready = self.devices.available(key)
        self.player.select(key)
        if self.ready_before and not ready:
            self.pause.setChecked(True)
        self.ready_before = ready
        if ready and self.player.bridge_ready:
            self.connection.setText(f"Mezcla activa: {self.player.microphone_name} + sonidos -> "
                                    f"{self.devices.pairs[key].description()}")
        elif ready:
            self.connection.setText(self.player.bridge_error or "No se pudo iniciar la mezcla")
        elif self.devices.error:
            self.connection.setText(self.devices.error)
        elif key:
            self.connection.setText("El cable guardado no esta disponible. Selecciona un cable operativo.")
        else:
            self.connection.setText("Selecciona VB-Cable para activar las macros.")
        self.test_button.setEnabled(ready and not self.diagnostic.running)
        self.install_button.setVisible(not ready)
        self.sync_hotkeys()
        self.update_buttons()

    def select_device(self, _index):
        old = self.library.selected_device_id
        self.library.selected_device_id = self.selector.currentData() or ""
        try:
            self.library.save()
        except (OSError, ValueError) as exc:
            self.library.selected_device_id = old
            self.show_error(str(exc))
        self.diagnostic.cancel()
        self.refresh_devices()

    def sync_hotkeys(self):
        active = (not self.paused and not self.editing and not self.diagnostic.running
                  and not self.library.read_only and self.player.bridge_ready)
        macros = [m for m in self.library.macros if m.enabled and self.library.path(m).is_file()] if active else []
        stop_hotkey = (self.library.stop_hotkey if not self.editing and not self.diagnostic.running
                       and not self.library.read_only else "")
        self.hotkeys.register(macros, stop_hotkey)
        self.update_macro_states()

    def update_macro_states(self):
        for row, macro in enumerate(self.library.macros):
            item = self.table.item(row, 3)
            if item:
                state, detail = self.macro_state(macro)
                item.setText(state)
                item.setToolTip(detail)

    def trigger(self, macro_id, generation):
        if generation != self.hotkeys.generation:
            return
        if macro_id == STOP_ACTION_ID:
            self.stop_audio()
            return
        if self.paused or self.editing or self.diagnostic.running:
            return
        macro = next((m for m in self.library.macros if m.id == macro_id and m.enabled), None)
        if macro:
            self.player.play(self.library.path(macro))

    def set_paused(self, value):
        self.paused = value
        self.pause_action.blockSignals(True)
        self.pause_action.setChecked(value)
        self.pause_action.blockSignals(False)
        if value:
            self.stop_audio()
        self.sync_hotkeys()

    def open_settings(self):
        if self.editing:
            return
        status = self.hotkeys.statuses.get(STOP_ACTION_ID, "Sin asignar")
        detail = self.hotkeys.status_details.get(STOP_ACTION_ID, "")
        self.editing = True
        self.sync_hotkeys()
        dialog = SettingsDialog(self.library, status, detail, self)
        dialog.exec()
        dialog.deleteLater()
        self.editing = False
        self.sync_hotkeys()

    def edit_macro(self, _checked=False, new=False):
        macro = None if new else self.selected_macro()
        if not new and not macro:
            return
        self.editing = True
        self.stop_audio()
        self.sync_hotkeys()
        dialog = MacroDialog(self.library, self.hotkeys, macro, self)
        dialog.exec()
        dialog.deleteLater()
        self.editing = False
        self.refresh_table()
        self.sync_hotkeys()

    def toggle_macro(self):
        macro = self.selected_macro()
        if macro:
            try:
                self.library.toggle(macro.id)
                self.refresh_table()
                self.sync_hotkeys()
            except (OSError, ValueError) as exc:
                self.show_error(str(exc))

    def delete_macro(self):
        macro = self.selected_macro()
        if macro and QMessageBox.question(self, "Eliminar macro", f"Eliminar {macro.name} y su copia de audio?",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                         QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.stop_audio()
            try:
                self.library.remove(macro.id)
                self.refresh_table()
                self.sync_hotkeys()
            except (OSError, ValueError) as exc:
                self.show_error(str(exc))

    def preview(self):
        macro = self.selected_macro()
        if macro:
            self.player.play(self.library.path(macro))

    def stop_audio(self):
        self.player.stop_clip()
        was_running = self.diagnostic.running
        self.diagnostic.cancel()
        if was_running:
            self.player.resume_bridge()
            self.test_button.setEnabled(self.devices.available(self.library.selected_device_id))
            self.sync_hotkeys()
            self.update_buttons()

    def test_route(self):
        self.player.suspend_bridge()
        self.hotkeys.clear()
        self.test_button.setEnabled(False)
        self.connection.setText("Comprobando el recorrido del audio...")
        self.diagnostic.start(self.library.selected_device_id)
        self.update_macro_states()
        self.update_buttons()

    def diagnosed(self, valid, message):
        self.player.resume_bridge()
        prefix = "Conexion verificada. " if valid else "Prueba fallida. "
        self.connection.setText(prefix + message)
        self.test_button.setEnabled(self.devices.available(self.library.selected_device_id))
        self.sync_hotkeys()
        self.update_buttons()

    def install_cable(self):
        from .installer import offer_install
        offer_install(self)

    def hotkey_error(self, message):
        self.paused = True
        self.pause.blockSignals(True)
        self.pause.setChecked(True)
        self.pause.blockSignals(False)
        self.show_error(message)

    def bridge_changed(self, ready, message, microphone):
        key = self.library.selected_device_id
        if ready and self.devices.available(key):
            self.connection.setText(f"Mezcla activa: {microphone} + sonidos -> "
                                    f"{self.devices.pairs[key].description()}")
        elif message and not self.diagnostic.running:
            self.connection.setText(message)
        self.sync_hotkeys()
        self.update_buttons()

    def show_error(self, message):
        self.statusBar().showMessage(message)
        if self.isVisible():
            QMessageBox.warning(self, "Trollsound", message)
        else:
            self.tray.showMessage("Trollsound", message, QSystemTrayIcon.MessageIcon.Warning)

    def reveal(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        if not self.quitting and self.library.minimize_to_tray and self.tray.isVisible():
            self.hide()
            event.ignore()
        else:
            self.cleanup()
            event.accept()

    def cleanup(self):
        if self.volume_save_timer.isActive():
            self.volume_save_timer.stop()
            self.persist_volumes(False)
        self.hotkeys.close()
        self.player.close()
        self.diagnostic.cancel()
        self.tray.hide()

    def shutdown(self):
        self.quitting = True
        self.cleanup()
        QApplication.instance().quit()
