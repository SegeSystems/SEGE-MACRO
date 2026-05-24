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
import ctypes

from PyQt5.QtWidgets import (
    QDialog, QGridLayout, QLabel, QComboBox, 
    QLineEdit, QPushButton, QDoubleSpinBox, 
    QDialogButtonBox, QHBoxLayout, QWidget,
    QFrame, QVBoxLayout, QSizePolicy, QMessageBox,
    QCheckBox, QGroupBox, QSpinBox, QApplication
)
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtCore import Qt, QSize, pyqtSignal, QTimer

import pyautogui

try:
    import keyboard
except ImportError:
    keyboard = None

# ---------------------------------------------------------
# SÜRÜCÜLER
# ---------------------------------------------------------
try:
    from clicksend import KeyboardDriver as _ClicksendKeyboardDriver
    from clicksend import MouseDriver as _ClicksendMouseDriver
    HAS_DRIVERS = True
except ImportError:
    _ClicksendKeyboardDriver = None
    _ClicksendMouseDriver = None
    HAS_DRIVERS = False

# ---------------------------------------------------------
# SABİTLER VE AYAR DOSYASI
# ---------------------------------------------------------
CONFIG_FILE = "priest_goat_config.json"
SC_R = 0x13
SC_I = 0x17 # Inventory Key
DIGIT_SCANCODES = {
    0: 0x0B, 1: 0x02, 2: 0x03, 3: 0x04, 4: 0x05,
    5: 0x06, 6: 0x07, 7: 0x08, 8: 0x09, 9: 0x0A
}

# =========================================================
# 1. LOGIC (MOTOR)
# =========================================================
class PriestGoatLogic:
    def __init__(self):
        # Varsayılan Ayarlar
        self.default_config = {
            "hotkey": "F",         
            "attack_key": 2,       
            "hp_key": 1,           
            "mana_key": 3,         
            
            "kitap_enabled": False,
            "kitap_key": 8,
            "kitap_delay": 180.0,
            
            "kol_enabled": False,
            "kol_key": 9,
            "kol_delay": 180.0,
            
            "inv_coords": [0, 0],  
            "mouse_return": False, 
            "inv_auto_open": False, # Otomatik I basma
            
            "other_skill_delay": 0.65,   
            "manual_attack_delay": 0.20, 
            
            "r_speed": 0.02,
            "skill_speed": 0.05,
        }
        
        self.config = self._load_config()

        self._driver = _ClicksendKeyboardDriver() if _ClicksendKeyboardDriver else None
        self._mouse = _ClicksendMouseDriver() if _ClicksendMouseDriver else None
        
        self._running = False
        self._stop_event = threading.Event()
        self._pause_event = threading.Event() 
        self._pause_event.set() 

        self.is_weapon_equipped = False 
        self._passive_lock = threading.Lock() 
        self._interrupt_lock = threading.Lock() 

    # --- AYAR YÖNETİMİ ---
    def _load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    data = json.load(f)
                    for k, v in self.default_config.items():
                        if k not in data: data[k] = v
                    return data
            except:
                return self.default_config.copy()
        return self.default_config.copy()

    def save_config_to_file(self):
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(self.config, f, indent=4)
        except Exception as e: print(f"Kayıt Hatası: {e}")

    def update_config(self, cfg):
        self.config.update(cfg)
        self.save_config_to_file()

    # --- TEMEL EYLEMLER ---
    def _press_key(self, key_digit):
        sc = DIGIT_SCANCODES.get(int(key_digit))
        if sc:
            if self._driver: self._driver.tusbas(sc, 0.03)
            else: pyautogui.press(str(key_digit))

    def _press_i(self):
        if self._driver: self._driver.tusbas(SC_I, 0.05)
        else: pyautogui.press("i")

    def _perform_click(self, x, y):
        if x == 0 and y == 0: return
        if self._mouse:
            self._mouse.rightclick(0.04, int(x), int(y))
        else:
            pyautogui.moveTo(x, y)
            pyautogui.rightClick()

    # --- SWAP (TAK/ÇIKAR) ---
    def _perform_swap_action(self, to_weapon=True, force=False):
        coords = self.config["inv_coords"]
        if coords[0] == 0 and coords[1] == 0: return

        if not force:
            if to_weapon and self.is_weapon_equipped: return
            if not to_weapon and not self.is_weapon_equipped: return

        try:
            start_x, start_y = pyautogui.position()

            # 1. Envanter Aç (I)
            if self.config["inv_auto_open"]:
                self._press_i()
                time.sleep(0.20) 

            # 2. Tıkla (Swap)
            self._perform_click(coords[0], coords[1])
            
            # 3. Envanter Kapat (I)
            if self.config["inv_auto_open"]:
                time.sleep(0.10)
                self._press_i()

            # 4. Mouse Geri Dön
            if self.config["mouse_return"]:
                if self._mouse and hasattr(self._mouse, 'move'):
                    try: self._mouse.move(int(start_x), int(start_y))
                    except: pyautogui.moveTo(start_x, start_y)
                else:
                    pyautogui.moveTo(start_x, start_y)

            self.is_weapon_equipped = to_weapon
            
        except Exception as e:
            print(f"Swap Hatası: {e}")
        
        time.sleep(0.15) 

    # --- MOD YÖNETİMİ ---
    def start_goat_mode(self):
        if self._running: return
        print("[GOAT] Mod Başladı")
        self._running = True
        self._stop_event.clear()
        self._pause_event.set()

        threading.Thread(target=self._initial_equip, daemon=True).start()
        
        threading.Thread(target=self._attack_loop, daemon=True).start()
        threading.Thread(target=self._timer_loop, daemon=True).start()

    def _initial_equip(self):
        self._perform_swap_action(to_weapon=True)

    def stop_goat_mode(self):
        if not self._running: return
        print("[GOAT] Mod Durdu")
        self._running = False
        self._stop_event.set()
        self._pause_event.set()
        
        threading.Thread(target=lambda: self._perform_swap_action(to_weapon=False), daemon=True).start()

    # --- PASİF MOD (MANUEL VURMA - KESİN ÇÖZÜM) ---
    def handle_passive_attack_key(self):
        if self._running: return 
        if not self._passive_lock.acquire(blocking=False): return

        try:
            coords = self.config["inv_coords"]
            if coords[0] == 0 and coords[1] == 0: return

            delay = self.config.get("manual_attack_delay", 0.20)
            start_x, start_y = pyautogui.position()

            # 1. I BAS (AÇ)
            if self.config["inv_auto_open"]:
                self._press_i()
                time.sleep(0.20) # Menü açılışını bekle

            # 2. SAĞ TIK (SİLAH TAK)
            self._perform_click(coords[0], coords[1])
            time.sleep(delay)

            # 3. SKILL VUR
            self._press_key(self.config["attack_key"])
            time.sleep(delay)

            # 4. SAĞ TIK (KALKAN TAK)
            self._perform_click(coords[0], coords[1])
            time.sleep(0.10) # Tıklamanın algılanması için

            # 5. I BAS (KAPAT)
            if self.config["inv_auto_open"]:
                self._press_i()

            # 6. MOUSE GERİ DÖN
            if self.config["mouse_return"]:
                if self._mouse and hasattr(self._mouse, 'move'):
                    try: self._mouse.move(int(start_x), int(start_y))
                    except: pyautogui.moveTo(start_x, start_y)
                else:
                    pyautogui.moveTo(start_x, start_y)

        except Exception as e:
            print(f"Pasif Mod Hatası: {e}")
        finally:
            self._passive_lock.release()

    # --- AKTİF MOD: SKILL SIKIŞTIRMA ---
    def trigger_interrupt_skill(self, key_digit):
        if not self._running: return 
        if not self._interrupt_lock.acquire(blocking=False): return 

        try:
            self._pause_event.clear() 
            time.sleep(0.15) 

            self._perform_swap_action(to_weapon=False)
            
            self._press_key(key_digit)

            delay = self.config["other_skill_delay"]
            start_time = time.time()
            while time.time() - start_time < delay:
                if keyboard.is_pressed('w') or keyboard.is_pressed('s'): break 
                time.sleep(0.01)

            self._perform_swap_action(to_weapon=True)

            self._pause_event.set()

        except Exception as e:
            print(f"Interrupt Hatası: {e}")
        finally:
            self._interrupt_lock.release()

    # --- DÖNGÜLER ---
    def _attack_loop(self):
        while not self._stop_event.is_set():
            self._pause_event.wait() 
            if self._stop_event.is_set(): break

            try:
                if not self.is_weapon_equipped:
                    self._perform_swap_action(to_weapon=True)

                sc_skill = DIGIT_SCANCODES.get(int(self.config["attack_key"]))
                if self._driver and sc_skill:
                    self._driver.tusbas(sc_skill, self.config["skill_speed"])
                else:
                    pyautogui.press(str(self.config["attack_key"]))
                    time.sleep(self.config["skill_speed"])
                
                if self._driver:
                    self._driver.tusbas(SC_R, self.config["r_speed"])
                    self._driver.tusbas(SC_R, self.config["r_speed"])
                else:
                    pyautogui.press('r'); time.sleep(self.config["r_speed"])
                    pyautogui.press('r')
                
                time.sleep(0.05)
            except: time.sleep(1)

    def _timer_loop(self):
        last_kitap = 0
        last_kol = 0
        while not self._stop_event.is_set():
            self._pause_event.wait()
            now = time.time()

            if self.config["kitap_enabled"] and (now - last_kitap > self.config["kitap_delay"]):
                self._press_key(self.config["kitap_key"])
                last_kitap = now
                time.sleep(0.2)

            if self.config["kol_enabled"] and (now - last_kol > self.config["kol_delay"]):
                self._press_key(self.config["kol_key"])
                last_kol = now
                time.sleep(0.2)
            
            time.sleep(0.5)

# =========================================================
# 2. GUI (AYARLAR)
# =========================================================
class PriestGoatSettings(QDialog):
    def __init__(self, parent, logic_instance):
        super().__init__(parent)
        self.setWindowTitle("PRIEST GOAT AYARLARI")
        self.setModal(True)
        self.resize(350, 650)
        self.logic = logic_instance
        self.config = self.logic.config.copy()
        
        self.capture_active = False 
        self.hotkey_capture = False 

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10,10,10,10)

        # --- GRUP 1: TUŞLAR ---
        grp_genel = QGroupBox("1. TEMEL TUŞLAR")
        gl = QGridLayout(grp_genel)

        gl.addWidget(QLabel("Başlatma Tuşu:"), 0, 0)
        self.edit_hotkey = QLineEdit(self.config.get("hotkey", "F"))
        self.edit_hotkey.setReadOnly(True)
        btn_hk = QPushButton("SEÇ")
        btn_hk.clicked.connect(self.start_hotkey_capture)
        h_hk = QHBoxLayout(); h_hk.addWidget(self.edit_hotkey); h_hk.addWidget(btn_hk)
        gl.addLayout(h_hk, 0, 1)

        gl.addWidget(QLabel("Atak Skilli:"), 1, 0)
        self.cmb_attack = self._create_key_combo(self.config["attack_key"])
        gl.addWidget(self.cmb_attack, 1, 1)

        gl.addWidget(QLabel("HP Pot:"), 2, 0)
        self.cmb_hp = self._create_key_combo(self.config["hp_key"])
        gl.addWidget(self.cmb_hp, 2, 1)

        gl.addWidget(QLabel("Mana Pot:"), 3, 0)
        self.cmb_mana = self._create_key_combo(self.config["mana_key"])
        gl.addWidget(self.cmb_mana, 3, 1)

        layout.addWidget(grp_genel)

        # --- GRUP 2: BUFFLAR ---
        grp_buff = QGroupBox("2. OTO BUFF")
        gb = QGridLayout(grp_buff)

        self.chk_kitap = QCheckBox("Kitap"); self.chk_kitap.setChecked(self.config["kitap_enabled"])
        self.cmb_kitap = self._create_key_combo(self.config["kitap_key"])
        self.sp_kitap = QDoubleSpinBox(); self.sp_kitap.setRange(1, 999); self.sp_kitap.setValue(self.config["kitap_delay"])
        gb.addWidget(self.chk_kitap, 0, 0); gb.addWidget(self.cmb_kitap, 0, 1); gb.addWidget(self.sp_kitap, 0, 2)

        self.chk_kol = QCheckBox("Kol"); self.chk_kol.setChecked(self.config["kol_enabled"])
        self.cmb_kol = self._create_key_combo(self.config["kol_key"])
        self.sp_kol = QDoubleSpinBox(); self.sp_kol.setRange(1, 999); self.sp_kol.setValue(self.config["kol_delay"])
        gb.addWidget(self.chk_kol, 1, 0); gb.addWidget(self.cmb_kol, 1, 1); gb.addWidget(self.sp_kol, 1, 2)

        layout.addWidget(grp_buff)

        # --- GRUP 3: ENVANTER ---
        grp_inv = QGroupBox("3. ENVANTER & SİLAH")
        gi = QGridLayout(grp_inv)

        self.lbl_coord = QLineEdit(f"{self.config['inv_coords'][0]}, {self.config['inv_coords'][1]}")
        self.lbl_coord.setReadOnly(True)
        btn_cap = QPushButton("SİLAH YERİ SEÇ (F)")
        btn_cap.clicked.connect(self.start_coord_capture)
        
        gi.addWidget(QLabel("Koordinat:"), 0, 0)
        gi.addWidget(self.lbl_coord, 0, 1)
        gi.addWidget(btn_cap, 1, 0, 1, 2)

        self.chk_inv_auto = QCheckBox("Envanteri Otomatik Aç/Kapa (I)")
        self.chk_inv_auto.setChecked(self.config.get("inv_auto_open", False))
        gi.addWidget(self.chk_inv_auto, 2, 0, 1, 2)

        self.chk_mouse = QCheckBox("Mouse Geri Dönsün")
        self.chk_mouse.setChecked(self.config["mouse_return"])
        gi.addWidget(self.chk_mouse, 3, 0, 1, 2)

        layout.addWidget(grp_inv)

        # --- GRUP 4: DİĞER ---
        grp_oth = QGroupBox("4. DİĞER AYARLAR")
        go = QGridLayout(grp_oth)
        
        go.addWidget(QLabel("Ara Skill Bekleme (sn):"), 0, 0)
        self.sp_oth = QDoubleSpinBox(); self.sp_oth.setRange(0.1, 5.0); self.sp_oth.setValue(self.config["other_skill_delay"])
        go.addWidget(self.sp_oth, 0, 1)

        go.addWidget(QLabel("Manuel Vurma Bekleme (sn):"), 1, 0)
        self.sp_manual = QDoubleSpinBox(); self.sp_manual.setRange(0.01, 2.0); self.sp_manual.setSingleStep(0.01)
        self.sp_manual.setValue(self.config.get("manual_attack_delay", 0.20))
        go.addWidget(self.sp_manual, 1, 1)

        layout.addWidget(grp_oth)

        # Butonlar
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.save_config)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        if keyboard:
            try: keyboard.on_press_key("f", self.on_f_press, suppress=False)
            except: pass

    def _create_key_combo(self, val):
        cb = QComboBox()
        for i in range(10): cb.addItem(str(i), i)
        cb.setCurrentIndex(int(val))
        return cb

    def start_hotkey_capture(self):
        self.hotkey_capture = True
        self.edit_hotkey.setText("BAS...")

    def keyPressEvent(self, e):
        if self.hotkey_capture:
            k = e.text().upper()
            if not k and e.key() == Qt.Key_F1: k = "F1" 
            if k:
                self.edit_hotkey.setText(k)
                self.hotkey_capture = False
        else:
            super().keyPressEvent(e)

    def start_coord_capture(self):
        self.capture_active = True
        self.lbl_coord.setText("Inventory'e Gelip F Bas...")

    def on_f_press(self, e):
        if self.capture_active:
            x, y = pyautogui.position()
            self.config["inv_coords"] = [x, y]
            self.lbl_coord.setText(f"{x}, {y}")
            self.capture_active = False

    def save_config(self):
        self.config["hotkey"] = self.edit_hotkey.text()
        self.config["attack_key"] = self.cmb_attack.currentData()
        self.config["hp_key"] = self.cmb_hp.currentData()
        self.config["mana_key"] = self.cmb_mana.currentData()
        
        self.config["kitap_enabled"] = self.chk_kitap.isChecked()
        self.config["kitap_key"] = self.cmb_kitap.currentData()
        self.config["kitap_delay"] = self.sp_kitap.value()
        
        self.config["kol_enabled"] = self.chk_kol.isChecked()
        self.config["kol_key"] = self.cmb_kol.currentData()
        self.config["kol_delay"] = self.sp_kol.value()
        
        self.config["mouse_return"] = self.chk_mouse.isChecked()
        self.config["inv_auto_open"] = self.chk_inv_auto.isChecked()
        
        self.config["other_skill_delay"] = self.sp_oth.value()
        self.config["manual_attack_delay"] = self.sp_manual.value()
        
        self.logic.update_config(self.config)
        self.accept()

    def closeEvent(self, event):
        if keyboard: keyboard.unhook_all()
        event.accept()

# =========================================================
# 3. ANA WIDGET
# =========================================================
class PriestGoatWidget(QFrame):
    update_signal = pyqtSignal()

    def __init__(self, parent=None, macro_instance=None, config=None):
        super().__init__(parent)
        self.logic = macro_instance or PriestGoatLogic()
        if config: self.logic.update_config(config)
        self.listen_active = False
        self._hooks = []
        self.update_signal.connect(self._safe_update_status)
        self.setup_ui()
        self._safe_update_status()

    def setup_ui(self):
        self.setFrameShape(QFrame.Box)
        self.setMaximumWidth(260)
        self.setStyleSheet("QFrame { background-color: #101010; border: 1px solid #444; border-radius: 4px; }")
        
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(4)

        # Header
        h_head = QHBoxLayout()
        icon_lbl = QLabel()
        icon_lbl.setFixedSize(25, 25)
        icon_path = "icons/priest/pri62.png" 
        if os.path.exists(icon_path):
            pix = QPixmap(icon_path)
            icon_lbl.setPixmap(pix.scaled(25, 25, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            icon_lbl.setText("🐐")
            icon_lbl.setStyleSheet("border:none; font-size: 18px;")
        h_head.addWidget(icon_lbl); h_head.addStretch()
        title = QLabel("PRIEST GOAT"); title.setObjectName("MinorHeaderLabel"); h_head.addWidget(title)
        v.addLayout(h_head)

        self.btn_listen = QPushButton("TUŞ DİNLEMEYİ BAŞLAT")
        self.btn_listen.setObjectName("ThreeFiveListenButton")
        self.btn_listen.clicked.connect(self.toggle_listen)
        v.addWidget(self.btn_listen)

        self.lbl_status = QLabel("DURUM: PASİF"); self.lbl_status.setObjectName("MinorStatusLabel"); v.addWidget(self.lbl_status)

        row = QHBoxLayout(); row.setSpacing(4)
        row.addWidget(QLabel("TUŞ:"))
        self.lbl_hotkey = QLabel(self.logic.config.get("hotkey", "F"))
        self.lbl_hotkey.setObjectName("HotkeyLabel"); self.lbl_hotkey.setAlignment(Qt.AlignCenter)
        row.addWidget(self.lbl_hotkey)
        btn_set = QPushButton("⚙ AYARLAR"); btn_set.setObjectName("MinorSettingsButton")
        btn_set.clicked.connect(self.open_settings)
        row.addWidget(btn_set)
        v.addLayout(row)

    def open_settings(self):
        dlg = PriestGoatSettings(self, self.logic)
        if dlg.exec_():
            self.lbl_hotkey.setText(self.logic.config["hotkey"])
            if self.listen_active: self.toggle_listen(); self.toggle_listen()

    def toggle_listen(self):
        if not keyboard: return
        if not self.listen_active:
            try:
                hk = self.logic.config["hotkey"].lower()
                h1 = keyboard.on_press_key(hk, self.on_trigger_press)
                self._hooks.append(h1)
                for i in range(10):
                    h = keyboard.on_press_key(str(i), lambda e, k=i: self.on_digit_press(k))
                    self._hooks.append(h)
                self.listen_active = True
            except: self.listen_active = False
        else:
            for h in self._hooks: 
                try: keyboard.unhook(h)
                except: pass
            self._hooks = []
            self.listen_active = False
            self.logic.stop_goat_mode()
        self._safe_update_status()

    def on_trigger_press(self, e):
        if self.logic._running: self.logic.stop_goat_mode()
        else: self.logic.start_goat_mode()
        self.update_signal.emit()

    def on_digit_press(self, k):
        cfg = self.logic.config
        specials = [cfg["attack_key"], cfg["hp_key"], cfg["mana_key"], cfg["kitap_key"], cfg["kol_key"]]
        
        # Pasif Mod
        if k in specials:
            if not self.logic._running and k == cfg["attack_key"]:
                threading.Thread(target=self.logic.handle_passive_attack_key, daemon=True).start()
            return

        # Aktif Mod (Interrupt)
        if self.logic._running:
            threading.Thread(target=self.logic.trigger_interrupt_skill, args=(k,), daemon=True).start()

    def apply_status_style(self, color):
        self.lbl_status.setStyleSheet(f"color: {color}; font-weight: bold;")

    def _safe_update_status(self):
        if not self.listen_active:
            self.lbl_status.setText("DURUM: PASİF")
            self.apply_status_style("#ff5555")
            self.btn_listen.setText("TUŞ DİNLEMEYİ BAŞLAT")
            self.btn_listen.setProperty("active", False)
        else:
            if self.logic._running:
                self.lbl_status.setText("ÇALIŞIYOR (GOAT)")
                self.apply_status_style("#00ff4c")
            else:
                self.lbl_status.setText("BEKLİYOR")
                self.apply_status_style("#ffff55")
            self.btn_listen.setText("TUŞ DİNLEMEYİ DURDUR")
            self.btn_listen.setProperty("active", True)
        
        self.btn_listen.style().unpolish(self.btn_listen)
        self.btn_listen.style().polish(self.btn_listen)

if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    w = PriestGoatWidget()
    w.show()
    sys.exit(app.exec_())
