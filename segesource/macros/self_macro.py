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

# --- self.py ---

import threading
import time
import json
import os

# PyQt5
from PyQt5.QtWidgets import (
    QDialog, QGridLayout, QLabel, QComboBox, 
    QLineEdit, QPushButton, QDoubleSpinBox, 
    QDialogButtonBox, QHBoxLayout, QWidget,
    QFrame, QVBoxLayout, QSizePolicy, QMessageBox,
    QCheckBox, QScrollArea, QGroupBox
)
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtCore import Qt, QSize, pyqtSignal, QTimer

# Harici Kütüphaneler
try:
    import keyboard
except ImportError:
    keyboard = None

# Sürücüler
try:
    from clicksend import KeyboardDriver as _ClicksendKeyboardDriver
except ImportError:
    _ClicksendKeyboardDriver = None

# ---------------------------------------------------------
# SABİTLER VE SCANCODE
# ---------------------------------------------------------
# Basit tuş haritası (Genişletilebilir)
KEY_MAP = {
    "1": 0x02, "2": 0x03, "3": 0x04, "4": 0x05, "5": 0x06,
    "6": 0x07, "7": 0x08, "8": 0x09, "9": 0x0A, "0": 0x0B,
    "F1": 0x3B, "F2": 0x3C, "F3": 0x3D, "F4": 0x3E,
    "F5": 0x3F, "F6": 0x40, "F7": 0x41, "F8": 0x42,
    "Z": 0x2C, "W": 0x11, "S": 0x1F, "R": 0x13
}

def _get_scancode(key_str):
    return KEY_MAP.get(key_str.upper(), None)

# ---------------------------------------------------------
# 1. LOGIC (MAKRO MOTORU)
# ---------------------------------------------------------
class SelfMacro:
    def __init__(self):
        self._driver = _ClicksendKeyboardDriver() if _ClicksendKeyboardDriver else None
        
        self.entries = [] # [{"key": "1", "delay": 1.0, "enabled": True}, ...]
        self.sequential = True # Sıralı mı Paralel mi?
        
        self._running = False
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    def update_config(self, cfg):
        with self._lock:
            # Config'den gelen ham veriyi işlenebilir hale getir
            self.sequential = cfg.get("sequential", True)
            raw_entries = cfg.get("entries", [])
            
            self.entries = []
            for item in raw_entries:
                if not item.get("enabled", False): continue
                
                # Süreyi saniyeye çevir
                val = float(item.get("delay", 0.1))
                unit = item.get("unit", "sn")
                if unit == "ms": val /= 1000.0
                elif unit == "dk": val *= 60.0
                
                # Tuş Scancode
                key_str = item.get("key", "")
                sc = _get_scancode(key_str)
                
                self.entries.append({
                    "key_str": key_str,
                    "scancode": sc,
                    "delay": max(0.01, val),
                    "last_cast": 0
                })

    @property
    def is_running(self): return self._running

    def toggle(self):
        if self._running: self.stop()
        else: self.start()

    def start(self):
        if not self._running:
            self._stop_event.clear()
            self._running = True
            threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._stop_event.set()
        self._running = False

    def _loop(self):
        print(f"[SELF] Başladı. Mod: {'Sıralı' if self.sequential else 'Paralel'}")
        
        # Reset last_cast
        for e in self.entries: e["last_cast"] = 0
        
        while not self._stop_event.is_set():
            if not self.entries:
                time.sleep(1)
                continue

            try:
                if self.sequential:
                    # --- SIRALI MOD ---
                    for entry in self.entries:
                        if self._stop_event.is_set(): break
                        self._press(entry)
                        time.sleep(entry["delay"])
                else:
                    # --- PARALEL MOD (Zaman Damgası ile) ---
                    now = time.time()
                    action_taken = False
                    
                    for entry in self.entries:
                        if self._stop_event.is_set(): break
                        
                        if (now - entry["last_cast"]) >= entry["delay"]:
                            self._press(entry)
                            entry["last_cast"] = now
                            action_taken = True
                    
                    # İşlem yapılmadıysa CPU'yu yormamak için kısa bekleme
                    if not action_taken:
                        time.sleep(0.01)
                        
            except Exception as e:
                print(f"[SELF] Hata: {e}")
                time.sleep(1)

    def _press(self, entry):
        sc = entry["scancode"]
        if self._driver and sc:
            self._driver.tusbas(sc, 0.02)
        else:
            # Driver yoksa print (veya keyboard.press eklenebilir)
            # print(f"[SELF] Basıldı: {entry['key_str']}")
            pass

# ---------------------------------------------------------
# 2. GUI (AYAR PENCERESİ)
# ---------------------------------------------------------
class SelfSettingsDialog(QDialog):
    def __init__(self, parent, config, macro):
        super().__init__(parent)
        self.setWindowTitle("ÖZEL MAKRO AYARLARI")
        self.setModal(True)
        self.resize(550, 600)
        
        self.config = config
        self.macro = macro
        self.capture_hotkey = False
        
        # Ana Layout
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(15, 15, 15, 15)

        # --- ÜST KISIM (Tuş ve Mod) ---
        top_group = QGroupBox("Genel Ayarlar")
        top_layout = QGridLayout(top_group)
        
        top_layout.addWidget(QLabel("BAŞLAT TUŞU:"), 0, 0)
        self.txt_hotkey = QLineEdit(self.config.get("hotkey", "F"))
        self.txt_hotkey.setReadOnly(True)
        btn_hotkey = QPushButton("SEÇ")
        btn_hotkey.clicked.connect(self.on_hotkey_capture)
        
        hb = QHBoxLayout()
        hb.addWidget(self.txt_hotkey)
        hb.addWidget(btn_hotkey)
        top_layout.addLayout(hb, 0, 1)

        self.chk_seq = QCheckBox("Sıralı Mod (İşaretli=Sırayla, İşaretsiz=Aynı Anda)")
        self.chk_seq.setChecked(self.config.get("sequential", True))
        self.chk_seq.setStyleSheet("color: #00e676; font-weight: bold;")
        top_layout.addWidget(self.chk_seq, 1, 0, 1, 2)
        
        layout.addWidget(top_group)

        # --- ORTA KISIM (Liste) ---
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background-color: #151515; border: 1px solid #333;")
        
        list_widget = QWidget()
        self.list_layout = QVBoxLayout(list_widget)
        self.list_layout.setSpacing(5)
        
        # 13 Satır Oluştur
        self.ui_rows = []
        entries_data = self.config.get("entries", [])
        
        # Mevcut veriyi 13'e tamamla
        while len(entries_data) < 13:
            entries_data.append({"enabled": False, "key": "1", "delay": 1.0, "unit": "ms"})

        for i in range(13):
            data = entries_data[i]
            row_wid = QWidget()
            rl = QHBoxLayout(row_wid)
            rl.setContentsMargins(0,0,0,0)
            
            # 1. Checkbox
            chk = QCheckBox(f"Slot {i+1}")
            chk.setChecked(data.get("enabled", False))
            chk.setFixedWidth(70)
            
            # 2. Key Combo
            cmb_key = QComboBox()
            keys = ["1","2","3","4","5","6","7","8","9","0","F1","F2","F3","F4","F5","F6","F7","F8","Z","W","R","S"]
            cmb_key.addItems(keys)
            cmb_key.setCurrentText(data.get("key", "1"))
            
            # 3. Delay
            spin_delay = QDoubleSpinBox()
            spin_delay.setRange(0.01, 9999)
            spin_delay.setValue(float(data.get("delay", 1.0)))
            
            # 4. Unit
            cmb_unit = QComboBox()
            cmb_unit.addItems(["ms", "sn", "dk"])
            cmb_unit.setCurrentText(data.get("unit", "sn"))
            
            rl.addWidget(chk)
            rl.addWidget(cmb_key)
            rl.addWidget(spin_delay)
            rl.addWidget(cmb_unit)
            
            self.list_layout.addWidget(row_wid)
            self.ui_rows.append((chk, cmb_key, spin_delay, cmb_unit))
            
        self.list_layout.addStretch()
        scroll.setWidget(list_widget)
        layout.addWidget(scroll)

        # --- ALT KISIM (Butonlar) ---
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def on_hotkey_capture(self):
        self.capture_hotkey = True
        self.txt_hotkey.setText("...")

    def keyPressEvent(self, event):
        if self.capture_hotkey:
            name = event.text().upper()
            if event.key() >= Qt.Key_F1 and event.key() <= Qt.Key_F12:
                name = f"F{event.key() - Qt.Key_F1 + 1}"
            
            if name:
                self.txt_hotkey.setText(name)
                self.capture_hotkey = False
            return
        super().keyPressEvent(event)

    def accept(self):
        # Ayarları topla
        new_entries = []
        for chk, cmb_k, spin, cmb_u in self.ui_rows:
            new_entries.append({
                "enabled": chk.isChecked(),
                "key": cmb_k.currentText(),
                "delay": spin.value(),
                "unit": cmb_u.currentText()
            })
            
        self.config["hotkey"] = self.txt_hotkey.text()
        self.config["sequential"] = self.chk_seq.isChecked()
        self.config["entries"] = new_entries
        
        self.macro.update_config(self.config)
        super().accept()

# ---------------------------------------------------------
# 3. WIDGET (ANA EKRAN KARTI)
# ---------------------------------------------------------
# --- self.py --- (Sadece bu sınıfı değiştirmen yeterli)

# ---------------------------------------------------------
# 3. WIDGET (ANA EKRAN KARTI - GÜNCELLENMİŞ)
# ---------------------------------------------------------
class SelfWidget(QFrame):
    update_signal = pyqtSignal()

    def __init__(self, parent=None, macro_instance=None, config=None):
        super().__init__(parent)
        self.macro = macro_instance or SelfMacro()
        self.config = config or {}
        
        # Makroyu başlatırken ayarları yükle
        self.macro.update_config(self.config)
        
        self.listen_active = False
        self._hook = None
        
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

        # --- HEADER (Standart Stil) ---
        h = QHBoxLayout()
        h.setSpacing(6)
        
        # İkon (keyboard.png yoksa text gösterir)
        icon = QLabel()

             # İkon yoksa emoji fallback
        icon.setText("🧠")
        icon.setStyleSheet(" font-size: 25px;")
             
        h.addWidget(icon)

        # Başlık
        # Buradaki isim modules.py'den gelmez, widget içinden verilir.
        # Genel bir isim veriyoruz.
        lbl_title = QLabel("ÖZEL MAKRO PANELİ") 
        lbl_title.setObjectName("MinorHeaderLabel") # CSS uyumu
        h.addStretch(1)
        h.addWidget(lbl_title)
        
        v.addLayout(h)

        # --- BUTON (Standart Stil) ---
        self.btn_listen = QPushButton("TUŞ DİNLEMEYİ BAŞLAT")
        self.btn_listen.setObjectName("ThreeFiveListenButton") # CSS uyumu
        self.btn_listen.setProperty("active", False)
        self.btn_listen.clicked.connect(self.toggle_listen)
        v.addWidget(self.btn_listen)

        # --- DURUM ---
        self.lbl_status = QLabel("DURUM: PASİF")
        self.lbl_status.setObjectName("MinorStatusLabel") # CSS uyumu
        v.addWidget(self.lbl_status)

        # --- ALT KISIM ---
        row = QHBoxLayout()
        row.setSpacing(4)
        row.addWidget(QLabel("AKTİF TUŞ:"))
        
        self.lbl_key = QLabel(self.config.get("hotkey", "F6"))
        self.lbl_key.setObjectName("HotkeyLabel") # CSS uyumu
        self.lbl_key.setAlignment(Qt.AlignCenter)
        row.addWidget(self.lbl_key)
        
        btn_set = QPushButton("⚙ AYARLAR")
        btn_set.setObjectName("MinorSettingsButton") # CSS uyumu
        btn_set.setFlat(True)
        btn_set.setIcon(QIcon("icons/gear.png"))
        btn_set.setIconSize(QSize(12, 12))
        btn_set.clicked.connect(self.open_settings)
        row.addWidget(btn_set)
        
        v.addLayout(row)

    def open_settings(self):
        d = SelfSettingsDialog(self, self.config, self.macro)
        if d.exec_():
            self.lbl_key.setText(self.config["hotkey"])
            # Ayarlar değiştiğinde makroyu güncelle
            self.macro.update_config(self.config)
            
            if self.listen_active: 
                self.toggle_listen() # Kapat
                self.toggle_listen() # Aç

    def toggle_listen(self):
        if not keyboard: return
        if not self.listen_active:
            k = self.config.get("hotkey", "F6").lower()
            try:
                self._hook = keyboard.on_press_key(k, lambda e: self.macro.toggle())
                self.listen_active = True
            except: pass
        else:
            if self._hook: 
                try: keyboard.unhook(self._hook)
                except: pass
            self.listen_active = False
            self.macro.stop()
        self._safe_update_status()

    def apply_status_style(self, color: str = "#8d95c7"):
        self.lbl_status.setStyleSheet(f"color: {color}; font-weight: bold;")

    def _safe_update_status(self):
        if not self.listen_active:
            self.lbl_status.setText("DURUM: PASİF")
            self.apply_status_style("#ff5555") # KIRMIZI
            self.btn_listen.setText("TUŞ DİNLEMEYİ BAŞLAT")
            is_active = False
        else:
            if self.macro.is_running:
                self.lbl_status.setText("DURUM: ÇALIŞIYOR")
                self.apply_status_style("#00ff4c") # YEŞİL
            else:
                self.lbl_status.setText("DURUM: BEKLİYOR")
                self.apply_status_style("#ffff55") # SARI
            
            self.btn_listen.setText("TUŞ DİNLEMEYİ DURDUR")
            is_active = True
        
        # Buton stilini güncelle (CSS için property değişimi)
        self.btn_listen.setProperty("active", is_active)
        self.btn_listen.style().unpolish(self.btn_listen)
        self.btn_listen.style().polish(self.btn_listen)
        
        # Döngüsel kontrol
        if self.listen_active:
             QTimer.singleShot(500, self._safe_update_status)
