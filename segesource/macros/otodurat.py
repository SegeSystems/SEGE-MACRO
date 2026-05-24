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

# --- otodurat.py ---

import threading
import time
import os
import cv2
import numpy as np
import mss
import pyautogui
import json
from typing import Callable, Literal

# PyQt5
from PyQt5.QtWidgets import (
    QDialog, QGridLayout, QLabel, QComboBox, 
    QLineEdit, QPushButton, QDoubleSpinBox, 
    QDialogButtonBox, QHBoxLayout, QWidget,
    QFrame, QVBoxLayout, QSizePolicy, QMessageBox,
    QCheckBox, QScrollArea, QGroupBox
)
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtCore import Qt, QSize, pyqtSignal, QTimer

try:
    import keyboard
except ImportError:
    keyboard = None

# Sürücü Kontrolü
try:
    from clicksend import KeyboardDriver as _ClicksendKeyboardDriver
    from clicksend import MouseDriver as _ClicksendMouseDriver
except ImportError:
    _ClicksendKeyboardDriver = None
    _ClicksendMouseDriver = None

# ---------------------------------------------------------
# SABİTLER
# ---------------------------------------------------------
F_SCANCODES = {1: 0x3B, 2: 0x3C, 3: 0x3D, 4: 0x3E, 5: 0x3F, 6: 0x40, 7: 0x41, 8: 0x42, 9: 0x43}
DIGIT_SCANCODES = {1: 0x02, 2: 0x03, 3: 0x04, 4: 0x05, 5: 0x06, 6: 0x07, 7: 0x08, 8: 0x09, 9: 0x0A, 0: 0x0B}
F_KEY_MAP = {f"F{i}": i for i in range(1, 10)}
F_KEY_MAP["F YOK"] = 0
BUFF_REGION_FILE = "BUFF_ALANI.json"

def _default_tap(scan_code: int, duration: float = 0.01):
    if not scan_code: return
    if _ClicksendKeyboardDriver is None: return
    if not hasattr(_default_tap, "_driver"):
        _default_tap._driver = _ClicksendKeyboardDriver()
    _default_tap._driver.tusbas(scan_code, duration)

# --- GELİŞMİŞ RENK VE PARLAKLIK KONTROLÜ (GÜNCELLENDİ) ---
def is_icon_active(screen_img, top_left, w, h, name="Unknown"):
    """
    İkonun aktif olup olmadığını anlamak için hem DOYGUNLUK (Renk) 
    hem de PARLAKLIK (Işık) değerlerine bakar.
    """
    # --- AYARLANAN KISIM ---
    SATURATION_THRESHOLD = 80  
    VALUE_THRESHOLD = 40       

    x, y = top_left
    roi = screen_img[y:y+h, x:x+w]
    
    try:
        # BGR -> HSV Dönüşümü
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        
        # Ortalama değerleri hesapla
        mean_sat = np.mean(hsv[:, :, 1]) # Doygunluk (Grilik/Renklilik)
        mean_val = np.mean(hsv[:, :, 2]) # Parlaklık (Karanlık/Aydınlık)

        # Analiz çıktısı (debug için)
        # print(f"[ANALIZ] {name} -> Sat: {mean_sat:.1f} | Val: {mean_val:.1f}")
        
        if mean_sat > SATURATION_THRESHOLD and mean_val > VALUE_THRESHOLD:
            return True
        else:
            return False

    except Exception as e:
        print(f"Renk hatası: {e}")
        return True 

# ---------------------------------------------------------
# 1. LOGIC (MAKRO MOTORU)
# ---------------------------------------------------------
class OtoDuratMacro:
    def __init__(self):
        # Varsayılan Ayarlar
        self.key = "F12"
        self.f_key = "F3"
        self.num_key = "2"
        self.scan_mode = "toggle" 
        self.speed = 0.5          
        
        self.selected_icons = {} 
        self.region = {'top': 60, 'left': 400, 'width': 1515, 'height': 850}
        self.templates = {}
        
        self._running = False
        self._stop_event = threading.Event()
        self._sct = mss.mss()
        self._lock = threading.Lock()
        
        self._driver = _ClicksendKeyboardDriver() if _ClicksendKeyboardDriver else None
        self._mouse = _ClicksendMouseDriver() if _ClicksendMouseDriver else None
        
        self._load_templates()

    def update_config(self, cfg):
        with self._lock:
            self.key = cfg.get("key", "F12")
            self.f_key = cfg.get("f_key", "F3")
            self.num_key = cfg.get("num_key", "2")
            self.scan_mode = cfg.get("scan_mode", "toggle")
            self.speed = cfg.get("speed", 0.5)
            self.selected_icons = cfg.get("selected_icons", {})
            self._load_region()

    def _load_region(self):
        if os.path.isfile(BUFF_REGION_FILE):
            try:
                with open(BUFF_REGION_FILE, "r") as f:
                    d = json.load(f)
                    self.region = {
                        "left": int(d["x"]), "top": int(d["y"]), 
                        "width": int(d["w"]), "height": int(d["h"])
                    }
            except: pass

    def _load_templates(self):
        base_dir = "icons" 
        names = ["kafa.png", "80cc.png", "durat1.png", "durat2.png"]
        if not os.path.exists(base_dir): return
        
        for name in names:
            path = os.path.join(base_dir, name)
            if os.path.isfile(path):
                img = cv2.imread(path, cv2.IMREAD_COLOR)
                if img is not None:
                    self.templates[name] = img

    @property
    def is_running(self): return self._running

    def toggle(self):
        if self._running: self.stop()
        else: self.start_loop()

    def start_loop(self):
        if not self._running:
            self._stop_event.clear()
            self._running = True
            threading.Thread(target=self._loop_logic, daemon=True).start()

    def run_once(self):
        if not self._running:
            self._running = True
            threading.Thread(target=self._logic_single_wrapper, daemon=True).start()

    def stop(self):
        self._stop_event.set()
        self._running = False

    def _logic_single_wrapper(self):
        self._logic(quiet=False)
        self._running = False

    def _right_click_at(self, x, y):
        if self._mouse:
            try:
                if hasattr(self._mouse, 'move'):
                    self._mouse.move(int(x), int(y))
                    time.sleep(0.02)
                
                if hasattr(self._mouse, 'right_click'):
                     self._mouse.right_click()
                     time.sleep(0.05)
                     self._mouse.right_click()
                elif hasattr(self._mouse, 'rightclick'):
                     self._mouse.rightclick(0.05, int(x), int(y))
                     time.sleep(0.05)
                     self._mouse.rightclick(0.05, int(x), int(y))
            except Exception as e:
                print(f"[DURAT] Mouse Driver Hatası: {e}")
        else:
            pyautogui.moveTo(x, y)
            pyautogui.rightClick()
            pyautogui.rightClick()

    def _move_mouse_only(self, x, y):
        if self._mouse and hasattr(self._mouse, 'move'):
            self._mouse.move(int(x), int(y))
        else:
            pyautogui.moveTo(x, y)

    def _loop_logic(self):
        print(f"[DURAT] Otomatik Döngü Başladı. Hız: {self.speed}sn")
        while not self._stop_event.is_set():
            try:
                self._logic(quiet=True)
                time.sleep(self.speed)
            except Exception as e:
                print(f"[DURAT LOOP] Hata: {e}")
                time.sleep(1)
        self._running = False
        print("[DURAT] Otomatik Döngü Durduruldu.")

    def _logic(self, quiet=False):
        if not quiet: print("[DURAT] Manuel Tarama...")
        
        try:
            with mss.mss() as sct:
                scr = np.array(sct.grab(self.region))
                scr_bgr = cv2.cvtColor(scr, cv2.COLOR_BGRA2BGR)
                
                ox, oy = pyautogui.position()
                action_taken = False

                # Döngüyü kırmadan tüm seçili ikonları tara
                for name, enabled in self.selected_icons.items():
                    if not enabled or name not in self.templates: continue
                    
                    tmpl = self.templates[name]
                    res = cv2.matchTemplate(scr_bgr, tmpl, cv2.TM_CCOEFF_NORMED)
                    _, max_val, _, max_loc = cv2.minMaxLoc(res)
                    
                    if max_val > 0.8:
                        h, w = tmpl.shape[:2]
                        
                        # Parlaklık/Doygunluk Kontrolü
                        if not is_icon_active(scr_bgr, max_loc, w, h, name):
                            if not quiet: print(f"[DURAT] {name} SÖNÜK (Cooldown/Aktif). Atlanıyor.")
                            continue 

                        if not quiet: print(f"[DURAT] Bulundu ve AKTİF: {name} ({max_val:.2f})")
                        
                        # 1. F Tuşuna Bas (Örn: F3)
                        f_num = F_KEY_MAP.get(self.f_key, 0)
                        if f_num > 0:
                            scancode = F_SCANCODES.get(f_num)
                            if scancode:
                                _default_tap(scancode, 0.05)
                                time.sleep(0.05)
                        
                        # 2. Skill Tuşuna Bas (Örn: 2)
                        try:
                            d_num = int(self.num_key)
                            scancode_digit = DIGIT_SCANCODES.get(d_num)
                            if scancode_digit:
                                _default_tap(scancode_digit, 0.05)
                                time.sleep(0.05)
                        except: pass
                        
                        # 3. Mouse Git ve Sağ Tık
                        cx = self.region['left'] + max_loc[0] + w // 2
                        cy = self.region['top'] + max_loc[1] + h // 2
                        
                        self._right_click_at(cx, cy)
                        action_taken = True
                        
                        # Çoklu seçimde oyunun algılaması için küçük bir bekleme
                        time.sleep(0.2) 
                        
                        # 'break' KOMUTU KALDIRILDI: Döngü devam eder ve diğer ikonları da kontrol eder.
                
                # Eğer en az bir işlem yapıldıysa mouse'u eski yerine döndür
                if action_taken:
                    self._move_mouse_only(ox, oy)

        except Exception as e:
            print(f"[DURAT] Hata: {e}")

# ---------------------------------------------------------
# GUI KISIMLARI (AYNI KALDI)
# ---------------------------------------------------------
class OtoDuratSettingsDialog(QDialog):
    def __init__(self, parent, config, macro):
        super().__init__(parent)
        self.setWindowTitle("OTO DURATION AYARLARI")
        self.setModal(True)
        self.config = config
        self.macro = macro
        self.capture_hotkey = False
        
        layout = QGridLayout(self)
        layout.setSpacing(10)

        layout.addWidget(QLabel("BAŞLAT TUŞU:"), 0, 0)
        self.txt_key = QLineEdit(self.config.get("key", "F12"))
        self.txt_key.setReadOnly(True)
        btn_key = QPushButton("SEÇ")
        btn_key.clicked.connect(self.on_capture)
        h = QHBoxLayout(); h.addWidget(self.txt_key); h.addWidget(btn_key)
        layout.addLayout(h, 0, 1)

        layout.addWidget(QLabel("F BAR (F1–F9):"), 1, 0)
        self.cmb_f = QComboBox()
        self.cmb_f.addItem("F YOK", "F YOK") 
        self.cmb_f.addItems([f"F{i}" for i in range(1, 10)])
        self.cmb_f.setCurrentText(self.config.get("f_key", "F3"))
        layout.addWidget(self.cmb_f, 1, 1)

        layout.addWidget(QLabel("SKILL SLOTU (0–9):"), 2, 0)
        self.cmb_num = QComboBox()
        self.cmb_num.addItems([str(i) for i in range(10)])
        self.cmb_num.setCurrentText(self.config.get("num_key", "2"))
        layout.addWidget(self.cmb_num, 2, 1)

        layout.addWidget(QLabel("ÇALIŞMA MODU:"), 3, 0)
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItems(["Tek Seferlik (Manuel)", "Otomatik (Sürekli)"])
        current_mode = self.config.get("scan_mode", "toggle")
        self.cmb_mode.setCurrentIndex(1 if current_mode == "toggle" else 0)
        layout.addWidget(self.cmb_mode, 3, 1)

        layout.addWidget(QLabel("TARAMA HIZI (SN):"), 4, 0)
        self.spin_speed = QDoubleSpinBox()
        self.spin_speed.setRange(0.1, 5.0)
        self.spin_speed.setSingleStep(0.1)
        self.spin_speed.setValue(self.config.get("speed", 0.5))
        layout.addWidget(self.spin_speed, 4, 1)

        layout.addWidget(QLabel("HEDEFLER:"), 5, 0)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumHeight(120)
        content_widget = QWidget()
        target_box = QVBoxLayout(content_widget)
        
        self.checks = {}
        icons = ["kafa.png", "80cc.png", "durat1.png", "durat2.png"]
        sel = self.config.get("selected_icons", {})
        
        for ic in icons:
            chk = QCheckBox(ic.replace(".png", "").upper())
            chk.setChecked(sel.get(ic, False))
            target_box.addWidget(chk)
            self.checks[ic] = chk
            
        target_box.addStretch()
        scroll.setWidget(content_widget)
        layout.addWidget(scroll, 5, 1)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns, 6, 0, 1, 2)

    def on_capture(self):
        self.capture_hotkey = True
        self.txt_key.setText("...")

    def keyPressEvent(self, event):
        if self.capture_hotkey:
            key = event.key()
            name = None
            if key == Qt.Key_CapsLock: name = "CAPS LOCK"
            elif key == Qt.Key_Shift: name = "SHIFT"
            elif key == Qt.Key_Control: name = "CTRL"
            elif Qt.Key_F1 <= key <= Qt.Key_F12: 
                name = f"F{key - Qt.Key_F1 + 1}"
            else:
                text = event.text()
                if text and text.strip(): name = text.upper()
            if name:
                self.txt_key.setText(name)
                self.capture_hotkey = False
            return
        super().keyPressEvent(event)

    def accept(self):
        self.config["key"] = self.txt_key.text()
        self.config["f_key"] = self.cmb_f.currentText()
        self.config["num_key"] = self.cmb_num.currentText()
        is_auto = (self.cmb_mode.currentIndex() == 1)
        self.config["scan_mode"] = "toggle" if is_auto else "single"
        self.config["speed"] = self.spin_speed.value()
        new_sel = {}
        for name, chk in self.checks.items():
            new_sel[name] = chk.isChecked()
        self.config["selected_icons"] = new_sel
        self.macro.update_config(self.config)
        super().accept()

class OtoDuratWidget(QFrame):
    update_signal = pyqtSignal()

    def __init__(self, parent=None, macro_instance=None, config=None):
        super().__init__(parent)
        self.macro = macro_instance
        self.config = config or {}
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

        h = QHBoxLayout(); h.setSpacing(6)
        icon = QLabel(); icon.setFixedSize(25, 25)
        pix = QPixmap("icons/durat.png") 
        if not pix.isNull(): icon.setPixmap(pix.scaled(25,25, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        h.addWidget(icon)
        
        title = QLabel("OTO DURATION"); title.setObjectName("MinorHeaderLabel")
        h.addStretch(); h.addWidget(title)
        v.addLayout(h)

        self.btn_listen = QPushButton("TUŞ DİNLEMEYİ BAŞLAT")
        self.btn_listen.setObjectName("ThreeFiveListenButton")
        self.btn_listen.setProperty("active", False)
        self.btn_listen.clicked.connect(self.toggle_listen)
        v.addWidget(self.btn_listen)

        self.lbl_status = QLabel("DURUM: PASİF"); self.lbl_status.setObjectName("MinorStatusLabel")
        v.addWidget(self.lbl_status)

        row = QHBoxLayout()
        row.addWidget(QLabel("TUŞ:"))
        self.lbl_key = QLabel(self.config.get("key", "F12")); self.lbl_key.setObjectName("HotkeyLabel")
        row.addWidget(self.lbl_key)
        btn_set = QPushButton("⚙ AYARLAR"); btn_set.setObjectName("MinorSettingsButton")
        btn_set.clicked.connect(self.open_settings)
        row.addWidget(btn_set)
        v.addLayout(row)

    def open_settings(self):
        dlg = OtoDuratSettingsDialog(self, self.config, self.macro)
        if dlg.exec_():
            self.lbl_key.setText(self.config["key"])
            if self.listen_active: self.toggle_listen(); self.toggle_listen()

    def toggle_listen(self):
        if not keyboard:
            return QMessageBox.warning(self, "Hata", "keyboard kütüphanesi yok")

        if not self.listen_active:
            hotkey = self.config.get("key", "F12").lower()
            try:
                self._hooks.append(keyboard.on_press_key(hotkey, lambda e: self.on_hotkey_press()))
                self.listen_active = True
            except Exception as e:
                QMessageBox.warning(self, "Hata", f"Tuş dinleme başlatılamadı: {e}")
                self.listen_active = False
        else:
            for h in self._hooks: keyboard.unhook(h)
            self._hooks = []
            self.listen_active = False
            self.macro.stop()
        self._safe_update_status()

    def on_hotkey_press(self):
        if self.macro.scan_mode == "toggle":
            self.macro.toggle()
        else:
            if not self.macro.is_running:
                self.macro.run_once()
        self.update_signal.emit()

    def apply_status_style(self, color):
        self.lbl_status.setStyleSheet(f"color: {color}; font-weight: bold;")

    def _safe_update_status(self):
        if not self.listen_active:
            self.lbl_status.setText("DURUM: PASİF")
            self.btn_listen.setText("TUŞ DİNLEMEYİ BAŞLAT")
            act = False
            self.apply_status_style("#ff5555")
        else:
            if self.macro.is_running:
                mode_text = "OTO ÇALIŞIYOR" if self.macro.scan_mode == "toggle" else "TEK SEFERLİK"
                self.lbl_status.setText(mode_text)
                self.apply_status_style("#00ff4c")
            else:
                self.lbl_status.setText("BEKLİYOR")
                self.apply_status_style("#ffff55")
            self.btn_listen.setText("TUŞ DİNLEMEYİ DURDUR")
            act = True
        
        self.btn_listen.setProperty("active", act)
        self.btn_listen.style().unpolish(self.btn_listen)
        self.btn_listen.style().polish(self.btn_listen)

        if self.listen_active:
             QTimer.singleShot(200, self._safe_update_status)
