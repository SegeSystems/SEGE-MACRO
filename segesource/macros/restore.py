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

# --- restore.py ---

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
    QCheckBox
)
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtCore import Qt, QSize, pyqtSignal, QTimer

# Sürücü Kontrolü
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
# MACRO LOGIC
# ---------------------------------------------------------
class RestoreMacro:
    def __init__(self):
        self.key = "F5"
        self.speed = 0.1 
        self.click_speed = 0.05  # Varsayılan tık hızı
        self.region = {'top': 60, 'left': 400, 'width': 1515, 'height': 850}
        self.scan_mode = "toggle"
        
        self._running = False
        self._stop_event = threading.Event()
        self._sct = mss.mss()
        self._driver = _ClicksendKeyboardDriver() if _ClicksendKeyboardDriver else None
        self._mouse = _ClicksendMouseDriver() if _ClicksendMouseDriver else None
        self._template = None
        self._lock = threading.Lock()
        
        self._load_template()
        self._load_region()

    def update_config(self, cfg):
        with self._lock:
            self.key = cfg.get("key", "F5")
            self.speed = cfg.get("speed", 0.1)
            self.click_speed = cfg.get("click_speed", 0.05)
            self.scan_mode = cfg.get("scan_mode", "toggle")
            self._load_region()

    def _load_region(self):
        """Tarama alanını BUFF_ALANI.json dosyasından okur."""
        filename = "BUFF_ALANI.json"
        
        if os.path.isfile(filename):
            try:
                with open(filename, "r") as f:
                    d = json.load(f)
                    self.region = {
                        "left": int(d["x"]),
                        "top": int(d["y"]),
                        "width": int(d["w"]),
                        "height": int(d["h"])
                    }
                    print(f"[RESTORE] Özel Alan Yüklendi: {self.region}")
            except Exception as e:
                print(f"[RESTORE] HATA: JSON okunamadı! {e}")
        else:
            print(f"[RESTORE] HATA: {filename} dosyası bulunamadı! Varsayılan alan kullanılıyor.")
            self.region = {'top': 60, 'left': 400, 'width': 1515, 'height': 850} 

    def _load_template(self):
        path = "icons/restore.png"
        if os.path.isfile(path):
            img = cv2.imread(path, cv2.IMREAD_COLOR)
            if img is not None:
                self._template = img
            else:
                print("[RESTORE] İkon dosyası bozuk.")
        else:
            print("[RESTORE] 'icons/restore.png' bulunamadı!")

    @property
    def is_running(self):
        return self._running

    def toggle(self):
        if self._running: self.stop()
        else: self.start()

    def start(self):
        if self._template is None:
            print("[RESTORE] İkon yok, başlatılamadı.")
            return
            
        if not self._running:
            self._load_region()
            self._stop_event.clear()
            self._running = True
            
            if self.scan_mode == "toggle":
                threading.Thread(target=self._loop_toggle, daemon=True).start()
            else:
                threading.Thread(target=self._logic_single, daemon=True).start()
                
            print(f"[RESTORE] Başlatıldı. Mod: {self.scan_mode}, Tık Hızı: {self.click_speed}")

    def run_once(self):
        """Single modda tek seferlik çalıştırma."""
        if not self._running:
            self._load_region()
            self._running = True
            threading.Thread(target=self._logic_single, daemon=True).start()

    def stop(self):
        self._stop_event.set()
        self._running = False
        print("[RESTORE] Durduruldu.")

    # --- YARDIMCI MOUSE METOTLARI (GÜÇLENDİRİLMİŞ) ---
    def _move_mouse(self, x, y):
        if self._mouse and hasattr(self._mouse, 'move'):
            self._mouse.move(int(x), int(y))
        else:
            pyautogui.moveTo(int(x), int(y))

    def _left_click_at(self, x, y, duration):
        """
        Oyunun algılaması için MouseDown -> Sleep -> MouseUp yöntemi kullanılır.
        """
        # Hedefe git
        self._move_mouse(x, y)
        
        if self._mouse:
            # Sürücü varsa
            self._mouse.leftclick(duration, int(x), int(y))
        else:
            # Normal PyAutoGUI (Basılı tutma simülasyonu)
            try:
                pyautogui.mouseDown()
                time.sleep(0.02) # Oyunun "basıldı" sinyalini alması için kritik bekleme
                pyautogui.mouseUp()
                time.sleep(duration)
            except:
                pass

    def _perform_click_sequence(self, cx, cy):
        """Garanti silme için çift tıklama sekansı."""
        # 1. Tıklama
        self._left_click_at(cx, cy, self.click_speed)
        # 2. Tıklama
        self._left_click_at(cx, cy, self.click_speed)

    # ---------------------------------------------------------
    # TEK SEFERLİK MOD (SINGLE)
    # ---------------------------------------------------------
    def _logic_single(self):
        print("[RESTORE] Single Tarama Başladı.")
        try:
            with mss.mss() as sct:
                scr = np.array(sct.grab(self.region))
                scr_bgr = cv2.cvtColor(scr, cv2.COLOR_BGRA2BGR)
                
                res = cv2.matchTemplate(scr_bgr, self._template, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(res) 
                
                if max_val > 0.85:
                    h, w = self._template.shape[:2]
                    cx = self.region['left'] + max_loc[0] + w // 2
                    cy = self.region['top'] + max_loc[1] + h // 2
                    
                    ox, oy = pyautogui.position()
                    
                    # --- GÜNCELLENMİŞ TIKLAMA ÇAĞRISI ---
                    self._perform_click_sequence(cx, cy)
                        
                    self._move_mouse(ox, oy)
                    print(f"[RESTORE] Silindi! Skor: {max_val:.2f}")
                else:
                    print("[RESTORE] İkon bulunamadı.")
                
            time.sleep(0.1)

        except Exception as e:
            print(f"[RESTORE] Hata: {e}")
        finally:
            self._running = False

    # ---------------------------------------------------------
    # DÖNGÜSEL MOD (TOGGLE)
    # ---------------------------------------------------------
    def _loop_toggle(self):
        with mss.mss() as sct:
            while not self._stop_event.is_set():
                try:
                    scr = np.array(sct.grab(self.region))
                    scr_bgr = cv2.cvtColor(scr, cv2.COLOR_BGRA2BGR)
                    
                    res = cv2.matchTemplate(scr_bgr, self._template, cv2.TM_CCOEFF_NORMED)
                    _, max_val, _, max_loc = cv2.minMaxLoc(res) 
                    
                    if max_val > 0.85:
                        h, w = self._template.shape[:2]
                        cx = self.region['left'] + max_loc[0] + w // 2
                        cy = self.region['top'] + max_loc[1] + h // 2
                        
                        ox, oy = pyautogui.position()
                        
                        # --- GÜNCELLENMİŞ TIKLAMA ÇAĞRISI ---
                        self._perform_click_sequence(cx, cy)
                            
                        self._move_mouse(ox, oy)
                        
                        time.sleep(self.speed * 4) 
                    
                    time.sleep(self.speed)
                    
                except Exception as e:
                    print(f"[RESTORE] Hata: {e}")
                    time.sleep(1)
        self._running = False


# ---------------------------------------------------------
# SETTINGS UI (ESKİ TASARIM GERİ GELDİ)
# ---------------------------------------------------------
class RestoreSettingsDialog(QDialog):
    def __init__(self, parent, config, macro):
        super().__init__(parent)
        self.setWindowTitle("RESTORE SİLME AYARLARI")
        self.setModal(True)
        self.config = config
        self.macro = macro
        self.capture_hotkey = False
        self.result_config = None
        
        layout = QGridLayout(self)
        layout.setSpacing(10)

        # Tuş
        layout.addWidget(QLabel("BAŞLAT TUŞU:"), 0, 0)
        self.txt_key = QLineEdit(self.config.get("key", "F5"))
        self.txt_key.setReadOnly(True)
        btn_key = QPushButton("TUŞ SEÇ")
        btn_key.clicked.connect(self.on_capture)
        h = QHBoxLayout(); h.addWidget(self.txt_key); h.addWidget(btn_key)
        layout.addLayout(h, 0, 1)

        # Tarama Hızı
        layout.addWidget(QLabel("TARAMA HIZI (SN):"), 1, 0)
        self.spin_speed = QDoubleSpinBox()
        self.spin_speed.setRange(0.01, 2.0); self.spin_speed.setSingleStep(0.01)
        self.spin_speed.setValue(self.config.get("speed", 0.1))
        layout.addWidget(self.spin_speed, 1, 1)

        # --- YENİ EKLENEN: Mouse Tık Hızı ---
        layout.addWidget(QLabel("MOUSE TIK SÜRESİ (SN):"), 2, 0)
        self.spin_click_speed = QDoubleSpinBox()
        self.spin_click_speed.setRange(0.001, 1.0)
        self.spin_click_speed.setSingleStep(0.01)
        self.spin_click_speed.setDecimals(3)
        self.spin_click_speed.setValue(self.config.get("click_speed", 0.05))
        layout.addWidget(self.spin_click_speed, 2, 1)

        # MOD SEÇİMİ
        layout.addWidget(QLabel("ÇALIŞMA MODU:"), 3, 0)
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItems(["Otomatik (Sürekli Ara)", "Single (Tek Seferlik)"])
        mode_str = self.config.get("scan_mode", "toggle")
        self.cmb_mode.setCurrentIndex(0 if mode_str == "toggle" else 1)
        layout.addWidget(self.cmb_mode, 3, 1)

        # Butonlar
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns, 4, 0, 1, 2)

    def on_capture(self):
        self.capture_hotkey = True
        self.txt_key.setText("...")

    # --- HATA VEREN KISIM DÜZELTİLDİ (ESKİ SAĞLAM KOD) ---
    def keyPressEvent(self, event):
        if self.capture_hotkey:
            key = event.key()
            name = None
            if key == Qt.Key_CapsLock: name = "CAPSLOCK"
            elif key == Qt.Key_Shift: name = "SHIFT"
            elif key == Qt.Key_Control: name = "CTRL"
            elif key == Qt.Key_Alt: name = "ALT"
            elif Qt.Key_F1 <= key <= Qt.Key_F12: 
                name = f"F{key - Qt.Key_F1 + 1}"
            else:
                text = event.text()
                if text and text.strip():
                    name = text.upper()
                else:
                    name = "UNKNOWN"

            if name:
                self.txt_key.setText(name)
                self.capture_hotkey = False
            return
        super().keyPressEvent(event)

    def accept(self):
        mode_selection = self.cmb_mode.currentText()
        self.result_config = {
            "scan_mode": "toggle" if "Otomatik" in mode_selection else "single",
            "key": self.txt_key.text(),
            "speed": self.spin_speed.value(),
            "click_speed": self.spin_click_speed.value()
        }
        super().accept()

# ---------------------------------------------------------
# WIDGET (ESKİ TASARIM GERİ GELDİ)
# ---------------------------------------------------------
class RestoreWidget(QFrame):
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
        self.setFrameShape(QFrame.Box); self.setMaximumWidth(260)
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
        h = QHBoxLayout(); h.setSpacing(6)
        icon = QLabel(); icon.setFixedSize(25, 25)
        pix = QPixmap("icons/restore.png")
        if not pix.isNull(): icon.setPixmap(pix.scaled(25,25, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        h.addWidget(icon)
        
        title = QLabel("RESTORE SİL"); title.setObjectName("MinorHeaderLabel")
        h.addStretch(); h.addWidget(title)
        v.addLayout(h)

        # Buton
        self.btn_listen = QPushButton("TUŞ DİNLEMEYİ BAŞLAT")
        self.btn_listen.setObjectName("ThreeFiveListenButton")
        self.btn_listen.setProperty("active", False)
        self.btn_listen.clicked.connect(self.toggle_listen)
        v.addWidget(self.btn_listen)

        self.lbl_status = QLabel("PASİF"); self.lbl_status.setObjectName("MinorStatusLabel")
        v.addWidget(self.lbl_status)

        # Alt Kısım
        row = QHBoxLayout(); row.setSpacing(4)
        row.addWidget(QLabel("AKTİF TUŞ:"))
        self.lbl_key = QLabel(self.config.get("key", "F5")); self.lbl_key.setObjectName("HotkeyLabel")
        self.lbl_key.setAlignment(Qt.AlignCenter)
        row.addWidget(self.lbl_key)
        
        btn_set = QPushButton("⚙ AYARLAR"); btn_set.setObjectName("MinorSettingsButton")
        btn_set.clicked.connect(self.open_settings)
        row.addWidget(btn_set)
        
        v.addLayout(row)

    def open_settings(self):
        d = RestoreSettingsDialog(self, self.config, self.macro)
        if d.exec_():
            self.config.update(d.result_config)
            self.macro.update_config(self.config)
            self.lbl_key.setText(self.config["key"])
            if self.listen_active: self.toggle_listen(); self.toggle_listen()

    def toggle_listen(self):
        if not keyboard: 
            return QMessageBox.warning(self, "Hata", "keyboard modülü eksik")

        if not self.listen_active:
            # --- BAŞLATMA MANTIĞI ---
            k = self.config.get("key", "F5").lower()
            try:
                # Mod seçimine göre run_once veya toggle (start) metodunu bağla
                if self.config.get("scan_mode") == "toggle":
                    self._hooks.append(keyboard.on_press_key(k, lambda e: self.on_hotkey_press(), suppress=False))
                else:
                    self._hooks.append(keyboard.on_press_key(k, lambda e: self.on_hotkey_press(), suppress=False))
                    
                self.listen_active = True
                self._safe_update_status()
                print(f"[RESTORE] Dinleniyor: {k}")
            except Exception as e:
                QMessageBox.warning(self, "Hata", f"Tuş dinleme başlatılamadı: {e}")
                self.listen_active = False
        
        else:
            # --- DURDURMA MANTIĞI ---
            for h in self._hooks: 
                try: keyboard.unhook(h)
                except: pass
            self._hooks = []
            self.listen_active = False
            self.macro.stop()
            self._safe_update_status()

    def on_hotkey_press(self):
        if self.config.get("scan_mode") == "toggle":
            self.macro.toggle() 
        else:
            self.macro.run_once()
        
        self.update_signal.emit() # UI güncelle

    def apply_status_style(self, color: str = "#8d95c7"):
        self.lbl_status.setStyleSheet(f"color: {color}; font-weight: bold;")

    def _safe_update_status(self):
        if not self.listen_active:
            self.lbl_status.setText("DURUM: PASİF")
            self.btn_listen.setText("TUŞ DİNLEMEYİ BAŞLAT")
            self.apply_status_style("#ff5555")
            act = False
        else:
            if self.macro.is_running:
                self.lbl_status.setText("ÇALIŞIYOR")
                self.apply_status_style("#00ff4c")
            else:
                self.lbl_status.setText("BEKLİYOR")
                self.apply_status_style("#ffff55")
            self.btn_listen.setText("TUŞ DİNLEMEYİ DURDUR")
            act = True
        
        self.btn_listen.setProperty("active", act)
        self.btn_listen.style().unpolish(self.btn_listen)
        self.btn_listen.style().polish(self.btn_listen)

        if self.listen_active:
             QTimer.singleShot(200, self._safe_update_status)
