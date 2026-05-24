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
import winsound
import base64

# PyQt5
from PyQt5.QtWidgets import (
    QDialog, QGridLayout, QLabel, QComboBox, 
    QLineEdit, QPushButton, QDoubleSpinBox, 
    QDialogButtonBox, QHBoxLayout, QWidget,
    QFrame, QVBoxLayout, QSizePolicy, QMessageBox,
    QCheckBox, QGroupBox, QListWidget, QSpinBox
)
from PyQt5.QtGui import QPixmap, QIcon, QImage
from PyQt5.QtCore import Qt, pyqtSignal, QTimer

# Sürücüler
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

DATA_DIR = "farm_data"
if not os.path.exists(DATA_DIR): os.makedirs(DATA_DIR)

# =========================================================
# 1. LOGIC (VIP MOTORU)
# =========================================================
class VipStorageMacro:
    def __init__(self):
        self.slot1_pos = (0, 0)
        self.vip_btn_pos = (0, 0)
        self.inv_template = None 
        self.empty_template = None
        self.confirm_template = None
        
        self.mode = "Otomatik"
        self.item_count = 1
        self.timer_interval = 60
        self.slot_spacing = 50 
        self.click_delay = 0.2
        self.threshold = 0.70
        
        self._driver = _ClicksendKeyboardDriver() if _ClicksendKeyboardDriver else None
        self._mouse = _ClicksendMouseDriver() if _ClicksendMouseDriver else None
        self._sct = mss.mss()
        
        self._running = False
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self.last_run_time = 0

    def update_config(self, cfg):
        with self._lock:
            s1 = cfg.get("slot1_pos")
            self.slot1_pos = tuple(s1) if s1 else (0,0)
            vb = cfg.get("vip_btn_pos")
            self.vip_btn_pos = tuple(vb) if vb else (0,0)
            self.mode = cfg.get("mode", "Otomatik")
            self.item_count = cfg.get("item_count", 1)
            
            # --- ZAMAN HESABI ---
            val = cfg.get("timer_value", 60)
            unit = cfg.get("timer_unit", "Saniye")
            self.timer_interval = val if unit == "Saniye" else val * 60
            
            self.slot_spacing = cfg.get("slot_spacing", 50)
            self.click_delay = cfg.get("click_delay", 0.2)
            self.threshold = cfg.get("threshold", 0.70)
            self._load_templates(cfg)

    def _load_templates(self, cfg):
        files = {"inv": "vip_inv_header.png", "empty": "vip_empty_slot.png", "confirm": "vip_confirm_btn.png"}
        for key, fname in files.items():
            path = os.path.join(DATA_DIR, fname)
            img = cv2.imread(path, cv2.IMREAD_GRAYSCALE) if os.path.exists(path) else None
            if key == "inv": self.inv_template = img
            elif key == "empty": self.empty_template = img
            elif key == "confirm": self.confirm_template = img

    def is_inventory_open(self):
        if self.inv_template is None: return True 
        try:
            with mss.mss() as sct:
                mon = sct.monitors[1]
                region = {"top": 0, "left": mon["width"] // 2, "width": mon["width"] // 2, "height": mon["height"]}
                gray = cv2.cvtColor(np.array(sct.grab(region)), cv2.COLOR_BGRA2GRAY)
            res = cv2.matchTemplate(gray, self.inv_template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(res)
            return max_val > 0.75
        except: return False

    def ensure_inventory_open(self):
        """Envanter kapalıysa 'I' tuşuna basıp açar."""
        if not self.is_inventory_open():
            print("[VIP] Envanter kapalı, açılıyor...")
            if self._driver: 
                self._driver.tusbas(0x17, 0.1) # 'I' tuşu scancode: 0x17
            else: 
                pyautogui.press('i')
            time.sleep(1) # UI'ın ekrana gelmesi için bekleme

    def check_for_confirm(self):
        if self.confirm_template is None: return False
        try:
            vx, vy = self.vip_btn_pos
            region = {"left": vx - 150, "top": vy - 150, "width": 300, "height": 300}
            with mss.mss() as sct:
                gray = cv2.cvtColor(np.array(sct.grab(region)), cv2.COLOR_BGRA2GRAY)
            res = cv2.matchTemplate(gray, self.confirm_template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(res)
            return max_val > 0.75
        except: return False

    def get_slot_pos(self, slot_num, offset_y=0):
        idx = int(slot_num) - 1
        row, col = idx // 7, idx % 7
        x = self.slot1_pos[0] + (col * self.slot_spacing)
        y = self.slot1_pos[1] + (row * self.slot_spacing) - offset_y
        return (int(x), int(y))

    def get_slot_similarity(self, slot_num, offset_y=0):
        if self.empty_template is None: return 0.0
        x, y = self.get_slot_pos(slot_num, offset_y=offset_y)
        try:
            region = {"left": x - 15, "top": y - 15, "width": 30, "height": 30}
            with mss.mss() as sct:
                gray = cv2.cvtColor(np.array(sct.grab(region)), cv2.COLOR_BGRA2GRAY)
            res = cv2.matchTemplate(gray, self.empty_template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(res)
            return max_val
        except: return 0.0

    def is_slot_full(self, slot_num):
        # Benzerlik eşikten küçükse slot doludur
        return self.get_slot_similarity(slot_num) < self.threshold

    def _mouse_click(self, x, y, right=False):
        if self._stop_event.is_set(): return 
        if self._mouse:
            if right: self._mouse.rightclick(0.05, x, y)
            else: self._mouse.leftclick(0.05, x, y)
        else:
            pyautogui.moveTo(x, y); pyautogui.rightClick() if right else pyautogui.click()

    def _perform_dump(self):
        print(f"[VIP] {self.item_count} adet item boşaltılıyor...")
        self._mouse_click(self.vip_btn_pos[0], self.vip_btn_pos[1])
        time.sleep(0.2)
        self._mouse_click(self.vip_btn_pos[0], self.vip_btn_pos[1])
        
        time.sleep(1.0) # Deponun açılmasını bekle
        for i in range(1, self.item_count + 1):
            if self._stop_event.is_set(): break
            x, y = self.get_slot_pos(i, offset_y=50) 
            self._mouse_click(x, y, right=True)
            time.sleep(0.1)
            if self.check_for_confirm():
                if self._driver: self._driver.tusbas(0x1C, 0.05)
                else: keyboard.press_and_release('enter')
                time.sleep(0.2)
            else:
                time.sleep(self.click_delay)
        time.sleep(0.5)
        if self._driver: self._driver.tusbas(0x01, 0.1)
        else: pyautogui.press('esc')
        self.last_run_time = time.time()

    def _loop(self):
        print("[VIP] Döngü başladı.")
        while not self._stop_event.is_set():
            try:
                if self.mode == "Otomatik":
                    # Otomatik modda slotu görmek için envanter hep açık olmalı
                    self.ensure_inventory_open()
                    if self.is_slot_full(self.item_count):
                        self._perform_dump()
                        time.sleep(3.0)
                else:
                    # SÜRELİ MOD:
                    # Süre dolana kadar envanteri AÇMAZ, sadece bekler.
                    if time.time() - self.last_run_time >= self.timer_interval:
                        print("[VIP] Süre doldu, işlem başlıyor...")
                        
                        # 1. Önce envanteri aç
                        self.ensure_inventory_open()
                        time.sleep(0.1)
                        
                        # 2. VIP'e boşalt (Bu fonksiyon içinde zaten ESC ile kapatma var)
                        self._perform_dump()
                        
            except Exception as e: 
                print(f"[VIP] Hata: {e}")

            # Durdurma sinyalini hızlı yakalamak için kısa uykularla bekle
            for _ in range(10):
                if self._stop_event.is_set(): break
                time.sleep(0.2)

    def start(self):
        if not self._running:
            self._stop_event.clear(); self._running = True
            self.last_run_time = time.time() 
            threading.Thread(target=self._loop, daemon=True).start()

    def stop(self): self._stop_event.set(); self._running = False
    def toggle(self): self.stop() if self._running else self.start()
    @property
    def is_running(self): return self._running

# =========================================================
# 2. SETTINGS
# =========================================================
class VipStorageSettingsDialog(QDialog):
    def __init__(self, parent, config, macro):
        super().__init__(parent)
        self.setWindowTitle("VIP DEPOLAMA AYARLARI"); self.resize(480, 650)
        self.config, self.macro = config, macro
        layout = QVBoxLayout(self)
        
        g1 = QGroupBox("1. Başlatma Tuşu"); l1 = QHBoxLayout(g1)
        self.txt_hotkey = QLineEdit(self.config.get("hotkey", "F9")); self.txt_hotkey.setReadOnly(True)
        btn_hk = QPushButton("TUŞ SEÇ"); btn_hk.clicked.connect(self.start_hotkey_capture)
        l1.addWidget(self.txt_hotkey); l1.addWidget(btn_hk); layout.addWidget(g1)

        g2 = QGroupBox("2. Koordinatlar (F Tuşu ile)"); l2 = QGridLayout(g2)
        self.lbl_s1 = QLineEdit(str(self.config.get("slot1_pos", (0,0)))); btn_s1 = QPushButton("1. SLOT SEÇ")
        btn_s1.clicked.connect(lambda: self.start_capture("slot1"))
        self.lbl_vp = QLineEdit(str(self.config.get("vip_btn_pos", (0,0)))); btn_vp = QPushButton("VIP BUTON SEÇ")
        btn_vp.clicked.connect(lambda: self.start_capture("vip_btn"))
        l2.addWidget(QLabel("1. Slot Orta:"),0,0); l2.addWidget(self.lbl_s1,0,1); l2.addWidget(btn_s1,0,2)
        l2.addWidget(QLabel("VIP Buton:"),1,0); l2.addWidget(self.lbl_vp,1,1); l2.addWidget(btn_vp,1,2); layout.addWidget(g2)

        g3 = QGroupBox("3. Görsel Tanımlama"); l3 = QGridLayout(g3)
        
        # Dosya kontrolü yaparak başlangıç durumunu belirle
        iv_ok = os.path.exists(os.path.join(DATA_DIR, "vip_inv_header.png"))
        em_ok = os.path.exists(os.path.join(DATA_DIR, "vip_empty_slot.png"))
        cf_ok = os.path.exists(os.path.join(DATA_DIR, "vip_confirm_btn.png"))

        btn_iv = QPushButton("ENVANTER (F)"); btn_iv.clicked.connect(lambda: self.start_capture("inv_img"))
        self.st_iv = QLabel("✅" if iv_ok else "❌")
        
        btn_em = QPushButton("BOŞ KUTU (F)"); btn_em.clicked.connect(lambda: self.start_capture("empty_img"))
        self.st_em = QLabel("✅" if em_ok else "❌")
        
        btn_cf = QPushButton("CONFIRM (F)"); btn_cf.clicked.connect(lambda: self.start_capture("confirm_img"))
        self.st_cf = QLabel("✅" if cf_ok else "❌")

        # Stil: Yeşil ve kalın onay işaretleri
        for lbl in [self.st_iv, self.st_em, self.st_cf]:
            lbl.setStyleSheet("color: #00ff4c; font-weight: bold; font-size: 14px;")

        l3.addWidget(btn_iv,0,0); l3.addWidget(self.st_iv,0,1)
        l3.addWidget(btn_em,0,2); l3.addWidget(self.st_em,0,3) # Yan yana dizdik
        l3.addWidget(btn_cf,1,0); l3.addWidget(self.st_cf,1,1)
        layout.addWidget(g3)

        g4 = QGroupBox("4. Ayarlar"); l4 = QGridLayout(g4)
        self.cmb_m = QComboBox(); self.cmb_m.addItems(["Otomatik", "Süreli"]); self.cmb_m.setCurrentText(self.config.get("mode", "Otomatik"))
        self.sp_c = QSpinBox(); self.sp_c.setRange(1,28); self.sp_c.setValue(self.config.get("item_count", 5))
        
        # Saniye/Dakika Düzeni
        self.sp_timer_val = QSpinBox(); self.sp_timer_val.setRange(1, 3600); self.sp_timer_val.setValue(self.config.get("timer_value", 60))
        self.cmb_timer_unit = QComboBox(); self.cmb_timer_unit.addItems(["Saniye", "Dakika"]); self.cmb_timer_unit.setCurrentText(self.config.get("timer_unit", "Saniye"))
        time_layout = QHBoxLayout()
        time_layout.addWidget(self.sp_timer_val); time_layout.addWidget(self.cmb_timer_unit)

        self.sp_s = QSpinBox(); self.sp_s.setRange(30,70); self.sp_s.setValue(self.config.get("slot_spacing", 50))
        self.sp_th = QDoubleSpinBox(); self.sp_th.setRange(0.1,0.99); self.sp_th.setValue(self.config.get("threshold", 0.70))
        
        l4.addWidget(QLabel("Mod: OTO:"),0,0); l4.addWidget(self.cmb_m,0,1)
        l4.addWidget(QLabel("Depolanacak İtem Sayısı:"),1,0); l4.addWidget(self.sp_c,1,1)
        l4.addWidget(QLabel("Süreli Bekleme:"),2,0); l4.addLayout(time_layout, 2, 1)
        l4.addWidget(QLabel("Kutu Mesafesi (50px):"),3,0); l4.addWidget(self.sp_s,3,1)
        l4.addWidget(QLabel("Bos Kutu Hassasiyeti (0.70):"),4,0); l4.addWidget(self.sp_th,4,1); layout.addWidget(g4)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel); btns.accepted.connect(self.accept); btns.rejected.connect(self.reject); layout.addWidget(btns)
        self.timer = QTimer(self); self.timer.timeout.connect(self.check_f)

        self.setStyleSheet("""
            QDialog { background-color: #101010; color: white; }
            QLabel { color: white; background: transparent; }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { 
                background-color: #151515; 
                color: white; 
                border: 1px solid #333; 
                padding: 2px;
            }
            QGroupBox { color: #00ff4c; font-weight: bold; border: 1px solid #333; margin-top: 10px; padding-top: 10px; }
            QPushButton { background-color: #222; color: white; border: 1px solid #444; height: 25px; }
            QPushButton:hover { background-color: #333; }
        """)

    def start_hotkey_capture(self): self.capture_hotkey = True; self.txt_hotkey.setText("BAS..."); self.grabKeyboard()
    def keyPressEvent(self, e):
        if hasattr(self, 'capture_hotkey') and self.capture_hotkey:
            k = e.text().upper() or ("F1" if e.key()==Qt.Key_F1 else ""); self.txt_hotkey.setText(k); self.capture_hotkey = False; self.releaseKeyboard()
            return
        super().keyPressEvent(e)
    def start_capture(self, m): self.capture_mode = m; self.hide(); self.timer.start(50)
    def check_f(self):
        if keyboard.is_pressed('f'):
            x, y = pyautogui.position(); winsound.Beep(1000, 100)
            if self.capture_mode == "slot1": self.config["slot1_pos"] = (x, y); self.lbl_s1.setText(f"{x}, {y}")
            elif self.capture_mode == "vip_btn": self.config["vip_btn_pos"] = (x, y); self.lbl_vp.setText(f"{x}, {y}")
            elif self.capture_mode in ["inv_img", "empty_img", "confirm_img"]:
                w,h = (50,20) if self.capture_mode=="inv_img" else (30,30)
                with mss.mss() as sct:
                    g = cv2.cvtColor(np.array(sct.grab({"left":int(x-w/2),"top":int(y-h/2),"width":w,"height":h})), cv2.COLOR_BGRA2GRAY)
                    f_map = {"inv_img":"vip_inv_header.png", "empty_img":"vip_empty_slot.png", "confirm_img":"vip_confirm_btn.png"}
                    cv2.imwrite(os.path.join(DATA_DIR, f_map[self.capture_mode]), g)

                    if self.capture_mode == "inv_img": self.st_iv.setText("✅")
                    elif self.capture_mode == "empty_img": self.st_em.setText("✅")
                    elif self.capture_mode == "confirm_img": self.st_cf.setText("✅")
            self.timer.stop(); self.show()
        elif keyboard.is_pressed('esc'): self.timer.stop(); self.show()

    def accept(self):
        self.config["hotkey"] = self.txt_hotkey.text()
        self.config["mode"] = self.cmb_m.currentText()
        self.config["item_count"] = self.sp_c.value()
        
        # Yeni eklenen zaman değerleri
        self.config["timer_value"] = self.sp_timer_val.value()
        self.config["timer_unit"] = self.cmb_timer_unit.currentText()
        
        self.config["slot_spacing"] = self.sp_s.value()
        self.config["threshold"] = self.sp_th.value()
        self.macro.update_config(self.config)
        super().accept()
# =========================================================
# 3. WIDGET
# =========================================================
class VipStorageWidget(QFrame):
    update_signal = pyqtSignal()
    def __init__(self, parent=None, macro_instance=None, config=None):
        super().__init__(parent); self.macro = macro_instance or VipStorageMacro()
        self.config = config or {}; self.macro.update_config(self.config)
        self.listen_active = False; self._hotkey_hook = None
        self.update_signal.connect(self._safe_update); self.setup_ui(); self._safe_update()

    def setup_ui(self):
        self.setFrameShape(QFrame.Box); self.setMaximumWidth(260); self.setStyleSheet("QFrame { background-color: #101010; border: 1px solid #444; border-radius: 4px; }")
        v = QVBoxLayout(self); v.setContentsMargins(6,6,6,6); v.setSpacing(4)
        h = QHBoxLayout(); h.setSpacing(6)

        # --- İCON EKLEME KISMI (VIP) ---
        icon = QLabel(); icon.setFixedSize(30, 30); icon.setStyleSheet("border:none;")
        icon_path = os.path.join("icons", "gui", "vip.png")
        if os.path.exists(icon_path):
            pix = QPixmap(icon_path)
            icon.setPixmap(pix.scaled(30, 30, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        title = QLabel("VIP DEPOLAMA"); title.setObjectName("MinorHeaderLabel"); h.addWidget(icon); h.addStretch(); h.addWidget(title); v.addLayout(h)
        self.btn_listen = QPushButton("TUŞ DİNLEMEYİ BAŞLAT"); self.btn_listen.setObjectName("ThreeFiveListenButton"); self.btn_listen.setProperty("active", False)
        self.btn_listen.clicked.connect(self.toggle_listen); v.addWidget(self.btn_listen)
        self.lbl_status = QLabel("PASİF"); self.lbl_status.setObjectName("MinorStatusLabel"); v.addWidget(self.lbl_status)
        r = QHBoxLayout(); r.addWidget(QLabel("AKTİF TUŞ:")); self.lbl_key = QLabel(self.config.get("hotkey", "F9")); self.lbl_key.setObjectName("HotkeyLabel"); r.addWidget(self.lbl_key)
        btn_set = QPushButton("⚙ AYARLAR"); btn_set.setObjectName("MinorSettingsButton"); btn_set.clicked.connect(self.open_settings); r.addWidget(btn_set); v.addLayout(r)

    def open_settings(self):
        dlg = VipStorageSettingsDialog(self, self.config, self.macro)
        if dlg.exec_() == QDialog.Accepted: self.lbl_key.setText(self.config.get("hotkey"))

    def toggle_listen(self):
        if not keyboard: return
        if not self.listen_active:
            hk = self.config.get("hotkey", "F9").lower()
            try: self._hotkey_hook = keyboard.on_press_key(hk, lambda e: self.on_hotkey(), suppress=False); self.listen_active = True
            except: self.listen_active = False
        else:
            if self._hotkey_hook: keyboard.unhook(self._hotkey_hook)
            self._hotkey_hook = None; self.listen_active = False; self.macro.stop()
        self._safe_update()

    def on_hotkey(self): self.macro.toggle(); self.update_signal.emit()



    def _safe_update(self):
        if not self.listen_active:
            self.lbl_status.setText("PASİF"); self.lbl_status.setStyleSheet("color:#ff5555;font-weight:bold;")
            self.btn_listen.setText("TUŞ DİNLEMEYİ BAŞLAT"); self.btn_listen.setProperty("active", False)
        else:
            self.lbl_status.setText("BEKLİYOR" if not self.macro.is_running else "ÇALIŞIYOR")
            self.lbl_status.setStyleSheet("color:#ffff55;font-weight:bold;" if not self.macro.is_running else "color:#00ff4c;font-weight:bold;")
            self.btn_listen.setText("TUŞ DİNLEMEYİ DURDUR"); self.btn_listen.setProperty("active", True)
        self.btn_listen.style().unpolish(self.btn_listen); self.btn_listen.style().polish(self.btn_listen)
        QTimer.singleShot(500, self._safe_update)
