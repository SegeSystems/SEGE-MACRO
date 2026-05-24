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
import ctypes
import pyautogui

# PyQt5
from PyQt5.QtWidgets import (
    QDialog, QGridLayout, QLabel, QComboBox, 
    QLineEdit, QPushButton, QDoubleSpinBox, QSpinBox,
    QDialogButtonBox, QHBoxLayout, QWidget,
    QFrame, QVBoxLayout, QSizePolicy, QMessageBox,
    QCheckBox, QApplication, QRubberBand
)
from PyQt5.QtGui import QPixmap, QColor, QPainter, QPen, QBrush
from PyQt5.QtCore import Qt, pyqtSignal, QPoint, QRect, QSize

try:
    import keyboard
except ImportError:
    keyboard = None

# Driver (ClickSend)
try:
    from clicksend import MouseDriver as _ClicksendMouseDriver
except ImportError:
    _ClicksendMouseDriver = None

# ---------------------------------------------------------
# MOUSE VE YARDIMCI FONKSİYONLAR
# ---------------------------------------------------------
if not os.path.exists("icons/tiklama"):
    try: os.makedirs("icons/tiklama")
    except: pass 

def _move_mouse(x, y):
    # Ctypes ile kesin hareket
    ctypes.windll.user32.SetCursorPos(int(x), int(y))

def _click_left():
    if _ClicksendMouseDriver and hasattr(_click_left, "_driver"):
        try:
            _click_left._driver.leftclick(0.05, int(pyautogui.position()[0]), int(pyautogui.position()[1]))
            return
        except:
            pass
    
    # Fallback: SendInput (driver yok veya hata oldu)
    _send_input_mouse_click("left")

def _click_right():
    if _ClicksendMouseDriver and hasattr(_click_right, "_driver"):
        try:
            _click_right._driver.rightclick(0.05, int(pyautogui.position()[0]), int(pyautogui.position()[1]))
            return
        except:
            pass
    
    # Fallback: SendInput (driver yok veya hata oldu)
    _send_input_mouse_click("right")

def _send_input_mouse_click(click_type):
    """SendInput ile mouse tıklaması (driver fallback)"""
    PUL = ctypes.POINTER(ctypes.c_ulong)
    class MouseInput(ctypes.Structure):
        _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long), ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong), ("dwExtraInfo", PUL)]
    class Input_I(ctypes.Union):
        _fields_ = [("mi", MouseInput)]
    class Input(ctypes.Structure):
        _fields_ = [("type", ctypes.c_ulong), ("ii", Input_I)]
    
    extra = ctypes.c_ulong(0)
    
    if click_type == "left":
        # Sol tık DOWN
        ii = Input_I()
        ii.mi = MouseInput(0, 0, 0, 0x0002, 0, ctypes.pointer(extra))
        x_input = Input(ctypes.c_ulong(0), ii)
        ctypes.windll.user32.SendInput(1, ctypes.pointer(x_input), ctypes.sizeof(x_input))
        time.sleep(0.05)
        # Sol tık UP
        ii.mi = MouseInput(0, 0, 0, 0x0004, 0, ctypes.pointer(extra))
        x_input = Input(ctypes.c_ulong(0), ii)
        ctypes.windll.user32.SendInput(1, ctypes.pointer(x_input), ctypes.sizeof(x_input))
        
    elif click_type == "right":
        # Sağ tık DOWN
        ii = Input_I()
        ii.mi = MouseInput(0, 0, 0, 0x0008, 0, ctypes.pointer(extra))
        x_input = Input(ctypes.c_ulong(0), ii)
        ctypes.windll.user32.SendInput(1, ctypes.pointer(x_input), ctypes.sizeof(x_input))
        time.sleep(0.05)
        # Sağ tık UP
        ii.mi = MouseInput(0, 0, 0, 0x0010, 0, ctypes.pointer(extra))
        x_input = Input(ctypes.c_ulong(0), ii)
        ctypes.windll.user32.SendInput(1, ctypes.pointer(x_input), ctypes.sizeof(x_input))

# Sürücü başlatma (Varsa)
if _ClicksendMouseDriver:
    try:
        if not hasattr(_click_left, "_driver"):
            drv = _ClicksendMouseDriver()
            _click_left._driver = drv
            _click_right._driver = drv
    except: pass
# =========================================================
# ARAÇLAR: SNIPPING TOOL (DÜZELTİLMİŞ) & REGION SELECTOR
# =========================================================
class SnippingWidget(QWidget):
    signal_captured = pyqtSignal(str) 

    def __init__(self, save_path):
        super().__init__()
        # Tam ekran ve çerçevesiz
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setWindowState(Qt.WindowFullScreen)
        self.setCursor(Qt.CrossCursor)
        self.save_path = save_path
        self.start_point = None
        self.end_point = None
        
        # Ekran görüntüsünü al
        screen = QApplication.primaryScreen()
        if screen:
            self.original_pixmap = screen.grabWindow(0)
        else:
            self.original_pixmap = QPixmap(1920, 1080)
            self.original_pixmap.fill(Qt.black)

    def paintEvent(self, event):
        painter = QPainter(self)
        # 1. Ekran görüntüsünü çiz (Böylece gri ekran olmaz, ekranın kendisi görünür)
        painter.drawPixmap(0, 0, self.original_pixmap)
        
        # 2. Hafif karartma (Seçim yapılmayan yerler için)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 50)) # 50/255 şeffaflık (çok hafif karanlık)

        # 3. Seçilen alanı aydınlık (orijinal) göster
        if self.start_point and self.end_point:
            rect = QRect(self.start_point, self.end_point).normalized()
            painter.setCompositionMode(QPainter.CompositionMode_Source)
            # Seçili alanı orijinal resimden tekrar çizerek "aydınlatıyoruz"
            painter.drawPixmap(rect, self.original_pixmap, rect)
            
            # Kırmızı çerçeve çiz
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            pen = QPen(Qt.red, 2)
            painter.setPen(pen)
            painter.drawRect(rect)

    def mousePressEvent(self, event):
        self.start_point = event.pos()
        self.end_point = self.start_point
        self.update()

    def mouseMoveEvent(self, event):
        if self.start_point:
            self.end_point = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        self.end_point = event.pos()
        rect = QRect(self.start_point, self.end_point).normalized()
        
        # Çok küçük tıklamaları yoksay
        if rect.width() > 5 and rect.height() > 5:
            cropped = self.original_pixmap.copy(rect)
            cropped.save(self.save_path, "PNG")
            self.signal_captured.emit(self.save_path)
            self.close()
        else:
            # Sadece tıklandıysa kapatma, kullanıcı vazgeçmiş olabilir veya yanlış tıklamıştır
            self.start_point = None
            self.end_point = None
            self.update()

    def keyPressEvent(self, event):
        # ESC ile iptal
        if event.key() == Qt.Key_Escape:
            self.close()

class RegionSelector(QWidget):
    captured = pyqtSignal(dict)
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        total_rect = QRect()
        for screen in QApplication.screens():
            total_rect = total_rect.united(screen.geometry())
        self.setGeometry(total_rect)
        self.setCursor(Qt.CrossCursor)
        self.start_pos = None; self.end_pos = None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 80)) # Hafif gri arka plan
        if self.start_pos and self.end_pos:
            rect = QRect(self.start_pos, self.end_pos).normalized()
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            painter.fillRect(rect, Qt.transparent)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            painter.setPen(QPen(Qt.green, 2)); painter.drawRect(rect)
            
            # Koordinat yazısı
            painter.setPen(Qt.white)
            txt = f"{rect.width()}x{rect.height()}"
            painter.drawText(rect.topLeft() - QPoint(0, 5), txt)

    def mousePressEvent(self, e): self.start_pos = e.pos(); self.end_pos = self.start_pos; self.update()
    def mouseMoveEvent(self, e): 
        if self.start_pos: self.end_pos = e.pos(); self.update()
    def mouseReleaseEvent(self, e):
        self.end_pos = e.pos()
        rect = QRect(self.start_pos, self.end_pos).normalized()
        top_left = self.mapToGlobal(rect.topLeft())
        if rect.width() > 10:
            self.captured.emit({
                "left": top_left.x(), "top": top_left.y(),
                "width": rect.width(), "height": rect.height()
            })
        self.close()

# =========================================================
# 1. LOGIC (MAKRO MOTORU)
# =========================================================
class OtoTiklamaMacro:
    def __init__(self):
        self.items = {
            # order: 0 -> Önce SOL, Sonra SAĞ
            # order: 1 -> Önce SAĞ, Sonra SOL
            "obj_1": {"enabled": False, "l_count": 1, "r_count": 0, "order": 0, "icon_path": "icons/tiklama/obj_1.png", "tmpl": None},
            "obj_2": {"enabled": False, "l_count": 1, "r_count": 0, "order": 0, "icon_path": "icons/tiklama/obj_2.png", "tmpl": None},
            "obj_3": {"enabled": False, "l_count": 1, "r_count": 0, "order": 0, "icon_path": "icons/tiklama/obj_3.png", "tmpl": None},
            "obj_4": {"enabled": False, "l_count": 1, "r_count": 0, "order": 0, "icon_path": "icons/tiklama/obj_4.png", "tmpl": None},
        }
        
        self.scan_region = None 
        self.match_threshold = 0.85
        
        self._running = False
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        
        self.reload_templates()

    def update_config(self, cfg):
        with self._lock:
            self.match_threshold = cfg.get("threshold", 0.85)
            self.scan_region = cfg.get("scan_region", None)
            
            for key, val in cfg.get("items", {}).items():
                if key in self.items:
                    self.items[key]["enabled"] = val.get("enabled", False)
                    self.items[key]["l_count"] = val.get("l_count", 1)
                    self.items[key]["r_count"] = val.get("r_count", 0)
                    self.items[key]["order"]   = val.get("order", 0) # 0: Sol->Sağ, 1: Sağ->Sol
            
            if not self.scan_region:
                self.scan_region = {"top": 0, "left": 0, "width": 1920, "height": 1080}

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
                        else:
                            self.items[key]["tmpl"] = None
                    except: 
                        self.items[key]["tmpl"] = None

    def start(self):
        self.reload_templates()
        if not self.scan_region: 
             self.scan_region = {"top": 0, "left": 0, "width": 1920, "height": 1080}
             
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
                # 1. Ekran Görüntüsü Al
                scr = np.array(sct.grab(self.scan_region))
                gray_scr = cv2.cvtColor(scr, cv2.COLOR_BGRA2GRAY)
                
                found_something = False
                
                for key in active_items:
                    if self._stop_event.is_set(): break
                    
                    item = self.items[key]
                    tmpl = item["tmpl"]
                    h, w = tmpl.shape
                    
                    # 2. Eşleştirme
                    res = cv2.matchTemplate(gray_scr, tmpl, cv2.TM_CCOEFF_NORMED)
                    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
                    
                    if max_val >= self.match_threshold:
                        # 3. Koordinat Hesapla (Global)
                        local_x, local_y = max_loc
                        center_x = self.scan_region["left"] + local_x + (w // 2)
                        center_y = self.scan_region["top"] + local_y + (h // 2)
                        
                        # 4. Git ve Tıkla
                        _move_mouse(center_x, center_y)
                        time.sleep(0.1) # Mouse'un gitmesi için bekle
                        
                        # SIRALAMA MANTIĞI
                        order = item.get("order", 0)
                        
                        if order == 0: # Önce SOL, Sonra SAĞ
                            for _ in range(item["l_count"]):
                                _click_left(); time.sleep(0.05)
                            for _ in range(item["r_count"]):
                                _click_right(); time.sleep(0.05)
                        else: # Önce SAĞ, Sonra SOL
                            for _ in range(item["r_count"]):
                                _click_right(); time.sleep(0.05)
                            for _ in range(item["l_count"]):
                                _click_left(); time.sleep(0.05)

                        found_something = True
                        time.sleep(0.5) # Aynı resme spam atmaması için biraz bekle
                        break 

                if not found_something:
                    time.sleep(0.1) 
                    
            except Exception as e:
                print(f"[OTO TIK] Loop Hatası: {e}")
                time.sleep(1)

# =========================================================
# 2. GUI (AYAR PENCERESİ)
# =========================================================
class OtoTiklamaSettingsDialog(QDialog):
    def __init__(self, parent, config, macro):
        super().__init__(parent)
        self.setWindowTitle("OTO TIKLAMA AYARLARI")
        self.setModal(True)
        self.resize(600, 350) # Biraz genişlettik
        self.config = config 
        self.macro = macro
        self.capture_hotkey = False
        self.snipper = None
        self.region_sel = None
        
        main = QVBoxLayout(self)
        grid = QGridLayout()
        grid.setSpacing(10)
        main.addLayout(grid)

        # --- SATIR 0: Hotkey & Tarama Alanı ---
        grid.addWidget(QLabel("AKTIF TUŞ:"), 0, 0)
        self.txt_hotkey = QLineEdit(self.config.get("hotkey", "INSERT").upper())
        self.txt_hotkey.setReadOnly(True)
        self.btn_hotkey = QPushButton("TUŞ SEÇ")
        self.btn_hotkey.clicked.connect(self.on_hotkey_capture)
        
        hk_layout = QHBoxLayout()
        hk_layout.addWidget(self.txt_hotkey)
        hk_layout.addWidget(self.btn_hotkey)
        grid.addLayout(hk_layout, 0, 1)

        self.btn_region = QPushButton("TARAMA ALANI SEÇ")
        if self.config.get("scan_region"):
            self.btn_region.setText("ALAN SEÇİLİ ✅")
            self.btn_region.setStyleSheet("color: #00ff4c; font-weight: bold;")
        else:
             self.btn_region.setStyleSheet("color: #ff5555;")
        self.btn_region.clicked.connect(self.select_region)
        grid.addWidget(self.btn_region, 0, 2, 1, 3)

        # --- SATIR 1: Hassasiyet ---
        grid.addWidget(QLabel("HASSASİYET:"), 1, 0)
        self.spin_threshold = QDoubleSpinBox()
        self.spin_threshold.setRange(0.1, 1.0)
        self.spin_threshold.setSingleStep(0.05)
        self.spin_threshold.setValue(self.config.get("threshold", 0.85))
        grid.addWidget(self.spin_threshold, 1, 1)
        grid.addWidget(QLabel("(0.85 İdeal)"), 1, 2)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        grid.addWidget(line, 2, 0, 1, 6)

        # --- BAŞLIKLAR ---
        grid.addWidget(QLabel("<b>ÖZELLİK</b>"), 3, 0)
        grid.addWidget(QLabel("<b>DURUM</b>"), 3, 1)
        grid.addWidget(QLabel("<b>SIRALAMA</b>"), 3, 2) # YENİ SÜTUN
        grid.addWidget(QLabel("<b>SOL ADET</b>"), 3, 3)
        grid.addWidget(QLabel("<b>SAĞ ADET</b>"), 3, 4)
        grid.addWidget(QLabel("<b>GÖRSEL</b>"), 3, 5)

        self.item_rows = [
            ("obj_1", "Nesne 1"),
            ("obj_2", "Nesne 2"),
            ("obj_3", "Nesne 3"),
            ("obj_4", "Nesne 4"),
        ]
        
        self.ui_elements = {} 
        start_row = 4
        
        for i, (key, name) in enumerate(self.item_rows):
            row = start_row + i
            current_cfg = self.config.get("items", {}).get(key, {})
            
            # 1. Ad
            grid.addWidget(QLabel(name), row, 0)
            
            # 2. Checkbox
            chk = QCheckBox("Aktif")
            chk.setChecked(current_cfg.get("enabled", False))
            grid.addWidget(chk, row, 1)      
            
            # 3. Sıralama (Combo Box)
            cmb_order = QComboBox()
            cmb_order.addItem("Önce SOL, Sonra SAĞ", 0)
            cmb_order.addItem("Önce SAĞ, Sonra SOL", 1)
            
            idx = cmb_order.findData(current_cfg.get("order", 0))
            if idx >= 0: cmb_order.setCurrentIndex(idx)
            grid.addWidget(cmb_order, row, 2)

            # 4. Sol Tık Sayısı
            sb_left = QSpinBox()
            sb_left.setRange(0, 10)
            sb_left.setValue(current_cfg.get("l_count", 1))
            grid.addWidget(sb_left, row, 3)
            
            # 5. Sağ Tık Sayısı
            sb_right = QSpinBox()
            sb_right.setRange(0, 10)
            sb_right.setValue(current_cfg.get("r_count", 0))
            grid.addWidget(sb_right, row, 4)

            # 6. Görsel Seç
            vbox = QVBoxLayout()
            lbl_preview = QLabel()
            lbl_preview.setFixedSize(30, 30)
            lbl_preview.setStyleSheet("border: 1px solid gray; background-color:black;")
            
            icon_path = f"icons/tiklama/{key}.png"
            if os.path.exists(icon_path):
                pix = QPixmap(icon_path)
                lbl_preview.setPixmap(pix.scaled(30, 30, Qt.KeepAspectRatio))
            
            btn_pick = QPushButton("Seç")
            btn_pick.setFixedSize(40, 20)
            btn_pick.clicked.connect(lambda checked, k=key, l=lbl_preview: self.open_snipper(k, l))
            
            hbox_img = QHBoxLayout()
            hbox_img.addWidget(lbl_preview)
            hbox_img.addWidget(btn_pick)
            hbox_img.setContentsMargins(0,0,0,0)
            
            container = QWidget()
            container.setLayout(hbox_img)
            grid.addWidget(container, row, 5)
            
            self.ui_elements[key] = { "chk": chk, "l": sb_left, "r": sb_right, "order": cmb_order }

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        main.addWidget(btns)

    def select_region(self):
        self.hide()
        self.region_sel = RegionSelector()
        self.region_sel.captured.connect(self.on_region_selected)
        self.region_sel.show()

    def on_region_selected(self, rect_dict):
        self.config["scan_region"] = rect_dict
        self.btn_region.setText("ALAN SEÇİLİ ✅")
        self.btn_region.setStyleSheet("color: #00ff4c; font-weight: bold;")
        self.show()

    def open_snipper(self, key, label_widget):
        self.hide()
        save_path = f"icons/tiklama/{key}.png"
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
            elif key == Qt.Key_Insert: name = "INSERT"
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
            self.config["items"][key]["l_count"] = ui["l"].value()
            self.config["items"][key]["r_count"] = ui["r"].value()
            self.config["items"][key]["order"] = ui["order"].currentData() # Sıralamayı kaydet

        self.macro.update_config(self.config)
        self.macro.reload_templates()
        super().accept()

# =========================================================
# 3. WIDGET (ANA EKRAN KARTI)
# =========================================================
class OtoTiklamaWidget(QFrame):
    update_signal = pyqtSignal()

    def __init__(self, parent=None, macro_instance=None, config=None):
        super().__init__(parent)
        self.config = config or {}
        self.macro = macro_instance or OtoTiklamaMacro()
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
        h.setSpacing(6)
        
        # İkon
        icon = QLabel()
        icon.setText("🖱️")
        icon.setStyleSheet("font-size: 25px;")
        h.addWidget(icon)

        # Başlık
        lbl_title = QLabel("OTO TIKLAMA") 
        lbl_title.setObjectName("MinorHeaderLabel")
        lbl_title.setStyleSheet("color: white; font-weight: bold;")
        h.addStretch(1)
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

        # --- ALT KISIM ---
        row = QHBoxLayout()
        row.setSpacing(4)
        row.addWidget(QLabel("AKTİF TUŞ:"))
        
        self.lbl_hotkey = QLabel(self.config.get("hotkey", "INSERT"))
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
        dlg = OtoTiklamaSettingsDialog(self, self.config, self.macro)
        if dlg.exec_() == QDialog.Accepted:
            self.lbl_hotkey.setText(self.config.get("hotkey", "INSERT").upper())
            if self.listen_active:
                self.toggle_listen() 
                self.toggle_listen()

    def toggle_listen(self):
        if not keyboard:
            return QMessageBox.warning(self, "Hata", "keyboard kütüphanesi yok")

        if not self.listen_active:
            hotkey = self.config.get("hotkey", "INSERT").lower()
            try:
                self._hotkey_hook = keyboard.on_press_key(hotkey, self.on_hotkey_press, suppress=False)
                self.listen_active = True
                # *** DÜZELTME: Macro'yu burada BAŞLATMIYORUZ ***
                # Macro, on_hotkey_press içinde çağrılan self.macro.toggle() ile başlayacak.
            except Exception as e:
                print(f"[OTO TIK] Tuş hatası: {e}")
                self.listen_active = False
        else:
            if self._hotkey_hook:
                try: keyboard.unhook(self._hotkey_hook)
                except: pass
            self._hotkey_hook = None
            self.listen_active = False
            self.macro.stop() # Dinleme durunca macro'yu da durdur
        
        self._safe_update_status()

    def on_hotkey_press(self, e):
        current = time.time()
        if current - self._last_toggle_time < 0.2: return
        self._last_toggle_time = current
        
        self.macro.toggle() # <-- Makro BURADA BAŞLATILIP DURDURULACAK
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
