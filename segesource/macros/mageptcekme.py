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
import json
import os

# PyQt5
from PyQt5.QtWidgets import (
    QDialog, QGridLayout, QLabel, QComboBox, 
    QLineEdit, QPushButton, QDoubleSpinBox, 
    QDialogButtonBox, QHBoxLayout, QWidget,
    QFrame, QVBoxLayout, QSizePolicy, QMessageBox,
    QCheckBox, QGroupBox, QListWidget, QListWidgetItem
)
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtCore import Qt, QSize, pyqtSignal, QTimer

# Sürücüler
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

# Sabitler
F_SCANCODES = {1: 0x3B, 2: 0x3C, 3: 0x3D, 4: 0x3E, 5: 0x3F, 6: 0x40, 7: 0x41, 8: 0x42}
DIGIT_SCANCODES = {0: 0x0B, 1: 0x02, 2: 0x03, 3: 0x04, 4: 0x05, 5: 0x06, 6: 0x07, 7: 0x08, 8: 0x09, 9: 0x0A}

# =========================================================
# 1. LOGIC (MAKRO MOTORU)
# =========================================================
class MagePtCekmeMacro:
    def __init__(self):
        self.coords = [] # [(x, y), (x, y)...]
        
        # Ayarlar
        self.f_bar = 1
        self.digit = 1
        self.delay = 0.5 # Her TP arası bekleme
        
        self._driver = _ClicksendKeyboardDriver() if _ClicksendKeyboardDriver else None
        self._mouse = _ClicksendMouseDriver() if _ClicksendMouseDriver else None
        
        self._running = False
        self._lock = threading.Lock()

    def update_config(self, cfg):
        with self._lock:
            self.coords = cfg.get("coords", [])
            self.f_bar = cfg.get("f", 1)
            self.digit = cfg.get("d", 1)
            self.delay = cfg.get("delay", 0.5)

    @property
    def is_running(self): return self._running

    def run_sequence(self):
        """Kaydedilen koordinatları sırayla çeker"""
        if self._running: return # Zaten çalışıyorsa bekle
        
        if not self.coords:
            print("[MAGE TP] Koordinat listesi boş!")
            return

        with self._lock:
            self._running = True
            print(f"[MAGE TP] {len(self.coords)} kişi çekiliyor...")
            
            try:
                # Önce F sayfasına geç (Sadece 1 kere)
                if self.f_bar > 0:
                    sc_f = F_SCANCODES.get(self.f_bar)
                    if self._driver: self._driver.tusbas(sc_f, 0.02)
                    time.sleep(0.05)

                for (x, y) in self.coords:
                    # 1. Mouse ile Tıkla (Kişiyi Seç)
                    if self._mouse:
                        self._mouse.leftclick(0.05, int(x), int(y))
                    else:
                        pyautogui.click(x, y)
                    
                    time.sleep(0.1) # Seçim algılama süresi

                    # 2. Skill Bas
                    sc_d = DIGIT_SCANCODES.get(self.digit)
                    if self._driver: self._driver.tusbas(sc_d, 0.02)
                    
                    # 3. Bekle (Delay)
                    time.sleep(self.delay)

            except Exception as e:
                print(f"[MAGE TP HATA] {e}")
            finally:
                self._running = False
                print("[MAGE TP] İşlem bitti.")

# =========================================================
# 2. GUI - AYARLAR
# =========================================================
class MagePtCekmeSettingsDialog(QDialog):
    def __init__(self, parent, config):
        super().__init__(parent)
        self.setWindowTitle("SIRALI PT ÇEKME AYARLARI")
        self.setModal(True); self.resize(500, 500)
        self.config = config
        self.capture_active = False
        self.capture_hotkey = False
        self.hook_f = None
        
        self.temp_coords = self.config.get("coords", [])
        
        layout = QVBoxLayout(self)
        
        # 1. Hotkey
        h_key = QHBoxLayout()
        h_key.addWidget(QLabel("BAŞLATMA TUŞU:"))
        self.txt_hotkey = QLineEdit(self.config.get("hotkey", "G"))
        self.txt_hotkey.setReadOnly(True)
        btn_hk = QPushButton("TUŞ SEÇ"); btn_hk.clicked.connect(self.start_hotkey_capture)
        h_key.addWidget(self.txt_hotkey); h_key.addWidget(btn_hk)
        layout.addLayout(h_key)

        # 2. Skill Ayarları
        grp_skill = QGroupBox("Skill Ayarları")
        gs = QHBoxLayout(grp_skill)
        
        self.cmb_f = QComboBox(); self.cmb_f.addItem("F YOK", 0)
        for i in range(1, 9): self.cmb_f.addItem(f"F{i}", i)
        self.cmb_f.setCurrentIndex(self.cmb_f.findData(self.config.get("f", 1)))
        
        self.cmb_d = QComboBox()
        for i in range(10): self.cmb_d.addItem(str(i), i)
        self.cmb_d.setCurrentIndex(self.config.get("d", 1))
        
        self.sp_delay = QDoubleSpinBox(); self.sp_delay.setRange(0.1, 5.0); self.sp_delay.setSingleStep(0.1)
        self.sp_delay.setValue(self.config.get("delay", 0.5))
        
        gs.addWidget(QLabel("F Sayfası:")); gs.addWidget(self.cmb_f)
        gs.addWidget(QLabel("Tuş:")); gs.addWidget(self.cmb_d)
        gs.addWidget(QLabel("Gecikme (Sn):")); gs.addWidget(self.sp_delay)
        layout.addWidget(grp_skill)
        
        # 3. Koordinat Listesi
        grp_list = QGroupBox("Çekilecek Kişiler (Sırayla)")
        gl = QVBoxLayout(grp_list)
        
        self.list_widget = QListWidget()
        self.refresh_list()
        
        h_btns = QHBoxLayout()
        self.btn_add = QPushButton("KOORDİNAT EKLE (F Bas)"); self.btn_add.clicked.connect(self.toggle_coord_capture)
        self.btn_del = QPushButton("SEÇİLENİ SİL"); self.btn_del.clicked.connect(self.del_coord)
        self.btn_clr = QPushButton("TEMİZLE"); self.btn_clr.clicked.connect(self.clear_coords)
        
        h_btns.addWidget(self.btn_add); h_btns.addWidget(self.btn_del); h_btns.addWidget(self.btn_clr)
        
        gl.addWidget(self.list_widget)
        gl.addLayout(h_btns)
        layout.addWidget(grp_list)
        
        layout.addWidget(QLabel("BİLGİ: 'Koordinat Ekle' butonuna basıp, Party listesinde kişinin\nisminin üzerine gelip 'F' tuşuna basın.", styleSheet="color:#888; font-style:italic;"))

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        # F Hook
        if keyboard:
            try: self.hook_f = keyboard.on_press_key("F", self.on_f_press)
            except: pass

    def closeEvent(self, e):
        if keyboard and self.hook_f:
            try: keyboard.unhook(self.hook_f)
            except: pass
        super().closeEvent(e)

    def toggle_coord_capture(self):
        self.capture_active = not self.capture_active
        if self.capture_active:
            self.btn_add.setText("EKLEME MODU AKTİF (F Bas)...")
            self.btn_add.setStyleSheet("background-color: #00e676; color: black;")
        else:
            self.btn_add.setText("KOORDİNAT EKLE (F Bas)")
            self.btn_add.setStyleSheet("")

    def on_f_press(self, e):
        if self.capture_active:
            x, y = pyautogui.position()
            self.temp_coords.append((x, y))
            # Listeyi güvenli güncellemek için sinyal kullanılabilir ama dialog modal olduğu için
            # direct call genelde sorun çıkarmaz, yine de try-except
            try: self.list_widget.addItem(f"Kişi {self.list_widget.count()+1}: ({x}, {y})")
            except: pass

    def refresh_list(self):
        self.list_widget.clear()
        for i, (x, y) in enumerate(self.temp_coords):
            self.list_widget.addItem(f"Kişi {i+1}: ({x}, {y})")

    def del_coord(self):
        row = self.list_widget.currentRow()
        if row >= 0:
            self.temp_coords.pop(row)
            self.refresh_list()

    def clear_coords(self):
        self.temp_coords = []
        self.refresh_list()

    def start_hotkey_capture(self):
        self.capture_hotkey = True; self.txt_hotkey.setText("BAS..."); self.grabKeyboard()

    def keyPressEvent(self, e):
        if self.capture_hotkey:
            k = e.text().upper()
            if not k:
                if e.key() == Qt.Key_F1: k = "F1"
                # ...
            if k:
                self.txt_hotkey.setText(k); self.capture_hotkey = False; self.releaseKeyboard()
        else: super().keyPressEvent(e)

    def accept(self):
        self.config.update({
            "hotkey": self.txt_hotkey.text(),
            "f": self.cmb_f.currentData(),
            "d": int(self.cmb_d.currentText()),
            "delay": self.sp_delay.value(),
            "coords": self.temp_coords
        })
        super().accept()


# =========================================================
# 3. WIDGET (ANA KART)
# =========================================================
class MagePtCekmeWidget(QFrame):
    update_signal = pyqtSignal()

    def __init__(self, parent=None, macro_instance=None, config=None):
        super().__init__(parent)
        self.macro = macro_instance or MagePtCekmeMacro()
        self.config = config or {}
        self.macro.update_config(self.config)
        self.listen_active = False 
        self.update_signal.connect(self._update_status)
        self.setup_ui()
        self._update_status()

    def setup_ui(self):
        # STANDART BOYUT VE STİL (Diğerleriyle birebir aynı)
        self.setFrameShape(QFrame.Box)
        self.setMaximumWidth(260)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setStyleSheet("QFrame { background-color: #101010; border: 1px solid #444; border-radius: 4px; }")
        
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(4)

        # HEADER (👥 Emoji + tp.png + Başlık)
        h = QHBoxLayout()
        h.setSpacing(4)
        
        # 1. Mevcut Emoji
        icon_emoji = QLabel("👥")
        icon_emoji.setStyleSheet("font-size:16px; border:none; background:transparent;")
        h.addWidget(icon_emoji)
        
        # 2. tp.png İkonu
        import os
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(30, 30)
        self.icon_label.setAlignment(Qt.AlignCenter)
        
        icon_path = os.path.join("icons", "mage", "tp.png")
        pix = QPixmap(icon_path)
        if not pix.isNull():
            self.icon_label.setPixmap(pix.scaled(22, 22, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.icon_label.setText("👥") # png yoksa yedek
            self.icon_label.setStyleSheet("font-size:14px; border:none;")
        h.addWidget(self.icon_label)
        
        h.addStretch() # Başlığı sağa yasla
        
        title = QLabel("SIRALI PT ÇEKME")
        title.setObjectName("MinorHeaderLabel")
        h.addWidget(title)
        v.addLayout(h)

        # Dinleme Butonu
        self.btn_listen = QPushButton("TUŞ DİNLEMEYİ BAŞLAT")
        self.btn_listen.setObjectName("ThreeFiveListenButton")
        self.btn_listen.clicked.connect(self.toggle_listen)
        v.addWidget(self.btn_listen)

        # Durum Yazısı
        self.lbl_st = QLabel("DURUM: PASİF")
        self.lbl_st.setObjectName("MinorStatusLabel")
        v.addWidget(self.lbl_st)
        
        # FOOTER (Alt Satır - Diğerleriyle birebir aynı)
        row = QHBoxLayout()
        row.setSpacing(4)
        
        row.addWidget(QLabel("AKTİF TUŞ:"))
        
        self.lbl_hk = QLabel(self.config.get("hotkey", "G"))
        self.lbl_hk.setObjectName("HotkeyLabel")
        self.lbl_hk.setAlignment(Qt.AlignCenter)
        row.addWidget(self.lbl_hk)
        
        btn_set = QPushButton("⚙ AYARLAR")
        btn_set.setObjectName("MinorSettingsButton")
        btn_set.clicked.connect(self.settings)
        row.addWidget(btn_set)
        
        v.addLayout(row)

    def settings(self):
        dlg = MagePtCekmeSettingsDialog(self, self.config)
        if dlg.exec_():
            self.config = dlg.config
            self.macro.update_config(self.config)
            self.lbl_hk.setText(self.config.get("hotkey"))
            if self.listen_active: self.toggle_listen(); self.toggle_listen()

    def toggle_listen(self):
        if not keyboard: return QMessageBox.warning(self, "Hata", "Keyboard kütüphanesi eksik!")
        if not self.listen_active:
            hk = self.config.get("hotkey", "G").lower()
            try:
                self._hooks = []
                self._hooks.append(keyboard.on_press_key(hk, lambda e: self.on_hotkey(), suppress=False))
                self.listen_active = True
            except Exception as e:
                print(f"[PT CEKME] Hotkey hatası: {e}")
                self.listen_active = False
        else:
            if hasattr(self, '_hooks'):
                for h in self._hooks: 
                    try: keyboard.unhook(h)
                    except: pass
            self._hooks = []
            self.listen_active = False
        self._update_status()

    def on_hotkey(self):
        threading.Thread(target=self.macro.run_sequence, daemon=True).start()
        self.update_signal.emit()

    def _update_status(self):
        # Renkler ve metinler tüm mage modülleriyle eşlendi
        if not self.listen_active:
             self.lbl_st.setText("DURUM: PASİF")
             self.lbl_st.setStyleSheet("color:#ff5555; font-weight:bold;")
             self.btn_listen.setText("TUŞ DİNLEMEYİ BAŞLAT")
             self.btn_listen.setProperty("active", False)
        else:
            if self.macro.is_running:
                self.lbl_st.setText("DURUM: ÇEKİLİYOR...")
                self.lbl_st.setStyleSheet("color:#00ff4c; font-weight:bold;")
                self.btn_listen.setText("DURDUR")
            else:
                count = len(self.macro.coords)
                self.lbl_st.setText(f"DURUM: BEKLİYOR ({count} KİŞİ)")
                self.lbl_st.setStyleSheet("color:#ffff55; font-weight:bold;")
                self.btn_listen.setText("DURDUR")
            self.btn_listen.setProperty("active", True)
            
        self.btn_listen.style().unpolish(self.btn_listen)
        self.btn_listen.style().polish(self.btn_listen)

        # Durum değişimi durumunda periyodik kontrol (Eğer thread çalışıyorsa görseli güncellemek için)
        if self.listen_active and self.macro.is_running:
            QTimer.singleShot(200, self._update_status)
