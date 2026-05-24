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
    QFrame, QVBoxLayout, QSizePolicy, QMessageBox
)
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtCore import Qt, QSize, QTimer

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
F_SCANCODES = {
    1: 0x3B, 2: 0x3C, 3: 0x3D, 4: 0x3E,
}

def _default_send_key(scan_code: int):
    if _ClicksendKeyboardDriver is None:
        print(f"[OTOCURE][FAKE] {scan_code:#04x}")
        return
    if not hasattr(_default_send_key, "_driver"):
        _default_send_key._driver = _ClicksendKeyboardDriver()
    _default_send_key._driver.tusbas(scan_code, 0.01)

# =========================================================
# 1. LOGIC (MAKRO MOTORU)
# =========================================================
class OtoCureMacro:
    """
    OTO CURE MACRO: F-bar seç -> skill tuşuna bas.
    Genellikle Cure atmak için kullanılır.
    """
    def __init__(
        self,
        f_bar: int = 3,
        digit: int = 5,
        mode: Literal["toggle", "hold"] = "toggle",
        combo_delay: float = 0.05,
    ):
        self.f_bar = f_bar
        self.digit = digit
        self.mode = mode
        self.combo_delay = combo_delay
        self._running = False
        self._lock = threading.Lock()

    def set_f_bar(self, f_bar: int): self.f_bar = f_bar
    def set_digit(self, digit: int): self.digit = digit
    def set_mode(self, mode: str): self.mode = mode
    def set_combo_delay(self, delay: float): self.combo_delay = max(0.0, float(delay))

    @property
    def is_running(self): return self._running

    def toggle(self): self._do_combo_once()
    def hold_down(self): self._do_combo_once()
    def hold_up(self): pass

    def _do_combo_once(self):
        if self._running: return
        with self._lock:
            self._running = True
            try:
                # F-bar
                sc_f = F_SCANCODES.get(self.f_bar)
                if sc_f: _default_send_key(sc_f)
                
                if self.combo_delay > 0:
                    time.sleep(self.combo_delay)

                # Skill digit
                sc_d = DIGIT_SCANCODES.get(self.digit)
                if sc_d: _default_send_key(sc_d)
            finally:
                self._running = False

# 1. OtoCureMacro sınıfının içine şu metodu ekleyin:
    def update_config(self, cfg):
        with self._lock:
            self.f_bar = int(cfg.get("f_bar", 3))
            self.digit = int(cfg.get("digit", 5))
            self.mode = cfg.get("mode", "toggle")
            self.combo_delay = max(0.0, float(cfg.get("combo_delay", 0.05)))

# 2. OtoCureWidget sınıfının içindeki 'settings' fonksiyonunu şununla değiştirin:
    def settings(self):
        dlg = OtoCureSettingsDialog(self, self.config)
        if dlg.exec_() == QDialog.Accepted:
            self.config.update(dlg.result_config)
            
            # STANDARDIZE EDİLDİ
            self.macro.update_config(self.config)
            
            self.hk.setText(self.config["hotkey"])
            if self.listen_active: self.toggle_listen(); self.toggle_listen()
# =========================================================
# 2. GUI (AYAR PENCERESİ)
# =========================================================
class OtoCureSettingsDialog(QDialog):
    def __init__(self, parent=None, current_config=None):
        super().__init__(parent)
        self.setWindowTitle("OTO CURE AYARLARI")
        self.setModal(True)
        self._capture_next_key = False
        if current_config is None: current_config = {}

        f_bar = int(current_config.get("f_bar", 3))
        digit = int(current_config.get("digit", 5))
        mode = current_config.get("mode", "toggle")
        hotkey = current_config.get("hotkey", "C")
        combo_delay = float(current_config.get("combo_delay", 0.05))

        l = QGridLayout(self)
        l.setContentsMargins(12, 12, 12, 12)
        l.setHorizontalSpacing(8); l.setVerticalSpacing(6)

        l.addWidget(QLabel("F BAR (F1–F9):"), 0, 0)
        self.f = QComboBox()
        
        # 1. "F YOK" seçeneği (Değeri 0)
        self.f.addItem("F YOK", 0)
        
        # 2. F1'den F9'a kadar ekle
        for i in range(1, 10):
            self.f.addItem(f"F{i}", i)
        
        # 3. Kayıtlı değeri bul ve seç
        idx = self.f.findData(f_bar)
        if idx < 0: idx = 0 # Bulamazsa F YOK seç
        self.f.setCurrentIndex(idx)
        
        l.addWidget(self.f, 0, 1)

        l.addWidget(QLabel("CURE TUŞU (0–9):"), 1, 0)
        self.d = QComboBox(); self.d.addItems([str(i) for i in range(10)])
        self.d.setCurrentText(str(digit))
        l.addWidget(self.d, 1, 1)

        l.addWidget(QLabel("MOD:"), 2, 0)
        self.m = QComboBox(); self.m.addItems(["TOGGLE", "HOLD"])
        self.m.setCurrentText(mode)
        l.addWidget(self.m, 2, 1)

        l.addWidget(QLabel("AKTİF TUŞ:"), 3, 0)
        self.hk = QLineEdit(hotkey); self.hk.setReadOnly(True)
        btn = QPushButton("TUŞ SEÇ"); btn.setObjectName("KeyCaptureButton")
        btn.clicked.connect(self.cap)
        h = QHBoxLayout(); h.addWidget(self.hk); h.addWidget(btn); w = QWidget(); w.setLayout(h)
        l.addWidget(w, 3, 1)

        l.addWidget(QLabel("F → SKILL GECİKMESİ (SN):"), 4, 0)
        self.dl = QDoubleSpinBox(); self.dl.setRange(0, 1); self.dl.setSingleStep(0.01); self.dl.setValue(combo_delay)
        l.addWidget(self.dl, 4, 1)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        l.addWidget(bb, 5, 0, 1, 2)
        self.result_config = None

    def cap(self): self._capture_next_key = True; self.hk.setText("BAS...")
    def keyPressEvent(self, e):
        if self._capture_next_key:
            key = e.key()
            name = None
            
            # Özel Tuş Kontrolleri
            if key == Qt.Key_CapsLock: name = "CAPS LOCK"
            elif key == Qt.Key_Shift: name = "SHIFT"
            elif key == Qt.Key_Control: name = "CTRL"
            elif key == Qt.Key_Alt: name = "ALT"
            elif key == Qt.Key_Space: name = "SPACE"
            elif key == Qt.Key_Tab: name = "TAB"
            elif Qt.Key_F1 <= key <= Qt.Key_F12: 
                name = f"F{key - Qt.Key_F1 + 1}"
            else:
                text = e.text()
                if text and text.strip():
                    name = text.upper()
                else:
                    name = "UNKNOWN"

            if name:
                self.hk.setText(name)
                self._capture_next_key = False
            return
        super().keyPressEvent(e)
    def accept(self):
        self.result_config = {
            "f_bar": self.f.currentData(), "digit": int(self.d.currentText()),
            "mode": self.m.currentText(), "hotkey": self.hk.text(), "combo_delay": self.dl.value()
        }
        super().accept()


# =========================================================
# 3. WIDGET (ANA EKRAN KARTI)
# =========================================================
# --- otocure.py --- (OtoCureWidget Sınıfının Tamamı)

# --- otocure.py --- (OtoCureWidget Sınıfının Tamamı)

class OtoCureWidget(QFrame):
    def __init__(self, parent=None, macro_instance=None, config=None):
        super().__init__(parent)
        self.macro = macro_instance
        self.config = config or {}
        self.listen_active = False
        self._hotkey_handles = []
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

        # Header
        h = QHBoxLayout()
        h.setSpacing(6)
        
        icon = QLabel()
        icon.setFixedSize(25, 25)
        pix = QPixmap("icons/cure.png")
        
        
        if not pix.isNull():
            icon.setPixmap(pix.scaled(25, 25, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        h.addWidget(icon)
        
        lbl_title = QLabel("OTO CURE")
        lbl_title.setObjectName("MinorHeaderLabel") 
        h.addStretch(1)
        h.addWidget(lbl_title)
        
        v.addLayout(h)

        # Buton
        self.btn_listen = QPushButton("TUŞ DİNLEMEYİ BAŞLAT")
        self.btn_listen.setObjectName("ThreeFiveListenButton") 
        self.btn_listen.setProperty("active", False)
        self.btn_listen.clicked.connect(self.toggle_listen)
        v.addWidget(self.btn_listen)

        # Durum
        self.lbl_status = QLabel("DURUM: PASİF")
        self.lbl_status.setObjectName("MinorStatusLabel")
        v.addWidget(self.lbl_status)

        # Alt Kısım
        row = QHBoxLayout()
        row.setSpacing(4)
        row.addWidget(QLabel("AKTİF TUŞ:"))
        
        self.hk = QLabel(self.config.get("hotkey", "C"))
        self.hk.setObjectName("HotkeyLabel")
        self.hk.setAlignment(Qt.AlignCenter)
        row.addWidget(self.hk)

        s = QPushButton("⚙ AYARLAR")
        s.setObjectName("MinorSettingsButton")
        s.setFlat(True)
        s.setIcon(QIcon("icons/gear.png"))
        s.setIconSize(QSize(12, 12))
        s.clicked.connect(self.settings)
        row.addWidget(s)
        
        v.addLayout(row)

    # --- EKSİK OLAN FONKSİYONLAR BURADA ---

    def settings(self):
        dlg = OtoCureSettingsDialog(self, self.config)
        if dlg.exec_() == QDialog.Accepted:
            self.config.update(dlg.result_config)
            self.macro.set_f_bar(self.config["f_bar"])
            self.macro.set_digit(self.config["digit"])
            self.macro.set_mode(self.config["mode"])
            self.macro.set_combo_delay(self.config["combo_delay"])
            self.hk.setText(self.config["hotkey"])
            if self.listen_active: self.toggle_listen(); self.toggle_listen()

    def toggle_listen(self):
        try: import keyboard
        except: return QMessageBox.warning(self, "Hata", "keyboard modülü eksik")

        if not self.listen_active:
            k = self.config.get("hotkey", "C").lower()
            m = self.config.get("mode", "toggle")
            self._hotkey_handles = []
            try:
                if m == "toggle":
                    self._hotkey_handles.append(keyboard.on_press_key(k, lambda e: self.on_toggle()))
                else:
                    self._hotkey_handles.append(keyboard.on_press_key(k, lambda e: self.on_down()))
                    self._hotkey_handles.append(keyboard.on_release_key(k, lambda e: self.on_up()))
                self.listen_active = True
            except Exception as e:
                print(e); self.listen_active = False
        else:
            for h in self._hotkey_handles:
                try: keyboard.unhook(h)
                except: pass
            self._hotkey_handles = []
            self.listen_active = False
        
        self._safe_update_status()

    def on_toggle(self):
        threading.Thread(target=self._run_toggle, daemon=True).start()

    def _run_toggle(self):
        self.macro.toggle()

    def on_down(self):
        threading.Thread(target=self.macro.hold_down, daemon=True).start()

    def on_up(self):
        pass 

    def apply_status_style(self, color):
        self.lbl_status.setStyleSheet(f"color: {color}; font-weight: bold;")

    def _safe_update_status(self):
        if not self.listen_active:
            self.lbl_status.setText("DURUM: PASİF")
            self.btn_listen.setText("TUŞ DİNLEMEYİ BAŞLAT")
            act = False
            self.apply_status_style("#ff5555") # Kırmızı
        else:
            # is_running kontrolü (Attribute veya Property olabilir)
            is_running = getattr(self.macro, 'is_running', False)
            if callable(is_running): is_running = is_running()

            if is_running:
                self.lbl_status.setText("DURUM: ÇALIŞIYOR")
                self.apply_status_style("#00ff4c") # Yeşil
            else:
                self.lbl_status.setText("DURUM: BEKLİYOR")
                self.apply_status_style("#ffff55") # Sarı

            self.btn_listen.setText("TUŞ DİNLEMEYİ DURDUR")
            act = True
        
        self.btn_listen.setProperty("active", act)
        self.btn_listen.style().unpolish(self.btn_listen)
        self.btn_listen.style().polish(self.btn_listen)

        if self.listen_active:
             QTimer.singleShot(500, self._safe_update_status)
