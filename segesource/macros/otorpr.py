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
import ast
import os
import cv2
import numpy as np
import mss
import pyautogui
import json

import base64

# PyQt5
from PyQt5.QtWidgets import (
    QDialog, QGridLayout, QLabel, QComboBox, 
    QLineEdit, QPushButton, QDoubleSpinBox, 
    QDialogButtonBox, QHBoxLayout, QWidget,
    QFrame, QVBoxLayout, QSizePolicy, QMessageBox,
    QCheckBox, QGroupBox, QListWidget
)
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtCore import Qt, pyqtSignal, QTimer

# Sürücüler
try:
    from clicksend import KeyboardDriver as _ClicksendKeyboardDriver
    from clicksend import MouseDriver as _ClicksendMouseDriver
except ImportError:
    _ClicksendKeyboardDriver = None
    _ClicksendMouseDriver = None

try:
    import winsound
except ImportError:
    winsound = None
    
try:
    import keyboard
except ImportError:
    keyboard = None

# Sabitler
F_SCANCODES = {1: 0x3B, 2: 0x3C, 3: 0x3D, 4: 0x3E, 5: 0x3F, 6: 0x40, 7: 0x41, 8: 0x42}
DIGIT_SCANCODES = {0: 0x0B, 1: 0x02, 2: 0x03, 3: 0x04, 4: 0x05, 5: 0x06, 6: 0x07, 7: 0x08, 8: 0x09, 9: 0x0A}

# =========================================================
# 1. LOGIC (MAKRO MOTORU)
# =========================================================
class OtoRprMacro:
    def __init__(self):
        self.equipped_pos = (0, 0)
        self.backup_slots = []
        self.main_weapon_slot = (0, 0)
        self.inv_template = None # Hafızadaki envanter görseli
        
        self.rpr_f = 0
        self.rpr_d = 0
        self.check_interval = 2.0
        self.repair_delay = 1.5
        
        self._driver = _ClicksendKeyboardDriver() if _ClicksendKeyboardDriver else None
        self._mouse = _ClicksendMouseDriver() if _ClicksendMouseDriver else None
        self._sct = mss.mss()
        
        self._running = False
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self.only_hammer = False
        self.main_weapon_active = False

    def update_config(self, cfg):
        with self._lock:
            e_pos = cfg.get("equipped_pos")
            self.equipped_pos = tuple(e_pos) if e_pos else (0,0)

            b_slots = cfg.get("backup_slots")
            self.backup_slots = [tuple(x) for x in b_slots] if b_slots else []

            m_pos = cfg.get("main_weapon_slot")
            self.main_weapon_slot = tuple(m_pos) if m_pos else (0,0)
            
            self.rpr_f = cfg.get("rpr_f", 0)
            self.rpr_d = cfg.get("rpr_d", 0)
            self.check_interval = cfg.get("check_interval", 2.0)
            self.only_hammer = cfg.get("only_hammer", False)

            # --- ENVANTER GÖRSELİNİ YÜKLE ---
            img_data = cfg.get("inv_image_base64")
            if img_data:
                try:
                    nparr = np.frombuffer(base64.b64decode(img_data), np.uint8)
                    self.inv_template = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
                except: self.inv_template = None

    def get_color_ratio(self, x, y):
        """Debug için o bölgedeki kırmızı oranını döner."""
        if x == 0 or y == 0: return 0.0
        try:
            w, h = 20, 20
            region = {"left": int(x - w/2), "top": int(y - h/2), "width": w, "height": h}
            
            with mss.mss() as sct:
                scr = np.array(sct.grab(region))
            
            hsv = cv2.cvtColor(scr, cv2.COLOR_BGRA2BGR)
            hsv = cv2.cvtColor(hsv, cv2.COLOR_BGR2HSV)
            
            # --- GENİŞLETİLMİŞ KIRMIZI ARALIĞI ---
            # Range 1: Turuncudan Kırmızıya
            lower1 = np.array([0, 50, 40])
            upper1 = np.array([15, 255, 255])
            
            # Range 2: Pembe/Mor'dan Kırmızıya
            lower2 = np.array([160, 50, 40])
            upper2 = np.array([180, 255, 255])
            
            mask = cv2.bitwise_or(cv2.inRange(hsv, lower1, upper1), cv2.inRange(hsv, lower2, upper2))
            
            red_pixels = cv2.countNonZero(mask)
            total_pixels = w * h
            return red_pixels / total_pixels
        except:
            return 0.0

    def is_item_broken(self, x, y):
        ratio = self.get_color_ratio(x, y)
        # Eşiği 0.70 yapıyoruz (Logunda sağlam silah 0.56, kırık olan 1.00 çıkmış)
        is_broken = ratio > 0.70 
        if is_broken:
            print(f"[RPR] Kırık Tespit Edildi! Oran: {ratio:.2f} @ {x},{y}")
        return is_broken

    def is_inventory_open(self):
        """Ekranda envanterin açık olup olmadığını kontrol eder."""
        if self.inv_template is None: return True 
        try:
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                # Ekranın sağ yarısında envanter parçası ara
                region = {"top": 0, "left": monitor["width"] // 2, "width": monitor["width"] // 2, "height": monitor["height"]}
                scr = np.array(sct.grab(region))
                scr_gray = cv2.cvtColor(scr, cv2.COLOR_BGRA2GRAY)
            
            res = cv2.matchTemplate(scr_gray, self.inv_template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(res)
            return max_val > 0.75
        except: return False

    def ensure_inventory_open(self):
        """Envanter kapalıysa 'I' tuşuna basıp açar."""
        if not self.is_inventory_open():
            print("[RPR] Envanter kapalı, açılıyor...")
            if self._driver: self._driver.tusbas(0x17, 0.1) # 'I' scancode
            else: pyautogui.press('i')
            time.sleep(1.0)

    @property
    def is_running(self): return self._running

    def start(self):
        if not self._running:
            self.main_weapon_active = False
            if self.equipped_pos == (0,0):
                print("[RPR] Takılı silah pozisyonu seçilmemiş!")
                return
            
            self._stop_event.clear()
            self._running = True
            threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._stop_event.set()
        self._running = False

    def toggle(self): self.stop() if self._running else self.start()

    def _mouse_click(self, x, y, right=False):
        try:
            if self._mouse:
                if right: self._mouse.rightclick(0.05, int(x), int(y))
                else: self._mouse.leftclick(0.05, int(x), int(y))
            else:
                pyautogui.moveTo(x, y)
                if right: pyautogui.rightClick()
                else: pyautogui.click()
        except: pass

    def _press_key(self, sc):
        if self._driver and sc:
            self._driver.tusbas(sc, 0.05)

    def _perform_repair(self):
        if self.main_weapon_slot == (0,0): return
        print("[RPR] Tamir işlemi başlatılıyor...")
        mx, my = self.main_weapon_slot
        
        # 1. RPR SC Kullan
        if self.rpr_f > 0:
            self._press_key(F_SCANCODES.get(self.rpr_f))
            time.sleep(0.3)
        
        self._press_key(DIGIT_SCANCODES.get(self.rpr_d))
        time.sleep(0.3)
        
        # 2. Silaha Sol Tıkla
        self._mouse_click(mx, my, right=False)
        time.sleep(self.repair_delay)
        
        # 3. Silahı Geri Giy
        self._mouse_click(mx, my, right=True)
        print("[RPR] Tamir tamamlandı.")

    def _loop(self):
        print("[RPR] Döngü başladı.")
        while not self._stop_event.is_set():
            try:
                self.ensure_inventory_open()
                ex, ey = self.equipped_pos # Eldeki slot
                
                # MOD 1: Sadece Hammer Bas veya Yedekler Bitti Modu
                if self.only_hammer or self.main_weapon_active:
                    if self.is_item_broken(ex, ey):
                        print("[RPR] Ana silah/Eldeki silah kırık, hammer basılıyor.")
                        self._perform_repair(target_pos=(ex, ey))
                        time.sleep(2.0) # Ekranın tazelenmesi için şart
                
                # MOD 2: Yedekli Çalışma Modu (Henüz yedekler bitmediyse)
                else:
                    if self.is_item_broken(ex, ey):
                        swapped = False
                        if self.backup_slots:
                            for bx, by in self.backup_slots:
                                if not self.is_item_broken(bx, by):
                                    print(f"[RPR] Yedek takılıyor: {bx},{by}")
                                    self._mouse_click(bx, by, right=True)
                                    swapped = True
                                    time.sleep(1.5)
                                    break
                        
                        # EĞER YEDEK BULAMADIYSA: ANA SİLAHA GEÇ VE ORADA KAL
                        if not swapped:
                            print("[RPR] Yedek bitti! Ana silah kuşanılıyor ve sabit moda geçiliyor.")
                            mx, my = self.main_weapon_slot
                            self._mouse_click(mx, my, right=True) # Ana silahı giy
                            
                            # BURASI KRİTİK: Artık makro "Ana Silah Modu"na girdi.
                            self.main_weapon_active = True 
                            
                            time.sleep(1.5)
                            # İlk giydiğinde kırıksa hemen tamir et
                            if self.is_item_broken(ex, ey):
                                self._perform_repair(target_pos=(ex, ey))
                                time.sleep(2.0)

            except Exception as e:
                print(f"[RPR] Hata: {e}")
            
            time.sleep(self.check_interval)

    def _perform_repair(self, target_pos):
        tx, ty = target_pos
        if tx == 0 or ty == 0: return

        print(f"[RPR] Tamir kağıdı basılıyor: {tx},{ty}")
        
        # 1. F Sayfasına geç
        if self.rpr_f > 0:
            self._press_key(F_SCANCODES.get(self.rpr_f))
            time.sleep(0.3)
        
        # 2. Hammer/SC rakamına bas
        self._press_key(DIGIT_SCANCODES.get(self.rpr_d))
        time.sleep(0.3)
        
        print("[RPR] Tamir tamamlandı.")

# =========================================================
# 2. GUI (AYAR PENCERESİ)
# =========================================================
class OtoRprSettingsDialog(QDialog):
    def __init__(self, parent, config, macro):
        super().__init__(parent)
        self.setWindowTitle("OTO RPR AYARLARI")
        self.resize(600, 750)
        self.config = config
        self.macro = macro
        self.capture_hotkey = False
        self.coord_target = None
        self.capture_mode = False
        self.chk_only_hammer = QCheckBox("Sadece Hammer Bas (Yedek/Değişim Yapmaz)")
        self.chk_only_hammer.setChecked(self.config.get("only_hammer", False))
        self.temp_backups = list(self.config.get("backup_slots", []))
        layout = QVBoxLayout(self)
        
        # --- 0. BAŞLATMA TUŞU ---
        grp_hk = QGroupBox("1. Başlatma Tuşu")
        gh = QHBoxLayout(grp_hk)
        self.txt_hotkey = QLineEdit(self.config.get("hotkey", "F8"))
        self.txt_hotkey.setReadOnly(True)
        btn_hk = QPushButton("TUŞ SEÇ")
        btn_hk.clicked.connect(self.start_hotkey_capture)
        gh.addWidget(self.txt_hotkey); gh.addWidget(btn_hk)
        layout.addWidget(grp_hk)

        # --- 1. KOORDİNATLAR ---
        grp_pos = QGroupBox("2. Koordinat Tanımlama (F Tuşu ile)")
        gp = QGridLayout(grp_pos)
        
        # Takılı Silah
        self.lbl_equipped = QLineEdit(str(self.config.get("equipped_pos", (0,0))))
        self.lbl_equipped.setReadOnly(True)
        btn_equip = QPushButton("SEÇ")
        btn_equip.clicked.connect(lambda: self.select_coord("equipped_pos", self.lbl_equipped))
        
        # TEST Butonu
        btn_test_equip = QPushButton("TEST ET")
        btn_test_equip.setStyleSheet("background-color: #2979ff; color: white;")
        btn_test_equip.clicked.connect(lambda: self.test_coord("equipped_pos", self.lbl_equipped.text()))

        gp.addWidget(QLabel("Elindeki Silah:"), 0, 0)
        gp.addWidget(self.lbl_equipped, 0, 1)
        gp.addWidget(btn_equip, 0, 2)
        gp.addWidget(btn_test_equip, 0, 3) 

        # Ana Silah (Envanter)
        self.lbl_main = QLineEdit(str(self.config.get("main_weapon_slot", (0,0))))
        self.lbl_main.setReadOnly(True)
        btn_main = QPushButton("SEÇ")
        btn_main.clicked.connect(lambda: self.select_coord("main_weapon_slot", self.lbl_main))

        gp.addWidget(QLabel("Yuksek AP Silah:"), 1, 0)
        gp.addWidget(self.lbl_main, 1, 1)
        gp.addWidget(btn_main, 1, 2)

        # Envanter Örneği Seçme (YENİ)
        btn_inv = QPushButton("ENVANTER GÖRSELİ SEÇ (F)")
        btn_inv.setStyleSheet("background-color: #6a1b9a; color: white; font-weight: bold;")
        btn_inv.clicked.connect(self.start_inv_capture)
        self.lbl_inv_status = QLabel("Görsel Durumu: " + ("AYARLANDI ✅" if self.config.get("inv_image_base64") else "SEÇİLMEDİ ❌"))
        
        gp.addWidget(QLabel("Envanter Kontrolü:"), 2, 0)
        gp.addWidget(self.lbl_inv_status, 2, 1)
        gp.addWidget(btn_inv, 2, 2)
        
        layout.addWidget(grp_pos)
        
        # --- 2. YEDEKLER ---
        grp_back = QGroupBox("3. Yedek Silahlar")
        gb = QVBoxLayout(grp_back)
        self.list_backups = QListWidget()
        self.refresh_backups()
        
        bh = QHBoxLayout()
        btn_add_back = QPushButton("Silah Sec (Multi)")
        btn_add_back.setStyleSheet("background-color: #004d40; color: white; font-weight: bold;")
        btn_add_back.clicked.connect(self.add_backup_coord)
        
        btn_del_back = QPushButton("SEÇİLENİ SİL")
        btn_del_back.clicked.connect(self.del_backup)
        
        btn_clr_back = QPushButton("TEMİZLE")
        btn_clr_back.clicked.connect(self.clear_backups)
        
        bh.addWidget(btn_add_back); bh.addWidget(btn_del_back); bh.addWidget(btn_clr_back)
        gb.addWidget(self.list_backups)
        gb.addLayout(bh)
        gb.addWidget(QLabel("Yedek Ekle'ye basınca pencere gizlenir. Sırayla itemlerin üstüne gelip F'ye basın.\nBitince ESC'ye basarak pencereyi geri getirin.", styleSheet="color:gray; font-size:10px;"))
        layout.addWidget(grp_back)
        
        # --- 3. RPR SCROLL ---
        grp_sc = QGroupBox("4. RPR Kağıdı (Hammer) Tuşu")
        gc = QHBoxLayout(grp_sc)
        
        self.cmb_f = QComboBox(); self.cmb_f.addItem("F YOK", 0)
        for i in range(1, 9): self.cmb_f.addItem(f"F{i}", i)
        idx = self.cmb_f.findData(self.config.get("rpr_f", 0)); self.cmb_f.setCurrentIndex(idx if idx>=0 else 0)
        
        self.cmb_d = QComboBox()
        for i in range(10): self.cmb_d.addItem(str(i), i)
        self.cmb_d.setCurrentIndex(self.config.get("rpr_d", 0))
        
        gc.addWidget(QLabel("F Sayfası:")); gc.addWidget(self.cmb_f)
        gc.addWidget(QLabel("Tuş (0-9):")); gc.addWidget(self.cmb_d)
        layout.addWidget(grp_sc)
        
        # --- 4. AYARLAR ---
        grp_set = QGroupBox("5. Zamanlama")
        gst = QHBoxLayout(grp_set)
        self.sp_interval = QDoubleSpinBox(); self.sp_interval.setRange(0.5, 60.0); self.sp_interval.setValue(self.config.get("check_interval", 2.0))
        gst.addWidget(QLabel("Kontrol Sıklığı (sn):")); gst.addWidget(self.sp_interval)
        layout.addWidget(grp_set)



        self.chk_only_hammer = QCheckBox("Sadece Hammer Bas (Yedek/Ana Silah Değişimi Yapmaz)")
        self.chk_only_hammer.setStyleSheet("color: #ff9800; font-weight: bold; font-size: 13px;")
        self.chk_only_hammer.setChecked(self.config.get("only_hammer", False))
        layout.addWidget(self.chk_only_hammer)

        
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def test_coord(self, key, coord_str):
        # AUDIT-2026-05 Round 3 C8 FIX:
        # Eski eval() UI text-box icerigini Python kodu olarak calistirirdi.
        # Kullanici "__import__('os').system('...')" yazsa keyfi RCE olurdu.
        # ast.literal_eval YALNIZCA literal degerleri (tuple/list/sayi/string)
        # parse eder, kod calistirmaz.
        try:
            coord = ast.literal_eval(coord_str)
            if not isinstance(coord, tuple) or coord == (0,0):
                QMessageBox.warning(self, "Hata", "Geçersiz koordinat!")
                return
            x, y = coord
            ratio = self.macro.get_color_ratio(x, y)
            is_broken = ratio > 0.10
            status = "🔴 KIRIK ALGILANDI" if is_broken else "🟢 SAĞLAM"
            msg = (f"Koordinat: {x}, {y}\nKırmızılık Oranı: %{ratio*100:.2f}\nEşik Değeri: %10.00\n\nDurum: {status}")
            QMessageBox.information(self, "Test Sonucu", msg)
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Test hatası: {e}")

    def start_hotkey_capture(self):
        self.capture_hotkey = True; self.txt_hotkey.setText("BAS..."); self.grabKeyboard()

    def keyPressEvent(self, e):
        if self.capture_hotkey:
            k = e.text().upper()
            if not k and e.key() == Qt.Key_F1: k = "F1"
            if k: self.txt_hotkey.setText(k); self.capture_hotkey = False; self.releaseKeyboard()
            return
        super().keyPressEvent(e)

    def start_inv_capture(self):
        self.hide(); self.capture_mode = "inventory"
        self.timer = QTimer(self); self.timer.timeout.connect(self.check_f); self.timer.start(50)

    def select_coord(self, key, label):
        self.hide(); self.coord_target = (key, label); self.capture_mode = "single"
        self.timer = QTimer(self); self.timer.timeout.connect(self.check_f); self.timer.start(50)

    def add_backup_coord(self):
        self.hide(); self.capture_mode = "multi"
        self.timer = QTimer(self); self.timer.timeout.connect(self.check_f); self.timer.start(50)

    def check_f(self):
        if keyboard.is_pressed('f'):
            x, y = pyautogui.position(); winsound.Beep(1000, 100)
            if self.capture_mode == "inventory":
                w, h = 30, 30
                region = {"left": int(x-w/2), "top": int(y-h/2), "width": w, "height": h}
                with mss.mss() as sct:
                    img = np.array(sct.grab(region))
                    gray = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
                    _, buffer = cv2.imencode('.png', gray)
                    self.config["inv_image_base64"] = base64.b64encode(buffer).decode('utf-8')
                    self.lbl_inv_status.setText("Görsel Durumu: AYARLANDI ✅")
                self.timer.stop(); self.show()
            elif self.capture_mode == "single":
                key, lbl = self.coord_target; self.config[key] = (x, y); lbl.setText(f"{x}, {y}")
                self.timer.stop(); self.show()
            elif self.capture_mode == "multi":
                self.temp_backups.append((x, y)); self.refresh_backups(); time.sleep(0.3)
        elif keyboard.is_pressed('esc'): self.timer.stop(); self.show()

    def refresh_backups(self):
        self.list_backups.clear()
        for i, pos in enumerate(self.temp_backups):
            self.list_backups.addItem(f"Yedek {i+1}: {pos}")

    def del_backup(self):
        row = self.list_backups.currentRow()
        if row >= 0:
            self.temp_backups.pop(row); self.refresh_backups()

    def clear_backups(self):
        self.temp_backups = []; self.refresh_backups()

    def accept(self):
        self.config["hotkey"] = self.txt_hotkey.text()
        self.config["rpr_f"] = self.cmb_f.currentData()
        self.config["rpr_d"] = int(self.cmb_d.currentText())
        self.config["check_interval"] = self.sp_interval.value()
        self.config["backup_slots"] = self.temp_backups
        
        self.config["only_hammer"] = self.chk_only_hammer.isChecked()
        self.macro.update_config(self.config)
        super().accept()

# =========================================================
# 3. WIDGET
# =========================================================
class OtoRprWidget(QFrame):
    update_signal = pyqtSignal()
    def __init__(self, parent=None, macro_instance=None, config=None):
        super().__init__(parent); self.macro = macro_instance or OtoRprMacro(); self.config = config or {}; self.macro.update_config(self.config)
        self.listen_active = False; self._hotkey_hook = None
        self.update_signal.connect(self._safe_update); self.setup_ui(); self._safe_update()

    def setup_ui(self):
        self.setFrameShape(QFrame.Box)
        self.setMaximumWidth(260)
        self.setStyleSheet(
            "QFrame { background-color: #101010; border: 1px solid #444; border-radius: 4px; }"
        )

        v = QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(4)

        # ─── HEADER ──────────────────────────────
        h = QHBoxLayout()
        h.setSpacing(6)

        icon = QLabel()
        pix = QPixmap("icons/hammer.png")
        if not pix.isNull():
            icon.setPixmap(pix.scaled(22, 22, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        icon.setFixedSize(24, 24)
        icon.setStyleSheet("border:none;")

        title = QLabel("OTO RPR")
        title.setObjectName("MinorHeaderLabel")

        h.addWidget(icon)
        h.addStretch()
        h.addWidget(title)
        v.addLayout(h)
        
        self.btn_listen = QPushButton("TUŞ DİNLEMEYİ BAŞLAT")
        self.btn_listen.setObjectName("ThreeFiveListenButton")
        self.btn_listen.setProperty("active", False)
        self.btn_listen.clicked.connect(self.toggle_listen); v.addWidget(self.btn_listen)
        
        self.lbl_status = QLabel("PASİF"); self.lbl_status.setObjectName("MinorStatusLabel"); v.addWidget(self.lbl_status)
        
        r = QHBoxLayout(); r.addWidget(QLabel("AKTİF TUŞ:"))
        self.lbl_key = QLabel(self.config.get("hotkey", "F8")); self.lbl_key.setObjectName("HotkeyLabel"); r.addWidget(self.lbl_key)
        
        btn_set = QPushButton("⚙ AYARLAR"); btn_set.setObjectName("MinorSettingsButton"); btn_set.clicked.connect(self.open_settings)
        r.addWidget(btn_set); v.addLayout(r)

    def open_settings(self):
        dlg = OtoRprSettingsDialog(self, self.config, self.macro)
        if dlg.exec_() == QDialog.Accepted:
            self.lbl_key.setText(self.config.get("hotkey"))
            if self.listen_active: self.toggle_listen(); self.toggle_listen()

    def toggle_listen(self):
        if not keyboard: return
        if not self.listen_active:
            hk = self.config.get("hotkey", "F8").lower()
            try:
                self._hotkey_hook = keyboard.on_press_key(hk, lambda e: self.on_hotkey(), suppress=False)
                self.listen_active = True
            except: self.listen_active = False
        else:
            if self._hotkey_hook:
                try: keyboard.unhook(self._hotkey_hook)
                except: pass
            self._hotkey_hook = None; self.listen_active = False; self.macro.stop()
        self._safe_update()

    def on_hotkey(self):
        self.macro.toggle()
        self.update_signal.emit()

    def _safe_update(self):
        if not self.listen_active:
            self.lbl_status.setText("PASİF"); self.lbl_status.setStyleSheet("color:#ff5555;font-weight:bold;")
            self.btn_listen.setText("TUŞ DİNLEMEYİ BAŞLAT"); self.btn_listen.setProperty("active", False)
        else:
            if self.macro.is_running:
                self.lbl_status.setText("ÇALIŞIYOR"); self.lbl_status.setStyleSheet("color:#00ff4c;font-weight:bold;")
            else:
                self.lbl_status.setText("BEKLİYOR"); self.lbl_status.setStyleSheet("color:#ffff55;font-weight:bold;")
            self.btn_listen.setText("TUŞ DİNLEMEYİ DURDUR"); self.btn_listen.setProperty("active", True)
        self.btn_listen.style().unpolish(self.btn_listen); self.btn_listen.style().polish(self.btn_listen)
        QTimer.singleShot(500, self._safe_update)
