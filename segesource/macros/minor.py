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
    QCheckBox, QGroupBox, QSpinBox
)
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtCore import Qt, QSize, pyqtSignal, QTimer

# Opsiyonel clicksend / interception sürücüsü
try:
    from clicksend import KeyboardDriver as _ClicksendKeyboardDriver
except ImportError:
    _ClicksendKeyboardDriver = None


# ---------------------------------------------------------
# SABİTLER & YARDIMCI FONKSİYONLAR
# ---------------------------------------------------------
DIGIT_SCANCODES = {
    1: 0x02, 2: 0x03, 3: 0x04, 4: 0x05, 5: 0x06,
    6: 0x07, 7: 0x08, 8: 0x09, 9: 0x0A, 0: 0x0B,
}

def _default_send_key(scan_code: int):
    if _ClicksendKeyboardDriver is None:
        return
    if not hasattr(_default_send_key, "_driver"):
        _default_send_key._driver = _ClicksendKeyboardDriver()
    _default_send_key._driver.tusbas(scan_code, 0.01)


# =========================================================
# 1. LOGIC (MAKRO MOTORU)
# =========================================================
class MinorMacro:
    """
    1x mana + Nx minör patternini sürekli atan motor.
    """
    def __init__(
        self,
        mana_key: int = 7,
        minor_key: int = 8,
        mode: Literal["toggle", "hold"] = "toggle",
        send_key = None,  # Optional[Callable[[int], None]]
        combo_delay: float = 0.00,
        hp_key: int = 1,
        minor_count: int = 3  # YENİ PARAMETRE: Varsayılan 3
    ):
        self.mana_key = mana_key
        self.minor_key = minor_key
        self.hp_key = hp_key
        self.mode = mode
        self.combo_delay = combo_delay
        self.minor_count = minor_count

        self._send_key = send_key or _default_send_key
        self._thread = None  # Optional[threading.Thread]
        self._stop_event = threading.Event()
        self._running = False
        self._lock = threading.Lock() 
        
        self.hp_mode_active = False

    def set_params(self, mana_key, minor_key, mode, combo_delay, hp_key, minor_count):
        with self._lock:
            self.mana_key = mana_key
            self.minor_key = minor_key
            self.mode = mode
            self.combo_delay = combo_delay
            self.hp_key = hp_key
            self.minor_count = minor_count

    def toggle_hp_mode(self):
        self.hp_mode_active = not self.hp_mode_active
        return self.hp_mode_active

    @property
    def is_running(self) -> bool:
        return self._running

    def toggle(self):
        if self.mode != "toggle": return
        if self._running:
            self.stop()
        else:
            self.start()

    def hold_down(self):
        if self.mode != "hold": return
        if not self._running:
            self.start()

    def hold_up(self):
        if self.mode == "hold":
            if self._running:
                self.stop()

    def start(self):
        if self._running: return

        # Zombi Thread Koruması
        if self._thread and self._thread.is_alive():
            self._stop_event.set()
            self._thread.join(timeout=1.0)

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._running = True
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        self._running = False

    def _loop(self):
        while not self._stop_event.is_set():
            first_key = self.hp_key if self.hp_mode_active else self.mana_key
            
            try:
                # 1. Mana Bas
                self._press_digit(first_key)
                
                # 2. Minör Bas (Seçilen Adet Kadar)
                # Döngü içinde stop kontrolü yapmıyoruz ki kombo yarım kalmasın
                for _ in range(self.minor_count):
                    self._press_digit(self.minor_key)
                    
            except Exception:
                pass

            # Güvenli Bekleme
            if self.combo_delay > 0:
                if self._sleep_safe(self.combo_delay): break
            else:
                time.sleep(0.001)

    def _sleep_safe(self, duration):
        end_time = time.time() + duration
        while time.time() < end_time:
            if self._stop_event.is_set(): return True
            time.sleep(0.005) 
        return False

    def _press_digit(self, digit: int):
        sc = DIGIT_SCANCODES.get(digit)
        if sc: self._send_key(sc)


# =========================================================
# 2. GUI (AYAR PENCERESİ)
# =========================================================
class MinorSettingsDialog(QDialog):
    def __init__(self, parent=None, current_config=None):
        super().__init__(parent)
        self.setWindowTitle("MİNÖR AYARLARI")
        self.setModal(True)
        self._capture_target = None 
        self.result_config = None

        if current_config is None: current_config = {}

        mana_key = int(current_config.get("mana_key", 7))
        minor_key = int(current_config.get("minor_key", 8))
        mode = current_config.get("mode", "toggle")
        hotkey = current_config.get("hotkey", "V")
        combo_delay = float(current_config.get("combo_delay", 0.0))
        hp_convert_enabled = bool(current_config.get("hp_convert_enabled", False))
        hp_key = int(current_config.get("hp_key", 1))
        hp_convert_hotkey = current_config.get("hp_convert_hotkey", "G")
        minor_count = int(current_config.get("minor_count", 3)) # Varsayılan 3

        layout = QVBoxLayout(self)
        
        # --- GENEL AYARLAR ---
        grp_main = QGroupBox("TEMEL AYARLAR")
        grid = QGridLayout(grp_main)
        
        grid.addWidget(QLabel("MANA TUŞU (0-9):"), 0, 0)
        self.cmb_mana = QComboBox()
        self.cmb_mana.addItems([str(i) for i in range(10)])
        self.cmb_mana.setCurrentText(str(mana_key))
        grid.addWidget(self.cmb_mana, 0, 1)

        grid.addWidget(QLabel("MİNÖR TUŞU (0-9):"), 1, 0)
        self.cmb_minor = QComboBox()
        self.cmb_minor.addItems([str(i) for i in range(10)])
        self.cmb_minor.setCurrentText(str(minor_key))
        grid.addWidget(self.cmb_minor, 1, 1)

        # --- YENİ EKLENEN: MİNÖR ADEDİ ---
        grid.addWidget(QLabel("MİNÖR ADEDİ (1-9):"), 2, 0)
        self.spin_count = QSpinBox()
        self.spin_count.setRange(1, 9)
        self.spin_count.setValue(minor_count)
        self.spin_count.setSuffix(" x")
        grid.addWidget(self.spin_count, 2, 1)

        grid.addWidget(QLabel("GECİKME (SN):"), 3, 0)
        self.spin_delay = QDoubleSpinBox()
        self.spin_delay.setRange(0.0, 1.0)
        self.spin_delay.setSingleStep(0.005)
        self.spin_delay.setValue(combo_delay)
        grid.addWidget(self.spin_delay, 3, 1)

        grid.addWidget(QLabel("MİNÖR MODU:"), 4, 0)
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItem("BAS / BIRAK (TOGGLE)", "toggle")
        self.cmb_mode.addItem("BASILI TUT (HOLD)", "hold")
        idx = self.cmb_mode.findData(mode)
        if idx >= 0: self.cmb_mode.setCurrentIndex(idx)
        grid.addWidget(self.cmb_mode, 4, 1)

        grid.addWidget(QLabel("BAŞLATMA TUŞU:"), 5, 0)
        self.edit_hotkey = QLineEdit(hotkey)
        self.edit_hotkey.setReadOnly(True)
        hk_layout = QHBoxLayout()
        hk_layout.addWidget(self.edit_hotkey)
        btn_cap = QPushButton("TUŞ SEÇ")
        btn_cap.clicked.connect(lambda: self.start_capture("main"))
        hk_layout.addWidget(btn_cap)
        hk_widget = QWidget()
        hk_widget.setLayout(hk_layout)
        grid.addWidget(hk_widget, 5, 1)
        
        layout.addWidget(grp_main)

        # --- HP ÇEVİR ---
        grp_hp = QGroupBox("HP ÇEVİR (SWAP) AYARLARI")
        grid_hp = QGridLayout(grp_hp)

        self.chk_hp_enable = QCheckBox("HP ÇEVİR AKTİF ET")
        self.chk_hp_enable.setChecked(hp_convert_enabled)
        grid_hp.addWidget(self.chk_hp_enable, 0, 0, 1, 2)

        grid_hp.addWidget(QLabel("HP POT TUŞU:"), 1, 0)
        self.cmb_hp_key = QComboBox()
        self.cmb_hp_key.addItems([str(i) for i in range(10)])
        self.cmb_hp_key.setCurrentText(str(hp_key))
        grid_hp.addWidget(self.cmb_hp_key, 1, 1)

        grid_hp.addWidget(QLabel("ÇEVİRME TUŞU:"), 2, 0)
        self.edit_hp_hotkey = QLineEdit(hp_convert_hotkey)
        self.edit_hp_hotkey.setReadOnly(True)
        hp_hk_layout = QHBoxLayout()
        hp_hk_layout.addWidget(self.edit_hp_hotkey)
        btn_hp_cap = QPushButton("TUŞ SEÇ")
        btn_hp_cap.clicked.connect(lambda: self.start_capture("hp_swap"))
        hp_hk_layout.addWidget(btn_hp_cap)
        hp_hk_widget = QWidget()
        hp_hk_widget.setLayout(hp_hk_layout)
        grid_hp.addWidget(hp_hk_widget, 2, 1)

        layout.addWidget(grp_hp)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def start_capture(self, target):
        self._capture_target = target
        if target == "main": self.edit_hotkey.setText("TUŞA BAS...")
        else: self.edit_hp_hotkey.setText("TUŞA BAS...")
        self.grabKeyboard()

    def keyPressEvent(self, event):
        if self._capture_target:
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
                if text: name = text.upper()
            
            if name:
                if self._capture_target == "main": self.edit_hotkey.setText(name)
                else: self.edit_hp_hotkey.setText(name)
                self._capture_target = None
                self.releaseKeyboard()
            return
        super().keyPressEvent(event)

    def accept(self):
        self.result_config = {
            "mana_key": int(self.cmb_mana.currentText()),
            "minor_key": int(self.cmb_minor.currentText()),
            "mode": self.cmb_mode.currentData(),
            "hotkey": self.edit_hotkey.text(),
            "combo_delay": self.spin_delay.value(),
            "hp_convert_enabled": self.chk_hp_enable.isChecked(),
            "hp_key": int(self.cmb_hp_key.currentText()),
            "hp_convert_hotkey": self.edit_hp_hotkey.text(),
            "minor_count": self.spin_count.value() # Yeni parametre
        }
        super().accept()


# =========================================================
# 3. WIDGET (ANA EKRAN KARTI)
# =========================================================
class MinorWidget(QFrame):
    HP_SWAP_DEBOUNCE_TIME = 0.5 
    update_signal = pyqtSignal()

    def __init__(self, parent=None, macro_instance=None, config=None):
        super().__init__(parent)
        self.macro = macro_instance
        self.config = config or {}
        
        if self.macro:
             self.macro.hp_key = int(self.config.get("hp_key", 1))
             # Makroya minor_count'u da yükle
             self.macro.minor_count = int(self.config.get("minor_count", 3))

        self.listen_active = False
        self._hotkey_hook_handles = []
        self._last_hp_swap_press = time.time()
        self._last_toggle_press = 0
        
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

        h = QHBoxLayout()
        h.setSpacing(6)
        
        # --- TEK İKON YERİNE 1 MP + 3 MİNÖR DİZİLİMİ ---
        icon_row = QHBoxLayout()
        icon_row.setSpacing(2) # İkonlar arası boşluk
        
        # 1. Mana İkonu (mp.png)
        lbl_mana = QLabel(); lbl_mana.setFixedSize(25, 25)
        pix_mana = QPixmap("icons/mp.png")
        if not pix_mana.isNull():
            lbl_mana.setPixmap(pix_mana.scaled(25, 25, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        icon_row.addWidget(lbl_mana)
        
        # 2. Üç Adet Minör İkonu (minor.png)
        for _ in range(3):
            lbl_minor = QLabel(); lbl_minor.setFixedSize(25, 25)
            pix_minor = QPixmap("icons/minor.png")
            if not pix_minor.isNull():
                lbl_minor.setPixmap(pix_minor.scaled(25, 25, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            icon_row.addWidget(lbl_minor)

        # Dizilimi ana başlık düzenine (h) ekle
        h.addLayout(icon_row) 
        h.addStretch(1)  # Aradaki boşluğu doldur (Stretch)
        
        title = QLabel("MİNÖR"); title.setObjectName("MinorHeaderLabel") 
        h.addWidget(title) # Yazıyı en sağa koy
        
        v.addLayout(h)

        self.btn_listen = QPushButton("TUŞ DİNLEMEYİ BAŞLAT")
        self.btn_listen.setObjectName("MinorListenButton")
        self.btn_listen.setProperty("active", False)
        self.btn_listen.clicked.connect(self.toggle_listen)
        v.addWidget(self.btn_listen)

        self.lbl_status = QLabel("DURUM: PASİF")
        self.lbl_status.setObjectName("MinorStatusLabel")
        v.addWidget(self.lbl_status)

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
        dlg = MinorSettingsDialog(self, self.config)
        if dlg.exec_() == QDialog.Accepted and dlg.result_config:
            self.config.update(dlg.result_config)
            self.macro.set_params(
                self.config["mana_key"], self.config["minor_key"], self.config["mode"],
                self.config["combo_delay"], self.config["hp_key"], self.config.get("minor_count", 3)
            )
            self.lbl_hotkey.setText(self.config["hotkey"])
            
            if self.listen_active:
                self.toggle_listen() # Durdur
                QTimer.singleShot(150, self.toggle_listen) # Başlat

    def toggle_listen(self):
        try: import keyboard
        except: return QMessageBox.warning(self, "Hata", "keyboard eksik")

        if not self.listen_active:
            main_hotkey = self.config.get("hotkey", "V").lower()
            mode = self.config.get("mode", "toggle")
            
            hp_enabled = self.config.get("hp_convert_enabled", False)
            hp_swap_hotkey = self.config.get("hp_convert_hotkey", "G").lower()

            self._hotkey_hook_handles.clear()
            self.macro.hp_mode_active = False 

            try:
                if mode == "toggle":
                    h = keyboard.on_press_key(main_hotkey, lambda e: self.on_hotkey_toggle(), suppress=False)
                    self._hotkey_hook_handles.append(h)
                else:
                    h1 = keyboard.on_press_key(main_hotkey, lambda e: self.on_hotkey_hold_down(), suppress=False)
                    h2 = keyboard.on_release_key(main_hotkey, lambda e: self.on_hotkey_hold_up(), suppress=False)
                    self._hotkey_hook_handles.extend([h1, h2])

                if hp_enabled:
                    h_swap = keyboard.on_press_key(hp_swap_hotkey, lambda e: self.on_hp_swap_toggle(), suppress=False)
                    self._hotkey_hook_handles.append(h_swap)

                self.listen_active = True
            except Exception as e:
                print(e); self.listen_active = False
        else:
            for h in self._hotkey_hook_handles:
                try: keyboard.unhook(h)
                except: pass
            self._hotkey_hook_handles.clear()
            self.listen_active = False
            self.macro.stop()
        
        self._safe_update_status()

    def on_hotkey_toggle(self):
        current_time = time.time()
        if current_time - self._last_toggle_press < 0.2: return 
        self._last_toggle_press = current_time
        
        threading.Thread(target=self._run_toggle_thread, daemon=True).start()

    def _run_toggle_thread(self):
        self.macro.toggle()
        self.update_signal.emit()

    def on_hotkey_hold_down(self):
        if not self.macro.is_running:
            self.macro.hold_down()
            self.update_signal.emit()

    def on_hotkey_hold_up(self):
        if self.macro.mode == "hold" and self.macro.is_running:
            self.macro.stop()
            self.update_signal.emit()

    def on_hp_swap_toggle(self):
        current_time = time.time()
        if current_time - self._last_hp_swap_press < self.HP_SWAP_DEBOUNCE_TIME: return
        self._last_hp_swap_press = current_time
        
        self.macro.toggle_hp_mode()
        self.update_signal.emit()

    def apply_status_style(self, color: str = "#8d95c7"):
        self.lbl_status.setStyleSheet(f"color: {color}; font-weight: bold;")
        
    def _safe_update_status(self):
        if not self.listen_active:
            self.lbl_status.setText("DURUM: PASİF")
            self.btn_listen.setText("TUŞ DİNLEMEYİ BAŞLAT")
            self.apply_status_style("#ff5555")
            active = False
        else:
            hp_s = "(HP MODU)" if self.macro.hp_mode_active else "(MANA MODU)"
            if self.macro.is_running:
                self.lbl_status.setText(f"DURUM: ÇALIŞIYOR {hp_s}")
                self.apply_status_style("#00ff4c")
            else:
                self.lbl_status.setText(f"DURUM: BEKLİYOR {hp_s}")
                self.apply_status_style("#ffff55")
            self.btn_listen.setText("TUŞ DİNLEMEYİ DURDUR")
            active = True
        
        self.btn_listen.setProperty("active", active)
        self.btn_listen.style().unpolish(self.btn_listen)
        self.btn_listen.style().polish(self.btn_listen)
