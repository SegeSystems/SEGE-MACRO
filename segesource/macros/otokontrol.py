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
import json
import cv2
import numpy as np
import mss

# PyQt5 - wari_kafa.py ile aynı import yapısı
from PyQt5.QtWidgets import (
    QDialog, QGridLayout, QLabel, QComboBox, 
    QLineEdit, QPushButton, QDoubleSpinBox, 
    QDialogButtonBox, QHBoxLayout, QWidget,
    QFrame, QVBoxLayout, QSizePolicy, QMessageBox,
    QCheckBox, QApplication, QRubberBand
)
from PyQt5.QtGui import QPixmap, QColor, QCursor
from PyQt5.QtCore import Qt, pyqtSignal, QPoint, QRect, QSize

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
if not os.path.exists("icons/oto"):
    try: os.makedirs("icons/oto")
    except: pass

DIGIT_SCANCODES = {
    1: 0x02, 2: 0x03, 3: 0x04, 4: 0x05, 5: 0x06,
    6: 0x07, 7: 0x08, 8: 0x09, 9: 0x0A, 0: 0x0B,
}
F_SCANCODES = {
    1: 0x3B, 2: 0x3C, 3: 0x3D, 4: 0x3E,
    5: 0x3F, 6: 0x40, 7: 0x41, 8: 0x42,
    9: 0x43, 10: 0x44, 11: 0x57, 12: 0x58
}

REGION_FILE = "BUFF_ALANI.json"

def _default_tap(scan_code: int, hold: float = 0.05):
    if _ClicksendKeyboardDriver and not hasattr(_default_tap, "_driver"):
        _default_tap._driver = _ClicksendKeyboardDriver()
    
    if hasattr(_default_tap, "_driver"):
        _default_tap._driver.tusbas(scan_code, hold)

# =========================================================
# 1. SNIPPING TOOL (BASİTLEŞTİRİLMİŞ)
# =========================================================
class SnippingWidget(QWidget):
    signal_captured = pyqtSignal(str) 

    def __init__(self, save_path):
        super().__init__()
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setWindowState(Qt.WindowFullScreen)
        self.setCursor(Qt.CrossCursor)
        self.save_path = save_path
        self.start_point = None
        self.end_point = None
        self.rubberband = QRubberBand(QRubberBand.Rectangle, self)
        
        # Ekran görüntüsünü al
        screen = QApplication.primaryScreen()
        if screen:
            self.original_pixmap = screen.grabWindow(0)
        else:
            self.original_pixmap = QPixmap(1920, 1080)

        # Arka planı hafif karartmak için label
        self.background_label = QLabel(self)
        self.background_label.setPixmap(self.original_pixmap)
        self.background_label.setGeometry(0, 0, 1920, 1080) # Varsayılan boyut, full screen çözecek
        
        # Karartma efekti
        self.overlay = QWidget(self)
        self.overlay.setStyleSheet("background-color: rgba(0, 0, 0, 100);")
        self.overlay.setGeometry(0, 0, 3840, 2160) # Geniş alan

    def mousePressEvent(self, event):
        self.start_point = event.pos()
        self.rubberband.setGeometry(QRect(self.start_point, QSize()))
        self.rubberband.show()

    def mouseMoveEvent(self, event):
        if self.start_point:
            self.rubberband.setGeometry(QRect(self.start_point, event.pos()).normalized())

    def mouseReleaseEvent(self, event):
        self.end_point = event.pos()
        self.rubberband.hide()
        
        rect = QRect(self.start_point, self.end_point).normalized()
        if rect.width() > 5 and rect.height() > 5:
            cropped = self.original_pixmap.copy(rect)
            cropped.save(self.save_path, "PNG")
            self.signal_captured.emit(self.save_path)
        
        self.close()

# =========================================================
# 2. LOGIC (MAKRO MOTORU)
# =========================================================
class OtoKontrolMacro:
    def __init__(self):
        self.items = {
            "feat_1": {"enabled": False, "f": 0, "d": 0, "icon_path": "icons/oto/feat_1.png", "tmpl": None, "fail_count": 0},
            "feat_2": {"enabled": False, "f": 0, "d": 0, "icon_path": "icons/oto/feat_2.png", "tmpl": None, "fail_count": 0},
            "feat_3": {"enabled": False, "f": 0, "d": 0, "icon_path": "icons/oto/feat_3.png", "tmpl": None, "fail_count": 0},
            "feat_4": {"enabled": False, "f": 0, "d": 0, "icon_path": "icons/oto/feat_4.png", "tmpl": None, "fail_count": 0},
        }
        
        self.region = None 
        self.match_threshold = 0.80
        self.check_interval = 0.40
        self.fail_limit = 2        
        
        self._running = False
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        
        self._load_region()
        self.reload_templates()

    def update_config(self, cfg):
        with self._lock:
            self.match_threshold = cfg.get("threshold", 0.80)
            for key, val in cfg.get("items", {}).items():
                if key in self.items:
                    self.items[key]["enabled"] = val.get("enabled", False)
                    self.items[key]["f"] = val.get("f", 0)
                    self.items[key]["d"] = val.get("d", 0)
            self._load_region()

    def reload_templates(self):
        with self._lock:
            for key, data in self.items.items():
                path = data["icon_path"]
                if os.path.isfile(path):
                    try:
                        d = np.fromfile(path, dtype=np.uint8)
                        img = cv2.imdecode(d, cv2.IMREAD_COLOR)
                        if img is not None:
                            self.items[key]["tmpl"] = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                    except: pass

    def _load_region(self):
        # BUFF_ALANI.json yoksa varsayılan
        if os.path.isfile(REGION_FILE):
            try:
                with open(REGION_FILE, "r") as f:
                    d = json.load(f)
                    self.region = {"left": int(d["x"]), "top": int(d["y"]), "width": int(d["w"]), "height": int(d["h"])}
            except: 
                self.region = {'top': 60, 'left': 400, 'width': 1515, 'height': 850}
        else:
            self.region = {'top': 60, 'left': 400, 'width': 1515, 'height': 850}

    def start(self):
        self._load_region()
        self.reload_templates()
        if not self.region: return
        for k in self.items: self.items[k]["fail_count"] = 0
        self._stop_event.clear()
        threading.Thread(target=self._loop, daemon=True).start()
        self._running = True

    def stop(self):
        self._stop_event.set()
        self._running = False

    @property
    def is_running(self): return self._running

    def toggle(self):
        if self._running: self.stop()
        else: self.start()

    def _loop(self):
        sct = mss.mss()
        while not self._stop_event.is_set():
            active_items = [k for k, v in self.items.items() if v["enabled"] and v["tmpl"] is not None]
            if not active_items:
                time.sleep(1)
                continue
            try:
                scr = np.array(sct.grab(self.region))
                gray = cv2.cvtColor(scr, cv2.COLOR_BGRA2GRAY)
                for key in active_items:
                    if self._stop_event.is_set(): break
                    item = self.items[key]
                    res = cv2.matchTemplate(gray, item["tmpl"], cv2.TM_CCOEFF_NORMED)
                    _, max_val, _, _ = cv2.minMaxLoc(res)
                    if max_val < self.match_threshold:
                        self.items[key]["fail_count"] += 1
                        if self.items[key]["fail_count"] >= self.fail_limit:
                            f_val = item["f"]
                            if f_val > 0:
                                f_code = F_SCANCODES.get(f_val)
                                if f_code: _default_tap(f_code, 0.05)
                                time.sleep(0.05)
                            d_val = item["d"]
                            if d_val >= 0:
                                d_code = DIGIT_SCANCODES.get(d_val)
                                if d_code: _default_tap(d_code, 0.05)
                            self.items[key]["fail_count"] = 0
                            time.sleep(0.1) 
                    else:
                        self.items[key]["fail_count"] = 0
                time.sleep(self.check_interval)
            except: time.sleep(1)

# =========================================================
# 3. GUI (AYAR PENCERESİ - wari_kafa.py STİLİ)
# =========================================================
class OtoKontrolSettingsDialog(QDialog):
    def __init__(self, parent, config, macro):
        super().__init__(parent)
        self.setWindowTitle("OTO KONTROL AYARLARI")
        self.setModal(True)
        self.config = config 
        self.macro = macro
        self.capture_hotkey = False
        self.snipper = None
        
        main = QVBoxLayout(self)
        grid = QGridLayout()
        grid.setContentsMargins(10, 10, 10, 10)
        grid.setSpacing(10)
        main.addLayout(grid)

        # --- SATIR 0: Hotkey ---
        grid.addWidget(QLabel("AKTIF TUŞ:"), 0, 0)
        self.txt_hotkey = QLineEdit(self.config.get("hotkey", "F10").upper())
        self.txt_hotkey.setReadOnly(True)
        self.btn_hotkey = QPushButton("TUŞ SEÇ")
        self.btn_hotkey.clicked.connect(self.on_hotkey_capture)
        hk_box = QHBoxLayout()
        hk_box.addWidget(self.txt_hotkey)
        hk_box.addWidget(self.btn_hotkey)
        grid.addLayout(hk_box, 0, 1, 1, 3)

        # --- SATIR 1: Hassasiyet ---
        grid.addWidget(QLabel("HASSASİYET:"), 1, 0)
        self.spin_threshold = QDoubleSpinBox()
        self.spin_threshold.setRange(0.1, 1.0)
        self.spin_threshold.setSingleStep(0.05)
        self.spin_threshold.setValue(self.config.get("threshold", 0.80))
        grid.addWidget(self.spin_threshold, 1, 1)
        grid.addWidget(QLabel("(0.80 Önerilir)"), 1, 2, 1, 2)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        grid.addWidget(line, 2, 0, 1, 5)

        # Başlıklar
        grid.addWidget(QLabel("<b>ÖZELLİK</b>"), 3, 0)
        grid.addWidget(QLabel("<b>DURUM</b>"), 3, 1)
        grid.addWidget(QLabel("<b>F TUŞU</b>"), 3, 2)
        grid.addWidget(QLabel("<b>SAYI</b>"), 3, 3)
        grid.addWidget(QLabel("<b>GÖRSEL</b>"), 3, 4)

        self.item_rows = [
            ("feat_1", "Özellik 1"),
            ("feat_2", "Özellik 2"),
            ("feat_3", "Özellik 3"),
            ("feat_4", "Özellik 4"),
        ]
        
        self.ui_elements = {} 
        start_row = 4
        
        for i, (key, name) in enumerate(self.item_rows):
            row = start_row + i
            current_cfg = self.config.get("items", {}).get(key, {})
            
            # 1. Özellik Adı (Sabit)
            grid.addWidget(QLabel(name), row, 0)
            
            # 2. Checkbox (Aktif/Pasif)
            chk = QCheckBox("Aktif")
            chk.setChecked(current_cfg.get("enabled", False))
            grid.addWidget(chk, row, 1)      
            
            # 3. F Tuşu Combo
            cmb_f = QComboBox()
            cmb_f.addItem("-", 0)  
            for f in range(1, 13): cmb_f.addItem(f"F{f}", f)
            idx_f = cmb_f.findData(current_cfg.get("f", 0))
            if idx_f < 0: idx_f = 0 
            cmb_f.setCurrentIndex(idx_f)
            grid.addWidget(cmb_f, row, 2)
            
            # 4. Digit Tuşu Combo
            cmb_d = QComboBox()
            cmb_d.addItem("-", -1)
            for d in range(10): cmb_d.addItem(str(d), d)
            idx_d = cmb_d.findData(current_cfg.get("d", -1))
            if idx_d < 0: idx_d = 0
            cmb_d.setCurrentIndex(idx_d)
            grid.addWidget(cmb_d, row, 3)

            # 5. Görsel Seç Butonu & Önizleme
            vbox = QVBoxLayout()
            lbl_preview = QLabel()
            lbl_preview.setFixedSize(30, 30)
            lbl_preview.setStyleSheet("border: 1px solid gray; background-color: black;")
            
            # Resim varsa yükle
            icon_path = f"icons/oto/{key}.png"
            if os.path.exists(icon_path):
                pix = QPixmap(icon_path)
                lbl_preview.setPixmap(pix.scaled(30, 30, Qt.KeepAspectRatio))
            
            btn_pick = QPushButton("Seç")
            btn_pick.setFixedSize(40, 20)
            btn_pick.clicked.connect(lambda checked, k=key, l=lbl_preview: self.open_snipper(k, l))
            
            # Yan yana koy
            hbox_img = QHBoxLayout()
            hbox_img.addWidget(lbl_preview)
            hbox_img.addWidget(btn_pick)
            hbox_img.setContentsMargins(0,0,0,0)
            
            container = QWidget()
            container.setLayout(hbox_img)
            grid.addWidget(container, row, 4)
            
            self.ui_elements[key] = { "chk": chk, "f": cmb_f, "d": cmb_d }

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        main.addWidget(btns)

    def open_snipper(self, key, label_widget):
        self.hide()
        save_path = f"icons/oto/{key}.png"
        self.snipper = SnippingWidget(save_path)
        self.snipper.signal_captured.connect(lambda p: self.on_snipped(p, label_widget))
        self.snipper.show()

    def on_snipped(self, path, label_widget):
        self.show()
        if os.path.exists(path):
            pix = QPixmap(path)
            label_widget.setPixmap(pix.scaled(30, 30, Qt.KeepAspectRatio))

    def on_hotkey_capture(self):
        self.capture_hotkey = True
        self.txt_hotkey.setText("BAS...")

    def keyPressEvent(self, event):
        if self.capture_hotkey:
            key = event.key()
            name = None
            if key == Qt.Key_CapsLock: name = "CAPSLOCK"
            elif key == Qt.Key_Shift: name = "SHIFT"
            elif key == Qt.Key_Control: name = "CTRL"
            elif key == Qt.Key_Alt: name = "ALT"
            elif Qt.Key_F1 <= key <= Qt.Key_F12: name = f"F{key - Qt.Key_F1 + 1}"
            else:
                text = event.text()
                if text: name = text.upper()
            
            if name:
                self.txt_hotkey.setText(name)
                self.capture_hotkey = False
            return
        super().keyPressEvent(event)

    def accept(self):
        self.config["hotkey"] = self.txt_hotkey.text()
        self.config["threshold"] = self.spin_threshold.value()
        
        if "items" not in self.config: self.config["items"] = {}
        for key, ui in self.ui_elements.items():
            if key not in self.config["items"]: self.config["items"][key] = {}
            self.config["items"][key]["enabled"] = ui["chk"].isChecked()
            self.config["items"][key]["f"] = int(ui["f"].currentData())
            self.config["items"][key]["d"] = int(ui["d"].currentData())

        self.macro.update_config(self.config)
        self.macro.reload_templates()
        super().accept()

# =========================================================
# 4. WIDGET (ANA EKRAN KARTI - wari_kafa.py ILE AYNI)
# =========================================================
class OtoKontrolWidget(QFrame):
    update_signal = pyqtSignal()

    def __init__(self, parent=None, macro_instance=None, config=None):
        super().__init__(parent)
        self.config = config or {}
        # Eğer dışarıdan instance gelmezse (loader mantığına göre) kendimiz yaratıyoruz
        self.macro = macro_instance or OtoKontrolMacro()
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

        # --- HEADER (Standart Stil) ---
        h = QHBoxLayout()
        h.setSpacing(4)
        
        # Basit ikon gösterimi (varsa)
        for i in range(1, 5):
            l = QLabel()
            l.setFixedSize(30, 30)
            l.setStyleSheet("border: 1px solid #333; background-color: black;")
            path = f"icons/oto/feat_{i}.png"
            if os.path.exists(path):
                pix = QPixmap(path)
                l.setPixmap(pix.scaled(30, 30, Qt.KeepAspectRatio))
            h.addWidget(l)
            
        h.addStretch(1)
        lbl_title = QLabel("OTO KONTROL")
        lbl_title.setObjectName("MinorHeaderLabel")
        lbl_title.setStyleSheet("color: white; font-weight: bold;")
        h.addWidget(lbl_title)
        v.addLayout(h)

        # --- BUTON (Standart Stil) ---
        self.btn_listen = QPushButton("TUŞ DİNLEMEYİ BAŞLAT")
        self.btn_listen.setObjectName("ThreeFiveListenButton") 
        self.btn_listen.setProperty("active", False)
        self.btn_listen.clicked.connect(self.toggle_listen)
        v.addWidget(self.btn_listen)

        # --- DURUM ---
        self.lbl_status = QLabel("DURUM: PASİF")
        self.lbl_status.setObjectName("MinorStatusLabel")
        v.addWidget(self.lbl_status)

        # --- ALT KISIM (Hotkey & Ayar) ---
        row = QHBoxLayout()
        row.setSpacing(4)
        row.addWidget(QLabel("AKTİF TUŞ:"))
        
        self.lbl_hotkey = QLabel(self.config.get("hotkey", "F10"))
        self.lbl_hotkey.setObjectName("HotkeyLabel")
        self.lbl_hotkey.setStyleSheet("border: 1px solid #444; padding: 4px; color: #00ff4c; font-weight: bold;")
        self.lbl_hotkey.setAlignment(Qt.AlignCenter)
        row.addWidget(self.lbl_hotkey)
        
        btn_settings = QPushButton("⚙ AYARLAR")
        btn_settings.setObjectName("MinorSettingsButton")
        btn_settings.setFlat(True)
        btn_settings.clicked.connect(self.open_settings)
        row.addWidget(btn_settings)

        v.addLayout(row)

    def open_settings(self):
        dlg = OtoKontrolSettingsDialog(self, self.config, self.macro)
        if dlg.exec_() == QDialog.Accepted:
            self.lbl_hotkey.setText(self.config.get("hotkey", "F10").upper())
            if self.listen_active:
                self.toggle_listen() # Restart
                self.toggle_listen()

    def toggle_listen(self):
        if not keyboard:
            return QMessageBox.warning(self, "Hata", "keyboard kütüphanesi yok")

        if not self.listen_active:
            hotkey = self.config.get("hotkey", "F10").lower()
            try:
                self._hotkey_hook = keyboard.on_press_key(hotkey, self.on_hotkey_press, suppress=False)
                self.listen_active = True
                print(f"[OTO] Dinleniyor: {hotkey}")
            except Exception as e:
                print(f"[OTO] Tuş hatası: {e}")
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
