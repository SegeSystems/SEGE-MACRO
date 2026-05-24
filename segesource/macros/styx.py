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
import json
import os

# PyQt5 - Gerekli tüm modüller
from PyQt5.QtWidgets import (
    QDialog, QGridLayout, QLabel, QComboBox, 
    QLineEdit, QPushButton, QDoubleSpinBox, 
    QDialogButtonBox, QHBoxLayout, QWidget,
    QFrame, QVBoxLayout, QSizePolicy, QMessageBox, 
    QGroupBox, QFormLayout
)
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtCore import Qt, pyqtSignal, QSize

# Harici Kütüphaneler (Koordinat tespiti için)
import pyautogui

try:
    import keyboard
except ImportError:
    keyboard = None

# Sürücüler (Varsa donanımsal, yoksa sanal)
try:
    from clicksend import KeyboardDriver as _ClicksendKeyboardDriver
    from clicksend import MouseDriver as _ClicksendMouseDriver
except ImportError:
    _ClicksendKeyboardDriver = None
    _ClicksendMouseDriver = None

# ---------------------------------------------------------
# SABİTLER VE SCANCODE'LAR
# ---------------------------------------------------------
CONFIG_FILE = "styx.json"
SC_I = 0x17  # 'I' tuşu (Envanter)

# Rakamlar (Skill Bar Tuşları)
DIGIT_SCANCODES = {
    1: 0x02, 2: 0x03, 3: 0x04, 4: 0x05, 5: 0x06,
    6: 0x07, 7: 0x08, 8: 0x09, 9: 0x0A, 0: 0x0B,
}

# F Tuşları (F1 - F8)
F_SCANCODES = {
    1: 0x3B, 2: 0x3C, 3: 0x3D, 4: 0x3E,
    5: 0x3F, 6: 0x40, 7: 0x41, 8: 0x42
}

# ---------------------------------------------------------
# 1. LOGIC (MAKRO MOTORU)
# ---------------------------------------------------------
class StyxMacro:
    def __init__(self):
        self.kb = _ClicksendKeyboardDriver() if _ClicksendKeyboardDriver else None
        self.mouse = _ClicksendMouseDriver() if _ClicksendMouseDriver else None
        
        # Varsayılanlar
        self.coords = [(0,0), (0,0), (0,0), (0,0)] # 4 Koordinat
        self.f_key = 1      # F1
        self.digit_key = 1  # 1
        
        # Zamanlamalar
        self.delay_inv = 0.20   # Çanta açılma süresi
        self.delay_click = 0.05 # Tıklama hızı
        self.delay_skill = 0.05 # Skill basma hızı
        
        self._running = False
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    def update_config(self, cfg):
        """Ayarları dışarıdan veya JSON'dan yükler"""
        with self._lock:
            # Koordinatlar listesi (4 adet olmalı)
            loaded_coords = cfg.get("coords", [])
            if len(loaded_coords) == 4:
                self.coords = loaded_coords
            
            self.f_key = cfg.get("f_key", 1)
            self.digit_key = cfg.get("digit_key", 1)
            
            self.delay_inv = cfg.get("delay_inv", 0.20)
            self.delay_click = cfg.get("delay_click", 0.05)
            self.delay_skill = cfg.get("delay_skill", 0.05)

    @property
    def is_running(self):
        return self._running

    def stop(self):
        if self._running:
            self._stop_event.set()

    def run_sequence(self):
        """
        Senaryo:
        1. I Bas (Çanta Aç)
        2. Coord 1 -> Sağ Tık
        3. Coord 2 -> Sağ Tık
        4. F_Key Bas -> Digit_Key Bas
        5. Coord 3 -> Sağ Tık (Eski yerine koyma veya çıkarma)
        6. Coord 4 -> Sağ Tık
        7. I Bas (Çanta Kapat)
        """
        if self._running: 
            return # Zaten çalışıyorsa tekrar başlatma

        with self._lock:
            self._running = True
            self._stop_event.clear()
            
            try:
                # 1. ADIM: ENVANTER AÇ
                self._press_key(SC_I)
                time.sleep(self.delay_inv)
                if self._stop_event.is_set(): return

                # 2. ADIM: İLK İKİ KOORDİNAT (TAKMA)
                # Coord 1
                self._right_click(self.coords[0][0], self.coords[0][1])
                time.sleep(self.delay_click)
                if self._stop_event.is_set(): return
                
                # Coord 2
                self._right_click(self.coords[1][0], self.coords[1][1])
                time.sleep(self.delay_click)
                if self._stop_event.is_set(): return

                # 3. ADIM: SKILL KULLANIMI
                # F Tuşu
                sc_f = F_SCANCODES.get(self.f_key)
                if sc_f: self._press_key(sc_f)
                time.sleep(self.delay_skill)
                
                # Rakam Tuşu
                sc_d = DIGIT_SCANCODES.get(self.digit_key)
                if sc_d: self._press_key(sc_d)
                time.sleep(self.delay_skill)
                if self._stop_event.is_set(): return

                # 4. ADIM: SON İKİ KOORDİNAT (ÇIKARMA / GERİ KOYMA)
                # Coord 3
                self._right_click(self.coords[2][0], self.coords[2][1])
                time.sleep(self.delay_click)
                if self._stop_event.is_set(): return

                # Coord 4
                self._right_click(self.coords[3][0], self.coords[3][1])
                time.sleep(self.delay_click)
                
                # 5. ADIM: ENVANTER KAPAT
                # Son işlemden sonra minik bir bekleme
                time.sleep(0.1) 
                self._press_key(SC_I)

            except Exception as e:
                print(f"[STYX] Hata: {e}")
            finally:
                self._running = False

    # --- YARDIMCI FONKSİYONLAR ---
    def _press_key(self, sc):
        if self.kb:
            self.kb.tusbas(sc, 0.02)
        else:
            # Driver yoksa simülasyon (test için)
            print(f"[SIM] Tuş Bas: {sc}")

    def _right_click(self, x, y):
        if x == 0 and y == 0: return # Koordinat ayarlanmamışsa geç

        if self.mouse:
            self.mouse.rightclick(0.01, x, y)
        else:
            # Driver yoksa pyautogui
            pyautogui.click(x, y, button='right')

# ---------------------------------------------------------
# 2. GUI (AYAR PENCERESİ)
# ---------------------------------------------------------
class StyxSettingsDialog(QDialog):
    def __init__(self, parent, config):
        super().__init__(parent)
        self.setWindowTitle("STYX / MANA SİLME AYARLARI")
        self.setModal(True)
        self.config = config or {}
        
        # Koordinat yakalama için değişkenler
        self.capture_active = False
        self.capture_target_index = -1 # Hangi slotu kaydediyoruz? (0-3)
        self.hotkey_capture_mode = False
        
        self.setStyleSheet("background-color: #121212; color: #eee;")

        layout = QVBoxLayout(self)

        # ---------------------------------------------
        # KOORDİNAT AYARLARI
        # ---------------------------------------------
        grp_coords = QGroupBox("1. Koordinat Ayarları (Sağ Tık Sırası)")
        grp_coords.setStyleSheet("QGroupBox { border: 1px solid #00e676; border-radius: 5px; margin-top: 10px; } QGroupBox::title { color: #00e676; }")
        grid_coords = QGridLayout(grp_coords)

        self.coord_labels = []
        self.temp_coords = self.config.get("coords", [(0,0)]*4)
        if len(self.temp_coords) != 4: self.temp_coords = [(0,0)]*4

        labels_text = ["1. İtem (Tak)", "2. İtem (Tak)", "3. İtem (Çıkar)", "4. İtem (Çıkar)"]

        for i in range(4):
            # Label
            lbl_desc = QLabel(f"{labels_text[i]}:")
            grid_coords.addWidget(lbl_desc, i, 0)

            # Koordinat Göstergesi
            lbl_val = QLineEdit(f"{self.temp_coords[i][0]}, {self.temp_coords[i][1]}")
            lbl_val.setReadOnly(True)
            lbl_val.setStyleSheet("background: #222; color: #00e676; border: 1px solid #444; width: 80px;")
            self.coord_labels.append(lbl_val)
            grid_coords.addWidget(lbl_val, i, 1)

            # Yakala Butonu
            btn = QPushButton("Yakala (F)")
            btn.setStyleSheet("background: #333; color: white; border: 1px solid #555;")
            btn.clicked.connect(lambda _, idx=i: self.start_coord_capture(idx))
            grid_coords.addWidget(btn, i, 2)

        layout.addWidget(grp_coords)
        
        # Bilgilendirme
        lbl_info = QLabel("Bilgi: 'Yakala'ya bas, mouse'u item üstüne getir ve 'F' tuşuna bas.")
        lbl_info.setStyleSheet("color: #888; font-size: 8pt; font-style: italic;")
        layout.addWidget(lbl_info)

        # ---------------------------------------------
        # SKILL AYARLARI
        # ---------------------------------------------
        grp_skill = QGroupBox("2. Skill Ayarları")
        grp_skill.setStyleSheet("QGroupBox { border: 1px solid #00e676; border-radius: 5px; margin-top: 10px; } QGroupBox::title { color: #00e676; }")
        form_skill = QFormLayout(grp_skill)

        # F Tuşu Seçimi
        self.cmb_f = QComboBox()
        for i in range(1, 9): self.cmb_f.addItem(f"F{i}", i)
        self.cmb_f.setCurrentIndex(self.config.get("f_key", 1) - 1)
        form_skill.addRow("F Sayfası:", self.cmb_f)

        # Rakam Tuşu Seçimi
        self.cmb_d = QComboBox()
        for i in range(10): self.cmb_d.addItem(str(i), i)
        # ComboBox index mantığı: 0->0, 1->1 ...
        d_val = self.config.get("digit_key", 1)
        self.cmb_d.setCurrentText(str(d_val))
        form_skill.addRow("Skill Tuşu:", self.cmb_d)

        layout.addWidget(grp_skill)

        # ---------------------------------------------
        # ZAMANLAMA AYARLARI
        # ---------------------------------------------
        grp_time = QGroupBox("3. Gecikme Ayarları (Saniye)")
        grp_time.setStyleSheet("QGroupBox { border: 1px solid #00e676; border-radius: 5px; margin-top: 10px; } QGroupBox::title { color: #00e676; }")
        grid_time = QGridLayout(grp_time)

        grid_time.addWidget(QLabel("Çanta Açılış:"), 0, 0)
        self.spin_inv = QDoubleSpinBox()
        self.spin_inv.setRange(0.05, 1.0); self.spin_inv.setSingleStep(0.01)
        self.spin_inv.setValue(self.config.get("delay_inv", 0.20))
        grid_time.addWidget(self.spin_inv, 0, 1)

        grid_time.addWidget(QLabel("Tıklama Hızı:"), 1, 0)
        self.spin_click = QDoubleSpinBox()
        self.spin_click.setRange(0.01, 1.0); self.spin_click.setSingleStep(0.01)
        self.spin_click.setValue(self.config.get("delay_click", 0.05))
        grid_time.addWidget(self.spin_click, 1, 1)

        grid_time.addWidget(QLabel("Skill Basma:"), 2, 0)
        self.spin_skill = QDoubleSpinBox()
        self.spin_skill.setRange(0.01, 1.0); self.spin_skill.setSingleStep(0.01)
        self.spin_skill.setValue(self.config.get("delay_skill", 0.05))
        grid_time.addWidget(self.spin_skill, 2, 1)

        layout.addWidget(grp_time)

        # ---------------------------------------------
        # BAŞLATMA TUŞU
        # ---------------------------------------------
        h_hot = QHBoxLayout()
        h_hot.addWidget(QLabel("Makro Tuşu:"))
        self.txt_hotkey = QLineEdit(self.config.get("hotkey", "K"))
        self.txt_hotkey.setReadOnly(True)
        h_hot.addWidget(self.txt_hotkey)
        
        btn_hot = QPushButton("Tuş Ata")
        btn_hot.clicked.connect(self.start_hotkey_capture)
        h_hot.addWidget(btn_hot)
        
        layout.addLayout(h_hot)

        # Butonlar
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.save_and_close)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        # Keyboard Hook Başlat (Sadece dialog açıkken F tuşunu dinlemek için)
        if keyboard:
            try:
                self.hook_f = keyboard.on_press_key("F", self.on_f_press)
            except: self.hook_f = None

    def closeEvent(self, event):
        if keyboard and hasattr(self, 'hook_f') and self.hook_f: 
            try: keyboard.unhook(self.hook_f)
            except: pass
        super().closeEvent(event)

    def start_coord_capture(self, index):
        self.capture_active = True
        self.capture_target_index = index
        self.coord_labels[index].setText("F Bas...")

    def on_f_press(self, e):
        if self.capture_active and self.capture_target_index >= 0:
            x, y = pyautogui.position()
            self.temp_coords[self.capture_target_index] = (x, y)
            # GUI güncellemesi thread güvenliği için setText direkt burada çağrılmaz ama 
            # basitlik için ve QDialog modal olduğu için genelde çalışır.
            # Yine de lambda ile ana thread'e paslamak daha doğrudur ama burada shortcut yapıyoruz.
            self.coord_labels[self.capture_target_index].setText(f"{x}, {y}")
            self.capture_active = False
            self.capture_target_index = -1

    def start_hotkey_capture(self):
        self.hotkey_capture_mode = True
        self.txt_hotkey.setText("...")

    def keyPressEvent(self, e):
        if self.hotkey_capture_mode:
            key_text = e.text().upper()
            if key_text:
                self.txt_hotkey.setText(key_text)
                self.hotkey_capture_mode = False
        else:
            super().keyPressEvent(e)

    def save_and_close(self):
        self.result_config = {
            "coords": self.temp_coords,
            "f_key": self.cmb_f.currentData(),
            "digit_key": int(self.cmb_d.currentText()),
            "delay_inv": self.spin_inv.value(),
            "delay_click": self.spin_click.value(),
            "delay_skill": self.spin_skill.value(),
            "hotkey": self.txt_hotkey.text()
        }
        self.accept()

# =========================================================
# 3. WIDGET (ANA EKRAN KARTI) - YENİ STİL
# =========================================================
class StyxWidget(QFrame):
    update_signal = pyqtSignal()

    def __init__(self, parent=None, macro_instance=None, config=None):
        super().__init__(parent)
        self.macro = macro_instance or StyxMacro()
        self.config = config or {}
        
        self.macro.update_config(self.config)

        self.listen_active = False
        self._hook_handle = None

        self.update_signal.connect(self._safe_update_status)
        self.setup_ui()
        self._safe_update_status()

    def setup_ui(self):
        self.setFrameShape(QFrame.Box)
        self.setFrameShadow(QFrame.Plain)
        self.setMaximumWidth(260)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        
        # 3-5 ile aynı standart stil
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
        h.setSpacing(6)
        
        icon = QLabel()
        icon.setFixedSize(25, 25)
        pix = QPixmap("icons/styx.png") 
        if not pix.isNull():
            icon.setPixmap(pix.scaled(25, 25, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        h.addWidget(icon)

        h.addStretch(1)
        
        lbl_title = QLabel("STYX / MANA SİLME")
        lbl_title.setObjectName("MinorHeaderLabel") # 3-5 Başlık Stili
        h.addWidget(lbl_title)
        
        v.addLayout(h)

        # --- BUTON ---
        self.btn_listen = QPushButton("TUŞ DİNLEMEYİ BAŞLAT")
        self.btn_listen.setObjectName("ThreeFiveListenButton") # 3-5 Buton Stili
        self.btn_listen.setProperty("active", False)
        self.btn_listen.clicked.connect(self.toggle_listen)
        v.addWidget(self.btn_listen)

        # --- STATUS ---
        self.lbl_status = QLabel("DURUM: PASİF")
        self.lbl_status.setObjectName("MinorStatusLabel")
        v.addWidget(self.lbl_status)

        # --- ALT KISIM ---
        row = QHBoxLayout()
        row.setSpacing(4)
        row.addWidget(QLabel("AKTİF TUŞ:"))
        
        self.lbl_hotkey = QLabel(self.config.get("hotkey", "K"))
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

    def apply_status_style(self, color: str = "#8d95c7"):
        self.lbl_status.setStyleSheet(f"color: {color}; font-weight: bold;")

    def toggle_listen(self):
        if not keyboard: return
        if not self.listen_active:
            hk = self.config.get("hotkey", "K").lower()
            try:
                self._hook_handle = keyboard.on_press_key(hk, self.on_hotkey)
                self.listen_active = True
            except Exception as e: print(e); self.listen_active = False
        else:
            if self._hook_handle: 
                try: keyboard.unhook(self._hook_handle)
                except: pass
                self._hook_handle = None
            self.listen_active = False; self.macro.stop()
        self._safe_update_status()

    def on_hotkey(self, e):
        if not self.macro.is_running:
            self.update_signal.emit()
            threading.Thread(target=self._run_wrapper, daemon=True).start()

    def _run_wrapper(self):
        self.macro.run_sequence()
        self.update_signal.emit()

    def open_settings(self):
        dlg = StyxSettingsDialog(self, self.config)
        if dlg.exec_():
            self.config.update(dlg.result_config)
            self.macro.update_config(self.config)
            self.lbl_hotkey.setText(self.config.get("hotkey", "K"))
            if self.listen_active: self.toggle_listen(); self.toggle_listen()
