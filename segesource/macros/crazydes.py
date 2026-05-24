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

# --- crazydes.py ---

import threading
import time
import os
import cv2
import numpy as np
import mss
import pyautogui
import ctypes

# PyQt5
from PyQt5.QtWidgets import (
    QDialog, QGridLayout, QLabel, QComboBox, 
    QLineEdit, QPushButton, QDoubleSpinBox, 
    QDialogButtonBox, QHBoxLayout, QWidget,
    QFrame, QVBoxLayout, QSizePolicy, QMessageBox,
    QCheckBox, QApplication, QRubberBand, QGroupBox
)
from PyQt5.QtGui import QPixmap, QColor, QCursor, QPainter, QPen, QBrush
from PyQt5.QtCore import Qt, pyqtSignal, QPoint, QRect, QSize, QTimer

# DPI FIX
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except:
    try: ctypes.windll.user32.SetProcessDPIAware()
    except: pass

try:
    import keyboard
except ImportError:
    keyboard = None

# Driver
try:
    from clicksend import KeyboardDriver as _ClicksendKeyboardDriver
    from clicksend import MouseDriver as _ClicksendMouseDriver
except ImportError:
    _ClicksendKeyboardDriver = None
    _ClicksendMouseDriver = None

# ---------------------------------------------------------
# DRIVER VE MOUSE FONKSİYONLARI
# ---------------------------------------------------------
DIGIT_SCANCODES = {
    1: 0x02, 2: 0x03, 3: 0x04, 4: 0x05, 5: 0x06,
    6: 0x07, 7: 0x08, 8: 0x09, 9: 0x0A, 0: 0x0B,
}
F_SCANCODES = {
    1: 0x3B, 2: 0x3C, 3: 0x3D, 4: 0x3E,
    5: 0x3F, 6: 0x40, 7: 0x41, 8: 0x42,
    9: 0x43, 10: 0x44, 11: 0x57, 12: 0x58
}

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP   = 0x0004

def _move_mouse_absolute(x, y):
    try: ctypes.windll.user32.SetCursorPos(int(x), int(y))
    except: pyautogui.moveTo(x, y)

def _win32_click():
    ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.05)
    ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

def _driver_tap(scan_code, duration=0.05):
    if _ClicksendKeyboardDriver:
        if not hasattr(_driver_tap, "kb"): _driver_tap.kb = _ClicksendKeyboardDriver()
        try: _driver_tap.kb.tusbas(scan_code, duration)
        except: pass

def _driver_click(x, y):
    _move_mouse_absolute(x, y)
    time.sleep(0.05)
    if _ClicksendMouseDriver:
        if not hasattr(_driver_click, "ms"): _driver_click.ms = _ClicksendMouseDriver()
        try: _driver_click.ms.leftclick()
        except: _win32_click()
    else: _win32_click()

# =========================================================
# YARDIMCI ARAÇLAR
# =========================================================
class RegionSelector(QWidget):
    captured = pyqtSignal(tuple)
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
        painter.fillRect(self.rect(), QColor(0, 0, 0, 80))
        if self.start_pos and self.end_pos:
            rect = QRect(self.start_pos, self.end_pos).normalized()
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            painter.fillRect(rect, Qt.transparent)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            painter.setPen(QPen(Qt.green, 2)); painter.drawRect(rect)

    def mousePressEvent(self, e): self.start_pos = e.pos(); self.end_pos = self.start_pos; self.update()
    def mouseMoveEvent(self, e): 
        if self.start_pos: self.end_pos = e.pos(); self.update()
    def mouseReleaseEvent(self, e):
        self.end_pos = e.pos()
        rect = QRect(self.start_pos, self.end_pos).normalized()

        # GLOBAL koordinata çevir
        top_left = self.mapToGlobal(rect.topLeft())

        if rect.width() > 5:
            self.captured.emit((
                top_left.x(),
                top_left.y(),
                rect.width(),
                rect.height()
            ))

        self.close()

class PointSelector(QWidget):
    captured = pyqtSignal(tuple)
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        total_rect = QRect()
        for screen in QApplication.screens():
            total_rect = total_rect.united(screen.geometry())
        self.setGeometry(total_rect)
        self.setCursor(Qt.CrossCursor)

    def paintEvent(self, event):
        p = QPainter(self); p.fillRect(self.rect(), QColor(0, 0, 0, 60))
        p.setPen(Qt.yellow); font = p.font(); font.setPointSize(14); font.setBold(True); p.setFont(font)
        p.drawText(self.rect(), Qt.AlignCenter, "KOORDİNAT ALMAK ISTEDIGINIZ YERE TIKLAYIN (SOL TIK)")

    def mousePressEvent(self, e):
        global_pos = QCursor.pos()
        self.captured.emit((global_pos.x(), global_pos.y()))
        self.close()

# =========================================================
# 1. LOGIC (MAKRO MOTORU)
# =========================================================
class CrazyDesMacro:
    def __init__(self):
        self.config = {}
        self._running = False
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        
        self.des_in_progress = False
        self._hp_ref = None  
        
        # YENİ: Kilit Mekanizması
        self.des_triggered = False # True ise bir daha basmaz

    def update_config(self, cfg):
        with self._lock: 
            self.config = cfg.copy()
            self._hp_ref = None 
            self.des_triggered = False # Ayar değişince sıfırla

    def start(self):
        if self._running: return
        self._stop_event.clear()
        self._running = True
        self._hp_ref = None 
        self.des_triggered = False
        threading.Thread(target=self._hp_loop, daemon=True).start()
        print("[CRAZY DES] Motor Başladı.")

    def stop(self):
        self._stop_event.set()
        self._running = False
        print("[CRAZY DES] Motor Durduruldu.")

    @property
    def is_running(self): return self._running

    def trigger_manual(self):
        if not self._running: return
        if not self.config.get("manual_active", False): return
        
        target = self.config.get("coord_manual")
        if target:
            print("[CRAZY DES] Manuel Tuş Basıldı.")
            _driver_click(target[0], target[1])
            self._cast_des()

    def _hp_loop(self):
        """HP Takip Döngüsü (Akıllı Kilit Sistemi)"""
        last_print = 0
        
        while not self._stop_event.is_set():
            if self.config.get("hp_active", False) and not self.des_in_progress:
                try:
                    region = self.config.get("hp_region")
                    if region:
                        x, y, w, h = region
                        with mss.mss() as sct:
                            sct_img = sct.grab({"left": int(x), "top": int(y), "width": int(w), "height": int(h)})
                            img_np = np.array(sct_img)
                        
                        # 1. HP Hesapla
                        hp_count, _ = self._count_hp_pixels(img_np)
                        print(f"-> Görülen Kırmızı Piksel: {hp_count} | Referans (Max): {self._hp_ref}")
                        
                        if hp_count > 0: self._update_hp_ref(hp_count)
                        
                        current_ratio = 1.0
                        if self._hp_ref and self._hp_ref > 0:
                            current_ratio = hp_count / self._hp_ref
                        
                        hp_pct = current_ratio * 100.0
                        threshold = self.config.get("hp_threshold", 90)
                        
                        # 2. DEBUG BİLGİSİ
                        if time.time() - last_print > 1.0:
                            status = "KİLİTLİ (Canın Dolmasını Bekliyor)" if self.des_triggered else "HAZIR"
                            print(f"[DEBUG] HP: %{hp_pct:.1f} | Limit: %{threshold} | Mod: {status}")
                            last_print = time.time()
                        
                        # 3. MANTIK ZİNCİRİ
                        
                        # DURUM A: Can Kritik Seviyenin Üstüne Çıktı -> RESETLE
                        if hp_pct > threshold + 2: # +2 Buffer ekledik ki sınırda titremesin
                            if self.des_triggered:
                                print("[CRAZY DES] Can Toparlandı -> SİSTEM SIFIRLANDI.")
                                self.des_triggered = False # Kilidi Aç
                        
                        # DURUM B: Can Kritik Seviyenin Altında
                        elif 0.1 < hp_pct <= threshold:
                            # Eğer daha önce basılmadıysa (Kilit açık)
                            if not self.des_triggered:
                                
                                # Skillin durumunu kontrol et (Pembe mi?)
                                is_pink = self._is_skill_pink_check()
                                
                                if is_pink:
                                    # Skill zaten CD'de, basmaya gerek yok
                                    # Kendi kendine basılmış veya manuel basılmış olabilir
                                    # Sistemi kilitle ki spamlamasın
                                    if not self.des_triggered:
                                        print("[CRAZY DES] Skill Zaten CD'de (Pembe). İşlem Pas geçiliyor.")
                                        self.des_triggered = True
                                else:
                                    # Skill Müsait -> BAS
                                    print(f"[CRAZY DES] HP DÜŞTÜ (%{hp_pct:.1f})! DES ATILIYOR...")
                                    self._perform_auto_des()
                                    self.des_triggered = True # KİLİTLE (Can dolana kadar bir daha basma)

                except Exception as e:
                    print(f"Loop Hatası: {e}")
            
            time.sleep(0.08)

    def _count_hp_pixels(self, img_np):
        img_bgr = cv2.cvtColor(img_np, cv2.COLOR_BGRA2BGR)
        img_hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
        S_MIN = 80; V_MIN = 80 
        lower_1 = np.array([0, S_MIN, V_MIN]); upper_1 = np.array([25, 255, 255])
        lower_2 = np.array([160, S_MIN, V_MIN]); upper_2 = np.array([180, 255, 255])
        lower_3 = np.array([10, S_MIN, V_MIN]); upper_3 = np.array([40, 255, 255])
        lower_4 = np.array([130, S_MIN, V_MIN]); upper_4 = np.array([170, 255, 255])
        mask1 = cv2.inRange(img_hsv, lower_1, upper_1)
        mask2 = cv2.inRange(img_hsv, lower_2, upper_2)
        mask3 = cv2.inRange(img_hsv, lower_3, upper_3)
        mask4 = cv2.inRange(img_hsv, lower_4, upper_4)
        mask = cv2.bitwise_or(mask1, mask2); mask = cv2.bitwise_or(mask, mask3); mask = cv2.bitwise_or(mask, mask4)
        red_pixels = cv2.countNonZero(mask)
        print(f"[PIXEL DEBUG] Bulunan Kırmızı Piksel: {red_pixels}") 
        total_pixels = img_np.shape[0] * img_np.shape[1]
        return red_pixels, total_pixels

    def _update_hp_ref(self, cur):
        if self._hp_ref is None: self._hp_ref = cur; return
        if cur >= self._hp_ref * 0.97: self._hp_ref = 0.90 * self._hp_ref + 0.10 * cur 

    def _perform_auto_des(self):
        self.des_in_progress = True
        t1 = self.config.get("coord_t1")
        t2 = self.config.get("coord_t2")
        
        # Hedef 1'i dene
        if t1:
            print(f"-> Hedef 1'e gidiliyor...")
            _driver_click(t1[0], t1[1])
            self._cast_des()
            time.sleep(0.3)
            # Eğer skill pembeleştiyse (CD'ye girdiyse) başarılı
            if self._is_skill_pink_check():
                print("-> Des Başarılı (CD).")
                self.des_in_progress = False; return

        # Hedef 1 olmadıysa Hedef 2
        if t2:
            print("-> Hedef 2'ye gidiliyor...")
            _driver_click(t2[0], t2[1])
            self._cast_des()
        
        self.des_in_progress = False

    def _cast_des(self):
        f = self.config.get("des_f", 0)
        d = self.config.get("des_d", 1)
        if f > 0:
            sc = F_SCANCODES.get(f)
            if sc: _driver_tap(sc, 0.05); time.sleep(0.05)
        sc_d = DIGIT_SCANCODES.get(d)
        if sc_d: _driver_tap(sc_d, 0.05)

    def _is_skill_pink_check(self):
        """Skill ikonunu anlık kontrol eder. Pembeyse True döner."""
        r = self.config.get("skill_region")
        if not r: return False
        x, y, w, h = r
        if w <= 0 or h <= 0: return False
        try:
            with mss.mss() as sct:
                sct_img = sct.grab({"left": int(x), "top": int(y), "width": int(w), "height": int(h)})
                img = np.array(sct_img)
            hsv = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            hsv = cv2.cvtColor(hsv, cv2.COLOR_BGR2HSV)
            # Pembe/Mor Maskesi
            mask = cv2.inRange(hsv, np.array([140, 50, 50]), np.array([170, 255, 255]))
            ratio = cv2.countNonZero(mask) / (w * h)
            return ratio > 0.30
        except: return False

# =========================================================
# 2. GUI (AYAR PENCERESİ)
# =========================================================
class CrazyDesSettingsDialog(QDialog):
    def __init__(self, parent, config, macro):
        super().__init__(parent)
        self.setWindowTitle("CRAZY DES AYARLARI")
        self.setModal(True)
        self.resize(450, 550)
        self.config = config; self.macro = macro; self.capture_hotkey = False
        
        # Ana Layout
        main = QVBoxLayout(self)
        
        # 1. HP AYARLARI
        grp_hp = QGroupBox("1. HP ve Tetikleyici")
        l_hp = QGridLayout(grp_hp)
        
        self.chk_hp = QCheckBox("Otomatik HP Takibi Aktif")
        self.chk_hp.setChecked(config.get("hp_active", False))
        l_hp.addWidget(self.chk_hp, 0, 0, 1, 2)
        
        self.lbl_hp = QLabel("HP Alanı: " + ("✅ SEÇİLİ" if config.get("hp_region") else "❌ SEÇİLMEDİ"))
        self.lbl_hp.setStyleSheet("color: #00ff4c" if config.get("hp_region") else "color: #ff5555")
        b_hp = QPushButton("HP BARINI SEÇ")
        b_hp.clicked.connect(lambda: self.sel_reg("hp_region", self.lbl_hp))
        l_hp.addWidget(self.lbl_hp, 1, 0)
        l_hp.addWidget(b_hp, 1, 1)
        
        l_hp.addWidget(QLabel("Tetiklenme Limiti (%):"), 2, 0)
        self.spin_hp = QDoubleSpinBox()
        self.spin_hp.setRange(1, 99)
        self.spin_hp.setValue(config.get("hp_threshold", 90))
        l_hp.addWidget(self.spin_hp, 2, 1)
        
        main.addWidget(grp_hp)
        
        # 2. SKILL VE HEDEF
        grp_skill = QGroupBox("2. Skill ve Hedef Konumları")
        l_sk = QGridLayout(grp_skill)
        
        self.lbl_sk = QLabel("Skill İkonu: " + ("✅ SEÇİLİ" if config.get("skill_region") else "❌ SEÇİLMEDİ"))
        self.lbl_sk.setStyleSheet("color: #00ff4c" if config.get("skill_region") else "color: #ff5555")
        b_sk = QPushButton("SKILL İKONUNU SEÇ")
        b_sk.clicked.connect(lambda: self.sel_reg("skill_region", self.lbl_sk))
        l_sk.addWidget(self.lbl_sk, 0, 0)
        l_sk.addWidget(b_sk, 0, 1)
        
        # Hedef 1
        self.lbl_t1 = QLabel(f"Hedef 1: {config.get('coord_t1','YOK')}")
        b_t1 = QPushButton("HEDEF 1 SEÇ")
        b_t1.clicked.connect(lambda: self.sel_pt("coord_t1", self.lbl_t1))
        l_sk.addWidget(self.lbl_t1, 1, 0); l_sk.addWidget(b_t1, 1, 1)
        
        # Hedef 2
        self.lbl_t2 = QLabel(f"Hedef 2: {config.get('coord_t2','YOK')}")
        b_t2 = QPushButton("HEDEF 2 SEÇ")
        b_t2.clicked.connect(lambda: self.sel_pt("coord_t2", self.lbl_t2))
        l_sk.addWidget(self.lbl_t2, 2, 0); l_sk.addWidget(b_t2, 2, 1)

        main.addWidget(grp_skill)
        
        # 3. TUŞLAR VE MANUEL (DÜZELTİLMİŞ HALİ)
        # ---------------------------------------------------------
        grp_key = QGroupBox("3. Tuş Atamaları ve Manuel Mod")
        l_key = QGridLayout(grp_key)
        
        # --- SATIR 0: Skill Sayfası (F) ---
        self.cmb_f = QComboBox(); self.cmb_f.addItem("F YOK", 0)
        for i in range(1,13): self.cmb_f.addItem(f"F{i}", i)
        # Ayarı çek
        idx = self.cmb_f.findData(config.get("des_f", 0))
        self.cmb_f.setCurrentIndex(idx if idx>=0 else 0)
        
        l_key.addWidget(QLabel("Skill Sayfası (F):"), 0, 0)
        l_key.addWidget(self.cmb_f, 0, 1)

        # --- SATIR 2: Des Tuşu (Des Adet/Sayı) ---
        self.cmb_des = QComboBox()
        for i in range(10): self.cmb_des.addItem(str(i), i)
        # Farklı bir ayar isminden çekiyoruz (des_d)
        self.cmb_des.setCurrentText(str(config.get("des_d", "1")))
        
        l_key.addWidget(QLabel("Des Tusu:"), 2, 0)
        l_key.addWidget(self.cmb_des, 2, 1)

        # --- SATIR 3: Manuel Tetik Tuşu ---
        self.txt_hk = QLineEdit(config.get("hotkey_manual", "G")); self.txt_hk.setReadOnly(True)
        b_hk = QPushButton("TUŞ SEÇ"); b_hk.clicked.connect(self.capt_hk)
        
        l_key.addWidget(QLabel("Tetik Tuşu:"), 3, 0)
        h_hk = QHBoxLayout(); h_hk.addWidget(self.txt_hk); h_hk.addWidget(b_hk)
        l_key.addLayout(h_hk, 3, 1)
        
        # --- SATIR 4: Manuel Hedef ---
        self.lbl_tm = QLabel(f"Manuel Hedef: {config.get('coord_manual','YOK')}")
        b_tm = QPushButton("MANUEL NOKTA SEÇ")
        b_tm.clicked.connect(lambda: self.sel_pt("coord_manual", self.lbl_tm))
        l_key.addWidget(self.lbl_tm, 4, 0); l_key.addWidget(b_tm, 4, 1)
        
        # --- SATIR 5: Checkbox ---
        self.chk_man = QCheckBox("Manuel Tuş Modu Aktif")
        self.chk_man.setChecked(config.get("manual_active", True))
        l_key.addWidget(self.chk_man, 5, 0, 1, 2)
        
        main.addWidget(grp_key)
        
        # Butonlar
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        main.addWidget(btns)

    def sel_reg(self, k, l): self.hide(); self.s=RegionSelector(); self.s.captured.connect(lambda r: self.ok_reg(k,r,l)); self.s.show()
    def ok_reg(self, k, r, l): self.show(); self.config[k]=r; l.setText("✅ SEÇİLDİ"); l.setStyleSheet("color:#00ff4c")
    def sel_pt(self, k, l): self.hide(); self.p=PointSelector(); self.p.captured.connect(lambda p: self.ok_pt(k,p,l)); self.p.show()
    def ok_pt(self, k, p, l): self.show(); self.config[k]=p; l.setText(f"✅ {p}"); l.setStyleSheet("color: #00ff4c; font-weight: bold;")
    def capt_hk(self): self.txt_hk.setText("..."); self.capture_hotkey = True; self.txt_hk.setFocus()
    def keyPressEvent(self, e): 
        if self.capture_hotkey:
            k = e.text().upper()
            if not k and e.key() == Qt.Key_CapsLock: k = "CAPS LOCK"
            if k: self.txt_hk.setText(k); self.capture_hotkey=False
        else: super().keyPressEvent(e)
    def accept(self):
        # BURADA İKİSİNİ AYRI AYRI KAYDEDİYORUZ (skill_d ve des_d)
        self.config.update({
            "hp_threshold": self.spin_hp.value(),
            "des_f": self.cmb_f.currentData(),
            "des_d": int(self.cmb_des.currentText()),     # Des Tuşu
            "hotkey_manual": self.txt_hk.text(),
            "hp_active": self.chk_hp.isChecked(),
            "manual_active": self.chk_man.isChecked()
        })
        self.macro.update_config(self.config)
        super().accept()

# =========================================================
# 3. WIDGET
# =========================================================
class CrazyDesWidget(QFrame):
    update_signal = pyqtSignal()
    
    def __init__(self, parent=None, macro_instance=None, config=None):
        super().__init__(parent)
        self.macro = macro_instance or CrazyDesMacro()
        self.config = config or {}
        self.macro.update_config(self.config)
        self.listen_active = False
        self.manual_hook = None
        
        self.update_signal.connect(self._safe_update_status)
        self.setup_ui()
        self._safe_update_status()

    def setup_ui(self):
        # Standart Stil ve Boyut
        self.setFrameShape(QFrame.Box)
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

        # Header
        h = QHBoxLayout()
        h.setSpacing(6)
        
        # İkon (Placeholder emoji veya ikon)
        icon_lbl = QLabel()
        icon_lbl.setFixedSize(25, 25)
        icon_lbl.setAlignment(Qt.AlignCenter)
        
        # Resim yolunu belirle
        icon_path = os.path.join("icons", "wari", "des.png")
        pix = QPixmap(icon_path)
        
        if not pix.isNull():
            # Resim varsa yükle ve boyutlandır
            icon_lbl.setPixmap(pix.scaled(25, 25, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            # Resim yoksa kalkan emojisi koy (Yedek)
            icon_lbl.setText("🛡️")
            icon_lbl.setStyleSheet("font-size:20px; border:none; background:transparent;")
            
        h.addWidget(icon_lbl)
        
        title = QLabel("CRAZY DES")
        title.setObjectName("MinorHeaderLabel") 
        h.addStretch(1)
        h.addWidget(title)
        
        v.addLayout(h)

        # Listen Button
        self.btn_listen = QPushButton("TUŞ DİNLEMEYİ BAŞLAT")
        self.btn_listen.setObjectName("ThreeFiveListenButton") 
        self.btn_listen.setProperty("active", False)
        self.btn_listen.clicked.connect(self.toggle_listen)
        v.addWidget(self.btn_listen)

        # Status
        self.lbl_status = QLabel("DURUM: PASİF")
        self.lbl_status.setObjectName("MinorStatusLabel")
        v.addWidget(self.lbl_status)

        # Footer
        row = QHBoxLayout()
        row.setSpacing(4)
        row.addWidget(QLabel("AKTİF TUŞ:"))
        
        self.lbl_info = QLabel(self.config.get("hotkey_manual", "G"))
        self.lbl_info.setObjectName("HotkeyLabel")
        self.lbl_info.setAlignment(Qt.AlignCenter)
        row.addWidget(self.lbl_info)

        btn_settings = QPushButton("⚙ AYARLAR")
        btn_settings.setObjectName("MinorSettingsButton")
        btn_settings.setFlat(True)
        btn_settings.clicked.connect(self.open_settings)
        row.addWidget(btn_settings)
        
        v.addLayout(row)

    def open_settings(self):
        dlg = CrazyDesSettingsDialog(self, self.config, self.macro)
        if dlg.exec_() == QDialog.Accepted:
            self.lbl_info.setText(self.config.get("hotkey_manual", "G"))
            if self.listen_active:
                self.toggle_listen()
                self.toggle_listen()

    def toggle_listen(self):
        if not keyboard: return QMessageBox.warning(self, "Hata", "Keyboard modülü yok")
        if not self.listen_active:
            self.listen_active = True
            self.macro.start()
            hk = self.config.get("hotkey_manual", "G").lower()
            if hk and self.config.get("manual_active", False):
                try: self.manual_hook = keyboard.on_press_key(hk, lambda e: self.macro.trigger_manual())
                except Exception as e: print(f"Hook Hatası: {e}")
        else:
            self.listen_active = False
            self.macro.stop()
            if self.manual_hook:
                try: keyboard.unhook(self.manual_hook)
                except: pass
                self.manual_hook = None
        self._safe_update_status()

    def _safe_update_status(self):
        if not self.listen_active:
            self.lbl_status.setText("DURUM: PASİF")
            self.apply_status_style("#ff5555") # Kırmızı
            self.btn_listen.setText("TUŞ DİNLEMEYİ BAŞLAT")
            is_active = False
        else:
            if self.macro.des_triggered:
                self.lbl_status.setText("DURUM: KİLİTLİ (CD)")
                self.apply_status_style("#ffaa00") # Turuncu
            elif self.macro.is_running:
                self.lbl_status.setText("DURUM: HAZIR")
                self.apply_status_style("#00ff4c") # Yeşil
            else:
                self.lbl_status.setText("DURUM: BEKLİYOR")
                self.apply_status_style("#ffff55") # Sarı
                
            self.btn_listen.setText("TUŞ DİNLEMEYİ DURDUR")
            is_active = True
        
        self.btn_listen.setProperty("active", is_active)
        self.btn_listen.style().unpolish(self.btn_listen)
        self.btn_listen.style().polish(self.btn_listen)

        if self.listen_active:
             QTimer.singleShot(500, self._safe_update_status)

    def apply_status_style(self, color):
        self.lbl_status.setStyleSheet(f"color: {color}; font-weight: bold;")
