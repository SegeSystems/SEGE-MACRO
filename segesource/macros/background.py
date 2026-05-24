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
import win32gui
import win32api
import win32con
import os
import json
import keyboard
from PyQt5.QtWidgets import (
    QDialog, QGridLayout, QLabel, QComboBox, 
    QLineEdit, QPushButton, QDoubleSpinBox, 
    QDialogButtonBox, QHBoxLayout, QWidget,
    QFrame, QVBoxLayout, QSizePolicy, QMessageBox,
    QScrollArea, QCheckBox, QGroupBox, QListWidget, QAbstractItemView, QListWidgetItem
)
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtCore import Qt, pyqtSignal, QTimer

# Detaylı Tuş Haritası
KEY_MAP = {
    "1": 0x02, "2": 0x03, "3": 0x04, "4": 0x05, "5": 0x06, "6": 0x07, "7": 0x08, "8": 0x09, "9": 0x0A, "0": 0x0B,
    "A": 0x1E, "B": 0x30, "C": 0x2E, "D": 0x20, "E": 0x12, "F": 0x21, "G": 0x22, "H": 0x23, "I": 0x17, "J": 0x24,
    "K": 0x25, "L": 0x26, "M": 0x32, "N": 0x31, "O": 0x18, "P": 0x19, "Q": 0x10, "R": 0x13, "S": 0x1F, "T": 0x14,
    "U": 0x16, "V": 0x2F, "W": 0x11, "X": 0x2D, "Y": 0x15, "Z": 0x2C,
    "F1": 0x3B, "F2": 0x3C, "F3": 0x3D, "F4": 0x3E, "F5": 0x3F, "F6": 0x40, "F7": 0x41, "F8": 0x42,
}

def make_lparam(scancode, is_down):
    lparam = 1 
    lparam |= (scancode << 16)
    if not is_down:
        lparam |= (1 << 30) | (1 << 31)
    return lparam

# =========================================================
# 1. LOGIC (ARKA PLAN MOTORU)
# =========================================================
class BackgroundBotV2Macro:
    def __init__(self):
        self.target_hwnds = []
        self.entries = [] 
        self._running = False
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self.hotkey = "INSERT" # Varsayılan


    def update_config(self, cfg):
        with self._lock:
            self.hotkey = cfg.get("hotkey", "INSERT") # Hotkey'i ayardan oku
            self.target_hwnds = cfg.get("target_hwnds", [])
            raw_entries = cfg.get("entries", [])
            self.entries = []
            for item in raw_entries:
                if not item.get("enabled"): continue
                sc = KEY_MAP.get(item.get("key", "").upper())
                if sc:
                    val = float(item.get("delay", 0.5))
                    unit = item.get("unit", "ms")
                    if unit == "ms": val /= 1000.0
                    elif unit == "dk": val *= 60.0
                    
                    self.entries.append({
                        "scancode": sc,
                        "delay": max(0.01, val),
                        "last_cast": 0
                    })
        pass

    @property
    def is_running(self): return self._running



    def start(self):
        if not self._running:
            self._stop_event.clear()
            self._running = True
            threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._stop_event.set()
        self._running = False

    def toggle(self):
        """Makro çalışıyorsa durdurur, duruyorsa başlatır"""
        if self._running:
            self.stop()
        else:
            self.start()

    def _loop(self):
        while not self._stop_event.is_set():
            if not self.entries or not self.target_hwnds:
                time.sleep(0.5); continue

            now = time.time()
            for entry in self.entries:
                if self._stop_event.is_set(): break
                
                if (now - entry["last_cast"]) >= entry["delay"]:
                    sc = entry["scancode"]
                    vk = win32api.MapVirtualKey(sc, 1)
                    
                    for hwnd in self.target_hwnds:
                        if win32gui.IsWindow(hwnd):
                            # Arka Plan Mesajları (PostMessage pencere alttayken çalışır)
                            win32api.PostMessage(hwnd, win32con.WM_ACTIVATE, win32con.WA_ACTIVE, 0)
                            win32api.PostMessage(hwnd, win32con.WM_KEYDOWN, vk, make_lparam(sc, True))
                            time.sleep(0.01)
                            win32api.PostMessage(hwnd, win32con.WM_KEYUP, vk, make_lparam(sc, False))
                    
                    entry["last_cast"] = now
            time.sleep(0.005)
        pass

# =========================================================
# 2. GUI (AYARLAR)
# =========================================================
class BackgroundBotV2SettingsDialog(QDialog):
    def __init__(self, parent, config, macro):
        super().__init__(parent)
        self.setWindowTitle("ARKA PLAN BOT AYARLARI")
        self.resize(500, 750)
        self.config = config
        self.macro = macro
        self.capture_mode = False
        self.setStyleSheet("background-color: #161616; color: white;")
        layout = QVBoxLayout(self)

        # --- 1. HOTKEY ATAMA (STANDART YEŞİL) ---
        grp_hk = QGroupBox("1. Başlatma Tuşu")
        grp_hk.setStyleSheet("color: #00e676; font-weight: bold;") # SARI -> YEŞİL
        hk_lay = QHBoxLayout(grp_hk)
        self.txt_hk = QLineEdit(self.config.get("hotkey", "INSERT"))
        self.txt_hk.setReadOnly(True)
        self.txt_hk.setStyleSheet("background: #000; color: #00e676; font-family: Consolas; font-weight: bold; border: 1px solid #333;")
        
        btn_cap = QPushButton("TUŞ SEÇ")
        btn_cap.setStyleSheet("background: #252525; color: #00e676; border: 1px solid #00e676; font-weight: bold;")
        btn_cap.clicked.connect(self.start_hk_cap)
        
        hk_lay.addWidget(QLabel("Aktif Tuş:")); hk_lay.addWidget(self.txt_hk); hk_lay.addWidget(btn_cap)
        layout.addWidget(grp_hk)

# --- 2. PENCERE SEÇİMİ (Kaydırma Sorunu Giderilmiş Hali) ---
        grp_win = QGroupBox("2. Hedef Karakterleri Seç")
        grp_win.setStyleSheet("color: #00e676; font-weight: bold;")
        win_lay = QVBoxLayout(grp_win)
        
        self.win_scroll = QScrollArea()
        self.win_scroll.setWidgetResizable(True) # İçerik arttıkça alanı genişletir
        self.win_scroll.setMinimumHeight(200)    # En az 200px yükseklik
        self.win_scroll.setStyleSheet("background: #000; border: 1px solid #333;")
        
        self.win_container = QWidget()
        self.win_list_lay = QVBoxLayout(self.win_container)
        self.win_list_lay.setAlignment(Qt.AlignTop) # İsimleri yukarı yaslar, boşluk bırakmaz
        self.win_scroll.setWidget(self.win_container)
        
        self.window_checks = []
        win_lay.addWidget(self.win_scroll)
        
        btn_ref = QPushButton("Pencereleri Tara / Yenile")
        btn_ref.clicked.connect(self.refresh_windows)
        win_lay.addWidget(btn_ref)
        layout.addWidget(grp_win)

        # --- 3. SLOTLAR (SOLA HİZALI & 1MS DEFAULT) ---
        grp_slots = QGroupBox("3. Makro Slotları ve Gecikmeler")
        grp_slots.setStyleSheet("color: #00e676; font-weight: bold;")
        slot_main_lay = QVBoxLayout(grp_slots)
        
        self.rows = []
        entries = self.config.get("entries", [])
        while len(entries) < 10: # 10 Slot
            entries.append({"enabled": False, "key": "1", "delay": 1, "unit": "ms"}) # 500 -> 1ms

        for i in range(10):
            row_w = QWidget()
            row = QHBoxLayout(row_w)
            row.setContentsMargins(0, 2, 0, 2)
            row.setSpacing(10)
            row.setAlignment(Qt.AlignLeft) # SOLA HİZALAMA
            
            chk = QCheckBox(f"#{i+1}"); chk.setChecked(entries[i].get("enabled"))
            chk.setStyleSheet("QCheckBox { color: #00e676; font-weight: bold; }")
            
            cmb_k = QComboBox(); cmb_k.addItems(list(KEY_MAP.keys())); cmb_k.setCurrentText(entries[i].get("key"))
            cmb_k.setFixedWidth(65); cmb_k.setStyleSheet("background: #000; color: #00e676; border: 1px solid #333;")
            
            sp_d = QDoubleSpinBox(); sp_d.setRange(0, 99999); sp_d.setValue(entries[i].get("delay"))
            sp_d.setFixedWidth(80); sp_d.setStyleSheet("background: #000; color: #00e676; border: 1px solid #333;")
            
            cmb_u = QComboBox(); cmb_u.addItems(["ms", "sn", "dk"]); cmb_u.setCurrentText(entries[i].get("unit"))
            cmb_u.setFixedWidth(55); cmb_u.setStyleSheet("background: #000; color: #00e676; border: 1px solid #333;")
            
            row.addWidget(chk); row.addWidget(cmb_k); row.addWidget(sp_d); row.addWidget(cmb_u)
            slot_main_lay.addWidget(row_w)
            self.rows.append((chk, cmb_k, sp_d, cmb_u))
            
        layout.addWidget(grp_slots)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.setStyleSheet("QPushButton { background: #252525; color: white; }")
        btns.accepted.connect(self.save_data); btns.rejected.connect(self.reject)
        layout.addWidget(btns)
        self.refresh_windows()

    # CAPS LOCK ve DİĞER ÖZEL TUŞLAR İÇİN DÜZELTME
    def keyPressEvent(self, e):
        if self.capture_mode:
            key = e.key()
            name = None
            if key == Qt.Key_CapsLock: name = "CAPS LOCK"
            elif key == Qt.Key_Insert: name = "INSERT"
            elif key == Qt.Key_Delete: name = "DELETE"
            elif key == Qt.Key_Home: name = "HOME"
            elif key == Qt.Key_End: name = "END"
            elif key == Qt.Key_PageUp: name = "PAGE UP"
            elif key == Qt.Key_PageDown: name = "PAGE DOWN"
            elif key == Qt.Key_Control: name = "CTRL"
            elif key == Qt.Key_Shift: name = "SHIFT"
            elif key == Qt.Key_Alt: name = "ALT"
            elif Qt.Key_F1 <= key <= Qt.Key_F12: name = f"F{key - Qt.Key_F1 + 1}"
            else:
                text = e.text().upper()
                if text: name = text

            if name:
                self.txt_hk.setText(name)
                self.capture_mode = False
                self.releaseKeyboard()
        else: super().keyPressEvent(e)

    def start_hk_cap(self):
        self.capture_mode = True
        self.txt_hk.setText("...")
        self.grabKeyboard()

    def refresh_windows(self):
        # 1. Layout içindeki her şeyi tamamen temizle (Spacers dahil)
        while self.win_list_lay.count():
            item = self.win_list_lay.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        self.window_checks = []
        
        # Filtre kelimeleri
        target_keys = ["knight", "client", "rexe", "soacs", "online"]

        def enum_cb(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                class_name = win32gui.GetClassName(hwnd)
                
                is_target = any(k in title.lower() for k in target_keys) or \
                            any(k in class_name.lower() for k in target_keys)

                if is_target:
                    display_text = title if title.strip() else f"Adsız Oyun Penceresi ({class_name})"
                    
                    cb = QCheckBox(f"[{hwnd}] {display_text}")
                    cb.setProperty("hwnd", hwnd)
                    cb.setMinimumHeight(30) # Her satıra standart yükseklik ver (Scroll için önemli)
                    cb.setStyleSheet("""
                        QCheckBox { color: white; padding: 5px; border-bottom: 1px solid #111; } 
                        QCheckBox:checked { color: #00e676; font-weight: bold; }
                        QCheckBox:hover { background: #222; }
                    """)
                    
                    if hwnd in self.config.get("target_hwnds", []):
                        cb.setChecked(True)
                    
                    self.win_list_lay.addWidget(cb)
                    self.window_checks.append(cb)

        # Windows pencerelerini tara
        win32gui.EnumWindows(enum_cb, None)
        
        # Eğer hiç pencere bulunamazsa uyarı yazısı ekle
        if not self.window_checks:
            lbl = QLabel("Uygun pencere bulunamadı.")
            lbl.setStyleSheet("color: gray; padding: 10px;")
            self.win_list_lay.addWidget(lbl)
        
        # 2. Sadece bir kez en alta boşluk ekle (Tüm isimleri yukarı yaslar)
        self.win_list_lay.addStretch(1)

    def save_data(self):
        selected = [cb.property("hwnd") for cb in self.window_checks if cb.isChecked()]
        new_entries = [{"enabled": r[0].isChecked(), "key": r[1].currentText(), "delay": r[2].value(), "unit": r[3].currentText()} for r in self.rows]
        self.result_config = {"hotkey": self.txt_hk.text(), "target_hwnds": selected, "entries": new_entries}
        self.accept()

# =========================================================
# 3. WIDGET (STANDART KART)
# =========================================================
class BackgroundBotV2Widget(QFrame):
    update_signal = pyqtSignal()
    def __init__(self, parent=None, macro_instance=None, config=None):
        super().__init__(parent)
        self.macro = macro_instance or BackgroundBotV2Macro()
        self.config = config or {}
        self.macro.update_config(self.config)
        self.listen_active = False
        self._hooks = []

        self.setFrameShape(QFrame.Box)
        self.setFrameShadow(QFrame.Plain)
        self.setMaximumWidth(260)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setStyleSheet("QFrame { background-color: #101010; border: 1px solid #444; border-radius: 4px; }")
        
        self.setup_ui() # Arayüzü oluştur
        
        self.update_signal.connect(self._safe_update_status)
        self._safe_update_status()

    def setup_ui(self):
        v = QVBoxLayout(self); v.setContentsMargins(6, 6, 6, 6); v.setSpacing(4)
        
        # Header (İkon + İsim)
        h = QHBoxLayout(); h.setSpacing(6)
        
        # İkonu 2 tane yaptık, genişliği 50 yaptık ve çizgiyi sildik
        icon = QLabel("🕹🕹")
        icon.setFixedSize(50, 25)
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("border: none; background: transparent;") 
        
        h.addWidget(icon)
        h.addStretch(1)
        lbl_title = QLabel("ARKA PLAN BOTU"); lbl_title.setObjectName("MinorHeaderLabel"); h.addWidget(lbl_title)
        v.addLayout(h)

        # Dinleme Butonu
        self.btn_listen = QPushButton("TUŞ DİNLEMEYİ BAŞLAT")
        self.btn_listen.setObjectName("ThreeFiveListenButton")
        self.btn_listen.setProperty("active", False)
        self.btn_listen.clicked.connect(self.toggle_listen)
        v.addWidget(self.btn_listen)

        # Durum Label
        self.lbl_status = QLabel("DURUM: PASİF")
        self.lbl_status.setObjectName("MinorStatusLabel")
        v.addWidget(self.lbl_status)

        # --- KRİTİK EKSİK PARÇA BURASI ---
        # Bağlı client sayısını gösteren küçük gri yazı
        self.lbl_info = QLabel(f"Bağlı: {len(self.config.get('target_hwnds', []))} Client")
        self.lbl_info.setStyleSheet("color: #888; font-size: 8pt; border: none;")
        v.addWidget(self.lbl_info)
        # -------------------------------

        # Alt Satır (Hotkey & Ayarlar)
        row = QHBoxLayout(); row.setSpacing(4)
        row.addWidget(QLabel("AKTİF TUŞ:"))
        self.lbl_hotkey = QLabel(self.config.get("hotkey", "INSERT"))
        self.lbl_hotkey.setObjectName("HotkeyLabel"); self.lbl_hotkey.setAlignment(Qt.AlignCenter)
        row.addWidget(self.lbl_hotkey)
        
        btn_set = QPushButton("⚙ AYARLAR"); btn_set.setObjectName("MinorSettingsButton")
        btn_set.setFlat(True); btn_set.clicked.connect(self.open_settings)
        row.addWidget(btn_set)
        v.addLayout(row)

    def toggle_listen(self):
        if not keyboard: return
        if not self.listen_active:
            hk = self.config.get("hotkey", "INSERT").lower()
            try:
                h = keyboard.on_press_key(hk, lambda e: self.on_hotkey_trigger())
                self._hooks.append(h)
                self.listen_active = True
            except: self.listen_active = False
        else:
            for h in self._hooks: keyboard.unhook(h)
            self._hooks = []; self.listen_active = False
            self.macro.stop()
        self._safe_update_status()

    def on_hotkey_trigger(self):
        self.macro.toggle()
        self.update_signal.emit()

    def _safe_update_status(self):
        if not self.listen_active:
            self.lbl_status.setText("DURUM: PASİF")
            self.lbl_status.setStyleSheet("color: #ff5555; font-weight: bold;")
            self.btn_listen.setText("TUŞ DİNLEMEYİ BAŞLAT")
            self.btn_listen.setProperty("active", False)
        else:
            if self.macro.is_running:
                client_count = len(self.macro.target_hwnds)
                self.lbl_status.setText(f"DURUM: ÇALIŞIYOR ({client_count} CLIENT)")
                self.lbl_status.setStyleSheet("color: #00ff4c; font-weight: bold;")
            else:
                self.lbl_status.setText("DURUM: BEKLİYOR")
                self.lbl_status.setStyleSheet("color: #ffff55; font-weight: bold;")
            self.btn_listen.setText("TUŞ DİNLEMEYİ DURDUR")
            self.btn_listen.setProperty("active", True)
        
        self.lbl_hotkey.setStyleSheet("color: #00e676; font-weight: bold; font-family: Consolas;")
        self.btn_listen.style().unpolish(self.btn_listen); self.btn_listen.style().polish(self.btn_listen)

    def open_settings(self):
        dlg = BackgroundBotV2SettingsDialog(self, self.config, self.macro)
        if dlg.exec_():
            self.config.update(dlg.result_config)
            self.macro.update_config(self.config)
            self.lbl_hotkey.setText(self.config.get("hotkey"))
            # Artık self.lbl_info tanımlı olduğu için bu satır hata vermeyecek:
            self.lbl_info.setText(f"Bağlı: {len(self.config.get('target_hwnds', []))} Client")
            self.update_signal.emit()
            if self.listen_active: self.toggle_listen(); self.toggle_listen()
