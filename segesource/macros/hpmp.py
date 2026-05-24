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
from typing import Callable, Literal, Tuple, Optional
import pyautogui
import numpy as np 
import cv2 # KRİTİK: Renk Uzayı Dönüşümü İçin

# PyQt5
from PyQt5.QtWidgets import (
    QDialog, QGridLayout, QLabel, QComboBox, 
    QLineEdit, QPushButton, QDoubleSpinBox, 
    QDialogButtonBox, QHBoxLayout, QWidget,
    QFrame, QVBoxLayout, QSizePolicy, QMessageBox, QCheckBox, QApplication
)
from PyQt5.QtGui import QPixmap, QIcon, QPainter, QColor, QPen, QBrush
from PyQt5.QtCore import Qt, QSize, QRect, pyqtSignal, QTimer

# Interception / clicksend
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
# F1 - F8
F_SCANCODES = {
    1: 0x3B, 2: 0x3C, 3: 0x3D, 4: 0x3E,
    5: 0x3F, 6: 0x40, 7: 0x41, 8: 0x42
}

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
class SmartHpMpMacro:
    def __init__(
        self,
        hp_region=None, mp_region=None, # Tek region kullanılacak ama uyumluluk için tutuyoruz
        hp_f_bar=1, hp_digit=1,
        mp_f_bar=1, mp_digit=2,
        hp_trigger_ratio=0.90, mp_trigger_ratio=0.90,
        hp_cooldown=0.6, mp_cooldown=0.6,
        mode="toggle", scan_interval=0.08,
        send_key=None,
    ):
        # TEK ORTAK BÖLGE TANIMI
        self.common_region = None
        
        self.hp_f_bar = hp_f_bar
        self.hp_digit = hp_digit
        self.mp_f_bar = mp_f_bar
        self.mp_digit = mp_digit
        
        self.hp_trigger_ratio = hp_trigger_ratio
        self.mp_trigger_ratio = mp_trigger_ratio
        
        self.hp_cooldown = hp_cooldown
        self.mp_cooldown = mp_cooldown
        self.scan_interval = scan_interval
        self.mode = mode

        self._send_key = send_key or _default_send_key
        self.hp_enabled = True
        self.mp_enabled = True
        
        self._hp_ref = None
        self._mp_ref = None
        self._hp_last_pot = 0.0
        self._mp_last_pot = 0.0
        
        self.hp_current_ratio = 1.0
        self.mp_current_ratio = 1.0
        
        self._thread = None
        self._stop_event = threading.Event()
        self._running = False
        self._lock = threading.Lock() 

    # --- CANLI DEĞER SETTER'LARI ---
    def set_common_region(self, region):
        with self._lock: 
            self.common_region = region
            self._hp_ref = None # Referansları sıfırla
            self._mp_ref = None
            
    # Eski set_hp/mp_region'ları common_region'a yönlendiriyoruz
    def set_hp_region(self, region): self.set_common_region(region)
    def set_mp_region(self, region): self.set_common_region(region)
        
    def set_hp_pot(self, f_bar, digit): 
        with self._lock: self.hp_f_bar = f_bar; self.hp_digit = digit
        
    def set_mp_pot(self, f_bar, digit): 
        with self._lock: self.mp_f_bar = f_bar; self.mp_digit = digit
        
    def set_trigger_ratios(self, hp, mp): 
        with self._lock: self.hp_trigger_ratio = hp; self.mp_trigger_ratio = mp
        
    def set_mode(self, mode): self.mode = mode

    @property
    def is_running(self): return self._running

    def toggle(self): self.stop() if self._running else self.start()
    
    def hold_down(self): self.start() if not self._running else None
    def hold_up(self): self.stop() if self.mode == "hold" and self._running else None

    def start(self):
        if self._running: return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._running = True
        self._thread.start()
        print("[HPMP] Başladı")

    def stop(self):
        self._stop_event.set()
        self._running = False
        if self._thread:
            self._thread.join(0.5)
            self._thread = None
        print("[HPMP] Durduruldu")

    def _loop(self):
        while not self._stop_event.is_set():
            try: self._check_bars()
            except Exception as e: 
                print("[HPMP] HATA:", e)
                time.sleep(1)
            time.sleep(self.scan_interval)

    # --- KONTROL MEKANİZMASI ---
    def _check_bars(self):
        now = time.time()
        
        # Görüntüyü tek sefer al
        if self.common_region is None: return
        img_np = self._capture_image_np(self.common_region)
        if img_np is None: return

        # HP KONTROL (HSV Sayımı)
        if self.hp_enabled:
            hp_count, total_pixels = self._count_hp_pixels(img_np) 
            
            if total_pixels > 0:
                self._update_hp_ref(hp_count, is_count=True)
                
                if self._hp_ref and self._hp_ref > 0:
                    ratio = hp_count / self._hp_ref
                    self.hp_current_ratio = max(0.0, min(1.0, ratio))
                
                # Eşik kontrolü
                if self._hp_ref and hp_count < self._hp_ref * self.hp_trigger_ratio:
                    if (now - self._hp_last_pot) >= self.hp_cooldown:
                        self._press_pot(self.hp_f_bar, self.hp_digit)
                        self._hp_last_pot = now

        # MP KONTROL (HSV Sayımı)
        if self.mp_enabled:
            mp_count, total_pixels = self._count_mp_pixels(img_np)

            if total_pixels > 0:
                self._update_mp_ref(mp_count, is_count=True)

                if self._mp_ref and self._mp_ref > 0:
                    ratio = mp_count / self._mp_ref
                    self.mp_current_ratio = max(0.0, min(1.0, ratio))
                
                # Eşik kontrolü
                if self._mp_ref and mp_count < self._mp_ref * self.mp_trigger_ratio:
                    if (now - self._mp_last_pot) >= self.mp_cooldown:
                        self._press_pot(self.mp_f_bar, self.mp_digit)
                        self._mp_last_pot = now

    # --- GÖRÜNTÜ YAKALAMA VE RENK SAYMA FONKSİYONLARI ---
    
    def _capture_image_np(self, region):
        """Tek seferde NumPy dizisi olarak ekran görüntüsü alır."""
        if region[2] <= 0 or region[3] <= 0: return None
        try:
            img = pyautogui.screenshot(region=region)
            return np.array(img)
        except: return None
        
    def _count_hp_pixels(self, img_np):
        """HP (Kırmızı/Pembe/Mor) için Renk Tonu (HSV) aralığındaki pikselleri sayar."""
        
        img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR) # OpenCV BGR kullanır
        img_hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
        
        # Tonlar (Hue): Kırmızı, Mor, Turuncu, Pembe
        # S_MIN ve V_MIN: Beyaz sayıları ve koyu arkaplanı ayırmak için
        S_MIN = 80 
        V_MIN = 80 

        # 1. Kırmızı/Turuncu Aralığı (0 derece civarı)
        lower_1 = np.array([0, S_MIN, V_MIN])
        upper_1 = np.array([25, 255, 255])
        
        # 2. Pembe/Mor Aralığı (180 derece civarı)
        lower_2 = np.array([160, S_MIN, V_MIN])
        upper_2 = np.array([180, 255, 255])
        
        # 3. Turuncu/Sarımsı (Ekstra Kapsama)
        # Turuncu tonları Kırmızıdan (0) Sarıya (30) geçer.
        lower_3 = np.array([10, S_MIN, V_MIN])
        upper_3 = np.array([40, 255, 255])
        
        # 4. Daha geniş bir Pembe/Mor (Ekstra Kapsama)
        lower_4 = np.array([130, S_MIN, V_MIN])
        upper_4 = np.array([170, 255, 255])
        
        mask1 = cv2.inRange(img_hsv, lower_1, upper_1)
        mask2 = cv2.inRange(img_hsv, lower_2, upper_2)
        mask3 = cv2.inRange(img_hsv, lower_3, upper_3)
        mask4 = cv2.inRange(img_hsv, lower_4, upper_4)
        
        mask = cv2.bitwise_or(mask1, mask2)
        mask = cv2.bitwise_or(mask, mask3)
        mask = cv2.bitwise_or(mask, mask4)
        
        red_pixels = cv2.countNonZero(mask)
        total_pixels = img_hsv.size / 3 
        
        return red_pixels, total_pixels
        
    def _count_mp_pixels(self, img_np):
        """MP (Mavi) için Mavi Renk Tonu aralığındaki pikselleri sayar."""
        
        img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
        img_hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
        
        S_MIN = 80 
        V_MIN = 80
        
        # Mavi Ton Aralığı (100-140 civarı)
        lower_blue = np.array([100, S_MIN, V_MIN])
        upper_blue = np.array([140, 255, 255])
        
        mask = cv2.inRange(img_hsv, lower_blue, upper_blue)

        blue_pixels = cv2.countNonZero(mask)
        total_pixels = img_hsv.size / 3
        
        return blue_pixels, total_pixels

    def _update_hp_ref(self, cur, is_count=False):
        if self._hp_ref is None: self._hp_ref = cur; return
        if cur >= self._hp_ref * 0.97: 
            self._hp_ref = 0.90 * self._hp_ref + 0.10 * cur 

    def _update_mp_ref(self, cur, is_count=False):
        if self._mp_ref is None: self._mp_ref = cur; return
        if cur >= self._mp_ref * 0.97: 
            self._mp_ref = 0.90 * self._mp_ref + 0.10 * cur

    def _press_pot(self, f_bar, digit):
        if f_bar > 0 and f_bar in F_SCANCODES:
            self._send_key(F_SCANCODES[f_bar], 0.01)
            time.sleep(0.015)
        
        if digit in DIGIT_SCANCODES:
            self._send_key(DIGIT_SCANCODES[digit], 0.01)


# =========================================================
# 2. YARDIMCI DİALOG (ALAN SEÇİMİ)
# =========================================================
class RectSelectDialog(QDialog):
    # ... (RectSelectDialog kodu aynı kalacak)
    def __init__(self, parent=None, title="ALANI SEÇ"):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setWindowState(Qt.WindowFullScreen)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setCursor(Qt.CrossCursor)
        
        self.origin = None
        self.current = None
        self.result_rect = None
        self.title = title

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.origin = event.pos()
            self.current = self.origin
            self.update()
        elif event.button() == Qt.RightButton:
            self.reject()

    def mouseMoveEvent(self, event):
        if self.origin is not None:
            self.current = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.origin is not None:
            x = min(self.origin.x(), event.pos().x())
            y = min(self.origin.y(), event.pos().y())
            w = abs(self.origin.x() - event.pos().x())
            h = abs(self.origin.y() - event.pos().y())
            
            if w < 5 or h < 5:
                self.origin = None; self.current = None; self.update()
            else:
                self.result_rect = (x, y, w, h)
                self.accept()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 60)) 

        if self.origin and self.current:
            x = min(self.origin.x(), self.current.x())
            y = min(self.origin.y(), self.current.y())
            w = abs(self.origin.x() - self.current.x())
            h = abs(self.origin.y() - self.current.y())
            
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            painter.fillRect(x, y, w, h, Qt.transparent)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

            pen = QPen(QColor(255, 0, 0), 2); pen.setStyle(Qt.SolidLine)
            painter.setPen(pen); painter.setBrush(Qt.NoBrush)
            painter.drawRect(x, y, w, h)
            
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(x, y - 5, f"{w}x{h}")
        else:
            # --- MESAJIN GÖRÜNÜRLÜĞÜ İÇİN DÜZENLEME BURADA ---
            from PyQt5.QtGui import QFont
            font = QFont("Arial", 16, QFont.Bold) # Fontu büyüt
            painter.setFont(font)
            
            # Parlak Sarı/Yeşil Renk
            painter.setPen(QColor(255, 255, 0)) # Sarı renk
            
            # Metni ekranın ortasına çizmeyi kolaylaştırmak için QRect kullan
            text_rect = self.rect()
            
            painter.drawText(text_rect, Qt.AlignCenter, 
                             self.title + "\n\n(Sol Tık Sürükle, Sağ Tık İptal)")

# =========================================================
# 2.3 YARDIMCI: KAYITLI BÖLGEYİ GÖSTEREN YEŞİL KUTU
# =========================================================
class HPMPAreaVisualizer(QWidget):
    """
    Kaydedilmiş bölgeyi gösteren basit, şeffaf, yeşil çerçeveli overlay.
    """
    def __init__(self, region_data, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Kullanıcının içinden tıklayabilmesi için
        self.setWindowFlags(self.windowFlags() | Qt.WindowTransparentForInput)

        # region_data: (x, y, w, h) şeklinde tuple bekliyoruz
        if isinstance(region_data, (list, tuple)) and len(region_data) == 4:
            x, y, w, h = region_data
            self.setGeometry(x, y, w, h)
            self.show()
        else:
            self.setGeometry(0, 0, 0, 0)
            self.close()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setPen(QPen(Qt.green, 4))
        p.setBrush(Qt.NoBrush)
        # Çerçeve tam olarak sınırın içinde görünmesi için 2 piksel içeri kaydır
        p.drawRect(self.rect().adjusted(2, 2, -3, -3))
        
# =========================================================
# 2.5 YARDIMCI Progress Bar (Canlı Çizim)
# =========================================================
class HPMPBar(QFrame):
    def __init__(self, color_rgb: Tuple[int, int, int], parent=None):
        super().__init__(parent)
        self.setFixedSize(248, 15)
        self.ratio = 1.0
        self.bar_color = QColor(*color_rgb)
        self.setStyleSheet("border: 1px solid #444; border-radius: 3px; background-color: #000;")

    def set_ratio(self, ratio):
        self.ratio = max(0.0, min(1.0, ratio))
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        
        p = QPainter(self)
        rect = self.rect()
        
        # Dolu kısmı çiz
        width = int(rect.width() * self.ratio)
        p.setBrush(QBrush(self.bar_color))
        p.setPen(Qt.NoPen)
        p.drawRect(rect.x(), rect.y(), width, rect.height())

        # Yüzdeyi yaz
        p.setPen(QColor(255, 255, 255))
        p.setFont(self.font())
        percent_text = f"{self.ratio * 100:.1f} %"
        p.drawText(rect, Qt.AlignCenter, percent_text)


# =========================================================
# 3. GUI (AYAR PENCERESİ)
# =========================================================
class HpMpSettingsDialog(QDialog):
    def __init__(self, parent, config, macro):
        super().__init__(parent)
        self.setWindowTitle("SMART HP / MP AYARLARI")
        self.setModal(True)
        self.config = config or {}
        self.macro = macro
        self._capture_next_key = False
        
        self._original_pos = None

        # --- ARAYÜZ DÜZENİ ---
        main_layout = QVBoxLayout(self)
        grid = QGridLayout()
        grid.setContentsMargins(10, 10, 10, 10)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        main_layout.addLayout(grid)

        # ROW 0: AKTİF TUŞ SEÇİMİ
        grid.addWidget(QLabel("AKTİF TUŞ:"), 0, 0, 1, 2)
        self.hotkey_edit = QLineEdit(self.config.get("hotkey", "H"))
        self.hotkey_edit.setReadOnly(True)
        
        btn_cap = QPushButton("TUŞ ATA")
        btn_cap.clicked.connect(self.start_key_capture)
        
        hk_l = QHBoxLayout()
        hk_l.addWidget(self.hotkey_edit)
        hk_l.addWidget(btn_cap)
        grid.addLayout(hk_l, 0, 2, 1, 3)

        # ROW 1: SEPARATOR
        line = QFrame(); line.setFrameShape(QFrame.HLine); line.setFrameShadow(QFrame.Sunken)
        grid.addWidget(line, 1, 0, 1, 5)

        # ROW 2: HP AYARLARI
        lbl_hp_icon = QLabel(); lbl_hp_icon.setFixedSize(24, 24); pix_hp = QPixmap("icons/hp.png")
        if not pix_hp.isNull(): lbl_hp_icon.setPixmap(pix_hp.scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        grid.addWidget(lbl_hp_icon, 2, 0)

        self.chk_hp = QCheckBox("HP AÇ"); self.chk_hp.setChecked(self.config.get("hp_enabled", True))
        grid.addWidget(self.chk_hp, 2, 1)

        self.hp_f = QComboBox(); self.hp_f.addItem("F YOK", 0)
        for i in range(1, 9): self.hp_f.addItem(f"F{i}", i)
        val_hp_f = self.config.get("hp_f_bar", 1); idx = self.hp_f.findData(val_hp_f)
        if idx < 0: idx = 0
        self.hp_f.setCurrentIndex(idx); grid.addWidget(self.hp_f, 2, 2)

        self.hp_digit = QComboBox(); self.hp_digit.addItems([str(i) for i in range(10)])
        self.hp_digit.setCurrentText(str(self.config.get("hp_digit", 1))); grid.addWidget(self.hp_digit, 2, 3)

        self.hp_ratio = QDoubleSpinBox(); self.hp_ratio.setRange(10, 100)
        self.hp_ratio.setValue(self.config.get("hp_trigger", 0.9) * 100); grid.addWidget(self.hp_ratio, 2, 4)

        self.hp_f.setEnabled(self.chk_hp.isChecked()); self.hp_digit.setEnabled(self.chk_hp.isChecked()); self.hp_ratio.setEnabled(self.chk_hp.isChecked())
        self.chk_hp.toggled.connect(self.hp_f.setEnabled); self.chk_hp.toggled.connect(self.hp_digit.setEnabled); self.chk_hp.toggled.connect(self.hp_ratio.setEnabled)


        # ROW 3: MP AYARLARI
        lbl_mp_icon = QLabel(); lbl_mp_icon.setFixedSize(24, 24); pix_mp = QPixmap("icons/mp.png")
        if not pix_mp.isNull(): lbl_mp_icon.setPixmap(pix_mp.scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        grid.addWidget(lbl_mp_icon, 3, 0)

        self.chk_mp = QCheckBox("MP AÇ"); self.chk_mp.setChecked(self.config.get("mp_enabled", True))
        grid.addWidget(self.chk_mp, 3, 1)

        self.mp_f = QComboBox(); self.mp_f.addItem("F YOK", 0)
        for i in range(1, 9): self.mp_f.addItem(f"F{i}", i)
        val_mp_f = self.config.get("mp_f_bar", 1); idx = self.mp_f.findData(val_mp_f)
        if idx < 0: idx = 0
        self.mp_f.setCurrentIndex(idx); grid.addWidget(self.mp_f, 3, 2)

        self.mp_digit = QComboBox(); self.mp_digit.addItems([str(i) for i in range(10)])
        self.mp_digit.setCurrentText(str(self.config.get("mp_digit", 2))); grid.addWidget(self.mp_digit, 3, 3)

        self.mp_ratio = QDoubleSpinBox(); self.mp_ratio.setRange(10, 100)
        self.mp_ratio.setValue(self.config.get("mp_trigger", 0.9) * 100); grid.addWidget(self.mp_ratio, 3, 4)

        self.mp_f.setEnabled(self.chk_mp.isChecked()); self.mp_digit.setEnabled(self.chk_mp.isChecked()); self.mp_ratio.setEnabled(self.chk_mp.isChecked())
        self.chk_mp.toggled.connect(self.mp_f.setEnabled); self.chk_mp.toggled.connect(self.mp_digit.setEnabled); self.chk_mp.toggled.connect(self.mp_ratio.setEnabled)

        # ROW 4: SEPARATOR
        line2 = QFrame(); line2.setFrameShape(QFrame.HLine); line2.setFrameShadow(QFrame.Sunken)
        grid.addWidget(line2, 4, 0, 1, 5)

        # ROW 5: ORTAK ALAN SEÇİM BUTONU
        btn_common_area = QPushButton("HP/MP ORTAK ALANINI SEÇ")
        btn_common_area.setStyleSheet("background-color: #303030; color: white; font-weight: bold; padding: 5px;")
        btn_common_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btn_common_area.clicked.connect(self.select_common_area)
        grid.addWidget(btn_common_area, 5, 0, 1, 5)

        # --- ALAN GOSTER (ROW 6) ---
        self.btn_show_area = QPushButton("SEÇİLEN ALANI GÖSTER / GİZLE")
        self.btn_show_area.setStyleSheet("background-color: #303030; color: #BBBBBB; padding: 5px;")
        self.btn_show_area.clicked.connect(self.toggle_area_visualizer)
        grid.addWidget(self.btn_show_area, 6, 0, 1, 5)
        # ------------------------------------

        # ROW 7: OK / CANCEL 
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        main_layout.addWidget(btns)

        self.result = None
        
        # --- YENİ EKLENECEK ALAN ---
        self.visualizer = None

    def _temp_hide(self):
        self._original_pos = self.pos()
        self.move(-10000, -10000)
        QApplication.processEvents()
        time.sleep(0.1)

    def _temp_show(self):
        if self._original_pos: self.move(self._original_pos)
        self.activateWindow(); self.raise_(); QApplication.processEvents()

    # --- TEK ALAN SEÇİM FONKSİYONU ---
    def select_common_area(self):
        self._temp_hide()
        # Metni RectSelectDialog'un içine gönderiyoruz
        d = RectSelectDialog(None, "HP ve MP BARLARINI KAPSAYAN TEK KARE ÇİZİN\n") 
        res = d.exec_()
        self._temp_show()
        if res == QDialog.Accepted and d.result_rect:
            # Tek region'ı hem HP hem MP olarak kaydet
            self.config["hp_region"] = list(d.result_rect)
            self.config["mp_region"] = list(d.result_rect)
            self.macro.set_common_region(tuple(d.result_rect))
            
            # --- MESAJ STİLİ DÜZENLEMESİ ---
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Başarılı")
            
            html_content = (
                f"<p style='color: #00ff4c; font-size: 14pt; font-weight: bold;'>ORTAK HP/MP ALANI KAYDEDİLDİ.</p>"
                f"<p style='font-size: 10pt; color: #aaa;'>Koordinatlar: {d.result_rect}</p>"
                f"<p style='color: yellow; font-size: 10pt; font-weight: bold;'></p>"
            )
            msg_box.setText(html_content)
            msg_box.setIcon(QMessageBox.Information)
            msg_box.setStandardButtons(QMessageBox.Ok)
            msg_box.setStyleSheet("""
                QMessageBox { background-color: #222; color: white; }
                QLabel { color: white; }
                QPushButton { background-color: #444; color: white; border: 1px solid #666; padding: 5px; }
            """)
            
            msg_box.exec_()

    def start_key_capture(self): 
        self._capture_next_key = True; self.hotkey_edit.setText("BAS..."); self.hotkey_edit.setFocus()

    def keyPressEvent(self, event):
        if self._capture_next_key:
            key = event.key()
            name = None

            # Özel tuş isimleri (minor.py ile aynı mantık)
            if key == Qt.Key_NumLock:
                name = "NUM LOCK"
            elif key == Qt.Key_CapsLock:
                name = "CAPS LOCK"
            elif key == Qt.Key_ScrollLock:
                name = "SCROLL LOCK"
            elif key == Qt.Key_Pause:
                name = "PAUSE"
            elif key == Qt.Key_Print:
                name = "PRINT SCREEN"
            elif key == Qt.Key_Enter or key == Qt.Key_Return:
                name = "ENTER"
            elif key == Qt.Key_Escape:
                name = "ESC"
            elif key == Qt.Key_Tab:
                name = "TAB"
            elif key == Qt.Key_Backspace:
                name = "BACKSPACE"
            elif key == Qt.Key_Delete:
                name = "DELETE"
            elif key == Qt.Key_Insert:
                name = "INSERT"
            elif key == Qt.Key_Left:
                name = "LEFT"
            elif key == Qt.Key_Up:
                name = "UP"
            elif key == Qt.Key_Right:
                name = "RIGHT"
            elif key == Qt.Key_Down:
                name = "DOWN"
            elif key == Qt.Key_Home:
                name = "HOME"
            elif key == Qt.Key_End:
                name = "END"
            elif key == Qt.Key_PageUp:
                name = "PAGE UP"
            elif key == Qt.Key_PageDown:
                name = "PAGE DOWN"
            elif key == Qt.Key_Meta:
                name = "WINDOWS"
            elif key == Qt.Key_Menu:
                name = "MENU"
            elif key == Qt.Key_Space:
                name = "SPACE"
            elif key == Qt.Key_Shift:
                name = "SHIFT"
            elif key == Qt.Key_Control:
                name = "CTRL"
            elif key == Qt.Key_Alt:
                name = "ALT"
            elif Qt.Key_F1 <= key <= Qt.Key_F12:
                name = f"F{key - Qt.Key_F1 + 1}"
            else:
                # Normal karakterli tuşlar (A, B, C, 1, 2 vb.)
                text = event.text()
                if text:
                    name = text.upper()

            if name:
                # Seçilen tuşu edit'e yaz ve capture modundan çık
                self.hotkey_edit.setText(name)
                self._capture_next_key = False

            return  # Olayı burada tüket

        # Normal durumda varsayılan davranış
        super().keyPressEvent(event)

    def accept(self):
                # Kapatmadan önce gösterge açıksa kapat
        if self.visualizer:
            self.visualizer.close()
            self.visualizer = None
        self.result = {
            "hp_f_bar": int(self.hp_f.currentData()), "hp_digit": int(self.hp_digit.currentText()),
            "mp_f_bar": int(self.mp_f.currentData()), "mp_digit": int(self.mp_digit.currentText()),
            "hp_trigger": self.hp_ratio.value() / 100.0, "mp_trigger": self.mp_ratio.value() / 100.0,
            "hp_enabled": self.chk_hp.isChecked(), "mp_enabled": self.chk_mp.isChecked(),
            "hotkey": self.hotkey_edit.text(),
            # Ortak bölgeyi kaydet
            "hp_region": self.config.get("hp_region"), "mp_region": self.config.get("mp_region")
        }
        super().accept()

    def toggle_area_visualizer(self):
        region = self.config.get("hp_region") # Ortak bölgeyi kullan
        
        if not region:
            return QMessageBox.warning(self, "Uyarı", "Önce HP/MP Ortak Alanını Seçmelisiniz.")
            
        if self.visualizer is None:
            # Region (x, y, w, h) formatında olmalı
            self.visualizer = HPMPAreaVisualizer(region, parent=None)
        else:
            self.visualizer.close()
            self.visualizer = None
# =========================================================
# 4. WIDGET (ANA EKAN KARTI)
# =========================================================
class HpMpWidget(QFrame):
    update_signal = pyqtSignal()

    def __init__(self, parent=None, macro_instance=None, config=None):
        super().__init__(parent)
        self.macro = macro_instance
        self.config = config or {}
        self.listen_active = False
        self._hotkey_handles = []
        
        # CANLI BARLAR
        self.hp_bar = HPMPBar(color_rgb=(255, 0, 0))
        self.mp_bar = HPMPBar(color_rgb=(0, 0, 255))
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_bars_and_status)
        self.timer.start(100) # 100ms'de bir güncelle

        self.update_signal.connect(self._safe_update_status)
        self.setup_ui()
        self._safe_update_status()

    def setup_ui(self):
        self.setFrameShape(QFrame.Box); self.setFrameShadow(QFrame.Plain); self.setMaximumWidth(260)
        self.setStyleSheet("QFrame {background-color: #101010; border: 1px solid #444444; border-radius: 4px;}")
        v = QVBoxLayout(self); v.setContentsMargins(6, 6, 6, 6); v.setSpacing(4)
        
        # Header (HP ve MP İkonları yan yana)
        h = QHBoxLayout(); h.setSpacing(4)
        
        for icon_file in ["hp.png", "mp.png"]:
            lbl = QLabel(); lbl.setFixedSize(30, 30); pix = QPixmap(f"icons/{icon_file}")
            if not pix.isNull(): lbl.setPixmap(pix.scaled(30, 30, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            h.addWidget(lbl)

        h.addStretch(1) 
        
        lbl_title = QLabel("SMART HP/MP"); lbl_title.setObjectName("MinorHeaderLabel")
        h.addWidget(lbl_title); v.addLayout(h)

        self.btn_listen = QPushButton("TUŞ DİNLEMEYİ BAŞLAT")
        self.btn_listen.setObjectName("ThreeFiveListenButton") 
        self.btn_listen.setProperty("active", False)
        self.btn_listen.clicked.connect(self.toggle_listen)
        v.addWidget(self.btn_listen)

        self.lbl_status = QLabel("DURUM: PASİF"); self.lbl_status.setObjectName("MinorStatusLabel")
        v.addWidget(self.lbl_status)
        
        # CANLI BARLAR EKLENDİ
        v.addWidget(self.hp_bar)
        v.addWidget(self.mp_bar)
        
        row = QHBoxLayout()
        row.setSpacing(4)
        row.addWidget(QLabel("AKTİF TUŞ:"))
        
        self.lbl_hotkey = QLabel(self.config.get("hotkey", "H"))
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
        was_listening = self.listen_active
        if was_listening: self.toggle_listen()

        # Düzeltme 1: Doğru Dialog Sınıfını Çağırıyoruz
        dlg = HpMpSettingsDialog(self.window(), self.config, self.macro)
        
        if dlg.exec_() == QDialog.Accepted:
            self.config.update(dlg.result)
            c = self.config
            self.macro.set_hp_pot(c["hp_f_bar"], c["hp_digit"])
            self.macro.set_mp_pot(c["mp_f_bar"], c["mp_digit"])
            self.macro.set_trigger_ratios(c["hp_trigger"], c["mp_trigger"])
            self.macro.hp_enabled = c["hp_enabled"]
            self.macro.mp_enabled = c["mp_enabled"]
            
            # Tekrar set etme
            if c.get("hp_region"): self.macro.set_common_region(tuple(c["hp_region"]))
            
            # Düzeltme 2: Hotkey etiketini doğru isimle güncelliyoruz
            self.lbl_hotkey.setText(c["hotkey"]) 

            # Eğer dinleme aktifse tekrar başlat
            if was_listening: self.toggle_listen()
        
    def toggle_listen(self):
        try: import keyboard
        except: return QMessageBox.warning(self, "Hata", "keyboard modülü yüklü değil")
        
        if not self.listen_active:
            k = self.config.get("hotkey", "H").lower()
            self._hotkey_handles = []
            try:
                h = keyboard.on_press_key(k, lambda e: self.on_toggle())
                self._hotkey_handles.append(h)
                self.listen_active = True
            except Exception as e: 
                print(e); self.listen_active = False
                QMessageBox.critical(self, "Hata", f"Tuş bağlanamadı: {e}")
        else:
            for h in self._hotkey_handles:
                try: keyboard.unhook(h)
                except: pass
            self._hotkey_handles = []
            self.listen_active = False
            if self.macro.is_running: self.macro.stop()
        self._safe_update_status()

    def on_toggle(self):
        self.macro.toggle()
        self.update_signal.emit()

    def _update_bars_and_status(self):
        self.hp_bar.set_ratio(self.macro.hp_current_ratio)
        self.mp_bar.set_ratio(self.macro.mp_current_ratio)
        
        if self.listen_active:
            is_running = self.macro.is_running
            self.lbl_status.setText("DURUM: ÇALIŞIYOR" if is_running else "DURUM: BEKLİYOR")
            self.apply_status_style("#00ff4c" if is_running else "#ffff55")

    def _safe_update_status(self):
        if not self.listen_active:
            self.lbl_status.setText("DURUM: PASİF")
            self.btn_listen.setText("TUŞ DİNLEMEYİ BAŞLAT")
            act = False
            self.apply_status_style("#ff5555")
        else:
            self.btn_listen.setText("TUŞ DİNLEMEYİ DURDUR")
            act = True
        
        self.btn_listen.setProperty("active", act)
        self.btn_listen.style().unpolish(self.btn_listen)
        self.btn_listen.style().polish(self.btn_listen)

    def apply_status_style(self, color: str = "#8d95c7"):
        self.lbl_status.setStyleSheet(f"color: {color}; font-weight: bold;")
