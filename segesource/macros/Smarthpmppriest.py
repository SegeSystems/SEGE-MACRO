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

# ---------------------------------------------------------
# SÜRÜCÜ VE KÜTÜPHANE İMPORTLARI
# ---------------------------------------------------------
try:
    from clicksend import KeyboardDriver as _ClicksendKeyboardDriver
except ImportError:
    _ClicksendKeyboardDriver = None

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
class SmartPriestHpMpMacro:
    def __init__(self):
        self.common_region = None
        
        # --- HP POT AYARLARI ---
        self.hp_enabled = True
        self.hp_f_bar = 1
        self.hp_digit = 1
        self.hp_trigger = 0.80
        self.hp_cooldown = 0.5
        
        # --- MP POT AYARLARI ---
        self.mp_enabled = True
        self.mp_f_bar = 1
        self.mp_digit = 2
        self.mp_trigger = 0.40
        self.mp_cooldown = 0.5
        
        # --- HEAL AYARLARI ---
        self.heal_enabled = False
        self.heal_f_bar = 2
        self.heal_digit = 1
        self.heal_trigger = 0.70
        self.heal_cooldown = 1.0 
        
        # Runtime
        self.scan_interval = 0.05
        self._send_key = _default_send_key
        
        # Referanslar
        self._hp_ref = None; self._mp_ref = None
        self._last_hp_pot = 0; self._last_mp_pot = 0; self._last_heal = 0
        
        self.hp_ratio = 1.0; self.mp_ratio = 1.0
        
        self._thread = None
        self._stop_event = threading.Event()
        self._running = False
        self._lock = threading.Lock() 

    def update_config(self, cfg):
        with self._lock:
            # HP
            self.hp_enabled = cfg.get("hp_enabled", True)
            self.hp_f_bar = cfg.get("hp_f_bar", 1)
            self.hp_digit = cfg.get("hp_digit", 1)
            self.hp_trigger = cfg.get("hp_trigger", 0.80)
            
            # MP
            self.mp_enabled = cfg.get("mp_enabled", True)
            self.mp_f_bar = cfg.get("mp_f_bar", 1)
            self.mp_digit = cfg.get("mp_digit", 2)
            self.mp_trigger = cfg.get("mp_trigger", 0.40)
            
            # HEAL
            self.heal_enabled = cfg.get("heal_enabled", False)
            self.heal_f_bar = cfg.get("heal_f_bar", 2)
            self.heal_digit = cfg.get("heal_digit", 1)
            self.heal_trigger = cfg.get("heal_trigger", 0.70)
            self.heal_cooldown = cfg.get("heal_cooldown", 1.0)
            
            # Region
            if cfg.get("hp_region"):
                self.common_region = tuple(cfg.get("hp_region"))
                # Region değişirse referansları sıfırla ki yeniden öğrensin
                self._hp_ref = None; self._mp_ref = None

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
            try: self._check_logic()
            except Exception as e: print("[PRIEST HP] Hata:", e)
            time.sleep(self.scan_interval)

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
                
                # --- HEAL KONTROLÜ (Öncelikli) ---
                if self.heal_enabled and (now - self._last_heal >= self.heal_cooldown):
                    if hp_count < self._hp_ref * self.heal_trigger:
                        print(f"[PRIEST] HEAL BASILIYOR! Can: %{self.hp_ratio*100:.1f}")
                        self._press_skill(self.heal_f_bar, self.heal_digit)
                        self._last_heal = now
                        return # Heal basıldıysa potu bir sonraki turda kontrol et

                # --- HP POT KONTROLÜ ---
                if self.hp_enabled and (now - self._last_hp_pot >= self.hp_cooldown):
                    if hp_count < self._hp_ref * self.hp_trigger:
                        self._press_skill(self.hp_f_bar, self.hp_digit)
                        self._last_hp_pot = now

        # 2. MP ANALİZİ
        if self.mp_enabled:
            mp_count, mp_total = self._count_pixels(img, "mp")
            if mp_total > 0:
                self._update_ref(mp_count, "mp")
                if self._mp_ref:
                    self.mp_ratio = mp_count / self._mp_ref
                    
                    if (now - self._last_mp_pot >= self.mp_cooldown):
                        if mp_count < self._mp_ref * self.mp_trigger:
                            self._press_skill(self.mp_f_bar, self.mp_digit)
                            self._last_mp_pot = now

    def _count_pixels(self, img_np, mode):
        img_hsv = cv2.cvtColor(cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR), cv2.COLOR_BGR2HSV)
        
        if mode == "hp":
            # Kırmızı/Pembe tonları
            lower1 = np.array([0, 80, 80]); upper1 = np.array([25, 255, 255])
            lower2 = np.array([160, 80, 80]); upper2 = np.array([180, 255, 255])
            mask = cv2.bitwise_or(cv2.inRange(img_hsv, lower1, upper1), cv2.inRange(img_hsv, lower2, upper2))
        else:
            # Mavi tonları
            lower = np.array([100, 80, 80]); upper = np.array([140, 255, 255])
            mask = cv2.inRange(img_hsv, lower, upper)
            
        return cv2.countNonZero(mask), img_hsv.size / 3

    def _update_ref(self, cur, mode):
        if mode == "hp":
            if self._hp_ref is None or cur > self._hp_ref: self._hp_ref = cur
        else:
            if self._mp_ref is None or cur > self._mp_ref: self._mp_ref = cur

    def _press_skill(self, f_bar, digit):
        if f_bar > 0:
            sc = F_SCANCODES.get(f_bar)
            if sc: 
                self._send_key(sc, 0.02)
                time.sleep(0.02)
        
        sc_d = DIGIT_SCANCODES.get(digit)
        if sc_d: self._send_key(sc_d, 0.02)

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
class PriestHpMpSettingsDialog(QDialog):
    def __init__(self, parent, config, macro):
        super().__init__(parent)
        self.setWindowTitle("PRIEST HP/MP/HEAL AYARLARI")
        self.setModal(True); self.config = config
        self.macro = macro # Makro referansı
        self._key_capture = None
        self.visualizer = None
        
        main = QVBoxLayout(self); grid = QGridLayout()
        main.addLayout(grid)

        # 1. Hotkey
        grid.addWidget(QLabel("BAŞLATMA TUŞU:"), 0, 0)
        self.txt_hotkey = QLineEdit(self.config.get("hotkey", "H")); self.txt_hotkey.setReadOnly(True)
        btn_hk = QPushButton("SEÇ"); btn_hk.clicked.connect(self.cap_hotkey)
        h = QHBoxLayout(); h.addWidget(self.txt_hotkey); h.addWidget(btn_hk)
        grid.addLayout(h, 0, 1, 1, 4)

        # 2. Headers
        grid.addWidget(QLabel("AKTİF"), 1, 0); grid.addWidget(QLabel("F SAYFASI"), 1, 1)
        grid.addWidget(QLabel("TUŞ (0-9)"), 1, 2); grid.addWidget(QLabel("TETİK (%)"), 1, 3)

        # 3. HP POT ROW
        self.chk_hp = QCheckBox("HP POT"); self.chk_hp.setChecked(self.config.get("hp_enabled", True))
        self.hp_f = self._create_f_combo(self.config.get("hp_f_bar", 1))
        self.hp_d = self._create_d_combo(self.config.get("hp_digit", 1))
        self.hp_trig = self._create_spin(self.config.get("hp_trigger", 0.80)*100)
        grid.addWidget(self.chk_hp, 2, 0); grid.addWidget(self.hp_f, 2, 1)
        grid.addWidget(self.hp_d, 2, 2); grid.addWidget(self.hp_trig, 2, 3)

        # 4. MP POT ROW
        self.chk_mp = QCheckBox("MP POT"); self.chk_mp.setChecked(self.config.get("mp_enabled", True))
        self.mp_f = self._create_f_combo(self.config.get("mp_f_bar", 1))
        self.mp_d = self._create_d_combo(self.config.get("mp_digit", 2))
        self.mp_trig = self._create_spin(self.config.get("mp_trigger", 0.40)*100)
        grid.addWidget(self.chk_mp, 3, 0); grid.addWidget(self.mp_f, 3, 1)
        grid.addWidget(self.mp_d, 3, 2); grid.addWidget(self.mp_trig, 3, 3)

        # 5. HEAL ROW (YENİ)
        self.chk_heal = QCheckBox("OTO HEAL"); self.chk_heal.setChecked(self.config.get("heal_enabled", False))
        self.heal_f = self._create_f_combo(self.config.get("heal_f_bar", 2))
        self.heal_d = self._create_d_combo(self.config.get("heal_digit", 1))
        self.heal_trig = self._create_spin(self.config.get("heal_trigger", 0.70)*100)
        grid.addWidget(self.chk_heal, 4, 0); grid.addWidget(self.heal_f, 4, 1)
        grid.addWidget(self.heal_d, 4, 2); grid.addWidget(self.heal_trig, 4, 3)
        
        # Ekstra Heal Cooldown
        grid.addWidget(QLabel("HEAL COOLDOWN (SN):"), 5, 0, 1, 2)
        self.spin_cd = QDoubleSpinBox(); self.spin_cd.setRange(0.1, 5.0); self.spin_cd.setValue(self.config.get("heal_cooldown", 1.0))
        grid.addWidget(self.spin_cd, 5, 2, 1, 2)

        # 6. Alan Seçimi
        btn_area = QPushButton("HP/MP ORTAK ALANINI SEÇ"); btn_area.clicked.connect(self.sel_area)
        grid.addWidget(btn_area, 6, 0, 1, 4)
        
        btn_show = QPushButton("SEÇİLEN ALANI GÖSTER"); btn_show.clicked.connect(self.toggle_area_visualizer)
        grid.addWidget(btn_show, 7, 0, 1, 4)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        main.addWidget(btns)

    def _create_f_combo(self, val):
        c = QComboBox(); c.addItem("F YOK", 0)
        for i in range(1, 9): c.addItem(f"F{i}", i)
        idx = c.findData(val); c.setCurrentIndex(idx if idx >= 0 else 0)
        return c
    def _create_d_combo(self, val):
        c = QComboBox(); 
        for i in range(10): c.addItem(str(i), i)
        c.setCurrentIndex(val)
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
        d = RectSelectDialog(None, "HP ve MP BARINI KAPSAYAN ALANI SEÇİN")
        if d.exec_() == QDialog.Accepted:
            self.config["hp_region"] = list(d.result_rect)
            # Makroya anında set et (Görselleştirici için önemli)
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
        if self.visualizer: self.visualizer.close()
        self.config.update({
            "hotkey": self.txt_hotkey.text(),
            "hp_enabled": self.chk_hp.isChecked(), "hp_f_bar": self.hp_f.currentData(), "hp_digit": int(self.hp_d.currentText()), "hp_trigger": self.hp_trig.value()/100,
            "mp_enabled": self.chk_mp.isChecked(), "mp_f_bar": self.mp_f.currentData(), "mp_digit": int(self.mp_d.currentText()), "mp_trigger": self.mp_trig.value()/100,
            "heal_enabled": self.chk_heal.isChecked(), "heal_f_bar": self.heal_f.currentData(), "heal_digit": int(self.heal_d.currentText()), "heal_trigger": self.heal_trig.value()/100, "heal_cooldown": self.spin_cd.value()
        })
        super().accept()

# =========================================================
# 4. WIDGET (ANA KART)
# =========================================================
class PriestHpMpWidget(QFrame):
    update_signal = pyqtSignal()

    def __init__(self, parent=None, macro_instance=None, config=None):
        super().__init__(parent)
        self.macro = macro_instance or SmartPriestHpMpMacro()
        self.config = config or {}
        self.macro.update_config(self.config)
        
        self.listen_active = False
        self._hooks = []
        
        self.hp_bar = HPMPBar((255, 0, 0))
        self.mp_bar = HPMPBar((0, 0, 255))
        
        self.timer = QTimer(self); self.timer.timeout.connect(self.update_ui); self.timer.start(100)
        self.update_signal.connect(self._safe_update)
        self.setup_ui(); self._safe_update()

    def setup_ui(self):
        self.setFrameShape(QFrame.Box)
        self.setMaximumWidth(260)
        self.setStyleSheet("QFrame { background: #101010; border: 1px solid #444; border-radius: 4px; }")
        
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(4)

        # ---------------- HEADER (PNG EKLEMESİ BURADA) ----------------
        header = QHBoxLayout()
        header.setSpacing(6)

        icon_row = QHBoxLayout()
        icon_row.setSpacing(3)

        # Kullanmak istediğiniz ikonların yollarını buraya yazın
        icon_paths = [
            "icons/priest/hp.png",   # HP ikonu yolu
            "icons/priest/mp.png",   # MP ikonu yolu
            "icons/priest/45heal.png"  # Heal ikonu yolu
        ]

        for path in icon_paths:
            lbl = QLabel()
            lbl.setFixedSize(25, 25)
            pix = QPixmap(path)
            if not pix.isNull():
                lbl.setPixmap(
                    pix.scaled(25, 25, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
            else:
                # Eğer resim bulunamazsa yedek emoji gösterir
                lbl.setText("💊")
                lbl.setStyleSheet("border:none; font-size:16px;")
            icon_row.addWidget(lbl)

        header.addLayout(icon_row)
        header.addStretch(1)

        title = QLabel("PRIEST OTO HEAL/POT")
        title.setObjectName("MinorHeaderLabel")
        header.addWidget(title)
        
        v.addLayout(header)

        self.btn_listen = QPushButton("TUŞ DİNLEMEYİ BAŞLAT")
        self.btn_listen.setObjectName("ThreeFiveListenButton")
        self.btn_listen.clicked.connect(self.toggle_listen)
        v.addWidget(self.btn_listen)

        self.lbl_status = QLabel("PASİF"); self.lbl_status.setObjectName("MinorStatusLabel")
        v.addWidget(self.lbl_status)
        
        v.addWidget(self.hp_bar); v.addWidget(self.mp_bar)

        r = QHBoxLayout(); r.addWidget(QLabel("TUŞ:"))
        self.lbl_key = QLabel(self.config.get("hotkey", "H")); self.lbl_key.setObjectName("HotkeyLabel")
        r.addWidget(self.lbl_key)
        btn_set = QPushButton("⚙"); btn_set.setObjectName("MinorSettingsButton")
        btn_set.clicked.connect(self.open_settings)
        r.addWidget(btn_set); v.addLayout(r)

    def open_settings(self):
        dlg = PriestHpMpSettingsDialog(self, self.config, self.macro)
        if dlg.exec_():
            self.config = dlg.config; self.macro.update_config(self.config)
            self.lbl_key.setText(self.config["hotkey"])
            if self.listen_active: self.toggle_listen(); self.toggle_listen()

    def toggle_listen(self):
        if not keyboard: return QMessageBox.warning(self, "Hata", "keyboard modülü yüklü değil")
        if not self.listen_active:
            hk = self.config.get("hotkey", "H").lower()
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

    def _safe_update(self):
        if not self.listen_active:
            self.lbl_status.setText("PASİF"); self.lbl_status.setStyleSheet("color:#ff5555;font-weight:bold;")
            self.btn_listen.setText("TUŞ DİNLEMEYİ BAŞLAT"); self.btn_listen.setProperty("active", False)
        else:
            txt = "ÇALIŞIYOR" if self.macro.is_running else "BEKLİYOR"
            col = "#00ff4c" if self.macro.is_running else "#ffff55"
            self.lbl_status.setText(txt); self.lbl_status.setStyleSheet(f"color:{col};font-weight:bold;")
            self.btn_listen.setText("DURDUR"); self.btn_listen.setProperty("active", True)
        
        self.btn_listen.style().unpolish(self.btn_listen); self.btn_listen.style().polish(self.btn_listen)
        if self.listen_active: QTimer.singleShot(200, self._safe_update)
