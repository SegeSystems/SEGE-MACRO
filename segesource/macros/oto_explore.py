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
import cv2
import numpy as np
import mss

# PyQt5
from PyQt5.QtWidgets import (
    QDialog, QGridLayout, QLabel, QComboBox, 
    QLineEdit, QPushButton, QDoubleSpinBox, 
    QDialogButtonBox, QHBoxLayout, QWidget,
    QFrame, QVBoxLayout, QSizePolicy, QMessageBox,
    QCheckBox, QSpacerItem
)
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtCore import Qt, QSize, pyqtSignal

try:
    import keyboard
except ImportError:
    keyboard = None

# ---------------------------------------------------------
# DRIVER (OtoDef ile aynı mantık)
# clicksend.py dosyası bu dosyanın yanında olmalı!
# ---------------------------------------------------------
try:
    from clicksend import KeyboardDriver as _ClicksendKeyboardDriver
except ImportError:
    _ClicksendKeyboardDriver = None
    print("[HATA] 'clicksend.py' bulunamadı! Tuş basmayacaktır.")

# ---------------------------------------------------------
# SABİTLER
# ---------------------------------------------------------
DIGIT_SCANCODES = {
    1: 0x02, 2: 0x03, 3: 0x04, 4: 0x05, 5: 0x06,
    6: 0x07, 7: 0x08, 8: 0x09, 9: 0x0A, 0: 0x0B,
}
F_SCANCODES = {
    1: 0x3B, 2: 0x3C, 3: 0x3D, 4: 0x3E,
    5: 0x3F, 6: 0x40, 7: 0x41, 8: 0x42
}

BUFF_REGION_FILE = "BUFF_ALANI.json"

def _default_tap(scan_code: int, hold: float = 0.01):
    # OtoDef'teki gibi driver'ı başlatıp tuşa basıyoruz
    if _ClicksendKeyboardDriver and not hasattr(_default_tap, "_driver"):
        _default_tap._driver = _ClicksendKeyboardDriver()
    
    if hasattr(_default_tap, "_driver"):
        _default_tap._driver.tusbas(scan_code, hold)
    else:
        print(f"[HATA] Driver yok, tuşa basılamadı: {scan_code}")

# =========================================================
# 1. LOGIC (MAKRO MOTORU)
# =========================================================
class OtoExploreMacro:
    def __init__(self):
        self.skills = {
            "lf":   {"enabled": False, "f": 1, "d": 1, "icon": "lightfeet.png", "tmpl": None, "last_cast": 0},
            "wolf": {"enabled": False, "f": 1, "d": 2, "icon": "wolf.png",      "tmpl": None, "last_cast": 0},
            "lup":  {"enabled": False, "f": 1, "d": 3, "icon": "lupin.png",     "tmpl": None, "last_cast": 0},
            "ms":   {"enabled": False, "f": 1, "d": 4, "icon": "62.png",        "tmpl": None, "last_cast": 0}, 
        }
        
        self.buff_region = None
        self.match_threshold = 0.80  
        self.check_interval = 0.20
        self.cast_cooldown = 1.5
        self.same_skill_cd = 5.0
        
        self._running = False
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        
        self._load_buff_region()
        self._load_templates()

    def update_config(self, cfg):
        with self._lock:
            if "skills" in cfg:
                for key, val in cfg["skills"].items():
                    if key in self.skills:
                        self.skills[key]["enabled"] = val.get("enabled", False)
                        self.skills[key]["f"] = val.get("f", 1)
                        self.skills[key]["d"] = val.get("d", 1)
            self._load_buff_region()

    def _load_buff_region(self):
        if os.path.isfile(BUFF_REGION_FILE):
            try:
                with open(BUFF_REGION_FILE, "r") as f:
                    d = json.load(f)
                    self.buff_region = {
                        "left": int(d["x"]), "top": int(d["y"]), 
                        "width": int(d["w"]), "height": int(d["h"])
                    }
            except: 
                self.buff_region = None

    def _load_templates(self):
        base_dir = "icons"
        if not os.path.exists(base_dir):
            print(f"[EXPLORE HATA] '{base_dir}' klasörü yok!")
            return
        
        for key in self.skills:
            path = os.path.join(base_dir, self.skills[key]["icon"])
            if os.path.exists(path):
                # Hatalı olan yer burasıydı: IMREAD_GRAYSCALE olarak düzeltildi
                img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
                if img is not None:
                    self.skills[key]["tmpl"] = img
                    print(f"[EXPLORE] Template yüklendi: {key}")
                else:
                    print(f"[EXPLORE HATA] {path} okunamadı (Format hatası?)")
            else:
                print(f"[EXPLORE HATA] {path} bulunamadı!")


    @property
    def is_running(self): return self._running

    def toggle(self):
        if self._running: self.stop()
        else: self.start()

    def start(self):
        self._load_buff_region()
        if not self.buff_region:
            print("[EXPLORE] Buff bölgesi ayarlanmamış!")
            return
        
        for k in self.skills: self.skills[k]["last_cast"] = 0
        
        self._stop_event.clear()
        threading.Thread(target=self._loop, daemon=True).start()
        self._running = True
        print(f"[EXPLORE] Başladı. Eşik: {self.match_threshold}")

    def stop(self):
        self._stop_event.set()
        self._running = False
        print("[EXPLORE] Durduruldu.")

    def _loop(self):
        sct = mss.mss()
        print(f"[DEBUG] Döngü başladı. Buff bölgesi: {self.buff_region}")

        if not self.buff_region:
            print("[HATA] Buff bölgesi yüklenemedi!")
            return

        while not self._stop_event.is_set():
            try:
                # 1. Görüntü Al
                scr = np.array(sct.grab(self.buff_region))
                


                # 3. Aktif Skill Kontrolü
                active_skills = [k for k, v in self.skills.items() if v["enabled"] and v["tmpl"] is not None]
                if not active_skills:
                    time.sleep(1)
                    continue

                gray = cv2.cvtColor(scr, cv2.COLOR_BGRA2GRAY)
                current_time = time.time()
                action_taken = False

                for key in active_skills:
                    if self._stop_event.is_set(): break
                    skill = self.skills[key]
                    
                    if (current_time - skill["last_cast"]) < self.same_skill_cd:
                        continue

                    res = cv2.matchTemplate(gray, skill["tmpl"], cv2.TM_CCOEFF_NORMED)
                    _, max_val, _, _ = cv2.minMaxLoc(res)
                    
                    # OtoDef mantığı: Eşik altındaysa BAS
                    if max_val < self.match_threshold:
                        print(f"[EXPLORE] {key} eksik (Skor: {max_val:.2f}). Basılıyor...")
                        
                        f_val = skill["f"]
                        if f_val > 0:
                            f_code = F_SCANCODES.get(f_val)
                            if f_code: 
                                _default_tap(f_code, 0.04) # Süreyi biraz arttırdım garanti olsun
                                time.sleep(0.05)
                        
                        d_code = DIGIT_SCANCODES.get(skill["d"])
                        if d_code: 
                            _default_tap(d_code, 0.04)
                        
                        self.skills[key]["last_cast"] = time.time()
                        time.sleep(self.cast_cooldown)
                        action_taken = True
                        break 

                if not action_taken:
                    time.sleep(self.check_interval)

            except Exception as e:
                print(f"[EXPLORE HATA] Döngü: {e}")
                time.sleep(1)


# =========================================================
# 2. GUI (AYAR PENCERESİ)
# =========================================================
class OtoExploreSettingsDialog(QDialog):
    def __init__(self, parent, config, macro):
        super().__init__(parent)
        self.setWindowTitle("OTO EXPLORE AYARLARI")
        self.setModal(True)
        self.config = config
        self.macro = macro
        self.capture_hotkey = False
        
        main = QVBoxLayout(self)
        grid = QGridLayout()
        grid.setContentsMargins(10, 10, 10, 10); grid.setSpacing(10)
        main.addLayout(grid)

        grid.addWidget(QLabel("AKTIF TUŞ:"), 0, 0, 1, 2)
        self.txt_hotkey = QLineEdit(); self.txt_hotkey.setReadOnly(True)
        self.txt_hotkey.setText(self.config.get("hotkey", "CAPS LOCK").upper())
        btn_hot = QPushButton("TUŞ SEÇ"); btn_hot.clicked.connect(self.on_hotkey_capture)
        hk_box = QHBoxLayout(); hk_box.addWidget(self.txt_hotkey); hk_box.addWidget(btn_hot)
        grid.addLayout(hk_box, 0, 2, 1, 2)

        line = QFrame(); line.setFrameShape(QFrame.HLine); line.setFrameShadow(QFrame.Sunken)
        grid.addWidget(line, 1, 0, 1, 4)

        self.skill_rows = [
            ("lf",   "Light Feet",  "icons/lightfeet.png"),
            ("wolf", "Wolf",        "icons/wolf.png"),
            ("lup",  "Lupin Eyes",  "icons/lupin.png"),
            ("ms",   "Magic Shield","icons/62.png")
        ]
        
        self.ui_elements = {} 
        start_row = 2
        for i, (key, name, icon_path) in enumerate(self.skill_rows):
            row = start_row + i
            lbl_icon = QLabel(); lbl_icon.setFixedSize(30, 30); pix = QPixmap(icon_path)
            if not pix.isNull(): lbl_icon.setPixmap(pix.scaled(30, 30, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            grid.addWidget(lbl_icon, row, 0) 

            chk = QCheckBox(name)
            chk.setChecked(self.config.get("skills", {}).get(key, {}).get("enabled", False))
            grid.addWidget(chk, row, 1)      
            
            cmb_f = QComboBox(); cmb_f.addItem("F YOK", 0)  
            for f in range(1, 9): cmb_f.addItem(f"F{f}", f)
            val_f = self.config.get("skills", {}).get(key, {}).get("f", 1)
            idx_f = cmb_f.findData(val_f); 
            if idx_f < 0: idx_f = 0 
            cmb_f.setCurrentIndex(idx_f)
            grid.addWidget(cmb_f, row, 2)
            
            cmb_d = QComboBox(); cmb_d.addItems([str(d) for d in range(10)])
            val_d = self.config.get("skills", {}).get(key, {}).get("d", 1)
            cmb_d.setCurrentText(str(val_d))
            grid.addWidget(cmb_d, row, 3)
            
            self.ui_elements[key] = { "chk": chk, "f": cmb_f, "d": cmb_d }
            cmb_f.setEnabled(chk.isChecked()); cmb_d.setEnabled(chk.isChecked())
            chk.toggled.connect(cmb_f.setEnabled); chk.toggled.connect(cmb_d.setEnabled)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        main.addWidget(btns)

    def on_hotkey_capture(self): self.capture_hotkey = True; self.txt_hotkey.setText("BAS...")
    def keyPressEvent(self, event):
        if self.capture_hotkey:
            key = event.key()
            name = None
            if key == Qt.Key_CapsLock: name = "caps lock"
            elif key == Qt.Key_Shift: name = "shift"
            elif key == Qt.Key_Control: name = "ctrl"
            elif key == Qt.Key_Alt: name = "alt"
            elif Qt.Key_F1 <= key <= Qt.Key_F12: name = f"f{key - Qt.Key_F1 + 1}"
            else:
                text = event.text(); 
                if text: name = text.lower()
            if name: self.txt_hotkey.setText(name.upper()); self.capture_hotkey = False
            return
        super().keyPressEvent(event)

    def accept(self):
        self.config["hotkey"] = self.txt_hotkey.text()
        if "skills" not in self.config: self.config["skills"] = {}
        for key, ui in self.ui_elements.items():
            if key not in self.config["skills"]: self.config["skills"][key] = {}
            self.config["skills"][key]["enabled"] = ui["chk"].isChecked()
            self.config["skills"][key]["f"] = int(ui["f"].currentData())
            self.config["skills"][key]["d"] = int(ui["d"].currentText())
        self.macro.update_config(self.config)
        super().accept()

# =========================================================
# 3. WIDGET (ANA EKRAN KARTI)
# =========================================================
class OtoExploreWidget(QFrame):
    update_signal = pyqtSignal()

    def __init__(self, parent=None, macro_instance=None, config=None):
        super().__init__(parent)
        self.macro = macro_instance or OtoExploreMacro()
        self.config = config or {}
        self.macro.update_config(self.config)

        self.listen_active = False
        self._hotkey_hook = None
        self._last_toggle_time = 0
        
        self.update_signal.connect(self._safe_update_status)
        self.setup_ui()
        self._safe_update_status()

    def setup_ui(self):
        self.setFrameShape(QFrame.Box); self.setFrameShadow(QFrame.Plain); self.setMaximumWidth(260)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setStyleSheet("QFrame {background-color: #101010; border: 1px solid #444444; border-radius: 4px;}")
        
        v = QVBoxLayout(self); v.setContentsMargins(6, 6, 6, 6); v.setSpacing(4)
        h = QHBoxLayout(); h.setSpacing(4)
        icons = ["lightfeet.png", "wolf.png", "lupin.png", "62.png"]
        for icon in icons:
            l = QLabel(); l.setFixedSize(25, 25); pix = QPixmap(f"icons/{icon}")
            if not pix.isNull():
                l.setPixmap(pix.scaled(25, 25, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            h.addWidget(l)
        h.addStretch(1); lbl = QLabel("OTO EXPLORE"); lbl.setObjectName("MinorHeaderLabel"); h.addWidget(lbl)
        v.addLayout(h)

        self.btn_listen = QPushButton("TUŞ DİNLEMEYİ BAŞLAT")
        self.btn_listen.setObjectName("ThreeFiveListenButton") 
        self.btn_listen.setProperty("active", False)
        self.btn_listen.clicked.connect(self.toggle_listen)
        v.addWidget(self.btn_listen)

        self.lbl_status = QLabel("DURUM: PASİF"); self.lbl_status.setObjectName("MinorStatusLabel")
        v.addWidget(self.lbl_status)

        row = QHBoxLayout(); row.setSpacing(4); row.addWidget(QLabel("AKTİF TUŞ:"))
        self.lbl_hotkey = QLabel(self.config.get("hotkey", "CAPS LOCK")); self.lbl_hotkey.setObjectName("HotkeyLabel"); self.lbl_hotkey.setAlignment(Qt.AlignCenter)
        row.addWidget(self.lbl_hotkey)
        
        btn_set = QPushButton("⚙ AYARLAR"); btn_set.setObjectName("MinorSettingsButton"); btn_set.setFlat(True)
        btn_set.clicked.connect(self.open_settings)
        row.addWidget(btn_set)
        v.addLayout(row)

    def open_settings(self):
        dlg = OtoExploreSettingsDialog(self, self.config, self.macro)
        if dlg.exec_() == QDialog.Accepted:
            self.lbl_hotkey.setText(self.config.get("hotkey", "CAPS LOCK").upper())
            if self.listen_active: self.toggle_listen(); self.toggle_listen()

    def toggle_listen(self):
        if not keyboard: return QMessageBox.warning(self, "Hata", "keyboard yok")
        if not self.listen_active:
            hotkey = self.config.get("hotkey", "caps lock").lower()
            try:
                self._hotkey_hook = keyboard.on_press_key(hotkey, self.on_hotkey_press, suppress=False)
                self.listen_active = True
            except Exception as e:
                print(f"[EXPLORE] Tuş hatası: {e}"); self.listen_active = False
        else:
            if self._hotkey_hook:
                try: keyboard.unhook(self._hotkey_hook)
                except: pass
            self._hotkey_hook = None
            self.listen_active = False
            self.macro.stop()
        self._safe_update_status()

    def on_hotkey_press(self, e):
        # Debounce (Tuş koruması)
        current = time.time()
        if current - self._last_toggle_time < 0.3: return
        self._last_toggle_time = current
        
        self.macro.toggle()
        self.update_signal.emit()

    def _safe_update_status(self):
        if not self.listen_active:
            self.lbl_status.setText("DURUM: PASİF"); self.btn_listen.setText("TUŞ DİNLEMEYİ BAŞLAT")
            act = False; self.apply_status_style("#ff5555")
        else:
            if self.macro.is_running:
                self.lbl_status.setText("DURUM: ÇALIŞIYOR"); self.apply_status_style("#00ff4c")
            else:
                self.lbl_status.setText("DURUM: BEKLİYOR"); self.apply_status_style("#ffff55")
            self.btn_listen.setText("TUŞ DİNLEMEYİ DURDUR"); act = True
        
        self.btn_listen.setProperty("active", act)
        self.btn_listen.style().unpolish(self.btn_listen); self.btn_listen.style().polish(self.btn_listen)

    def apply_status_style(self, color): self.lbl_status.setStyleSheet(f"color: {color}; font-weight: bold;")
