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

from PyQt5.QtWidgets import (
    QDialog, QGridLayout, QLabel, QComboBox,
    QLineEdit, QPushButton, QDoubleSpinBox,
    QDialogButtonBox, QHBoxLayout, QWidget,
    QFrame, QVBoxLayout, QSizePolicy, QMessageBox,
    QCheckBox, QGroupBox
)
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtCore import Qt, QSize, pyqtSignal

# ---------------------------------------------------------
# Opsiyonel clicksend / interception sürücüsü
# ---------------------------------------------------------
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
SC_Z = 0x2C  # Z

# =========================================================
# 1. LOGIC (MAKRO MOTORU)
# =========================================================
class PriestAttackMacro:
    """
    PRIEST BP ATAK MAKROSU
    Skill + R + R
    Opsiyonel kitap & kol
    """

    def __init__(
        self,
        skill_key: int = 2,
        skill_delay: float = 0.05,
        r_delay: float = 0.02,
        z_enabled: bool = False,
        z_delay: float = 0.05,
        mode: str = "toggle",

        kitap_enabled: bool = False,
        kitap_key: int = 8,
        kitap_delay: float = 3.0,

        kol_enabled: bool = False,
        kol_key: int = 9,
        kol_delay: float = 3.0
    ):
        # --- Temel ---
        self.skill_key = skill_key
        self.skill_delay = skill_delay
        self.r_delay = r_delay
        self.z_enabled = z_enabled
        self.z_delay = z_delay
        self.mode = mode

        # --- Kitap ---
        self.kitap_enabled = kitap_enabled
        self.kitap_key = kitap_key
        self.kitap_delay = kitap_delay

        # --- Kol ---
        self.kol_enabled = kol_enabled
        self.kol_key = kol_key
        self.kol_delay = kol_delay

        # --- Runtime ---
        self._driver = _ClicksendKeyboardDriver() if _ClicksendKeyboardDriver else None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._running = False

        self._last_kitap_time = 0.0
        self._last_kol_time = 0.0

    # -----------------------------------------------------

    @property
    def is_running(self):
        return self._running

    # -----------------------------------------------------

    def update_config(self, cfg: dict):
        with self._lock:
            self.skill_key = int(cfg.get("skill_key", self.skill_key))
            self.skill_delay = float(cfg.get("skill_delay", self.skill_delay))
            self.r_delay = float(cfg.get("r_delay", self.r_delay))
            self.z_enabled = bool(cfg.get("z_enabled", self.z_enabled))
            self.z_delay = float(cfg.get("z_delay", self.z_delay))
            self.mode = cfg.get("mode", self.mode)

            self.kitap_enabled = bool(cfg.get("kitap_enabled", self.kitap_enabled))
            self.kitap_key = int(cfg.get("kitap_key", self.kitap_key))
            self.kitap_delay = float(cfg.get("kitap_delay", self.kitap_delay))

            self.kol_enabled = bool(cfg.get("kol_enabled", self.kol_enabled))
            self.kol_key = int(cfg.get("kol_key", self.kol_key))
            self.kol_delay = float(cfg.get("kol_delay", self.kol_delay))

    # -----------------------------------------------------

    def toggle(self):
        if self._running:
            self.stop()
        else:
            self.start()

    def hold_down(self):
        if self.mode == "hold":
            self.start()
        else:
            self.toggle()

    def hold_up(self):
        if self.mode == "hold":
            self.stop()

    # -----------------------------------------------------

    def start(self):
        if self._running:
            return

        print("[PRIEST BP] Başlatılıyor")
        self._stop_event.clear()
        self._last_kitap_time = 0
        self._last_kol_time = 0

        threading.Thread(
            target=self._run_loop,
            daemon=True
        ).start()

        self._running = True

    def stop(self):
        if not self._running:
            return

        print("[PRIEST BP] Durduruluyor")
        self._stop_event.set()
        self._running = False

    # -----------------------------------------------------

    def _run_loop(self):
        while not self._stop_event.is_set():
            now = time.time()

            if self.kitap_enabled and now - self._last_kitap_time >= self.kitap_delay:
                self._tap_digit(self.kitap_key, 0.05)
                self._last_kitap_time = now
                time.sleep(0.15)

            if self.kol_enabled and now - self._last_kol_time >= self.kol_delay:
                self._tap_digit(self.kol_key, 0.05)
                self._last_kol_time = now
                time.sleep(0.15)

            self._attack_combo()

    # -----------------------------------------------------

    def _attack_combo(self):
        if self.z_enabled:
            self._tap_scan(SC_Z, 0.01)
            time.sleep(self.z_delay)

        self._tap_digit(self.skill_key, self.skill_delay)
        self._tap_scan(SC_R, self.r_delay)
        self._tap_scan(SC_R, self.r_delay)

    # -----------------------------------------------------

    def _tap_digit(self, digit: int, delay: float):
        sc = DIGIT_SCANCODES.get(digit)
        if sc:
            self._tap_scan(sc, delay)

    def _tap_scan(self, scancode: int, delay: float):
        if self._driver:
            self._driver.tusbas(scancode, delay)
        else:
            time.sleep(delay)

# =========================================================
# 2. GUI (AYAR PENCERESİ)
# =========================================================
class PriestAttackSettingsDialog(QDialog):

    def __init__(self, parent=None, current_config=None):
        super().__init__(parent)
        self.setWindowTitle("PRIEST BP ATAK AYARLARI")
        self.setModal(True)
        self.resize(350, 500)

        self._capture_next_key = False
        self.result_config = {}

        if current_config is None:
            current_config = {}

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)

        # -------------------------------------------------
        # GRUP 1: TEMEL ATAK
        # -------------------------------------------------
        grp_genel = QGroupBox("⚔️ TEMEL ATAK")
        gl = QGridLayout(grp_genel)

        gl.addWidget(QLabel("BAŞLATMA TUŞU:"), 0, 0)
        self.edit_hotkey = QLineEdit(current_config.get("hotkey", "Z"))
        self.edit_hotkey.setReadOnly(True)

        btn_cap = QPushButton("SEÇ")
        btn_cap.clicked.connect(self.start_capture_hotkey)

        h_key = QHBoxLayout()
        h_key.addWidget(self.edit_hotkey)
        h_key.addWidget(btn_cap)
        gl.addLayout(h_key, 0, 1)

        gl.addWidget(QLabel("MOD:"), 1, 0)
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItem("TOGGLE (AÇ/KAPA)", "toggle")
        self.cmb_mode.addItem("HOLD (BASILI TUT)", "hold")
        idx = self.cmb_mode.findData(current_config.get("mode", "toggle"))
        if idx >= 0:
            self.cmb_mode.setCurrentIndex(idx)
        gl.addWidget(self.cmb_mode, 1, 1)

        gl.addWidget(QLabel("ATAK SKILL (0-9):"), 2, 0)
        self.cmb_skill = QComboBox()
        self.cmb_skill.addItems([str(i) for i in range(10)])
        self.cmb_skill.setCurrentText(str(current_config.get("skill_key", 2)))
        gl.addWidget(self.cmb_skill, 2, 1)

        gl.addWidget(QLabel("SKILL HIZI (SN):"), 3, 0)
        self.spin_skill_delay = QDoubleSpinBox()
        self.spin_skill_delay.setRange(0.01, 1.0)
        self.spin_skill_delay.setSingleStep(0.01)
        self.spin_skill_delay.setValue(float(current_config.get("skill_delay", 0.05)))
        gl.addWidget(self.spin_skill_delay, 3, 1)

        gl.addWidget(QLabel("R HIZI (SN):"), 4, 0)
        self.spin_r_delay = QDoubleSpinBox()
        self.spin_r_delay.setRange(0.01, 1.0)
        self.spin_r_delay.setSingleStep(0.01)
        self.spin_r_delay.setValue(float(current_config.get("r_delay", 0.02)))
        gl.addWidget(self.spin_r_delay, 4, 1)

        self.chk_z = QCheckBox("OTO Z BAS")
        self.chk_z.setChecked(bool(current_config.get("z_enabled", False)))
        gl.addWidget(self.chk_z, 5, 0, 1, 2)

        layout.addWidget(grp_genel)

        # -------------------------------------------------
        # GRUP 2: KİTAP AYARLARI
        # -------------------------------------------------
        grp_kitap = QGroupBox("📖 KİTAP AYARLARI")
        gk = QGridLayout(grp_kitap)

        self.chk_kitap = QCheckBox("AKTİF ET")
        self.chk_kitap.setChecked(bool(current_config.get("kitap_enabled", False)))
        gk.addWidget(self.chk_kitap, 0, 0, 1, 2)

        gk.addWidget(QLabel("KİTAP TUŞU (0-9):"), 1, 0)
        self.cmb_kitap_key = QComboBox()
        self.cmb_kitap_key.addItems([str(i) for i in range(10)])
        self.cmb_kitap_key.setCurrentText(str(current_config.get("kitap_key", 8)))
        gk.addWidget(self.cmb_kitap_key, 1, 1)

        gk.addWidget(QLabel("SÜRE (SN):"), 2, 0)
        self.spin_kitap_time = QDoubleSpinBox()
        self.spin_kitap_time.setRange(0.1, 600.0)
        self.spin_kitap_time.setSingleStep(0.5)
        self.spin_kitap_time.setValue(float(current_config.get("kitap_delay", 3.0)))
        gk.addWidget(self.spin_kitap_time, 2, 1)

        layout.addWidget(grp_kitap)

        # -------------------------------------------------
        # GRUP 3: KOL AYARLARI
        # -------------------------------------------------
        grp_kol = QGroupBox("💪 KOL / EKSTRA SKILL")
        gkol = QGridLayout(grp_kol)

        self.chk_kol = QCheckBox("AKTİF ET")
        self.chk_kol.setChecked(bool(current_config.get("kol_enabled", False)))
        gkol.addWidget(self.chk_kol, 0, 0, 1, 2)

        gkol.addWidget(QLabel("KOL TUŞU (0-9):"), 1, 0)
        self.cmb_kol_key = QComboBox()
        self.cmb_kol_key.addItems([str(i) for i in range(10)])
        self.cmb_kol_key.setCurrentText(str(current_config.get("kol_key", 9)))
        gkol.addWidget(self.cmb_kol_key, 1, 1)

        gkol.addWidget(QLabel("SÜRE (SN):"), 2, 0)
        self.spin_kol_time = QDoubleSpinBox()
        self.spin_kol_time.setRange(0.1, 600.0)
        self.spin_kol_time.setSingleStep(0.5)
        self.spin_kol_time.setValue(float(current_config.get("kol_delay", 3.0)))
        gkol.addWidget(self.spin_kol_time, 2, 1)

        layout.addWidget(grp_kol)

        # -------------------------------------------------
        # BUTONLAR
        # -------------------------------------------------
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    # -------------------------------------------------

    def start_capture_hotkey(self):
        self._capture_next_key = True
        self.edit_hotkey.setText("BAS...")

    def keyPressEvent(self, event):
        if self._capture_next_key:
            key = event.key()
            text = event.text().upper()

            if not text and key == Qt.Key_F1:
                text = "F1"

            if text:
                self.edit_hotkey.setText(text)
                self._capture_next_key = False
            return

        super().keyPressEvent(event)

    # -------------------------------------------------

    def accept(self):
        self.result_config = {
            "hotkey": self.edit_hotkey.text(),
            "mode": self.cmb_mode.currentData(),

            "skill_key": int(self.cmb_skill.currentText()),
            "skill_delay": self.spin_skill_delay.value(),
            "r_delay": self.spin_r_delay.value(),

            "z_enabled": self.chk_z.isChecked(),
            "z_delay": 0.05,

            "kitap_enabled": self.chk_kitap.isChecked(),
            "kitap_key": int(self.cmb_kitap_key.currentText()),
            "kitap_delay": self.spin_kitap_time.value(),

            "kol_enabled": self.chk_kol.isChecked(),
            "kol_key": int(self.cmb_kol_key.currentText()),
            "kol_delay": self.spin_kol_time.value(),
        }

        super().accept()

# =========================================================
# 3. WIDGET (ANA EKRAN KARTI)
# =========================================================
class PriestAttackWidget(QFrame):

    update_signal = pyqtSignal()

    def __init__(self, parent=None, macro_instance=None, config=None):
        super().__init__(parent)

        self.macro = macro_instance
        self.config = config or {}

        self.listen_active = False
        self._hotkey_hook_handles = []
        self._last_toggle_time = 0.0

        self.update_signal.connect(self._safe_update_status)

        self.setup_ui()
        self._safe_update_status()

    # -----------------------------------------------------

    def setup_ui(self):
        self.setFrameShape(QFrame.Box)
        self.setFrameShadow(QFrame.Plain)
        self.setMaximumWidth(260)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        self.setStyleSheet("""
            QFrame {
                background-color: #101010;
                border: 1px solid #444;
                border-radius: 4px;
            }
        """)

        v = QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(4)

        # ---------------- HEADER ----------------
        header = QHBoxLayout()
        header.setSpacing(6)

        icon_row = QHBoxLayout()
        icon_row.setSpacing(3)

        icon_paths = [
            "icons/priest/pri62.png",
            "icons/priest/pri72.png"
        ]

        for path in icon_paths:
            lbl = QLabel()
            lbl.setFixedSize(25, 25)
            pix = QPixmap(path)
            if not pix.isNull():
                lbl.setPixmap(
                    pix.scaled(25, 25, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
            else:
                lbl.setText("✝️")
                lbl.setStyleSheet("border:none; font-size:16px;")
            icon_row.addWidget(lbl)

        header.addLayout(icon_row)
        header.addStretch(1)

        title = QLabel("BP ATAK")
        title.setObjectName("MinorHeaderLabel")
        header.addWidget(title)

        v.addLayout(header)

        # ---------------- LISTEN BUTTON ----------------
        self.btn_listen = QPushButton("TUŞ DİNLEMEYİ BAŞLAT")
        self.btn_listen.setObjectName("ThreeFiveListenButton")
        self.btn_listen.setProperty("active", False)
        self.btn_listen.clicked.connect(self.toggle_listen)
        v.addWidget(self.btn_listen)

        # ---------------- STATUS ----------------
        self.lbl_status = QLabel("DURUM: PASİF")
        self.lbl_status.setObjectName("MinorStatusLabel")
        v.addWidget(self.lbl_status)

        # ---------------- HOTKEY + SETTINGS ----------------
        row = QHBoxLayout()
        row.setSpacing(4)

        row.addWidget(QLabel("AKTİF TUŞ:"))

        self.lbl_hotkey = QLabel(self.config.get("hotkey", "Z"))
        self.lbl_hotkey.setAlignment(Qt.AlignCenter)
        self.lbl_hotkey.setObjectName("HotkeyLabel")
        row.addWidget(self.lbl_hotkey)

        btn_settings = QPushButton("⚙ AYARLAR")
        btn_settings.setFlat(True)
        btn_settings.setIcon(QIcon("icons/gear.png"))
        btn_settings.setIconSize(QSize(12, 12))
        btn_settings.clicked.connect(self.open_settings)
        row.addWidget(btn_settings)

        v.addLayout(row)

    # -----------------------------------------------------

    def open_settings(self):
        dlg = PriestAttackSettingsDialog(self, self.config)
        if dlg.exec_() == QDialog.Accepted and dlg.result_config:
            self.config.update(dlg.result_config)
            self.macro.update_config(self.config)
            self.lbl_hotkey.setText(self.config.get("hotkey", "Z"))

            if self.listen_active:
                self.toggle_listen()
                self.toggle_listen()

    # -----------------------------------------------------

    def toggle_listen(self):
        try:
            import keyboard
        except ImportError:
            QMessageBox.warning(self, "Hata", "'keyboard' kütüphanesi eksik.")
            return

        if not self.listen_active:
            hotkey = self.config.get("hotkey", "Z").lower()
            mode = self.config.get("mode", "toggle")

            self._hotkey_hook_handles.clear()

            try:
                if mode == "hold":
                    h1 = keyboard.on_press_key(
                        hotkey, lambda e: self.on_hold_down(), suppress=False
                    )
                    h2 = keyboard.on_release_key(
                        hotkey, lambda e: self.on_hold_up(), suppress=False
                    )
                    self._hotkey_hook_handles.extend([h1, h2])
                else:
                    h = keyboard.on_press_key(
                        hotkey, lambda e: self.on_hotkey_toggle(), suppress=False
                    )
                    self._hotkey_hook_handles.append(h)

                self.listen_active = True
                print(f"[PRIEST] Dinleniyor: {hotkey}")

            except Exception as e:
                print(f"[PRIEST] Hotkey hatası: {e}")
                self.listen_active = False

        else:
            for h in self._hotkey_hook_handles:
                try:
                    keyboard.unhook(h)
                except Exception:
                    pass

            self._hotkey_hook_handles.clear()
            self.listen_active = False

            if self.macro.is_running:
                self.macro.stop()

        self._safe_update_status()

    # -----------------------------------------------------

    def on_hold_down(self):
        self.macro.hold_down()
        self.update_signal.emit()

    def on_hold_up(self):
        self.macro.hold_up()
        self.update_signal.emit()

    def on_hotkey_toggle(self):
        now = time.time()
        if now - self._last_toggle_time < 0.2:
            return

        self._last_toggle_time = now
        self.macro.toggle()
        self.update_signal.emit()

    # -----------------------------------------------------

    def apply_status_style(self, color: str):
        self.lbl_status.setStyleSheet(
            f"color: {color}; font-weight: bold;"
        )

    def _safe_update_status(self):
        if not self.listen_active:
            self.lbl_status.setText("DURUM: PASİF")
            self.btn_listen.setText("TUŞ DİNLEMEYİ BAŞLAT")
            self.apply_status_style("#ff5555")
            active = False

        else:
            if self.macro.is_running:
                self.lbl_status.setText("DURUM: ÇALIŞIYOR")
                self.apply_status_style("#00ff4c")
            else:
                self.lbl_status.setText("DURUM: BEKLİYOR")
                self.apply_status_style("#ffff55")

            self.btn_listen.setText("TUŞ DİNLEMEYİ DURDUR")
            active = True

        self.btn_listen.setProperty("active", active)
        self.btn_listen.style().unpolish(self.btn_listen)
        self.btn_listen.style().polish(self.btn_listen)
