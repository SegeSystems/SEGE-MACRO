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
import pyautogui
import numpy as np 
import cv2 

# PyQt5
from PyQt5.QtWidgets import (
    QDialog, QGridLayout, QLabel, QComboBox, 
    QLineEdit, QPushButton, QDoubleSpinBox, 
    QDialogButtonBox, QHBoxLayout, QWidget,
    QFrame, QVBoxLayout, QSizePolicy, QMessageBox, QCheckBox, QApplication,
    QGroupBox
)
from PyQt5.QtGui import QPixmap, QIcon, QPainter, QColor, QBrush, QPen
from PyQt5.QtCore import Qt, QSize, QRect, pyqtSignal, QTimer

# Clicksend Import (MouseDriver EKLENDİ)
try:
    from clicksend import KeyboardDriver as _ClicksendKeyboardDriver, MouseDriver as _ClicksendMouseDriver
except ImportError:
    _ClicksendKeyboardDriver = None
    _ClicksendMouseDriver = None

try:
    import keyboard
except ImportError:
    keyboard = None

# ---------------------------------------------------------
# SABİTLER
# ---------------------------------------------------------
DIGIT_SCANCODES = {
    0: 0x0B, 1: 0x02, 2: 0x03, 3: 0x04, 4: 0x05, 
    5: 0x06, 6: 0x07, 7: 0x08, 8: 0x09, 9: 0x0A
}
F_SCANCODES = {
    1: 0x3B, 2: 0x3C, 3: 0x3D, 4: 0x3E,
    5: 0x3F, 6: 0x40, 7: 0x41, 8: 0x42
}

# Z tuşu scancode
Z_SCANCODE = 0x2C

def _default_send_key(scan_code: int, press_time: float = 0.01):
    if _ClicksendKeyboardDriver and not hasattr(_default_send_key, "_driver"):
        _default_send_key._driver = _ClicksendKeyboardDriver()
    
    if hasattr(_default_send_key, "_driver"):
        _default_send_key._driver.tusbas(scan_code, press_time)
    else:
        time.sleep(press_time)

# =========================================================
# 1. LOGIC (MAKRO MOTORU)
# =========================================================
class SmartPetMacro:
    def __init__(self):
        self.common_region = None
        
        # --- HP AYARLARI (Alt+1~9) ---
        self.hp_enabled = True
        self.hp_alt_num = 1  # Alt+1 ~ Alt+9
        self.hp_trigger = 0.50
        self.hp_cooldown = 0.5
        
        # --- MP AYARLARI (Alt+1~9) ---
        self.mp_enabled = True
        self.mp_alt_num = 2  # Alt+1 ~ Alt+9
        self.mp_trigger = 0.30
        self.mp_cooldown = 0.5
        
        # --- FEED AYARLARI (Yaprak/Süt/Ekmek) ---
        self.feed_enabled = True
        self.feed_type = 1  # 1=Yaprak, 2=Süt, 3=Ekmek
        self.feed_trigger = 0.40
        self.feed_cooldown = 2.0
        
        # --- ATAK AYARLARI (YENİ) ---
        self.attack_enabled = False  # Varsayılan kapalı
        self.z_duration = 0.05       # Z tuşu basılı tutma süresi (saniye)
        self.alt2_duration = 0.05    # Alt+2 tuşu basılı tutma süresi (saniye)
        self.attack_interval = 1.0   # Atak döngü aralığı (saniye)
        
        # --- ICON PATHS ---
        self.feed_icons = {
            1: "icons/yaprak.png",
            2: "icons/sut.png",
            3: "icons/ekmek.png"
        }
        self.itembutton_path = "icons/itembutton.png"
        self.confirm_path = "icons/confirm.png"
        self.feeding_path = "icons/feeding.png"
        
        # Runtime
        self.scan_interval = 0.05
        self._send_key = _default_send_key
        
        # Referanslar
        self._hp_ref = None
        self._mp_ref = None
        self._satiation_ref = None
        
        self.hp_ratio = 1.0
        self.mp_ratio = 1.0
        self.satiation_ratio = 1.0
        
        self._last_hp = 0
        self._last_mp = 0
        self._last_satiation = 0
        self._last_attack = 0  # Atak için son zaman
        
        self._thread = None
        self._stop_event = threading.Event()
        self._running = False
        self._lock = threading.Lock() 

    def update_config(self, cfg):
        with self._lock:
            # HP
            self.hp_enabled = cfg.get("hp_enabled", True)
            self.hp_alt_num = cfg.get("hp_alt_num", 1)
            self.hp_trigger = cfg.get("hp_trigger", 0.50)
            
            # MP
            self.mp_enabled = cfg.get("mp_enabled", True)
            self.mp_alt_num = cfg.get("mp_alt_num", 2)
            self.mp_trigger = cfg.get("mp_trigger", 0.30)
            
            # FEED
            self.feed_enabled = cfg.get("feed_enabled", True)
            self.feed_type = cfg.get("feed_type", 1)
            self.feed_trigger = cfg.get("feed_trigger", 0.40)
            
            # ATAK (YENİ)
            self.attack_enabled = cfg.get("attack_enabled", False)
            self.z_duration = cfg.get("z_duration", 0.05)
            self.alt2_duration = cfg.get("alt2_duration", 0.05)
            self.attack_interval = cfg.get("attack_interval", 1.0)
            
            # Region
            if cfg.get("hp_region"):
                self.common_region = tuple(cfg.get("hp_region"))
                self._hp_ref = None
                self._mp_ref = None
                self._satiation_ref = None

    @property
    def is_running(self): return self._running

    def toggle(self): self.stop() if self._running else self.start()

    def start(self):
        if self._running: return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._running = True
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        self._running = False
        if self._thread: self._thread.join(0.5)

    def _loop(self):
        while not self._stop_event.is_set():
            try: 
                self._check_logic()
                self._check_attack()  # Atak kontrolü
            except Exception as e: print("[PET] Hata:", e)
            time.sleep(self.scan_interval)

    def _check_attack(self):
        """Atak sistemini kontrol et ve çalıştır"""
        if not self.attack_enabled:
            return
        
        now = time.time()
        if now - self._last_attack < self.attack_interval:
            return
        
        try:
            # 1. Z tuşuna bas
            self._press_z()
            time.sleep(0.1)
            
            # 2. Alt+2 bas
            self._press_alt_digit_attack(2)
            
            self._last_attack = now
            print(f"[PET] ATAK YAPILDI! Z:{self.z_duration}s, Alt+2:{self.alt2_duration}s")
            
        except Exception as e:
            print(f"[PET] Atak hatası: {e}")

    def _press_z(self):
        """Z tuşuna belirtilen süre kadar bas"""
        if not _ClicksendKeyboardDriver:
            return
        
        driver = _ClicksendKeyboardDriver()
        driver.tusbas(Z_SCANCODE, self.z_duration)

    def _press_alt_digit_attack(self, digit):
        """Atak için Alt+digit kombinasyonunu bas (ayarlanabilir süre)"""
        if not _ClicksendKeyboardDriver:
            return
        
        driver = _ClicksendKeyboardDriver()
        # Alt tuşu bas
        driver.tusbasilitut(0x38)  # Left Alt
        time.sleep(0.05)
        # Digit tuşu bas (ayarlanabilir süre)
        digit_scan = DIGIT_SCANCODES.get(digit, 0x03)  # 2 için 0x03
        driver.tusbas(digit_scan, self.alt2_duration)
        time.sleep(0.05)
        # Alt tuşu bırak
        driver.tusbirak(0x38)

    def _check_logic(self):
        if self.common_region is None: return
        
        try:
            img = np.array(pyautogui.screenshot(region=self.common_region))
        except: return

        now = time.time()

        # 1. HP ANALİZİ
        hp_count, hp_total = self._count_pixels(img, "hp")
        if hp_total > 0:
            self._update_ref(hp_count, "hp")
            if self._hp_ref:
                self.hp_ratio = hp_count / self._hp_ref
                
                if self.hp_enabled and (now - self._last_hp >= self.hp_cooldown):
                    if hp_count < self._hp_ref * self.hp_trigger:
                        print(f"[PET] HP POT BASILIYOR! Can: %{self.hp_ratio*100:.1f}")
                        self._press_alt_digit(self.hp_alt_num)
                        self._last_hp = now

        # 2. MP ANALİZİ
        if self.mp_enabled:
            mp_count, mp_total = self._count_pixels(img, "mp")
            if mp_total > 0:
                self._update_ref(mp_count, "mp")
                if self._mp_ref:
                    self.mp_ratio = mp_count / self._mp_ref
                    
                    if (now - self._last_mp >= self.mp_cooldown):
                        if mp_count < self._mp_ref * self.mp_trigger:
                            print(f"[PET] MP POT BASILIYOR! Mana: %{self.mp_ratio*100:.1f}")
                            self._press_alt_digit(self.mp_alt_num)
                            self._last_mp = now

        # 3. SATIATION ANALİZİ (FEED)
        if self.feed_enabled:
            sat_count, sat_total = self._count_pixels(img, "satiation")
            if sat_total > 0:
                self._update_ref(sat_count, "satiation")
                if self._satiation_ref:
                    self.satiation_ratio = sat_count / self._satiation_ref
                    
                    if (now - self._last_satiation >= self.feed_cooldown):
                        if sat_count < self._satiation_ref * self.feed_trigger:
                            print(f"[PET] BESLENME BAŞLANIYOR! Satiation: %{self.satiation_ratio*100:.1f}")
                            self._execute_feeding()
                            self._last_satiation = now

    def _count_pixels(self, img_np, mode):
        img_hsv = cv2.cvtColor(cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR), cv2.COLOR_BGR2HSV)
        
        if mode == "hp":
            # Kırmızı/Pembe tonları
            lower1 = np.array([0, 80, 80]); upper1 = np.array([25, 255, 255])
            lower2 = np.array([160, 80, 80]); upper2 = np.array([180, 255, 255])
            mask = cv2.bitwise_or(cv2.inRange(img_hsv, lower1, upper1), cv2.inRange(img_hsv, lower2, upper2))
        elif mode == "mp":
            # Mavi tonları
            lower = np.array([100, 80, 80]); upper = np.array([140, 255, 255])
            mask = cv2.inRange(img_hsv, lower, upper)
        elif mode == "satiation":
            # Sarı/Orange tonları
            lower = np.array([15, 80, 80]); upper = np.array([40, 255, 255])
            mask = cv2.inRange(img_hsv, lower, upper)
        else: return 0, 0
            
        return cv2.countNonZero(mask), img_hsv.size / 3

    def _update_ref(self, cur, mode):
        if mode == "hp":
            if self._hp_ref is None or cur > self._hp_ref: self._hp_ref = cur
        elif mode == "mp":
            if self._mp_ref is None or cur > self._mp_ref: self._mp_ref = cur
        elif mode == "satiation":
            if self._satiation_ref is None or cur > self._satiation_ref: self._satiation_ref = cur

    def _press_alt_digit(self, digit):
        """Alt+digit kombinasyonunu bas"""
        if not _ClicksendKeyboardDriver:
            return
        
        driver = _ClicksendKeyboardDriver()
        # Alt tuşu bas
        driver.tusbasilitut(0x38)  # Left Alt
        time.sleep(0.05)
        # Digit tuşu bas
        digit_scan = DIGIT_SCANCODES.get(digit, 0x02)
        driver.tusbas(digit_scan, 0.02)
        time.sleep(0.05)
        # Alt tuşu bırak
        driver.tusbirak(0x38)

    def _execute_feeding(self):
        """Beslenme akışını çalıştır - İNSAN GİBİ SÜRÜKLEME (DÜZELTİLMİŞ)"""
        try:
            if not _ClicksendKeyboardDriver or not _ClicksendMouseDriver:
                print("[PET] Driver eksik!")
                return
            
            kb = _ClicksendKeyboardDriver()
            ms = _ClicksendMouseDriver()
            
            # 1. P tuşu bas
            kb.tusbas(0x19, 0.1)  # P
            time.sleep(0.8)
            
            # 2. Item button'a tıkla
            if not self._click_image(ms, self.itembutton_path):
                kb.tusbas(0x01, 0.1) # ESC
                return
            time.sleep(0.5)
            
            # 3. Yiyecek ve Feeding Alanı Konumlarını Bul
            food_path = self.feed_icons.get(self.feed_type)
            if not food_path: return

            # Threshold 0.90 (Yanlış itemi seçmemesi için)
            food_pos = self._find_image_center(food_path, threshold=0.90)
            feeding_pos = self._find_image_center(self.feeding_path, threshold=0.7)

            if food_pos and feeding_pos:
                fx, fy = food_pos
                tx, ty = feeding_pos
                target_y = ty + 50 

                # --- SÜRÜKLEME BAŞLANGICI ---
                
                # A. Yiyeceğin üzerine git
                ms.mouse_move(fx, fy)
                time.sleep(0.15)

                # B. Sol tık BASILI TUT (yerinde, hareket yok)
                ms.mouse_left_down(fx, fy)
                time.sleep(0.1)

                # C. SÜRÜKLEME - basılı tutarken hareket et
                steps = 40
                diff_x = tx - fx
                diff_y = target_y - fy

                for i in range(steps):
                    ratio = (i + 1) / steps
                    next_x = int(fx + diff_x * ratio)
                    next_y = int(fy + diff_y * ratio)
                    
                    ms.mouse_move(next_x, next_y)  # Sadece hareket, tıklama yok
                    time.sleep(0.015)

                # D. BIRAK
                time.sleep(0.1)
                ms.mouse_left_up(tx, target_y)
                
                # --- SÜRÜKLEME BİTİŞİ ---

            # 5. Confirm
            time.sleep(0.5)
            confirm_pos = self._find_image_center(self.confirm_path, threshold=0.6)
            if confirm_pos:
                print(f"[PET] Confirm BULUNDU: {confirm_pos}")
                ms.leftclick(0.1, confirm_pos[0], confirm_pos[1])
            else:
                print("[PET] Confirm BULUNAMADI!")
            time.sleep(0.5)
            
            # 6. Menüleri Kapat
            kb.tusbas(0x1F, 0.1)  # S
            time.sleep(0.3)
            kb.tusbas(0x01, 0.1)  # ESC
            
        except Exception as e:
            print(f"[PET] Hata: {e}")

    def _find_image_center(self, icon_path, threshold=0.7):
        """Görseli arar ve merkez koordinatlarını (x, y) döner."""
        try:
            import os
            if not os.path.exists(icon_path):
                print(f"[PET] Dosya bulunamadı: {icon_path}")
                return None
            
            screenshot = pyautogui.screenshot()
            screen_np = np.array(screenshot)
            screen_bgr = cv2.cvtColor(screen_np, cv2.COLOR_RGB2BGR)
            
            template = cv2.imread(icon_path)
            if template is None:
                print(f"[PET] Template okunamadı: {icon_path}")
                return None
            
            result = cv2.matchTemplate(screen_bgr, template, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
            
            print(f"[PET] {icon_path} -> max_val: {max_val:.2f}, threshold: {threshold}")
            
            if max_val > threshold:
                h, w = template.shape[:2]
                center_x = max_loc[0] + w // 2
                center_y = max_loc[1] + h // 2
                return (center_x, center_y)
            
            return None
        except Exception as e:
            print(f"[PET] _find_image_center hata: {e}")
            return None

    def _click_image(self, ms, icon_path, threshold=0.8):
        """Ekranda görüntü bulup tıkla"""
        pos = self._find_image_center(icon_path, threshold=threshold)
        if pos:
            print(f"[PET] {icon_path} BULUNDU: {pos}")
            ms.leftclick(0.1, pos[0], pos[1])
            return True
        print(f"[PET] {icon_path} BULUNAMADI!")
        return False

# =========================================================
# 2. YARDIMCI DİALOGLAR
# =========================================================
class RectSelectDialog(QDialog):
    def __init__(self, parent=None, title="ALANI SEÇ"):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setWindowState(Qt.WindowFullScreen)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setCursor(Qt.CrossCursor)
        self.origin = None; self.current = None; self.result_rect = None; self.title = title

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton: self.origin = e.pos(); self.current = self.origin; self.update()
        elif e.button() == Qt.RightButton: self.reject()

    def mouseMoveEvent(self, e):
        if self.origin: self.current = e.pos(); self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.origin:
            x = min(self.origin.x(), e.pos().x()); y = min(self.origin.y(), e.pos().y())
            w = abs(self.origin.x() - e.pos().x()); h = abs(self.origin.y() - e.pos().y())
            if w > 5 and h > 5: self.result_rect = (x, y, w, h); self.accept()
            else: self.origin = None; self.update()

    def paintEvent(self, e):
        p = QPainter(self); p.fillRect(self.rect(), QColor(0,0,0,100))
        if self.origin and self.current:
            x = min(self.origin.x(), self.current.x()); y = min(self.origin.y(), self.current.y())
            w = abs(self.origin.x() - self.current.x()); h = abs(self.origin.y() - self.current.y())
            p.setCompositionMode(QPainter.CompositionMode_Clear); p.fillRect(x,y,w,h,Qt.transparent)
            p.setCompositionMode(QPainter.CompositionMode_SourceOver)
            p.setPen(QPen(Qt.red, 2)); p.drawRect(x,y,w,h)
        p.setPen(Qt.yellow); font = p.font(); font.setPointSize(16); p.setFont(font)
        p.drawText(self.rect(), Qt.AlignCenter, self.title)

class HPMPBar(QFrame):
    def __init__(self, color_rgb, parent=None):
        super().__init__(parent); self.setFixedSize(248, 15); self.ratio = 1.0; self.col = QColor(*color_rgb)
        self.setStyleSheet("border: 1px solid #444; background: #000;")
    def set_ratio(self, r): self.ratio = max(0.0, min(1.0, r)); self.update()
    def paintEvent(self, e):
        super().paintEvent(e); p = QPainter(self); r = self.rect()
        w = int(r.width() * self.ratio); p.fillRect(r.x(), r.y(), w, r.height(), self.col)
        p.setPen(Qt.white); p.drawText(r, Qt.AlignCenter, f"{self.ratio*100:.1f}%")

class HPMPAreaVisualizer(QWidget):
    def __init__(self, region_data, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowFlags(self.windowFlags() | Qt.WindowTransparentForInput)
        if isinstance(region_data, (list, tuple)) and len(region_data) == 4:
            self.setGeometry(*region_data); self.show()
        else: self.close()
    def paintEvent(self, e):
        p = QPainter(self); p.setPen(QPen(Qt.green, 4)); p.setBrush(Qt.NoBrush)
        p.drawRect(self.rect().adjusted(2, 2, -3, -3))

# =========================================================
# 3. GUI (AYAR PENCERESİ)
# =========================================================
class PetSettingsDialog(QDialog):
    def __init__(self, parent, config, macro):
        super().__init__(parent)
        self.setWindowTitle("PET HP/MP/FEED/ATAK AYARLARI")
        self.setModal(True); self.config = config
        self.macro = macro
        self._key_capture = None
        self.visualizer = None
        
        main = QVBoxLayout(self); grid = QGridLayout()
        main.addLayout(grid)

        # 1. Hotkey
        grid.addWidget(QLabel("BAŞLATMA TUŞU:"), 0, 0)
        self.txt_hotkey = QLineEdit(self.config.get("hotkey", "F")); self.txt_hotkey.setReadOnly(True)
        btn_hk = QPushButton("SEÇ"); btn_hk.clicked.connect(self.cap_hotkey)
        h = QHBoxLayout(); h.addWidget(self.txt_hotkey); h.addWidget(btn_hk)
        grid.addLayout(h, 0, 1, 1, 4)

        # 2. Headers
        grid.addWidget(QLabel("AKTİF"), 1, 0); grid.addWidget(QLabel("ALT TUŞU"), 1, 1)
        grid.addWidget(QLabel("TETİK (%)"), 1, 2)

        # 3. HP ROW
        self.chk_hp = QCheckBox("HP POT"); self.chk_hp.setChecked(self.config.get("hp_enabled", True))
        self.hp_alt = self._create_alt_combo(self.config.get("hp_alt_num", 1))
        self.hp_trig = self._create_spin(self.config.get("hp_trigger", 0.50)*100)
        grid.addWidget(self.chk_hp, 2, 0); grid.addWidget(self.hp_alt, 2, 1)
        grid.addWidget(self.hp_trig, 2, 2)

        # 4. MP ROW
        self.chk_mp = QCheckBox("MP POT"); self.chk_mp.setChecked(self.config.get("mp_enabled", True))
        self.mp_alt = self._create_alt_combo(self.config.get("mp_alt_num", 2))
        self.mp_trig = self._create_spin(self.config.get("mp_trigger", 0.30)*100)
        grid.addWidget(self.chk_mp, 3, 0); grid.addWidget(self.mp_alt, 3, 1)
        grid.addWidget(self.mp_trig, 3, 2)

        # 5. FEED ROW (Yaprak/Süt/Ekmek)
        self.chk_feed = QCheckBox("FEED"); self.chk_feed.setChecked(self.config.get("feed_enabled", True))
        self.feed_combo = QComboBox()
        self.feed_combo.addItem("Yaprak", 1)
        self.feed_combo.addItem("Süt", 2)
        self.feed_combo.addItem("Ekmek", 3)
        self.feed_combo.setCurrentIndex(self.config.get("feed_type", 1) - 1)
        self.feed_trig = self._create_spin(self.config.get("feed_trigger", 0.40)*100)
        grid.addWidget(self.chk_feed, 4, 0); grid.addWidget(self.feed_combo, 4, 1)
        grid.addWidget(self.feed_trig, 4, 2)

        # ========== 6. ATAK BÖLÜMÜ (YENİ) ==========
        attack_group = QGroupBox("ATAK AYARLARI")
        attack_layout = QGridLayout(attack_group)
        
        # Atak Yap Checkbox
        self.chk_attack = QCheckBox("ATAK YAP")
        self.chk_attack.setChecked(self.config.get("attack_enabled", False))
        self.chk_attack.setStyleSheet("font-weight: bold; color: #ff6666;")
        attack_layout.addWidget(self.chk_attack, 0, 0, 1, 2)
        
        # Z Süresi
        attack_layout.addWidget(QLabel("Z Süresi (sn):"), 1, 0)
        self.z_duration_spin = QDoubleSpinBox()
        self.z_duration_spin.setRange(0.01, 2.0)
        self.z_duration_spin.setSingleStep(0.01)
        self.z_duration_spin.setDecimals(2)
        self.z_duration_spin.setValue(self.config.get("z_duration", 0.05))
        attack_layout.addWidget(self.z_duration_spin, 1, 1)
        
        # Alt+2 Süresi
        attack_layout.addWidget(QLabel("Alt+2 Süresi (sn):"), 2, 0)
        self.alt2_duration_spin = QDoubleSpinBox()
        self.alt2_duration_spin.setRange(0.01, 2.0)
        self.alt2_duration_spin.setSingleStep(0.01)
        self.alt2_duration_spin.setDecimals(2)
        self.alt2_duration_spin.setValue(self.config.get("alt2_duration", 0.05))
        attack_layout.addWidget(self.alt2_duration_spin, 2, 1)
        
        # Atak Aralığı
        attack_layout.addWidget(QLabel("Atak Aralığı (sn):"), 3, 0)
        self.attack_interval_spin = QDoubleSpinBox()
        self.attack_interval_spin.setRange(0.1, 10.0)
        self.attack_interval_spin.setSingleStep(0.1)
        self.attack_interval_spin.setDecimals(1)
        self.attack_interval_spin.setValue(self.config.get("attack_interval", 1.0))
        attack_layout.addWidget(self.attack_interval_spin, 3, 1)
        
        main.addWidget(attack_group)
        # ========== ATAK BÖLÜMÜ SONU ==========

        # 7. ALAN SEÇİMİ
        btn_area = QPushButton("HP/MP/SATIATION ALANINI SEÇ"); btn_area.clicked.connect(self.sel_area)
        main.addWidget(btn_area)
        
        btn_show = QPushButton("SEÇİLEN ALANI GÖSTER"); btn_show.clicked.connect(self.toggle_area_visualizer)
        main.addWidget(btn_show)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        main.addWidget(btns)

    def _create_alt_combo(self, val):
        c = QComboBox()
        for i in range(1, 10): c.addItem(f"Alt+{i}", i)
        c.setCurrentIndex(val - 1)
        return c
    
    def _create_spin(self, val):
        s = QDoubleSpinBox(); s.setRange(10, 100); s.setValue(val); return s

    def cap_hotkey(self): self._key_capture = True; self.txt_hotkey.setText("BAS...")
    def keyPressEvent(self, e):
        if self._key_capture:
            t = e.text().upper(); 
            if not t and e.key() >= Qt.Key_F1: t = f"F{e.key()-Qt.Key_F1+1}"
            if t: self.txt_hotkey.setText(t); self._key_capture = False
        else: super().keyPressEvent(e)

    def sel_area(self):
        self.hide(); time.sleep(0.2)
        d = RectSelectDialog(None, "HP/MP/SATIATION ALANINI SEÇİN")
        if d.exec_() == QDialog.Accepted:
            self.config["hp_region"] = list(d.result_rect)
            if self.macro:
                self.macro.update_config(self.config)
            QMessageBox.information(self, "Başarılı", "Alan kaydedildi.")
        self.show()

    def toggle_area_visualizer(self):
        region = self.config.get("hp_region")
        if not region: return QMessageBox.warning(self, "Uyarı", "Önce alan seçin.")
        
        if self.visualizer:
            self.visualizer.close(); self.visualizer = None
        else:
            self.visualizer = HPMPAreaVisualizer(region); self.visualizer.show()

    def accept(self):
        """asas.py ile aynı mantık - result_config oluştur"""
        if self.visualizer: self.visualizer.close()
        
        # result_config oluştur (asas.py ile aynı pattern)
        self.result_config = {
            "hotkey": self.txt_hotkey.text(),
            "hp_enabled": self.chk_hp.isChecked(),
            "hp_alt_num": self.hp_alt.currentData(),
            "hp_trigger": self.hp_trig.value() / 100,
            "mp_enabled": self.chk_mp.isChecked(),
            "mp_alt_num": self.mp_alt.currentData(),
            "mp_trigger": self.mp_trig.value() / 100,
            "feed_enabled": self.chk_feed.isChecked(),
            "feed_type": self.feed_combo.currentData(),
            "feed_trigger": self.feed_trig.value() / 100,
            # ATAK AYARLARI (YENİ)
            "attack_enabled": self.chk_attack.isChecked(),
            "z_duration": self.z_duration_spin.value(),
            "alt2_duration": self.alt2_duration_spin.value(),
            "attack_interval": self.attack_interval_spin.value(),
        }
        
        # hp_region varsa koru
        if self.config.get("hp_region"):
            self.result_config["hp_region"] = self.config.get("hp_region")
        
        super().accept()

# =========================================================
# 4. WIDGET (ANA KART)
# =========================================================
# =========================================================
# 4. WIDGET (ANA KART) - TEMİZLENMİŞ HALİ
# =========================================================
class PetMacroWidget(QFrame):
    update_signal = pyqtSignal()

    def __init__(self, parent=None, macro_instance=None, config=None):
        super().__init__(parent)
        self.macro = macro_instance or SmartPetMacro()
        self.config = config or {}
        self.macro.update_config(self.config)
        
        self.listen_active = False
        self._hooks = []
        
        self.hp_bar = HPMPBar((255, 0, 0))
        self.mp_bar = HPMPBar((0, 0, 255))
        self.satiation_bar = HPMPBar((255, 165, 0))
        
        self.timer = QTimer(self); self.timer.timeout.connect(self.update_ui); self.timer.start(100)
        self.update_signal.connect(self._safe_update)
        self.setup_ui(); self._safe_update()

    def setup_ui(self):
        # 1. Çerçeve Ayarları
        self.setFrameShape(QFrame.Box)
        self.setMaximumWidth(260)
        self.setStyleSheet("QFrame { background: #101010; border: 1px solid #444; border-radius: 4px; }")
        
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(4)

        # 2. İKONLU BAŞLIK ALANI (Clan ile aynı yapı)
        h_header = QHBoxLayout()
        h_header.setSpacing(6)
        
        # İkon
        icon_label = QLabel()
        icon_label.setFixedSize(30, 30)
        icon_label.setStyleSheet("border: none; background: transparent;")
        
        # İkon dosyası kontrolü (icons/gui/pet.png var mı diye bakar)
        import os
        icon_path = os.path.join("icons", "pet.png")
        if not os.path.exists(icon_path):
            # Alternatif yol (bazen düz icons klasöründe olabilir)
            icon_path = os.path.join("icons", "pet.png")
            
        if os.path.exists(icon_path):
            pix = QPixmap(icon_path)
            icon_label.setPixmap(pix.scaled(30, 30, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        
        # Başlık Metni
        title = QLabel("PET BESLEME/ATAK")
        title.setObjectName("MinorHeaderLabel") # Yazı stili (CSS'den gelir)
        
        # Yatay düzene ekle: İkon - Boşluk - Başlık
        h_header.addWidget(icon_label)
        h_header.addStretch() # Araya esnek boşluk (Clan'daki gibi sağa yaslamak için)
        h_header.addWidget(title)
        
        v.addLayout(h_header)

        # 3. Dinleme Butonu
        self.btn_listen = QPushButton("TUŞ DİNLEMEYİ BAŞLAT")
        self.btn_listen.setObjectName("ThreeFiveListenButton")
        self.btn_listen.clicked.connect(self.toggle_listen)
        v.addWidget(self.btn_listen)

        # 4. Durum
        self.lbl_status = QLabel("PASİF")
        self.lbl_status.setObjectName("MinorStatusLabel")
        v.addWidget(self.lbl_status)

        # 5. Barlar
        v.addWidget(self.hp_bar)
        v.addWidget(self.mp_bar)
        v.addWidget(self.satiation_bar)

        # 6. Alt Kısım (Tuş ve Ayarlar)
        r = QHBoxLayout()
        r.addWidget(QLabel("TUŞ:"))
        
        self.lbl_key = QLabel(self.config.get("hotkey", "F"))
        self.lbl_key.setObjectName("HotkeyLabel")
        r.addWidget(self.lbl_key)
        
        btn_set = QPushButton("⚙ AYARLAR")
        btn_set.setObjectName("MinorSettingsButton")
        btn_set.clicked.connect(self.open_settings)
        r.addWidget(btn_set)
        
        v.addLayout(r)

    def open_settings(self):
        """asas.py ile aynı mantık - result_config kullan"""
        dlg = PetSettingsDialog(self, self.config, self.macro)
        if dlg.exec_():
            # result_config'i config'e update et
            self.config.update(dlg.result_config)
            self.macro.update_config(self.config)
            self.lbl_key.setText(self.config.get("hotkey", "F"))
            
            # Hotkey değiştiyse yeniden başlat
            if self.listen_active:
                self.toggle_listen()
                self.toggle_listen()

    def toggle_listen(self):
        if not keyboard: return QMessageBox.warning(self, "Hata", "keyboard modülü yüklü değil")
        if not self.listen_active:
            hk = self.config.get("hotkey", "F").lower()
            try:
                self._hooks.append(keyboard.on_press_key(hk, lambda e: self.macro.toggle(), suppress=False))
                self.listen_active = True
            except: self.listen_active = False
        else:
            for h in self._hooks: 
                try: keyboard.unhook(h)
                except: pass
            self._hooks = []; self.listen_active = False; self.macro.stop()
        self._safe_update()

    def update_ui(self):
        self.hp_bar.set_ratio(self.macro.hp_ratio)
        self.mp_bar.set_ratio(self.macro.mp_ratio)
        self.satiation_bar.set_ratio(self.macro.satiation_ratio)
        # _update_attack_label ÇAĞRISI KALDIRILDI

    def _safe_update(self):
        if not self.listen_active:
            self.lbl_status.setText("PASİF"); self.lbl_status.setStyleSheet("color:#ff5555;font-weight:bold;")
            self.btn_listen.setText("TUŞ DİNLEMEYİ BAŞLAT"); self.btn_listen.setProperty("active", False)
        else:
            txt = "ÇALIŞIYOR" if self.macro.is_running else "BEKLİYOR"
            col = "#00ff4c" if self.macro.is_running else "#ffff55"
            self.lbl_status.setText(txt); self.lbl_status.setStyleSheet(f"color:{col};font-weight:bold;")
            self.btn_listen.setText("TUŞ DİNLEMEYİ DURDUR"); self.btn_listen.setProperty("active", True)
        
        self.btn_listen.style().unpolish(self.btn_listen); self.btn_listen.style().polish(self.btn_listen)
        if self.listen_active: QTimer.singleShot(200, self._safe_update)
