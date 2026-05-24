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

# --- kurianseriskill.py ---

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
# 1. LOGIC (MAKRO MOTORU)
# ---------------------------------------------------------
class KurianSeriSkill:
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
            self.skill_key = cfg.get("skill_key", 2)
            self.mode = cfg.get("mode", "toggle")
            self.skill_bar = cfg.get("skill_bar", "FYOK")

    @property
    def is_running(self):
        return self._running

    def toggle(self):
        with self._lock:
            if not self._running: self._start_internal()
            else: self._stop_internal()

    def hold_down(self):
        if self.mode == "hold": self.start()
        else: self.toggle()

    def hold_up(self):
        if self.mode == "hold": self.stop()

    def start(self):
        if not self._running: self._start_internal()

    def stop(self):
        if self._running: self._stop_internal()

    def _start_internal(self):
        print("[KURIAN] Başlatılıyor...")
        self._stop_event.clear()
        self._bar_applied = False
        self._main_thread = threading.Thread(target=self._run_loop, daemon=True)
        self._main_thread.start()
        self._running = True

    def _stop_internal(self):
        print("[KURIAN] Durduruluyor...")
        self._stop_event.set()
        self._running = False

    def _run_loop(self):
        while not self._stop_event.is_set():
            try:
                if not self._bar_applied:
                    self._apply_skill_bar_once()
                    self._bar_applied = True
                self._do_combo_once()
                time.sleep(0.01)
            except Exception as e:
                print(f"[KURIAN] Hata: {e}")
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

        if self.z_enabled: self._tap_scan(SC_Z, self.z_delay)

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

    def _tap_scan(self, scancode: int, delay: float):
        if self._stop_event.is_set(): return
        if self._driver: self._driver.tusbas(scancode, delay)
        else: time.sleep(delay)

# ---------------------------------------------------------
# 2. GUI (AYAR PENCERESİ)
# ---------------------------------------------------------
class KurianSettingsDialog(QDialog):
    def __init__(self, parent=None, current_config=None):
        super().__init__(parent)
        self.setWindowTitle("KURIAN AYARLARI")
        self.setModal(True)
        self._capture_next_key = False
        self.result_config = None

        if current_config is None: current_config = {}

        # Config değerlerini çek (Yoksa varsayılan)
        key = current_config.get("key", "X")
        z_enabled = bool(current_config.get("z_enabled", False))
        key_2_duration = float(current_config.get("key_2_duration", 0.05))
        key_r_duration = float(current_config.get("key_r_duration", 0.02))
        skill_key = current_config.get("skill_key", 2)
        order = current_config.get("order", "2rr")
        mode = current_config.get("mode", "toggle")
        skill_bar = current_config.get("skill_bar", "FYOK")

        l = QGridLayout(self)
        l.setContentsMargins(12, 12, 12, 12); l.setSpacing(10)

        l.addWidget(QLabel("AKTIF TUS:"), 0, 0)
        self.edit_hotkey = QLineEdit(key); self.edit_hotkey.setReadOnly(True)
        b_cap = QPushButton("TUŞ SEÇ"); b_cap.clicked.connect(self.start_capture_hotkey)
        h = QHBoxLayout(); h.addWidget(self.edit_hotkey); h.addWidget(b_cap); l.addLayout(h, 0, 1)

        l.addWidget(QLabel("MOD:"), 1, 0)
        self.cmb_mode = QComboBox(); self.cmb_mode.addItems(["TOGGLE", "HOLD"])
        self.cmb_mode.setItemData(0, "toggle"); self.cmb_mode.setItemData(1, "hold")
        idx = self.cmb_mode.findData(str(mode).lower()); 
        if idx >= 0: self.cmb_mode.setCurrentIndex(idx)
        l.addWidget(self.cmb_mode, 1, 1)

        l.addWidget(QLabel("F BAR:"), 2, 0)
        self.cmb_bar = QComboBox(); self.cmb_bar.addItems(["FYOK"] + [f"F{i}" for i in range(1,9)])
        self.cmb_bar.setCurrentText(str(skill_bar).upper())
        l.addWidget(self.cmb_bar, 2, 1)

        self.chk_z = QCheckBox("OTO Z BAS")
        self.chk_z.setChecked(z_enabled)
        l.addWidget(self.chk_z, 3, 0)

        l.addWidget(QLabel("SKILL SLOTU (0–9):"), 4, 0)
        self.cmb_skill = QComboBox(); self.cmb_skill.addItems([str(i) for i in range(10)])
        self.cmb_skill.setCurrentText(str(skill_key))
        l.addWidget(self.cmb_skill, 4, 1)

        l.addWidget(QLabel("SKILL HIZI:"), 5, 0)
        self.sp_s = QDoubleSpinBox(); self.sp_s.setRange(0.01, 1.0); self.sp_s.setSingleStep(0.01); self.sp_s.setValue(key_2_duration)
        l.addWidget(self.sp_s, 5, 1)

        l.addWidget(QLabel("R HIZI:"), 6, 0)
        self.sp_r = QDoubleSpinBox(); self.sp_r.setRange(0.01, 1.0); self.sp_r.setSingleStep(0.01); self.sp_r.setValue(key_r_duration)
        l.addWidget(self.sp_r, 6, 1)

        l.addWidget(QLabel("KOMBO:"), 7, 0)
        self.cmb_ord = QComboBox()
        self.cmb_ord.addItem("Skill - R - R", "2rr"); self.cmb_ord.addItem("R - R - Skill", "rr2"); self.cmb_ord.addItem("W - R - Skill", "wr2")
        idx = self.cmb_ord.findData(order); 
        if idx >= 0: self.cmb_ord.setCurrentIndex(idx)
        l.addWidget(self.cmb_ord, 7, 1)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        l.addWidget(btns, 8, 0, 1, 2)

    def start_capture_hotkey(self): self._capture_next_key = True; self.edit_hotkey.setText("...")
    def keyPressEvent(self, e):
        if self._capture_next_key:
            k = e.key(); t = e.text().upper()
            if k == Qt.Key_CapsLock: t = "CAPS LOCK"
            if t: self.edit_hotkey.setText(t); self._capture_next_key = False
        else: super().keyPressEvent(e)

    def accept(self):
        self.result_config = {
            "key": self.edit_hotkey.text(), "mode": self.cmb_mode.currentData(),
            "skill_bar": self.cmb_bar.currentText(), "z_enabled": self.chk_z.isChecked(),
            "key_2_duration": self.sp_s.value(), "key_r_duration": self.sp_r.value(),
            "order": self.cmb_ord.currentData(), "skill_key": int(self.cmb_skill.currentText())
        }
        super().accept()

# ---------------------------------------------------------
# 3. WIDGET (ANA EKRAN KARTI)
# ---------------------------------------------------------
class KurianSeriSkillWidget(QFrame):
    update_signal = pyqtSignal()

    def __init__(self, parent=None, macro_instance=None, config=None):
        super().__init__(parent)
        self.macro = macro_instance or KurianSeriSkill()
        self.config = config or {}
        self.macro.update_config(self.config)
        self.listen_active = False
        self._hooks = []
        self.update_signal.connect(self._safe_update_status)
        self.setup_ui(); self._safe_update_status()

    def setup_ui(self):
        self.setFrameShape(QFrame.Box)
        self.setMaximumWidth(260)
        # Stil tanımlaması (setStyleSheet içindeki background yerine background-color daha sağlıklıdır)
        self.setStyleSheet("QFrame { background-color: #101010; border: 1px solid #444; border-radius: 4px; }")
        
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(4)

        # ---------------- HEADER (4 KURIAN IKONU) ----------------
        header = QHBoxLayout()
        header.setSpacing(6)

        icon_row = QHBoxLayout()
        icon_row.setSpacing(3)

        # Fotoğrafların dosya isimlerini buraya yazın (Örn: k1.png, k2.png...)
        # Dosyaların 'icons/kurian/' klasöründe olduğunu varsayıyorum
        icon_paths = [
            "icons/kurian/kuri63a.png", 
            "icons/kurian/kuri63b.png", 
            "icons/kurian/kuri75a.png", 
            "icons/kurian/kuri75b.png"
        ]

        for path in icon_paths:
            lbl = QLabel()
            lbl.setFixedSize(25, 25) # İkon boyutu
            pix = QPixmap(path)
            
            if not pix.isNull():
                lbl.setPixmap(
                    pix.scaled(25, 25, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
            else:
                # Resim bulunamazsa eski emoji "👹" gözüksün
                lbl.setText("👹")
                lbl.setStyleSheet("border:none; font-size:16px;")
            
            icon_row.addWidget(lbl)

        header.addLayout(icon_row)
        header.addStretch(1) # İkonlar ile başlık arasını açar

        title = QLabel("KURIAN SERİ")
        title.setObjectName("MinorHeaderLabel")
        header.addWidget(title)
        
        v.addLayout(header)

        self.btn = QPushButton("TUŞ DİNLEMEYİ BAŞLAT")
        self.btn.setObjectName("ThreeFiveListenButton")
        self.btn.clicked.connect(self.toggle_listen); v.addWidget(self.btn)

        self.lbl_st = QLabel("PASİF"); self.lbl_st.setObjectName("MinorStatusLabel"); v.addWidget(self.lbl_st)

        r = QHBoxLayout(); r.addWidget(QLabel("TUŞ:"))
        self.lbl_key = QLabel(self.config.get("key", "X")); self.lbl_key.setObjectName("HotkeyLabel")
        r.addWidget(self.lbl_key)
        b_set = QPushButton("⚙AYARLAR"); b_set.setObjectName("MinorSettingsButton")
        b_set.clicked.connect(self.open_settings); r.addWidget(b_set)
        v.addLayout(r)

    def open_settings(self):
        d = KurianSettingsDialog(self, self.config)
        if d.exec_():
            self.config = d.result_config; self.macro.update_config(self.config)
            self.lbl_key.setText(self.config["key"])
            if self.listen_active: self.toggle_listen(); self.toggle_listen()

    def toggle_listen(self):
        try: import keyboard
        except: return QMessageBox.warning(self, "Hata", "keyboard yok")
        
        if not self.listen_active:
            hk = self.config.get("key", "X").lower(); mode = self.config.get("mode", "toggle")
            self._hooks = []
            try:
                if mode == "hold":
                    self._hooks.append(keyboard.on_press_key(hk, lambda e: self.macro.hold_down(), suppress=False))
                    self._hooks.append(keyboard.on_release_key(hk, lambda e: self.macro.hold_up(), suppress=False))
                else:
                    self._hooks.append(keyboard.on_press_key(hk, lambda e: self.macro.toggle(), suppress=False))
                self.listen_active = True
            except: self.listen_active = False
        else:
            for h in self._hooks: 
                try: keyboard.unhook(h)
                except: pass
            self._hooks = []; self.listen_active = False; self.macro.stop()
        self._safe_update_status()

    def _safe_update_status(self):
        if not self.listen_active:
            self.lbl_st.setText("PASİF"); self.lbl_st.setStyleSheet("color:#ff5555;font-weight:bold;")
            self.btn.setText("TUŞ DİNLEMEYİ BAŞLAT"); self.btn.setProperty("active", False)
        else:
            if self.macro.is_running:
                self.lbl_st.setText("ÇALIŞIYOR"); self.lbl_st.setStyleSheet("color:#00ff4c;font-weight:bold;")
            else:
                self.lbl_st.setText("BEKLİYOR"); self.lbl_st.setStyleSheet("color:#ffff55;font-weight:bold;")
            self.btn.setText("DURDUR"); self.btn.setProperty("active", True)
        self.btn.style().unpolish(self.btn); self.btn.style().polish(self.btn)
