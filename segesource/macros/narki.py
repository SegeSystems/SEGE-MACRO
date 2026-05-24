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
import pyautogui
import json

# PyQt5
from PyQt5.QtWidgets import (
    QDialog, QGridLayout, QLabel, QComboBox, 
    QLineEdit, QPushButton, QDoubleSpinBox, 
    QDialogButtonBox, QHBoxLayout, QWidget,
    QFrame, QVBoxLayout, QSizePolicy, QMessageBox,
    QCheckBox, QGroupBox, QSpinBox, QApplication, QRubberBand
)
from PyQt5.QtGui import QPixmap, QIcon, QPainter, QPen, QColor, QBrush
from PyQt5.QtCore import Qt, QSize, pyqtSignal, QTimer, QPoint, QRect

# Opsiyonel Sürücü
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

# ---------------------------------------------------------
# SABİTLER VE AYARLAR
# ---------------------------------------------------------
DATA_DIR = "narki_data"
if not os.path.exists(DATA_DIR): os.makedirs(DATA_DIR)

# Envanter Slot Aralığı (Standart UI için genelde 50px)
SLOT_SPACING = 50 

# ---------------------------------------------------------
# YARDIMCI: ALAN SEÇİCİ (RESİM KIRPMA İÇİN)
# ---------------------------------------------------------
class SnippingOverlay(QWidget):
    def __init__(self, on_selected_callback):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setGeometry(QApplication.desktop().geometry())
        self.setCursor(Qt.CrossCursor)
        self.on_selected_callback = on_selected_callback
        self.start_pos = None
        self.current_pos = None
        self.setStyleSheet("background-color: black;")
        self.setWindowOpacity(0.3) 
        self.show()
        self.activateWindow()
        self.raise_()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.start_pos = event.pos(); self.current_pos = event.pos(); self.update()
        elif event.button() == Qt.RightButton:
            self.close()

    def mouseMoveEvent(self, event):
        if self.start_pos:
            self.current_pos = event.pos(); self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.start_pos:
            x = min(self.start_pos.x(), event.pos().x())
            y = min(self.start_pos.y(), event.pos().y())
            w = abs(self.start_pos.x() - event.pos().x())
            h = abs(self.start_pos.y() - event.pos().y())
            self.close()
            if w > 5 and h > 5:
                rect = QRect(x, y, w, h)
                self.on_selected_callback(rect)

    def paintEvent(self, event):
        if self.start_pos and self.current_pos:
            painter = QPainter(self)
            painter.setPen(QPen(QColor(0, 255, 0), 2))
            painter.setBrush(Qt.NoBrush)
            rect = QRect(self.start_pos, self.current_pos).normalized()
            painter.drawRect(rect)

# =========================================================
# 1. LOGIC (NARKI MOTORU) - START BUTONU REFERANSLI SİSTEM
# =========================================================
class NarkiMacro:
    def __init__(self):
        self.npc_coords = (0, 0)      
        self.item_count = 1           
        self.speed_click = 0.1        
        self.start_stop_delay = 0.05  
        self.loop_delay = 0.5         
        
        # OFSETLER: (START BUTONUNA GÖRE KONUMLAR)
        self.offset_stop_rel = (0, 30)   
        self.offset_item1_rel = (0, 100) 
        
        # Resimler
        self.img_dissolve = None      
        self.img_start = None         
        self.img_empty = None         
        
        self._driver = _ClicksendKeyboardDriver() if _ClicksendKeyboardDriver else None
        self._mouse = _ClicksendMouseDriver() if _ClicksendMouseDriver else None
        self._sct = mss.mss()
        self._running = False
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    def update_config(self, cfg):
        with self._lock:
            self.npc_coords = tuple(cfg.get("npc_coords", (0, 0)))
            self.item_count = int(cfg.get("item_count", 1))
            self.speed_click = float(cfg.get("speed_click", 0.1))
            self.start_stop_delay = float(cfg.get("start_stop_delay", 0.05))
            self.loop_delay = float(cfg.get("loop_delay", 0.5))
            
            self.offset_stop_rel = tuple(cfg.get("offset_stop", (0, 30)))
            self.offset_item1_rel = tuple(cfg.get("offset_item1", (0, 100)))
            
            self._load_images(cfg)

    def _load_images(self, cfg):
        def load(key):
            path = cfg.get(key)
            if path and os.path.exists(path):
                return cv2.imread(path, cv2.IMREAD_GRAYSCALE)
            return None
            
        self.img_dissolve = load("path_dissolve")
        self.img_start = load("path_start")
        self.img_empty = load("path_empty")

    @property
    def is_running(self): return self._running

    def start(self):
        if self._running: return
        
        if self.npc_coords == (0,0) or self.img_start is None:
            print("[NARKI] HATA: NPC Koordinatı veya Start Butonu resmi eksik.")
            return

        self._stop_event.clear()
        self._running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._stop_event.set()
        self._running = False

    def toggle(self):
        self.stop() if self._running else self.start()

    # --- EKRAN TARAMA VE KOORDİNAT BULMA ---
    def _find_image_on_screen(self, sct_instance, template, confidence=0.8):
        if template is None: return None
        try:
            monitor = sct_instance.monitors[1]
            scr = np.array(sct_instance.grab(monitor))
            gray = cv2.cvtColor(scr, cv2.COLOR_BGRA2GRAY)
            
            res = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            
            if max_val >= confidence:
                h, w = template.shape
                return (max_loc[0] + w // 2, max_loc[1] + h // 2)
        except Exception as e:
            print(f"[NARKI] Resim arama hatası: {e}")
        return None

    def _is_slot_empty(self, sct_instance, x, y):
        if self.img_empty is None: return False
        try:
            w, h = self.img_empty.shape[::-1]
            region = {"left": int(x - w/2), "top": int(y - h/2), "width": w, "height": h}
            
            scr = np.array(sct_instance.grab(region))
            gray = cv2.cvtColor(scr, cv2.COLOR_BGRA2GRAY)
            
            res = cv2.matchTemplate(gray, self.img_empty, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(res)
            
            return max_val > 0.85
        except: return False

    # --- MOUSE HAREKETLERİ ---
    def _click(self, x, y, right=False):
        if self._stop_event.is_set(): return
        
        # NPC tıklaması dışındaki tüm hareketleri sadece tıklama sinyali olarak gönder
        if self._mouse:
            if right: self._mouse.rightclick(0.05, int(x), int(y))
            else: self._mouse.leftclick(0.05, int(x), int(y))
        else:
            # PyAutoGUI ekranı kaydırır, sadece NPC için kullan
            if right and self.npc_coords == (x,y):
                 pyautogui.moveTo(x, y); pyautogui.click(button='right')
            elif not right:
                 # Diğer tıklamalar için (Start/Stop/Item) sadece tıklama sinyali
                 pyautogui.click(x, y, button='right' if right else 'left')
            time.sleep(0.05)


    # --- ANA DÖNGÜ ---
    def _loop(self):
        print("[NARKI] İşlem Başlıyor...")
        
        with mss.mss() as sct:
            try:
                # 1. ADIM: NPC'YE SAĞ TIKLA (EKRANI KAYDIRABİLİRİZ)
                self._click(self.npc_coords[0], self.npc_coords[1], right=True)
                time.sleep(0.5)
                
                # 2. ADIM: "DISSASSEMBLING" BUL VE TIKLA
                dissolve_pos = None
                for _ in range(10):
                    if self._stop_event.is_set(): return
                    dissolve_pos = self._find_image_on_screen(sct, self.img_dissolve)
                    if dissolve_pos: break
                    time.sleep(0.3)
                
                if not dissolve_pos:
                    print("[NARKI] 'Dissassembling' bulunamadı!")
                    self._running = False; return
                    
                self._click(dissolve_pos[0], dissolve_pos[1])
                time.sleep(0.5)
                
                # 3. ADIM: İTEM KIRMA DÖNGÜSÜ BAŞLANGICI
                for i in range(self.item_count):
                    if self._stop_event.is_set(): break
                    
                    # A. START BUTONUNU BUL (REFERANS) - Her İtem Basmada Yeniden
                    start_pos = None
                    for _ in range(5):
                        if self._stop_event.is_set(): return
                        start_pos = self._find_image_on_screen(sct, self.img_start)
                        if start_pos: break
                        time.sleep(0.1)
                        
                    if not start_pos:
                        print("[NARKI] 'Start' butonu kayboldu! İşlem durduruluyor.")
                        break # İşlem durdurulmalı
                    
                    # --- DİNAMİK REFERANS HESAPLAMA (START'A GÖRE) ---
                    ref_x, ref_y = start_pos
                    
                    # B. Item 1 Konumu = Start Konumu + Offset_Item1_Rel
                    item1_x = ref_x + self.offset_item1_rel[0]
                    item1_y = ref_y + self.offset_item1_rel[1]
                    
                    # C. Stop Butonu Konumu = Start Konumu + Offset_Stop_Rel
                    stop_x = ref_x + self.offset_stop_rel[0]
                    stop_y = ref_y + self.offset_stop_rel[1]
                    
                    # D. İtem koordinatını hesapla (Grid: 7 Sütun)
                    col = i % 7
                    row = i // 7
                    
                    item_x = item1_x + (col * SLOT_SPACING)
                    item_y = item1_y + (row * SLOT_SPACING)
                    
                    # E. Boş slot kontrolü
                    if self._is_slot_empty(sct, item_x, item_y):
                        continue
                    
                    # F. İteme Sağ Tıkla
                    self._click(item_x, item_y, right=True)
                    time.sleep(0.15)
                    
                    # G. Start'a Bas
                    self._click(ref_x, ref_y)
                    
                    # H. Stop'a Bas
                    if self.start_stop_delay > 0:
                        time.sleep(self.start_stop_delay)
                    self._click(stop_x, stop_y)
                    
                    time.sleep(self.loop_delay)

                print("[NARKI] İşlem Tamamlandı.")

            except Exception as e:
                print(f"[NARKI] Kritik Hata: {e}")
            finally:
                self._running = False


# =========================================================
# 2. GUI (AYAR PENCERESİ)
# =========================================================
class NarkiSettingsDialog(QDialog):
    def __init__(self, parent, config, macro):
        super().__init__(parent)
        self.setWindowTitle("NARKI (ITEM KIRDIRMA) AYARLARI")
        self.setModal(True)
        self.resize(600, 550) # Gereksiz alanları kaldırdım
        self.config = config
        self.macro = macro
        
        self.overlay = None
        self.capture_mode = None # 'npc', 'calib_start', 'calib_item', 'calib_stop'
        
        self.hotkey_capture_active = False 
        self.calib_start_pos = None # START butonu F'ye basıldığında kaydedilen pozisyon
        self.temp_config = self.config.copy()
        
        layout = QVBoxLayout(self)
        
        # --- 0. BAŞLATMA TUŞU ---
        grp_hotkey = QGroupBox("0. Başlatma Tuşu")
        gh = QHBoxLayout(grp_hotkey)
        self.txt_hotkey = QLineEdit(self.temp_config.get("hotkey", "F10").upper())
        self.txt_hotkey.setReadOnly(True)
        btn_hotkey = QPushButton("TUŞU DEĞİŞTİR")
        btn_hotkey.clicked.connect(self.start_hotkey_capture)
        gh.addWidget(QLabel("Makro Tuşu:")); gh.addWidget(self.txt_hotkey); gh.addWidget(btn_hotkey)
        layout.addWidget(grp_hotkey)
        
        # --- 1. KOORDİNAT VE KALİBRASYON ---
        grp_calib = QGroupBox("1. Konumlandırma ve Kalibrasyon")
        gl = QGridLayout(grp_calib)
        
        # NPC Koordinatı
        self.lbl_npc = QLineEdit(str(self.temp_config.get("npc_coords", (0,0))))
        self.lbl_npc.setReadOnly(True)
        btn_npc = QPushButton("NPC YERİ SEÇ (F)")
        btn_npc.clicked.connect(self.capture_npc)
        gl.addWidget(QLabel("NPC Koordinatı:"), 0, 0); gl.addWidget(self.lbl_npc, 0, 1); gl.addWidget(btn_npc, 0, 2)
        
        # OFSET KALİBRASYONU BAŞLAT
        btn_calib = QPushButton("OFSET KALİBRASYONU BAŞLAT (START/STOP/ITEM1)")
        btn_calib.setStyleSheet("background-color: #d500f9; color: white; font-weight: bold; height: 30px;")
        btn_calib.clicked.connect(self.start_calibration_wizard)
        gl.addWidget(btn_calib, 1, 0, 1, 3)
        
        self.lbl_calib_status = QLabel("Durum: Bekleniyor...")
        self.lbl_calib_status.setStyleSheet("color: yellow;")
        gl.addWidget(self.lbl_calib_status, 2, 0, 1, 3)
        layout.addWidget(grp_calib)
        
        # --- 2. GÖRSEL TANIMLAMA ---
        grp_img = QGroupBox("2. Görseller (Kırp)")
        il = QGridLayout(grp_img)
        
        btns = [
            ("path_dissolve", "1. Dissassembling Yazısı", "KIRP"),
            ("path_start",    "2. Start Butonu", "KIRP"),
            ("path_empty",    "3. Boş Envanter Slotu", "KIRP")
        ]
        
        self.img_labels = {}
        for i, (key, label, btn_text) in enumerate(btns):
            il.addWidget(QLabel(label), i, 0)
            status_lbl = QLabel("✅" if self.temp_config.get(key) and os.path.exists(self.temp_config.get(key)) else "❌")
            self.img_labels[key] = status_lbl
            il.addWidget(status_lbl, i, 1)
            btn = QPushButton(btn_text)
            btn.clicked.connect(lambda _, k=key: self.capture_image(k))
            il.addWidget(btn, i, 2)
        layout.addWidget(grp_img)
        
        # --- 3. AYARLAR ---
        grp_set = QGroupBox("3. Ayarlar")
        sl = QGridLayout(grp_set)
        
        sl.addWidget(QLabel("Kırılacak İtem Sayısı:"), 0, 0)
        self.sp_count = QSpinBox(); self.sp_count.setRange(1, 28); self.sp_count.setValue(int(self.temp_config.get("item_count", 1)))
        sl.addWidget(self.sp_count, 0, 1)
        
        sl.addWidget(QLabel("Tıklama Hızı (sn):"), 1, 0)
        self.sp_click = QDoubleSpinBox(); self.sp_click.setRange(0.01, 2.0); self.sp_click.setValue(float(self.temp_config.get("speed_click", 0.1)))
        sl.addWidget(self.sp_click, 1, 1)
        
        sl.addWidget(QLabel("Start-Stop Arası (Serilik):"), 2, 0)
        self.sp_ss = QDoubleSpinBox(); self.sp_ss.setRange(0.00, 2.0); self.sp_ss.setValue(float(self.temp_config.get("start_stop_delay", 0.05)))
        sl.addWidget(self.sp_ss, 2, 1)
        
        sl.addWidget(QLabel("İtem Geçiş Gecikmesi:"), 3, 0)
        self.sp_loop = QDoubleSpinBox(); self.sp_loop.setRange(0.1, 5.0); self.sp_loop.setValue(float(self.temp_config.get("loop_delay", 0.5)))
        sl.addWidget(self.sp_loop, 3, 1)
        
        layout.addWidget(grp_set)
        
        # --- BUTONLAR ---
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        layout.addWidget(bb)
        
        self.timer = QTimer(self); self.timer.timeout.connect(self.check_f_key)

    # --- HOTKEY YAKALAMA ---
    def start_hotkey_capture(self):
        self.hotkey_capture_active = True
        self.txt_hotkey.setText("TUŞA BASIN...")

    def keyPressEvent(self, event):
        if self.hotkey_capture_active:
            key = event.key()
            name = None
            if key == Qt.Key_Escape: name = "ESC"
            elif key == Qt.Key_Tab: name = "TAB"
            elif key == Qt.Key_CapsLock: name = "CAPS LOCK"
            elif key == Qt.Key_Shift: name = "SHIFT"
            elif key == Qt.Key_Control: name = "CTRL"
            elif key == Qt.Key_Alt: name = "ALT"
            elif Qt.Key_F1 <= key <= Qt.Key_F12: name = f"F{key - Qt.Key_F1 + 1}"
            else:
                text = event.text()
                if text: name = text.upper()
            
            if name:
                self.txt_hotkey.setText(name)
                self.hotkey_capture_active = False
            return
        super().keyPressEvent(event)

    # --- KOORDİNAT YAKALAMA / KALİBRASYON ---
    def capture_npc(self):
        self.hide(); time.sleep(0.2); self.capture_mode = 'npc'; self.timer.start(50)
        
    def start_calibration_wizard(self):
        self.hide(); time.sleep(0.2)
        QMessageBox.information(None, "Adım 1/3", "Mouse'u 'START' butonunun tam ortasına getirin ve 'F' tuşuna basın.")
        self.capture_mode = 'calib_start'
        self.timer.start(50)

    def check_f_key(self):
        if keyboard and keyboard.is_pressed('f'):
            x, y = pyautogui.position()
            
            if self.capture_mode == 'npc':
                self.temp_config["npc_coords"] = (x, y)
                self.lbl_npc.setText(f"{x}, {y}")
                self.finish_capture()
                
            elif self.capture_mode == 'calib_start':
                self.calib_start_pos = (x, y)
                self.timer.stop(); time.sleep(0.3)
                QMessageBox.information(None, "Adım 2/3", "Şimdi Mouse'u 'STOP' butonunun üzerine getirin ve 'F' tuşuna basın.")
                self.capture_mode = 'calib_stop'
                self.timer.start(50)
                
            elif self.capture_mode == 'calib_stop':
                # Stop'un Start'a göre ofseti
                dx = x - self.calib_start_pos[0]
                dy = y - self.calib_start_pos[1]
                self.temp_config["offset_stop"] = (dx, dy)
                self.lbl_calib_status.setText(f"Adım 3/3: Stop Farkı: {dx},{dy}")
                
                self.timer.stop(); time.sleep(0.3)
                QMessageBox.information(None, "Adım 3/3", "Son olarak Envanterdeki İLK (Sol Üst) İtemin üzerine gelin ve 'F' tuşuna basın.")
                self.capture_mode = 'calib_item'
                self.timer.start(50)
                
            elif self.capture_mode == 'calib_item':
                # Item 1'in Start'a göre ofseti
                dx_start = x - self.calib_start_pos[0]
                dy_start = y - self.calib_start_pos[1]
                self.temp_config["offset_item1"] = (dx_start, dy_start)
                
                self.finish_capture()
                self.lbl_calib_status.setText(f"Tamamlandı! Item 1 Ofset: {dx_start},{dy_start}")
                self.lbl_calib_status.setStyleSheet("color: #00ff00; font-weight: bold;")

        elif keyboard and keyboard.is_pressed('esc'):
            self.finish_capture()

    def finish_capture(self):
        self.timer.stop()
        self.capture_mode = None
        self.show()
        self.activateWindow()

    def capture_image(self, key):
        self.hide(); time.sleep(0.2)
        self.overlay = SnippingOverlay(lambda rect: self.save_image(rect, key))

    def save_image(self, rect, key):
        self.overlay = None
        if rect:
            with mss.mss() as sct:
                monitor = {"left": rect.x(), "top": rect.y(), "width": rect.width(), "height": rect.height()}
                img = np.array(sct.grab(monitor))
                path = f"{DATA_DIR}/{key}.png"
                cv2.imwrite(path, cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY))
                self.temp_config[key] = path
                self.img_labels[key].setText("✅")
        self.show()

    def accept(self):
        self.temp_config["hotkey"] = self.txt_hotkey.text()
        self.temp_config["item_count"] = self.sp_count.value()
        self.temp_config["speed_click"] = self.sp_click.value()
        self.temp_config["start_stop_delay"] = self.sp_ss.value()
        self.temp_config["loop_delay"] = self.sp_loop.value()
        
        self.config.update(self.temp_config)
        self.macro.update_config(self.config)
        super().accept()

# =========================================================
# 3. WIDGET (ANA EKRAN KARTI)
# =========================================================
class NarkiWidget(QFrame):
    update_signal = pyqtSignal()

    def __init__(self, parent=None, macro_instance=None, config=None):
        super().__init__(parent)
        self.macro = macro_instance or NarkiMacro()
        self.config = config or {}
        self.macro.update_config(self.config)
        self.listen_active = False 
        self._hotkey_handles = []
        self.timer = QTimer(self); self.timer.timeout.connect(self._check_status); self.timer.start(500)
        
        self.update_signal.connect(self._safe_update_status)
        self.setup_ui()
        self._safe_update_status()

    def setup_ui(self):
        self.setFrameShape(QFrame.Box); self.setMaximumWidth(260)
        self.setStyleSheet("QFrame { background-color: #101010; border: 1px solid #444444; border-radius: 4px; }")
        v = QVBoxLayout(self); v.setContentsMargins(6,6,6,6); v.setSpacing(4)

        h = QHBoxLayout(); h.setSpacing(6)
        icon = QLabel("🔨"); icon.setStyleSheet("font-size:20px; border:none;")
        h.addWidget(icon); h.addStretch()
        h.addWidget(QLabel("NARKI (ITEM KIRDIRMA)", objectName="MinorHeaderLabel"))
        v.addLayout(h)

        self.btn_run = QPushButton("TUŞ DİNLEMEYİ BAŞLAT")
        self.btn_run.setObjectName("ThreeFiveListenButton")
        self.btn_run.clicked.connect(self.toggle_listen)
        v.addWidget(self.btn_run)

        self.lbl_status = QLabel("DURUM: PASİF")
        self.lbl_status.setObjectName("MinorStatusLabel")
        v.addWidget(self.lbl_status)

        row = QHBoxLayout()
        row.setSpacing(4)
        row.addWidget(QLabel("AKTIF TUŞ:"))
        self.lbl_hotkey = QLabel(self.config.get("hotkey", "F10").upper())
        self.lbl_hotkey.setObjectName("HotkeyLabel")
        self.lbl_hotkey.setAlignment(Qt.AlignCenter)
        row.addWidget(self.lbl_hotkey)
        
        btn_set = QPushButton("⚙ AYARLAR")
        btn_set.setObjectName("MinorSettingsButton")
        btn_set.clicked.connect(self.open_settings)
        row.addWidget(btn_set)
        v.addLayout(row)

    def open_settings(self):
        dlg = NarkiSettingsDialog(self, self.config, self.macro)
        if dlg.exec_():
            self.config.update(dlg.config)
            self.macro.update_config(self.config)
            self.lbl_hotkey.setText(self.config["hotkey"])

    def toggle_listen(self):
        if not keyboard: return QMessageBox.warning(self, "Hata", "keyboard kütüphanesi yok")

        if not self.listen_active:
            k = self.config.get("hotkey", "F10").lower()
            try:
                self._hotkey_handles = []
                self._hotkey_handles.append(keyboard.on_press_key(k, lambda e: self.run_macro(), suppress=False))
                self.listen_active = True
            except Exception as e: 
                print(f"[NARKI] Hook hatası: {e}"); self.listen_active = False
        else:
            for h in self._hotkey_handles: 
                try: keyboard.unhook(h)
                except: pass
            self._hotkey_handles = []
            self.listen_active = False
            self.macro.stop()
        
        self._safe_update_status()

    def run_macro(self):
        self.macro.start()
        self.update_signal.emit()
        
    def _check_status(self):
        if self.macro.is_running != (self.lbl_status.text() == "DURUM: ÇALIŞIYOR"):
            self.update_signal.emit()

    def apply_status_style(self, color: str):
        self.lbl_status.setStyleSheet(f"color: {color}; font-weight: bold;")

    def _safe_update_status(self):
        if not self.listen_active:
            self.lbl_status.setText("DURUM: PASİF")
            self.btn_run.setText("TUŞ DİNLEMEYİ BAŞLAT")
            act = False
            self.apply_status_style("#ff5555")
        else:
            if self.macro.is_running:
                self.lbl_status.setText("DURUM: ÇALIŞIYOR")
                self.apply_status_style("#00ff4c")
            else:
                self.lbl_status.setText("DURUM: BEKLİYOR")
                self.apply_status_style("#ffff55")
            
            self.btn_run.setText("DURDUR")
            act = True
        
        self.btn_run.setProperty("active", act)
        self.btn_run.style().unpolish(self.btn_run)
        self.btn_run.style().polish(self.btn_run)
