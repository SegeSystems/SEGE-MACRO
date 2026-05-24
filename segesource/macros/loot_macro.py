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
    QCheckBox, QGroupBox, QSpinBox, QApplication, QFormLayout
)
from PyQt5.QtGui import QPixmap, QIcon, QPainter, QPen, QColor, QBrush
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QRect, QPoint

# Sürücüler
try:
    from clicksend import KeyboardDriver as _ClicksendKeyboardDriver
    from clicksend import MouseDriver as _ClicksendMouseDriver
    HAS_CLICKSEND = True
except ImportError:
    _ClicksendKeyboardDriver = None
    _ClicksendMouseDriver = None
    HAS_CLICKSEND = False

try:
    import keyboard
except ImportError:
    keyboard = None

DATA_DIR = os.path.abspath("farm_data")
if not os.path.exists(DATA_DIR): os.makedirs(DATA_DIR)

# --- SABİTLER ---
DROP_OFFSETS = [(80, 0), (-80, 0), (0, 80), (0, -80)]
DEFAULT_CONFIDENCE = 0.85 # Varsayılan hassasiyet
EMPTY_SLOT_CONFIDENCE = 0.80 

# --- YARDIMCI: ALAN SEÇİCİ ---
class SnippingOverlay(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setWindowState(Qt.WindowFullScreen)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.CrossCursor)
        self.start_pos = None
        self.current_pos = None
        self.selected_rect = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.start_pos = event.pos()
            self.current_pos = event.pos()
            self.update()
        elif event.button() == Qt.RightButton:
            self.reject()

    def mouseMoveEvent(self, event):
        if self.start_pos:
            self.current_pos = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.start_pos:
            x = min(self.start_pos.x(), event.pos().x())
            y = min(self.start_pos.y(), event.pos().y())
            w = abs(self.start_pos.x() - event.pos().x())
            h = abs(self.start_pos.y() - event.pos().y())
            if w > 5 and h > 5:
                self.selected_rect = QRect(x, y, w, h)
                self.accept()
            else:
                self.start_pos = None
                self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 100))
        if self.start_pos and self.current_pos:
            x = min(self.start_pos.x(), self.current_pos.x())
            y = min(self.start_pos.y(), self.current_pos.y())
            w = abs(self.start_pos.x() - self.current_pos.x())
            h = abs(self.start_pos.y() - self.current_pos.y())
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            painter.fillRect(x, y, w, h, Qt.transparent)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            pen = QPen(QColor(0, 255, 0), 2)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(x, y, w, h)

# =========================================================
# 1. LOGIC (OTODROP MOTORU)
# =========================================================
class AutoDropMacro:
    def __init__(self):
        self.loot_center = (0, 0)
        self.loot_area = None
        self.loot_layout = "4'lü Dikey"
        self.loot_offset = 50
        self.loot_mode = "Manuel (Tuşla)"
        self.loop_delay = 15.0
        self.click_delay = 0.15
        
        # YENİ: Hassasiyet Ayarı
        self.confidence_loot = DEFAULT_CONFIDENCE

        self.scan_offset = 80
        
        self.img_loot = None  # Coin Resmi
        self.img_empty = None # Boş Slot Resmi
        
        self._driver = _ClicksendKeyboardDriver() if _ClicksendKeyboardDriver else None
        self._mouse = _ClicksendMouseDriver() if _ClicksendMouseDriver else None
        self._sct = mss.mss()
        
        self._running = False
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        
        self.is_auto_active = False
        self.is_processing = False
        self._pending_config = None 

    def update_config(self, cfg):
        with self._lock:
            self._pending_config = cfg.copy()

    def _apply_pending_config(self):
        config_to_load = None
        with self._lock:
            if self._pending_config:
                config_to_load = self._pending_config
                self._pending_config = None
        
        if config_to_load:
            self.loot_center = tuple(config_to_load.get("loot_center", (0, 0)))
            area = config_to_load.get("loot_area")
            self.loot_area = tuple(area) if area else None
            self.loot_layout = config_to_load.get("loot_layout", "4'lü Dikey")
            self.loot_offset = int(config_to_load.get("loot_offset", 50))
            self.loot_mode = config_to_load.get("mode", "Manuel (Tuşla)")
            self.loop_delay = float(config_to_load.get("loop_delay", 15.0))
            self.click_delay = float(config_to_load.get("click_delay", 0.15))
            
            # YENİ: Config'den hassasiyeti oku
            self.confidence_loot = float(config_to_load.get("confidence_loot", DEFAULT_CONFIDENCE))

            self.scan_offset = int(config_to_load.get("scan_offset", 80))
            
            # Coin Resmi
            path_loot = config_to_load.get("path_loot")
            if path_loot and os.path.exists(path_loot):
                try: self.img_loot = cv2.imread(path_loot, cv2.IMREAD_GRAYSCALE)
                except: pass
            
            # Boş Slot Resmi
            path_empty = config_to_load.get("path_empty")
            if path_empty and os.path.exists(path_empty):
                try: self.img_empty = cv2.imread(path_empty, cv2.IMREAD_GRAYSCALE)
                except: pass
            
    @property
    def is_running(self): return self._running

    def start(self):
        if self._running: return
        self._stop_event.clear()
        self._running = True
        self.is_auto_active = False 
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._stop_event.set()
        self._running = False
        self.is_auto_active = False

    def toggle_auto(self):
        self.is_auto_active = not self.is_auto_active
        return self.is_auto_active

    def run_manual_once(self):
        if self.is_processing: return 
        threading.Thread(target=self._manual_worker, daemon=True).start()

    def _manual_worker(self):
        self._apply_pending_config()
        self.is_processing = True
        try:
            self._sequence_open_and_collect()
        finally:
            self.is_processing = False

    def _loop(self):
        print(f"[LOOT] Döngü Başladı (Beklemede). Hassasiyet: {self.confidence_loot}")
        last_auto_time = 0
        
        while not self._stop_event.is_set():
            self._apply_pending_config()

            # 1. PASİF TARAMA
            if not self.is_processing:
                found_pos = self._find_image_coin()
                if found_pos:
                    print("[LOOT] Coin bulundu, toplanıyor...")
                    self.is_processing = True
                    try:
                        self._action_collect_loot(found_pos)
                    finally:
                        self.is_processing = False
                    time.sleep(0.5) 
                    continue

            # 2. OTOMATİK MOD
            if self.loot_mode == "Otomatik (Süreli)" and self.is_auto_active:
                now = time.time()
                if now - last_auto_time >= self.loop_delay:
                    if not self.is_processing:
                        print("[LOOT] Otomatik süre doldu, işlem başlıyor...")
                        self.is_processing = True
                        try:
                            self._sequence_open_and_collect()
                        finally:
                            self.is_processing = False
                        last_auto_time = now
            
            time.sleep(0.1)
        
        self._running = False
        print("[LOOT] Döngü Bitti.")

    # --- İŞLEM ZİNCİRİ ---
    def _sequence_open_and_collect(self):
        if self.loot_center == (0,0): return

        cx, cy = self.loot_center
        found_pos = self._find_image_coin()

        if not found_pos:
            # Resim yoksa kutu açmayı dene
            # ARTIK SABİT DEĞİL, AYARLANABİLİR LİSTE KULLANIYORUZ
            dist = self.scan_offset
            
            # İsteğin üzerine (0,0) yani merkez de eklendi:
            offsets_to_try = [
                (0, 0),       # <-- MERKEZ
                (dist, 0),    # Sağ
                (-dist, 0),   # Sol
                (0, dist),    # Alt
                (0, -dist)    # Üst
            ]

            for dx, dy in offsets_to_try:
                tx, ty = cx + dx, cy + dy
                self._move_cursor(tx, ty)
                time.sleep(0.02)
                self._mouse_click(tx, ty, right=True)
                
                time.sleep(0.15) 
                
                found_pos = self._find_image_coin()
                if found_pos:
                    break 
        
        if found_pos:
            self._action_collect_loot(found_pos)

    # --- TOPLAMA FONKSİYONU ---
    def _action_collect_loot(self, found_pos):
        if not found_pos: return

        # İlk slotun (Coin'in olduğu yer) konumunu kaydediyoruz.
        top_slot_x = found_pos[0]
        top_slot_y = found_pos[1]

        try:
            # 1. Coin'in kendisine tıkla
            self._move_cursor(top_slot_x, top_slot_y)
            time.sleep(0.05)
            self._mouse_click(top_slot_x, top_slot_y) 
            time.sleep(self.click_delay)

            # 2. Diğer slotları kontrol ederek topla
            if self.loot_layout == "4'lü Dikey":
                start_x = top_slot_x
                start_y = top_slot_y + 40 
                
                for i in range(4):
                    tx, ty = start_x, start_y + (i * self.loot_offset)
                    
                    # Pencere Kontrolü
                    if not self._is_area_dark(top_slot_x, top_slot_y):
                        print("[LOOT] Zemin algılandı (Pencere kapandı). DURDURULDU.")
                        break
                    
                    # Slot Boş mu Kontrolü
                    if self._is_slot_empty(tx, ty):
                        print(f"[LOOT] Slot {i+1} boş, toplama BİTTİ.")
                        break

                    self._move_cursor(tx, ty)
                    time.sleep(0.02)
                    self._mouse_click(tx, ty) 
                    time.sleep(self.click_delay)
                    
            elif self.loot_layout == "6'lı (2x3)":
                start_x = top_slot_x - 50
                start_y = top_slot_y + 40
                
                stop_signal = False
                for row in range(2):
                    if stop_signal: break
                    for col in range(3):
                        tx = start_x + (col * 50) 
                        ty = start_y + (row * 50)

                        if not self._is_area_dark(top_slot_x, top_slot_y):
                            stop_signal = True; break
                        
                        if self._is_slot_empty(tx, ty):
                            stop_signal = True; break

                        self._move_cursor(tx, ty)
                        time.sleep(0.02)
                        self._mouse_click(tx, ty) 
                        time.sleep(self.click_delay)

            if self._driver: self._driver.tusbas(0x01, 0.1)
            else: pyautogui.press('esc')
            
        except Exception as e:
            print(f"[LOOT] Toplama hatası: {e}")

    def _move_cursor(self, x, y):
        try: pyautogui.moveTo(x, y)
        except: pass

    # --- YENİ: KARANLIK ALAN TESTİ (Pencere Kontrolü İçin) ---
    def _is_area_dark(self, x, y):
        try:
            with mss.mss() as sct:
                mon = {"left": int(x)-5, "top": int(y)-5, "width": 10, "height": 10}
                scr = np.array(sct.grab(mon))
                gray = cv2.cvtColor(scr, cv2.COLOR_BGRA2GRAY)
                mean_val = np.mean(gray)
                
                # EŞİK DEĞERİ: 60
                if mean_val < 60:
                    return True # Karanlık (Pencere Açık)
                else:
                    return False # Aydınlık (Zemin/Çimen)
        except:
            return True 
        
    def _is_slot_empty(self, x, y):
        if self.img_empty is None: return False 

        try:
            h, w = self.img_empty.shape
            top = int(y - h/2)
            left = int(x - w/2)
            
            with mss.mss() as sct:
                mon = {"left": left, "top": top, "width": w, "height": h}
                scr = np.array(sct.grab(mon))
                gray = cv2.cvtColor(scr, cv2.COLOR_BGRA2GRAY)
                
                res = cv2.matchTemplate(gray, self.img_empty, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(res)
                
                if max_val > EMPTY_SLOT_CONFIDENCE:
                    return True # Evet boş
        except: pass
        return False 

    def _find_image_coin(self):
        if self.loot_area is None or self.img_loot is None: return None
        try:
            with mss.mss() as sct:
                mon = {"left": self.loot_area[0], "top": self.loot_area[1], "width": self.loot_area[2], "height": self.loot_area[3]}
                scr = np.array(sct.grab(mon))
                gray = cv2.cvtColor(scr, cv2.COLOR_BGRA2GRAY)
                res = cv2.matchTemplate(gray, self.img_loot, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(res)
                
                # DEĞİŞTİRİLEN KISIM: Ayarlanabilir hassasiyet
                if max_val > self.confidence_loot:
                    h, w = self.img_loot.shape
                    return (self.loot_area[0] + max_loc[0] + w//2, self.loot_area[1] + max_loc[1] + h//2)
        except: pass
        return None

    def _mouse_click(self, x, y, right=False):
        if self._mouse:
            if right: self._mouse.rightclick(0.05, int(x), int(y))
            else: self._mouse.leftclick(0.05, int(x), int(y))
        else:
            pyautogui.click(x, y, button='right' if right else 'left')

# =========================================================
# 2. GUI (AYAR PENCERESİ)
# =========================================================
class AutoDropSettingsDialog(QDialog):
    def __init__(self, parent, config, macro):
        super().__init__(parent)
        self.setWindowTitle("AUTO LOOT (DROP) AYARLARI")
        self.resize(600, 650)
        self.config = config
        self.macro = macro
        self.capture_hotkey = False
        self.capture_mode = None
        
        self.timer = QTimer(self); self.timer.timeout.connect(self.check_f_key)
        self.temp_config = self.config.copy()
        
        layout = QVBoxLayout(self)
        
        # 1. Ayarlar
        grp_set = QGroupBox("1. Genel Ayarlar")
        sl = QGridLayout(grp_set)
        
        sl.addWidget(QLabel("Tetikleme Tuşu:"), 0, 0)
        self.txt_hotkey = QLineEdit(self.config.get("hotkey", "X")); self.txt_hotkey.setReadOnly(True)
        btn_hk = QPushButton("SEÇ"); btn_hk.clicked.connect(self.start_hotkey_capture)
        hk_lay = QHBoxLayout(); hk_lay.addWidget(self.txt_hotkey); hk_lay.addWidget(btn_hk)
        sl.addLayout(hk_lay, 0, 1)
        
        sl.addWidget(QLabel("Mod:"), 1, 0)
        self.cmb_mode = QComboBox(); self.cmb_mode.addItems(["Manuel (Tuşla)", "Otomatik (Süreli)"])
        self.cmb_mode.setCurrentText(self.temp_config.get("mode", "Manuel (Tuşla)"))
        sl.addWidget(self.cmb_mode, 1, 1)
        
        sl.addWidget(QLabel("Oto Süre (sn):"), 2, 0)
        self.sp_loop = QDoubleSpinBox(); self.sp_loop.setRange(1.0, 300.0); self.sp_loop.setValue(float(self.temp_config.get("loop_delay", 15.0)))
        sl.addWidget(self.sp_loop, 2, 1)
        
        layout.addWidget(grp_set)

        # 2. Konumlandırma
        grp_area = QGroupBox("2. Konumlandırma")
        ga = QGridLayout(grp_area)
        
        self.lbl_center = QLineEdit(str(self.temp_config.get("loot_center", (0,0)))); self.lbl_center.setReadOnly(True)
        btn_center = QPushButton("MERKEZ SEÇ (F)")
        btn_center.clicked.connect(lambda: self.capture_point("loot_center"))
        ga.addWidget(QLabel("Loot Penceresi Merkezi:"), 0, 0); ga.addWidget(self.lbl_center, 0, 1); ga.addWidget(btn_center, 0, 2)

        self.lbl_loot_area = QLineEdit(str(self.temp_config.get("loot_area", "Yok"))); self.lbl_loot_area.setReadOnly(True)
        btn_loot_area = QPushButton("TARAMA ALANI ÇİZ")
        btn_loot_area.clicked.connect(self.exec_select_area)
        ga.addWidget(QLabel("Tarama Alanı (Tüm Pencere):"), 1, 0); ga.addWidget(self.lbl_loot_area, 1, 1); ga.addWidget(btn_loot_area, 1, 2)
        
        layout.addWidget(grp_area)

        # 3. Görsel
        grp_img = QGroupBox("3. Görseller")
        gi = QGridLayout(grp_img)
        
        # COIN Resmi
        path_c = self.temp_config.get("path_loot")
        exists_c = path_c and os.path.exists(path_c)
        self.lbl_img_status = QLabel("✅" if exists_c else "❌")
        btn_img = QPushButton("COIN/PARA RESMİ KIRP")
        btn_img.clicked.connect(lambda: self.exec_crop_image("coin"))
        gi.addWidget(QLabel("Coin (Ana Resim):"), 0, 0); gi.addWidget(self.lbl_img_status, 0, 1); gi.addWidget(btn_img, 0, 2)

        # BOŞ SLOT Resmi
        path_e = self.temp_config.get("path_empty")
        exists_e = path_e and os.path.exists(path_e)
        self.lbl_empty_status = QLabel("✅" if exists_e else "❌")
        btn_empty = QPushButton("BOŞ SLOT RESMİ KIRP")
        btn_empty.clicked.connect(lambda: self.exec_crop_image("empty"))
        gi.addWidget(QLabel("Boş Slot (Referans):"), 1, 0); gi.addWidget(self.lbl_empty_status, 1, 1); gi.addWidget(btn_empty, 1, 2)
        
        layout.addWidget(grp_img)
        
        # 4. Detaylar
        grp_det = QGroupBox("4. Detaylar")
        gd = QGridLayout(grp_det)
        self.cmb_layout = QComboBox(); self.cmb_layout.addItems(["4'lü Dikey", "6'lı (2x3)"])
        self.cmb_layout.setCurrentText(self.temp_config.get("loot_layout", "4'lü Dikey"))
        gd.addWidget(QLabel("Kutu Tipi:"), 0, 0); gd.addWidget(self.cmb_layout, 0, 1)
        
        self.sp_offset = QSpinBox(); self.sp_offset.setRange(20, 100); self.sp_offset.setValue(int(self.temp_config.get("loot_offset", 50)))
        gd.addWidget(QLabel("Slot Aralığı (px):"), 1, 0); gd.addWidget(self.sp_offset, 1, 1)

        self.sp_click = QDoubleSpinBox(); self.sp_click.setRange(0.01, 1.0); self.sp_click.setValue(float(self.temp_config.get("click_delay", 0.15)))
        gd.addWidget(QLabel("Tıklama Hızı:"), 2, 0); gd.addWidget(self.sp_click, 2, 1)

        # Mevcut Hassasiyet Ayarı
        self.sp_confidence = QDoubleSpinBox()
        self.sp_confidence.setRange(0.10, 1.00) 
        self.sp_confidence.setSingleStep(0.05)    
        self.sp_confidence.setValue(float(self.temp_config.get("confidence_loot", DEFAULT_CONFIDENCE)))
        gd.addWidget(QLabel("Resim Hassasiyeti (0-1):"), 3, 0)
        gd.addWidget(self.sp_confidence, 3, 1)

        # --- YENİ EKLENEN: Tarama Genişliği Ayarı ---
        self.sp_scan_offset = QSpinBox()
        self.sp_scan_offset.setRange(0, 300) # 0 ile 300 px arası
        self.sp_scan_offset.setValue(int(self.temp_config.get("scan_offset", 80)))
        gd.addWidget(QLabel("Tarama Genişliği (px):"), 4, 0) 
        gd.addWidget(self.sp_scan_offset, 4, 1)
        # --------------------------------------------
        
        layout.addWidget(grp_det)
        
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.save_and_accept); btns.rejected.connect(self.reject)
        layout.addWidget(btns)
        
    def start_hotkey_capture(self):
        self.capture_hotkey = True; self.txt_hotkey.setText("BAS...")
    
    def keyPressEvent(self, e):
        if self.capture_hotkey:
            k = e.text().upper() if e.text() else "UNKNOWN"
            if e.key() == Qt.Key_F1: k = "F1"
            elif e.key() == Qt.Key_CapsLock: k = "CAPS LOCK"
            self.txt_hotkey.setText(k); self.capture_hotkey = False
        else: super().keyPressEvent(e)

    def check_f_key(self):
        if keyboard and keyboard.is_pressed('f'):
            x, y = pyautogui.position()
            if self.capture_mode == "loot_center":
                self.temp_config["loot_center"] = (x, y)
                self.lbl_center.setText(f"{x}, {y}")
                self.finish_capture()
        elif keyboard and keyboard.is_pressed('esc'):
            self.finish_capture()
            
    def finish_capture(self):
        self.timer.stop(); self.capture_mode = None; self.show(); self.activateWindow()

    def capture_point(self, key):
        self.hide(); time.sleep(0.2); self.capture_mode = key; self.timer.start(50)

    def exec_select_area(self):
        self.hide(); QTimer.singleShot(250, self._do_select_area)

    def _do_select_area(self):
        overlay = SnippingOverlay()
        if overlay.exec_() == QDialog.Accepted and overlay.selected_rect:
            rect = overlay.selected_rect
            self.temp_config['loot_area'] = (rect.x(), rect.y(), rect.width(), rect.height())
            self.lbl_loot_area.setText(str(self.temp_config['loot_area']))
        self.show(); self.activateWindow()

    def exec_crop_image(self, img_type):
        self.hide(); 
        QTimer.singleShot(250, lambda: self._do_crop_image(img_type))

    def _do_crop_image(self, img_type):
        overlay = SnippingOverlay()
        if overlay.exec_() == QDialog.Accepted and overlay.selected_rect:
            rect = overlay.selected_rect
            try:
                with mss.mss() as sct:
                    mon = {"left": rect.x(), "top": rect.y(), "width": rect.width(), "height": rect.height()}
                    img = np.array(sct.grab(mon))
                    
                    filename = "loot_target.png" if img_type == "coin" else "loot_empty.png"
                    path = os.path.join(DATA_DIR, filename)
                    
                    cv2.imwrite(path, cv2.cvtColor(img, cv2.COLOR_BGRA2BGR))
                    
                    if img_type == "coin":
                        self.temp_config["path_loot"] = path
                        self.lbl_img_status.setText("✅")
                    else:
                        self.temp_config["path_empty"] = path
                        self.lbl_empty_status.setText("✅")
            except: pass
        self.show(); self.activateWindow()

    def save_and_accept(self):
        self.timer.stop()
        self.temp_config["hotkey"] = self.txt_hotkey.text()
        self.temp_config["mode"] = self.cmb_mode.currentText()
        self.temp_config["loop_delay"] = self.sp_loop.value()
        self.temp_config["loot_layout"] = self.cmb_layout.currentText()
        self.temp_config["loot_offset"] = self.sp_offset.value()
        self.temp_config["click_delay"] = self.sp_click.value()
        self.temp_config["scan_offset"] = self.sp_scan_offset.value()
        
        # YENİ: Hassasiyeti kaydet
        self.temp_config["confidence_loot"] = self.sp_confidence.value()
        
        self.config.update(self.temp_config)
        self.macro.update_config(self.config)
        super().accept()

# =========================================================
# 3. WIDGET (ANA EKRAN KARTI)
# =========================================================
class AutoDropWidget(QFrame):
    update_signal = pyqtSignal()

    def __init__(self, parent=None, macro_instance=None, config=None):
        super().__init__(parent)
        self.macro = macro_instance or AutoDropMacro()
        self.config = config or {}
        self.macro.update_config(self.config)
        self.listen_active = False 
        self._hooks = []
        self._last_press = 0
        self.update_signal.connect(self._safe_update_status)
        self.setup_ui()
        self._safe_update_status()

    def setup_ui(self):
        self.setFrameShape(QFrame.Box); self.setMaximumWidth(260)
        self.setStyleSheet("QFrame { background-color: #101010; border: 1px solid #444444; border-radius: 4px; }")
        v = QVBoxLayout(self); v.setContentsMargins(6,6,6,6); v.setSpacing(4)
        h = QHBoxLayout(); h.setSpacing(4)
        icon = QLabel("💰"); icon.setStyleSheet("font-size:20px; border:none;"); h.addWidget(icon)
        h.addStretch(1)
        title = QLabel("AUTO DROP"); title.setObjectName("MinorHeaderLabel"); h.addWidget(title)
        v.addLayout(h)
        self.btn_listen = QPushButton("TUŞ DİNLEMEYİ BAŞLAT")
        self.btn_listen.setObjectName("ThreeFiveListenButton")
        self.btn_listen.clicked.connect(self.toggle_listen)
        v.addWidget(self.btn_listen)
        self.lbl_status = QLabel("DURUM: PASİF"); self.lbl_status.setObjectName("MinorStatusLabel"); v.addWidget(self.lbl_status)
        row = QHBoxLayout(); row.setSpacing(4)
        row.addWidget(QLabel("TUŞ:"))
        self.lbl_hotkey = QLabel(self.config.get("hotkey", "X"))
        self.lbl_hotkey.setObjectName("HotkeyLabel"); self.lbl_hotkey.setAlignment(Qt.AlignCenter); row.addWidget(self.lbl_hotkey)
        btn_set = QPushButton("⚙ AYARLAR"); btn_set.setObjectName("MinorSettingsButton")
        btn_set.clicked.connect(self.open_settings); row.addWidget(btn_set)
        v.addLayout(row)

    def open_settings(self):
        dlg = AutoDropSettingsDialog(self, self.config, self.macro)
        if dlg.exec_():
            self.config.update(dlg.config)
            self.lbl_hotkey.setText(self.config.get("hotkey"))
            self.macro.update_config(self.config)

    def toggle_listen(self):
        if not keyboard: return QMessageBox.warning(self, "Hata", "keyboard yok")
        if not self.listen_active:
            k = self.config.get("hotkey", "X").lower()
            try:
                self._hooks = [keyboard.on_press_key(k, lambda e: self.on_hotkey(), suppress=False)]
                self.listen_active = True
                self.macro.start() 
            except Exception as e: 
                print(f"[DROP] Hook hatası: {e}"); self.listen_active = False
        else:
            for h in self._hooks: 
                try: keyboard.unhook(h)
                except: pass
            self._hooks = []
            self.listen_active = False
            self.macro.stop()
        self._safe_update_status()

    def on_hotkey(self):
        if time.time() - self._last_press < 0.5: return
        self._last_press = time.time()
        
        mode = self.config.get("mode", "Manuel (Tuşla)")
        
        if mode == "Manuel (Tuşla)":
            self.macro.run_manual_once()
        else:
            state = self.macro.toggle_auto()
            print(f"Otomatik Mod Durumu: {'AKTİF' if state else 'DURDU'}")
            
        self.update_signal.emit()

    def apply_status_style(self, color: str):
        self.lbl_status.setStyleSheet(f"color: {color}; font-weight: bold;")

    def _safe_update_status(self):
        if not self.listen_active:
            self.lbl_status.setText("DURUM: PASİF"); self.btn_listen.setText("TUŞ DİNLEMEYİ BAŞLAT")
            self.apply_status_style("#ff5555")
            self.btn_listen.setProperty("active", False)
        else:
            if self.macro.is_auto_active:
                self.lbl_status.setText("DURUM: ÇALIŞIYOR (OTO)")
                self.apply_status_style("#00ff4c")
            elif self.config.get("mode") == "Manuel (Tuşla)":
                self.lbl_status.setText("DURUM: HAZIR (MANUEL)")
                self.apply_status_style("#ffff55")
            else:
                self.lbl_status.setText("DURUM: BEKLİYOR (OTO)")
                self.apply_status_style("#ffff55")
                
            self.btn_listen.setText("TUŞ DİNLEMEYİ DURDUR")
            self.btn_listen.setProperty("active", True)
        
        self.btn_listen.style().unpolish(self.btn_listen)
        self.btn_listen.style().polish(self.btn_listen)

if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    w = AutoDropWidget()
    w.show()
    sys.exit(app.exec_())
