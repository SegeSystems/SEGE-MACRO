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

# PyQt5 - Gerekli tüm modüller buraya eklendi
from PyQt5.QtWidgets import (
    QDialog, QGridLayout, QLabel, QComboBox,
    QLineEdit, QPushButton, QDoubleSpinBox,
    QDialogButtonBox, QHBoxLayout, QVBoxLayout,
    QCheckBox, QGroupBox, QTabWidget, QWidget,
    QFrame, QSizePolicy, QSpinBox
)
from PyQt5.QtCore import Qt, pyqtSignal, QSize
from PyQt5.QtGui import QPixmap, QIcon

# Keyboard Driver (Varsa ClickSend, yoksa simülasyon)
try:
    from clicksend import KeyboardDriver as _ClicksendKeyboardDriver
except ImportError:
    _ClicksendKeyboardDriver = None


# ================================================================
# SCANCODE TABLOLARI
# ================================================================
DIGIT_SCANCODES = {
    1: 0x02, 2: 0x03, 3: 0x04, 4: 0x05, 5: 0x06,
    6: 0x07, 7: 0x08, 8: 0x09, 9: 0x0A, 0: 0x0B,
}
F_SCANCODES = {
    1: 0x3B, 2: 0x3C, 3: 0x3D, 4: 0x3E,
    5: 0x3F, 6: 0x40, 7: 0x41, 8: 0x42
}
SC_R = 0x13
SC_Z = 0x2C


def _send_key(scan_code: int, press_duration: float = 0.01):
    """
    Tuşu basar, 'press_duration' kadar bekler ve bırakır.
    """
    if scan_code is None:
        return

    if _ClicksendKeyboardDriver and not hasattr(_send_key, "_driver"):
        _send_key._driver = _ClicksendKeyboardDriver()

    if hasattr(_send_key, "_driver"):
        _send_key._driver.tusbas(scan_code, press_duration)
    else:
        # Driver yoksa time.sleep ile simüle et
        time.sleep(press_duration)

# ======================================================================
# HYBRID ASAS MACRO – ARDUINO LOGIC (AYARLANABİLİR)
# ======================================================================
class AsasHybridMacro:
    def __init__(self):
        self.running = False
        self.stop_event = threading.Event()

        # Varsayılanlar
        self.active_digits = [2, 3, 4, 5, 6]
        self.repeat_r = 56

        self.use_f_cycle = False
        self.f_list = []
        self.f_cycle_count = 1
        self.use_auto_z = False

        # --- GERİ GETİRİLEN VE DETAYLANDIRILAN ZAMANLAMALAR ---
        
        # Skill (Rakamlar) için zamanlamalar
        self.time_skill_press = 0.010  # Skill tuşuna basılı tutma süresi (Arduino: delay(10))
        self.time_skill_wait  = 0.000  # Skill bıraktıktan sonra bekleme (Arduino'da yoktu, opsiyonel)

        # R tuşu için zamanlamalar
        self.time_r_press = 0.010      # R tuşuna basılı tutma süresi (Arduino: delay(10))
        self.time_r_wait  = 0.005      # R bıraktıktan sonraki bekleme (Arduino: delay(5))

        # Genel döngü
        self.loop_delay = 0.001        # Tüm tur bittiğinde başa dönmeden önceki minik bekleme

        self.hotkey = "Z"

    def update_config(self, cfg):
        self.active_digits = cfg.get("digits", [2, 3, 4, 5, 6])
        self.repeat_r = cfg.get("repeat_r", 56)

        self.use_f_cycle = cfg.get("use_f", False)
        self.f_list = cfg.get("f_list", [])
        self.f_cycle_count = cfg.get("f_cycle_count", 1)
        self.use_auto_z = cfg.get("use_z", False)

        # Zamanlamaları Config'den al
        self.time_skill_press = cfg.get("time_skill_press", 0.010)
        self.time_skill_wait  = cfg.get("time_skill_wait", 0.000)
        
        self.time_r_press = cfg.get("time_r_press", 0.010)
        self.time_r_wait  = cfg.get("time_r_wait", 0.005)
        
        self.loop_delay   = cfg.get("loop_delay", 0.001)

        self.hotkey = cfg.get("hotkey", "Z")

    # --------------------------------------------------------------
    def start(self):
        if self.running:
            return
        self.running = True
        self.stop_event.clear()
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self.running = False
        self.stop_event.set()

    def toggle(self):
        if self.running:
            self.stop()
        else:
            self.start()

    # --------------------------------------------------------------
    # ÇEKİRDEK MANTIK
    # --------------------------------------------------------------
    def run_sequence(self):
        # 1. BÖLÜM: SKILLER
        for d in self.active_digits:
            if self.stop_event.is_set(): return
            
            sc = DIGIT_SCANCODES.get(d)
            # Tuşa bas (time_skill_press kadar tut)
            _send_key(sc, self.time_skill_press)
            
            # Eğer kullanıcı skill arası bekleme koyduysa bekle (Arduino'da 0)
            if self.time_skill_wait > 0:
                time.sleep(self.time_skill_wait)

        # 2. BÖLÜM: R DÖNGÜSÜ
        for _ in range(self.repeat_r):
            if self.stop_event.is_set(): return

            # R Bas (time_r_press kadar tut)
            _send_key(SC_R, self.time_r_press)
            
            # R arası bekleme (time_r_wait kadar bekle)
            if self.time_r_wait > 0:
                time.sleep(self.time_r_wait)

        # Opsiyonel: Auto Z
        if self.use_auto_z:
            _send_key(SC_Z, 0.01)

    # --------------------------------------------------------------
    def _loop(self):
        while not self.stop_event.is_set():

            if self.use_f_cycle and len(self.f_list) > 0:
                for f in self.f_list:
                    if self.stop_event.is_set(): break

                    # F tuşuna bas
                    sc = F_SCANCODES.get(f)
                    _send_key(sc, 0.01)
                    time.sleep(0.15) # F sonrası animasyon payı

                    for _ in range(self.f_cycle_count):
                        if self.stop_event.is_set(): break
                        self.run_sequence()
                        time.sleep(self.loop_delay)
            else:
                self.run_sequence()
                # Döngü sonu gecikmesi
                if self.loop_delay > 0:
                    time.sleep(self.loop_delay)

# ======================================================================
# SETTINGS DIALOG – GELİŞMİŞ AYARLAR GERİ GELDİ
# ======================================================================
class AsasSettingsDialog(QDialog):
    def __init__(self, parent, config):
        super().__init__(parent)
        self.setWindowTitle("ASAS PRO AYARLARI")
        self.setModal(True)

        self.config = config or {}
        self.capture_hotkey = False

        self.setStyleSheet("""
            QDialog, QWidget { background-color:#101010; color:white; }
            QGroupBox {
                border:1px solid #00e676;
                margin-top:12px;
                padding-top:12px;
                border-radius:6px;
                font-weight: bold;
            }
            QPushButton {
                background:#151515;
                border:1px solid #00e676;
                color:white;
                padding:5px;
                border-radius:4px;
            }
            QPushButton:hover { background:#00e676; color:black; }
            QDoubleSpinBox, QSpinBox {
                background:#151515;
                color:white;
                border:1px solid #00e676;
                padding: 2px;
            }
            QLabel { color: #cccccc; }
        """)

        lay = QVBoxLayout(self)
        
        # Eğer içerik çok uzun olursa taşmayı önlemek için ScrollArea eklenebilir
        # ama şimdilik direkt sıralıyoruz:

        # ------------------------------------------------------------
        # 1. DIGIT SEÇİMİ (BÜYÜK CHECKBOX'LAR)
        # ------------------------------------------------------------
        grp_digits = QGroupBox("Aktif Skill Slotları")
        g = QGridLayout(grp_digits)

        self.chk_digits = {}
        digits_cfg = self.config.get("digits", [2, 3, 4, 5, 6])

        # Yeni, büyük ve tıklanabilir QCheckBox stili
        LARGE_CHECKBOX_STYLE = """
            QCheckBox {
                spacing: 15px; /* Metin ile checkmark arası */
                padding: 10px; /* Tıklanabilir alanı artırır */
                font-size: 11pt;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 1px solid #00e676;
                border-radius: 3px;
                background-color: #222;
            }
            QCheckBox::indicator:checked {
                background-color: #00e676;
            }
        """

        row = 0; col = 0
        for d in range(10):
            cb = QCheckBox(str(d))
            cb.setStyleSheet(LARGE_CHECKBOX_STYLE) # Yeni stil
            cb.setChecked(d in digits_cfg)
            self.chk_digits[d] = cb
            g.addWidget(cb,row,col)
            col += 1
            if col == 5:
                col = 0
                row += 1

        lay.addWidget(grp_digits)

        # ------------------------------------------------------------
        # 2. ZAMANLAMA AYARLARI
        # ------------------------------------------------------------
        grp_time = QGroupBox("Zamanlama Ayarları (Saniye)")
        gt = QGridLayout(grp_time)

        # Skill Ayarları
        gt.addWidget(QLabel("Skill Basılı Tutma:"), 0, 0)
        self.spin_skill_press = QDoubleSpinBox()
        self.spin_skill_press.setRange(0.001, 1.0)
        self.spin_skill_press.setSingleStep(0.001)
        self.spin_skill_press.setDecimals(3)
        self.spin_skill_press.setValue(self.config.get("time_skill_press", 0.010))
        gt.addWidget(self.spin_skill_press, 0, 1)

        gt.addWidget(QLabel("Skill Arası Bekleme:"), 0, 2)
        self.spin_skill_wait = QDoubleSpinBox()
        self.spin_skill_wait.setRange(0.000, 1.0)
        self.spin_skill_wait.setSingleStep(0.001)
        self.spin_skill_wait.setDecimals(3)
        self.spin_skill_wait.setValue(self.config.get("time_skill_wait", 0.000))
        gt.addWidget(self.spin_skill_wait, 0, 3)

        # R Ayarları
        gt.addWidget(QLabel("R Basılı Tutma:"), 1, 0)
        self.spin_r_press = QDoubleSpinBox()
        self.spin_r_press.setRange(0.001, 1.0)
        self.spin_r_press.setSingleStep(0.001)
        self.spin_r_press.setDecimals(3)
        self.spin_r_press.setValue(self.config.get("time_r_press", 0.010))
        gt.addWidget(self.spin_r_press, 1, 1)

        gt.addWidget(QLabel("R Arası Bekleme:"), 1, 2)
        self.spin_r_wait = QDoubleSpinBox()
        self.spin_r_wait.setRange(0.000, 1.0)
        self.spin_r_wait.setSingleStep(0.001)
        self.spin_r_wait.setDecimals(3)
        self.spin_r_wait.setValue(self.config.get("time_r_wait", 0.005))
        gt.addWidget(self.spin_r_wait, 1, 3)
        
        # Döngü Ayarı
        gt.addWidget(QLabel("Tur Sonu Gecikme:"), 2, 0)
        self.spin_loop = QDoubleSpinBox()
        self.spin_loop.setRange(0.000, 2.0)
        self.spin_loop.setSingleStep(0.001)
        self.spin_loop.setDecimals(3)
        self.spin_loop.setValue(self.config.get("loop_delay", 0.001))
        gt.addWidget(self.spin_loop, 2, 1)

        lay.addWidget(grp_time)

        # ------------------------------------------------------------
        # 3. R TEKRAR & AUTO Z
        # ------------------------------------------------------------
        hbox = QHBoxLayout()
        
        grp_r = QGroupBox("R Tekrar")
        hr = QVBoxLayout(grp_r)
        self.spin_r_count = QSpinBox()
        self.spin_r_count.setRange(1, 500)
        self.spin_r_count.setValue(self.config.get("repeat_r", 56))
        hr.addWidget(self.spin_r_count)
        hbox.addWidget(grp_r)

        grp_z = QGroupBox("Ekstra")
        hz = QVBoxLayout(grp_z)
        self.chk_z = QCheckBox("Auto Z Bas")
        self.chk_z.setChecked(self.config.get("use_z", False))
        hz.addWidget(self.chk_z)
        hbox.addWidget(grp_z)

        lay.addLayout(hbox)

        # ------------------------------------------------------------
        # 4. F DESTEĞİ
        # ------------------------------------------------------------

        grp_f = QGroupBox("F Tuş Döngüsü")
        gf = QGridLayout(grp_f)

        self.chk_use_f = QCheckBox("Aktif")
        self.chk_use_f.setStyleSheet(LARGE_CHECKBOX_STYLE) # <<< STİL BURAYA DA UYGULANDI
        self.chk_use_f.setChecked(self.config.get("use_f", False))
        gf.addWidget(self.chk_use_f,0,0)

        self.chk_f_list = {}
        f_cfg = self.config.get("f_list", [])

        row=1; col=0
        for f in range(1,9):
            cb = QCheckBox(f"F{f}")
            cb.setStyleSheet(LARGE_CHECKBOX_STYLE) # <<< STİL BURAYA DA UYGULANDI
            cb.setChecked(f in f_cfg)
            self.chk_f_list[f] = cb
            gf.addWidget(cb,row,col)
            col += 1
            if col == 4:
                col = 0
                row += 1

        gf.addWidget(QLabel("Her F arası kaç tur:"), row, 0, 1, 2)
        self.spin_fcount = QSpinBox()
        self.spin_fcount.setRange(1,20)
        self.spin_fcount.setValue(self.config.get("f_cycle_count", 1))
        gf.addWidget(self.spin_fcount,row,2)

        lay.addWidget(grp_f)

        # ------------------------------------------------------------
        # HOTKEY
        # ------------------------------------------------------------
        grp_hot = QGroupBox("Başlatma Tuşu")
        hk = QHBoxLayout(grp_hot)
        self.txt_hotkey = QLineEdit(self.config.get("hotkey","Z"))
        self.txt_hotkey.setReadOnly(True)
        hk.addWidget(self.txt_hotkey)
        btn_cap = QPushButton("Tuş Ata")
        btn_cap.clicked.connect(self.start_capture)
        hk.addWidget(btn_cap)

        lay.addWidget(grp_hot)

        # --- TAB EKLEME KODU SİLİNDİ ---
        # tabs.addTab(tab,"GENEL AYARLAR")  <-- SİLİNDİ

        # Butonlar
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns) # main yerine lay'e ekledik

    # ============================================================
    def start_capture(self):
        self.capture_hotkey = True
        self.txt_hotkey.setText("...")

    def keyPressEvent(self, e):
        if self.capture_hotkey:
            key = e.text().upper()
            if key.strip():
                self.txt_hotkey.setText(key)
                self.capture_hotkey = False

    # ============================================================
    def accept(self):
        digits = [int(btn.text()) for d,btn in self.chk_digits.items() if btn.isChecked()] 
        f_list = [f for f,cb in self.chk_f_list.items() if cb.isChecked()]

        self.result_config = {
            "digits": digits,
            "repeat_r": self.spin_r_count.value(),
            "use_f": self.chk_use_f.isChecked(),
            "f_list": f_list,
            "f_cycle_count": self.spin_fcount.value(),
            "use_z": self.chk_z.isChecked(),
            
            # Zamanlamalar
            "time_skill_press": self.spin_skill_press.value(),
            "time_skill_wait":  self.spin_skill_wait.value(),
            "time_r_press":     self.spin_r_press.value(),
            "time_r_wait":      self.spin_r_wait.value(),
            "loop_delay":       self.spin_loop.value(),

            "hotkey": self.txt_hotkey.text(),
        }
        super().accept()

# ======================================================================
# ANA WIDGET (STYLING UYGULANMIŞ HALİ)
# ======================================================================
class AsasWidget(QFrame):
    update_signal = pyqtSignal()

    def __init__(self, parent=None, macro_instance=None, config=None):
        super().__init__(parent)

        self.macro = macro_instance or AsasHybridMacro()
        self.config = config or {}
        
        # Varsayılan konfigürasyon (Eğer boşsa)
        if not self.config:
            self.config = {
                "digits": [2, 3, 4, 5, 6],
                "repeat_r": 56,
                "time_skill_press": 0.010,
                "time_skill_wait": 0.000,
                "time_r_press": 0.010,
                "time_r_wait": 0.005,
                "loop_delay": 0.001,
                "hotkey": "Z"
            }
        
        self.macro.update_config(self.config)

        self.listen_active = False
        self.hotkey_hook = None
        self.last_press = 0

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

        # --- HEADER ---
        h = QHBoxLayout()
        h.setSpacing(2) # İkonlar arası boşluk
        
        # İkon listesi (Dosya isimleri icons klasöründe olmalı)
        icon_list = ["cp.png", "72.png", "spike.png", "75.png"]
        
        for icon_name in icon_list:
            lbl_icon = QLabel()
            lbl_icon.setFixedSize(25, 25)
            # Resim yükleme
            pix = QPixmap(f"icons/{icon_name}")
            if not pix.isNull():
                lbl_icon.setPixmap(pix.scaled(25, 25, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            h.addWidget(lbl_icon)

        h.addStretch(1) # Boşluk bırak (Yazıyı sağa yasla)
        
        lbl_title = QLabel("ASAS")
        lbl_title.setObjectName("MinorHeaderLabel") 
        h.addWidget(lbl_title)
        
        v.addLayout(h)

        # --- BUTON ---
        self.btn_listen = QPushButton("TUŞ DİNLEMEYİ BAŞLAT")
        self.btn_listen.setObjectName("ThreeFiveListenButton")
        self.btn_listen.setProperty("active", False)
        self.btn_listen.clicked.connect(self.toggle_listen)
        v.addWidget(self.btn_listen)

        # --- DURUM ---
        self.lbl_status = QLabel("DURUM: PASİF")
        self.lbl_status.setObjectName("MinorStatusLabel")
        v.addWidget(self.lbl_status)

        # --- ALT KISIM ---
        row = QHBoxLayout()
        row.setSpacing(4)
        row.addWidget(QLabel("AKTİF TUŞ:"))
        
        self.lbl_hotkey = QLabel(self.config.get("hotkey","Z"))
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
            if self.macro.running:
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
        import keyboard

        if not self.listen_active:
            key = self.config.get("hotkey","Z").lower()
            try:
                self.hotkey_hook = keyboard.on_press_key(key, self.on_hotkey)
                self.listen_active = True
            except Exception as e:
                print("Hata:", e)
                self.listen_active = False
        else:
            if self.hotkey_hook:
                import keyboard
                keyboard.unhook(self.hotkey_hook)
            self.listen_active = False
            self.macro.stop()

        self._safe_update_status()

    def on_hotkey(self, e):
        t = time.time()
        # Debounce
        if t - self.last_press < 0.2:
            return
        self.last_press = t
        self.macro.toggle()
        self.update_signal.emit()

    def open_settings(self):
        dlg = AsasSettingsDialog(self, self.config)
        if dlg.exec_():
            self.config.update(dlg.result_config)
            self.macro.update_config(self.config)
            self.lbl_hotkey.setText(self.config.get("hotkey","Z"))
            
            if self.listen_active:
                self.toggle_listen()
                self.toggle_listen()
