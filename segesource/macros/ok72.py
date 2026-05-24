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
from typing import Callable, Literal

# PyQt5
from PyQt5.QtWidgets import (
    QDialog, QGridLayout, QLabel, QComboBox, 
    QLineEdit, QPushButton, QDoubleSpinBox, 
    QDialogButtonBox, QHBoxLayout, QWidget,
    QFrame, QVBoxLayout, QSizePolicy, QMessageBox, QCheckBox
)
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtCore import Qt, QSize, pyqtSignal

# Opsiyonel clicksend / interception sürücüsü
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
SC_W = 0x11  # W tuşu
SC_R = 0x13  # R tuşu
SC_Z = 0x2C  # Z tuşu

# ---------------------------------------------------------
# YARDIMCI FONKSİYONLAR
# ---------------------------------------------------------
def _default_send_scan(scan_code: int, delay: float = 0.01):
    if _ClicksendKeyboardDriver and not hasattr(_default_send_scan, "_driver"):
        _default_send_scan._driver = _ClicksendKeyboardDriver()
    
    if hasattr(_default_send_scan, "_driver"):
        _default_send_scan._driver.tusbas(scan_code, delay)
    else:
        time.sleep(delay)

def _default_hold_scan(scan_code: int, down: bool):
    if _ClicksendKeyboardDriver and not hasattr(_default_hold_scan, "_driver"):
        _default_hold_scan._driver = _ClicksendKeyboardDriver()
    
    if hasattr(_default_hold_scan, "_driver"):
        if down:
            _default_hold_scan._driver.tusbasilitut(scan_code)
        else:
            _default_hold_scan._driver.tusbirak(scan_code)

# ---------------------------------------------------------
# 1. LOGIC (MAKRO MOTORU)
# ---------------------------------------------------------
class Ok72Macro:
    """
    72 OKÇU MAKROSU
    """
    def __init__(
        self,
        f_bar: int = 2,
        digit: int = 3,
        digit_delay: float = 0.40,
        r_delay: float = 0.10,
        z_delay: float = 0.05,
        z_enabled: bool = False,
        mode: str = "toggle",
    ):
        self.f_bar = f_bar
        self.digit = digit
        self.digit_delay = float(digit_delay)
        self.r_delay = float(r_delay)
        self.z_delay = float(z_delay)
        self.z_enabled = bool(z_enabled)
        self.mode = mode

        self._thread = None
        self._stop_event = threading.Event()
        self._running = False
        self._lock = threading.Lock()

    def set_params(self, f_bar, digit, digit_delay, r_delay, z_delay, z_enabled, mode):
        with self._lock:
            self.f_bar = f_bar
            self.digit = digit
            self.digit_delay = float(digit_delay)
            self.r_delay = float(r_delay)
            self.z_delay = float(z_delay)
            self.z_enabled = bool(z_enabled)
            self.mode = mode

    @property
    def is_running(self):
        return self._running

    def toggle(self):
        if self.mode != "toggle": return
        if not self._running:
            self._start_internal()
        else:
            self._stop_internal()

    def hold_down(self):
        if self.mode != "hold": return
        if not self._running:
            self._start_internal()

    def hold_up(self):
        if self.mode != "hold": return
        if self._running:
            self._stop_internal()

    def _start_internal(self):
        # Eğer eski thread hala canlıysa, durmasını bekle (Join)
        if self._thread and self._thread.is_alive():
            self._stop_event.set()
            self._thread.join(timeout=0.5)
        
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._running = True
        self._thread.start()

    def _stop_internal(self):
        self._stop_event.set()
        self._running = False
        # Arayüz donmasın diye burada join yapmıyoruz, loop kendisi çıkacak.

    def _loop(self):
        # F Tuşu (Başlangıçta bir kez)
        if not self._stop_event.is_set() and self.f_bar > 0:
            sc_f = F_SCANCODES.get(self.f_bar)
            if sc_f: _default_send_scan(sc_f, 0.02)
            time.sleep(0.05)

        # W Basılı Tut
        if not self._stop_event.is_set():
            _default_hold_scan(SC_W, True)
            time.sleep(0.02)

        try:
            while not self._stop_event.is_set():
                # 1. Z Vur (Varsa)
                if self.z_enabled:
                    if self._stop_event.is_set(): break
                    self._tap_scan(SC_Z, 0.01) 
                    
                    # Z Delay (Güvenli Bekleme)
                    if self._sleep_safe(self.z_delay): break

                # 2. Skill Vur
                if self._stop_event.is_set(): break
                self._tap_digit(self.digit, 0.01)
                
                # Skill Delay
                if self._sleep_safe(self.digit_delay): break

                # 3. R Vur 1
                if self._stop_event.is_set(): break
                self._tap_scan(SC_R, 0.01)
                
                if self._sleep_safe(self.r_delay): break

                # 4. R Vur 2
                if self._stop_event.is_set(): break
                self._tap_scan(SC_R, 0.01)
                
                if self._sleep_safe(self.r_delay): break

        except Exception as e:
            print(f"72 Hata: {e}")
        finally:
            # Döngü bitince W bırak
            _default_hold_scan(SC_W, False)
            self._running = False

    def _sleep_safe(self, duration):
        """
        Süreyi küçük parçalar halinde bekler. 
        Eğer stop sinyali gelirse hemen çıkar.
        Return: True (Durduruldu), False (Süre Bitti)
        """
        end_time = time.time() + duration
        while time.time() < end_time:
            if self._stop_event.is_set(): return True
            time.sleep(0.01)
        return False

    def _tap_digit(self, digit, press_time):
        sc = DIGIT_SCANCODES.get(digit)
        if sc: _default_send_scan(sc, press_time)

    def _tap_scan(self, scancode, press_time):
        _default_send_scan(scancode, press_time)


# ---------------------------------------------------------
# 2. GUI (AYAR PENCERESİ)
# ---------------------------------------------------------
class Ok72SettingsDialog(QDialog):
    def __init__(self, parent=None, current_config=None):
        super().__init__(parent)
        self.setWindowTitle("72 MACRO AYARLARI")
        self.setModal(True)
        self._capture_next_key = False
        if not current_config: current_config = {}
        
        f_bar = int(current_config.get("f_bar", 2))
        digit = int(current_config.get("digit", 3))
        digit_delay = float(current_config.get("digit_delay", 0.40))
        r_delay = float(current_config.get("r_delay", 0.10))
        z_delay = float(current_config.get("z_delay", 0.05))
        z_enabled = bool(current_config.get("z_enabled", False))
        mode = current_config.get("mode", "toggle")
        hotkey = current_config.get("hotkey", "N")

        layout = QGridLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(8)

        # --- ROW 0: AKTİF TUŞ ---
        layout.addWidget(QLabel("AKTİF TUŞ:"), 0, 0, 1, 2)
        self.edit_hotkey = QLineEdit(hotkey); self.edit_hotkey.setReadOnly(True)
        btn_capture = QPushButton("TUŞ SEÇ")
        btn_capture.setObjectName("KeyCaptureButton")
        btn_capture.clicked.connect(self.start_capture_hotkey)
        
        h = QHBoxLayout(); h.addWidget(self.edit_hotkey); h.addWidget(btn_capture)
        layout.addLayout(h, 0, 2, 1, 3)

        # --- ROW 1: MOD ---
        layout.addWidget(QLabel("ÇALIŞMA MODU:"), 1, 0, 1, 2)
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItem("BAS / BIRAK (TOGGLE)", "toggle")
        self.cmb_mode.addItem("BASILI TUT (HOLD)", "hold")
        self.cmb_mode.setCurrentIndex(self.cmb_mode.findData(mode))
        layout.addWidget(self.cmb_mode, 1, 2, 1, 3)

        # --- ROW 2: SEPARATOR ---
        line = QFrame(); line.setFrameShape(QFrame.HLine); line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line, 2, 0, 1, 5)

        # --- ROW 3: SKILL BAR (F) ---
        layout.addWidget(QLabel("SKILL BAR (F1–F8):"), 3, 0, 1, 2)
        self.cmb_fbar = QComboBox()
        self.cmb_fbar.addItem("F YOK", 0)
        for i in range(1, 9): self.cmb_fbar.addItem(f"F{i}", i)
        
        idx = self.cmb_fbar.findData(f_bar)
        if idx < 0: idx = 0
        self.cmb_fbar.setCurrentIndex(idx)
        layout.addWidget(self.cmb_fbar, 3, 2, 1, 3)

        # --- ROW 4: SKILL TUŞU ---
        layout.addWidget(QLabel("72 SKILL TUŞU (0–9):"), 4, 0, 1, 2)
        self.cmb_digit = QComboBox()
        self.cmb_digit.addItems([str(i) for i in range(10)])
        self.cmb_digit.setCurrentText(str(digit))
        layout.addWidget(self.cmb_digit, 4, 2, 1, 3)

        # --- ROW 5: SKILL GECİKMESİ ---
        layout.addWidget(QLabel("SKILL GECİKMESİ:"), 5, 0, 1, 2)
        self.spin_digit_delay = QDoubleSpinBox()
        self.spin_digit_delay.setRange(0.0, 5.0); self.spin_digit_delay.setSingleStep(0.01)
        self.spin_digit_delay.setValue(digit_delay); self.spin_digit_delay.setSuffix(" sn")
        layout.addWidget(self.spin_digit_delay, 5, 2, 1, 3)

        # --- ROW 6: R GECİKMESİ ---
        layout.addWidget(QLabel("R GECİKMESİ:"), 6, 0, 1, 2)
        self.spin_r_delay = QDoubleSpinBox()
        self.spin_r_delay.setRange(0.0, 5.0); self.spin_r_delay.setSingleStep(0.01)
        self.spin_r_delay.setValue(r_delay); self.spin_r_delay.setSuffix(" sn")
        layout.addWidget(self.spin_r_delay, 6, 2, 1, 3)

        # --- ROW 7: OTO Z (YENİ) ---
        self.chk_z = QCheckBox("OTO Z")
        self.chk_z.setChecked(z_enabled)
        self.chk_z.setStyleSheet("font-weight: bold; color: #ffaa00;")
        layout.addWidget(self.chk_z, 7, 0, 1, 2)

        self.spin_z_delay = QDoubleSpinBox()
        self.spin_z_delay.setRange(0.0, 5.0); self.spin_z_delay.setSingleStep(0.01)
        self.spin_z_delay.setValue(z_delay); self.spin_z_delay.setSuffix(" sn")
        layout.addWidget(self.spin_z_delay, 7, 2, 1, 3)
        
        self.spin_z_delay.setEnabled(z_enabled)
        self.chk_z.toggled.connect(self.spin_z_delay.setEnabled)

        # --- BUTTONS ---
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        layout.addWidget(btns, 8, 0, 1, 5)
        self.result_config = None

    def start_capture_hotkey(self):
        self._capture_next_key = True
        self.edit_hotkey.setText("BAS...")

    # --- GELİŞMİŞ TUŞ YAKALAMA ---
    def keyPressEvent(self, event):
        if self._capture_next_key:
            key = event.key()
            name = None
            if key == Qt.Key_Escape: name = "ESC"
            elif key == Qt.Key_Tab: name = "TAB"
            elif key == Qt.Key_Backspace: name = "BACKSPACE"
            elif key == Qt.Key_Return or key == Qt.Key_Enter: name = "ENTER"
            elif key == Qt.Key_Space: name = "SPACE"
            elif key == Qt.Key_CapsLock: name = "CAPS LOCK"
            elif key == Qt.Key_NumLock: name = "NUM LOCK"
            elif key == Qt.Key_Shift: name = "SHIFT"
            elif key == Qt.Key_Control: name = "CTRL"
            elif key == Qt.Key_Alt: name = "ALT"
            elif key == Qt.Key_Left: name = "LEFT"
            elif key == Qt.Key_Up: name = "UP"
            elif key == Qt.Key_Right: name = "RIGHT"
            elif key == Qt.Key_Down: name = "DOWN"
            elif Qt.Key_F1 <= key <= Qt.Key_F12: name = f"F{key - Qt.Key_F1 + 1}"
            else:
                text = event.text()
                if text: name = text.upper()
            
            if name:
                self.edit_hotkey.setText(name)
                self._capture_next_key = False
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if self._capture_next_key:
            name = None
            btn = event.button()
            if btn == Qt.LeftButton: name = "LEFT CLICK"
            elif btn == Qt.RightButton: name = "RIGHT CLICK"
            elif btn == Qt.MiddleButton: name = "MIDDLE CLICK"
            elif btn == Qt.XButton1: name = "MOUSE4"
            elif btn == Qt.XButton2: name = "MOUSE5"
            if name:
                self.edit_hotkey.setText(name)
                self._capture_next_key = False
            return
        super().mousePressEvent(event)

    def accept(self):
        self.result_config = {
            "f_bar": int(self.cmb_fbar.currentData()),
            "digit": int(self.cmb_digit.currentText()),
            "digit_delay": self.spin_digit_delay.value(),
            "r_delay": self.spin_r_delay.value(),
            "z_delay": self.spin_z_delay.value(),
            "z_enabled": self.chk_z.isChecked(),
            "mode": self.cmb_mode.currentData(),
            "hotkey": self.edit_hotkey.text()
        }
        super().accept()


# ---------------------------------------------------------
# 3. WIDGET (ANA EKRAN KARTI)
# ---------------------------------------------------------
class Ok72Widget(QFrame):
    update_signal = pyqtSignal()

    def __init__(self, parent=None, macro_instance=None, config=None):
        super().__init__(parent)
        self.macro = macro_instance
        self.config = config or {}
        
        self.listen_active = False
        self._hotkey_handles = []
        self._last_toggle_time = 0
        
        # Sinyal Bağla (Thread Safety)
        self.update_signal.connect(self._safe_update_status)
        self.setup_ui()
        self._safe_update_status()

    def setup_ui(self):
        self.setFrameShape(QFrame.Box)
        self.setFrameShadow(QFrame.Plain)
        self.setMaximumWidth(260)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setStyleSheet("QFrame {background-color: #101010; border: 1px solid #444444; border-radius: 4px;}")
        
        v = QVBoxLayout(self); v.setContentsMargins(6, 6, 6, 6); v.setSpacing(4)
        
        # Header (YAZI SAĞA YASLI)
        h = QHBoxLayout(); h.setSpacing(6)
        icon = QLabel(); icon.setFixedSize(25, 25)
        pix = QPixmap("icons/ok72.png")
        if not pix.isNull(): icon.setPixmap(pix.scaled(25, 25, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        
        lbl = QLabel("72"); lbl.setObjectName("MinorHeaderLabel") 
        
        h.addWidget(icon); h.addStretch(1); h.addWidget(lbl); # YAZI SAĞDA
        v.addLayout(h)

        # Buton
        self.btn_listen = QPushButton("TUŞ DİNLEMEYİ BAŞLAT")
        self.btn_listen.setObjectName("ThreeFiveListenButton") 
        self.btn_listen.setProperty("active", False)
        self.btn_listen.clicked.connect(self.toggle_listen)
        v.addWidget(self.btn_listen)

        # Status
        self.lbl_status = QLabel("DURUM: PASİF")
        self.lbl_status.setObjectName("MinorStatusLabel")
        v.addWidget(self.lbl_status)

        # Alt
        row = QHBoxLayout()
        row.setSpacing(4)
        row.addWidget(QLabel("AKTİF TUŞ:"))
        
        self.lbl_hotkey = QLabel(self.config.get("hotkey", "V")) # <-- 'V' varsayılanı korundu
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
        dlg = Ok72SettingsDialog(self, self.config)
        if dlg.exec_() == QDialog.Accepted:
            self.config.update(dlg.result_config)
            self.macro.set_params(
                f_bar=self.config["f_bar"],
                digit=self.config["digit"], 
                digit_delay=self.config["digit_delay"], 
                r_delay=self.config["r_delay"],
                z_delay=self.config.get("z_delay", 0.05),
                z_enabled=self.config["z_enabled"], 
                mode=self.config["mode"]
            )
            self.lbl_hotkey.setText(self.config["hotkey"])
            if self.listen_active: self.toggle_listen(); self.toggle_listen()

    def toggle_listen(self):
        try: import keyboard
        except: return QMessageBox.warning(self, "Hata", "keyboard yok")

        if not self.listen_active:
            k = self.config.get("hotkey", "N").lower()
            m = self.config.get("mode", "toggle")
            self._hotkey_handles = []
            try:
                # Toggle/Hold mantığı (UCBES gibi)
                if m == "toggle": 
                    # suppress=False: Tuşun normal işlevi çalışsın
                    self._hotkey_handles.append(keyboard.on_press_key(k, lambda e: self.on_hotkey_toggle(), suppress=False))
                else:
                    self._hotkey_handles.append(keyboard.on_press_key(k, lambda e: self.on_hotkey_down(), suppress=False))
                    self._hotkey_handles.append(keyboard.on_release_key(k, lambda e: self.on_hotkey_up(), suppress=False))
                self.listen_active = True
            except Exception as e: 
                print(e); self.listen_active = False
        else:
            for h in self._hotkey_handles: 
                try: keyboard.unhook(h)
                except: pass
            self._hotkey_handles = []
            self.listen_active = False
            # !!! ÖNEMLİ: Durdururken makroyu tamamen durdur.
            self.macro._stop_internal()
        
        self._safe_update_status()

    # --- HOTKEY FONKSİYONLARI ---
    def on_hotkey_toggle(self):
        current = time.time()
        if current - self._last_toggle_time < 0.2: return
        self._last_toggle_time = current
        
        self.macro.toggle()
        self.update_signal.emit()

    def on_hotkey_down(self):
        self.macro.hold_down()
        self.update_signal.emit()

    def on_hotkey_up(self):
        self.macro.hold_up()
        self.update_signal.emit()

    def _safe_update_status(self):
        if not self.listen_active:
            self.lbl_status.setText("DURUM: PASİF")
            self.btn_listen.setText("TUŞ DİNLEMEYİ BAŞLAT")
            active = False
            self.apply_status_style("#ff5555")
        else:
            if self.macro.is_running:
                self.lbl_status.setText("DURUM: ÇALIŞIYOR")
                self.apply_status_style("#00ff4c")
            else:
                self.lbl_status.setText("DURUM: BEKLİYOR")
                self.apply_status_style("#ffff55")
            
            self.btn_listen.setText("TUŞ DİNLEMEYİ DURDUR")
            active = True
        
        self.btn_listen.setProperty("active", active)
        self.btn_listen.style().unpolish(self.btn_listen)
        self.btn_listen.style().polish(self.btn_listen)

    def apply_status_style(self, color: str = "#8d95c7"):
        self.lbl_status.setStyleSheet(f"color: {color}; font-weight: bold;")
