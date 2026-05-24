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

# PyQt5
from PyQt5.QtWidgets import (
    QDialog, QGridLayout, QLabel, QComboBox, 
    QLineEdit, QPushButton, QDoubleSpinBox, 
    QDialogButtonBox, QHBoxLayout, QWidget,
    QFrame, QVBoxLayout, QSizePolicy, QMessageBox,
    QCheckBox, QGroupBox, QRadioButton, QButtonGroup
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

try:
    import keyboard
except ImportError:
    keyboard = None


# ---------------------------------------------------------
# 1. LOGIC (MAKRO MOTORU)
# ---------------------------------------------------------
class PriestKalkanMacro:
    def __init__(self):
        self.key = "F"
        self.coords = (0, 0)
        self.inv_speed = 0.1      # Envanter açma hızı
        self.click_speed = 0.1    # Tıklama hızı (Loop için)
        
        self.mode = "single"      # "single" veya "loop"
        self.inv_mode = False     # Çanta zaten açık mı?
        self.return_mouse = False # Mouse geri dönsün mü?
        
        self._driver = _ClicksendKeyboardDriver() if _ClicksendKeyboardDriver else None
        self._mouse = _ClicksendMouseDriver() if _ClicksendMouseDriver else None
        
        self._running = False
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    def update_config(self, cfg):
        with self._lock:
            self.key = cfg.get("key", "F")
            self.coords = cfg.get("coords", (0, 0))
            self.inv_speed = cfg.get("inv_speed", 0.1)
            self.click_speed = cfg.get("click_speed", 0.1)
            self.mode = cfg.get("mode", "single")
            self.inv_mode = cfg.get("inv_mode", False)
            self.return_mouse = cfg.get("return_mouse", False)

    @property
    def is_running(self):
        return self._running 

    def toggle(self):
        if self._running:
            self.stop()
        else:
            self.start()

    def start(self):
        if self._running: return
        self._stop_event.clear()
        self._running = True
        
        if self.mode == "loop":
            threading.Thread(target=self._loop_logic, daemon=True).start()
        else:
            threading.Thread(target=self._single_logic, daemon=True).start()

    def stop(self):
        self._stop_event.set()
        self._running = False

    # --- MOD 1: TEK SEFERLİK (WARRIOR GİBİ) ---
    def _single_logic(self):
        start_x, start_y = pyautogui.position()
        try:
            if self.coords == (0, 0): return

            # 1. Çanta Aç
            if not self.inv_mode:
                self._tap_key(SC_I, 0.05)
                time.sleep(self.inv_speed)

            # 2. Tıkla
            self._right_click_at(self.coords[0], self.coords[1])
            time.sleep(0.05)

            # 3. Çanta Kapat
            if not self.inv_mode:
                self._tap_key(SC_I, 0.05)

            # 4. Geri Dön
            if self.return_mouse:
                self._move_mouse(start_x, start_y)

        except Exception as e:
            print(f"[PRIEST KALKAN] Hata: {e}")
        finally:
            self._running = False

    # --- MOD 2: SÜREKLİ TAK/ÇIKAR (LOOP) ---
    def _loop_logic(self):
        print("[PRIEST KALKAN] Loop Başladı...")
        start_x, start_y = pyautogui.position()
        
        try:
            if self.coords == (0, 0): return

            # 1. Döngü Başında Çanta Aç
            if not self.inv_mode:
                self._tap_key(SC_I, 0.05)
                time.sleep(self.inv_speed)

            # 2. Döngüsel Tıklama
            while not self._stop_event.is_set():
                self._right_click_at(self.coords[0], self.coords[1])
                time.sleep(self.click_speed)

            # 3. Döngü Bitince Çanta Kapat
            if not self.inv_mode:
                self._tap_key(SC_I, 0.05)

            # 4. Geri Dön
            if self.return_mouse:
                self._move_mouse(start_x, start_y)

        except Exception as e:
            print(f"[PRIEST KALKAN] Loop Hata: {e}")
        finally:
            self._running = False
            print("[PRIEST KALKAN] Loop Bitti.")

    # --- YARDIMCILAR ---
    def _tap_key(self, sc, delay):
        if self._driver: self._driver.tusbas(sc, delay)
        else: pyautogui.press('i'); time.sleep(delay)

    def _right_click_at(self, x, y):
        if self._mouse:
            self._mouse.rightclick(0.05, int(x), int(y))
        else:
            pyautogui.moveTo(x, y)
            pyautogui.rightClick()

    def _move_mouse(self, x, y):
        if self._mouse and hasattr(self._mouse, 'move'):
            self._mouse.move(int(x), int(y))
        else:
            pyautogui.moveTo(x, y)


# ---------------------------------------------------------
# 2. GUI (AYAR PENCERESİ)
# ---------------------------------------------------------
class PriestKalkanSettings(QDialog):
    def __init__(self, parent=None, current_config=None):
        super().__init__(parent)
        self.setWindowTitle("PRIEST KALKAN AYARLARI")
        self.setModal(True)
        self.config = current_config or {}
        
        self.coords = self.config.get("coords", (0, 0))
        self.capture_active = False
        self.hotkey_capture = False
        self.hook_f = None

        layout = QVBoxLayout(self)
        
        # --- KOORDİNAT ---
        grp_coord = QGroupBox("1. Kalkan Koordinatı")
        gc = QHBoxLayout(grp_coord)
        self.lbl_coord = QLineEdit(f"{self.coords[0]}, {self.coords[1]}")
        self.lbl_coord.setReadOnly(True)
        btn_cap = QPushButton("YAKALA (F)")
        btn_cap.clicked.connect(self.start_coord_capture)
        gc.addWidget(self.lbl_coord); gc.addWidget(btn_cap)
        layout.addWidget(grp_coord)

        # --- MOD SEÇİMİ ---
        grp_mode = QGroupBox("2. Çalışma Modu")
        gm = QVBoxLayout(grp_mode)
        self.rb_single = QRadioButton("Tek Seferlik (Normal Tak/Çıkar)")
        self.rb_loop = QRadioButton("Sürekli Döngü (Seri Tak/Çıkar)")
        
        bg = QButtonGroup(self)
        bg.addButton(self.rb_single); bg.addButton(self.rb_loop)
        
        mode = self.config.get("mode", "single")
        if mode == "loop": self.rb_loop.setChecked(True)
        else: self.rb_single.setChecked(True)
        
        gm.addWidget(self.rb_single); gm.addWidget(self.rb_loop)
        layout.addWidget(grp_mode)

        # --- AYARLAR ---
        grp_set = QGroupBox("3. Zamanlama ve Seçenekler")
        gs = QGridLayout(grp_set)
        
        gs.addWidget(QLabel("Çanta Açılış Gecikmesi:"), 0, 0)
        self.spin_inv_spd = QDoubleSpinBox(); self.spin_inv_spd.setRange(0.01, 1.0); self.spin_inv_spd.setValue(self.config.get("inv_speed", 0.1))
        gs.addWidget(self.spin_inv_spd, 0, 1)

        gs.addWidget(QLabel("Tıklama Hızı (Loop İçin):"), 1, 0)
        self.spin_click_spd = QDoubleSpinBox(); self.spin_click_spd.setRange(0.01, 2.0); self.spin_click_spd.setValue(self.config.get("click_speed", 0.1))
        gs.addWidget(self.spin_click_spd, 1, 1)

        self.chk_inv = QCheckBox("Çanta Zaten Açık (I Basma)")
        self.chk_inv.setChecked(self.config.get("inv_mode", False))
        gs.addWidget(self.chk_inv, 2, 0, 1, 2)

        self.chk_return = QCheckBox("Mouse Geri Dönsün")
        self.chk_return.setChecked(self.config.get("return_mouse", False))
        gs.addWidget(self.chk_return, 3, 0, 1, 2)
        
        layout.addWidget(grp_set)

        # --- HOTKEY ---
        h_key = QHBoxLayout()
        h_key.addWidget(QLabel("Başlatma Tuşu:"))
        self.txt_hotkey = QLineEdit(self.config.get("key", "F"))
        self.txt_hotkey.setReadOnly(True)
        btn_hk = QPushButton("SEÇ")
        btn_hk.clicked.connect(self.start_hotkey_capture)
        h_key.addWidget(self.txt_hotkey); h_key.addWidget(btn_hk)
        layout.addLayout(h_key)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.save_config)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        if keyboard:
            try: self.hook_f = keyboard.on_press_key("F", self.on_f_press)
            except: pass

    def closeEvent(self, e):
        if keyboard and self.hook_f:
            try: keyboard.unhook(self.hook_f)
            except: pass
        super().closeEvent(e)

    def start_coord_capture(self):
        self.capture_active = True
        self.lbl_coord.setText("F Bas...")

    def on_f_press(self, e):
        if self.capture_active:
            x, y = pyautogui.position()
            self.coords = (x, y)
            self.lbl_coord.setText(f"{x}, {y}")
            self.capture_active = False

    def start_hotkey_capture(self):
        self.hotkey_capture = True
        self.txt_hotkey.setText("...")

    def keyPressEvent(self, e):
        if self.hotkey_capture:
            k = e.text().upper()
            if not k: 
                if e.key() == Qt.Key_F1: k = "F1"
                # ... diğer F tuşları eklenebilir
            if k:
                self.txt_hotkey.setText(k)
                self.hotkey_capture = False
        else:
            super().keyPressEvent(e)

    def save_config(self):
        self.result_config = {
            "key": self.txt_hotkey.text(),
            "coords": self.coords,
            "mode": "loop" if self.rb_loop.isChecked() else "single",
            "inv_speed": self.spin_inv_spd.value(),
            "click_speed": self.spin_click_spd.value(),
            "inv_mode": self.chk_inv.isChecked(),
            "return_mouse": self.chk_return.isChecked()
        }
        self.accept()

# ---------------------------------------------------------
# 3. WIDGET
# ---------------------------------------------------------
class PriestKalkanWidget(QFrame):
    update_signal = pyqtSignal()

    def __init__(self, parent=None, macro_instance=None, config=None):
        super().__init__(parent)
        self.macro = macro_instance or PriestKalkanMacro()
        self.config = config or {}
        self.macro.update_config(self.config)
        
        self.listen_active = False
        self._hooks = []
        self.update_signal.connect(self._safe_update)
        self.setup_ui()
        self._safe_update()

    def setup_ui(self):
        self.setFrameShape(QFrame.Box)
        self.setMaximumWidth(260)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setStyleSheet("QFrame { background-color: #101010; border: 1px solid #444; border-radius: 4px; }")
        v = QVBoxLayout(self); v.setContentsMargins(6,6,6,6); v.setSpacing(4)

        h = QHBoxLayout()
        icon_lbl = QLabel()
        icon_lbl.setFixedSize(25, 25)
        # Warrior kalkan ikonunu kullanıyoruz
        pix = QPixmap("icons/wari/kalkan1.png")
        if not pix.isNull():
            icon_lbl.setPixmap(pix.scaled(25, 25, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            icon_lbl.setText("🛡️")
            icon_lbl.setStyleSheet("font-size:20px; border:none;")
        
        h.addWidget(icon_lbl); h.addStretch()
        h.addWidget(QLabel("PRIEST KALKAN", objectName="MinorHeaderLabel"))
        v.addLayout(h)

        self.btn_listen = QPushButton("TUŞ DİNLEMEYİ BAŞLAT")
        self.btn_listen.setObjectName("ThreeFiveListenButton")
        self.btn_listen.clicked.connect(self.toggle_listen)
        v.addWidget(self.btn_listen)

        self.lbl_status = QLabel("PASİF"); self.lbl_status.setObjectName("MinorStatusLabel")
        v.addWidget(self.lbl_status)

        r = QHBoxLayout(); r.addWidget(QLabel("TUŞ:"))
        self.lbl_key = QLabel(self.config.get("key", "F")); self.lbl_key.setObjectName("HotkeyLabel")
        r.addWidget(self.lbl_key)
        btn_set = QPushButton("⚙"); btn_set.setObjectName("MinorSettingsButton")
        btn_set.clicked.connect(self.open_settings)
        r.addWidget(btn_set)
        v.addLayout(r)

    def open_settings(self):
        dlg = PriestKalkanSettings(self, self.config)
        if dlg.exec_():
            self.config = dlg.result_config
            self.macro.update_config(self.config)
            self.lbl_key.setText(self.config["key"])
            if self.listen_active: self.toggle_listen(); self.toggle_listen()

    def toggle_listen(self):
        if not keyboard: return
        if not self.listen_active:
            hk = self.config.get("key", "F").lower()
            try:
                # Toggle mantığı
                self._hooks.append(keyboard.on_press_key(hk, lambda e: self.on_hotkey(), suppress=False))
                self.listen_active = True
            except: self.listen_active = False
        else:
            for h in self._hooks: 
                try: keyboard.unhook(h)
                except: pass
            self._hooks = []
            self.listen_active = False
            self.macro.stop()
        self._safe_update()

    def on_hotkey(self):
        self.macro.toggle()
        self.update_signal.emit()

    def _safe_update(self):
        if not self.listen_active:
            self.lbl_status.setText("PASİF"); self.lbl_status.setStyleSheet("color:#ff5555;font-weight:bold;")
            self.btn_listen.setText("TUŞ DİNLEMEYİ BAŞLAT"); self.btn_listen.setProperty("active", False)
        else:
            if self.macro.is_running:
                mode = "LOOP" if self.config.get("mode") == "loop" else "TEK"
                self.lbl_status.setText(f"ÇALIŞIYOR ({mode})")
                self.lbl_status.setStyleSheet("color:#00ff4c;font-weight:bold;")
            else:
                self.lbl_status.setText("BEKLİYOR")
                self.lbl_status.setStyleSheet("color:#ffff55;font-weight:bold;")
            
            # --- DÜZELTİLEN KISIM ---
            self.btn_listen.setText("TUŞ DİNLEMEYİ DURDUR"); 
            self.btn_listen.setProperty("active", True)
        
        self.btn_listen.style().unpolish(self.btn_listen)
        self.btn_listen.style().polish(self.btn_listen)
        
        if self.listen_active: QTimer.singleShot(200, self._safe_update)
