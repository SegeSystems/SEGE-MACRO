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
import pyautogui # Ekran boyutunu almak için gerekli
from typing import Dict

from PyQt5.QtWidgets import (
    QDialog, QGridLayout, QLabel, QComboBox,
    QLineEdit, QPushButton, QDoubleSpinBox,
    QDialogButtonBox, QHBoxLayout, QWidget,
    QFrame, QVBoxLayout, QSizePolicy, QMessageBox,
    QCheckBox, QGroupBox, QScrollArea
)
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtCore import Qt, QSize, pyqtSignal


# ---------------------------------------------------------
# Opsiyonel clicksend / interception sürücüsü
# ---------------------------------------------------------
try:
    from clicksend import KeyboardDriver as _ClicksendKeyboardDriver
    from clicksend import MouseDriver as _ClicksendMouseDriver
except ImportError:
    _ClicksendKeyboardDriver = None
    _ClicksendMouseDriver = None

try:
    import keyboard
except ImportError:
    keyboard = None


# ---------------------------------------------------------
# SABİTLER VE AYARLAR
# ---------------------------------------------------------
DIGIT_SCANCODES = {
    0: 0x0B, 1: 0x02, 2: 0x03, 3: 0x04, 4: 0x05,
    5: 0x06, 6: 0x07, 7: 0x08, 8: 0x09, 9: 0x0A
}

F_SCANCODES = {
    1: 0x3B, 2: 0x3C, 3: 0x3D, 4: 0x3E,
    5: 0x3F, 6: 0x40, 7: 0x41, 8: 0x42
}

SKILL_LIST = [
    "Cure",
    "Debuff",
    "Malice",
    "Torment",
    "1920 Heal",
    "Party Heal",
    "10k Heal"
]

# İkon Dosya Yolları (icons klasörünün içinde olmalı)
SKILL_ICONS = {
    "Cure": "icons/priest/cure.png",
    "Debuff": "icons/priest/parazit.png",
    "Malice": "icons/priest/malice.png",
    "Torment": "icons/priest/torment.png",
    "1920 Heal": "icons/priest/45heal.png",
    "Party Heal": "icons/priest/party10k.png",
    "10k Heal": "icons/priest/tek10k.png"
}


# =========================================================
# 1. LOGIC (MAKRO MOTORU)
# =========================================================
class OtoPriestSkillerMacro:

    def __init__(self):
        self._driver = _ClicksendKeyboardDriver() if _ClicksendKeyboardDriver else None
        self._mouse = _ClicksendMouseDriver() if _ClicksendMouseDriver else None
        self._lock = threading.Lock()

        # Varsayılan konfigürasyon
        self.skills_config = {}
        for s in SKILL_LIST:
            self.skills_config[s] = {
                "enabled": False,
                "hotkey": "",
                "f_bar": 0,     # 0 = F Yok
                "digit": 1,
                "delay": 0.5
            }

    # -------------------------------------------------

    def update_config(self, cfg: Dict):
        with self._lock:
            if "skills" in cfg:
                for name, data in cfg["skills"].items():
                    if name in self.skills_config:
                        self.skills_config[name].update(data)

    # -------------------------------------------------

    def cast_skill(self, skill_name: str):
        """Tek seferlik skill basma"""
        if skill_name not in self.skills_config:
            return

        cfg = self.skills_config[skill_name]
        if not cfg["enabled"]:
            return

        # Aynı anda iki skill basılmasını önle
        if not self._lock.acquire(blocking=False):
            return

        try:
            print(f"[PRIEST] {skill_name} basılıyor")

            # 1. F Tuşu
            f_val = int(cfg["f_bar"])
            if f_val > 0:
                sc_f = F_SCANCODES.get(f_val)
                if sc_f:
                    self._send_key(sc_f, 0.02)
                    time.sleep(0.05)

            # 2. Digit Tuşu
            d_val = int(cfg["digit"])
            sc_d = DIGIT_SCANCODES.get(d_val)
            if sc_d:
                self._send_key(sc_d, 0.02)

            # --- TORMENT ÖZEL KODU ---
            if skill_name == "Torment":
                time.sleep(0.1) # Skill alanının açılması için minik bekleme
                self._click_center()
            # -------------------------

            # 3. Animasyon süresi
            wait_time = float(cfg["delay"])
            if wait_time > 0:
                time.sleep(wait_time)

        except Exception as e:
            print(f"[PRIEST] Hata: {e}")

        finally:
            self._lock.release()

    # -------------------------------------------------

    def _send_key(self, scancode: int, duration: float):
        if self._driver:
            self._driver.tusbas(scancode, duration)
        else:
            time.sleep(duration)

    def _click_center(self):
        """Ekranın ortasına sol tık atar (Torment için)"""
        try:
            screen_w, screen_h = pyautogui.size()
            center_x = int(screen_w / 2)
            center_y = int(screen_h / 2)
            
            if self._mouse:
                # Driver varsa
                self._mouse.leftclick(0.05, center_x, center_y)
            else:
                # Driver yoksa
                pyautogui.click(center_x, center_y)
                
            print(f"[PRIEST] Torment için ortaya tıklandı: {center_x},{center_y}")
        except Exception as e:
            print(f"[PRIEST] Mouse tıklama hatası: {e}")


class OtoPriestSkillerWidget(QFrame):
    update_signal = pyqtSignal()

    def __init__(self, parent=None, macro_instance=None, config=None):
        super().__init__(parent)
        self.macro = macro_instance or OtoPriestSkillerMacro()
        self.config = config or {}
        if "skills" in self.config: self.macro.update_config(self.config)

        self.listen_active = False
        self._hooks = []

        self.update_signal.connect(self._safe_update_status)
        self.setup_ui()
        self._safe_update_status()

    def setup_ui(self):
        # OtoExplore ile aynı çerçeve stili
        self.setFrameShape(QFrame.Box)
        self.setMaximumWidth(260)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setStyleSheet("QFrame { background-color: #101010; border: 1px solid #444444; border-radius: 4px; }")

        v = QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 6); v.setSpacing(4)

        # Üst Satır: İkonlar ve Başlık (Explore Stili)
        h_top = QHBoxLayout(); h_top.setSpacing(4)
        # Örnek 3 ikon gösterelim
        for icon_key in ["Cure", "Debuff", "Torment"]:
            lbl_i = QLabel(); lbl_i.setFixedSize(25, 25)
            pix = QPixmap(SKILL_ICONS[icon_key])
            if not pix.isNull():
                lbl_i.setPixmap(pix.scaled(25, 25, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            h_top.addWidget(lbl_i)
        
        h_top.addStretch(1)
        lbl_title = QLabel("OTO PRIEST SKILLER")
        lbl_title.setObjectName("MinorHeaderLabel") # CSS için önemli
        h_top.addWidget(lbl_title)
        v.addLayout(h_top)

        # Dinleme Butonu (ThreeFiveListenButton stilini kullanır)
        self.btn_listen = QPushButton("TUŞ DİNLEMEYİ BAŞLAT")
        self.btn_listen.setObjectName("ThreeFiveListenButton")
        self.btn_listen.setProperty("active", False)
        self.btn_listen.clicked.connect(self.toggle_listen)
        v.addWidget(self.btn_listen)

        # Durum Etiketi
        self.lbl_status = QLabel("DURUM: PASİF")
        self.lbl_status.setObjectName("MinorStatusLabel")
        v.addWidget(self.lbl_status)

        # Ayarlar Butonu (Explore gibi alt satırda)
        h_bot = QHBoxLayout()
        h_bot.addStretch()
        btn_set = QPushButton("⚙ AYARLARI DÜZENLE")
        btn_set.setObjectName("MinorSettingsButton")
        btn_set.clicked.connect(self.open_settings)
        h_bot.addWidget(btn_set)
        v.addLayout(h_bot)

    def open_settings(self):
        dlg = OtoPriestSkillerSettingsDialog(self, self.config)
        if dlg.exec_() == QDialog.Accepted:
            self.config = dlg.config
            self.macro.update_config(self.config)
            if self.listen_active:
                self.toggle_listen(); self.toggle_listen()

    def toggle_listen(self):
        if not keyboard: return QMessageBox.warning(self, "Hata", "keyboard yok")
        if not self.listen_active:
            reg = 0
            for name, cfg in self.config.get("skills", {}).items():
                if cfg.get("enabled") and cfg.get("hotkey"):
                    try:
                        h = keyboard.on_press_key(cfg["hotkey"].lower(), 
                             lambda e, n=name: threading.Thread(target=self.macro.cast_skill, args=(n,), daemon=True).start())
                        self._hooks.append(h)
                        reg += 1
                    except: pass
            if reg == 0: return QMessageBox.warning(self, "Uyarı", "Aktif skill yok.")
            self.listen_active = True
        else:
            for h in self._hooks: 
                try: keyboard.unhook(h)
                except: pass
            self._hooks = []
            self.listen_active = False
        self._safe_update_status()

    def _safe_update_status(self):
        if self.listen_active:
            self.lbl_status.setText("DURUM: AKTİF (DİNLİYOR)")
            self.lbl_status.setStyleSheet("color:#00ff4c; font-weight:bold;")
            self.btn_listen.setText("TUŞ DİNLEMEYİ DURDUR")
            self.btn_listen.setProperty("active", True)
        else:
            self.lbl_status.setText("DURUM: PASİF")
            self.lbl_status.setStyleSheet("color:#ff5555; font-weight:bold;")
            self.btn_listen.setText("TUŞ DİNLEMEYİ BAŞLAT")
            self.btn_listen.setProperty("active", False)
        
        self.btn_listen.style().unpolish(self.btn_listen); self.btn_listen.style().polish(self.btn_listen)

# =========================================================
# 2. GUI (AYAR PENCERESİ)
# =========================================================
class OtoPriestSkillerSettingsDialog(QDialog):
    def __init__(self, parent=None, current_config=None):
        super().__init__(parent)
        self.setWindowTitle("PRIEST SKILL AYARLARI")
        self.setModal(True)
        self.resize(700, 500)
        self.setStyleSheet("background-color: #121212; color: white;")

        self.config = current_config if current_config else {"skills": {}}
        self.ui_elements = {}
        self._capture_target = None

        main_layout = QVBoxLayout(self)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background-color: #121212;")

        content = QWidget()
        grid = QGridLayout(content)
        grid.setSpacing(10)

        # Başlıklar
        headers = ["", "SKILL ADI", "AKTİF", "TETİK TUŞU", "OYUN TUŞU", "F SAYFASI", "SÜRE (SN)"]
        for i, h in enumerate(headers):
            lbl = QLabel(h)
            lbl.setStyleSheet("color:#00e676; font-weight:bold; font-size: 10px;")
            grid.addWidget(lbl, 0, i)

        for idx, skill in enumerate(SKILL_LIST, 1):
            data = self.config["skills"].get(skill, {"enabled": False, "hotkey": "", "digit": 1, "f_bar": 0, "delay": 0.5})

            # İkon
            lbl_icon = QLabel()
            pix = QPixmap(SKILL_ICONS.get(skill, ""))
            if not pix.isNull():
                lbl_icon.setPixmap(pix.scaled(28, 28, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            grid.addWidget(lbl_icon, idx, 0)

            # İsim
            grid.addWidget(QLabel(skill), idx, 1)

            # Checkbox
            chk = QCheckBox()
            chk.setChecked(data["enabled"])
            grid.addWidget(chk, idx, 2)

            # Tetik Tuşu
            hk_edit = QLineEdit(data["hotkey"])
            hk_edit.setReadOnly(True); hk_edit.setFixedWidth(60); hk_edit.setAlignment(Qt.AlignCenter)
            btn_cap = QPushButton("SEÇ"); btn_cap.setFixedWidth(40)
            btn_cap.clicked.connect(lambda _, s=skill, e=hk_edit: self.start_capture(s, e))
            
            hk_lay = QHBoxLayout()
            hk_lay.addWidget(hk_edit); hk_lay.addWidget(btn_cap); hk_lay.setContentsMargins(0,0,0,0)
            hk_w = QWidget(); hk_w.setLayout(hk_lay)
            grid.addWidget(hk_w, idx, 3)

            # Oyun Tuşu
            cmb_d = QComboBox()
            for i in range(10): cmb_d.addItem(str(i), i)
            cmb_d.setCurrentIndex(int(data["digit"]))
            grid.addWidget(cmb_d, idx, 4)

            # F Sayfası
            cmb_f = QComboBox()
            cmb_f.addItem("F YOK", 0)
            for i in range(1, 9): cmb_f.addItem(f"F{i}", i)
            cmb_f.setCurrentIndex(cmb_f.findData(int(data["f_bar"])))
            grid.addWidget(cmb_f, idx, 5)

            # Delay
            sp = QDoubleSpinBox(); sp.setRange(0.0, 5.0); sp.setSingleStep(0.1); sp.setValue(float(data["delay"]))
            grid.addWidget(sp, idx, 6)

            self.ui_elements[skill] = {"chk": chk, "hk": hk_edit, "digit": cmb_d, "f": cmb_f, "delay": sp}

        scroll.setWidget(content)
        main_layout.addWidget(scroll)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        main_layout.addWidget(btns)

    def start_capture(self, skill_name, edit_widget):
        self._capture_target = (skill_name, edit_widget)
        edit_widget.setText("...")
        self.grabKeyboard()

    def keyPressEvent(self, event):
        if self._capture_target:
            key = event.key()
            text = ""
            if key == Qt.Key_Escape: text = "ESC"
            elif Qt.Key_F1 <= key <= Qt.Key_F12: text = f"F{key - Qt.Key_F1 + 1}"
            elif key == Qt.Key_Space: text = "SPACE"
            else:
                t = event.text().upper()
                if t: text = t
            if text:
                self._capture_target[1].setText(text)
                self._capture_target = None
                self.releaseKeyboard()
            return
        super().keyPressEvent(event)

    def accept(self):
        for name, ui in self.ui_elements.items():
            self.config["skills"][name] = {
                "enabled": ui["chk"].isChecked(), "hotkey": ui["hk"].text(),
                "digit": ui["digit"].currentData(), "f_bar": ui["f"].currentData(),
                "delay": ui["delay"].value()
            }
        super().accept()

# =========================================================
# 3. ANA WIDGET (OTO EXPLORE TASARIMININ AYNISI)
# =========================================================
class OtoPriestSkillerSettingsDialog(QDialog):
    def __init__(self, parent=None, current_config=None):
        super().__init__(parent)
        self.setWindowTitle("PRIEST SKILL AYARLARI")
        self.setModal(True)
        self.setFixedSize(620, 420) # Pencere boyutunu sabitledik, daha toplu durur
        self.setStyleSheet("""
            QDialog { background-color: #121212; }
            QLabel { color: white; font-family: 'Segoe UI'; font-size: 11px; }
            QLineEdit { background: #1a1a1a; border: 1px solid #333; color: #00ff4c; padding: 2px; }
            QComboBox { background: #1a1a1a; border: 1px solid #333; color: white; padding: 1px; }
            QDoubleSpinBox { background: #1a1a1a; border: 1px solid #333; color: white; }
            QPushButton { background: #252525; color: white; border: 1px solid #444; padding: 3px; }
            QPushButton:hover { background: #333; }
            QCheckBox::indicator { width: 15px; height: 15px; }
        """)

        self.config = current_config if current_config else {"skills": {}}
        self.ui_elements = {}
        self._capture_target = None

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 10, 15, 10)
        main_layout.setSpacing(10)

        # Üst Başlık Row (Basit ve İnce)
        header_widget = QWidget()
        header_grid = QGridLayout(header_widget)
        header_grid.setContentsMargins(0, 0, 0, 0)
        
        headers = [
            ("", 35), ("SKILL ADI", 100), ("AKTİF", 40), 
            ("TETİK TUŞU", 110), ("OYUN TUŞU", 70), 
            ("F SAYFASI", 80), ("SÜRE(SN)", 60)
        ]

        for i, (text, width) in enumerate(headers):
            lbl = QLabel(text)
            lbl.setFixedWidth(width)
            lbl.setStyleSheet("color: #00e676; font-weight: bold; font-size: 10px; border-bottom: 1px solid #333; padding-bottom: 5px;")
            header_grid.addWidget(lbl, 0, i)
        
        main_layout.addWidget(header_widget)

        # Scroll Area (Skiller için)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        content = QWidget()
        grid = QGridLayout(content)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setVerticalSpacing(8)

        for idx, skill in enumerate(SKILL_LIST):
            data = self.config["skills"].get(skill, {"enabled": False, "hotkey": "", "digit": 1, "f_bar": 0, "delay": 0.5})

            # 0. İkon
            lbl_icon = QLabel()
            pix = QPixmap(SKILL_ICONS.get(skill, ""))
            if not pix.isNull():
                lbl_icon.setPixmap(pix.scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            grid.addWidget(lbl_icon, idx, 0)

            # 1. İsim
            name_lbl = QLabel(skill)
            name_lbl.setFixedWidth(100)
            grid.addWidget(name_lbl, idx, 1)

            # 2. Aktif (Checkbox)
            chk = QCheckBox()
            chk.setChecked(data["enabled"])
            grid.addWidget(chk, idx, 2, Qt.AlignCenter)

            # 3. Tetik Tuşu (Edit + Seç Butonu)
            hk_edit = QLineEdit(data["hotkey"])
            hk_edit.setReadOnly(True)
            hk_edit.setFixedWidth(50)
            hk_edit.setAlignment(Qt.AlignCenter)
            
            btn_cap = QPushButton("SEÇ")
            btn_cap.setFixedWidth(40)
            btn_cap.clicked.connect(lambda _, s=skill, e=hk_edit: self.start_capture(s, e))
            
            hk_lay = QHBoxLayout()
            hk_lay.setContentsMargins(0,0,0,0)
            hk_lay.setSpacing(2)
            hk_lay.addWidget(hk_edit)
            hk_lay.addWidget(btn_cap)
            hk_w = QWidget(); hk_w.setLayout(hk_lay); hk_w.setFixedWidth(110)
            grid.addWidget(hk_w, idx, 3)

            # 4. Oyun Tuşu
            cmb_d = QComboBox()
            cmb_d.setFixedWidth(60)
            for i in range(10): cmb_d.addItem(str(i), i)
            cmb_d.setCurrentIndex(int(data["digit"]))
            grid.addWidget(cmb_d, idx, 4)

            # 5. F Sayfası
            cmb_f = QComboBox()
            cmb_f.setFixedWidth(75)
            cmb_f.addItem("F YOK", 0)
            for i in range(1, 9): cmb_f.addItem(f"F{i}", i)
            cmb_f.setCurrentIndex(cmb_f.findData(int(data["f_bar"])))
            grid.addWidget(cmb_f, idx, 5)

            # 6. Süre
            sp = QDoubleSpinBox()
            sp.setFixedWidth(55)
            sp.setRange(0.0, 5.0); sp.setSingleStep(0.1); sp.setValue(float(data["delay"]))
            grid.addWidget(sp, idx, 6)

            self.ui_elements[skill] = {"chk": chk, "hk": hk_edit, "digit": cmb_d, "f": cmb_f, "delay": sp}

        scroll.setWidget(content)
        main_layout.addWidget(scroll)

        # Alt Butonlar
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.setStyleSheet("QPushButton { width: 60px; height: 20px; }")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        main_layout.addWidget(btns)

    def start_capture(self, skill_name, edit_widget):
        self._capture_target = (skill_name, edit_widget)
        edit_widget.setText("BAS...")
        edit_widget.setStyleSheet("border: 1px solid #00ff4c; background: #102010;")
        self.grabKeyboard()

    def keyPressEvent(self, event):
        if self._capture_target:
            key = event.key()
            text = ""
            if key == Qt.Key_Escape: text = "ESC"
            elif Qt.Key_F1 <= key <= Qt.Key_F12: text = f"F{key - Qt.Key_F1 + 1}"
            elif key == Qt.Key_Space: text = "SPACE"
            elif key == Qt.Key_CapsLock: text = "CAPS"
            else:
                t = event.text().upper()
                if t: text = t
            if text:
                skill_name, widget = self._capture_target
                widget.setText(text)
                widget.setStyleSheet("background: #1a1a1a; border: 1px solid #333; color: #00ff4c;")
                self._capture_target = None
                self.releaseKeyboard()
            return
        super().keyPressEvent(event)

    def accept(self):
        for name, ui in self.ui_elements.items():
            self.config["skills"][name] = {
                "enabled": ui["chk"].isChecked(),
                "hotkey": ui["hk"].text(),
                "digit": ui["digit"].currentData(),
                "f_bar": ui["f"].currentData(),
                "delay": ui["delay"].value()
            }
        super().accept()
