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
import os
import json
import keyboard
import random
import pyautogui # Koordinat yakalamak için
from PyQt5.QtWidgets import (
    QDialog, QGridLayout, QLabel, QComboBox, 
    QLineEdit, QPushButton, QDoubleSpinBox, 
    QDialogButtonBox, QHBoxLayout, QWidget,
    QFrame, QVBoxLayout, QSizePolicy, QMessageBox,
    QScrollArea, QCheckBox, QGroupBox, QRadioButton,
    QButtonGroup
)
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt, pyqtSignal, QTimer

# Sürücü Kontrolü
try:
    from clicksend import KeyboardDriver, MouseDriver
except ImportError:
    KeyboardDriver = None
    MouseDriver = None

# Sistem Scancode Tablosu
SCANCODES = {
    'a': 0x1E, 'b': 0x30, 'c': 0x2E, 'd': 0x20, 'e': 0x12, 'f': 0x21, 'g': 0x22, 'h': 0x23, 'i': 0x17, 'j': 0x24,
    'k': 0x25, 'l': 0x26, 'm': 0x32, 'n': 0x31, 'o': 0x18, 'p': 0x19, 'q': 0x10, 'r': 0x13, 's': 0x1F, 't': 0x14,
    'u': 0x16, 'v': 0x2F, 'w': 0x11, 'x': 0x2D, 'y': 0x15, 'z': 0x2C,
    '0': 0x0B, '1': 0x02, '2': 0x03, '3': 0x04, '4': 0x05, '5': 0x06, '6': 0x07, '7': 0x08, '8': 0x09, '9': 0x0A,
    ' ': 0x39, '.': 0x34, ',': 0x33, '-': 0x0C, '+': 0x0D, '/': 0x35, ':': 0x27, '!': 0x02, '?': 0x35,
    'enter': 0x1C
}

class ChatMacro:
    def __init__(self):
        self.config = {}
        self._running = False
        self._active = False
        self._stop_event = threading.Event()
        self.kb = KeyboardDriver() if KeyboardDriver else None
        self.mouse = MouseDriver() if MouseDriver else None
        self._current_idx = 0

    def update_config(self, cfg):
        self.config = cfg

    @property
    def is_running(self): return self._running
    @property
    def is_active(self): return self._active

    def toggle_active(self):
        if not self._running: return
        self._active = not self._active

    def start(self):
        if not self._running:
            self._stop_event.clear()
            self._running = True
            self._active = False
            threading.Thread(target=self._main_loop, daemon=True).start()

    def stop(self):
        self._stop_event.set()
        self._running = False
        self._active = False

    def _send_text(self, text, channel):
        if not self.kb or not self.mouse or not text: return
        try:
            # 1. Koordinatı Al
            chan_key = "coord_all" if channel == "ALL" else "coord_shout"
            coords = self.config.get(chan_key, (0, 0))
            tx, ty = int(coords[0]), int(coords[1])
            server_mode = self.config.get("server_mode", "usko")

            # 2. Koordinata Git ve Tıkla
            if hasattr(self.mouse, 'move'): self.mouse.move(tx, ty)
            time.sleep(0.1)
            self.mouse.leftclick(0.05, tx, ty)
            time.sleep(0.2)

            # 3. Yazım Modu
            if server_mode == "usko":
                self.kb.tusbas(SCANCODES['enter'], 0.05) # USKO Ekstra Enter
                time.sleep(0.1)
            
            for char in text.lower():
                if self._stop_event.is_set(): return
                sc = SCANCODES.get(char)
                if sc: self.kb.tusbas(sc, 0.01)
                time.sleep(0.01)
            
            time.sleep(0.05)
            self.kb.tusbas(SCANCODES['enter'], 0.05) # Gönder

        except Exception as e: print(f"Hata: {e}")

    def _main_loop(self):
        last_msg_time = 0
        current_wait = 1.0
        while not self._stop_event.is_set():
            if self._active:
                raw_msgs = self.config.get("messages", [])
                active_msgs = [m for m in raw_msgs if m.get('active') and m.get('text','').strip()]
                if active_msgs:
                    now = time.time()
                    if now - last_msg_time >= current_wait:
                        if self._current_idx >= len(active_msgs): self._current_idx = 0
                        target = active_msgs[self._current_idx]
                        self._send_text(target['text'], target['channel'])
                        self._current_idx = (self._current_idx + 1) % len(active_msgs)
                        last_msg_time = time.time()
                        # Yeni Süreyi Belirle
                        if self.config.get("speed_mode") == "random":
                            current_wait = random.uniform(self.config.get("rand_min", 1.0), self.config.get("rand_max", 3.0))
                        else:
                            current_wait = self.config.get("message_speed", 1.0)
                else: time.sleep(0.5)
            time.sleep(self.config.get("main_speed", 0.05))

# ---------------------------------------------------------
# SETTINGS UI
# ---------------------------------------------------------
class ChatSettingsDialog(QDialog):
    coord_signal = pyqtSignal(int, int)

    def __init__(self, parent, config, macro):
        super().__init__(parent)
        self.setWindowTitle("CHAT SPAM AYARLARI")
        self.setFixedSize(850, 700) # Biraz boyu uzattık koordinatlar için
        self.config, self.macro = config, macro
        self.capture_mode = 0 # 1:Key, 2:All, 3:Shout
        self.coord_signal.connect(self._handle_coord)

        self.setStyleSheet("""
            QDialog { background-color: #121212; }
            QLabel { color: #ccc; font-family: 'Segoe UI'; font-size: 11px; }
            QLineEdit { background: #080808; border: 1px solid #333; color: #00ff4c; padding: 4px; }
            QPushButton { background-color: #252525; color: white; border: 1px solid #444; padding: 6px; }
            QCheckBox { color: #00ff4c; font-size: 10px; }
            QRadioButton { color: #eee; font-size: 11px; }
            QComboBox { background: #222; color: #00ff4c; border: 1px solid #444; }
            QScrollArea { border: 1px solid #222; background: #000; }
            
        """)

        layout = QVBoxLayout(self)

        # ÜST PANEL: Tuş ve Oyun Modu
        top_h = QHBoxLayout()
        top_h.addWidget(QLabel("BAŞLAT TUŞU:"))
        self.txt_key = QLineEdit(self.config.get("key", "CTRL"))
        self.txt_key.setFixedWidth(80); self.txt_key.setReadOnly(True)
        btn_key = QPushButton("SEÇ"); btn_key.clicked.connect(lambda: self._set_capture(1))
        top_h.addWidget(self.txt_key); top_h.addWidget(btn_key)
        
        top_h.addSpacing(30)
        top_h.addWidget(QLabel("MOD:"))
        self.rb_usko = QRadioButton("USKO"); self.rb_acme = QRadioButton("ACME")
        self.server_grp = QButtonGroup(self); self.server_grp.addButton(self.rb_usko); self.server_grp.addButton(self.rb_acme)
        if self.config.get("server_mode") == "acme": self.rb_acme.setChecked(True)
        else: self.rb_usko.setChecked(True)
        top_h.addWidget(self.rb_usko); top_h.addWidget(self.rb_acme); top_h.addStretch()
        layout.addLayout(top_h)


        label = QLabel("⚠️ ÖNERİ: Karakter içeren harfler (F,A,S vb.) yerine CTRL, Shift seçiniz.")
        label.setStyleSheet("""
            color: #ffaa00;
            font-weight: bold;
            font-size: 14px;
        """)
        layout.addWidget(label)

        # KOORDİNAT PANELİ
        coord_h = QHBoxLayout()
        self.btn_all = QPushButton(f"ALL KOORDİNAT AL (F) - {self.config.get('coord_all', (0,0))}")
        self.btn_all.clicked.connect(lambda: self._set_capture(2))
        self.btn_shout = QPushButton(f"SHOUT KOORDİNAT AL (F) - {self.config.get('coord_shout', (0,0))}")
        self.btn_shout.clicked.connect(lambda: self._set_capture(3))
        coord_h.addWidget(self.btn_all); coord_h.addWidget(self.btn_shout)
        layout.addLayout(coord_h)

        # SÜRE PANELİ
        speed_group = QGroupBox("GÖNDERİM SÜRE MODU")
        speed_group.setStyleSheet("color: #00ff4c; font-weight: bold; border: 1px solid #333;")
        speed_l = QVBoxLayout(speed_group)
        h1 = QHBoxLayout(); self.rb_fixed = QRadioButton("SABİT:"); self.spin_f = QDoubleSpinBox(); self.spin_f.setValue(self.config.get("message_speed", 1.0))
        h1.addWidget(self.rb_fixed); h1.addWidget(self.spin_f); h1.addStretch()
        h2 = QHBoxLayout(); self.rb_rand = QRadioButton("RANDOM:"); self.s_min = QDoubleSpinBox(); self.s_max = QDoubleSpinBox()
        self.s_min.setValue(self.config.get("rand_min", 1.0)); self.s_max.setValue(self.config.get("rand_max", 3.0))
        h2.addWidget(self.rb_rand); h2.addWidget(QLabel("Min:")); h2.addWidget(self.s_min); h2.addWidget(QLabel("Max:")); h2.addWidget(self.s_max); h2.addStretch()
        speed_l.addLayout(h1); speed_l.addLayout(h2); layout.addWidget(speed_group)
        
        self.speed_grp = QButtonGroup(self); self.speed_grp.addButton(self.rb_fixed); self.speed_grp.addButton(self.rb_rand)
        if self.config.get("speed_mode") == "random": self.rb_rand.setChecked(True)
        else: self.rb_fixed.setChecked(True)

        

        # MESAJ LİSTESİ
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.container = QWidget(); self.grid = QGridLayout(self.container)
        self.inputs = []
        saved_msgs = self.config.get("messages", [])
        for i in range(20):
            row, col = i % 10, (i // 10) * 3
            chk = QCheckBox(f"#{i+1}")
            cmb = QComboBox(); cmb.addItems(["ALL", "SHOUT"])
            edit = QLineEdit()
            if i < len(saved_msgs):
                edit.setText(saved_msgs[i].get("text", ""))
                chk.setChecked(saved_msgs[i].get("active", False))
                cmb.setCurrentText(saved_msgs[i].get("channel", "ALL"))
            self.grid.addWidget(chk, row, col)
            self.grid.addWidget(cmb, row, col + 1)
            self.grid.addWidget(edit, row, col + 2)
            self.inputs.append((chk, cmb, edit))
        self.scroll.setWidget(self.container); layout.addWidget(self.scroll)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject); layout.addWidget(btns)

        if keyboard: keyboard.on_press_key("f", self._on_f_press)

    def _set_capture(self, mode):
        self.capture_mode = mode
        if mode == 1: self.txt_key.setText("..."); self.grabKeyboard()
        elif mode == 2: self.btn_all.setText("MOUSE'U GETİRİN VE F BASIN")
        elif mode == 3: self.btn_shout.setText("MOUSE'U GETİRİN VE F BASIN")

    def _on_f_press(self, e):
        if self.capture_mode in [2, 3]:
            x, y = pyautogui.position(); self.coord_signal.emit(x, y)

    def _handle_coord(self, x, y):
        if self.capture_mode == 2:
            self.config["coord_all"] = (x, y); self.btn_all.setText(f"ALL KOORDİNAT - {(x,y)}")
        elif self.capture_mode == 3:
            self.config["coord_shout"] = (x, y); self.btn_shout.setText(f"SHOUT KOORDİNAT - {(x,y)}")
        self.capture_mode = 0

    def keyPressEvent(self, e):
        if self.capture_mode == 1:
            key = e.key()
            name = {Qt.Key_CapsLock: "CAPSLOCK", Qt.Key_Shift: "SHIFT", Qt.Key_Control: "CTRL", Qt.Key_F1: "F1"}.get(key) or e.text().upper()
            if name: self.txt_key.setText(name); self.capture_mode = 0; self.releaseKeyboard()
        else: super().keyPressEvent(e)

    def accept(self):
        msg_data = []
        for chk, cmb, edit in self.inputs:
            msg_data.append({"active": chk.isChecked(), "channel": cmb.currentText(), "text": edit.text()})
        self.config.update({
            "key": self.txt_key.text(), "server_mode": "acme" if self.rb_acme.isChecked() else "usko",
            "speed_mode": "random" if self.rb_rand.isChecked() else "fixed",
            "message_speed": self.spin_f.value(), "rand_min": self.s_min.value(), "rand_max": self.s_max.value(),
            "messages": msg_data
        })
        self.macro.update_config(self.config); super().accept()

# ---------------------------------------------------------
# WIDGET
# ---------------------------------------------------------
class ChatWidget(QFrame):
    update_signal = pyqtSignal()
    def __init__(self, parent=None, macro_instance=None, config=None):
        super().__init__(parent); self.macro = macro_instance
        self.config = config or {"key": "CTRL", "server_mode": "usko", "speed_mode": "fixed", "message_speed": 1.0, "messages": [], "main_speed": 0.05}
        self.listen_active, self._hook = False, None
        self.setup_ui(); self.update_signal.connect(self._safe_update); self._safe_update()

    def setup_ui(self):
        self.setFrameShape(QFrame.Box); self.setFixedWidth(260)
        self.setStyleSheet("QFrame { background-color: #101010; border: 1px solid #444; border-radius: 4px; }")
        v = QVBoxLayout(self)
        h = QHBoxLayout(); h.addWidget(QLabel("💬")); h.addStretch(); h.addWidget(QLabel("FLOOD MACRO", objectName="MinorHeaderLabel")); v.addLayout(h)
        self.btn = QPushButton("TUŞ DİNLEMEYİ BAŞLAT"); self.btn.setObjectName("ThreeFiveListenButton"); self.btn.clicked.connect(self.toggle_listen); v.addWidget(self.btn)
        self.st = QLabel("DURUM: PASİF"); self.st.setObjectName("MinorStatusLabel"); v.addWidget(self.st)
        row = QHBoxLayout(); row.addWidget(QLabel("TUŞ:")); self.hk = QLabel(self.config.get("key", "CAPSLOCK")); self.hk.setObjectName("HotkeyLabel"); row.addWidget(self.hk); btn_set = QPushButton("⚙ AYARLAR"); btn_set.setObjectName("MinorSettingsButton"); btn_set.clicked.connect(self.open_set); row.addWidget(btn_set); v.addLayout(row)

    def open_set(self):
        if ChatSettingsDialog(self, self.config, self.macro).exec_():
            self.hk.setText(self.config["key"])
            if self.listen_active: self.toggle_listen(); self.toggle_listen()

    def toggle_listen(self):
        if not self.listen_active:
            try:
                self._hook = keyboard.on_press_key(self.config["key"].lower(), lambda e: self.on_hotkey())
                self.listen_active = True; self.macro.start()
            except: pass
        else:
            if self._hook: keyboard.unhook(self._hook)
            self._hook, self.listen_active = None, False; self.macro.stop()
        self._safe_update()

    def on_hotkey(self): self.macro.toggle_active(); self.update_signal.emit()

    def _safe_update(self):
        if not self.listen_active:
            # Dinleme Kapalıyken
            self.st.setText("DURUM: PASİF")
            self.st.setStyleSheet("color:#ff5555; font-weight:bold;")
            self.btn.setText("TUŞ DİNLEMEYİ BAŞLAT") # Buton yazısını güncelle
        else:
            # Dinleme Açıkken
            active = self.macro.is_active
            mode = self.config.get("server_mode", "USKO").upper()
            self.st.setText(f"{mode} YAZIYOR..." if active else f"BEKLİYOR ({self.config['key']})")
            self.st.setStyleSheet(f"color:{'#00ff4c' if active else '#ffff55'}; font-weight:bold;")
            self.btn.setText("TUŞ DİNLEMEYİ DURDUR") # Buton yazısını güncelle

        # Hover efektinin (Mor) çalışması için gereken property ve stil yenileme
        self.btn.setProperty("active", self.listen_active)
        self.btn.style().unpolish(self.btn)
        self.btn.style().polish(self.btn)

        if self.listen_active:
            QTimer.singleShot(500, self._safe_update)
