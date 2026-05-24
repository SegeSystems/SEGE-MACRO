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

import threading
import time
import json
import os
import pyautogui

from PyQt5.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QCheckBox, QComboBox, QDoubleSpinBox, QGroupBox, QGridLayout,
    QDialog, QDialogButtonBox, QLineEdit
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QSize
from PyQt5.QtGui import QPixmap, QIcon

# --- DRIVER KONTROLÜ ---
try:
    from clicksend import KeyboardDriver, MouseDriver
    HAS_INTERCEPTION = True
except ImportError:
    HAS_INTERCEPTION = False

try:
    import keyboard
except ImportError:
    keyboard = None

# ---------------------------------------------------------
# LOGIC (PROFESYONEL MOUSE DRAG SPIN)
# ---------------------------------------------------------
class FirfirMacro:
    def __init__(self):
        self.kb_driver = KeyboardDriver() if HAS_INTERCEPTION else None
        self.ms_driver = MouseDriver() if HAS_INTERCEPTION else None
        
        # Ayarlar
        self.coord_1 = (960, 500)
        self.coord_2 = (960, 540)
        self.move_delay = 0.01    # Hareketler arası bekleme
        self.z_enabled = True      
        self.z_delay = 0.05        # Z basma hızı
        
        self._running = False
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self.SCAN_Z = 0x2C # Z Tuşu

    def update_config(self, cfg):
        with self._lock:
            self.coord_1 = cfg.get("coord_1", (960, 500))
            self.coord_2 = cfg.get("coord_2", (960, 540))
            self.move_delay = cfg.get("move_delay", 0.01)
            self.z_enabled = cfg.get("z_enabled", True)
            self.z_delay = cfg.get("z_delay", 0.05)

    @property
    def is_running(self): return self._running

    def start(self):
        if self._running: return
        self._running = True
        self._stop_event.clear()
        
        # --- BAŞLANGIÇ: MOUSE SOL TIK KİLİTLE ---
        if self.ms_driver:
            # İlk noktada mouse'u yere yapıştır
            self.ms_driver.mouse_left_down(self.coord_1[0], self.coord_1[1])

        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._running = False
        self._stop_event.set()
        
        # --- BİTİŞ: MOUSE SOL TIK BIRAK ---
        if self.ms_driver:
            # Mouse'un o anki yerinde bırak
            x, y = pyautogui.position()
            self.ms_driver.mouse_left_up(x, y)

    def _loop(self):
        last_z_time = 0
        while not self._stop_event.is_set():
            if not self.ms_driver:
                time.sleep(0.5); continue

            # 1. Z-Z BÖLÜMÜ (Periyodik Basım)
            if self.z_enabled and self.kb_driver:
                now = time.time()
                if now - last_z_time >= self.z_delay:
                    self.kb_driver.tusbas(self.SCAN_Z, 0.005)
                    last_z_time = now

            # 2. HAREKET (Sürükleme Devam Ediyor)
            # Sol tık start() içerisinde down yapıldığı için burada sadece move sinyali yollar
            if self._stop_event.is_set(): break
            self.ms_driver.mouse_left_down(self.coord_1[0], self.coord_1[1])
            if self.move_delay > 0: time.sleep(self.move_delay)
            
            if self._stop_event.is_set(): break
            self.ms_driver.mouse_left_down(self.coord_2[0], self.coord_2[1])
            if self.move_delay > 0: time.sleep(self.move_delay)

# ---------------------------------------------------------
# GUI (AYAR PENCERESİ)
# ---------------------------------------------------------
class FirfirSettingsDialog(QDialog):
    def __init__(self, parent, config):
        super().__init__(parent)
        self.setWindowTitle("DRAG FIRFIR VE Z-Z AYARLARI")
        self.config = config
        self.setModal(True)
        self.resize(400, 500)
        self.setStyleSheet("background-color: #121212; color: white;")
        
        layout = QVBoxLayout(self)
        
        # --- MOD SEÇİMİ ---
        grp_mode = QGroupBox("Çalışma Modu")
        grp_mode.setStyleSheet("color: #ffea00; font-weight: bold;")
        ml = QVBoxLayout(grp_mode)
        self.cmb_run_mode = QComboBox()
        self.cmb_run_mode.addItems(["BASILI TUT (HOLD)", "AÇ / KAPAT (TOGGLE)"])
        self.cmb_run_mode.setCurrentText("BASILI TUT (HOLD)" if self.config.get("mode") == "hold" else "AÇ / KAPAT (TOGGLE)")
        ml.addWidget(self.cmb_run_mode)
        layout.addWidget(grp_mode)

        # --- KOORDİNATLAR ---
        grp_coords = QGroupBox("1. Hareket Koordinatları (Drag Aralığı)")
        grp_coords.setStyleSheet("color: #00e676; font-weight: bold;")
        gl = QGridLayout(grp_coords)
        self.btn_get_1 = QPushButton("1. NOKTA SEÇ (F)")
        self.lbl_1 = QLabel(f"{self.config.get('coord_1', (0,0))}")
        gl.addWidget(self.btn_get_1, 0, 0); gl.addWidget(self.lbl_1, 0, 1)
        self.btn_get_2 = QPushButton("2. NOKTA SEÇ (F)")
        self.lbl_2 = QLabel(f"{self.config.get('coord_2', (0,0))}")
        gl.addWidget(self.btn_get_2, 1, 0); gl.addWidget(self.lbl_2, 1, 1)
        layout.addWidget(grp_coords)
        
        # --- Z-Z VE HIZ ---
        grp_speed = QGroupBox("2. Zamanlama Ayarları")
        grp_speed.setStyleSheet("color: #2979ff; font-weight: bold;")
        fl = QGridLayout(grp_speed)
        
        self.chk_z = QCheckBox("Z-Z (Hedefleme) Aktif"); self.chk_z.setChecked(self.config.get("z_enabled", True))
        fl.addWidget(self.chk_z, 0, 0)
        self.spin_z = QDoubleSpinBox(); self.spin_z.setRange(0.001, 5.0); self.spin_z.setDecimals(3)
        self.spin_z.setValue(self.config.get("z_delay", 0.05))
        fl.addWidget(QLabel("Z-Z Basma Hızı:"), 1, 0); fl.addWidget(self.spin_z, 1, 1)

        self.spin_click = QDoubleSpinBox(); self.spin_click.setRange(0.001, 5.0); self.spin_click.setDecimals(3)
        self.spin_click.setValue(self.config.get("move_delay", 0.01))
        fl.addWidget(QLabel("Mouse Hareket Hızı:"), 2, 0); fl.addWidget(self.spin_click, 2, 1)
        layout.addWidget(grp_speed)

        # --- TETİKLEME ---
        grp_hotkey = QGroupBox("3. Başlatma Tuşu")
        hl = QHBoxLayout(grp_hotkey)
        self.txt_hotkey = QLineEdit(self.config.get("hotkey", "CapsLock"))
        self.txt_hotkey.setReadOnly(True)
        self.btn_cap = QPushButton("TUŞ ATA")
        hl.addWidget(self.txt_hotkey); hl.addWidget(self.btn_cap)
        layout.addWidget(grp_hotkey)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        self.btn_get_1.clicked.connect(lambda: self.start_capture("1"))
        self.btn_get_2.clicked.connect(lambda: self.start_capture("2"))
        self.btn_cap.clicked.connect(self.start_key_cap)
        
        self.capture_target = None; self.temp_config = self.config.copy()
        self.timer = QTimer(); self.timer.timeout.connect(self.polling); self.timer.start(50)

    def start_capture(self, target): self.capture_target = target
    def start_key_cap(self): self.capture_target = "key"; self.txt_hotkey.setText("...")
    def polling(self):
        if self.capture_target in ["1", "2"] and keyboard and keyboard.is_pressed('f'):
            x, y = pyautogui.position()
            if self.capture_target == "1":
                self.temp_config["coord_1"] = (x, y); self.lbl_1.setText(f"{x}, {y}")
            else:
                self.temp_config["coord_2"] = (x, y); self.lbl_2.setText(f"{x}, {y}")
            self.capture_target = None

    def keyPressEvent(self, e):
        if self.capture_target == "key":
            name = e.text().upper()
            if e.key() == Qt.Key_CapsLock: name = "CAPSLOCK"
            if name: self.txt_hotkey.setText(name); self.capture_target = None
        else: super().keyPressEvent(e)

    def accept(self):
        self.config.update(self.temp_config)
        self.config.update({
            "z_enabled": self.chk_z.isChecked(),
            "z_delay": self.spin_z.value(),
            "move_delay": self.spin_click.value(),
            "hotkey": self.txt_hotkey.text(),
            "mode": "hold" if self.cmb_run_mode.currentIndex() == 0 else "toggle"
        })
        super().accept()

# ---------------------------------------------------------
# 3. WIDGET (ANA KART)
# ---------------------------------------------------------
class FirfirWidget(QFrame):
    update_signal = pyqtSignal()

    def __init__(self, parent=None, macro_instance=None, config=None):
        super().__init__(parent)
        self.macro = macro_instance or FirfirMacro()
        self.config = config or {"hotkey": "CAPSLOCK", "z_enabled": True, "move_delay": 0.01, "z_delay": 0.05, "mode": "hold"}
        self.macro.update_config(self.config)
        self.listen_active = False
        self._hooks = []
        self.setup_ui()
        self.update_signal.connect(self._safe_update_status)

    def setup_ui(self):
        self.setFrameShape(QFrame.Box); self.setMaximumWidth(260)
        self.setStyleSheet("QFrame { background-color: #101010; border: 1px solid #444; border-radius: 4px; }")
        v = QVBoxLayout(self); v.setContentsMargins(6, 6, 6, 6)
        
        h = QHBoxLayout()
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(25, 25)
        pix = QPixmap("icons/firfir.png") 
        if not pix.isNull(): self.icon_label.setPixmap(pix.scaled(25, 25, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else: self.icon_label.setText("🌀")
        h.addWidget(self.icon_label)
        
        lbl = QLabel("FIRFIR"); lbl.setObjectName("MinorHeaderLabel")
        h.addStretch(1); h.addWidget(lbl); v.addLayout(h)

        self.btn_listen = QPushButton("TUŞ DİNLEMEYİ BAŞLAT"); self.btn_listen.setObjectName("ThreeFiveListenButton")
        self.btn_listen.clicked.connect(self.toggle_listen); v.addWidget(self.btn_listen)
        self.lbl_status = QLabel("PASİF"); self.lbl_status.setObjectName("MinorStatusLabel"); v.addWidget(self.lbl_status)

        row = QHBoxLayout()
        row.addWidget(QLabel("TUŞ:")); self.lbl_key = QLabel(self.config.get("hotkey", "CAPSLOCK"))
        self.lbl_key.setObjectName("HotkeyLabel")
        btn_set = QPushButton("⚙ AYARLAR"); btn_set.setObjectName("MinorSettingsButton")
        btn_set.clicked.connect(self.open_settings)
        row.addWidget(self.lbl_key); row.addWidget(btn_set); v.addLayout(row)

    def toggle_listen(self):
        if not keyboard: return
        if not self.listen_active:
            hk = self.config.get("hotkey", "CAPSLOCK").lower()
            mode = self.config.get("mode", "hold")
            try:
                if mode == "hold":
                    h1 = keyboard.on_press_key(hk, lambda e: self.macro.start(), suppress=False)
                    h2 = keyboard.on_release_key(hk, lambda e: self.macro.stop(), suppress=False)
                    self._hooks = [h1, h2]
                else:
                    h1 = keyboard.on_press_key(hk, lambda e: self.on_toggle_key(), suppress=False)
                    self._hooks = [h1]
                self.listen_active = True
            except: pass
        else:
            self.listen_active = False
            self.macro.stop()
            for h in self._hooks:
                try: keyboard.unhook(h)
                except: pass
            self._hooks = []
        self._safe_update_status()

    def on_toggle_key(self):
        if self.macro.is_running: self.macro.stop()
        else: self.macro.start()
        self.update_signal.emit()

    def open_settings(self):
        d = FirfirSettingsDialog(self, self.config)
        if d.exec_():
            was_listening = self.listen_active
            if was_listening: self.toggle_listen()
            self.macro.update_config(self.config)
            self.lbl_key.setText(self.config["hotkey"])
            if was_listening: self.toggle_listen()

    def _safe_update_status(self):
        active = self.listen_active
        mode_str = self.config.get("mode", "hold").upper()
        
        if not active:
            self.lbl_status.setText("PASİF")
            self.lbl_status.setStyleSheet("color: #ff5555; font-weight: bold;")
        else:
            if self.macro.is_running:
                self.lbl_status.setText(f"AKTİF ({mode_str})")
                self.lbl_status.setStyleSheet("color: #00ff4c; font-weight: bold;")
            else:
                self.lbl_status.setText(f"HAZIR ({mode_str})")
                self.lbl_status.setStyleSheet("color: #ffea00; font-weight: bold;")

        self.btn_listen.setText("DURDUR" if active else "TUŞ DİNLEMEYİ BAŞLAT")
        self.btn_listen.setProperty("active", active)
        self.btn_listen.style().unpolish(self.btn_listen); self.btn_listen.style().polish(self.btn_listen)
