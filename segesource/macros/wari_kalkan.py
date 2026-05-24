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

# --- wari_kalkan.py ---

import threading
import time
import pyautogui

# PyQt5
from PyQt5.QtWidgets import (
    QDialog, QGridLayout, QLabel, QComboBox, 
    QLineEdit, QPushButton, QDoubleSpinBox, 
    QDialogButtonBox, QHBoxLayout, QWidget,
    QFrame, QVBoxLayout, QSizePolicy, QMessageBox,
    QCheckBox
)
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtCore import Qt, QSize, pyqtSignal, QTimer

# Opsiyonel Sürücü
try:
    from clicksend import KeyboardDriver as _ClicksendKeyboardDriver
    from clicksend import MouseDriver as _ClicksendMouseDriver
except ImportError:
    _ClicksendKeyboardDriver = None
    _ClicksendMouseDriver = None

# Tuş Kodları
SC_I = 0x17 # I (Inventory)

# Harici Kütüphane
try:
    import keyboard
except ImportError:
    keyboard = None


# ---------------------------------------------------------
# 1. LOGIC (MAKRO MOTORU)
# ---------------------------------------------------------
class WarriorKalkanMacro:
    """
    Warrior Kalkan Takma Mantığı.
    """
    def __init__(self):
        self.key = "F"
        self.coords = (0, 0)
        self.speed = 0.1 # Envanter açma hızı
        self.click_duration = 0.15
        
        # Yeni Ayarlar
        self.inv_open_mode = False  # Çanta zaten açık mı?
        self.return_mouse = False   # Mouse geri dönsün mü?
        
        self._driver = _ClicksendKeyboardDriver() if _ClicksendKeyboardDriver else None
        self._mouse = _ClicksendMouseDriver() if _ClicksendMouseDriver else None
        
        self._running = False
        self._lock = threading.Lock()

    def update_config(self, cfg):
        with self._lock:
            self.key = cfg.get("key", "F")
            self.coords = cfg.get("coords", (0, 0))
            self.speed = cfg.get("speed", 0.1)
            self.click_duration = cfg.get("click_duration", 0.15)
            self.inv_open_mode = cfg.get("inv_open_mode", False)
            self.return_mouse = cfg.get("return_mouse", False)

    @property
    def is_running(self):
        return self._running 

    def run_once(self):
        if not self._running:
            threading.Thread(target=self._logic, daemon=True).start()

    def stop(self):
        self._running = False

    def _logic(self):
        if self._running: return
        with self._lock:
            self._running = True
            
            # Mouse pozisyonunu kaydet
            start_x, start_y = pyautogui.position()
            
            try:
                if self.coords == (0, 0):
                    print("[KALKAN] Koordinat ayarlanmamış!")
                    return

                # 1. ÇANTA AÇ
                if not self.inv_open_mode:
                    self._tap_scan(SC_I, self.speed)
                
                # 2. KOORDİNATA GİT VE SAĞ TIKLA
                x, y = self.coords
                
                if self._mouse:
                    self._mouse.rightclick(self.click_duration, x, y)
                else:
                    pyautogui.moveTo(x, y)
                    pyautogui.rightClick()
                    time.sleep(self.click_duration)

                time.sleep(0.05)

                # 3. ÇANTA KAPAT
                if not self.inv_open_mode:
                    self._tap_scan(SC_I, 0.05)

                # 4. MOUSE GERİ DÖNDÜR
                if self.return_mouse:
                    if self._mouse and hasattr(self._mouse, 'move'):
                         self._mouse.move(start_x, start_y)
                    else:
                         pyautogui.moveTo(start_x, start_y)
            
            except Exception as e:
                print(f"[KALKAN] Hata: {e}")
            finally:
                self._running = False

    def _tap_scan(self, scancode: int, delay: float):
        if self._driver:
            self._driver.tusbas(scancode, delay)
        else:
            pyautogui.press('i')
            time.sleep(delay)


# ---------------------------------------------------------
# 2. GUI (AYAR PENCERESİ - DUZELTILMIS YERLESIM)
# ---------------------------------------------------------
class WarriorKalkanSettings(QDialog):
    def __init__(self, parent=None, current_config=None):
        super().__init__(parent)
        self.setWindowTitle("KALKAN TAK AYARLARI")
        self.setModal(True)
        self.result_config = None
        
        self.capture_active = False
        self.hotkey_capture_mode = False 
        self.hook_f = None
        
        if current_config is None: current_config = {}

        self.coords = current_config.get("coords", (0, 0))
        self.temp_coords = list(self.coords) 
        
        key = current_config.get("key", "F")
        speed = current_config.get("speed", 0.1)
        click_dur = current_config.get("click_duration", 0.15)
        
        inv_mode = current_config.get("inv_open_mode", False)
        mouse_mode = current_config.get("return_mouse", False)

        layout = QGridLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(8)
        
        # --- SATIR 0: TETİK TUŞU ---
        layout.addWidget(QLabel("AKTIF TUS:"), 0, 0)
        self.txt_hotkey = QLineEdit(key)
        self.txt_hotkey.setReadOnly(True)
        hk_layout = QHBoxLayout()
        hk_layout.addWidget(self.txt_hotkey)
        
        btn_key = QPushButton("TUŞ SEÇ")
        btn_key.setObjectName("KeyCaptureButton")
        btn_key.clicked.connect(self.start_hotkey_capture)
        hk_layout.addWidget(btn_key)
        
        hk_widget = QWidget()
        hk_widget.setLayout(hk_layout)
        layout.addWidget(hk_widget, 0, 1)

        # --- SATIR 1: KOORDİNAT ---
        layout.addWidget(QLabel("KALKAN KOORDİNATI:"), 1, 0)
        
        coord_layout = QHBoxLayout()
        self.lbl_coord_val = QLineEdit(f"{self.temp_coords[0]}, {self.temp_coords[1]}")
        self.lbl_coord_val.setReadOnly(True)
        self.lbl_coord_val.setStyleSheet("background: #222; color: #00e676; border: 1px solid #444;")
        coord_layout.addWidget(self.lbl_coord_val)
        
        btn_coord = QPushButton("YAKALA (F)")
        btn_coord.setObjectName("KeyCaptureButton")
        btn_coord.clicked.connect(self.start_coord_capture)
        coord_layout.addWidget(btn_coord)
        
        coord_widget = QWidget()
        coord_widget.setLayout(coord_layout)
        layout.addWidget(coord_widget, 1, 1)
        
        # Bilgi Label
        lbl_info = QLabel("Bilgi: 'YAKALA'ya bas, mouse'u kalkan üstüne getir ve 'F' tuşuna bas.")
        lbl_info.setStyleSheet("color: #888; font-size: 8pt; font-style: italic;")
        layout.addWidget(lbl_info, 2, 0, 1, 2)

        # --- SATIR 3: HIZLAR ---
        layout.addWidget(QLabel("ENVANTER GECİKMESİ:"), 3, 0)
        self.spin_speed = QDoubleSpinBox()
        self.spin_speed.setRange(0.01, 1.0); self.spin_speed.setSingleStep(0.01)
        self.spin_speed.setValue(speed)
        layout.addWidget(self.spin_speed, 3, 1)

        layout.addWidget(QLabel("TIKLAMA SÜRESİ:"), 4, 0)
        self.spin_click = QDoubleSpinBox()
        self.spin_click.setRange(0.01, 1.0); self.spin_click.setSingleStep(0.01)
        self.spin_click.setValue(click_dur)
        layout.addWidget(self.spin_click, 4, 1)

        # --- SATIR 5: CHECKBOXLAR (AŞAĞI ALINDI) ---
        self.chk_inv = QCheckBox("Çanta Zaten Açık (I Basma)")
        self.chk_inv.setChecked(inv_mode)
        
        self.chk_mouse = QCheckBox("Mouse Geri Dönsün")
        self.chk_mouse.setChecked(mouse_mode)
        
        opts_layout = QVBoxLayout()
        opts_layout.addWidget(self.chk_inv)
        opts_layout.addWidget(self.chk_mouse)
        
        layout.addLayout(opts_layout, 5, 0, 1, 2)

        # --- BUTONLAR ---
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.save_and_close)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns, 6, 0, 1, 2)
        
        if keyboard:
            try:
                self.hook_f = keyboard.on_press_key("F", self.on_f_press)
            except: self.hook_f = None

    def closeEvent(self, event):
        if keyboard and hasattr(self, 'hook_f') and self.hook_f: 
            try: keyboard.unhook(self.hook_f)
            except: pass
        super().closeEvent(event)

    def start_coord_capture(self):
        self.capture_active = True
        self.lbl_coord_val.setText("F Bas...")

    def on_f_press(self, e):
        if self.capture_active:
            x, y = pyautogui.position()
            self.temp_coords = [x, y]
            self.lbl_coord_val.setText(f"{x}, {y}")
            self.capture_active = False

    def start_hotkey_capture(self):
        self.hotkey_capture_mode = True
        self.txt_hotkey.setText("...")

    def keyPressEvent(self, e):
        if self.hotkey_capture_mode:
            key_text = None
            if e.key() == Qt.Key_F1: key_text = "F1"
            elif e.key() == Qt.Key_F2: key_text = "F2"
            elif e.key() == Qt.Key_F3: key_text = "F3"
            elif e.key() == Qt.Key_F4: key_text = "F4"
            elif e.key() == Qt.Key_F5: key_text = "F5"
            elif e.key() == Qt.Key_F6: key_text = "F6"
            elif e.key() == Qt.Key_F7: key_text = "F7"
            elif e.key() == Qt.Key_F8: key_text = "F8"
            elif e.key() == Qt.Key_F9: key_text = "F9"
            elif e.key() == Qt.Key_F10: key_text = "F10"
            elif e.key() == Qt.Key_F11: key_text = "F11"
            elif e.key() == Qt.Key_F12: key_text = "F12"
            elif e.key() == Qt.Key_CapsLock: key_text = "CAPSLOCK"
            else:
                t = e.text()
                if t: key_text = t.upper()

            if key_text:
                self.txt_hotkey.setText(key_text)
                self.hotkey_capture_mode = False
        else:
            super().keyPressEvent(e)

    def save_and_close(self):
        self.result_config = {
            "key": self.txt_hotkey.text(),
            "coords": tuple(self.temp_coords),
            "speed": self.spin_speed.value(),
            "click_duration": self.spin_click.value(),
            "inv_open_mode": self.chk_inv.isChecked(),
            "return_mouse": self.chk_mouse.isChecked()
        }
        self.accept()


# ---------------------------------------------------------
# 3. WIDGET (ANA EKRAN KARTI)
# ---------------------------------------------------------
class WarriorKalkanWidget(QFrame):
    update_signal = pyqtSignal()

    def __init__(self, parent=None, macro_instance=None, config=None):
        super().__init__(parent)
        self.macro = macro_instance
        self.config = config or {}
        self.listen_active = False
        self._hooks = []
        
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

        # --- HEADER ---
        h = QHBoxLayout()
        h.setSpacing(4) 
        
        icon_list = ["kalkan1.png", "kalkan2.png", "kalkan3.png", "kalkan4.png"]
        for icon_name in icon_list:
            icon_lbl = QLabel()
            icon_lbl.setFixedSize(25, 25)
            pix = QPixmap(f"icons/wari/{icon_name}")
            if not pix.isNull():
                icon_lbl.setPixmap(pix.scaled(25, 25, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            h.addWidget(icon_lbl)

        lbl = QLabel("KALKAN TAK")
        lbl.setObjectName("MinorHeaderLabel") 
        h.addStretch(); h.addWidget(lbl)
        v.addLayout(h)

        # --- BUTON ---
        self.btn_listen = QPushButton("TUŞ DİNLEMEYİ BAŞLAT")
        self.btn_listen.setObjectName("ThreeFiveListenButton") 
        self.btn_listen.setProperty("active", False)
        self.btn_listen.clicked.connect(self.toggle_listen)
        v.addWidget(self.btn_listen)

        # --- DURUM LABEL ---
        self.lbl_status = QLabel("DURUM: PASİF")
        self.lbl_status.setObjectName("MinorStatusLabel") 
        v.addWidget(self.lbl_status)

        # --- ALT SATIR ---
        row = QHBoxLayout()
        row.setSpacing(4)
        row.addWidget(QLabel("AKTIF TUŞ:"))
        
        self.lbl_hotkey = QLabel(self.config.get("key", "F"))
        self.lbl_hotkey.setObjectName("HotkeyLabel") 
        self.lbl_hotkey.setAlignment(Qt.AlignCenter)
        row.addWidget(self.lbl_hotkey)

        btn_set = QPushButton("⚙ AYARLAR")
        btn_set.setObjectName("MinorSettingsButton") 
        btn_set.setFlat(True)
        btn_set.setIcon(QIcon("icons/gear.png"))
        btn_set.setIconSize(QSize(12, 12))
        btn_set.clicked.connect(self.open_settings)
        row.addWidget(btn_set)
        
        v.addLayout(row)

    def open_settings(self):
        d = WarriorKalkanSettings(self, self.config)
        if d.exec_():
            self.config.update(d.result_config)
            self.macro.update_config(self.config)
            self.lbl_hotkey.setText(self.config["key"])
            if self.listen_active: self.toggle_listen(); self.toggle_listen()

    def toggle_listen(self):
        import keyboard
        if not self.listen_active:
            try:
                k = self.config.get("key", "F").lower()
                self._hooks.append(keyboard.on_press_key(k, lambda e: self.macro.run_once()))
                self.listen_active = True
            except: self.listen_active = False
        else:
            for h in self._hooks: 
                try: keyboard.unhook(h)
                except: pass
            self._hooks = []
            self.listen_active = False
        
        self._safe_update_status()

    def apply_status_style(self, color):
        self.lbl_status.setStyleSheet(f"color: {color}; font-weight: bold;")

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
        
        if self.listen_active:
             QTimer.singleShot(200, self._safe_update_status)
