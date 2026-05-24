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
import os
import cv2
import numpy as np
import mss
import pyautogui
import json
import ctypes
import random

from PyQt5.QtWidgets import (
    QDialog, QGridLayout, QLabel, QComboBox, 
    QLineEdit, QPushButton, QDoubleSpinBox, 
    QDialogButtonBox, QHBoxLayout, QWidget,
    QFrame, QVBoxLayout, QSizePolicy, QMessageBox,
    QCheckBox, QGroupBox, QScrollArea, QSpinBox, QApplication, QFormLayout
)
from PyQt5.QtGui import QPixmap, QIcon, QPainter, QPen, QColor, QCursor, QImage, QBrush, QKeySequence
from PyQt5.QtCore import Qt, QSize, pyqtSignal, QTimer, QPoint, QRect

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except:
    pass

# Sürücü Kontrolü
try:
    from clicksend import KeyboardDriver as _ClicksendKeyboardDriver
    from clicksend import MouseDriver as _ClicksendMouseDriver
except ImportError:
    _ClicksendKeyboardDriver = None
    _ClicksendMouseDriver = None

try:
    import keyboard
except ImportError:
    keyboard = None

# --- SCANCODES ---
SC_R = 0x13; SC_W = 0x11; SC_S = 0x1F; SC_Z = 0x2C
SC_ESC = 0x01
SC_MIDDLE_CLICK = 999 
DIGIT_SCANCODES = {1:0x02, 2:0x03, 3:0x04, 4:0x05, 5:0x06, 6:0x07, 7:0x08, 8:0x09, 9:0x0A, 0:0x0B}

# F1 - F8
F_SCANCODES = {1: 0x3B, 2: 0x3C, 3: 0x3D, 4: 0x3E, 5: 0x3F, 6: 0x40, 7: 0x41, 8: 0x42}
FKEY_SCANCODES_STR = {"F1": 0x3B, "F2": 0x3C, "F3": 0x3D, "F4": 0x3E, "F5": 0x3F, "F6": 0x40, "F7": 0x41, "F8": 0x42}

# --- WINDOWS INPUT STRUCTURES ---
PUL = ctypes.POINTER(ctypes.c_ulong)
class KeyBdInput(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort), ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong), ("dwExtraInfo", PUL)]
class HardwareInput(ctypes.Structure):
    _fields_ = [("uMsg", ctypes.c_ulong), ("wParamL", ctypes.c_ushort), ("wParamH", ctypes.c_ushort)]
class MouseInput(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long), ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong), ("dwExtraInfo", PUL)]
class Input_I(ctypes.Union):
    _fields_ = [("ki", KeyBdInput), ("mi", MouseInput), ("hi", HardwareInput)]
class Input(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("ii", Input_I)]

# --- AYAR KAYIT DOSYASI ---
CONFIG_FILE = "antiafk_settings.json"

# =========================================================
# YARDIMCI: EKRAN SEÇİCİLER
# =========================================================
class FullScreenSelector(QDialog):
    def __init__(self, mode="area", title=""):
        super().__init__()
        self.mode = mode 
        self.title = title
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.screen = QApplication.primaryScreen()
        self.screen_geo = self.screen.geometry()
        self.setGeometry(self.screen_geo)
        self.full_screenshot = self.screen.grabWindow(0)
        self.start_pos = None; self.current_pos = None; self.result = None
        self.setCursor(Qt.CrossCursor)

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self.full_screenshot)
        overlay_color = QColor(0, 0, 0, 100)
        if self.mode == "area":
            if self.start_pos and self.current_pos:
                selection_rect = QRect(self.start_pos, self.current_pos).normalized()
                painter.setBrush(QBrush(overlay_color))
                painter.setPen(Qt.NoPen)
                painter.drawRect(0, 0, self.width(), selection_rect.top())
                painter.drawRect(0, selection_rect.bottom(), self.width(), self.height() - selection_rect.bottom())
                painter.drawRect(0, selection_rect.top(), selection_rect.left(), selection_rect.height())
                painter.drawRect(selection_rect.right(), selection_rect.top(), self.width() - selection_rect.right(), selection_rect.height())
                painter.setBrush(Qt.NoBrush); painter.setPen(QPen(Qt.green, 2)); painter.drawRect(selection_rect)
            else:
                painter.fillRect(self.rect(), overlay_color)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            if self.mode == "pixel":
                img = self.full_screenshot.toImage()
                color = QColor(img.pixel(e.x(), e.y()))
                self.result = [color.red(), color.green(), color.blue()]
                self.accept()
            else:
                self.start_pos = e.pos(); self.current_pos = e.pos()
        elif e.button() == Qt.RightButton: self.reject()

    def mouseMoveEvent(self, e):
        self.current_pos = e.pos(); self.update()

    def mouseReleaseEvent(self, e):
        if self.mode == "area" and self.start_pos:
            rect = QRect(self.start_pos, e.pos()).normalized()
            if rect.width() > 5 and rect.height() > 5:
                self.result = (rect.left(), rect.top(), rect.width(), rect.height())
                self.accept()
            else: self.reject()

# =========================================================
# DETAYLI AYAR PENCERELERİ
# =========================================================
class WarriorSkillSettingsDialog(QDialog):
    def __init__(self, parent=None, current_config=None):
        super().__init__(parent); self.setWindowTitle("WARRIOR AYARLARI"); self.result_config = current_config or {}; l = QGridLayout(self)
        l.addWidget(QLabel("SKILL BAR:"), 0, 0); self.cmb_bar = QComboBox(); self.cmb_bar.addItems(["FYOK"] + [f"F{i}" for i in range(1,9)]); self.cmb_bar.setCurrentText(self.result_config.get("skill_bar", "FYOK")); l.addWidget(self.cmb_bar, 0, 1)
        l.addWidget(QLabel("SKILL SLOTU:"), 1, 0); self.cmb_key = QComboBox(); self.cmb_key.addItems([str(i) for i in range(10)]); self.cmb_key.setCurrentText(str(self.result_config.get("skill_key", 2))); l.addWidget(self.cmb_key, 1, 1)
        l.addWidget(QLabel("KOMBO:"), 2, 0); self.cmb_ord = QComboBox(); self.cmb_ord.addItem("2 - R - R", "2rr"); self.cmb_ord.addItem("R - R - 2", "rr2"); self.cmb_ord.addItem("W - R - 2", "wr2"); idx = self.cmb_ord.findData(self.result_config.get("order", "2rr")); self.cmb_ord.setCurrentIndex(idx); l.addWidget(self.cmb_ord, 2, 1)
        l.addWidget(QLabel("SKILL HIZI:"), 3, 0); self.sp_s = QDoubleSpinBox(); self.sp_s.setRange(0, 1); self.sp_s.setSingleStep(0.01); self.sp_s.setValue(self.result_config.get("key_2_duration", 0.05)); l.addWidget(self.sp_s, 3, 1)
        l.addWidget(QLabel("R HIZI:"), 4, 0); self.sp_r = QDoubleSpinBox(); self.sp_r.setRange(0, 1); self.sp_r.setSingleStep(0.01); self.sp_r.setValue(self.result_config.get("key_r_duration", 0.02)); l.addWidget(self.sp_r, 4, 1)
        self.chk_z = QCheckBox("OTO Z BAS"); self.chk_z.setChecked(self.result_config.get("z_enabled", False)); l.addWidget(self.chk_z, 5, 0)
        btn = QPushButton("KAYDET"); btn.clicked.connect(self.accept); l.addWidget(btn, 6, 0, 1, 2)
    def accept(self):
        self.result_config.update({"skill_bar": self.cmb_bar.currentText(), "skill_key": int(self.cmb_key.currentText()), "order": self.cmb_ord.currentData(), "key_2_duration": self.sp_s.value(), "key_r_duration": self.sp_r.value(), "z_enabled": self.chk_z.isChecked()}); super().accept()

class AsasSettingsDialog(QDialog):
    def __init__(self, parent, config):
        super().__init__(parent); self.setWindowTitle("ASAS PRO AYARLARI"); self.result_config = config or {}; lay = QVBoxLayout(self)
        grp_digits = QGroupBox("Aktif Skill Slotları"); g = QGridLayout(grp_digits); self.chk_digits = {}; digits_cfg = self.result_config.get("digits", [2, 3, 4, 5, 6]); row = 0; col = 0
        for d in range(10):
            cb = QCheckBox(str(d)); cb.setChecked(d in digits_cfg); self.chk_digits[d] = cb; g.addWidget(cb,row,col); col += 1
            if col == 5: row += 1; col = 0
        lay.addWidget(grp_digits)
        grp_time = QGroupBox("Zamanlama (Saniye)"); gt = QGridLayout(grp_time)
        gt.addWidget(QLabel("Skill Basılı:"), 0, 0); self.s_press = QDoubleSpinBox(); self.s_press.setRange(0,1); self.s_press.setSingleStep(0.001); self.s_press.setDecimals(3); self.s_press.setValue(self.result_config.get("time_skill_press", 0.010)); gt.addWidget(self.s_press, 0, 1)
        gt.addWidget(QLabel("R Basılı:"), 1, 0); self.r_press = QDoubleSpinBox(); self.r_press.setRange(0,1); self.r_press.setSingleStep(0.001); self.r_press.setDecimals(3); self.r_press.setValue(self.result_config.get("time_r_press", 0.010)); gt.addWidget(self.r_press, 1, 1)
        lay.addWidget(grp_time)
        grp_r = QGroupBox("Diğer"); hr = QFormLayout(grp_r)
        self.spin_r = QSpinBox(); self.spin_r.setRange(1, 500); self.spin_r.setValue(self.result_config.get("repeat_r", 5)); hr.addRow("R Tekrar Sayısı:", self.spin_r)
        self.chk_z = QCheckBox("Combo Arası Z Bas"); self.chk_z.setChecked(self.result_config.get("use_z", False)); hr.addRow(self.chk_z); lay.addWidget(grp_r)
        btn = QPushButton("KAYDET"); btn.clicked.connect(self.accept); lay.addWidget(btn)
    def accept(self):
        digits = [d for d, btn in self.chk_digits.items() if btn.isChecked()]; self.result_config.update({"digits": digits, "repeat_r": self.spin_r.value(), "time_skill_press": self.s_press.value(), "time_r_press": self.r_press.value(), "use_z": self.chk_z.isChecked()}); super().accept()

class ThreeFiveSettingsDialog(QDialog):
    def __init__(self, parent=None, config=None):
        super().__init__(parent); self.setWindowTitle("3-5 AYARLARI"); self.result_config = config or {}; l = QGridLayout(self)
        self.chk_f = QCheckBox("F Bar Kullan"); self.chk_f.setChecked(self.result_config.get("use_f_key", True)); l.addWidget(self.chk_f, 0, 0)
        self.cmb_f = QComboBox(); self.cmb_f.addItems([f"F{i}" for i in range(1,9)]); self.cmb_f.setCurrentIndex(self.result_config.get("f_bar", 3)-1); l.addWidget(self.cmb_f, 0, 1)
        l.addWidget(QLabel("5'li OK:"), 1, 0); self.c5 = QComboBox(); self.c5.addItems([str(i) for i in range(10)]); self.c5.setCurrentText(str(self.result_config.get("key5", 2))); l.addWidget(self.c5, 1, 1)
        l.addWidget(QLabel("3'lü OK:"), 2, 0); self.c3 = QComboBox(); self.c3.addItems([str(i) for i in range(10)]); self.c3.setCurrentText(str(self.result_config.get("key3", 3))); l.addWidget(self.c3, 2, 1)
        l.addWidget(QLabel("Skill Gecikme:"), 3, 0); self.sp_c = QDoubleSpinBox(); self.sp_c.setRange(0,2); self.sp_c.setSingleStep(0.01); self.sp_c.setValue(self.result_config.get("combo_delay", 0.46)); l.addWidget(self.sp_c, 3, 1)
        l.addWidget(QLabel("W Gecikme:"), 4, 0); self.sp_w = QDoubleSpinBox(); self.sp_w.setRange(0,1); self.sp_w.setSingleStep(0.01); self.sp_w.setValue(self.result_config.get("w_delay", 0.05)); l.addWidget(self.sp_w, 4, 1)
        self.chk_z = QCheckBox("Oto Z"); self.chk_z.setChecked(self.result_config.get("use_z", False)); l.addWidget(self.chk_z, 5, 0)
        btn = QPushButton("KAYDET"); btn.clicked.connect(self.accept); l.addWidget(btn, 6, 0, 1, 2)
    def accept(self):
        self.result_config.update({"use_f_key": self.chk_f.isChecked(), "f_bar": self.cmb_f.currentIndex() + 1, "key5": int(self.c5.currentText()), "key3": int(self.c3.currentText()), "combo_delay": self.sp_c.value(), "w_delay": self.sp_w.value(), "use_z": self.chk_z.isChecked()}); super().accept()

class SelfSettingsDialog(QDialog):
    def __init__(self, parent=None, config=None, macro=None):
        super().__init__(parent); self.setWindowTitle("SELF AYARLARI"); self.config = config or {}; l = QVBoxLayout(self)
        scroll = QScrollArea(); w = QWidget(); self.sl = QVBoxLayout(w); self.rows = []; entries = self.config.get("entries", []);
        while len(entries) < 8: entries.append({"enabled":False, "key":"1", "delay":0.5})
        for i, e in enumerate(entries):
            r = QHBoxLayout(); chk = QCheckBox(f"Slot {i+1}"); chk.setChecked(e.get("enabled", False)); cmb = QComboBox(); cmb.addItems(["1","2","3","4","5","6","7","8","9","0","Z","R"]); cmb.setCurrentText(e.get("key", "1")); sp = QDoubleSpinBox(); sp.setValue(e.get("delay", 0.5)); r.addWidget(chk); r.addWidget(cmb); r.addWidget(sp); self.sl.addLayout(r); self.rows.append((chk, cmb, sp))
        scroll.setWidget(w); scroll.setWidgetResizable(True); l.addWidget(scroll); btn = QPushButton("KAYDET"); btn.clicked.connect(self.accept); l.addWidget(btn)
    def accept(self):
        new_ent = [];
        for c, k, d in self.rows:
            new_ent.append({"enabled": c.isChecked(), "key": k.currentText(), "delay": d.value()});
        self.config["entries"] = new_ent; super().accept()

# =========================================================
# GÖMÜLÜ KOMBO SINIFLARI
# =========================================================
class ComboMacroBase:
    def __init__(self, cfg=None, parent_engine=None): 
        self.config = cfg or {}
        self.parent_engine = parent_engine
    def _tap_sc(self, sc, delay):
        if self.parent_engine: self.parent_engine._execute_tap(sc, delay)
    def update_config(self, cfg):
        self.config.update(cfg)

class WarriorMacro(ComboMacroBase):
    def _do_combo_once(self):
        sc_skill = DIGIT_SCANCODES.get(int(self.config.get("skill_key", 2)))
        s_delay = float(self.config.get("key_2_duration", 0.05))
        r_delay = float(self.config.get("key_r_duration", 0.02))
        order = self.config.get("order", "2rr")
        
        if self.config.get("skill_bar") != "FYOK":
            f_code = FKEY_SCANCODES_STR.get(self.config.get("skill_bar", "F1"))
            if f_code: self._tap_sc(f_code, 0.02)
        
        if order == '2rr':
            self._tap_sc(sc_skill, s_delay); self._tap_sc(SC_R, r_delay); self._tap_sc(SC_R, r_delay)
        elif order == 'rr2':
            self._tap_sc(SC_R, r_delay); self._tap_sc(SC_R, r_delay); self._tap_sc(sc_skill, s_delay)
        elif order == 'wr2':
            self._tap_sc(SC_W, 0.05); self._tap_sc(SC_R, r_delay); self._tap_sc(sc_skill, s_delay)

class AsasMacro(ComboMacroBase):
    def run_sequence(self):
        digits = self.config.get("digits", [2, 3, 4, 5, 6])
        repeat_r = self.config.get("repeat_r", 5)
        s_press = self.config.get("time_skill_press", 0.010)
        r_press = self.config.get("time_r_press", 0.010)
        
        for d in digits:
            sc = DIGIT_SCANCODES.get(d);
            if sc: self._tap_sc(sc, s_press); time.sleep(0.01)
        for _ in range(repeat_r):
             self._tap_sc(SC_R, r_press); time.sleep(0.01)

class ThreeFiveMacro(ComboMacroBase):
    def _do_combo_once(self):
        key5 = self.config.get("key5", 2); key3 = self.config.get("key3", 3)
        c_delay = self.config.get("combo_delay", 0.46); w_delay = self.config.get("w_delay", 0.05)
        
        k5_sc = DIGIT_SCANCODES.get(int(key5)); k3_sc = DIGIT_SCANCODES.get(int(key3))
        
        if self.config.get("use_f_key"):
            sc_f = F_SCANCODES.get(int(self.config.get("f_bar", 3)), 0x3D);
            if sc_f: self._tap_sc(sc_f, 0.01)
        
        if k5_sc: self._tap_sc(k5_sc, c_delay); self._tap_sc(SC_W, w_delay)
        if k3_sc: self._tap_sc(k3_sc, c_delay); self._tap_sc(SC_W, w_delay)

class SelfMacro(ComboMacroBase):
    def run_sequence(self):
        entries = self.config.get("entries", [])
        KEY_MAP = {"1":0x02, "2":0x03, "3":0x04, "4":0x05, "5":0x06, "6":0x07, "7":0x08, "8":0x09, "9":0x0A, "0":0x0B, "Z":0x2C, "R":0x13}
        for item in entries:
            if item.get("enabled"):
                sc = KEY_MAP.get(item.get("key"))
                if sc: 
                    self._tap_sc(sc, 0.02)
                    time.sleep(float(item.get("delay", 0.1)))

class PriestMacro(ComboMacroBase):
    """Priest BP Atak - Skill + R + R, opsiyonel kitap & kol"""
    def __init__(self, cfg=None, parent_engine=None):
        super().__init__(cfg, parent_engine)
        self._last_kitap_time = 0.0
        self._last_kol_time = 0.0

    def do_attack(self):
        now = time.time()
        # Kitap kontrolu
        if self.config.get("kitap_enabled", False):
            kitap_delay = float(self.config.get("kitap_delay", 3.0))
            if now - self._last_kitap_time >= kitap_delay:
                kitap_key = int(self.config.get("kitap_key", 8))
                sc = DIGIT_SCANCODES.get(kitap_key)
                if sc: self._tap_sc(sc, 0.05)
                self._last_kitap_time = now
                time.sleep(0.15)
        # Kol kontrolu
        if self.config.get("kol_enabled", False):
            kol_delay = float(self.config.get("kol_delay", 3.0))
            if now - self._last_kol_time >= kol_delay:
                kol_key = int(self.config.get("kol_key", 9))
                sc = DIGIT_SCANCODES.get(kol_key)
                if sc: self._tap_sc(sc, 0.05)
                self._last_kol_time = now
                time.sleep(0.15)
        # Ana atak combo: Skill + R + R
        skill_key = int(self.config.get("skill_key", 2))
        skill_delay = float(self.config.get("skill_delay", 0.05))
        r_delay = float(self.config.get("r_delay", 0.02))
        sc_skill = DIGIT_SCANCODES.get(skill_key)
        if sc_skill: self._tap_sc(sc_skill, skill_delay)
        self._tap_sc(SC_R, r_delay)
        self._tap_sc(SC_R, r_delay)

class PriestSettingsDialog(QDialog):
    def __init__(self, parent=None, current_config=None):
        super().__init__(parent)
        self.setWindowTitle("PRIEST BP AYARLARI")
        self.result_config = current_config or {}
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Temel Atak Grubu
        grp_genel = QGroupBox("TEMEL ATAK")
        gl = QGridLayout(grp_genel)

        gl.addWidget(QLabel("ATAK SKILL (0-9):"), 0, 0)
        self.cmb_skill = QComboBox()
        self.cmb_skill.addItems([str(i) for i in range(10)])
        self.cmb_skill.setCurrentText(str(self.result_config.get("skill_key", 2)))
        gl.addWidget(self.cmb_skill, 0, 1)

        gl.addWidget(QLabel("SKILL GECİKME:"), 1, 0)
        self.spin_skill_delay = QDoubleSpinBox()
        self.spin_skill_delay.setRange(0.01, 1.0)
        self.spin_skill_delay.setSingleStep(0.01)
        self.spin_skill_delay.setValue(self.result_config.get("skill_delay", 0.05))
        gl.addWidget(self.spin_skill_delay, 1, 1)

        gl.addWidget(QLabel("R GECİKME:"), 2, 0)
        self.spin_r_delay = QDoubleSpinBox()
        self.spin_r_delay.setRange(0.01, 1.0)
        self.spin_r_delay.setSingleStep(0.01)
        self.spin_r_delay.setValue(self.result_config.get("r_delay", 0.02))
        gl.addWidget(self.spin_r_delay, 2, 1)

        layout.addWidget(grp_genel)

        # Kitap Grubu
        grp_kitap = QGroupBox("KİTAP")
        kl = QGridLayout(grp_kitap)

        self.chk_kitap = QCheckBox("KİTAP AKTİF")
        self.chk_kitap.setChecked(self.result_config.get("kitap_enabled", False))
        kl.addWidget(self.chk_kitap, 0, 0, 1, 2)

        kl.addWidget(QLabel("KİTAP TUŞU:"), 1, 0)
        self.cmb_kitap_key = QComboBox()
        self.cmb_kitap_key.addItems([str(i) for i in range(10)])
        self.cmb_kitap_key.setCurrentText(str(self.result_config.get("kitap_key", 8)))
        kl.addWidget(self.cmb_kitap_key, 1, 1)

        kl.addWidget(QLabel("KİTAP SÜRESİ (sn):"), 2, 0)
        self.spin_kitap_time = QDoubleSpinBox()
        self.spin_kitap_time.setRange(1.0, 60.0)
        self.spin_kitap_time.setValue(self.result_config.get("kitap_delay", 3.0))
        kl.addWidget(self.spin_kitap_time, 2, 1)

        layout.addWidget(grp_kitap)

        # Kol Grubu
        grp_kol = QGroupBox("KOL")
        kol_l = QGridLayout(grp_kol)

        self.chk_kol = QCheckBox("KOL AKTİF")
        self.chk_kol.setChecked(self.result_config.get("kol_enabled", False))
        kol_l.addWidget(self.chk_kol, 0, 0, 1, 2)

        kol_l.addWidget(QLabel("KOL TUŞU:"), 1, 0)
        self.cmb_kol_key = QComboBox()
        self.cmb_kol_key.addItems([str(i) for i in range(10)])
        self.cmb_kol_key.setCurrentText(str(self.result_config.get("kol_key", 9)))
        kol_l.addWidget(self.cmb_kol_key, 1, 1)

        kol_l.addWidget(QLabel("KOL SÜRESİ (sn):"), 2, 0)
        self.spin_kol_time = QDoubleSpinBox()
        self.spin_kol_time.setRange(1.0, 60.0)
        self.spin_kol_time.setValue(self.result_config.get("kol_delay", 3.0))
        kol_l.addWidget(self.spin_kol_time, 2, 1)

        layout.addWidget(grp_kol)

        # Kaydet butonu
        btn = QPushButton("KAYDET")
        btn.clicked.connect(self.accept)
        layout.addWidget(btn)

    def accept(self):
        self.result_config = {
            "skill_key": int(self.cmb_skill.currentText()),
            "skill_delay": self.spin_skill_delay.value(),
            "r_delay": self.spin_r_delay.value(),
            "kitap_enabled": self.chk_kitap.isChecked(),
            "kitap_key": int(self.cmb_kitap_key.currentText()),
            "kitap_delay": self.spin_kitap_time.value(),
            "kol_enabled": self.chk_kol.isChecked(),
            "kol_key": int(self.cmb_kol_key.currentText()),
            "kol_delay": self.spin_kol_time.value(),
        }
        super().accept()

# =========================================================
# 1. LOGIC (ANTIAFK MOTORU)
# =========================================================
class AntiAfkEngine:
    def __init__(self):
        self.config = self._load_config()
        self._running = False
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self.kb = _ClicksendKeyboardDriver() if _ClicksendKeyboardDriver else None
        self.mouse = _ClicksendMouseDriver() if _ClicksendMouseDriver else None
        
        self.last_clicked_coords = [] 
        self.blacklist_coords = [] 
        self.img_name = None; self.img_box = None; self.img_drop = None; self.img_hp = None; self.img_loot_window = None
        
        self.sub_macros = self._initialize_sub_macros()
        self.attack_mode = self.config.get("mode", "Warrior (Seri)")
        self.turn_interval = float(self.config.get("turn_interval", 1.5))
        self.last_turn_time = 0

    def _load_config(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        return {}

    def _initialize_sub_macros(self):
        return {
            "Warrior (Seri)": WarriorMacro(parent_engine=self),
            "Asas (VS)": AsasMacro(parent_engine=self),
            "Okçu (3-5)": ThreeFiveMacro(parent_engine=self),
            "Priest (BP)": PriestMacro(parent_engine=self),
            "Self (Özel)": SelfMacro(parent_engine=self),
        }

    def _execute_tap(self, sc, delay):
        if sc == SC_MIDDLE_CLICK:
             if self.mouse: 
                 mx, my = pyautogui.size(); 
                 pyautogui.moveTo(int(mx/2), int(my/2))
                 pyautogui.mouseDown(button='middle')
                 time.sleep(0.20)
                 pyautogui.mouseUp(button='middle')
             else: 
                 pyautogui.click(button='middle')
             return

        if self.kb: self.kb.tusbas(sc, delay)
        else: pyautogui.press(keyboard.get_hotkey_name(sc) if keyboard else 'r')

    # W BASILI TUTMA (DRIVER VEYA DIRECTINPUT)
    def _driver_hold(self, sc):
        if self.kb and hasattr(self.kb, 'keydown'):
            try: self.kb.keydown(sc); return
            except: pass
        extra = ctypes.c_ulong(0); ii_ = Input_I(); ii_.ki = KeyBdInput(0, sc, 0x0008, 0, ctypes.pointer(extra)); x = Input(ctypes.c_ulong(1), ii_); ctypes.windll.user32.SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))

    def _driver_release(self, sc):
        if self.kb and hasattr(self.kb, 'keyup'):
            try: self.kb.keyup(sc); return
            except: pass
        extra = ctypes.c_ulong(0); ii_ = Input_I(); ii_.ki = KeyBdInput(0, sc, 0x0008 | 0x0002, 0, ctypes.pointer(extra)); x = Input(ctypes.c_ulong(1), ii_); ctypes.windll.user32.SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))

    def update_config(self, cfg):
        with self._lock:
            self.config = cfg
            self.attack_mode = self.config.get("mode", "Warrior (Seri)")
            self.turn_interval = float(self.config.get("turn_interval", 1.5))
            self._load_resources()
            
            for mode, macro in self.sub_macros.items():
                 sub_key = f"subconfig_{mode}"
                 if sub_key in self.config and hasattr(macro, 'update_config'):
                      cfg_copy = self.config[sub_key].copy()
                      cfg_copy["z_enabled"] = False 
                      cfg_copy["use_z"] = False
                      macro.update_config(cfg_copy)

    def _load_resources(self):
        for key in ["path_name", "path_box", "path_drop", "path_hp", "path_loot_window"]:
            path = self.config.get(key)
            if path and os.path.exists(path):
                img = cv2.imread(path); setattr(self, key.replace("path_", "img_"), img)
            else:
                setattr(self, key.replace("path_", "img_"), None)

    @property
    def is_running(self): return self._running
    def stop(self): self._stop_event.set(); self._running = False
    def toggle(self):
        if self._running: self.stop()
        else:
            self._stop_event.clear(); self._running = True
            self.last_turn_time = time.time()
            threading.Thread(target=self._main_loop, daemon=True).start()

    def _tap(self, sc, delay=0.03):
        self._execute_tap(sc, delay)

    def _click(self, x, y, right=False):
        # Bu fonksiyon genel tıklamalar içindir
        if self.mouse:
            if right: self.mouse.rightclick(0.05, int(x), int(y))
            else: self.mouse.leftclick(0.05, int(x), int(y))
        else: 
            pyautogui.click(int(x), int(y), button='right' if right else 'left')

    def _is_match(self, sct, template, validation_region):
        if template is None or not validation_region: return False
        try:
            mon = {"left": int(validation_region[0]), "top": int(validation_region[1]), "width": int(validation_region[2]), "height": int(validation_region[3])}
            scr = np.array(sct.grab(mon))
            res = cv2.matchTemplate(scr[:,:,:3], template, cv2.TM_CCOEFF_NORMED)
            return cv2.minMaxLoc(res)[1] > 0.68
        except Exception as e: 
            return False

    def _find_pixel_in_area(self, sct):
        reg = self.config.get("region_search"); target_rgb = self.config.get("pixel_rgb")
        if not reg or not target_rgb: return None
        try:
            mon = {"left": int(reg[0]), "top": int(reg[1]), "width": int(reg[2]), "height": int(reg[3])}
            scr = np.array(sct.grab(mon))
            scr_hsv = cv2.cvtColor(scr[:,:,:3], cv2.COLOR_BGR2HSV)
            target_bgr = np.array([[[target_rgb[2], target_rgb[1], target_rgb[0]]]], dtype=np.uint8)
            target_hsv = cv2.cvtColor(target_bgr, cv2.COLOR_BGR2HSV)[0][0]
            h = int(target_hsv[0]); s = int(target_hsv[1]); v = int(target_hsv[2])
            h_tol = 3; s_tol = 30; v_tol = 25
            h_min = max(0, h - h_tol); s_min = max(0, s - s_tol); v_min = max(10, v - v_tol)
            h_max = min(180, h + h_tol); s_max = min(255, s + s_tol); v_max = min(255, v + v_tol)
            lower = np.array([h_min, s_min, v_min], dtype=np.uint8); upper = np.array([h_max, s_max, v_max], dtype=np.uint8)
            mask = cv2.inRange(scr_hsv, lower, upper)
            kernel = np.ones((4,4), np.uint8); mask = cv2.erode(mask, kernel, iterations=1); mask = cv2.dilate(mask, kernel, iterations=3)
            num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
            valid_targets = []
            now = time.time()
            self.blacklist_coords = [c for c in self.blacklist_coords if now - c[2] < 20.0]
            self.last_clicked_coords = [c for c in self.last_clicked_coords if now - c[2] < 5.0]
            for i in range(1, num_labels):
                area = stats[i, cv2.CC_STAT_AREA]
                if 40 < area < 10000:
                    cx, cy = centroids[i]; gx, gy = int(reg[0] + cx), int(reg[1] + cy)
                    is_black = any(abs(gx-bx)<40 and abs(gy-by)<40 for bx,by,bt in self.blacklist_coords)
                    is_recent = any(abs(gx-lx)<70 and abs(gy-ly)<70 for lx,ly,lt in self.last_clicked_coords)
                    if not is_black and not is_recent: valid_targets.append((gx, gy))
            if valid_targets: return random.choice(valid_targets)
        except: pass
        return None

    def _find_coords_of_pixel(self, sct, reg, target_rgb):
        if not reg or not target_rgb: return None
        try:
            mon = {"left": int(reg[0]), "top": int(reg[1]), "width": int(reg[2]), "height": int(reg[3])}
            scr = np.array(sct.grab(mon))
            scr_hsv = cv2.cvtColor(scr[:,:,:3], cv2.COLOR_BGR2HSV)
            target_bgr = np.array([[[target_rgb[2], target_rgb[1], target_rgb[0]]]], dtype=np.uint8)
            target_hsv = cv2.cvtColor(target_bgr, cv2.COLOR_BGR2HSV)[0][0]
            h = int(target_hsv[0]); s = int(target_hsv[1]); v = int(target_hsv[2])
            h_tol = 3; s_tol = 30; v_tol = 25
            h_min = max(0, h - h_tol); s_min = max(0, s - s_tol); v_min = max(10, v - v_tol)
            h_max = min(180, h + h_tol); s_max = min(255, s + s_tol); v_max = min(255, v + v_tol)
            lower = np.array([h_min, s_min, v_min], dtype=np.uint8); upper = np.array([h_max, s_max, v_max], dtype=np.uint8)
            mask = cv2.inRange(scr_hsv, lower, upper)
            kernel = np.ones((4,4), np.uint8); mask = cv2.erode(mask, kernel, iterations=1); mask = cv2.dilate(mask, kernel, iterations=3)
            num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
            max_area = 0; best_coord = None
            for i in range(1, num_labels):
                area = stats[i, cv2.CC_STAT_AREA]
                if area > 20 and area > max_area:
                    max_area = area; cx, cy = centroids[i]; best_coord = (int(reg[0] + cx), int(reg[1] + cy))
            return best_coord
        except: pass
        return None

    # --- YENİLENEN CHANNEL DEĞİŞİM FONKSİYONU ---
    def _perform_channel_change(self):
        print("[ANTI-AFK] Mob bulunamadı! Channel değişimi için hazırlanıyor...")
        reg1 = self.config.get("region_cc_1") # 1. Koordinat (Button)
        reg2 = self.config.get("region_cc_2") # 2. Koordinat (Channel)
        
        if not reg1 or not reg2:
            print("[HATA] Channel koordinatları seçilmemiş!")
            return

        # Koordinat Merkezleri
        x1, y1 = reg1[0] + reg1[2] // 2, reg1[1] + reg1[3] // 2
        x2, y2 = reg2[0] + reg2[2] // 2, reg2[1] + reg2[3] // 2

        # 1. ADIM: İLK KOORDİNATA SOL TIK
        print(f"[CC] 1. Koordinata gidiliyor: {x1}, {y1}")
        ctypes.windll.user32.SetCursorPos(x1, y1) # Işınlan
        time.sleep(0.1)
        self._left_click_explicit(x1, y1)
        
        # Menünün açılması için bekle (1 saniye)
        time.sleep(1.0) 

        # 2. ADIM: İKİNCİ KOORDİNATA SOL TIK
        print(f"[CC] 2. Koordinata gidiliyor: {x2}, {y2}")
        ctypes.windll.user32.SetCursorPos(x2, y2) # Işınlan
        time.sleep(0.1)
        self._left_click_explicit(x2, y2)

        print("[ANTI-AFK] Channel değişimi tıklandı. Yükleniyor...")
        
        # Oyunun kendine gelmesi için 5 saniye bekle
        time.sleep(5.0) 

    # Yardımcı: Kesin Sol Tık (Garanti olsun diye)
    def _left_click_explicit(self, x, y):
        if self.mouse:
            self.mouse.leftclick(0.05, x, y)
        else:
            # Donanımsal Sol Tık Simülasyonu
            extra = ctypes.c_ulong(0)
            ii_ = Input_I()
            
            # Sol Bas
            ii_.mi = MouseInput(0, 0, 0, 0x0002, 0, ctypes.pointer(extra)) 
            x_in = Input(ctypes.c_ulong(0), ii_)
            ctypes.windll.user32.SendInput(1, ctypes.pointer(x_in), ctypes.sizeof(x_in))
            
            time.sleep(0.1) # Algılama süresi
            
            # Sol Bırak
            ii_.mi = MouseInput(0, 0, 0, 0x0004, 0, ctypes.pointer(extra)) 
            x_in = Input(ctypes.c_ulong(0), ii_)
            ctypes.windll.user32.SendInput(1, ctypes.pointer(x_in), ctypes.sizeof(x_in))

    def _main_loop(self):
        validation_region = self.config.get("region_validate"); search_region = self.config.get("region_search")
        attack_start_region = self.config.get("region_attack_start"); mob_pixel_rgb = self.config.get("pixel_rgb")
        
        if not validation_region or not search_region: print("[HATA] Lütfen tüm alanları seçin!"); self.stop(); return
        
        # Mobsuzluk Sayacı Başlangıcı
        mob_search_start_time = time.time()
        cc_enabled = self.config.get("cc_enabled", False)
        cc_timeout = float(self.config.get("cc_timeout", 4.0))

        with mss.mss() as sct:
            while not self._stop_event.is_set():
                target = self._find_pixel_in_area(sct)
                
                # --- HEDEF BULUNAMADIĞINDA ---
                if not target:
                    now = time.time()
                    
                    # Channel Değişimi Kontrolü
                    if cc_enabled:
                        elapsed_no_mob = now - mob_search_start_time
                        if elapsed_no_mob > cc_timeout:
                            # Süre doldu, mob yok -> Channel Değiş
                            self._perform_channel_change()
                            
                            # Sayaçları sıfırla ki tekrar döngüye girince hemen bir daha değişmesin
                            mob_search_start_time = time.time()
                            self.last_turn_time = time.time()
                            continue

                    # Kamera Çevirme
                    if now - self.last_turn_time > self.turn_interval: 
                        self._execute_tap(SC_MIDDLE_CLICK, delay=0.05)
                        self.last_turn_time = now
                    
                    time.sleep(0.3)
                    continue 
                
                # --- HEDEF BULUNDUĞUNDA ---
                if target:
                    # Mob bulduğumuz için sayacı sıfırlıyoruz
                    mob_search_start_time = time.time()

                    tx, ty = target; self._click(tx, ty); time.sleep(0.4)
                    is_name_match = self._is_match(sct, self.img_name, validation_region) 
                    if self.config.get("check_box_icon", False): is_box_match = self._is_match(sct, self.img_box, validation_region)
                    else: is_box_match = True 
                    
                    if is_name_match and is_box_match:
                        print(f"[ANTI-AFK] Hedef Doğrulandı. {tx}, {ty}")
                        self.last_clicked_coords.append((tx, ty, time.time()))
                        is_archer_mode = (self.attack_mode == "Okçu (3-5)")
                        can_attack = True
                        if attack_start_region and mob_pixel_rgb:
                            can_attack = False
                            print("[ANTI-AFK] Mobun atak alanına girmesi bekleniyor...")
                            if is_archer_mode: self._driver_hold(SC_W)
                            else: self._tap(SC_R) 
                            
                            approach_start = time.time()
                            min_approach_duration = 2.0
                            while True:
                                elapsed = time.time() - approach_start
                                if elapsed < min_approach_duration:
                                    if is_archer_mode: self._tap(SC_R); time.sleep(0.15) 
                                    else: time.sleep(0.1) 
                                    continue 
                                
                                if elapsed > 5.0: break 
                                
                                if self._find_coords_of_pixel(sct, attack_start_region, mob_pixel_rgb):
                                    can_attack = True; print("[ANTI-AFK] Mob menzilde!"); break
                                    
                                if is_archer_mode: self._tap(SC_R); time.sleep(0.15)
                                else: time.sleep(0.1)
                                
                            if is_archer_mode: self._driver_release(SC_W)
                            if not can_attack: 
                                print("[ANTI-AFK] Mob menzile girmedi.")
                                if not is_archer_mode: self._tap(SC_S)
                        else:
                            if not is_archer_mode: self._tap(SC_R)

                        if can_attack:
                            attack_start_time = time.time(); hp_check_done = False
                            while not self._stop_event.is_set():
                                self._run_combat_class_only_attack() 
                                if self.config.get("check_hp_bar", False) and not hp_check_done:
                                    if time.time() - attack_start_time > 2.0: 
                                        if self._is_match(sct, self.img_hp, validation_region): 
                                            print("[ANTI-AFK] Mob Hasar Almıyor!"); self.blacklist_coords.append((tx, ty, time.time())); break 
                                        hp_check_done = True 
                                if not self._is_match(sct, self.img_name, validation_region): 
                                    print("[ANTI-AFK] Mob Öldü. Loot bekleniyor...")
                                    self.blacklist_coords.append((tx, ty, time.time()))
                                    if is_archer_mode: self._driver_release(SC_W)
                                    self._tap(SC_S)
                                    time.sleep(0.5) 
                                    if self.config.get("auto_drop"): self._handle_loot(sct, search_region)
                                    
                                    # Mob öldü ve işimiz bitti, sayacı tekrar sıfırla
                                    mob_search_start_time = time.time()
                                    break
                                time.sleep(0.1)
                    else:
                        print(f"[ANTI-AFK] Hatalı Seçim."); self.blacklist_coords.append((tx, ty, time.time()))
                time.sleep(0.2)

    def _handle_loot(self, sct, search_region):
        if not self.config.get("auto_drop", False): return

        # Ayarlar
        loot_wait = self.config.get("loot_open_delay", 0.6)
        loot_offset = self.config.get("loot_offset", 50)
        loot_layout = self.config.get("loot_layout", "4'lü Dikey")

        # 1. BEKLEME AŞAMASI
        print(f"[ANTI-AFK] Kutu için {loot_wait} saniye bekleniyor...")
        time.sleep(loot_wait)

        # 2. 4 NOKTAYA SAĞ TIKLAMA (SAĞ-SOL-ALT-ÜST 25px)
        mx, my = pyautogui.size()
        center_x, center_y = int(mx / 2), int(my / 2)
        
        # Koordinat farkları: (x_fark, y_fark)
        offsets = [
            (25, 0),   # 25 px Sağ
            (-25, 0),  # 25 px Sol
            (0, 25),   # 25 px Alt
            (0, -25)   # 25 px Üst
        ]

        # Her bir nokta için döngü
        for dx, dy in offsets:
            target_x = center_x + dx
            target_y = center_y + dy
            
            # 1. Fareyi Oraya Işınla
            ctypes.windll.user32.SetCursorPos(target_x, target_y)
            time.sleep(0.03) # Kısa bekleme
            
            # 2. Sağ Tıkla (Bas-Bırak)
            if self.mouse:
                self.mouse.rightclick(0.04, target_x, target_y)
            else:
                extra = ctypes.c_ulong(0)
                ii_ = Input_I()
                
                # Sağ Tuş BAS
                ii_.mi = MouseInput(0, 0, 0, 0x0008, 0, ctypes.pointer(extra)) 
                x = Input(ctypes.c_ulong(0), ii_)
                ctypes.windll.user32.SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))
                
                time.sleep(0.08) # Oyun algılasın diye çok kısa basılı tut
                
                # Sağ Tuş BIRAK (Mouse hareket etmeden önce bırakılır, ekran kaymaz)
                ii_.mi = MouseInput(0, 0, 0, 0x0010, 0, ctypes.pointer(extra)) 
                x = Input(ctypes.c_ulong(0), ii_)
                ctypes.windll.user32.SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))
            
            # Diğer noktaya geçmeden önce çok kısa bekle
            time.sleep(0.05)

        # Tıklamalar bitti, pencerenin açılması için kısa bekleme
        time.sleep(0.3)

        # 3. LOOT PENCERESİNİ TARAMA VE TOPLAMA (Standart)
        if self.img_loot_window is not None:
            win_found = False
            wait_win_start = time.time()
            while time.time() - wait_win_start < 2.0:
                mon = {"left": int(search_region[0]), "top": int(search_region[1]), "width": int(search_region[2]), "height": int(search_region[3])}
                scr = np.array(sct.grab(mon))
                res = cv2.matchTemplate(scr[:,:,:3], self.img_loot_window, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(res)
                
                if max_val > 0.70:
                    win_x = search_region[0] + max_loc[0]; win_y = search_region[1] + max_loc[1]
                    print("[ANTI-AFK] Loot Penceresi Algılandı. Toplanıyor.")
                    
                    c_x = win_x + (self.img_loot_window.shape[1] // 2)
                    c_y = win_y + (self.img_loot_window.shape[0] // 2)
                    
                    if loot_layout == "4'lü Dikey":
                        self._click(c_x, c_y); time.sleep(0.15)
                        for i in range(1, 4):
                            self._click(c_x, c_y + (i * 50))
                            time.sleep(0.15)
                    else: 
                        for row in range(3):
                            y = c_y + (row * loot_offset)
                            self._click(c_x - 22, y); time.sleep(0.1)
                            self._click(c_x + 22, y); time.sleep(0.1)
                    
                    self._execute_tap(SC_ESC, delay=0.05) 
                    win_found = True
                    break
                time.sleep(0.1)
                
            if not win_found: print("[ANTI-AFK] Loot Penceresi açılmadı.")
        else: print("[UYARI] Loot Penceresi Resmi ayarlı değil.")

    def _run_combat_class_only_attack(self):
        active_macro = self.sub_macros.get(self.attack_mode)
        if not active_macro: return
        if self.attack_mode == "Warrior (Seri)": active_macro._do_combo_once()
        elif self.attack_mode == "Asas (VS)": active_macro.run_sequence()
        elif self.attack_mode == "Okçu (3-5)": active_macro._do_combo_once()
        elif self.attack_mode == "Priest (BP)": active_macro.do_attack()
        elif self.attack_mode == "Self (Özel)": self._execute_tap(DIGIT_SCANCODES[1], 0.05)

# =========================================================
# 2. GUI WIDGET & SETTINGS
# =========================================================
class AntiAfkWidget(QFrame):
    update_signal = pyqtSignal()
    def __init__(self, parent=None, macro_instance=None, config=None):
        super().__init__(parent)
        self.macro = macro_instance or AntiAfkEngine(); self.config = self.macro._load_config() or {}
        self.macro.update_config(self.config); self.listen_active = False; self.setup_ui()
        self.update_signal.connect(self._safe_update)

    def setup_ui(self):
        self.setFrameShape(QFrame.Box); self.setFixedWidth(260)
        self.setStyleSheet("QFrame { background-color: #101010; border: 1px solid #444; border-radius: 4px; }")
        v = QVBoxLayout(self); v.setContentsMargins(8,8,8,8); v.setSpacing(5)
        h = QHBoxLayout()

        # --- İCON EKLEME KISMI (ANTI-AFK) ---
        icon = QLabel(); icon.setFixedSize(30, 30); icon.setStyleSheet("border:none;")
        icon_path = os.path.join("icons", "gui", "antiafk.png")
        if os.path.exists(icon_path):
            pix = QPixmap(icon_path)
            icon.setPixmap(pix.scaled(30, 30, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        # ------------------------------------

        h.addWidget(icon)
        h.addStretch()
        
        title = QLabel("ANTI-AFK")
        title.setObjectName("MinorHeaderLabel")
        h.addWidget(title)
        
        v.addLayout(h)
        self.btn_listen = QPushButton("MAKROYU BAŞLAT"); self.btn_listen.setObjectName("ThreeFiveListenButton")
        self.btn_listen.clicked.connect(self.toggle_listen); v.addWidget(self.btn_listen)
        self.lbl_st = QLabel("DURUM: PASİF"); self.lbl_st.setObjectName("MinorStatusLabel"); v.addWidget(self.lbl_st)
        row = QHBoxLayout(); row.addWidget(QLabel("TUŞ:")); self.lbl_hk = QLabel(self.config.get("hotkey", "INSERT")); self.lbl_hk.setObjectName("HotkeyLabel"); row.addWidget(self.lbl_hk)
        btn_set = QPushButton("⚙ AYARLAR"); btn_set.setObjectName("MinorSettingsButton"); btn_set.clicked.connect(self.open_settings); row.addWidget(btn_set); v.addLayout(row)

    def open_settings(self):
        dlg = AntiAfkSettingsDialog(self, self.config, self.macro)
        if dlg.exec_() == QDialog.Accepted:
            self.config = dlg.result_config; self.macro.update_config(self.config); self._save_config_to_file(); self.lbl_hk.setText(self.config["hotkey"])
        dlg.deleteLater()

    def _save_config_to_file(self):
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            print(f"AYAR KAYIT HATASI: {e}")

    def toggle_listen(self):
        if not keyboard: return
        if not self.listen_active:
            try:
                hk = self.config.get("hotkey", "INSERT").lower()
                self._hook = keyboard.on_press_key(hk, lambda e: self.macro.toggle())
                self.listen_active = True
            except: self.listen_active = False
        else:
            if hasattr(self, '_hook'): 
                try: keyboard.unhook(self._hook)
                except: pass
                self._hook = None
            self.listen_active = False; self.macro.stop()
        self._safe_update()

    def _safe_update(self):
        if not self.listen_active: self.lbl_st.setText("DURUM: PASİF"); self.lbl_st.setStyleSheet("color:#ff5555; font-weight:bold;")
        else:
            active = self.macro.is_running
            self.lbl_st.setText("DURUM: ÇALIŞIYOR" if active else "DURUM: HAZIR"); self.lbl_st.setStyleSheet(f"color:{'#00ff4c' if active else '#ffff55'}; font-weight:bold;")

from PyQt5.QtCore import QSize
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QScrollArea, QWidget

class AntiAfkSettingsDialog(QDialog):
    BASE_W, BASE_H = 550, 850

    def __init__(self, parent, config, macro):
        super().__init__(parent)

        self.setWindowTitle("ANTI-AFK AYARLARI")

        # ❌ Sabit boyut yok -> kullanıcı küçültüp büyütebilsin
        self.setMinimumSize(420, 620)
        self.resize(520, 740)
        self.setSizeGripEnabled(True)

        self.config = config.copy()
        self.macro = macro
        self.result_config = None

        # ölçek state
        self._base_size = QSize(self.BASE_W, self.BASE_H)
        self._base_font_pt = float(self.font().pointSizeF() or 10.0)
        self._last_scale = 1.0

        # === Dış layout: üstte scroll, altta OK/Cancel sabit ===
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(8)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)

        content = QWidget()
        layout = QVBoxLayout(content)   # <-- senin eski layout = QVBoxLayout(self) yerine
        layout.setSpacing(10)

        self._scroll.setWidget(content)
        outer.addWidget(self._scroll)

        # --- 1. Görsel Tanımlamalar ---
        grp_pick = QGroupBox("Görsel Tanımlamalar")
        gl = QGridLayout(grp_pick)

        self.lbl_pix = QLabel(f"Pixel: {self.config.get('pixel_rgb', 'Seçilmedi')}")
        btn_pix = QPushButton("1. Mob Pixel Seç")
        btn_pix.clicked.connect(self.pick_pixel)
        gl.addWidget(self.lbl_pix, 0, 0)
        gl.addWidget(btn_pix, 0, 1)

        btn_name = QPushButton("2. Üst İsim Yakala")
        btn_name.clicked.connect(lambda: self.cap_img("path_name", "İSİM ALANINI ÇİZ"))
        gl.addWidget(QLabel("İsim Onayı:"), 1, 0)
        gl.addWidget(btn_name, 1, 1)

        self.chk_box_icon = QCheckBox("Kutu Kontrolü Aktif")
        self.chk_box_icon.setChecked(self.config.get("check_box_icon", False))
        gl.addWidget(self.chk_box_icon, 2, 0)

        btn_box = QPushButton("3. Üst Kutu Yakala")
        btn_box.clicked.connect(lambda: self.cap_img("path_box", "KUTU ALANINI ÇİZ"))
        gl.addWidget(btn_box, 2, 1)

        layout.addWidget(grp_pick)

        # --- 2. HP Kontrolü ---
        grp_hp = QGroupBox("Akıllı HP Kontrolü (Smart Damage)")
        ghp = QGridLayout(grp_hp)

        self.chk_hp_check = QCheckBox("HP Kontrolü Aktif")
        self.chk_hp_check.setChecked(self.config.get("check_hp_bar", False))
        ghp.addWidget(self.chk_hp_check, 0, 0)

        btn_hp_img = QPushButton("6. HP Barını Yakala (Dolu Hali)")
        btn_hp_img.clicked.connect(lambda: self.cap_img("path_hp", "DOLU HP BARINI KIRP"))
        ghp.addWidget(btn_hp_img, 0, 1)

        layout.addWidget(grp_hp)

        # --- 3. Alan Tanımlamaları ---
        grp_area = QGroupBox("Alan Tanımlamaları")
        gal = QGridLayout(grp_area)

        btn_search = QPushButton("Mob Arama Alanı Çiz")
        btn_search.clicked.connect(lambda: self.sel_area("region_search", "ARAMA ALANI ÇİZ"))
        gal.addWidget(btn_search, 0, 0)

        btn_attack_start = QPushButton("ATAK BAŞLAMA ALANI ÇİZ")
        btn_attack_start.clicked.connect(lambda: self.sel_area("region_attack_start", "ATAK BAŞLANGIÇ ALANINI ÇİZ"))
        gal.addWidget(btn_attack_start, 1, 0)

        btn_validate = QPushButton("4. Doğrulama Alanını Çiz")
        btn_validate.clicked.connect(lambda: self.sel_area("region_validate", "ONAY ALANINI ÇİZ (Can Barı/İsim)"))
        gal.addWidget(btn_validate, 2, 0, 1, 2)

        layout.addWidget(grp_area)

        # --- 4. Atak Modu ve Loot ---
        grp_comb = QGroupBox("Atak Modu ve Loot")
        cl = QGridLayout(grp_comb)

        self.cmb_mode = QComboBox()
        self.cmb_mode.addItems(["Warrior (Seri)", "Asas (VS)", "Okçu (3-5)", "Priest (BP)", "Self (Özel)"])
        self.cmb_mode.setCurrentText(self.config.get("mode", "Warrior (Seri)"))
        cl.addWidget(QLabel("Atak Modu:"), 0, 0)
        cl.addWidget(self.cmb_mode, 0, 1)

        # ✅ local değil -> ölçeklenebilsin
        self.btn_mode_cfg = QPushButton("⚙")
        self.btn_mode_cfg.setFixedSize(30, 25)  # ilk boyut, resize ile güncellenecek
        self.btn_mode_cfg.clicked.connect(self.open_mode_settings)
        cl.addWidget(self.btn_mode_cfg, 0, 2)

        self.chk_drop = QCheckBox("Kutu Loot Aktif")
        self.chk_drop.setChecked(self.config.get("auto_drop", False))
        cl.addWidget(self.chk_drop, 1, 0)

        btn_loot_win = QPushButton("Loot (Coin) Resmi Seç")
        btn_loot_win.clicked.connect(lambda: self.cap_img("path_loot_window", "COIN RESMİNİ KIRP"))
        cl.addWidget(btn_loot_win, 2, 1)

        cl.addWidget(QLabel("360° Çevirme Aralığı (sn):"), 3, 0)
        self.spin_turn = QDoubleSpinBox()
        self.spin_turn.setRange(0.5, 60.0)
        self.spin_turn.setValue(self.config.get("turn_interval", 1.5))
        cl.addWidget(self.spin_turn, 3, 1)

        cl.addWidget(QLabel("Kutu Açılma Gecikmesi (sn):"), 4, 0)
        self.spin_loot_delay = QDoubleSpinBox()
        self.spin_loot_delay.setRange(0.1, 5.0)
        self.spin_loot_delay.setValue(self.config.get("loot_open_delay", 0.6))
        cl.addWidget(self.spin_loot_delay, 4, 1)

        cl.addWidget(QLabel("Loot Düzeni:"), 5, 0)
        self.cmb_loot_layout = QComboBox()
        self.cmb_loot_layout.addItems(["4'lü Dikey", "6'lı (2x3)"])
        self.cmb_loot_layout.setCurrentText(self.config.get("loot_layout", "4'lü Dikey"))
        cl.addWidget(self.cmb_loot_layout, 5, 1)

        cl.addWidget(QLabel("Slot Aralığı (px):"), 6, 0)
        self.spin_loot_offset = QSpinBox()
        self.spin_loot_offset.setRange(10, 100)
        self.spin_loot_offset.setValue(self.config.get("loot_offset", 50))
        cl.addWidget(self.spin_loot_offset, 6, 1)

        layout.addWidget(grp_comb)

        # --- 5. OTO CHANNEL DEĞİŞİMİ ---
        grp_cc = QGroupBox("Oto Channel Değişimi")
        gcc = QGridLayout(grp_cc)

        self.chk_cc = QCheckBox("Aktif Et")
        self.chk_cc.setChecked(self.config.get("cc_enabled", False))
        gcc.addWidget(self.chk_cc, 0, 0)

        gcc.addWidget(QLabel("Mobsuz Süre (sn):"), 0, 1)
        self.spin_cc_time = QSpinBox()
        self.spin_cc_time.setRange(3, 600)
        self.spin_cc_time.setValue(self.config.get("cc_timeout", 4))
        gcc.addWidget(self.spin_cc_time, 0, 2)

        btn_cc1 = QPushButton("1. Kanal Butonu Çiz")
        btn_cc1.clicked.connect(lambda: self.sel_area("region_cc_1", "SAĞ ÜSTTEKİ CH BUTONUNU ÇERÇEVELE"))
        gcc.addWidget(btn_cc1, 1, 0, 1, 3)

        btn_cc2 = QPushButton("2. Hedef Kanal Çiz")
        btn_cc2.clicked.connect(lambda: self.sel_area("region_cc_2", "GİDİLECEK KANALI (ÖRN: CH2) ÇERÇEVELE"))
        gcc.addWidget(btn_cc2, 2, 0, 1, 3)

        layout.addWidget(grp_cc)

        # --- Başlatma Tuşu ---
        h_lay = QHBoxLayout()
        h_lay.addWidget(QLabel("Başlatma Tuşu:"))

        self.txt_hk = QLineEdit(self.config.get("hotkey", "INSERT"))
        self.txt_hk.setReadOnly(True)
        h_lay.addWidget(self.txt_hk)

        self.btn_capture_hk = QPushButton("TUŞ SEÇ")
        self.btn_capture_hk.clicked.connect(self.start_hotkey_capture)
        h_lay.addWidget(self.btn_capture_hk)

        layout.addLayout(h_lay)

        # OK/Cancel scroll dışında, altta sabit
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.on_accept)
        btns.rejected.connect(self.reject)
        outer.addWidget(btns)

        # ilk stil + ölçek uygula
        self._apply_scale(1.0)

    # ---- Ölçekleme: pencere küçülünce font + butonlar küçülsün ----
    def showEvent(self, e):
        super().showEvent(e)
        self._update_scale()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._update_scale()

    def _update_scale(self):
        s = min(self.width() / self._base_size.width(), self.height() / self._base_size.height())
        s = max(0.75, min(1.10, s))  # çok küçülüp okunmaz olmasın
        if abs(s - self._last_scale) < 0.02:
            return
        self._last_scale = s
        self._apply_scale(s)

    def _apply_scale(self, s: float):
        # font ölçeği
        f = QFont(self.font())
        f.setPointSizeF(max(8.0, self._base_font_pt * s))
        self.setFont(f)

        pad = max(3, int(6 * s))
        rad = max(3, int(4 * s))
        btn_h = max(24, int(30 * s))
        edit_h = max(22, int(26 * s))

        self.setStyleSheet(f"""
            QDialog {{ background-color: #121212; }}
            QLabel {{ color: #ccc; }}
            QGroupBox {{ color: #ccc; }}

            QPushButton {{
                background: #252525;
                color: white;
                border: 1px solid #444;
                padding: {pad}px;
                border-radius: {rad}px;
                min-height: {btn_h}px;
            }}
            QPushButton:hover {{ border-color: #00e676; }}

            QLineEdit {{
                background: #000;
                color: #00ff4c;
                border: 1px solid #333;
                padding: {max(2, int(4*s))}px;
                min-height: {edit_h}px;
            }}
            QComboBox, QSpinBox, QDoubleSpinBox {{
                background: #000;
                color: #ddd;
                border: 1px solid #333;
                padding: {max(2, int(4*s))}px;
                min-height: {edit_h}px;
            }}
        """)

        # ⚙ butonu ölçekle
        if hasattr(self, "btn_mode_cfg"):
            self.btn_mode_cfg.setFixedSize(max(26, int(30*s)), max(22, int(25*s)))

    # ---- Senin mevcut fonksiyonların (değişmedim) ----
    def pick_pixel(self):
        self.setWindowOpacity(0); QApplication.processEvents(); time.sleep(0.2)
        d = FullScreenSelector("pixel", "LÜTFEN MOB ÜZERİNDEN PİKSEL RENGİ SEÇİN")
        if d.exec_() == QDialog.Accepted:
            self.config["pixel_rgb"] = d.result
            self.lbl_pix.setText(f"Pixel: {self.config['pixel_rgb']}")
        d.deleteLater(); self.setWindowOpacity(1); self.activateWindow()

    def cap_img(self, key, title):
        self.setWindowOpacity(0); QApplication.processEvents(); time.sleep(0.2)
        d = FullScreenSelector("area", title)
        if d.exec_() == QDialog.Accepted and d.result:
            x, y, w, h = d.result
            with mss.mss() as sct:
                img = np.array(sct.grab({"left": int(x), "top": int(y), "width": int(w), "height": int(h)}))
                if not os.path.exists("farm_data"): os.makedirs("farm_data")
                path = f"farm_data/afk_{key}.png"; cv2.imwrite(path, img); self.config[key] = path
        d.deleteLater(); self.setWindowOpacity(1); self.activateWindow()

    def sel_area(self, key, title):
        self.setWindowOpacity(0); QApplication.processEvents(); time.sleep(0.2)
        d = FullScreenSelector("area", title)
        if d.exec_() == QDialog.Accepted: self.config[key] = d.result
        d.deleteLater(); self.setWindowOpacity(1); self.activateWindow()

    def open_mode_settings(self):
        mode = self.cmb_mode.currentText()
        sub_key = f"subconfig_{mode}"
        current_sub_cfg = self.config.get(sub_key, {})
        dlg = None
        if mode == "Warrior (Seri)": dlg = WarriorSkillSettingsDialog(self, current_sub_cfg)
        elif mode == "Asas (VS)": dlg = AsasSettingsDialog(self, current_sub_cfg)
        elif mode == "Okçu (3-5)": dlg = ThreeFiveSettingsDialog(self, current_sub_cfg)
        elif mode == "Priest (BP)": dlg = PriestSettingsDialog(self, current_sub_cfg)
        elif mode == "Self (Özel)":
            dlg = SelfSettingsDialog(self, current_sub_cfg, None)

        if dlg and dlg.exec_() == QDialog.Accepted:
            new_cfg = getattr(dlg, "result_config", getattr(dlg, "config", {}))
            self.config[sub_key] = new_cfg

    def start_hotkey_capture(self):
        self.capture_hotkey = True
        self.txt_hk.setText("BİR TUŞA BASIN...")
        self.btn_capture_hk.setText("BEKLENİYOR...")
        self.grabKeyboard()

    def keyPressEvent(self, e):
        if hasattr(self, 'capture_hotkey') and self.capture_hotkey:
            key_code = e.key()
            special_keys = {
                Qt.Key_Insert: "INSERT",
                Qt.Key_Delete: "DELETE",
                Qt.Key_Home: "HOME",
                Qt.Key_End: "END",
                Qt.Key_PageUp: "PAGE UP",
                Qt.Key_PageDown: "PAGE DOWN",
                Qt.Key_Pause: "PAUSE",
                Qt.Key_F1: "F1", Qt.Key_F2: "F2", Qt.Key_F3: "F3", Qt.Key_F4: "F4",
                Qt.Key_F5: "F5", Qt.Key_F6: "F6", Qt.Key_F7: "F7", Qt.Key_F8: "F8",
                Qt.Key_F9: "F9", Qt.Key_F10: "F10", Qt.Key_F11: "F11", Qt.Key_F12: "F12",
                Qt.Key_Control: "CTRL",
                Qt.Key_Shift: "SHIFT",
                Qt.Key_Alt: "ALT",
                Qt.Key_CapsLock: "CAPS LOCK",
                Qt.Key_Tab: "TAB"
            }

            if key_code in special_keys:
                key_text = special_keys[key_code]
            else:
                key_text = e.text().upper()

            if key_text:
                self.txt_hk.setText(key_text)
                self.capture_hotkey = False
                self.btn_capture_hk.setText("TUŞ SEÇ")
                self.releaseKeyboard()
            return

        super().keyPressEvent(e)

    def on_accept(self):
        self.config.update({
            "hotkey": self.txt_hk.text().upper(),
            "mode": self.cmb_mode.currentText(),
            "auto_drop": self.chk_drop.isChecked(),
            "turn_interval": self.spin_turn.value(),
            "check_box_icon": self.chk_box_icon.isChecked(),
            "check_hp_bar": self.chk_hp_check.isChecked(),
            "loot_open_delay": self.spin_loot_delay.value(),
            "loot_layout": self.cmb_loot_layout.currentText(),
            "loot_offset": self.spin_loot_offset.value(),
            "cc_enabled": self.chk_cc.isChecked(),
            "cc_timeout": self.spin_cc_time.value(),
        })
        self.result_config = self.config
        self.accept()
