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

# --- wari_kafa.py ---

import threading
import time
import os
import json
import cv2
import numpy as np
import mss

# PyQt5
from PyQt5.QtWidgets import (
    QDialog, QGridLayout, QLabel, QComboBox, 
    QLineEdit, QPushButton, QDoubleSpinBox, 
    QDialogButtonBox, QHBoxLayout, QWidget,
    QFrame, QVBoxLayout, QSizePolicy, QMessageBox,
    QCheckBox, QSpacerItem
)
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtCore import Qt, QSize, pyqtSignal
from pynput import mouse 

try:
    import keyboard
except ImportError:
    keyboard = None

# Driver
try:
    from clicksend import KeyboardDriver as _ClicksendKeyboardDriver
except ImportError:
    _ClicksendKeyboardDriver = None

# ---------------------------------------------------------
# SABİTLER
# ---------------------------------------------------------
DIGIT_SCANCODES = {
    1: 0x02, 2: 0x03, 3: 0x04, 4: 0x05, 5: 0x06,
    6: 0x07, 7: 0x08, 8: 0x09, 9: 0x0A, 0: 0x0B,
}
F_SCANCODES = {
    1: 0x3B, 2: 0x3C, 3: 0x3D, 4: 0x3E,
    5: 0x3F, 6: 0x40, 7: 0x41, 8: 0x42
}

# Tarama alanını BUFF_ALANI.json dosyasından alıyoruz.
REGION_FILE = "BUFF_ALANI.json" 

def _default_tap(scan_code: int, hold: float = 0.01):
    if _ClicksendKeyboardDriver and not hasattr(_default_tap, "_driver"):
        _default_tap._driver = _ClicksendKeyboardDriver()
    
    if hasattr(_default_tap, "_driver"):
        _default_tap._driver.tusbas(scan_code, hold)

# =========================================================
# 1. LOGIC (MAKRO MOTORU)
# =========================================================
class WarriorKafaMacro:
    def __init__(self):
        # Varsayılan itemler
        self.items = {
            "kafa":    {"enabled": False, "f": 1, "d": 9, "icon": "kafa.png",    "tmpl": None, "fail_count": 0},
            "kol":     {"enabled": False, "f": 1, "d": 0, "icon": "kol.png",     "tmpl": None, "fail_count": 0},
            "kilic":   {"enabled": False, "f": 1, "d": 6, "icon": "kilic.png",   "tmpl": None, "fail_count": 0},
            "booster": {"enabled": False, "f": 1, "d": 8, "icon": "booster.png", "tmpl": None, "fail_count": 0}, 
        }
        
        self.region = None # Tarama Alanı: BUFF_ALANI.json'dan gelecek
        self.match_threshold = 0.75 # Daha önce belirlenen eşik
        self.check_interval = 0.40
        self.fail_limit = 2        
        
        self._running = False
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        
        self._load_region() # Region'ı buff dosyasından yükle
        self._load_templates()

    def update_config(self, cfg):
        """Widget'tan gelen tüm ayarları günceller."""
        with self._lock:
            # Item ayarları
            for key, val in cfg.get("items", {}).items():
                if key in self.items:
                    self.items[key]["enabled"] = val.get("enabled", False)
                    self.items[key]["f"] = val.get("f", 1)
                    self.items[key]["d"] = val.get("d", 1)
            
            # Region Ayarı (Sadece güvenli olsun diye kontrol ediyoruz, asıl region load ile çekiliyor)
            self._load_region()

    def _load_region(self):
        """Tarama alanını BUFF_ALANI.json dosyasından okur (OtoExplore mantığı)."""
        if os.path.isfile(REGION_FILE):
            try:
                with open(REGION_FILE, "r") as f:
                    d = json.load(f)
                    self.region = {
                        "left": int(d["x"]), "top": int(d["y"]), 
                        "width": int(d["w"]), "height": int(d["h"])
                    }
 
            except: 
                print("[KAFA] HATA: BUFF_ALANI.json okunamadı. Varsayılan kullanılıyor.")
                self.region = {'top': 60, 'left': 400, 'width': 1515, 'height': 850}
        else:
            print("[KAFA] HATA: BUFF_ALANI.json bulunamadı. Varsayılan kullanılıyor.")
            self.region = {'top': 60, 'left': 400, 'width': 1515, 'height': 850}


    def _load_templates(self):
        base_dir = "icons/wari"
        if not os.path.exists(base_dir): return
            
        for key, data in self.items.items():
            path = os.path.join(base_dir, data["icon"])
            if os.path.isfile(path):
                try:
                    d = np.fromfile(path, dtype=np.uint8)
                    img = cv2.imdecode(d, cv2.IMREAD_COLOR)
                    if img is not None:
                        self.items[key]["tmpl"] = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                except: pass

    @property
    def is_running(self): return self._running

    def toggle(self):
        if self._running: self.stop()
        else: self.start()

    def start(self):
        self._load_region() # Başlamadan önce alanı güncelle
        if not self.region: return # Alan yoksa başlatma
            
        for k in self.items: self.items[k]["fail_count"] = 0
        
        self._stop_event.clear()
        threading.Thread(target=self._loop, daemon=True).start()
        self._running = True
        print(f"[KAFA] Başladı. Eşik: {self.match_threshold}")

    def stop(self):
        self._stop_event.set()
        self._running = False
        print("[KAFA] Durduruldu.")

    def _loop(self):
        sct = mss.mss()
        
        while not self._stop_event.is_set():
            active_items = [k for k, v in self.items.items() if v["enabled"] and v["tmpl"] is not None]
            
            if not active_items:
                time.sleep(1)
                continue

            try:
                # self.region'dan yakala
                scr = np.array(sct.grab(self.region))
                gray = cv2.cvtColor(scr, cv2.COLOR_BGRA2GRAY)
                
                for key in active_items:
                    if self._stop_event.is_set(): break
                    
                    item = self.items[key]
                    
                    res = cv2.matchTemplate(gray, item["tmpl"], cv2.TM_CCOEFF_NORMED)
                    _, max_val, _, _ = cv2.minMaxLoc(res)
                    
                    # Mantık: İkon GÖRÜNMÜYORSA (Skor düşükse) -> Bas
                    if max_val < self.match_threshold:
                        self.items[key]["fail_count"] += 1
                        
                        if self.items[key]["fail_count"] >= self.fail_limit:
                            print(f"[KAFA] {key} eksik! Tuş basılıyor...")
                            
                            f_val = item["f"]
                            if f_val > 0:
                                f_code = F_SCANCODES.get(f_val)
                                if f_code: 
                                    _default_tap(f_code, 0.05)
                                    time.sleep(0.05)
                            
                            d_code = DIGIT_SCANCODES.get(item["d"])
                            if d_code:
                                _default_tap(d_code, 0.05)
                            
                            self.items[key]["fail_count"] = 0
                            time.sleep(0.1) 
                    else:
                        self.items[key]["fail_count"] = 0

                time.sleep(self.check_interval)

            except Exception as e:
                print(f"[KAFA] Hata: {e}")
                time.sleep(1)


# =========================================================
# 2. GUI (AYAR PENCERESİ)
# =========================================================
class WarriorKafaSettingsDialog(QDialog):
    def __init__(self, parent, config, macro):
        super().__init__(parent)
        self.setWindowTitle("KAFA / EŞYA AYARLARI")
        self.setModal(True)
        self.config = config 
        self.macro = macro
        self.capture_hotkey = False
        
        main = QVBoxLayout(self)
        grid = QGridLayout()
        grid.setContentsMargins(10, 10, 10, 10)
        grid.setSpacing(10)
        main.addLayout(grid)

        # --- SATIR 0: Hotkey Seçimi ---
        grid.addWidget(QLabel("AKTIF TUŞ:"), 0, 0, 1, 2)
        self.txt_hotkey = QLineEdit(self.config.get("hotkey", "F11").upper())
        self.txt_hotkey.setReadOnly(True)
        self.btn_hotkey = QPushButton("TUŞ SEÇ")
        self.btn_hotkey.clicked.connect(self.on_hotkey_capture)
        hk_box = QHBoxLayout()
        hk_box.addWidget(self.txt_hotkey)
        hk_box.addWidget(self.btn_hotkey)
        grid.addLayout(hk_box, 0, 2, 1, 2)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        grid.addWidget(line, 1, 0, 1, 4)

        # İtem Listesi (Tarama alanı butonu kaldırıldı)
        self.item_rows = [
            ("kafa",    "Kafa",     "icons/wari/kafa.png"),
            ("kol",     "Kol",      "icons/wari/kol.png"),
            ("kilic",   "Kılıç",    "icons/wari/kilic.png"),
            ("booster", "Booster",  "icons/wari/booster.png")
        ]
        
        self.ui_elements = {} 
        start_row = 2
        
        for i, (key, name, icon_path) in enumerate(self.item_rows):
            row = start_row + i
            
            # İkon
            lbl_icon = QLabel()
            lbl_icon.setFixedSize(30, 30)
            pix = QPixmap(icon_path)
            if not pix.isNull():
                lbl_icon.setPixmap(pix.scaled(30, 30, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            grid.addWidget(lbl_icon, row, 0) 
            
            # Checkbox
            chk = QCheckBox(name)
            chk.setChecked(self.config.get("items", {}).get(key, {}).get("enabled", False))
            grid.addWidget(chk, row, 1)      
            
            # F Tuşu Combo
            cmb_f = QComboBox()
            cmb_f.addItem("F YOK", 0)  
            for f in range(1, 9): 
                cmb_f.addItem(f"F{f}", f)
            
            val_f = self.config.get("items", {}).get(key, {}).get("f", 1)
            idx_f = cmb_f.findData(val_f)
            if idx_f < 0: idx_f = 0 
            cmb_f.setCurrentIndex(idx_f)
            grid.addWidget(cmb_f, row, 2)
            
            # Digit Tuşu Combo
            cmb_d = QComboBox()
            cmb_d.addItems([str(d) for d in range(10)])
            val_d = self.config.get("items", {}).get(key, {}).get("d", 1)
            cmb_d.setCurrentText(str(val_d))
            grid.addWidget(cmb_d, row, 3)
            
            self.ui_elements[key] = { "chk": chk, "f": cmb_f, "d": cmb_d }
            
            # Enable/Disable logic
            cmb_f.setEnabled(chk.isChecked())
            cmb_d.setEnabled(chk.isChecked())
            chk.toggled.connect(cmb_f.setEnabled)
            chk.toggled.connect(cmb_d.setEnabled)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        main.addWidget(btns)

    def on_hotkey_capture(self):
        self.capture_hotkey = True
        self.txt_hotkey.setText("BAS...")

    def on_hotkey_capture(self):
        # 1. capture_hotkey değişkenini True yap
        self.capture_hotkey = True
        self.txt_hotkey.setText("BAS...")

    def keyPressEvent(self, event):
        # 1. İsimlendirme hatasını düzelt: self._capture_next_key -> self.capture_hotkey
        if self.capture_hotkey:
            key = event.key()
            name = None

            # 2. CAPS LOCK ve diğer özel tuşları pyautogui'nin anladığı formata (BÜYÜK TEK KELİME) düzelt
            if key == Qt.Key_CapsLock: name = "CAPSLOCK"
            elif key == Qt.Key_Shift: name = "SHIFT"
            elif key == Qt.Key_Control: name = "CTRL"
            elif key == Qt.Key_Alt: name = "ALT"
            elif key == Qt.Key_Space: name = "SPACE"
            elif Qt.Key_F1 <= key <= Qt.Key_F12: name = f"F{key - Qt.Key_F1 + 1}"
            else:
                text = event.text()
                if text: name = text.upper() # Harfleri/rakamları büyük harf yap
            
            if name:
                self.txt_hotkey.setText(name)
                # 3. İsimlendirme hatasını düzelt: self.capture_hotkey = False
                self.capture_hotkey = False
            return
        super().keyPressEvent(event)

    def accept(self):
        self.config["hotkey"] = self.txt_hotkey.text()
        
        # 1. Item ayarlarını kaydet
        if "items" not in self.config: self.config["items"] = {}
        for key, ui in self.ui_elements.items():
            if key not in self.config["items"]: self.config["items"][key] = {}
            
            enabled = ui["chk"].isChecked()
            f_val = int(ui["f"].currentData())
            d_val = int(ui["d"].currentText())

            self.config["items"][key]["enabled"] = enabled
            self.config["items"][key]["f"] = f_val
            self.config["items"][key]["d"] = d_val

        # 2. Region ayarı kaldırıldı, macro update'i ile güncellenecek
            
        # 3. Makroya yeni config'i uygula
        self.macro.update_config(self.config)

        super().accept()

# =========================================================
# 3. WIDGET (ANA EKRAN KARTI)
# =========================================================
class WarriorKafaWidget(QFrame):
    update_signal = pyqtSignal()

    def __init__(self, parent=None, macro_instance=None, config=None):
        super().__init__(parent)
        
        self.config = config or {}
        self.macro = macro_instance or WarriorKafaMacro()

        self.macro.update_config(self.config)


        self.listen_active = False
        self._hotkey_hook = None
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

        # Header ve İkonlar
        h = QHBoxLayout()
        h.setSpacing(4)
        
        icons = ["kafa.png", "kol.png", "kilic.png", "booster.png"]
        for icon in icons:
            l = QLabel()
            l.setFixedSize(25, 25)
            pix = QPixmap(f"icons/wari/{icon}")
            if not pix.isNull():
                l.setPixmap(pix.scaled(25, 25, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            h.addWidget(l)
            
        h.addStretch(1)
        lbl_title = QLabel("KAFA KONTROL")
        lbl_title.setObjectName("MinorHeaderLabel") # Mevcut CSS stilini kullan
        h.addWidget(lbl_title)
        v.addLayout(h)

        # Dinleme Butonu
        self.btn_listen = QPushButton("TUŞ DİNLEMEYİ BAŞLAT")
        self.btn_listen.setObjectName("ThreeFiveListenButton") # Mevcut CSS stilini kullan
        self.btn_listen.setProperty("active", False)
        self.btn_listen.clicked.connect(self.toggle_listen)
        v.addWidget(self.btn_listen)

        # Durum
        self.lbl_status = QLabel("DURUM: PASİF")
        self.lbl_status.setObjectName("MinorStatusLabel")
        v.addWidget(self.lbl_status)

        # Alt Kısım (Hotkey & Ayar)
        row = QHBoxLayout()
        row.setSpacing(4)
        row.addWidget(QLabel("AKTIF TUŞ:"))
        
        self.lbl_hotkey = QLabel(self.config.get("hotkey", "F11"))
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
        dlg = WarriorKafaSettingsDialog(self, self.config, self.macro)
        if dlg.exec_() == QDialog.Accepted:
            self.lbl_hotkey.setText(self.config.get("hotkey", "F11").upper())
            if self.listen_active:
                self.toggle_listen() # Kapat
                self.toggle_listen() # Aç

    def toggle_listen(self):
        if not keyboard:
            return QMessageBox.warning(self, "Hata", "keyboard kütüphanesi yok")

        if not self.listen_active:
            hotkey = self.config.get("hotkey", "F11").lower()
            try:
                # Toggle çalışması için on_press_key kullanıyoruz
                self._hotkey_hook = keyboard.on_press_key(hotkey, self.on_hotkey_press, suppress=False)
                self.listen_active = True
                print(f"[KAFA] Dinleniyor: {hotkey}")
            except Exception as e:
                print(f"[KAFA] Tuş hatası: {e}")
                self.listen_active = False
        else:
            if self._hotkey_hook:
                try: keyboard.unhook(self._hotkey_hook)
                except: pass
            self._hotkey_hook = None
            self.listen_active = False
            self.macro.stop()
        
        self._safe_update_status()

    def on_hotkey_press(self, e):
        current = time.time()
        if current - self._last_toggle_time < 0.2: return
        self._last_toggle_time = current
        
        self.macro.toggle()
        self.update_signal.emit()

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
