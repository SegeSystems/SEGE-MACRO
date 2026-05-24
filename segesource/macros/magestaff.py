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

SC_R = 0x13  # R
SC_W = 0x11  # W
SC_S = 0x1F  # S
SC_Z = 0x2C  # Z

# F1-F8 scancodes
FKEY_SCANCODES = {
    "F1": 0x3B, "F2": 0x3C, "F3": 0x3D, "F4": 0x3E,
    "F5": 0x3F, "F6": 0x40, "F7": 0x41, "F8": 0x42,
}

# ---------------------------------------------------------
# 1. LOGIC (MAKRO MOTORU) - Dokunulmadı
# ---------------------------------------------------------
class MageStaffMacro:
    """
    Mage Staff Atak Mantığı.
    Skill + R, R + Skill veya W + R + Skill kombinasyonları.
    """
    def __init__(
        self,
        order: str = "2rr",
        key_2_duration: float = 0.05,
        key_r_duration: float = 0.02,
        z_enabled: bool = False,
        z_delay: float = 0.05,
        skill_key: int = 1,
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
        self.skill_bar = skill_bar

        self._driver = _ClicksendKeyboardDriver() if _ClicksendKeyboardDriver else None

        self._main_thread = None
        self._stop_event = threading.Event()
        self._running = False
        self._lock = threading.Lock()
        self._bar_applied = False

    def update_config(self, cfg):
        with self._lock:
            self.order = cfg.get("order", "2rr")
            self.s_delay = cfg.get("key_2_duration", 0.05)
            self.r_delay = cfg.get("key_r_duration", 0.02)
            self.z_enabled = cfg.get("z_enabled", False)
            self.z_delay = cfg.get("z_key_duration", 0.05)
            self.skill_key = cfg.get("skill_key", 1)
            self.mode = cfg.get("mode", "toggle")
            self.skill_bar = cfg.get("skill_bar", "FYOK")

    @property
    def is_running(self):
        return self._running

    def toggle(self):
        with self._lock:
            if not self._running:
                self._start_internal()
            else:
                self._stop_internal()

    def hold_down(self):
        if self.mode == "hold": self.start()
        else: self.toggle()

    def hold_up(self):
        if self.mode == "hold": self.stop()

    def start(self):
        if not self._running:
            self._start_internal()

    def stop(self):
        if self._running:
            self._stop_internal()

    def _start_internal(self):
        print("[MAGE] Staff Başlatılıyor...")
        self._stop_event.clear()
        self._bar_applied = False
        self._main_thread = threading.Thread(target=self._run_loop, daemon=True)
        self._main_thread.start()
        self._running = True

    def _stop_internal(self):
        print("[MAGE] Staff Durduruluyor...")
        self._stop_event.set()
        self._running = False

    def _run_loop(self):
        while not self._stop_event.is_set():
            try:
                # Skill Bar Seçimi (Başlangıçta bir kere)
                if not self._bar_applied:
                    self._apply_skill_bar_once()
                    self._bar_applied = True

                self._do_combo_once()
                time.sleep(0.01)
            except Exception as e:
                print(f"[MAGE] Hata: {e}")
                break

    def _apply_skill_bar_once(self):
        if self._stop_event.is_set(): return
        bar = str(self.skill_bar or "FYOK").upper()
        if bar == "FYOK": return
        sc = FKEY_SCANCODES.get(bar)
        if sc: self._tap_scan(sc, 0.02)

    def _do_combo_once(self):
        if self._stop_event.is_set(): return

        sc_skill = DIGIT_SCANCODES.get(int(self.skill_key))
        if sc_skill is None: return

        # Z (Opsiyonel)
        if self.z_enabled:
            self._tap_scan(SC_Z, self.z_delay)

        # Kombo Tipi
        if self.order == '2rr': # Skill - R - R
            self._tap_scan(sc_skill, self.s_delay)
            self._tap_scan(SC_R, self.r_delay)
            self._tap_scan(SC_R, self.r_delay)

        elif self.order == 'rr2': # R - R - Skill
            self._tap_scan(SC_R, self.r_delay)
            self._tap_scan(SC_R, self.r_delay)
            self._tap_scan(sc_skill, self.s_delay)

        elif self.order == 'wr2': # W - R - Skill (Slide)
            self._tap_scan(SC_W, 0.05)
            self._tap_scan(SC_R, self.r_delay)
            self._tap_scan(sc_skill, self.s_delay)

        elif self.order == 'wr2sr2': # W-R-Skill-S-R-Skill (İleri Geri Slide)
            self._tap_scan(SC_W, 0.05)
            self._tap_scan(SC_R, self.r_delay)
            self._tap_scan(sc_skill, self.s_delay)
            self._tap_scan(SC_S, 0.05)
            self._tap_scan(SC_R, self.r_delay)
            self._tap_scan(sc_skill, self.s_delay)

    def _tap_scan(self, scancode: int, delay: float):
        if self._stop_event.is_set(): return
        if self._driver:
            self._driver.tusbas(scancode, delay)
        else:
            time.sleep(delay)

# ---------------------------------------------------------
# 2. SETTINGS DIALOG - Eskiden Alındı
# ---------------------------------------------------------
class MageStaffSettingsDialog(QDialog):
    def __init__(self, parent=None, current_config=None):
        super().__init__(parent)
        self.setWindowTitle("MAGE STAFF AYARLARI")
        self.setModal(True)
        self._capture_next_key = False
        
        if current_config is None: current_config = {}

        key = current_config.get("key", "Z")
        z_enabled = bool(current_config.get("z_enabled", False))
        z_key_duration = float(current_config.get("z_key_duration", 0.05))
        key_2_duration = float(current_config.get("key_2_duration", 0.05))
        key_r_duration = float(current_config.get("key_r_duration", 0.02))
        skill_key = current_config.get("skill_key", 1)
        order = current_config.get("order", "2rr")
        mode = current_config.get("mode", "toggle")
        skill_bar = current_config.get("skill_bar", "FYOK")

        layout = QGridLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # 0. Aktif Tuş
        layout.addWidget(QLabel("BAŞLATMA TUŞU:"), 0, 0)
        self.edit_hotkey = QLineEdit(key)
        self.edit_hotkey.setReadOnly(True)
        btn_cap = QPushButton("TUŞ SEÇ")
        btn_cap.clicked.connect(self.start_capture_hotkey)
        h_key = QHBoxLayout(); h_key.addWidget(self.edit_hotkey); h_key.addWidget(btn_cap)
        layout.addLayout(h_key, 0, 1)

        # 1. Mod
        layout.addWidget(QLabel("MOD:"), 1, 0)
        self.cmb_mode = QComboBox(); self.cmb_mode.addItems(["TOGGLE (AÇ/KAPA)", "HOLD (BASILI TUT)"])
        idx_m = 0 if mode == "toggle" else 1
        self.cmb_mode.setCurrentIndex(idx_m)
        layout.addWidget(self.cmb_mode, 1, 1)

        # 2. Skill Bar
        layout.addWidget(QLabel("F BAR:"), 2, 0)
        self.cmb_bar = QComboBox(); self.cmb_bar.addItems(["FYOK"] + [f"F{i}" for i in range(1,9)])
        self.cmb_bar.setCurrentText(skill_bar)
        layout.addWidget(self.cmb_bar, 2, 1)

        # 3. Z Ayarı
        self.chk_z = QCheckBox("OTO Z BAS")
        self.chk_z.setChecked(z_enabled)
        layout.addWidget(self.chk_z, 3, 0)
        self.spin_z = QDoubleSpinBox(); self.spin_z.setRange(0.01, 1.0); self.spin_z.setValue(z_key_duration)
        layout.addWidget(self.spin_z, 3, 1)

        # 4. Skill Slotu
        layout.addWidget(QLabel("STAFF SKILL (0-9):"), 4, 0)
        self.cmb_skill_key = QComboBox(); self.cmb_skill_key.addItems([str(i) for i in range(10)])
        self.cmb_skill_key.setCurrentText(str(skill_key))
        layout.addWidget(self.cmb_skill_key, 4, 1)

        # 5. Skill Süresi
        layout.addWidget(QLabel("SKILL SÜRESİ (SN):"), 5, 0)
        self.spin_s = QDoubleSpinBox(); self.spin_s.setRange(0.01, 1.0); self.spin_s.setValue(key_2_duration)
        layout.addWidget(self.spin_s, 5, 1)

        # 6. R Süresi
        layout.addWidget(QLabel("R SÜRESİ (SN):"), 6, 0)
        self.spin_r = QDoubleSpinBox(); self.spin_r.setRange(0.01, 1.0); self.spin_r.setValue(key_r_duration)
        layout.addWidget(self.spin_r, 6, 1)

        # 7. Kombo Tipi
        layout.addWidget(QLabel("KOMBO TİPİ:"), 7, 0)
        self.cmb_order = QComboBox()
        self.cmb_order.addItem("Skill - R - R", "2rr")
        self.cmb_order.addItem("R - R - Skill", "rr2")
        self.cmb_order.addItem("W - R - Skill (Slide)", "wr2")
        self.cmb_order.addItem("W-R-Skill-S-R-Skill", "wr2sr2")
        idx_o = self.cmb_order.findData(order)
        if idx_o >= 0: self.cmb_order.setCurrentIndex(idx_o)
        layout.addWidget(self.cmb_order, 7, 1)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        layout.addWidget(btns, 8, 0, 1, 2)

    def start_capture_hotkey(self):
        self._capture_next_key = True; self.edit_hotkey.setText("BAS...")
    
    def keyPressEvent(self, e):
        if self._capture_next_key:
            k = e.text().upper()
            if not k:
                if e.key() == Qt.Key_F1: k = "F1"
                elif e.key() == Qt.Key_CapsLock: k = "CAPS LOCK"
            if k:
                self.edit_hotkey.setText(k)
                self._capture_next_key = False
            return
        super().keyPressEvent(e)

    def accept(self):
        self.result_config = {
            "key": self.edit_hotkey.text(),
            "mode": "toggle" if self.cmb_mode.currentIndex() == 0 else "hold",
            "skill_bar": self.cmb_bar.currentText(),
            "z_enabled": self.chk_z.isChecked(),
            "z_key_duration": self.spin_z.value(),
            "skill_key": int(self.cmb_skill_key.currentText()),
            "key_2_duration": self.spin_s.value(),
            "key_r_duration": self.spin_r.value(),
            "order": self.cmb_order.currentData()
        }
        super().accept()

# ---------------------------------------------------------
# 3. WIDGET (ANA EKRAN KARTI) - Dokunulmadı
# ---------------------------------------------------------
class MageStaffWidget(QFrame):
    update_signal = pyqtSignal()

    def __init__(self, parent=None, macro_instance=None, config=None):
        super().__init__(parent)
        self.macro = macro_instance or MageStaffMacro()
        self.config = config or {}
        self.listen_active = False
        self._hooks = []
        self.update_signal.connect(self._safe_update)
        self.setup_ui()
        self._safe_update()

    def setup_ui(self):
        # Restore ile aynı boyut ve çerçeve ayarları
        self.setFrameShape(QFrame.Box)
        self.setMaximumWidth(260)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setStyleSheet("QFrame { background-color: #101010; border: 1px solid #444; border-radius: 4px; }")
        
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(4)

        # HEADER (İkon ve Başlık)
        h = QHBoxLayout()
        h.setSpacing(6)
        
        # İkon Label
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(25, 25)
        self.icon_label.setAlignment(Qt.AlignCenter)

        import os
        icon_path = os.path.join("icons", "mage", "mage72.png")
        pix = QPixmap(icon_path)
        
        if not pix.isNull():
            self.icon_label.setPixmap(pix.scaled(25, 25, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.icon_label.setText("🔥")
            self.icon_label.setStyleSheet("font-size:18px; border:none; background:transparent;")
        
        h.addWidget(self.icon_label)
        
        title = QLabel("MAGE STAFF")
        title.setObjectName("MinorHeaderLabel")
        h.addStretch()
        h.addWidget(title)
        v.addLayout(h)

        # Dinleme Butonu
        self.btn_listen = QPushButton("TUŞ DİNLEMEYİ BAŞLAT")
        self.btn_listen.setObjectName("ThreeFiveListenButton")
        self.btn_listen.clicked.connect(self.toggle_listen)
        v.addWidget(self.btn_listen)

        # Durum Yazısı
        self.lbl_status = QLabel("DURUM: PASİF")
        self.lbl_status.setObjectName("MinorStatusLabel")
        v.addWidget(self.lbl_status)

        # FOOTER
        row = QHBoxLayout()
        row.setSpacing(4)
        
        lbl_key_title = QLabel("AKTİF TUŞ:")
        row.addWidget(lbl_key_title)
        
        self.lbl_key = QLabel(self.config.get("key", "Z"))
        self.lbl_key.setObjectName("HotkeyLabel")
        self.lbl_key.setAlignment(Qt.AlignCenter)
        row.addWidget(self.lbl_key)
        
        btn_set = QPushButton("⚙ AYARLAR")
        btn_set.setObjectName("MinorSettingsButton")
        btn_set.clicked.connect(self.open_settings)
        row.addWidget(btn_set)
        
        v.addLayout(row)

    def open_settings(self):
        dlg = MageStaffSettingsDialog(self, self.config)
        if dlg.exec_():
            self.config.update(dlg.result_config)
            self.macro.update_config(self.config)
            self.lbl_key.setText(self.config["key"])
            if self.listen_active: self.toggle_listen(); self.toggle_listen()

    def toggle_listen(self):
        try: import keyboard
        except: return QMessageBox.warning(self, "Hata", "keyboard eksik")

        if not self.listen_active:
            hk = self.config.get("key", "Z").lower()
            mode = self.config.get("mode", "toggle")
            self._hooks = []
            try:
                if mode == "hold":
                    self._hooks.append(keyboard.on_press_key(hk, lambda e: self.on_down(), suppress=False))
                    self._hooks.append(keyboard.on_release_key(hk, lambda e: self.on_up(), suppress=False))
                else:
                    self._hooks.append(keyboard.on_press_key(hk, lambda e: self.on_toggle(), suppress=False))
                self.listen_active = True
            except: self.listen_active = False
        else:
            for h in self._hooks: 
                try: keyboard.unhook(h)
                except: pass
            self._hooks = []; self.listen_active = False; self.macro.stop()
        self._safe_update()

    def on_down(self): self.macro.hold_down(); self.update_signal.emit()
    def on_up(self): self.macro.hold_up(); self.update_signal.emit()
    def on_toggle(self): self.macro.toggle(); self.update_signal.emit()

    def _safe_update(self):
        if not self.listen_active:
            self.lbl_status.setText("DURUM: PASİF")
            self.lbl_status.setStyleSheet("color:#ff5555; font-weight:bold;")
            self.btn_listen.setText("TUŞ DİNLEMEYİ BAŞLAT")
            self.btn_listen.setProperty("active", False)
        else:
            if self.macro.is_running:
                self.lbl_status.setText("ÇALIŞIYOR")
                self.lbl_status.setStyleSheet("color:#00ff4c; font-weight:bold;")
            else:
                self.lbl_status.setText("BEKLİYOR")
                self.lbl_status.setStyleSheet("color:#ffff55; font-weight:bold;")
            self.btn_listen.setText("DURDUR")
            self.btn_listen.setProperty("active", True)
        
        self.btn_listen.style().unpolish(self.btn_listen)
        self.btn_listen.style().polish(self.btn_listen)
