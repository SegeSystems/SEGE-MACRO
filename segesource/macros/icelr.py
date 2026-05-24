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
    QFrame, QVBoxLayout, QSizePolicy, QMessageBox,
    QCheckBox  # <--- EKLENDİ
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

# ---------------------------------------------------------
# 1. LOGIC (MAKRO MOTORU)
# ---------------------------------------------------------
class IceManaLRMacro:
    """
    ICE / MANA / LR:
    (Opsiyonel F) → key1 → W → key2 → W → key3
    Her çağrıldığında sadece 1 defa çalışır (one-shot).
    """
    def __init__(
        self,
        f_bar: int = 1,
        key1: int = 3,
        key2: int = 4,
        key3: int = 5,
        combo_delay: float = 0.57,
        w_delay: float = 0.10,
        mode: str = "toggle",
        use_f_key: bool = True # Yeni parametre
    ):
        self.f_bar = f_bar
        self.key1 = key1
        self.key2 = key2
        self.key3 = key3
        self.combo_delay = combo_delay
        self.w_delay = w_delay
        self.mode = mode
        self.use_f_key = use_f_key

        self._driver = _ClicksendKeyboardDriver() if _ClicksendKeyboardDriver else None
        self._running = False 
        self._lock = threading.Lock() # Çakışma önleyici

    def set_params(self, f_bar, key1, key2, key3, combo_delay, w_delay, mode, use_f_key):
        with self._lock:
            self.f_bar = f_bar
            self.key1 = key1
            self.key2 = key2
            self.key3 = key3
            self.combo_delay = combo_delay
            self.w_delay = w_delay
            self.mode = mode
            self.use_f_key = use_f_key

    @property
    def is_running(self):
        return self._running

    def toggle(self):
        # One-shot: Tek seferlik çalışır
        self._do_combo_once()

    def hold_down(self):
        self._do_combo_once()

    def hold_up(self):
        pass

    def _do_combo_once(self):
        # Aynı anda birden fazla çalışmasını engelle
        with self._lock:
            if self._running:
                return
            self._running = True

        try:
            # 1. F bar (Sadece checkbox işaretliyse)
            if self.use_f_key:
                self._tap_scan(F_SCANCODES.get(self.f_bar, 0x3B), 0.01)
            
            # 2. 1. Skill
            self._tap_digit(self.key1, self.combo_delay)
            
            # 3. W
            self._tap_scan(SC_W, self.w_delay)
            
            # 4. 2. Skill
            self._tap_digit(self.key2, self.combo_delay)
            
            # 5. W
            self._tap_scan(SC_W, self.w_delay)
            
            # 6. 3. Skill
            self._tap_digit(self.key3, self.combo_delay)
            
        finally:
            with self._lock:
                self._running = False

    def _tap_digit(self, digit: int, delay: float):
        sc = DIGIT_SCANCODES.get(digit)
        if sc: self._tap_scan(sc, delay)

    def _tap_scan(self, scancode: int, delay: float):
        if self._driver:
            self._driver.tusbas(scancode, delay)
        else:
            time.sleep(delay)


# ---------------------------------------------------------
# 2. GUI (AYAR PENCERESİ)
# ---------------------------------------------------------
class IceManaLRSettingsDialog(QDialog):
    def __init__(self, parent=None, current_config=None):
        super().__init__(parent)
        self.setWindowTitle("ICE / MANA / LR AYARLARI")
        self.setModal(True)
        self._capture_next_key = False
        self.result_config = None

        if current_config is None: current_config = {}

        use_f_key = bool(current_config.get("use_f_key", True))
        f_bar = int(current_config.get("f_bar", 1))
        key1 = int(current_config.get("key1", 3))
        key2 = int(current_config.get("key2", 4))
        key3 = int(current_config.get("key3", 5))
        mode = current_config.get("mode", "toggle")
        hotkey = current_config.get("hotkey", "X")
        combo_delay = float(current_config.get("combo_delay", 0.40))
        w_delay = float(current_config.get("w_delay", 0.05))

        layout = QGridLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(8)

        # --- SATIR 0: SKILL BAR ---
        self.chk_use_f = QCheckBox()
        self.chk_use_f.setChecked(use_f_key)
        self.chk_use_f.setToolTip("Skill Bar (F Tuşu) gönderilsin mi?")
        layout.addWidget(self.chk_use_f, 0, 0) # Sütun 0

        layout.addWidget(QLabel("F BAR (F1–F8):"), 0, 1) # Sütun 1

        self.cmb_fbar = QComboBox()
        for i in range(1, 9): self.cmb_fbar.addItem(f"F{i}", i)
        idx = self.cmb_fbar.findData(f_bar)
        if idx >= 0: self.cmb_fbar.setCurrentIndex(idx)
        layout.addWidget(self.cmb_fbar, 0, 2) # Sütun 2

        # Checkbox kontrolü
        self.cmb_fbar.setEnabled(use_f_key)
        self.chk_use_f.toggled.connect(self.cmb_fbar.setEnabled)


        # --- SATIR 1: 1. SKILL ---
        layout.addWidget(QLabel("LR SKILL TUŞU (0–9):"), 1, 1)
        self.cmb_key1 = QComboBox()
        self.cmb_key1.addItems([str(i) for i in range(10)])
        self.cmb_key1.setCurrentText(str(key1))
        layout.addWidget(self.cmb_key1, 1, 2)

        # --- SATIR 2: 2. SKILL ---
        layout.addWidget(QLabel("MANA SKILL TUŞU (0–9):"), 2, 1)
        self.cmb_key2 = QComboBox()
        self.cmb_key2.addItems([str(i) for i in range(10)])
        self.cmb_key2.setCurrentText(str(key2))
        layout.addWidget(self.cmb_key2, 2, 2)

        # --- SATIR 3: 3. SKILL ---
        layout.addWidget(QLabel("ICE SKILL TUŞU (0–9):"), 3, 1)
        self.cmb_key3 = QComboBox()
        self.cmb_key3.addItems([str(i) for i in range(10)])
        self.cmb_key3.setCurrentText(str(key3))
        layout.addWidget(self.cmb_key3, 3, 2)

        # --- SATIR 4: MOD ---
        layout.addWidget(QLabel("MOD:"), 4, 1)
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItem("BAS / BIRAK (TOGGLE)", "toggle")
        self.cmb_mode.addItem("BASILI TUT (HOLD)", "hold")
        idx = self.cmb_mode.findData(mode)
        if idx >= 0: self.cmb_mode.setCurrentIndex(idx)
        layout.addWidget(self.cmb_mode, 4, 2)

        # --- SATIR 5: HOTKEY ---
        layout.addWidget(QLabel("AKTİF TUŞ:"), 5, 1)
        self.edit_hotkey = QLineEdit(hotkey)
        self.edit_hotkey.setReadOnly(True)
        hk_layout = QHBoxLayout()
        hk_layout.addWidget(self.edit_hotkey)
        btn_cap = QPushButton("TUŞ SEÇ")
        btn_cap.setObjectName("KeyCaptureButton")
        btn_cap.clicked.connect(self.start_capture_hotkey)
        hk_layout.addWidget(btn_cap)
        hk_widget = QWidget()
        hk_widget.setLayout(hk_layout)
        layout.addWidget(hk_widget, 5, 2)

        # --- SATIR 6: SKILL GECİKMESİ ---
        layout.addWidget(QLabel("SKILL GECİKMESİ (SN):"), 6, 1)
        self.spin_combo = QDoubleSpinBox()
        self.spin_combo.setRange(0.0, 1.0)
        self.spin_combo.setSingleStep(0.01)
        self.spin_combo.setValue(combo_delay)
        layout.addWidget(self.spin_combo, 6, 2)

        # --- SATIR 7: W GECİKMESİ ---
        layout.addWidget(QLabel("W BASMA SÜRESİ (SN):"), 7, 1)
        self.spin_w = QDoubleSpinBox()
        self.spin_w.setRange(0.0, 1.0)
        self.spin_w.setSingleStep(0.01)
        self.spin_w.setValue(w_delay)
        layout.addWidget(self.spin_w, 7, 2)

        # --- BUTONLAR ---
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns, 8, 0, 1, 3)

        # Sütun Ayarları
        layout.setColumnStretch(0, 0)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(2, 1)

    def start_capture_hotkey(self):
        self._capture_next_key = True
        self.edit_hotkey.setText("TUŞA BAS...")

    def keyPressEvent(self, event):
        if self._capture_next_key:
            key = event.key()
            name = None
            if key == Qt.Key_NumLock: name = "num lock"
            elif key == Qt.Key_Enter or key == Qt.Key_Return: name = "enter"
            elif key == Qt.Key_Escape: name = "esc"
            elif key == Qt.Key_Tab: name = "tab"
            elif key == Qt.Key_Backspace: name = "backspace"
            elif key == Qt.Key_Space: name = "space"
            elif key == Qt.Key_CapsLock: name = "caps lock"
            elif key == Qt.Key_Shift: name = "shift"
            elif key == Qt.Key_Control: name = "ctrl"
            elif key == Qt.Key_Alt: name = "alt"
            elif key == Qt.Key_Left: name = "left"
            elif key == Qt.Key_Up: name = "up"
            elif key == Qt.Key_Right: name = "right"
            elif key == Qt.Key_Down: name = "down"
            elif key == Qt.Key_Insert: name = "insert"
            elif key == Qt.Key_Delete: name = "delete"
            elif Qt.Key_F1 <= key <= Qt.Key_F12: name = f"f{key - Qt.Key_F1 + 1}"
            else:
                text = event.text()
                if text: name = text.lower()
            
            if name:
                self._capture_next_key = False
                self.edit_hotkey.setText(name.upper())
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if self._capture_next_key:
            name = None
            btn = event.button()
            if btn == Qt.LeftButton: name = "left"
            elif btn == Qt.RightButton: name = "right"
            elif btn == Qt.MiddleButton: name = "middle"
            elif btn == Qt.XButton1: name = "mouse4"
            elif btn == Qt.XButton2: name = "mouse5"
            if name:
                self._capture_next_key = False
                self.edit_hotkey.setText(name.upper())
            return
        super().mousePressEvent(event)

    def accept(self):
        self.result_config = {
            "use_f_key": self.chk_use_f.isChecked(),
            "f_bar": int(self.cmb_fbar.currentData()),
            "key1": int(self.cmb_key1.currentText()),
            "key2": int(self.cmb_key2.currentText()),
            "key3": int(self.cmb_key3.currentText()),
            "mode": self.cmb_mode.currentData(),
            "hotkey": self.edit_hotkey.text(),
            "combo_delay": self.spin_combo.value(),
            "w_delay": self.spin_w.value(),
        }
        super().accept()


# ---------------------------------------------------------
# 3. WIDGET (ANA EKRAN KARTI)
# ---------------------------------------------------------
class IceManaLRWidget(QFrame):
    update_signal = pyqtSignal()

    def __init__(self, parent=None, macro_instance=None, config=None):
        super().__init__(parent)
        self.macro = macro_instance
        self.config = config or {}
        
        self.listen_active = False
        self._hotkey_handles = []
        self._last_toggle_time = 0
        
        # Sinyal Bağlantısı
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

        # Header
        header = QHBoxLayout()
        header.setSpacing(6)
        
        icon_row = QHBoxLayout()
        icon_row.setSpacing(3)
        icon_paths = ["icons/iceshoot.png", "icons/styx.png", "icons/lrshoot.png"]
        
        for path in icon_paths:
            lbl = QLabel()
            lbl.setFixedSize(25, 25)
            pix = QPixmap(path)
            if not pix.isNull():
                lbl.setPixmap(pix.scaled(25, 25, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            icon_row.addWidget(lbl)
        
        header.addLayout(icon_row)
        
        title_label = QLabel("ICE / MANA / LR")
        title_label.setObjectName("MinorHeaderLabel") 

        # --- YAZIYI SAĞA YASLAYAN DÜZENLEME BAŞLANGICI ---
        header.addStretch(1) # <--- Buraya bir stretch koyarak başlığı en sağa itiyoruz
        header.addWidget(title_label)
        # header.addStretch(1) # <--- Bu artık gereksiz, silindi
        # --- YAZIYI SAĞA YASLAYAN DÜZENLEME BİTİŞİ ---

        v.addLayout(header)

        # Listen Button
        self.btn_listen = QPushButton("TUŞ DİNLEMEYİ BAŞLAT")
        self.btn_listen.setObjectName("MinorListenButton") 
        self.btn_listen.setProperty("active", False)
        self.btn_listen.clicked.connect(self.toggle_listen)
        v.addWidget(self.btn_listen)

        # Status
        self.lbl_status = QLabel("DURUM: PASİF")
        self.lbl_status.setObjectName("MinorStatusLabel")
        v.addWidget(self.lbl_status)

        # Alt Kısım
        row = QHBoxLayout()
        row.setSpacing(4)
        row.addWidget(QLabel("AKTİF TUŞ:"))
        
        self.lbl_hotkey = QLabel(self.config.get("hotkey", "X"))
        self.lbl_hotkey.setObjectName("HotkeyLabel")
        self.lbl_hotkey.setAlignment(Qt.AlignCenter)
        row.addWidget(self.lbl_hotkey)

        btn_settings = QPushButton("⚙ AYARLAR")
        btn_settings.setObjectName("MinorSettingsButton")
        btn_settings.setFlat(True)
        btn_settings.setIcon(QIcon("icons/gear.png"))
        btn_settings.setIconSize(QSize(12, 12))
        btn_settings.clicked.connect(self.open_settings)
        row.addWidget(btn_settings)
        
        v.addLayout(row)

    def open_settings(self):
        dlg = IceManaLRSettingsDialog(self, self.config)
        if dlg.exec_() == QDialog.Accepted and dlg.result_config:
            self.config.update(dlg.result_config)
            
            self.macro.set_params(
                self.config["f_bar"], self.config["key1"], self.config["key2"],
                self.config["key3"], self.config["combo_delay"], self.config["w_delay"],
                self.config["mode"], self.config.get("use_f_key", True)
            )
            self.lbl_hotkey.setText(self.config["hotkey"])
            
            if self.listen_active:
                self.toggle_listen()
                self.toggle_listen()

    def toggle_listen(self):
        try:
            import keyboard
        except ImportError:
            QMessageBox.warning(self, "Hata", "'keyboard' kütüphanesi eksik.")
            return

        if not self.listen_active:
            # --- BAŞLAT ---
            hotkey = self.config.get("hotkey", "X").lower()
            mode = self.config.get("mode", "toggle")
            self._hotkey_handles.clear()
            try:
                if mode == "toggle":
                    h = keyboard.on_press_key(hotkey, lambda e: self.on_hotkey_toggle(), suppress=False)
                    self._hotkey_handles.append(h)
                else:
                    h1 = keyboard.on_press_key(hotkey, lambda e: self.on_hotkey_hold_down(), suppress=False)
                    h2 = keyboard.on_release_key(hotkey, lambda e: self.on_hotkey_hold_up(), suppress=False)
                    self._hotkey_handles.extend([h1, h2])
                
                self.listen_active = True
                print(f"[ICE/LR] Dinleniyor: {hotkey}")
            except Exception as e:
                print(f"Hata: {e}")
                self.listen_active = False
        else:
            # --- DURDUR ---
            for h in self._hotkey_handles:
                try: keyboard.unhook(h)
                except: pass
            self._hotkey_handles.clear()
            self.listen_active = False
        
        self._safe_update_status()

    # --- THREAD & CALLBACK ---
    def on_hotkey_toggle(self):
        # Debounce
        current = time.time()
        if current - self._last_toggle_time < 0.2:
            return
        self._last_toggle_time = current

        # Bu makro uzun sürdüğü için, GUI thread'i bloklamamak adına
        # işlemi ayrı bir thread'de başlatıyoruz.
        threading.Thread(target=self._run_macro_thread, daemon=True).start()

    def on_hotkey_hold_down(self):
        # Hold modunda basılı tutunca çalışır
        threading.Thread(target=self._run_macro_thread, daemon=True).start()

    def on_hotkey_hold_up(self):
        # Hold up: şu anlık one-shot olduğu için durdurma işlevi yok ama eklenebilir
        pass

    def _run_macro_thread(self):
        """Makroyu çalıştırır ve GUI durumunu günceller."""
        # Çalışıyor durumuna geçir
        self.update_signal.emit()
        
        # Makro işlemini yap (Bu işlem 1-2 saniye sürebilir)
        self.macro.toggle()
        
        # Bitti durumuna geçir
        self.update_signal.emit()

    # --- SAFE UPDATE ---
    def _safe_update_status(self):
        if not self.listen_active:
            self.lbl_status.setText("DURUM: PASİF")
            self.btn_listen.setText("TUŞ DİNLEMEYİ BAŞLAT")
            is_active = False
            self.apply_status_style("#ff5555") # Kırmızı
        else:
            if self.macro.is_running:
                self.lbl_status.setText("DURUM: ÇALIŞIYOR")
                self.apply_status_style("#00ff4c") # Yeşil
            else:
                self.lbl_status.setText("DURUM: BEKLİYOR")
                self.apply_status_style("#ffff55") # Sarı
            
            self.btn_listen.setText("TUŞ DİNLEMEYİ DURDUR")
            is_active = True
        
        self.btn_listen.setProperty("active", is_active)
        self.btn_listen.style().unpolish(self.btn_listen)
        self.btn_listen.style().polish(self.btn_listen)

    def apply_status_style(self, color: str = "#8d95c7"):
        self.lbl_status.setStyleSheet(f"color: {color}; font-weight: bold;")
