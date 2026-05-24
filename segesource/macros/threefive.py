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
from typing import Literal

# PyQt5
from PyQt5.QtWidgets import (
    QDialog, QGridLayout, QLabel, QComboBox, 
    QLineEdit, QPushButton, QDoubleSpinBox, 
    QDialogButtonBox, QHBoxLayout, QWidget,
    QFrame, QVBoxLayout, QSizePolicy, QMessageBox,
    QCheckBox
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
# F1 - F8 Scancodes
F_SCANCODES = {
    1: 0x3B, 2: 0x3C, 3: 0x3D, 4: 0x3E,
    5: 0x3F, 6: 0x40, 7: 0x41, 8: 0x42
}
SC_W = 0x11  # W tuşu
SC_Z = 0x2C  # Z tuşu (Target)

# ---------------------------------------------------------
# 1. LOGIC (MAKRO MOTORU)
# ---------------------------------------------------------
class ThreeFiveMacro:
    """
    (Opsiyonel F) → 5'li ok → W → 3'lü ok → W döngüsü.
    Ayrıca opsiyonel 'Oto Z' döngüsü.
    """
    def __init__(
        self,
        f_bar: int = 3,
        key5: int = 2,
        key3: int = 3,
        combo_delay: float = 0.46,
        w_delay: float = 0.05,
        mode: str = "toggle",
        use_f_key: bool = True,
        use_z: bool = False,   # Yeni
        z_delay: float = 0.10  # Yeni
    ):
        self.f_bar = f_bar
        self.key5 = key5
        self.key3 = key3
        self.combo_delay = combo_delay
        self.w_delay = w_delay
        self.mode = mode
        self.use_f_key = use_f_key
        self.use_z = use_z
        self.z_delay = z_delay

        self._driver = _ClicksendKeyboardDriver() if _ClicksendKeyboardDriver else None
        
        # Thread yönetimi
        self._main_thread = None
        self._z_thread = None
        
        self._stop_event = threading.Event()
        self._running = False
        self._lock = threading.Lock() # Parametre güncelleme kilidi

    def set_params(self, f_bar, key5, key3, combo_delay, w_delay, mode, use_f_key, use_z, z_delay):
        with self._lock:
            self.f_bar = f_bar
            self.key5 = key5
            self.key3 = key3
            self.combo_delay = combo_delay
            self.w_delay = w_delay
            self.mode = mode
            self.use_f_key = use_f_key
            self.use_z = use_z
            self.z_delay = z_delay

    def update_config(self, cfg):
        """Global config'den ayarları yükle"""
        with self._lock:
            self.f_bar = int(cfg.get("f_bar", 3))
            self.key5 = int(cfg.get("key5", 2))
            self.key3 = int(cfg.get("key3", 3))
            self.combo_delay = float(cfg.get("combo_delay", 0.46))
            self.w_delay = float(cfg.get("w_delay", 0.05))
            self.mode = cfg.get("mode", "toggle")
            self.use_f_key = bool(cfg.get("use_f_key", True))
            self.use_z = bool(cfg.get("use_z", False))
            self.z_delay = float(cfg.get("z_delay", 0.10))

    @property
    def is_running(self):
        return self._running

    def toggle(self):
        with self._lock:
            if self.mode != "toggle": return
            if not self._running:
                self._start_internal()
            else:
                self._stop_internal()

    def hold_down(self):
        with self._lock:
            if self.mode != "hold": return
            if not self._running:
                self._start_internal()

    def hold_up(self):
        with self._lock:
            if self.mode != "hold": return
            if self._running:
                self._stop_internal()

    def _start_internal(self):
        print("[3/5] Başlatılıyor...")
        self._stop_event.clear()
        
        # 1. Ana Kombo Thread'i
        self._main_thread = threading.Thread(target=self._run_combo_loop, daemon=True)
        self._main_thread.start()

        # 2. (Opsiyonel) Z Thread'i
        if self.use_z:
            self._z_thread = threading.Thread(target=self._run_z_loop, daemon=True)
            self._z_thread.start()

        self._running = True

    def _stop_internal(self):
        print("[3/5] Durduruluyor...")
        self._stop_event.set()
        self._running = False

    # --- KOMBO DÖNGÜSÜ ---
    def _run_combo_loop(self):
        while not self._stop_event.is_set():
            try:
                self._do_combo_once()
            except Exception as e:
                print(f"[3/5] Kombo Hatası: {e}")
                break

    def _do_combo_once(self):
        if self._stop_event.is_set(): return

        # 1. F bar (Sadece checkbox işaretliyse bas)
        if self.use_f_key:
            self._tap_scan(F_SCANCODES.get(self.f_bar, 0x3D), 0.01)
        
        # 2. 5'li ok
        self._tap_digit(self.key5, self.combo_delay)
        if self._stop_event.is_set(): return

        # 3. W
        self._tap_scan(SC_W, self.w_delay)
        if self._stop_event.is_set(): return

        # 4. 3'lü ok
        self._tap_digit(self.key3, self.combo_delay)
        if self._stop_event.is_set(): return

        # 5. W
        self._tap_scan(SC_W, self.w_delay)

    # --- Z DÖNGÜSÜ ---
    def _run_z_loop(self):
        print("[3/5] Oto Z Başladı")
        while not self._stop_event.is_set():
            try:
                self._tap_scan(SC_Z, 0.02) # Z'ye hızlı bas çek
                
                # Bekleme (Stop event kontrolü ile)
                start_t = time.time()
                while time.time() - start_t < self.z_delay:
                    if self._stop_event.is_set(): return
                    time.sleep(0.01)
            except Exception as e:
                print(f"[3/5] Z Hatası: {e}")
                break

    # --- YARDIMCILAR ---
    def _tap_digit(self, digit: int, delay: float):
        sc = DIGIT_SCANCODES.get(digit)
        if sc: self._tap_scan(sc, delay)

    def _tap_scan(self, scancode: int, delay: float):
        if self._stop_event.is_set(): return
        
        if self._driver:
            self._driver.tusbas(scancode, delay)
        else:
            time.sleep(delay)


# ---------------------------------------------------------
# 2. GUI (AYAR PENCERESİ)
# ---------------------------------------------------------
class ThreeFiveSettingsDialog(QDialog):
    def __init__(self, parent=None, current_config=None):
        super().__init__(parent)
        self.setWindowTitle("3/5 AYARLARI")
        self.setModal(True)
        self._capture_next_key = False
        self.result_config = None

        if current_config is None: current_config = {}

        use_f_key = bool(current_config.get("use_f_key", True))
        f_bar = int(current_config.get("f_bar", 3))
        key5 = int(current_config.get("key5", 2))
        key3 = int(current_config.get("key3", 3))
        mode = current_config.get("mode", "toggle")
        hotkey = current_config.get("hotkey", "C")
        combo_delay = float(current_config.get("combo_delay", 0.40))
        w_delay = float(current_config.get("w_delay", 0.05))
        
        # Yeni Z ayarları
        use_z = bool(current_config.get("use_z", False))
        z_delay = float(current_config.get("z_delay", 0.10))

        # 3 Sütunlu Grid: [Checkbox] [Etiket] [Değer]
        layout = QGridLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(8)

        # --- SATIR 0: SKILL BAR ---
        self.chk_use_f = QCheckBox()
        self.chk_use_f.setChecked(use_f_key)
        self.chk_use_f.setToolTip("Skill Bar (F Tuşu) gönderilsin mi?")
        layout.addWidget(self.chk_use_f, 0, 0)

        layout.addWidget(QLabel("F BAR (F1–F8):"), 0, 1)

        self.cmb_fbar = QComboBox()
        for i in range(1, 9):
            self.cmb_fbar.addItem(f"F{i}", i)
        idx = self.cmb_fbar.findData(f_bar)
        if idx >= 0: self.cmb_fbar.setCurrentIndex(idx)
        layout.addWidget(self.cmb_fbar, 0, 2)
        
        self.cmb_fbar.setEnabled(use_f_key)
        self.chk_use_f.toggled.connect(self.cmb_fbar.setEnabled)


        # --- SATIR 1: 5'Lİ OK ---
        layout.addWidget(QLabel("5'Lİ OK TUŞU (0–9):"), 1, 1)
        self.cmb_key5 = QComboBox()
        self.cmb_key5.addItems([str(i) for i in range(10)])
        self.cmb_key5.setCurrentText(str(key5))
        layout.addWidget(self.cmb_key5, 1, 2)

        # --- SATIR 2: 3'LÜ OK ---
        layout.addWidget(QLabel("3'LÜ OK TUŞU (0–9):"), 2, 1)
        self.cmb_key3 = QComboBox()
        self.cmb_key3.addItems([str(i) for i in range(10)])
        self.cmb_key3.setCurrentText(str(key3))
        layout.addWidget(self.cmb_key3, 2, 2)

        # --- SATIR 3: MOD ---
        layout.addWidget(QLabel("3/5 MODU:"), 3, 1)
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItem("BAS / BIRAK (TOGGLE)", "toggle")
        self.cmb_mode.addItem("BASILI TUT (HOLD)", "hold")
        idx = self.cmb_mode.findData(mode)
        if idx >= 0: self.cmb_mode.setCurrentIndex(idx)
        layout.addWidget(self.cmb_mode, 3, 2)

        # --- SATIR 4: HOTKEY ---
        layout.addWidget(QLabel("AKTİF TUŞ:"), 4, 1)
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
        layout.addWidget(hk_widget, 4, 2)

        # --- SATIR 5: SKILL GECİKMESİ ---
        layout.addWidget(QLabel("SKILL GECİKMESİ (SN):"), 5, 1)
        self.spin_combo = QDoubleSpinBox()
        self.spin_combo.setRange(0.0, 1.0)
        self.spin_combo.setSingleStep(0.01)
        self.spin_combo.setValue(combo_delay)
        layout.addWidget(self.spin_combo, 5, 2)

        # --- SATIR 6: W GECİKMESİ ---
        layout.addWidget(QLabel("W BASMA SÜRESİ (SN):"), 6, 1)
        self.spin_w = QDoubleSpinBox()
        self.spin_w.setRange(0.0, 1.0)
        self.spin_w.setSingleStep(0.01)
        self.spin_w.setValue(w_delay)
        layout.addWidget(self.spin_w, 6, 2)
        
        # --- SATIR 7: OTO Z AYARLARI ---
        self.chk_use_z = QCheckBox()
        self.chk_use_z.setChecked(use_z)
        self.chk_use_z.setToolTip("Oto Z (Target) aktif edilsin mi?")
        layout.addWidget(self.chk_use_z, 7, 0)
        
        layout.addWidget(QLabel("OTO Z SÜRESİ (SN):"), 7, 1)
        
        self.spin_z = QDoubleSpinBox()
        self.spin_z.setRange(0.01, 2.0)
        self.spin_z.setSingleStep(0.01)
        self.spin_z.setValue(z_delay)
        layout.addWidget(self.spin_z, 7, 2)
        
        # Checkbox kapalıysa süreyi disable yap
        self.spin_z.setEnabled(use_z)
        self.chk_use_z.toggled.connect(self.spin_z.setEnabled)

        # --- BUTONLAR ---
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns, 8, 0, 1, 3) # 3 sütuna yayıl

        # Sütun Genişlik Ayarları
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
            if key == Qt.Key_NumLock: name = "NUM LOCK"
            elif key == Qt.Key_CapsLock: name = "CAPS LOCK"
            elif key == Qt.Key_ScrollLock: name = "SCROLL LOCK"
            elif key == Qt.Key_Pause: name = "PAUSE"
            elif key == Qt.Key_Print: name = "PRINT SCREEN"
            elif key == Qt.Key_Enter or key == Qt.Key_Return: name = "ENTER"
            elif key == Qt.Key_Escape: name = "ESC"
            elif key == Qt.Key_Tab: name = "TAB"
            elif key == Qt.Key_Backspace: name = "BACKSPACE"
            elif key == Qt.Key_Delete: name = "DELETE"
            elif key == Qt.Key_Insert: name = "INSERT"
            elif key == Qt.Key_Left: name = "LEFT"
            elif key == Qt.Key_Up: name = "UP"
            elif key == Qt.Key_Right: name = "RIGHT"
            elif key == Qt.Key_Down: name = "DOWN"
            elif key == Qt.Key_Home: name = "HOME"
            elif key == Qt.Key_End: name = "END"
            elif key == Qt.Key_PageUp: name = "PAGE UP"
            elif key == Qt.Key_PageDown: name = "PAGE DOWN"
            elif key == Qt.Key_Meta: name = "WINDOWS"
            elif key == Qt.Key_Menu: name = "MENU"
            elif key == Qt.Key_Space: name = "SPACE"
            elif key == Qt.Key_Shift: name = "SHIFT"
            elif key == Qt.Key_Control: name = "CTRL"
            elif key == Qt.Key_Alt: name = "ALT"
            elif Qt.Key_F1 <= key <= Qt.Key_F12: name = f"F{key - Qt.Key_F1 + 1}"
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
            "key5": int(self.cmb_key5.currentText()),
            "key3": int(self.cmb_key3.currentText()),
            "mode": self.cmb_mode.currentData(),
            "hotkey": self.edit_hotkey.text(),
            "combo_delay": self.spin_combo.value(),
            "w_delay": self.spin_w.value(),
            # Oto Z
            "use_z": self.chk_use_z.isChecked(),
            "z_delay": self.spin_z.value()
        }
        super().accept()


# ---------------------------------------------------------
# 3. WIDGET (ANA EKRAN KARTI)
# ---------------------------------------------------------
class ThreeFiveWidget(QFrame):
    update_signal = pyqtSignal()

    def __init__(self, parent=None, macro_instance=None, config=None):
        super().__init__(parent)
        self.macro = macro_instance
        self.config = config or {}
        
        self.listen_active = False
        self._hotkey_hook_handles = []
        
        self._last_toggle_time = 0

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

        # Header (DÜZENLENMİŞ KISIM)
        header = QHBoxLayout()
        header.setSpacing(6)
        
        # --- İKONLARI TEK BİR DÜZEN İÇİNE ALIYORUZ ---
        icon_row = QHBoxLayout()
        icon_row.setSpacing(3)
        icon_paths = ["icons/ok5li.png", "icons/ok3lu.png"] # 3'lü oku ekledik
        
        for path in icon_paths:
            lbl = QLabel()
            lbl.setFixedSize(25, 25)
            pix = QPixmap(path)
            if not pix.isNull():
                lbl.setPixmap(pix.scaled(25, 25, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            icon_row.addWidget(lbl)

        header.addLayout(icon_row) # İkonları sola yerleştir
        
        title_label = QLabel("3/5")
        title_label.setObjectName("MinorHeaderLabel")

        header.addStretch(1)      # Esnek boşluk koyarak yazıyı sağa it
        header.addWidget(title_label) # Yazıyı sağa yasla
        
        v.addLayout(header)

        self.btn_listen = QPushButton("TUŞ DİNLEMEYİ BAŞLAT")
        self.btn_listen.setObjectName("ThreeFiveListenButton")
        self.btn_listen.setProperty("active", False)
        self.btn_listen.clicked.connect(self.toggle_listen)
        v.addWidget(self.btn_listen)

        self.lbl_status = QLabel("DURUM: PASİF")
        self.lbl_status.setObjectName("MinorStatusLabel")
        v.addWidget(self.lbl_status)

        row = QHBoxLayout()
        row.setSpacing(4)
        row.addWidget(QLabel("AKTİF TUŞ:"))
        
        self.lbl_hotkey = QLabel(self.config.get("hotkey", "C"))
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
        dlg = ThreeFiveSettingsDialog(self, self.config)
        if dlg.exec_() == QDialog.Accepted and dlg.result_config:
            self.config.update(dlg.result_config)
            
            self.macro.set_params(
                f_bar=self.config["f_bar"],
                key5=self.config["key5"],
                key3=self.config["key3"],
                combo_delay=self.config["combo_delay"],
                w_delay=self.config["w_delay"],
                mode=self.config["mode"],
                use_f_key=self.config.get("use_f_key", True),
                use_z=self.config.get("use_z", False),
                z_delay=self.config.get("z_delay", 0.10)
            )
            self.lbl_hotkey.setText(self.config["hotkey"])
            
            # >>> ANA PENCERE CONFIG'İNİ GÜNCELLE
            parent = self.parent()
            while parent and not hasattr(parent, 'config'):
                parent = parent.parent()
            if parent and hasattr(parent, 'config'):
                if "threefive" in parent.config:
                    parent.config["threefive"].update(self.config)
            # <<<
            
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
            hotkey = self.config.get("hotkey", "C").lower()
            mode = self.config.get("mode", "toggle")
            self._hotkey_hook_handles.clear()
            
            try:
                if mode == "toggle":
                    h = keyboard.on_press_key(hotkey, lambda e: self.on_hotkey_toggle(), suppress=False)
                    self._hotkey_hook_handles.append(h)
                else:
                    h1 = keyboard.on_press_key(hotkey, lambda e: self.on_hotkey_hold_down(), suppress=False)
                    h2 = keyboard.on_release_key(hotkey, lambda e: self.on_hotkey_hold_up(), suppress=False)
                    self._hotkey_hook_handles.extend([h1, h2])
                self.listen_active = True
                print(f"[3/5] Dinleniyor: {hotkey}")
            except Exception as e:
                print(f"[3/5] Hotkey hatası: {e}")
                self.listen_active = False
        else:
            for h in self._hotkey_hook_handles:
                try: keyboard.unhook(h)
                except: pass
            self._hotkey_hook_handles.clear()
            
            self.listen_active = False
            if self.macro.is_running:
                if self.config.get("mode") == "toggle":
                    self.macro.toggle()
                else:
                    self.macro.hold_up()
        
        self._safe_update_status()

    def on_hotkey_toggle(self):
        current = time.time()
        if current - self._last_toggle_time < 0.2:
            return
        self._last_toggle_time = current
        self.macro.toggle()
        self.update_signal.emit()

    def on_hotkey_hold_down(self):
        if not self.macro.is_running:
            self.macro.hold_down()
            self.update_signal.emit()

    def on_hotkey_hold_up(self):
        if self.macro.is_running:
            self.macro.hold_up()
            self.update_signal.emit()

    def apply_status_style(self, color: str = "#8d95c7"):
        """Durum label'ının rengini ayarlar."""
        self.lbl_status.setStyleSheet(f"color: {color}; font-weight: bold;")

    def _safe_update_status(self):
        if not self.listen_active:
            # PASİF DURUM
            self.lbl_status.setText("DURUM: PASİF")
            self.btn_listen.setText("TUŞ DİNLEMEYİ BAŞLAT")
            self.apply_status_style("#ff5555") # KIRMIZI
            is_active = False
        else:
            # DİNLEME AKTİF
            if self.macro.is_running:
                # ÇALIŞIYOR
                self.lbl_status.setText("DURUM: ÇALIŞIYOR")
                self.apply_status_style("#00ff4c") # YEŞİL
            else:
                # BEKLİYOR
                self.lbl_status.setText("DURUM: BEKLİYOR")
                self.apply_status_style("#ffff55") # SARI

            self.btn_listen.setText("TUŞ DİNLEMEYİ DURDUR")
            is_active = True
        
        # Buton stilini (Kırmızı/Yeşil) güncelle
        self.btn_listen.setProperty("active", is_active)
        self.btn_listen.style().unpolish(self.btn_listen)
        self.btn_listen.style().polish(self.btn_listen)
