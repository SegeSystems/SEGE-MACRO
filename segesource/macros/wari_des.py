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

# --- wari_des.py ---

import threading
import time
import pyautogui

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
SC_1 = 0x02
SC_2 = 0x03
SC_R = 0x13
SC_Z = 0x2C

# F Tuşları Mapping
F_SCANCODES = {
    1: 0x3B, 2: 0x3C, 3: 0x3D, 4: 0x3E,
    5: 0x3F, 6: 0x40, 7: 0x41, 8: 0x42
}

DIGIT_MAP = {
    '1': 0x02, '2': 0x03, '3': 0x04, '4': 0x05, '5': 0x06,
    '6': 0x07, '7': 0x08, '8': 0x09, '9': 0x0A, '0': 0x0B
}

# F Key string'i -> int'e çeviren map
F_KEY_MAP = {f"F{i}": i for i in range(1, 9)}
F_KEY_MAP["F YOK"] = 0

# ---------------------------------------------------------
# 1. LOGIC (MAKRO MOTORU)
# ---------------------------------------------------------
class WarriorDesMacro:
    """
    SADELEŞTİRİLMİŞ WARRIOR DES:
    1. F Sayfasına Geç
    2. DES (X-X)
    3. Yere Vur (2-2)
    4. Kombo (Z+Skill+R)
    5. Kombo Sonu F
    """
    def __init__(self):
        self.fkey = "F2"
        self.combo_order = "3456"
        self.skill_speed = 0.28
        self.r_speed = 0.26

        # >>> YENİ
        self.des_skill = '1'
        self.end_fkey = "F YOK"
        # <<<

        self._driver = _ClicksendKeyboardDriver() if _ClicksendKeyboardDriver else None
        self._main_thread = None
        self._running = False
        self._lock = threading.Lock()

    def update_config(self, cfg):
        with self._lock:
            self.fkey = cfg.get("fkey", "F2")
            self.combo_order = cfg.get("combo_order", "3456")
            self.skill_speed = float(cfg.get("key_2_duration", 0.28))
            self.r_speed = float(cfg.get("r_speed", 0.26))

            # >>> YENİ
            self.des_skill = cfg.get("des_skill", '1')
            self.end_fkey = cfg.get("end_fkey", "F YOK")
            # <<<

    @property
    def is_running(self): 
        return self._running

    def run_once(self):
        if not self._running:
            self._start_internal()

    def stop(self): 
        self._running = False

    def _start_internal(self):
        print("[DES] Tetiklendi...")
        self._running = True
        self._main_thread = threading.Thread(target=self._run_logic, daemon=True)
        self._main_thread.start()

    # -----------------------------------------------------
    # TUŞ BASMA YARDIMCILARI
    # -----------------------------------------------------
    def _scancode_to_keyname(self, sc):
        if sc == SC_R: return 'r'
        if sc == SC_Z: return 'z'
        for k, v in DIGIT_MAP.items():
            if v == sc: return k
        for k, v in F_SCANCODES.items():
            if v == sc: return f"f{k}"
        return None

    def _tap_scan(self, scancode, delay=0.05):
        if not scancode: 
            return
        if self._driver:
            self._driver.tusbas(scancode, delay)
        else:
            key_name = self._scancode_to_keyname(scancode)
            if key_name:
                pyautogui.keyDown(key_name)
                time.sleep(delay)
                pyautogui.keyUp(key_name)
            else:
                time.sleep(delay)

    def _press_key_name(self, key_name, duration=0.05):
        if key_name in DIGIT_MAP:
            self._tap_scan(DIGIT_MAP[key_name], duration)

    # -----------------------------------------------------
    # ANA LOGIC
    # -----------------------------------------------------
    def _run_logic(self):
        try:
            # 1. F Sayfasına Geç
            f_num = F_KEY_MAP.get(self.fkey, 0)
            if f_num > 0:
                self._tap_scan(F_SCANCODES.get(f_num), 0.05)
                time.sleep(0.08)

            # 2. DES (X-X)
            des_sc = DIGIT_MAP.get(self.des_skill)
            if des_sc:
                self._tap_scan(des_sc, 0.05); time.sleep(0.08)
                self._tap_scan(des_sc, 0.05); time.sleep(0.08)

            # 3. Yere Vur (2-2)
            self._tap_scan(SC_2, 0.05); time.sleep(0.08)
            self._tap_scan(SC_2, 0.05); time.sleep(0.20)

            # 4. Kombo
            for char in self.combo_order:
                if not self._running:
                    break

                self._tap_scan(SC_Z, 0.05)
                self._press_key_name(char, self.skill_speed)

                if char != self.combo_order[-1]:
                    self._tap_scan(SC_R, self.r_speed)
                    self._tap_scan(SC_R, self.r_speed)

            # 5. Kombo Sonu F
            end_f = F_KEY_MAP.get(self.end_fkey, 0)
            if end_f > 0:
                self._tap_scan(F_SCANCODES.get(end_f), 0.05)

        except Exception as e:
            print(f"[DES] Hata: {e}")
        finally:
            self._running = False
            print("[DES] Bitti.")

# ---------------------------------------------------------
# 2. GUI (AYAR PENCERESİ)
# ---------------------------------------------------------
class WarriorDesSettingsDialog(QDialog):
    def __init__(self, parent=None, current_config=None):
        super().__init__(parent)
        self.setWindowTitle("DES + YERE VUR AYARLARI")
        self.setModal(True)
        self._capture_next_key = False

        if current_config is None:
            current_config = {}

        key = current_config.get("key", "G")
        fkey = current_config.get("fkey", "F2")
        combo_order = current_config.get("combo_order", "3456")
        skill_speed = float(current_config.get("key_2_duration", 0.28))
        r_speed = float(current_config.get("r_speed", 0.26))

        # >>> YENİ
        des_skill = current_config.get("des_skill", '1')
        end_fkey = current_config.get("end_fkey", "F YOK")
        # <<<

        layout = QGridLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Tetik Tuşu
        layout.addWidget(QLabel("AKTIF TUS:"), 0, 0)
        self.edit_hotkey = QLineEdit(key)
        self.edit_hotkey.setReadOnly(True)
        hk = QHBoxLayout()
        hk.addWidget(self.edit_hotkey)
        b = QPushButton("TUŞ SEÇ")
        b.clicked.connect(self.start_capture_hotkey)
        hk.addWidget(b)
        layout.addLayout(hk, 0, 1)

        # F Sayfası
        layout.addWidget(QLabel("DES SAYFASI (F):"), 1, 0)
        self.cmb_f = QComboBox()
        self.cmb_f.addItem("F YOK")
        self.cmb_f.addItems([f"F{i}" for i in range(1, 9)])
        self.cmb_f.setCurrentText(fkey)
        layout.addWidget(self.cmb_f, 1, 1)

        # Kombo
        layout.addWidget(QLabel("KOMBO SIRASI:"), 2, 0)
        self.cmb_order = QComboBox()
        self.cmb_order.addItems(['1234','2345','3456','4567','5678'])
        self.cmb_order.setCurrentText(combo_order)
        layout.addWidget(self.cmb_order, 2, 1)

        # Hızlar
        layout.addWidget(QLabel("SKILL HIZI:"), 3, 0)
        self.spin_s = QDoubleSpinBox()
        self.spin_s.setRange(0.01, 1.0)
        self.spin_s.setValue(skill_speed)
        layout.addWidget(self.spin_s, 3, 1)

        layout.addWidget(QLabel("R HIZI:"), 4, 0)
        self.spin_r = QDoubleSpinBox()
        self.spin_r.setRange(0.01, 1.0)
        self.spin_r.setValue(r_speed)
        layout.addWidget(self.spin_r, 4, 1)

        # >>> YENİ DES SKILL
        layout.addWidget(QLabel("DES SKILL SLOTU:"), 5, 0)
        self.cmb_des = QComboBox()
        self.cmb_des.addItems(list(DIGIT_MAP.keys()))
        self.cmb_des.setCurrentText(des_skill)
        layout.addWidget(self.cmb_des, 5, 1)

        # >>> YENİ KOMBO SONU F
        layout.addWidget(QLabel("KOMBO SONU F TUSU:"), 6, 0)
        self.cmb_end_f = QComboBox()
        self.cmb_end_f.addItem("F YOK")
        self.cmb_end_f.addItems([f"F{i}" for i in range(1, 9)])
        self.cmb_end_f.setCurrentText(end_fkey)
        layout.addWidget(self.cmb_end_f, 6, 1)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns, 7, 0, 1, 2)

    def start_capture_hotkey(self):
        self._capture_next_key = True
        self.edit_hotkey.setText("TUŞA BAS...")

    def keyPressEvent(self, e):
        if self._capture_next_key:
            self.edit_hotkey.setText(e.text().upper())
            self._capture_next_key = False
        else:
            super().keyPressEvent(e)

    def accept(self):
        self.result_config = {
            "key": self.edit_hotkey.text(),
            "fkey": self.cmb_f.currentText(),
            "combo_order": self.cmb_order.currentText(),
            "key_2_duration": self.spin_s.value(),
            "r_speed": self.spin_r.value(),
            "des_skill": self.cmb_des.currentText(),
            "end_fkey": self.cmb_end_f.currentText(),
        }
        super().accept()

# ---------------------------------------------------------
# 3. WIDGET (ANA EKRAN KARTI)
# ---------------------------------------------------------
class WarriorDesWidget(QFrame):
    update_signal = pyqtSignal()

    def __init__(self, parent=None, macro_instance=None, config=None):
        super().__init__(parent)
        self.macro = macro_instance
        self.config = config or {}

        self.macro.update_config(self.config)
        self.listen_active = False
        self._hooks = []

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

        h = QHBoxLayout()
        icon_list = ["yv1.png","yv2.png","yv3.png","yv4.png"]
        for i in icon_list:
            l = QLabel(); l.setFixedSize(25,25)
            p = QPixmap(f"icons/wari/{i}")
            if not p.isNull():
                l.setPixmap(p.scaled(25,25,Qt.KeepAspectRatio,Qt.SmoothTransformation))
            h.addWidget(l)
        t = QLabel("DES / YERE VUR"); t.setObjectName("MinorHeaderLabel")
        h.addStretch(); h.addWidget(t)
        v.addLayout(h)

        self.btn_listen = QPushButton("TUŞ DİNLEMEYİ BAŞLAT")
        self.btn_listen.setObjectName("ThreeFiveListenButton")
        self.btn_listen.clicked.connect(self.toggle_listen)
        v.addWidget(self.btn_listen)

        self.lbl_status = QLabel("DURUM: PASİF")
        self.lbl_status.setObjectName("MinorStatusLabel")
        v.addWidget(self.lbl_status)

        r = QHBoxLayout()
        r.addWidget(QLabel("AKTIF TUS:"))
        self.lbl_hotkey = QLabel(self.config.get("key","G"))
        self.lbl_hotkey.setObjectName("HotkeyLabel")
        r.addWidget(self.lbl_hotkey)

        s = QPushButton("⚙ AYARLAR")
        s.setObjectName("MinorSettingsButton")
        s.setFlat(True)
        s.clicked.connect(self.open_settings)
        r.addWidget(s)
        v.addLayout(r)

    def open_settings(self):
        dlg = WarriorDesSettingsDialog(self, self.config)
        if dlg.exec_() == QDialog.Accepted:
            self.config.update(dlg.result_config)
            self.macro.update_config(self.config)
            self.lbl_hotkey.setText(self.config["key"])
            if self.listen_active:
                self.toggle_listen()
                self.toggle_listen()

    def toggle_listen(self):
        import keyboard
        if not self.listen_active:
            try:
                k = self.config.get("key","G").lower()
                self._hooks.append(
                    keyboard.on_press_key(k, lambda e: self.macro.run_once())
                )
                self.listen_active = True
            except:
                self.listen_active = False
        else:
            for h in self._hooks:
                try: keyboard.unhook(h)
                except: pass
            self._hooks = []
            self.listen_active = False
            self.macro.stop()
        self._safe_update_status()

    def apply_status_style(self, c):
        self.lbl_status.setStyleSheet(f"color:{c};font-weight:bold;")

    def _safe_update_status(self):
        if not self.listen_active:
            self.lbl_status.setText("DURUM: PASİF")
            self.apply_status_style("#ff5555")
            self.btn_listen.setText("TUŞ DİNLEMEYİ BAŞLAT")
            act = False
        else:
            if self.macro.is_running:
                self.lbl_status.setText("DURUM: ÇALIŞIYOR")
                self.apply_status_style("#00ff4c")
            else:
                self.lbl_status.setText("DURUM: HAZIR")
                self.apply_status_style("#ffff55")
            self.btn_listen.setText("TUŞ DİNLEMEYİ DURDUR")
            act = True

        # >>> BURASI EKSİKTİ (GLOW)
        self.btn_listen.setProperty("active", act)
        self.btn_listen.style().unpolish(self.btn_listen)
        self.btn_listen.style().polish(self.btn_listen)
