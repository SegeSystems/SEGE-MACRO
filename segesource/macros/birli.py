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
import sys
import cv2
import numpy as np
import mss

# PyQt5
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QDialog, QLineEdit, QDoubleSpinBox, QDialogButtonBox, QFrame,
    QGridLayout, QSpinBox, QMessageBox, QCheckBox, QSizePolicy
)
from PyQt5.QtCore import Qt, QSize, QRect, pyqtSignal
from PyQt5.QtGui import QIcon, QPixmap

try:
    import keyboard
except ImportError:
    keyboard = None

try:
    import pyautogui
except ImportError:
    pyautogui = None

# Opsiyonel clicksend / interception sürücüsü
try:
    from clicksend import KeyboardDriver as _ClicksendKeyboardDriver
    from clicksend import MouseDriver as _ClicksendMouseDriver
    HAS_CLICKSEND = True
except ImportError:
    _ClicksendKeyboardDriver = None
    _ClicksendMouseDriver = None
    HAS_CLICKSEND = False

# -----------------------------------------------------
# DİZİN TESPİTİ (MASAÜSTÜ VE TÜRKÇE KARAKTER FIX)
# -----------------------------------------------------
def resolve_root_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        # birli.py macros/src içindeyse iki üst klasöre (proje root) çıkar
        current_path = os.path.dirname(os.path.abspath(__file__))
        # macros/src/birli.py → macros/src
        if os.path.basename(current_path) == "src":
            parent = os.path.dirname(current_path)  # macros/
            if os.path.basename(parent) == "macros":
                return os.path.dirname(parent)      # PROJECT_ROOT
        # geriye dönük uyumluluk: eski macros_src varsa
        if os.path.basename(current_path) == "macros_src":
            return os.path.dirname(current_path)
        return current_path

BASE_DIR = resolve_root_dir()
CONFIG_FILE = "1LI_ALANI.json"

# -----------------------------------------------------
# BİRLİ MACRO MANTIĞI
# -----------------------------------------------------
class BirliMacro:
    def __init__(self):
        self.mouse = None
        if HAS_CLICKSEND:
            try:
                self.mouse = _ClicksendMouseDriver()
            except: pass
        
        self.offset_y = 50
        self.auto_mode = False
        self.loop_delay = 0.2
        
        self._running = False
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self.base_dir = BASE_DIR

    def set_config(self, offset_y, auto_mode, loop_delay):
        with self._lock:
            self.offset_y = offset_y
            self.auto_mode = auto_mode
            self.loop_delay = max(0.01, float(loop_delay))

    @property
    def is_running(self):
        return self._running

    def load_region(self):
            # self.root_dir yerine self.base_dir kullanın
            full_path = os.path.join(self.base_dir, CONFIG_FILE)
            
            try:
                if os.path.exists(full_path):
                    with open(full_path, "r") as f:
                        data = json.load(f)
                        return {
                            "left": int(data["x"]), "top": int(data["y"]), 
                            "width": int(data["w"]), "height": int(data["h"])
                        }
            except Exception as e:
                print(f"JSON Okuma Hatası: {e}")
            return None

    def toggle(self):
        if self._running:
            self.stop()
        else:
            if self.auto_mode:
                self.start_loop()
            else:
                self.run_once()

    def start_loop(self):
        self._stop_event.clear()
        self._running = True
        threading.Thread(target=self._loop_task, daemon=True).start()

    def stop(self):
        self._stop_event.set()
        self._running = False

    def run_once(self):
        if self._running: return
        self._running = True
        try:
            self._scan_and_click()
        finally:
            self._running = False

    def _loop_task(self):
        while not self._stop_event.is_set():
            try:
                self._scan_and_click()
                time.sleep(self.loop_delay)
            except:
                time.sleep(1)
        self._running = False

    def _scan_and_click(self):
        region = self.load_region()
        if not region: return

        img_path = os.path.join(self.base_dir, "icons", "birli.png")
        if not os.path.exists(img_path): return 

        with mss.mss() as sct:
            scr = np.array(sct.grab(region))
        
        scr_img = cv2.cvtColor(scr, cv2.COLOR_BGRA2BGR)
        
        # MASAÜSTÜ KARAKTER FIX (np.fromfile)
        try:
            img_array = np.fromfile(img_path, np.uint8)
            template = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        except: return

        if template is None: return

        res = cv2.matchTemplate(scr_img, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)

        if max_val >= 0.80:
            h, w = template.shape[:2]
            target_x = region["left"] + max_loc[0] + w // 2
            target_y = region["top"] + max_loc[1] + h // 2 + self.offset_y
            
            if self.mouse:
                self.mouse.leftclick(0.05, target_x, target_y)
            elif pyautogui:
                pyautogui.click(target_x, target_y)
            time.sleep(0.1)

# -----------------------------------------------------
# BİRLİ AYARLAR PENCERESİ (ORİJİNAL TASARIM)
# -----------------------------------------------------
class BirliSettingsDialog(QDialog):
    def __init__(self, parent, config):
        super().__init__(parent)
        self.setWindowTitle("BİRLİ TARAMA AYARLARI")
        self.setModal(True)
        self.config = config or {}
        self._capture_next_key = False

        layout = QGridLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(8)

        layout.addWidget(QLabel("AKTIF TUS:"), 0, 0)
        self.edit_hotkey = QLineEdit(self.config.get("hotkey", "T").upper())
        self.edit_hotkey.setReadOnly(True)
        
        btn_cap = QPushButton("TUŞ SEÇ")
        btn_cap.setObjectName("KeyCaptureButton")
        btn_cap.clicked.connect(self.start_capture)
        
        h = QHBoxLayout()
        h.addWidget(self.edit_hotkey)
        h.addWidget(btn_cap)
        layout.addLayout(h, 0, 1)

        self.chk_auto = QCheckBox("OTOMATIK MOD (SÜREKLİ TARAMA)")
        self.chk_auto.setChecked(self.config.get("auto_mode", False))
        layout.addWidget(self.chk_auto, 1, 0, 1, 2)

        layout.addWidget(QLabel("TARAMA HIZI (SN):"), 2, 0)
        self.spin_delay = QDoubleSpinBox()
        self.spin_delay.setRange(0.01, 5.0)
        self.spin_delay.setSingleStep(0.05)
        self.spin_delay.setValue(self.config.get("loop_delay", 0.2))
        layout.addWidget(self.spin_delay, 2, 1)
        
        self.spin_delay.setEnabled(self.chk_auto.isChecked())
        self.chk_auto.toggled.connect(self.spin_delay.setEnabled)

        layout.addWidget(QLabel("DIKEY KAYDIRMA (PX):"), 3, 0)
        self.spin_offset = QSpinBox()
        self.spin_offset.setRange(-500, 500)
        self.spin_offset.setValue(self.config.get("click_offset_y", 50))
        self.spin_offset.setSuffix(" px")
        layout.addWidget(self.spin_offset, 3, 1)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns, 4, 0, 1, 2)

    def start_capture(self):
        self._capture_next_key = True
        self.edit_hotkey.setText("BAS...")

    def keyPressEvent(self, event):
        if self._capture_next_key:
            key = event.key()
            name = None
            if key == Qt.Key_Escape: name = "ESC"
            elif key == Qt.Key_Tab: name = "TAB"
            elif key == Qt.Key_Backspace: name = "BACKSPACE"
            elif key == Qt.Key_Space: name = "SPACE"
            elif key == Qt.Key_CapsLock: name = "CAPS LOCK"
            elif key == Qt.Key_Shift: name = "SHIFT"
            elif key == Qt.Key_Control: name = "CTRL"
            elif key == Qt.Key_Alt: name = "ALT"
            elif Qt.Key_F1 <= key <= Qt.Key_F12: name = f"F{key - Qt.Key_F1 + 1}"
            else:
                text = event.text()
                if text: name = text.upper()
            if name:
                self.edit_hotkey.setText(name)
                self._capture_next_key = False
            return
        super().keyPressEvent(event)

    def accept(self):
        self.result_config = {
            "hotkey": self.edit_hotkey.text(),
            "click_offset_y": self.spin_offset.value(),
            "auto_mode": self.chk_auto.isChecked(),
            "loop_delay": self.spin_delay.value()
        }
        super().accept()

# -----------------------------------------------------
# BİRLİ WIDGET (ORİJİNAL %100 TASARIM)
# -----------------------------------------------------
class BirliWidget(QFrame):
    update_signal = pyqtSignal()

    def __init__(self, parent=None, macro=None, config=None):
        super().__init__(parent)
        self.macro = BirliMacro() 
        if macro: self.macro = macro
        
        self.config = config or {}
        self.apply_config_to_macro()

        self.listen_active = False
        self._listen_thread = None
        
        self.update_signal.connect(self._safe_update_status)
        self.setup_ui()
        self._safe_update_status()

    def apply_config_to_macro(self):
        self.macro.set_config(
            offset_y=self.config.get("click_offset_y", 50),
            auto_mode=self.config.get("auto_mode", False),
            loop_delay=self.config.get("loop_delay", 0.2)
        )

    def setup_ui(self):
        self.setFrameShape(QFrame.Box)
        self.setFrameShadow(QFrame.Plain)
        self.setMaximumWidth(260)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        # Orijinal CSS Stili
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
        h.setSpacing(6)
        icon = QLabel()
        icon.setFixedSize(30, 30)
        
        # İKON YOLU FIX
        gui_pix_path = os.path.join(BASE_DIR, "icons", "guibirli.png")
        pix = QPixmap(gui_pix_path)
        if not pix.isNull():
            icon.setPixmap(pix.scaled(30, 30, Qt.KeepAspectRatio, Qt.SmoothTransformation))

        lbl = QLabel("BİRLİ TARAMA")
        lbl.setObjectName("MinorHeaderLabel")

        h.addWidget(icon)
        h.addStretch(1)
        h.addWidget(lbl)
        v.addLayout(h)

        self.btn_listen = QPushButton("TUŞ DİNLEMEYİ BAŞLAT")
        self.btn_listen.setObjectName("ThreeFiveListenButton") 
        self.btn_listen.setProperty("active", False)
        self.btn_listen.clicked.connect(self.toggle_listen)
        v.addWidget(self.btn_listen)

        self.lbl_status = QLabel("DURUM: PASİF")
        self.lbl_status.setObjectName("MinorStatusLabel")
        v.addWidget(self.lbl_status)

        row = QHBoxLayout()
        row.setSpacing(4)
        row.addWidget(QLabel("AKTIF TUS:"))
        
        self.lbl_hotkey = QLabel(self.config.get("hotkey", "T"))
        self.lbl_hotkey.setObjectName("HotkeyLabel")
        self.lbl_hotkey.setAlignment(Qt.AlignCenter)
        row.addWidget(self.lbl_hotkey)
        
        btn_settings = QPushButton("⚙ AYARLAR")
        btn_settings.setObjectName("MinorSettingsButton")
        btn_settings.setFlat(True)
        btn_settings.clicked.connect(self.open_settings)
        row.addWidget(btn_settings)
        v.addLayout(row)

    def open_settings(self):
        dlg = BirliSettingsDialog(self, self.config)
        if dlg.exec_() == QDialog.Accepted:
            self.config.update(dlg.result_config)
            self.apply_config_to_macro()
            self.lbl_hotkey.setText(self.config.get("hotkey"))
            if self.listen_active:
                self.toggle_listen(); self.toggle_listen()

    def toggle_listen(self):
        if not self.listen_active:
            self.listen_active = True
            self._listen_thread = threading.Thread(target=self._polling_loop, daemon=True)
            self._listen_thread.start()
        else:
            self.listen_active = False
            self.macro.stop()
        self._safe_update_status()

    def _polling_loop(self):
        hk = self.config.get("hotkey", "t").lower().strip()
        last = 0
        while self.listen_active:
            try:
                if keyboard.is_pressed(hk):
                    curr = time.time()
                    if curr - last > 0.3:
                        last = curr
                        self.macro.toggle()
                        self.update_signal.emit()
                time.sleep(0.01)
            except: time.sleep(1)

    def _safe_update_status(self):
        if not self.listen_active:
            self.lbl_status.setText("DURUM: PASİF")
            self.btn_listen.setText("TUŞ DİNLEMEYİ BAŞLAT")
            act = False
            self.apply_status_style("#ff5555")
        else:
            if self.macro.is_running:
                self.lbl_status.setText("DURUM: ÇALIŞIYOR")
                self.apply_status_style("#00ff4c")
            else:
                self.lbl_status.setText("DURUM: BEKLİYOR")
                self.apply_status_style("#ffff55")
            self.btn_listen.setText("TUŞ DİNLEMEYİ DURDUR")
            act = True
        
        self.btn_listen.setProperty("active", act)
        self.btn_listen.style().unpolish(self.btn_listen)
        self.btn_listen.style().polish(self.btn_listen)

    def apply_status_style(self, color: str = "#8d95c7"):
        self.lbl_status.setStyleSheet(f"color: {color}; font-weight: bold;")
