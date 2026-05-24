# -*- coding: utf-8 -*-
# ═══════════════════════════════════════════════════════════════════════════
# SEGE OPEN SOURCE — MACRO MODULE
# ═══════════════════════════════════════════════════════════════════════════
#
# EN:
#   This module is part of the SEGE open-source macro framework for
#   Knight Online. It defines a single automated behavior (a "macro") plus
#   its PyQt5 configuration widget. The macro is loaded at runtime by the
#   module registry (segesource/app/modules.py) and reacts to a configurable
#   hotkey defined by the user in the UI.
#
#   Architecture contract every macro module must follow:
#     - exports a `*Macro` class with `.start()` and `.stop()` methods
#     - exports a `*Widget` class (QWidget subclass) for configuration
#     - reads/writes its persistent state via the shared settings dict
#     - uses `drivers.clicksend` for keyboard/mouse output (Interception
#       driver wrapper), never raw pyautogui inside hotpath
#
#   This file ships under the MIT License (see LICENSE in the repo root).
#   It is provided for EDUCATIONAL and RESEARCH purposes only. Using this
#   software to automate input in any online game may violate that game's
#   Terms of Service.
#
# TR:
#   Bu modül, Knight Online için SEGE açık kaynak makro çerçevesinin bir
#   parçasıdır. Tek bir otomatik davranışı (bir "makro") ve onun PyQt5
#   konfigürasyon widget'ını içerir. Makro, çalışma zamanında modül kayıt
#   defteri (segesource/app/modules.py) tarafından yüklenir ve kullanıcının
#   arayüzde belirlediği kısayol tuşuna tepki verir.
#
#   Her makro modülünün uyması gereken mimari sözleşme:
#     - `.start()` ve `.stop()` metodları olan bir `*Macro` sınıfı sağlar
#     - Konfigürasyon için bir `*Widget` sınıfı (QWidget) sağlar
#     - Kalıcı durumunu paylaşılan settings sözlüğü üzerinden okur/yazar
#     - Klavye/fare çıktısı için `drivers.clicksend` kullanır (Interception
#       sürücü wrapper'ı), sıcak yolda asla doğrudan pyautogui değil
#
#   Bu dosya MIT lisansı altında dağıtılır (depo kökündeki LICENSE).
#   YALNIZCA EĞİTİM ve ARAŞTIRMA amaçlıdır. Bu yazılımı herhangi bir
#   çevrimiçi oyunda giriş otomasyonu için kullanmak ilgili oyunun
#   Kullanım Koşullarını ihlal edebilir.
#
# ═══════════════════════════════════════════════════════════════════════════

# --- wari_seriskill.py ---

import threading
import time
from typing import Literal

# PyQt5
from PyQt5.QtWidgets import (
    QDialog, QGridLayout, QLabel, QComboBox,
    QLineEdit, QPushButton, QDoubleSpinBox,
    QDialogButtonBox, QHBoxLayout, QWidget,
    QFrame, QVBoxLayout, QSizePolicy, QMessageBox,
    QCheckBox
)
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtCore import Qt, QSize, pyqtSignal

# Opsiyonel clicksend / interception sürücüsü
try:
    from clicksend import KeyboardDriver as _ClicksendKeyboardDriver
except ImportError:
    _ClicksendKeyboardDriver = None

# ---------------------------------------------------------
# SABİTLER (SCANCODES)
# ---------------------------------------------------------
DIGIT_SCANCODES = {
    1: 0x02, 2: 0x03, 3: 0x04, 4: 0x05, 5: 0x06,
    6: 0x07, 7: 0x08, 8: 0x09, 9: 0x0A, 0: 0x0B,
}

SC_2 = 0x03  # 2
SC_R = 0x13  # R
SC_W = 0x11  # W
SC_S = 0x1F  # S
SC_Z = 0x2C  # Z

# F1-F8 scancodes (standart)
FKEY_SCANCODES = {
    "F1": 0x3B,
    "F2": 0x3C,
    "F3": 0x3D,
    "F4": 0x3E,
    "F5": 0x3F,
    "F6": 0x40,
    "F7": 0x41,
    "F8": 0x42,
}

# ---------------------------------------------------------
# 1. LOGIC (MAKRO MOTORU)
# ---------------------------------------------------------
class WarriorSkillMacro:
    """
    Warrior Seri Skill Mantığı.
    Yapı ucbes.py ile birebir aynıdır (Thread ve Event yönetimi).
    """
    def __init__(
        self,
        order: str = "2rr",
        key_2_duration: float = 0.05,
        key_r_duration: float = 0.02,
        z_enabled: bool = False,
        z_delay: float = 0.05,
        skill_key: int = 2,
        mode: str = "toggle",
        skill_bar: str = "FYOK",
    ):
        self.order = order
        self.s_delay = key_2_duration
        self.r_delay = key_r_duration
        self.z_enabled = z_enabled
        self.z_delay = z_delay
        self.mode = mode
        self.skill_key = skill_key
        self.skill_bar = skill_bar  # <<< YENİ

        self._driver = _ClicksendKeyboardDriver() if _ClicksendKeyboardDriver else None

        # Thread yönetimi
        self._main_thread = None
        self._stop_event = threading.Event()
        self._running = False
        self._lock = threading.Lock()

        # Start'ta barı 1 kere basmak için
        self._bar_applied = False

    def update_config(self, cfg):
        with self._lock:
            self.order = cfg.get("order", "2rr")
            self.s_delay = cfg.get("key_2_duration", 0.05)
            self.r_delay = cfg.get("key_r_duration", 0.02)
            self.z_enabled = cfg.get("z_enabled", False)
            self.z_delay = cfg.get("z_key_duration", 0.05)
            self.skill_key = cfg.get("skill_key", 2)
            self.mode = cfg.get("mode", "toggle")          # <<< DÜZELTİLDİ
            self.skill_bar = cfg.get("skill_bar", "FYOK")  # <<< YENİ

    @property
    def is_running(self):
        return self._running

    def toggle(self):
        with self._lock:
            if not self._running:
                self._start_internal()
            else:
                self._stop_internal()

    def _scancode_to_keyname(self, scancode):
        # pyautogui için scancode -> key name
        if scancode == 0x03: return '2'
        if scancode == 0x13: return 'r'
        if scancode == 0x2C: return 'z'
        if scancode == 0x11: return 'w'
        if scancode == 0x1F: return 's'

        # F1-F8
        if scancode == 0x3B: return 'f1'
        if scancode == 0x3C: return 'f2'
        if scancode == 0x3D: return 'f3'
        if scancode == 0x3E: return 'f4'
        if scancode == 0x3F: return 'f5'
        if scancode == 0x40: return 'f6'
        if scancode == 0x41: return 'f7'
        if scancode == 0x42: return 'f8'

        return None

    # Hold/Toggle uyumu
    def hold_down(self):
        # HOLD modda basınca start
        if self.mode == "hold":
            self.start()
        else:
            self.toggle()

    def hold_up(self):
        # HOLD modda bırakınca stop
        if self.mode == "hold":
            self.stop()
        # toggle modda bir şey yapma

    def start(self):
        if not self._running:
            self._start_internal()

    def stop(self):
        if self._running:
            self._stop_internal()

    def _start_internal(self):
        print("[WARRIOR] Başlatılıyor...")
        self._stop_event.clear()
        self._bar_applied = False  # start'ta tekrar 1 kez uygula
        self._main_thread = threading.Thread(target=self._run_loop, daemon=True)
        self._main_thread.start()
        self._running = True

    def _stop_internal(self):
        print("[WARRIOR] Durduruluyor...")
        self._stop_event.set()
        self._running = False

    # --- ANA DÖNGÜ ---
    def _run_loop(self):
        while not self._stop_event.is_set():
            try:
                # Bar seçimi: sadece start'ta 1 kere bas
                if not self._bar_applied:
                    self._apply_skill_bar_once()
                    self._bar_applied = True

                self._do_combo_once()
                time.sleep(0.01)  # CPU Dostu bekleme
            except Exception as e:
                print(f"[WARRIOR] Hata: {e}")
                break

    def _apply_skill_bar_once(self):
        if self._stop_event.is_set():
            return
        bar = str(self.skill_bar or "FYOK").upper()
        if bar == "FYOK":
            return
        sc = FKEY_SCANCODES.get(bar)
        if sc:
            self._tap_scan(sc, 0.02)

    def _do_combo_once(self):
        if self._stop_event.is_set():
            return

        # Skill scancode
        sc_skill = DIGIT_SCANCODES.get(int(self.skill_key))

        # Hata Kontrolü
        if sc_skill is None:
            print("[WARRIOR] HATA: Skill tuşu scancode'u bulunamadı.")
            return

        # 1. Z (Opsiyonel)
        if self.z_enabled:
            self._tap_scan(SC_Z, self.z_delay)

        # 2. Kombo Sıralaması
        if self.order == '2rr':
            self._tap_scan(sc_skill, self.s_delay)
            self._tap_scan(SC_R, self.r_delay)
            self._tap_scan(SC_R, self.r_delay)

        elif self.order == 'rr2':
            self._tap_scan(SC_R, self.r_delay)
            self._tap_scan(SC_R, self.r_delay)
            self._tap_scan(sc_skill, self.s_delay)

        elif self.order == 'wr2':
            self._tap_scan(SC_W, 0.05)
            self._tap_scan(SC_R, self.r_delay)
            self._tap_scan(sc_skill, self.s_delay)

        elif self.order == 'wr2sr2':
            self._tap_scan(SC_W, 0.05)
            self._tap_scan(SC_R, self.r_delay)
            self._tap_scan(sc_skill, self.s_delay)
            self._tap_scan(SC_S, 0.05)
            self._tap_scan(SC_R, self.r_delay)
            self._tap_scan(sc_skill, self.s_delay)

    def _tap_scan(self, scancode: int, delay: float):
        if self._stop_event.is_set():
            return

        if self._driver:
            self._driver.tusbas(scancode, delay)
        else:
            import pyautogui
            key_name = self._scancode_to_keyname(scancode)
            if key_name:
                pyautogui.keyDown(key_name)
                time.sleep(delay)
                pyautogui.keyUp(key_name)
            else:
                time.sleep(delay)

# ---------------------------------------------------------
# 2. GUI (AYAR PENCERESİ)
# ---------------------------------------------------------
class WarriorSkillSettingsDialog(QDialog):
    def __init__(self, parent=None, current_config=None):
        super().__init__(parent)
        self.setWindowTitle("WARRIOR AYARLARI")
        self.setModal(True)
        self._capture_next_key = False
        self.result_config = None

        if current_config is None:
            current_config = {}

        key = current_config.get("key", "F")
        z_enabled = bool(current_config.get("z_enabled", False))
        z_key_duration = float(current_config.get("z_key_duration", 0.1))
        key_2_duration = float(current_config.get("key_2_duration", 0.05))
        key_r_duration = float(current_config.get("key_r_duration", 0.02))
        skill_key = current_config.get("skill_key", 2)
        order = current_config.get("order", "2rr")

        # YENİ: Mode + Bar
        mode = current_config.get("mode", "toggle")
        skill_bar = current_config.get("skill_bar", "FYOK")

        # Layout
        layout = QGridLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(8)

        # --- SATIR 0: BAŞLAT TUŞU ---
        layout.addWidget(QLabel("AKTIF TUS:"), 0, 0)
        self.edit_hotkey = QLineEdit(key)
        self.edit_hotkey.setReadOnly(True)
        hk_layout = QHBoxLayout()
        hk_layout.addWidget(self.edit_hotkey)
        btn_cap = QPushButton("TUŞ SEÇ")
        btn_cap.setObjectName("KeyCaptureButton")
        btn_cap.clicked.connect(self.start_capture_hotkey)
        hk_layout.addWidget(btn_cap)

        hk_widget = QWidget()
        hk_widget.setLayout(hk_layout)
        layout.addWidget(hk_widget, 0, 1)

        # --- SATIR 1: MOD (TOGGLE/HOLD) ---  <<< YENİ
        layout.addWidget(QLabel("MOD:"), 1, 0)
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItem("TOGGLE", "toggle")
        self.cmb_mode.addItem("HOLD", "hold")
        idxm = self.cmb_mode.findData(str(mode).lower())
        if idxm >= 0:
            self.cmb_mode.setCurrentIndex(idxm)
        layout.addWidget(self.cmb_mode, 1, 1)

        # --- SATIR 2: SKILL BAR (FYOK / F1-F8) ---  <<< YENİ
        layout.addWidget(QLabel("F BAR:"), 2, 0)
        self.cmb_bar = QComboBox()
        self.cmb_bar.addItems(["FYOK", "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8"])
        self.cmb_bar.setCurrentText(str(skill_bar).upper())
        layout.addWidget(self.cmb_bar, 2, 1)

        # --- SATIR 3: Z AYARI ---
        self.chk_z = QCheckBox("Z (OTO SEÇ)")
        self.chk_z.setChecked(z_enabled)
        layout.addWidget(self.chk_z, 3, 0)

        self.spin_z = QDoubleSpinBox()
        self.spin_z.setRange(0.01, 1.0)
        self.spin_z.setSingleStep(0.01)
        self.spin_z.setValue(z_key_duration)
        self.spin_z.setEnabled(z_enabled)
        self.chk_z.toggled.connect(self.spin_z.setEnabled)
        layout.addWidget(self.spin_z, 3, 1)

        # --- SATIR 4: SKILL SLOT SEÇİMİ ---
        layout.addWidget(QLabel("SKILL SLOTU (0–9):"), 4, 0)
        self.cmb_skill_key = QComboBox()
        self.cmb_skill_key.addItems([str(i) for i in range(10)])
        self.cmb_skill_key.setCurrentText(str(skill_key))
        layout.addWidget(self.cmb_skill_key, 4, 1)

        # --- SATIR 5: SKILL SÜRESİ ---
        layout.addWidget(QLabel("SKILL SÜRESİ(SN):"), 5, 0)
        self.spin_s = QDoubleSpinBox()
        self.spin_s.setRange(0.01, 1.0)
        self.spin_s.setSingleStep(0.01)
        self.spin_s.setValue(key_2_duration)
        layout.addWidget(self.spin_s, 5, 1)

        # --- SATIR 6: R SÜRESİ ---
        layout.addWidget(QLabel("R SÜRESİ:"), 6, 0)
        self.spin_r = QDoubleSpinBox()
        self.spin_r.setRange(0.01, 1.0)
        self.spin_r.setSingleStep(0.01)
        self.spin_r.setValue(key_r_duration)
        layout.addWidget(self.spin_r, 6, 1)

        # --- SATIR 7: KOMBO TİPİ ---
        layout.addWidget(QLabel("KOMBO TİPİ:"), 7, 0)
        self.cmb_order = QComboBox()
        self.cmb_order.addItem("2 - R - R", "2rr")
        self.cmb_order.addItem("R - R - 2", "rr2")
        self.cmb_order.addItem("W - R - 2", "wr2")
        self.cmb_order.addItem("W-R-2-S-R-2", "wr2sr2")

        idx = self.cmb_order.findData(order)
        if idx >= 0:
            self.cmb_order.setCurrentIndex(idx)
        layout.addWidget(self.cmb_order, 7, 1)

        # --- BUTONLAR ---
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns, 8, 0, 1, 2)

    def start_capture_hotkey(self):
        self._capture_next_key = True
        self.edit_hotkey.setText("TUŞA BAS...")

    def keyPressEvent(self, event):
        if self._capture_next_key:
            key = event.key()
            name = None
            if Qt.Key_F1 <= key <= Qt.Key_F12:
                name = f"F{key - Qt.Key_F1 + 1}"
            elif key == Qt.Key_CapsLock:
                name = "CAPS LOCK"
            elif key == Qt.Key_Shift:
                name = "SHIFT"
            elif key == Qt.Key_Control:
                name = "CTRL"
            elif key == Qt.Key_Alt:
                name = "ALT"
            elif key == Qt.Key_Space:
                name = "SPACE"
            else:
                text = event.text()
                if text:
                    name = text.upper()

            if name:
                self._capture_next_key = False
                self.edit_hotkey.setText(name)
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if self._capture_next_key:
            name = None
            btn = event.button()
            if btn == Qt.LeftButton:
                name = "LEFT"
            elif btn == Qt.RightButton:
                name = "RIGHT"
            elif btn == Qt.MiddleButton:
                name = "MIDDLE"
            elif btn == Qt.XButton1:
                name = "MOUSE4"
            elif btn == Qt.XButton2:
                name = "MOUSE5"

            if name:
                self._capture_next_key = False
                self.edit_hotkey.setText(name)
            return
        super().mousePressEvent(event)

    def accept(self):
        self.result_config = {
            "key": self.edit_hotkey.text(),
            "mode": self.cmb_mode.currentData(),         # <<< YENİ
            "skill_bar": self.cmb_bar.currentText(),     # <<< YENİ
            "z_enabled": self.chk_z.isChecked(),
            "z_key_duration": self.spin_z.value(),
            "key_2_duration": self.spin_s.value(),
            "key_r_duration": self.spin_r.value(),
            "order": self.cmb_order.currentData(),
            "skill_key": int(self.cmb_skill_key.currentText())
        }
        super().accept()

# ---------------------------------------------------------
# 3. WIDGET (ANA EKRAN KARTI)
# ---------------------------------------------------------
class WarriorSkillWidget(QFrame):
    update_signal = pyqtSignal()

    def __init__(self, parent=None, macro_instance=None, config=None):
        super().__init__(parent)
        self.macro = macro_instance
        self.config = config or {}

        self.listen_active = False
        self._hotkey_hook_handles = []
        self._last_toggle_time = 0

        self.update_signal.connect(self._safe_update_status)
        self.setup_ui()
        self._safe_update_status()

    def setup_ui(self):
        self.setFrameShape(QFrame.Box)
        self.setFrameShadow(QFrame.Plain)
        self.setMaximumWidth(260)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setStyleSheet("""
            QFrame {
                background-color: #101010;
                border: 1px solid #444444;
                border-radius: 4px;
            }
        """)

        v = QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(4)

        # --- HEADER ---
        header = QHBoxLayout()
        header.setSpacing(6)

        icon_row = QHBoxLayout()
        icon_row.setSpacing(3)
        icon_paths = ["icons/wari/83.png"]

        for path in icon_paths:
            lbl = QLabel()
            lbl.setFixedSize(25, 25)
            pix = QPixmap(path)
            if not pix.isNull():
                lbl.setPixmap(pix.scaled(25, 25, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            icon_row.addWidget(lbl)

        header.addLayout(icon_row)

        title_label = QLabel("WARRIOR SERİ")
        title_label.setObjectName("MinorHeaderLabel")

        header.addStretch(1)
        header.addWidget(title_label)

        v.addLayout(header)

        # --- BUTON ---
        self.btn_listen = QPushButton("TUŞ DİNLEMEYİ BAŞLAT")
        self.btn_listen.setObjectName("ThreeFiveListenButton")
        self.btn_listen.setProperty("active", False)
        self.btn_listen.clicked.connect(self.toggle_listen)
        v.addWidget(self.btn_listen)

        # --- DURUM LABEL ---
        self.lbl_status = QLabel("DURUM: PASİF")
        self.lbl_status.setObjectName("MinorStatusLabel")
        v.addWidget(self.lbl_status)

        # --- ALT SATIR (HOTKEY & AYAR) ---
        row = QHBoxLayout()
        row.setSpacing(4)
        row.addWidget(QLabel("AKTIF TUŞ:"))

        self.lbl_hotkey = QLabel(self.config.get("key", "F"))
        self.lbl_hotkey.setObjectName("HotkeyLabel")
        self.lbl_hotkey.setAlignment(Qt.AlignCenter)
        row.addWidget(self.lbl_hotkey)

        btn_settings = QPushButton("⚙ AYARLAR")
        btn_settings.setObjectName("MinorSettingsButton")
        btn_settings.setFlat(True)
        btn_settings.setIcon(QIcon("icons/gear.png"))
        btn_settings.setIconSize(QSize(12, 12))
        btn_settings.clicked.connect(self.open_settings)
        row.addWidget(btn_settings)

        v.addLayout(row)

    def open_settings(self):
        dlg = WarriorSkillSettingsDialog(self, self.config)
        if dlg.exec_() == QDialog.Accepted and dlg.result_config:
            self.config.update(dlg.result_config)

            self.macro.update_config(self.config)
            self.lbl_hotkey.setText(self.config["key"])

            if self.listen_active:
                self.toggle_listen()  # Kapat
                self.toggle_listen()  # Aç

    def toggle_listen(self):
        try:
            import keyboard
        except ImportError:
            QMessageBox.warning(self, "Hata", "'keyboard' kütüphanesi eksik.")
            return

        if not self.listen_active:
            hotkey = self.config.get("key", "F").lower()
            mode = self.config.get("mode", "toggle")
            self._hotkey_hook_handles.clear()

            try:
                if mode == "hold":
                    # HOLD: basılı tutunca çalış / bırakınca dur
                    h1 = keyboard.on_press_key(hotkey, lambda e: self.on_hold_down(), suppress=False)
                    h2 = keyboard.on_release_key(hotkey, lambda e: self.on_hold_up(), suppress=False)
                    self._hotkey_hook_handles.extend([h1, h2])
                else:
                    # TOGGLE: bas-aç / bas-kapat
                    h = keyboard.on_press_key(hotkey, lambda e: self.on_hotkey_toggle(), suppress=False)
                    self._hotkey_hook_handles.append(h)

                self.listen_active = True
                print(f"[WARRIOR] Dinleniyor: {hotkey} (mode={mode})")
            except Exception as e:
                print(f"[WARRIOR] Hotkey hatası: {e}")
                self.listen_active = False
        else:
            for h in self._hotkey_hook_handles:
                try:
                    keyboard.unhook(h)
                except:
                    pass
            self._hotkey_hook_handles.clear()

            self.listen_active = False
            if self.macro.is_running:
                self.macro.stop()

        self._safe_update_status()

    def on_hold_down(self):
        self.macro.hold_down()
        self.update_signal.emit()

    def on_hold_up(self):
        self.macro.hold_up()
        self.update_signal.emit()

    def on_hotkey_toggle(self):
        current = time.time()
        if current - self._last_toggle_time < 0.2:
            return
        self._last_toggle_time = current
        self.macro.toggle()
        self.update_signal.emit()

    def apply_status_style(self, color: str = "#8d95c7"):
        self.lbl_status.setStyleSheet(f"color: {color}; font-weight: bold;")

    def _safe_update_status(self):
        if not self.listen_active:
            self.lbl_status.setText("DURUM: PASİF")
            self.btn_listen.setText("TUŞ DİNLEMEYİ BAŞLAT")
            self.apply_status_style("#ff5555")
            is_active = False
        else:
            if self.macro.is_running:
                self.lbl_status.setText("DURUM: ÇALIŞIYOR")
                self.apply_status_style("#00ff4c")
            else:
                self.lbl_status.setText("DURUM: BEKLİYOR")
                self.apply_status_style("#ffff55")
            self.btn_listen.setText("TUŞ DİNLEMEYİ DURDUR")
            is_active = True
        self.btn_listen.setProperty("active", is_active)
        self.btn_listen.style().unpolish(self.btn_listen)
        self.btn_listen.style().polish(self.btn_listen)
