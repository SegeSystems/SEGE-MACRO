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
from typing import Callable, Literal

# PyQt5
from PyQt5.QtWidgets import (
    QDialog, QGridLayout, QLabel, QComboBox, 
    QLineEdit, QPushButton, QDoubleSpinBox, 
    QDialogButtonBox, QHBoxLayout, QWidget,
    QFrame, QVBoxLayout, QSizePolicy, QMessageBox, QListWidget, QListWidgetItem, QSpacerItem,
    QCheckBox # <--- EKLENDİ
)
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtCore import Qt, QSize, pyqtSignal

# Harici Kütüphaneler
import pyautogui

try:
    import keyboard
except ImportError:
    keyboard = None

# Opsiyonel clicksend / interception sürücüsü
try:
    from clicksend import KeyboardDriver as _ClicksendKeyboardDriver
    from clicksend import MouseDriver as _ClicksendMouseDriver
except ImportError:
    _ClicksendKeyboardDriver = None
    _ClicksendMouseDriver = None

# ---------------------------------------------------------
# SABİTLER
# ---------------------------------------------------------
SC_I = 0x17 # 'I' tuşu (Envanter)
CONFIG_FILE = "itemchange.json"

# ---------------------------------------------------------
# 1. LOGIC (MAKRO MOTORU)
# ---------------------------------------------------------
class ItemChangeMacro:
    def __init__(self):
        self.kb = _ClicksendKeyboardDriver() if _ClicksendKeyboardDriver else None
        self.mouse = _ClicksendMouseDriver() if _ClicksendMouseDriver else None
        self.coords = []
        self.delay = 0.05
        
        # Yeni Ayarlar
        self.inventory_open_mode = False
        self.return_mouse_pos = False
        
        self._running = False
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    def set_config(self, coords, delay, inv_mode, mouse_mode):
        self.coords = coords
        self.delay = max(0.01, float(delay))
        self.inventory_open_mode = inv_mode
        self.return_mouse_pos = mouse_mode

    # Eski uyumluluk için (kaldırmadım ama set_config kullanmak daha iyi)
    def set_coords(self, coords): self.coords = coords
    def set_delay(self, delay): self.delay = max(0.01, float(delay))

    @property
    def is_running(self):
        return self._running
    
    def stop(self):
        if self._running:
            self._stop_event.set()

    def run_once(self):
        if self._running: return
        
        with self._lock:
            self._running = True
            self._stop_event.clear()
            
            # Mouse pozisyonunu kaydet
            start_x, start_y = pyautogui.position()
            
            try:
                if not self.coords:
                    print("[ITEM] Koordinat listesi boş.")
                    return

                # 1. ÇANTA AÇ (Eğer "Zaten Açık" modu kapalıysa bas)
                if not self.inventory_open_mode:
                    if self._stop_event.is_set(): return
                    if self.kb: self.kb.tusbas(SC_I, 0.05)
                    else: print("[ITEM] Çanta Aç (Fake)")
                    
                    # Çanta açılış animasyon beklemesi
                    time.sleep(0.25) 
                else:
                    # Çanta zaten açıksa bekleme yapmaya gerek yok
                    pass

                # 2. İTEMLERİ DEĞİŞTİR
                for (x, y) in self.coords:
                    if self._stop_event.is_set(): break
                    
                    if self.mouse: 
                        self.mouse.rightclick(self.delay, x, y)
                    else:
                        print(f"[ITEM] Sağ tık: {x}, {y}")
                    
                    time.sleep(self.delay)

                time.sleep(0.10)
                
                # 3. ÇANTA KAPAT (Eğer "Zaten Açık" modu kapalıysa bas)
                if not self.inventory_open_mode:
                    if not self._stop_event.is_set():
                        if self.kb: self.kb.tusbas(SC_I, 0.05)
                
                # 4. MOUSE GERİ DÖNDÜR
                if self.return_mouse_pos:
                    if self.mouse and hasattr(self.mouse, 'move'):
                         self.mouse.move(start_x, start_y)
                    else:
                         pyautogui.moveTo(start_x, start_y)

            except Exception as e:
                print(f"[ITEM] Hata: {e}")
            finally:
                self._running = False


# ---------------------------------------------------------
# 2. GUI (AYAR PENCERESİ)
# ---------------------------------------------------------
class ItemChangeSettings(QDialog):
    coord_signal = pyqtSignal(int, int)

    def __init__(self, parent, config, macro):
        super().__init__(parent)
        self.setWindowTitle("İTEM DEĞİŞME AYARLARI")
        self.setModal(True)
        self.macro = macro
        self.config = config
        self.capture_hotkey = False
        self._f_hook = None
        
        self.coord_signal.connect(self._add_coord_to_list)

        # UI Layout
        main = QVBoxLayout(self)
        grid = QGridLayout()
        main.addLayout(grid)

        # Liste
        self.list_coords = QListWidget()
        grid.addWidget(QLabel("Kayıtlı Koordinatlar:"), 0, 0)
        grid.addWidget(self.list_coords, 1, 0, 5, 1) # Yüksekliği artırdık

        # Yan Panel
        side = QVBoxLayout()
        lbl_info = QLabel("Koordinat eklemek için\nMouse'u item üstüne getir\nve 'F' tuşuna bas.")
        lbl_info.setStyleSheet("color: #888; font-style: italic; font-size: 9pt;")
        lbl_info.setAlignment(Qt.AlignCenter)
        side.addWidget(lbl_info)
        side.addSpacing(10)
        
        btn_del = QPushButton("Seçileni Sil")
        btn_clear = QPushButton("Tümünü Sil")
        side.addWidget(btn_del)
        side.addWidget(btn_clear)
        side.addItem(QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding))
        grid.addLayout(side, 1, 1, 5, 1)

        # --- YENİ CHECKBOX AYARLARI ---
        self.chk_inv_mode = QCheckBox("Çanta Zaten Açık (I basma)")
        self.chk_inv_mode.setToolTip("İşaretlenirse makro başında ve sonunda 'I' tuşuna basmaz.")
        
        self.chk_mouse_return = QCheckBox("Mouse'u Eski Yerine Döndür")
        self.chk_mouse_return.setToolTip("İşlem bitince mouse imlecini başladığı yere geri ışınlar.")

        # Bunları alt alta ekleyelim
        opts_layout = QVBoxLayout()
        opts_layout.addWidget(self.chk_inv_mode)
        opts_layout.addWidget(self.chk_mouse_return)
        
        grid.addLayout(opts_layout, 6, 0, 1, 2)

        # Hotkey
        grid.addWidget(QLabel("Aktif Tuş:"), 7, 0)
        self.txt_hotkey = QLineEdit()
        self.txt_hotkey.setReadOnly(True)
        hk_layout = QHBoxLayout()
        hk_layout.addWidget(self.txt_hotkey)
        self.btn_hotkey = QPushButton("Tuş Seç")
        hk_layout.addWidget(self.btn_hotkey)
        grid.addLayout(hk_layout, 7, 1)

        # Delay
        grid.addWidget(QLabel("Sağ tık gecikme (sn):"), 8, 0)
        self.spin_delay = QDoubleSpinBox()
        self.spin_delay.setRange(0.01, 1.00)
        self.spin_delay.setDecimals(3)
        self.spin_delay.setSingleStep(0.01)
        grid.addWidget(self.spin_delay, 8, 1)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        main.addWidget(btn_box)

        # Events
        btn_del.clicked.connect(self.on_del)
        btn_clear.clicked.connect(self.on_clear)
        self.btn_hotkey.clicked.connect(self.on_hotkey_capture)
        btn_box.accepted.connect(self.on_accept)
        btn_box.rejected.connect(self.reject)

        self.load_to_ui()
        self.start_f_hook()

    def start_f_hook(self):
        try:
            if keyboard:
                self._f_hook = keyboard.on_press_key("F", self._on_f_press)
        except Exception as e:
            print(f"[ITEM] Hook hatası: {e}")

    def stop_f_hook(self):
        try:
            if self._f_hook and keyboard:
                keyboard.unhook(self._f_hook)
        except: pass

    def _on_f_press(self, e):
        x, y = pyautogui.position()
        self.coord_signal.emit(x, y)

    def _add_coord_to_list(self, x, y):
        self.list_coords.addItem(f"{x}, {y}")
        self.list_coords.scrollToBottom()

    def load_to_ui(self):
        self.list_coords.clear()
        for x, y in self.config.get("coords", []):
            self.list_coords.addItem(f"{x}, {y}")

        self.txt_hotkey.setText(self.config.get("hotkey", "G").upper())
        self.spin_delay.setValue(self.config.get("delay", 0.05))
        
        # Yeni Ayarları Yükle
        self.chk_inv_mode.setChecked(self.config.get("inv_mode", False))
        self.chk_mouse_return.setChecked(self.config.get("mouse_return", False))

    def save_from_ui(self):
        coords = []
        for i in range(self.list_coords.count()):
            t = self.list_coords.item(i).text()
            try:
                x, y = t.split(",")
                coords.append((int(x), int(y)))
            except: pass

        self.config["coords"] = coords
        self.config["hotkey"] = self.txt_hotkey.text()
        self.config["delay"] = float(self.spin_delay.value())
        
        # Yeni Ayarları Kaydet
        self.config["inv_mode"] = self.chk_inv_mode.isChecked()
        self.config["mouse_return"] = self.chk_mouse_return.isChecked()

        # Makroya gönder
        self.macro.set_config(
            coords=coords,
            delay=self.config["delay"],
            inv_mode=self.config["inv_mode"],
            mouse_mode=self.config["mouse_return"]
        )
        
        # JSON Dosyasına Yaz
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2)
        except: pass

    def on_del(self):
        row = self.list_coords.currentRow()
        if row >= 0: self.list_coords.takeItem(row)

    def on_clear(self): self.list_coords.clear()

    def on_hotkey_capture(self):
        self.capture_hotkey = True
        self.txt_hotkey.setText("TUŞA BAS...")

    def keyPressEvent(self, event):
        if self.capture_hotkey:
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
                self.txt_hotkey.setText(name.upper())
                self.capture_hotkey = False
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if self.capture_hotkey:
            name = None
            btn = event.button()
            if btn == Qt.LeftButton: name = "left"
            elif btn == Qt.RightButton: name = "right"
            elif btn == Qt.MiddleButton: name = "middle"
            elif btn == Qt.XButton1: name = "mouse4"
            elif btn == Qt.XButton2: name = "mouse5"
            if name:
                self.txt_hotkey.setText(name.upper())
                self.capture_hotkey = False
            return
        super().mousePressEvent(event)

    def on_accept(self):
        self.stop_f_hook()
        self.save_from_ui()
        self.result_config = self.config 
        self.accept()
    
    def reject(self):
        self.stop_f_hook()
        super().reject()


# =========================================================
# 3. WIDGET (ANA EKRAN KARTI)
# =========================================================
class ItemChangeWidget(QFrame):
    update_signal = pyqtSignal()

    def __init__(self, parent=None, macro_instance=None, config=None):
        super().__init__(parent)
        self.macro = macro_instance
        self.config = config or {}
        self.listen_active = False
        self._hotkey_handles = []
        
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
        h = QHBoxLayout()
        h.setSpacing(6)
        
        # İkonlar
        icon_row = QHBoxLayout()
        icon_row.setSpacing(3)
        icon_paths = ["icons/item_raptor.png", "icons/item_shard.png", "icons/item_ib.png", "icons/item_ii.png"]
        for p in icon_paths:
            l = QLabel()
            l.setFixedSize(25, 25)
            pix = QPixmap(p)
            if not pix.isNull(): 
                l.setPixmap(pix.scaled(25, 25, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            icon_row.addWidget(l)
        h.addLayout(icon_row)

        lbl = QLabel("İTEM DEĞİŞME")
        h.addStretch(1)
        lbl.setObjectName("MinorHeaderLabel") 
        h.addWidget(lbl)
        
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


        # Alt Kısım
        row = QHBoxLayout()
        row.setSpacing(4)
        row.addWidget(QLabel("AKTİF TUŞ:"))
        
        self.lbl_hotkey = QLabel(self.config.get("hotkey", "G").upper())
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
        dlg = ItemChangeSettings(self, self.config, self.macro)
        if dlg.exec_() == QDialog.Accepted:
            self.config.update(dlg.result_config)
            self.lbl_hotkey.setText(self.config["hotkey"].upper())
            
            # Ayarlar değiştiğinde makroya yeni ayarları gönder
            self.macro.set_config(
                coords=self.config.get("coords", []),
                delay=self.config.get("delay", 0.05),
                inv_mode=self.config.get("inv_mode", False),
                mouse_mode=self.config.get("mouse_return", False)
            )
            
            if self.listen_active: 
                self.toggle_listen()
                self.toggle_listen()

    def toggle_listen(self):
        try: import keyboard
        except: return QMessageBox.warning(self, "Hata", "keyboard kütüphanesi yok")

        if not self.listen_active:
            # BAŞLAT
            k = self.config.get("hotkey", "G").lower()
            self._hotkey_handles = []
            try:
                h = keyboard.on_press_key(k, lambda e: self.run_macro(), suppress=False)
                self._hotkey_handles.append(h)
                self.listen_active = True
            except Exception as e: 
                print(e)
                self.listen_active = False
        else:
            # DURDUR
            for h in self._hotkey_handles: 
                try: keyboard.unhook(h)
                except: pass
            self._hotkey_handles = []
            self.listen_active = False
            self.macro.stop()
        
        self._safe_update_status()

    def run_macro(self):
        if not self.macro.is_running:
            threading.Thread(target=self._run_macro_thread, daemon=True).start()

    def _run_macro_thread(self):
        self.update_signal.emit() # Çalışıyor
        self.macro.run_once()
        self.update_signal.emit() # Bitti

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
