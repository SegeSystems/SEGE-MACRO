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
import os
import cv2
import numpy as np
import mss
import json
import traceback



# PyQt5
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFrame, QComboBox, QMessageBox, QDialog, QGridLayout, QGroupBox, QLineEdit,
    QDoubleSpinBox, QCheckBox, QScrollArea, QSpinBox, QFormLayout, QSizePolicy,
    QDialogButtonBox, QApplication
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QSize
from PyQt5.QtGui import QPainter, QPen, QColor, QKeySequence, QPixmap, QFont, QBrush

# Klavye
try:
    import keyboard
except ImportError:
    keyboard = None

# Surucu
try:
    from clicksend import KeyboardDriver as _ClicksendKeyboardDriver
except ImportError:
    _ClicksendKeyboardDriver = None

# --- SABITLER ---
SC_Z = 0x2C
SC_R = 0x13
SC_W = 0x11
SC_S = 0x1F 

DIGIT_SCANCODES = {
    1: 0x02, 2: 0x03, 3: 0x04, 4: 0x05, 5: 0x06,
    6: 0x07, 7: 0x08, 8: 0x09, 9: 0x0A, 0: 0x0B,
}
F_SCANCODES = {
    1: 0x3B, 2: 0x3C, 3: 0x3D, 4: 0x3E,
    5: 0x3F, 6: 0x40, 7: 0x41, 8: 0x42
}
FKEY_SCANCODES_STR = {
    "F1": 0x3B, "F2": 0x3C, "F3": 0x3D, "F4": 0x3E,
    "F5": 0x3F, "F6": 0x40, "F7": 0x41, "F8": 0x42
}

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller temp klasoru
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# --- GLOBAL SURUCU YARDIMCILARI ---
def _ensure_driver():
    if _ClicksendKeyboardDriver:
        if not hasattr(_ensure_driver, "kb"):
            _ensure_driver.kb = _ClicksendKeyboardDriver()
        return _ensure_driver.kb
    return None

def _tap(sc, duration=0.03):
    kb = _ensure_driver()
    if kb and sc: kb.tusbas(sc, duration)

def _down(sc):
    kb = _ensure_driver()
    if kb and sc: kb.tusbasilitut(sc)

def _up(sc):
    kb = _ensure_driver()
    if kb and sc: kb.tusbirak(sc)

# ==============================================================================
# EKRAN SECIM ARACI (FullScreenSelector) - ANTIAFK TARZI
# ==============================================================================
from PyQt5.QtCore import QRect

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

# Eski AreaSelector uyumlulugu icin alias
AreaSelector = FullScreenSelector

# ==============================================================================
# GOMULU MAKROLAR (MANTIK AYNI KALDI)
# ==============================================================================
class WarriorSkillMacro:
    def __init__(self):
        self.order = "2rr"; self.s_delay = 0.05; self.r_delay = 0.02; self.skill_key = 2; self.skill_bar = "FYOK"; self.z_enabled = False; self.z_delay = 0.1; self._bar_applied = False
    def update_config(self, cfg):
        self.order = cfg.get("order", "2rr"); self.s_delay = cfg.get("key_2_duration", 0.05); self.r_delay = cfg.get("key_r_duration", 0.02); self.skill_key = cfg.get("skill_key", 2); self.skill_bar = cfg.get("skill_bar", "FYOK"); self.z_enabled = cfg.get("z_enabled", False); self.z_delay = cfg.get("z_key_duration", 0.1)
    def _do_combo_once(self):
        if self.z_enabled: _tap(SC_Z, 0.02); time.sleep(self.z_delay)
        if not self._bar_applied:
            if self.skill_bar != "FYOK":
                sc = FKEY_SCANCODES_STR.get(self.skill_bar);
                if sc: _tap(sc, 0.02)
            self._bar_applied = True
        sc_skill = DIGIT_SCANCODES.get(int(self.skill_key));
        if not sc_skill: return
        if self.order == '2rr':
            _tap(sc_skill, self.s_delay); _tap(SC_R, self.r_delay); _tap(SC_R, self.r_delay)
        elif self.order == 'rr2':
            _tap(SC_R, self.r_delay); _tap(SC_R, self.r_delay); _tap(sc_skill, self.s_delay)
        elif self.order == 'wr2':
            _tap(SC_W, 0.05); _tap(SC_R, self.r_delay); _tap(sc_skill, self.s_delay)

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

class AsasHybridMacro:
    def __init__(self):
        self.active_digits = [2, 3, 4, 5, 6]; self.repeat_r = 5; self.time_skill_press = 0.010; self.time_r_press = 0.010; self.use_auto_z = False
    def update_config(self, cfg):
        self.active_digits = cfg.get("digits", [2, 3, 4, 5, 6]); self.repeat_r = cfg.get("repeat_r", 5); self.use_auto_z = cfg.get("use_z", False); self.time_skill_press = cfg.get("time_skill_press", 0.010); self.time_r_press = cfg.get("time_r_press", 0.010)
    def run_sequence(self):
        for d in self.active_digits:
            sc = DIGIT_SCANCODES.get(d);
            if sc: _tap(sc, self.time_skill_press); time.sleep(0.01)
        for _ in range(self.repeat_r):
             _tap(SC_R, self.time_r_press); time.sleep(0.01)
        if self.use_auto_z: _tap(SC_Z, 0.01)

class AsasSettingsDialog(QDialog):
    def __init__(self, parent, config):
        super().__init__(parent); self.setWindowTitle("ASAS PRO AYARLARI"); self.result_config = config or {}; lay = QVBoxLayout(self)
        grp_digits = QGroupBox("Aktif Skill Slotlari"); g = QGridLayout(grp_digits); self.chk_digits = {}; digits_cfg = self.result_config.get("digits", [2, 3, 4, 5, 6]); row = 0; col = 0
        for d in range(10):
            cb = QCheckBox(str(d)); cb.setChecked(d in digits_cfg); self.chk_digits[d] = cb; g.addWidget(cb,row,col); col += 1
            if col == 5: row += 1; col = 0
        lay.addWidget(grp_digits)
        grp_time = QGroupBox("Zamanlama (Saniye)"); gt = QGridLayout(grp_time)
        gt.addWidget(QLabel("Skill Basili:"), 0, 0); self.s_press = QDoubleSpinBox(); self.s_press.setRange(0,1); self.s_press.setSingleStep(0.001); self.s_press.setDecimals(3); self.s_press.setValue(self.result_config.get("time_skill_press", 0.010)); gt.addWidget(self.s_press, 0, 1)
        gt.addWidget(QLabel("R Basili:"), 1, 0); self.r_press = QDoubleSpinBox(); self.r_press.setRange(0,1); self.r_press.setSingleStep(0.001); self.r_press.setDecimals(3); self.r_press.setValue(self.result_config.get("time_r_press", 0.010)); gt.addWidget(self.r_press, 1, 1)
        lay.addWidget(grp_time)
        grp_r = QGroupBox("Diger"); hr = QFormLayout(grp_r)
        self.spin_r = QSpinBox(); self.spin_r.setRange(1, 500); self.spin_r.setValue(self.result_config.get("repeat_r", 5)); hr.addRow("R Tekrar Sayisi:", self.spin_r)
        self.chk_z = QCheckBox("Combo Arasi Z Bas"); self.chk_z.setChecked(self.result_config.get("use_z", False)); hr.addRow(self.chk_z); lay.addWidget(grp_r)
        btn = QPushButton("KAYDET"); btn.clicked.connect(self.accept); lay.addWidget(btn)
    def accept(self):
        digits = [d for d, btn in self.chk_digits.items() if btn.isChecked()]; self.result_config.update({"digits": digits, "repeat_r": self.spin_r.value(), "time_skill_press": self.s_press.value(), "time_r_press": self.r_press.value(), "use_z": self.chk_z.isChecked()}); super().accept()

class ThreeFiveMacro:
    def __init__(self):
        self.f_bar = 3; self.key5 = 2; self.key3 = 3; self.combo_delay = 0.46; self.w_delay = 0.05; self.use_f = True; self.use_z = False; self.z_delay = 0.1
    def set_params(self, f_bar, k5, k3, cd, wd, mode, use_f, use_z, zd):
        self.f_bar = f_bar; self.key5 = k5; self.key3 = k3; self.combo_delay = cd; self.w_delay = wd; self.use_f = use_f; self.use_z = use_z; self.z_delay = zd
    def _do_combo_once(self):
        if self.use_f:
            sc_f = F_SCANCODES.get(self.f_bar);
            if sc_f: _tap(sc_f, 0.01)
        if self.use_z: _tap(SC_Z, 0.02); time.sleep(self.z_delay)
        k5 = DIGIT_SCANCODES.get(self.key5); k3 = DIGIT_SCANCODES.get(self.key3)
        if k5: _tap(k5, self.combo_delay); _tap(SC_W, self.w_delay)
        if k3: _tap(k3, self.combo_delay); _tap(SC_W, self.w_delay)

class ThreeFiveSettingsDialog(QDialog):
    def __init__(self, parent=None, config=None):
        super().__init__(parent); self.setWindowTitle("3-5 AYARLARI"); self.result_config = config or {}; l = QGridLayout(self)
        self.chk_f = QCheckBox("F Bar Kullan"); self.chk_f.setChecked(self.result_config.get("use_f_key", True)); l.addWidget(self.chk_f, 0, 0)
        self.cmb_f = QComboBox(); self.cmb_f.addItems([f"F{i}" for i in range(1,9)]); self.cmb_f.setCurrentIndex(self.result_config.get("f_bar", 3)-1); l.addWidget(self.cmb_f, 0, 1)
        l.addWidget(QLabel("5'li OK:"), 1, 0); self.c5 = QComboBox(); self.c5.addItems([str(i) for i in range(10)]); self.c5.setCurrentText(str(self.result_config.get("key5", 2))); l.addWidget(self.c5, 1, 1)
        l.addWidget(QLabel("3'lu OK:"), 2, 0); self.c3 = QComboBox(); self.c3.addItems([str(i) for i in range(10)]); self.c3.setCurrentText(str(self.result_config.get("key3", 3))); l.addWidget(self.c3, 2, 1)
        l.addWidget(QLabel("Skill Gecikme:"), 3, 0); self.sp_c = QDoubleSpinBox(); self.sp_c.setRange(0,2); self.sp_c.setSingleStep(0.01); self.sp_c.setValue(self.result_config.get("combo_delay", 0.46)); l.addWidget(self.sp_c, 3, 1)
        l.addWidget(QLabel("W Gecikme:"), 4, 0); self.sp_w = QDoubleSpinBox(); self.sp_w.setRange(0,1); self.sp_w.setSingleStep(0.01); self.sp_w.setValue(self.result_config.get("w_delay", 0.05)); l.addWidget(self.sp_w, 4, 1)
        self.chk_z = QCheckBox("Oto Z"); self.chk_z.setChecked(self.result_config.get("use_z", False)); l.addWidget(self.chk_z, 5, 0)
        btn = QPushButton("KAYDET"); btn.clicked.connect(self.accept); l.addWidget(btn, 6, 0, 1, 2)
    def accept(self):
        self.result_config.update({"use_f_key": self.chk_f.isChecked(), "f_bar": self.cmb_f.currentIndex() + 1, "key5": int(self.c5.currentText()), "key3": int(self.c3.currentText()), "combo_delay": self.sp_c.value(), "w_delay": self.sp_w.value(), "use_z": self.chk_z.isChecked()}); super().accept()

class SelfMacro:
    def __init__(self):
        self.entries = []
    def update_config(self, cfg):
        self.entries = []
        KEY_MAP = {"1":0x02, "2":0x03, "3":0x04, "4":0x05, "5":0x06, "6":0x07, "7":0x08, "8":0x09, "9":0x0A, "0":0x0B, "Z":0x2C, "R":0x13}
        for item in cfg.get("entries", []):
            if not item.get("enabled"): continue
            sc = KEY_MAP.get(item.get("key"), None);
            if sc: self.entries.append({"scancode": sc, "delay": float(item.get("delay", 0.1))})

class PriestAttackMacro:
    """Priest BP Atak Makrosu - Skill + R + R, opsiyonel kitap & kol"""
    def __init__(self):
        self.skill_key = 2
        self.skill_delay = 0.05
        self.r_delay = 0.02
        self.z_enabled = False
        self.z_delay = 0.05
        self.kitap_enabled = False
        self.kitap_key = 8
        self.kitap_delay = 3.0
        self.kol_enabled = False
        self.kol_key = 9
        self.kol_delay = 3.0
        self._last_kitap_time = 0.0
        self._last_kol_time = 0.0

    def update_config(self, cfg):
        self.skill_key = int(cfg.get("skill_key", 2))
        self.skill_delay = float(cfg.get("skill_delay", 0.05))
        self.r_delay = float(cfg.get("r_delay", 0.02))
        self.z_enabled = bool(cfg.get("z_enabled", False))
        self.z_delay = float(cfg.get("z_delay", 0.05))
        self.kitap_enabled = bool(cfg.get("kitap_enabled", False))
        self.kitap_key = int(cfg.get("kitap_key", 8))
        self.kitap_delay = float(cfg.get("kitap_delay", 3.0))
        self.kol_enabled = bool(cfg.get("kol_enabled", False))
        self.kol_key = int(cfg.get("kol_key", 9))
        self.kol_delay = float(cfg.get("kol_delay", 3.0))

    def do_attack(self):
        """Tek bir atak dongusu - FarmMacro tarafindan cagirilir"""
        now = time.time()
        # Kitap kontrolu
        if self.kitap_enabled and now - self._last_kitap_time >= self.kitap_delay:
            sc = DIGIT_SCANCODES.get(self.kitap_key)
            if sc: _tap(sc, 0.05)
            self._last_kitap_time = now
            time.sleep(0.15)
        # Kol kontrolu
        if self.kol_enabled and now - self._last_kol_time >= self.kol_delay:
            sc = DIGIT_SCANCODES.get(self.kol_key)
            if sc: _tap(sc, 0.05)
            self._last_kol_time = now
            time.sleep(0.15)
        # Ana atak combo
        if self.z_enabled:
            _tap(SC_Z, 0.01)
            time.sleep(self.z_delay)
        sc_skill = DIGIT_SCANCODES.get(self.skill_key)
        if sc_skill: _tap(sc_skill, self.skill_delay)
        _tap(SC_R, self.r_delay)
        _tap(SC_R, self.r_delay)

class PriestAttackSettingsDialog(QDialog):
    def __init__(self, parent=None, config=None):
        super().__init__(parent)
        self.setWindowTitle("PRIEST BP ATAK AYARLARI")
        self.result_config = config or {}
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

        gl.addWidget(QLabel("SKILL GECIKME:"), 1, 0)
        self.spin_skill_delay = QDoubleSpinBox()
        self.spin_skill_delay.setRange(0.01, 1.0)
        self.spin_skill_delay.setSingleStep(0.01)
        self.spin_skill_delay.setValue(self.result_config.get("skill_delay", 0.05))
        gl.addWidget(self.spin_skill_delay, 1, 1)

        gl.addWidget(QLabel("R GECIKME:"), 2, 0)
        self.spin_r_delay = QDoubleSpinBox()
        self.spin_r_delay.setRange(0.01, 1.0)
        self.spin_r_delay.setSingleStep(0.01)
        self.spin_r_delay.setValue(self.result_config.get("r_delay", 0.02))
        gl.addWidget(self.spin_r_delay, 2, 1)

        self.chk_z = QCheckBox("OTO Z BAS")
        self.chk_z.setChecked(self.result_config.get("z_enabled", False))
        gl.addWidget(self.chk_z, 3, 0, 1, 2)

        layout.addWidget(grp_genel)

        # Kitap Grubu
        grp_kitap = QGroupBox("KITAP")
        kl = QGridLayout(grp_kitap)

        self.chk_kitap = QCheckBox("KITAP AKTIF")
        self.chk_kitap.setChecked(self.result_config.get("kitap_enabled", False))
        kl.addWidget(self.chk_kitap, 0, 0, 1, 2)

        kl.addWidget(QLabel("KITAP TUSU:"), 1, 0)
        self.cmb_kitap_key = QComboBox()
        self.cmb_kitap_key.addItems([str(i) for i in range(10)])
        self.cmb_kitap_key.setCurrentText(str(self.result_config.get("kitap_key", 8)))
        kl.addWidget(self.cmb_kitap_key, 1, 1)

        kl.addWidget(QLabel("KITAP SURESI (sn):"), 2, 0)
        self.spin_kitap_time = QDoubleSpinBox()
        self.spin_kitap_time.setRange(1.0, 60.0)
        self.spin_kitap_time.setValue(self.result_config.get("kitap_delay", 3.0))
        kl.addWidget(self.spin_kitap_time, 2, 1)

        layout.addWidget(grp_kitap)

        # Kol Grubu
        grp_kol = QGroupBox("KOL")
        kol_l = QGridLayout(grp_kol)

        self.chk_kol = QCheckBox("KOL AKTIF")
        self.chk_kol.setChecked(self.result_config.get("kol_enabled", False))
        kol_l.addWidget(self.chk_kol, 0, 0, 1, 2)

        kol_l.addWidget(QLabel("KOL TUSU:"), 1, 0)
        self.cmb_kol_key = QComboBox()
        self.cmb_kol_key.addItems([str(i) for i in range(10)])
        self.cmb_kol_key.setCurrentText(str(self.result_config.get("kol_key", 9)))
        kol_l.addWidget(self.cmb_kol_key, 1, 1)

        kol_l.addWidget(QLabel("KOL SURESI (sn):"), 2, 0)
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

# ==============================================================================
# ANA FARM BOT MANTIGI (MANTIK AYNI KALDI)
# ==============================================================================
class FarmMacro:
    def __init__(self):
        self.config = {}; self._running = False; self._stop_event = threading.Event(); self._main_thread = None; self._z_thread = None; self._lock = threading.Lock()
        self.img_hp_bar = None; self.img_mob_name = None; self.farm_area = None
        self.mode = "Warrior (Seri)"; self.threshold = 0.60 
        self.sub_macros = {
            "Warrior (Seri)": WarriorSkillMacro(), "Asas (VS)": AsasHybridMacro(),
            "Okcu (3-5)": ThreeFiveMacro(), "Self (Ozel)": SelfMacro(),
            "Priest (BP)": PriestAttackMacro()
        }

    def update_config(self, cfg):
        with self._lock:
            self.config = cfg; self.mode = cfg.get("mode", "Warrior (Seri)"); self.farm_area = cfg.get("farm_area", None)
            self._load_image("path_hp_bar", "img_hp_bar", grayscale=True); self._load_image("path_mob_name", "img_mob_name", grayscale=True)
            if self.mode in self.sub_macros:
                sub_key = f"subconfig_{self.mode}"; sub_cfg = self.config.get(sub_key, {}); macro = self.sub_macros[self.mode]
                if hasattr(macro, "update_config"): macro.update_config(sub_cfg)
                elif hasattr(macro, "set_params"): macro.set_params(sub_cfg.get("f_bar", 3), sub_cfg.get("key5", 2), sub_cfg.get("key3", 3), sub_cfg.get("combo_delay", 0.46), sub_cfg.get("w_delay", 0.05), "toggle", sub_cfg.get("use_f_key", True), sub_cfg.get("use_z", False), 0.1)

    def _load_image(self, key, attr, grayscale=False):
        p = self.config.get(key)
        if p and os.path.exists(p):
            try: flags = cv2.IMREAD_GRAYSCALE if grayscale else cv2.IMREAD_COLOR; setattr(self, attr, cv2.imread(p, flags))
            except: pass

    @property
    def is_running(self): return self._running

    def toggle(self):
        if self._running: self.stop()
        else: self.start()

    def start(self):
        if self.img_hp_bar is None or self.img_mob_name is None or self.farm_area is None: 
            return False
        if not self._running:
            self._stop_event.clear(); self._running = True
            self._main_thread = threading.Thread(target=self._main_loop, daemon=True); self._main_thread.start()
            self._z_thread = threading.Thread(target=self._z_loop, daemon=True); self._z_thread.start()
            return True
        return False

    def stop(self):
        self._stop_event.set(); self._running = False; _up(SC_W)

    def _z_loop(self):
        while not self._stop_event.is_set(): _tap(SC_Z, 0.03); time.sleep(1.0) 

    def _main_loop(self):
        sct = mss.mss(); STATE_CHECK_HP = 0; STATE_APPROACH = 1; STATE_ATTACK = 2; current_state = STATE_CHECK_HP
        while not self._stop_event.is_set():
            try:
                if current_state == STATE_CHECK_HP:
                    scr = np.array(sct.grab(sct.monitors[1])); scr_top = scr[0:300, :, :3]; gray_top = cv2.cvtColor(scr_top, cv2.COLOR_BGRA2GRAY)
                    res = cv2.matchTemplate(gray_top, self.img_hp_bar, cv2.TM_CCOEFF_NORMED); _, val, _, _ = cv2.minMaxLoc(res)
                    if val > self.threshold: current_state = STATE_APPROACH
                    else: time.sleep(0.1)
                elif current_state == STATE_APPROACH:
                    _tap(SC_R, 0.03); time.sleep(0.02); _down(SC_W); start_time = time.time(); found_target = False
                    while time.time() - start_time < 2.5:
                        if self._stop_event.is_set(): _up(SC_W); return
                        x, y, w, h = self.farm_area
                        area_img = np.array(sct.grab({"left": x, "top": y, "width": w, "height": h})); area_gray = cv2.cvtColor(area_img, cv2.COLOR_BGRA2GRAY)
                        res = cv2.matchTemplate(area_gray, self.img_mob_name, cv2.TM_CCOEFF_NORMED); _, val, _, _ = cv2.minMaxLoc(res)
                        if val > self.threshold: found_target = True; break
                        time.sleep(0.01)
                    _up(SC_W) 
                    if found_target or time.time() - start_time >= 2.5:
                        _tap(SC_S, 0.05); current_state = STATE_ATTACK
                elif current_state == STATE_ATTACK:
                    scr = np.array(sct.grab(sct.monitors[1])); scr_top = scr[0:300, :, :3]; gray_top = cv2.cvtColor(scr_top, cv2.COLOR_BGRA2GRAY)
                    res = cv2.matchTemplate(gray_top, self.img_hp_bar, cv2.TM_CCOEFF_NORMED); _, val, _, _ = cv2.minMaxLoc(res)
                    if val < self.threshold: current_state = STATE_CHECK_HP; continue 
                    active_macro = self.sub_macros.get(self.mode)
                    if active_macro:
                        if self.mode == "Warrior (Seri)": active_macro._do_combo_once()
                        elif self.mode == "Asas (VS)": active_macro.run_sequence()
                        elif self.mode == "Okcu (3-5)": active_macro._do_combo_once()
                        elif self.mode == "Priest (BP)": active_macro.do_attack()
                        elif self.mode == "Self (Ozel)":
                            for entry in active_macro.entries:
                                if self._stop_event.is_set(): break
                                if entry.get("scancode"): _tap(entry["scancode"], 0.02); time.sleep(entry.get("delay", 0.1))
                    time.sleep(0.01)
            except: time.sleep(1)

# ==============================================================================
# MODERNIZE EDILMIS GUI (AntiAFK Tarzi)
# ==============================================================================
# ==============================================================================
# FARM WIDGET (AntiAfkWidget ile Ayni Yapida)
# ==============================================================================
class FarmWidget(QFrame):
    update_signal = pyqtSignal()

    def __init__(self, parent=None, macro_instance=None, config=None):
        super().__init__(parent)
        self.macro = macro_instance or FarmMacro()
        self.config = config or {}
        self.macro.update_config(self.config)
        
        self.listen_active = False
        self._hotkey_handles = []
        self._last_toggle_time = 0
        
        self.setup_ui()
        self.update_signal.connect(self._safe_update_status)

    def setup_ui(self):
        self.setFrameShape(QFrame.Box)
        self.setFixedWidth(260)
        self.setStyleSheet("QFrame { background-color: #101010; border: 1px solid #444; border-radius: 4px; }")
        
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(5)
        
        # Header: Icon + Title
        h = QHBoxLayout()
        icon = QLabel()
        icon.setFixedSize(30, 30)
        icon.setStyleSheet("border:none;")
        # Ikon yolu - oncelik sirasina gore dene
        icon_paths = [
            os.path.join("icons", "gui", "farm.png"),
            os.path.join("icons", "genie.png"),
            resource_path(os.path.join("icons", "genie.png"))
        ]
        icon_loaded = False
        for icon_path in icon_paths:
            if os.path.exists(icon_path):
                pix = QPixmap(icon_path)
                if not pix.isNull():
                    icon.setPixmap(pix.scaled(30, 30, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                    icon_loaded = True
                    break
        if not icon_loaded:
            icon.setText("🚜")
        h.addWidget(icon)
        h.addStretch()
        
        title = QLabel("OTO FARM")
        title.setObjectName("MinorHeaderLabel")
        h.addWidget(title)
        v.addLayout(h)
        
        # Listen Button
        self.btn_listen = QPushButton("MAKROYU BASLAT")
        self.btn_listen.setObjectName("ThreeFiveListenButton")
        self.btn_listen.clicked.connect(self.toggle_listen)
        v.addWidget(self.btn_listen)
        
        # Status Label
        self.lbl_st = QLabel("DURUM: PASIF")
        self.lbl_st.setObjectName("MinorStatusLabel")
        v.addWidget(self.lbl_st)
        
        # Hotkey Row + Settings Button
        row = QHBoxLayout()
        row.addWidget(QLabel("TUS:"))
        self.lbl_hk = QLabel(self.config.get("hotkey", "G").upper())
        self.lbl_hk.setObjectName("HotkeyLabel")
        row.addWidget(self.lbl_hk)
        
        btn_set = QPushButton("⚙ AYARLAR")
        btn_set.setObjectName("MinorSettingsButton")
        btn_set.clicked.connect(self.open_settings)
        row.addWidget(btn_set)
        v.addLayout(row)

    def open_settings(self):
        dlg = FarmSettingsDialog(self, self.config, self.macro)
        if dlg.exec_() == QDialog.Accepted:
            self.config = dlg.result_config
            self.macro.update_config(self.config)
            self.lbl_hk.setText(self.config.get("hotkey", "G").upper())
        dlg.deleteLater()

    def toggle_listen(self):
        if not keyboard: return
        if not self.listen_active:
            try:
                hk = self.config.get("hotkey", "G").lower()
                self._hook = keyboard.on_press_key(hk, lambda e: self._on_hotkey_trigger())
                self.listen_active = True
            except: self.listen_active = False
        else:
            if hasattr(self, '_hook'): 
                try: keyboard.unhook(self._hook)
                except: pass
                self._hook = None
            self.listen_active = False
            self.macro.stop()
        self._safe_update_status()

    def _on_hotkey_trigger(self):
        curr = time.time()
        if curr - self._last_toggle_time < 0.5: return
        self._last_toggle_time = curr
        
        if self.macro.is_running:
            self.macro.stop()
        else:
            if not self.config.get("farm_area"):
                return
            self.macro.start()
        self.update_signal.emit()

    def _safe_update_status(self):
        if not self.listen_active:
            self.lbl_st.setText("DURUM: PASIF")
            self.lbl_st.setStyleSheet("color:#ff5555; font-weight:bold;")
        else:
            active = self.macro.is_running
            self.lbl_st.setText("DURUM: CALISIYOR" if active else "DURUM: HAZIR")
            self.lbl_st.setStyleSheet(f"color:{'#00ff4c' if active else '#ffff55'}; font-weight:bold;")


# ==============================================================================
# FARM SETTINGS DIALOG (AntiAfkSettingsDialog ile Ayni Yapida)
# ==============================================================================
class FarmSettingsDialog(QDialog):
    BASE_W, BASE_H = 500, 650

    def __init__(self, parent, config, macro):
        super().__init__(parent)
        self.setWindowTitle("OTO FARM AYARLARI")
        
        # Resizable
        self.setMinimumSize(380, 500)
        self.resize(480, 620)
        self.setSizeGripEnabled(True)

        self.config = config.copy()
        self.macro = macro
        self.result_config = None

        # Olcek state
        self._base_size = QSize(self.BASE_W, self.BASE_H)
        self._base_font_pt = float(self.font().pointSizeF() or 10.0)
        self._last_scale = 1.0

        # Dis layout: ustte scroll, altta OK/Cancel sabit
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(8)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(10)

        self._scroll.setWidget(content)
        outer.addWidget(self._scroll)

        # --- 1. Gorsel Tanimlamalar ---
        grp_pick = QGroupBox("Gorsel Tanimlamalar")
        gl = QGridLayout(grp_pick)

        # HP Bar
        self.lbl_hp_status = QLabel("✗")
        self.lbl_hp_status.setFixedWidth(20)
        self._update_status_label(self.lbl_hp_status, self.config.get("path_hp_bar"))
        gl.addWidget(self.lbl_hp_status, 0, 0)
        gl.addWidget(QLabel("HP Bar Yanindaki Mob Ismi:"), 0, 1)
        btn_hp = QPushButton("Yakala")
        btn_hp.clicked.connect(lambda: self.cap_img("path_hp_bar", "HP BAR ALANINI CIZ", self.lbl_hp_status))
        gl.addWidget(btn_hp, 0, 2)

        # Mob Ismi
        self.lbl_mob_status = QLabel("✗")
        self.lbl_mob_status.setFixedWidth(20)
        self._update_status_label(self.lbl_mob_status, self.config.get("path_mob_name"))
        gl.addWidget(self.lbl_mob_status, 1, 0)
        gl.addWidget(QLabel("Mobun Ustundeki Isim:"), 1, 1)
        btn_mob = QPushButton("Yakala")
        btn_mob.clicked.connect(lambda: self.cap_img("path_mob_name", "MOB ISMI ALANINI CIZ", self.lbl_mob_status))
        gl.addWidget(btn_mob, 1, 2)

        layout.addWidget(grp_pick)

        # --- 2. Alan Tanimlamalari ---
        grp_area = QGroupBox("Alan Tanimlamalari")
        gal = QGridLayout(grp_area)

        # Atak Alani
        self.lbl_area_status = QLabel("✗")
        self.lbl_area_status.setFixedWidth(20)
        self._update_status_label(self.lbl_area_status, self.config.get("farm_area"))
        gal.addWidget(self.lbl_area_status, 0, 0)
        gal.addWidget(QLabel("Atak Alani:"), 0, 1)
        btn_farm = QPushButton("Ciz")
        btn_farm.clicked.connect(lambda: self.sel_area("farm_area", "ATAK ALANI CIZ", self.lbl_area_status))
        gal.addWidget(btn_farm, 0, 2)

        layout.addWidget(grp_area)

        # --- 3. Atak Modu ---
        grp_mode = QGroupBox("Atak Modu")
        ml = QGridLayout(grp_mode)

        self.cmb_mode = QComboBox()
        self.cmb_mode.addItems(["Warrior (Seri)", "Asas (VS)", "Okcu (3-5)", "Priest (BP)", "Self (Ozel)"])
        self.cmb_mode.setCurrentText(self.config.get("mode", "Warrior (Seri)"))
        ml.addWidget(QLabel("Mod:"), 0, 0)
        ml.addWidget(self.cmb_mode, 0, 1)

        self.btn_mode_cfg = QPushButton("⚙")
        self.btn_mode_cfg.setFixedSize(30, 25)
        self.btn_mode_cfg.clicked.connect(self.open_mode_settings)
        ml.addWidget(self.btn_mode_cfg, 0, 2)

        layout.addWidget(grp_mode)

        # --- 4. Baslama Tusu ---
        grp_hk = QGroupBox("Baslama Tusu")
        hkl = QHBoxLayout(grp_hk)
        
        self.txt_hk = QLineEdit(self.config.get("hotkey", "G").upper())
        self.txt_hk.setReadOnly(True)
        hkl.addWidget(self.txt_hk)

        self.btn_capture_hk = QPushButton("TUS SEC")
        self.btn_capture_hk.clicked.connect(self.start_hotkey_capture)
        hkl.addWidget(self.btn_capture_hk)

        layout.addWidget(grp_hk)

        # OK/Cancel scroll disinda, altta sabit
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.on_accept)
        btns.rejected.connect(self.reject)
        outer.addWidget(btns)

        # Ilk stil + olcek uygula
        self._apply_scale(1.0)

    # ---- Olcekleme: pencere kuculdukce font + butonlar kuculsun ----
    def showEvent(self, e):
        super().showEvent(e)
        self._update_scale()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._update_scale()

    def _update_scale(self):
        s = min(self.width() / self._base_size.width(), self.height() / self._base_size.height())
        s = max(0.75, min(1.10, s))
        if abs(s - self._last_scale) < 0.02:
            return
        self._last_scale = s
        self._apply_scale(s)

    def _apply_scale(self, s: float):
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

        # ⚙ butonu olcekle
        if hasattr(self, "btn_mode_cfg"):
            self.btn_mode_cfg.setFixedSize(max(26, int(30*s)), max(22, int(25*s)))

    # ---- Durum etiketi guncelleme ----
    def _update_status_label(self, label, value):
        if value:
            label.setText("✓")
            label.setStyleSheet("color: #00ff4c; font-weight: bold;")
        else:
            label.setText("✗")
            label.setStyleSheet("color: #ff5555; font-weight: bold;")

    # ---- Mevcut fonksiyonlar ----
    def cap_img(self, key, title, status_label=None):
        self.setWindowOpacity(0)
        QApplication.processEvents()
        time.sleep(0.2)
        d = FullScreenSelector("area", title)
        if d.exec_() == QDialog.Accepted and d.result:
            x, y, w, h = d.result
            with mss.mss() as sct:
                img = np.array(sct.grab({"left": int(x), "top": int(y), "width": int(w), "height": int(h)}))
                if not os.path.exists("farm_data"): os.makedirs("farm_data")
                path = f"farm_data/{key}.png"
                cv2.imwrite(path, img)
                self.config[key] = path
                if status_label:
                    self._update_status_label(status_label, True)
        d.deleteLater()
        self.setWindowOpacity(1)
        self.activateWindow()

    def sel_area(self, key, title, status_label=None):
        self.setWindowOpacity(0)
        QApplication.processEvents()
        time.sleep(0.2)
        d = FullScreenSelector("area", title)
        if d.exec_() == QDialog.Accepted and d.result:
            self.config[key] = d.result
            if status_label:
                self._update_status_label(status_label, True)
        d.deleteLater()
        self.setWindowOpacity(1)
        self.activateWindow()

    def open_mode_settings(self):
        mode = self.cmb_mode.currentText()
        sub_key = f"subconfig_{mode}"
        current_sub_cfg = self.config.get(sub_key, {})
        dlg = None
        if mode == "Warrior (Seri)": dlg = WarriorSkillSettingsDialog(self, current_sub_cfg)
        elif mode == "Asas (VS)": dlg = AsasSettingsDialog(self, current_sub_cfg)
        elif mode == "Okcu (3-5)": dlg = ThreeFiveSettingsDialog(self, current_sub_cfg)
        elif mode == "Priest (BP)": dlg = PriestAttackSettingsDialog(self, current_sub_cfg)
        elif mode == "Self (Ozel)":
            dlg = SelfSettingsDialog(self, current_sub_cfg, None)

        if dlg and dlg.exec_() == QDialog.Accepted:
            new_cfg = getattr(dlg, "result_config", getattr(dlg, "config", {}))
            self.config[sub_key] = new_cfg

    def start_hotkey_capture(self):
        self.capture_hotkey = True
        self.txt_hk.setText("BIR TUSA BASIN...")
        self.btn_capture_hk.setText("BEKLENIYOR...")
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
                self.btn_capture_hk.setText("TUS SEC")
                self.releaseKeyboard()
            return

        super().keyPressEvent(e)

    def on_accept(self):
        self.config.update({
            "hotkey": self.txt_hk.text().upper(),
            "mode": self.cmb_mode.currentText(),
        })
        self.result_config = self.config
        self.accept()
