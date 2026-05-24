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

# --- wari_silme.py --- (Nihai Düzeltilmiş Sürüm)

import threading
import time
import os
import cv2
import numpy as np
import mss
import pyautogui
import json

# PyQt5
from PyQt5.QtWidgets import (
    QDialog, QGridLayout, QLabel, QComboBox, 
    QLineEdit, QPushButton, QDoubleSpinBox, 
    QDialogButtonBox, QHBoxLayout, QWidget,
    QFrame, QVBoxLayout, QSizePolicy, QMessageBox,
    QCheckBox, QGroupBox
)
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtCore import Qt, QSize, pyqtSignal, QTimer

# Opsiyonel Sürücü
try:
    from clicksend import KeyboardDriver as _ClicksendKeyboardDriver
    from clicksend import MouseDriver as _ClicksendMouseDriver
except ImportError:
    _ClicksendKeyboardDriver = None
    _ClicksendMouseDriver = None

# Harici Kütüphane
try:
    import keyboard
except ImportError:
    keyboard = None

# Tuş Kodları
SC_I = 0x17 # I (Inventory)

# Rakam Scancode'ları
DIGIT_SCANCODES = {
    '1': 0x02, '2': 0x03, '3': 0x04, '4': 0x05, '5': 0x06,
    '6': 0x07, '7': 0x08, '8': 0x09, '9': 0x0A, '0': 0x0B
}
DIGIT_MAP_REVERSE = {v: k for k, v in DIGIT_SCANCODES.items()}

# Tarama Alanı Dosyası
BUFF_REGION_FILE = "BUFF_ALANI.json"

# ---------------------------------------------------------
# 1. LOGIC (MAKRO MOTORU)
# ---------------------------------------------------------
class WarriorSilmeMacro:
    def __init__(self):
        self.key = "F9"
        self.retry_key = "6" 
        self.shield_coords = (0, 0)
        self.mode = "Mod 2"
        self.click_duration = 0.15
        
        # SÜRÜCÜLER (Hata veren _driver yerine doğru isimler)
        self.kb = _ClicksendKeyboardDriver() if _ClicksendKeyboardDriver else None
        self.mouse = _ClicksendMouseDriver() if _ClicksendMouseDriver else None
        
        self._running = False
        self._stop_event = threading.Event()
        self._sct = mss.mss()
        self._lock = threading.Lock()
        
        self.region = {'top': 60, 'left': 400, 'width': 1515, 'height': 850}
        self._mod3_shield_equipped = False
        
        self._load_region()

    def update_config(self, cfg):
        with self._lock:
            self.key = cfg.get("key", "F9")
            self.retry_key = cfg.get("retry_key", "6")
            self.shield_coords = cfg.get("shield_coords", (0, 0))
            self.mode = cfg.get("mode", "Mod 2")
            self.click_duration = cfg.get("click_duration", 0.15)
            # Diğer ayarlar
            self.inv_open_mode = cfg.get("inv_open_mode", False)
            self.return_mouse = cfg.get("return_mouse", False)
            self.inv_delay = cfg.get("inv_delay", 0.25)

            self._load_region()

    @property
    def is_running(self): return self._running

    def toggle(self):
        if not self._running: self.start()
        else: self.stop()

    def start(self):
        if not self._running:
            self._load_region()
            self._stop_event.clear()
            self._running = True
            self._mod3_shield_equipped = False
            
            # MOD SEÇİMİNE GÖRE BAŞLAT
            if "Mod 3" in self.mode:
                threading.Thread(target=self._loop_mod3, daemon=True).start()
            else:
                threading.Thread(target=self._logic_oneshot, daemon=True).start() 

    def stop(self):
        self._stop_event.set()
        self._running = False
        self._mod3_shield_equipped = False

    # --- YARDIMCILAR ---
    def _get_kilic_template(self):
        kilic_path = os.path.join("icons/wari", 'kilic.png')
        if os.path.exists(kilic_path):
            return cv2.imread(kilic_path)
        return None

    def _click_target(self, match_loc, shape):
        """
        Çalışan kod mantığıyla güncellenmiş Tıklama Fonksiyonu.
        Araya bekleme süreleri ekleyerek çift tıklamayı garantiye alır.
        """
        h, w = shape[:2]
        cx = self.region['left'] + match_loc[0] + w // 2
        cy = self.region['top'] + match_loc[1] + h // 2
        
        ox, oy = pyautogui.position()
        
        # 1. Hedefe Git
        if self.mouse:
            # Sürücü varsa (ClickSend vb.) - Genelde kendi move fonksiyonu olmaz, direct click atar
            # Ama garanti olsun diye önce pyautoguyi ile götürebiliriz veya direkt driver click
            pass 
        else:
            pyautogui.moveTo(cx, cy)
        
        # 2. Çift Tıklama Mantığı (Araya Sleep Eklenmiş Hali)
        if self.mouse:
            # Sürücü ile
            self.mouse.leftclick(0.05, cx, cy)
            time.sleep(0.05) # <-- ÖNEMLİ BEKLEME
            self.mouse.leftclick(0.05, cx, cy)
        else:
            # Normal Mouse ile
            pyautogui.click()
            time.sleep(0.05) # <-- ÇALIŞAN KODDAKİ GİBİ BEKLEME
            pyautogui.click()
        
        # 3. Mouse Geri Dön (Eğer ayar açıksa)
        if self.return_mouse: 
            pyautogui.moveTo(ox, oy)

    def _equip_shield_only(self):
        if self.shield_coords == (0, 0): return
        ox, oy = pyautogui.position()
        
        # Envanter Aç
        if not self.inv_open_mode: 
            self._tap_scan(SC_I, 0.05)
            time.sleep(self.inv_delay)
        
        # Git ve Sağ Tıkla
        sx, sy = self.shield_coords
        if self.mouse:
             self.mouse.rightclick(self.click_duration, sx, sy)
        else:
             pyautogui.moveTo(sx, sy)
             pyautogui.rightClick()
             time.sleep(self.click_duration)
        
        # Envanter Kapat
        if not self.inv_open_mode: 
            self._tap_scan(SC_I, 0.05)
        
        # Mouse Geri Dön
        if self.return_mouse:
            pyautogui.moveTo(ox, oy)

    def _tap_scan(self, scancode, delay):
        # DÜZELTME: self._driver yerine self.kb (Klavye Driver)
        if self.kb:
            self.kb.tusbas(scancode, delay)
        else:
            if scancode == SC_I: pyautogui.press('i')
            else:
                key = DIGIT_MAP_REVERSE.get(scancode)
                if key: pyautogui.press(key)
            time.sleep(delay)

    def _load_region(self):
        """Tarama alanını BUFF_ALANI.json dosyasından okur."""
        if os.path.isfile(BUFF_REGION_FILE):
            try:
                with open(BUFF_REGION_FILE, "r") as f:
                    d = json.load(f)
                    self.region = {
                        "left": int(d["x"]), "top": int(d["y"]), 
                        "width": int(d["w"]), "height": int(d["h"])
                    }
            except: 
                # Hata olursa varsayılan alan kullanılır
                pass

    # ---------------------------------------------------------
    # TEK SEFERLİK MODLAR (MOD 1, MOD 2) – DÜZELTİLMİŞ
    # ---------------------------------------------------------
    def _logic_oneshot(self):
        try:
            # --- KILIÇ TEMPLATE ---
            img_kilic = self._get_kilic_template()
            if img_kilic is None:
                print("[SILME] HATA: Kılıç ikonu yüklenemedi!")
                return

            # --- MOD 2: ÖNCE KALKAN TAK ---
            if "Mod 2" in self.mode:
                self._equip_shield_only()
                time.sleep(0.3)

            # --- EKRAN GÖRÜNTÜSÜ AL ---
            with mss.mss() as sct:
                scr = np.array(sct.grab(self.region))
                scr = cv2.cvtColor(scr, cv2.COLOR_BGRA2BGR)

            # --- KILIÇ ARA (MOD 3 İLE AYNI) ---
            res = cv2.matchTemplate(scr, img_kilic, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)

            if max_val > 0.85:
                print(f"[SILME] Kılıç Bulundu -> Siliniyor ({self.mode})")
                self._click_target(max_loc, img_kilic.shape)
            else:
                print(f"[SILME] Kılıç Bulunamadı ({self.mode})")

        except Exception as e:
            print(f"[SILME] Hata (OneShot): {e}")
        finally:
            self._running = False

    # ---------------------------------------------------------
    # MOD 3: DÖNGÜSEL ÇALIŞMA (Orijinal Mantık)
    # ---------------------------------------------------------
    def _loop_mod3(self):
        """Mod 3: Debuff Varsa Kalkan/Sil, Yoksa Retry/Geri Tak (Döngüsel)"""
        print("[SILME] Mod 3 Başladı (Otomatik Döngü - Debuff Takibi)")
        
        # --- İKON YÜKLEME VE YEREL TANIMLAMALAR ---
        base_dir = "icons/wari"
        
        # YEREL DEĞİŞKENLER BURADA TANIMLANIYOR
        img_kilic = self._get_kilic_template()
        debuff_img_names = ['torment.png', 'parazit.png', 'malice.png', 'super.png']
        debuff_imgs = [cv2.imread(os.path.join(base_dir, n)) for n in debuff_img_names if os.path.exists(os.path.join(base_dir, n))]
        debuff_imgs = [img for img in debuff_imgs if img is not None] # None olanları filtrele

        if img_kilic is None:
            print("[SILME] HATA: Kılıç ikonu yüklenemedi!")
            self._running = False; return
        if not debuff_imgs:
            print("[SILME] HATA: Debuff ikonları yüklenemedi!")
            self._running = False; return
        # ------------------------------------------

        with mss.mss() as sct:
            while not self._stop_event.is_set():
                try:
                    scr = np.array(sct.grab(self.region))
                    scr = cv2.cvtColor(scr, cv2.COLOR_BGRA2BGR)
                    
                    # 1. DEBUFF KONTROLÜ
                    debuff_detected = False
                    for tmpl in debuff_imgs:
                        res = cv2.matchTemplate(scr, tmpl, cv2.TM_CCOEFF_NORMED)
                        if np.max(res) > 0.8:
                            debuff_detected = True
                            break
                            
                    # Kılıç Konumunu Bul
                    res_kilic = cv2.matchTemplate(scr, img_kilic, cv2.TM_CCOEFF_NORMED)
                    _, max_val_kilic, _, max_loc_kilic = cv2.minMaxLoc(res_kilic) 

                    # 2. MANTIK AKIŞI
                    if debuff_detected:
                        if not self._mod3_shield_equipped:
                            # Debuff geldi -> Kalkan Tak + Sil
                            self._equip_shield_only()
                            time.sleep(0.1)
                            
                            if max_val_kilic > 0.85:
                                self._click_target(max_loc_kilic, img_kilic.shape)

                            self._mod3_shield_equipped = True
                        
                    else:
                        if self._mod3_shield_equipped:
                            # Debuff gitti -> Retry Tuşu + Silahı Geri Tak
                            sc_retry = DIGIT_SCANCODES.get(self.retry_key)
                            
                            if self.kb and sc_retry:
                                self.kb.tusbas(sc_retry, 0.05)
                            else:
                                pyautogui.press(self.retry_key)
                            
                            self._equip_shield_only() 
                            
                            self._mod3_shield_equipped = False

                    time.sleep(0.05)
                except Exception as e:
                    print(f"[SILME] Döngü Hatası: {e}")
                    time.sleep(1)
        
        self._running = False

# ---------------------------------------------------------
# 2. GUI (AYAR PENCERESİ - STYX TARZI)
# ---------------------------------------------------------
class WarriorSilmeSettings(QDialog):
    def __init__(self, parent=None, current_config=None):
        super().__init__(parent)
        self.setWindowTitle("SİLME AYARLARI")
        self.setModal(True)
        self.result_config = None
        
        self.capture_active = False
        self.hotkey_capture_mode = False
        self.hook_f = None
        
        if current_config is None: current_config = {}
        
        self.coords = current_config.get("shield_coords", (0, 0))
        self.temp_coords = list(self.coords)
        
        key = current_config.get("key", "F9")
        mode = current_config.get("mode", "Mod 2")
        retry_key = current_config.get("retry_key", "6")

        inv_mode = current_config.get("inv_open_mode", False)
        mouse_mode = current_config.get("return_mouse", False)
        inv_delay = float(current_config.get("inv_delay", 0.25))
        click_dur = float(current_config.get("click_duration", 0.15))

        layout = QGridLayout(self)

        # 0. Satır: Aktif Tuş
        layout.addWidget(QLabel("AKTIF TUS:"), 0, 0)
        self.txt_hotkey = QLineEdit(key)
        self.txt_hotkey.setReadOnly(True)
        btn_key = QPushButton("TUŞ SEÇ")
        btn_key.clicked.connect(self.start_hotkey_capture)
        h = QHBoxLayout(); h.addWidget(self.txt_hotkey); h.addWidget(btn_key)
        layout.addLayout(h, 0, 1)

        # 1. Satır: Mod Seçimi
        layout.addWidget(QLabel("MOD SEÇİMİ:"), 1, 0)
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItems([
            "Mod 1: Sadece Kılıç Sil", 
            "Mod 2: Kalkan Tak + Sil (Tek)",
            "Mod 3: Kalkan + Sil (Toggle + Retry)"
        ])
        
        # Seçili modu ayarla
        if "Mod 1" in mode: self.cmb_mode.setCurrentIndex(0)
        elif "Mod 3" in mode: self.cmb_mode.setCurrentIndex(2)
        else: self.cmb_mode.setCurrentIndex(1)
        layout.addWidget(self.cmb_mode, 1, 1)

        # 2. Satır: Retry Tuşu
        layout.addWidget(QLabel("RETRY TUŞU (MOD 3):"), 2, 0)
        self.cmb_retry = QComboBox()
        self.cmb_retry.addItems([str(i) for i in range(10)]) # 0-9
        self.cmb_retry.setCurrentText(retry_key)
        layout.addWidget(self.cmb_retry, 2, 1)

        # 3. Satır: Kalkan Koordinatı
        layout.addWidget(QLabel("KALKAN KOOR.:"), 3, 0)
        self.lbl_coord_val = QLineEdit(f"{self.temp_coords[0]}, {self.temp_coords[1]}") # <<< DEĞİŞTİ
        self.lbl_coord_val.setReadOnly(True)
        self.lbl_coord_val.setStyleSheet("background: #222; color: #00e676; border: 1px solid #444;")
        btn_coord = QPushButton("YAKALA (F)") # <<< METİN DEĞİŞTİ
        btn_coord.clicked.connect(self.start_coord_capture)
        c_lay = QHBoxLayout(); c_lay.addWidget(self.lbl_coord_val); c_lay.addWidget(btn_coord)
        layout.addLayout(c_lay, 3, 1)

        # Bilgi
        lbl_info = QLabel("Bilgi: Mouse'u kalkan üstüne getirip 'F' tuşuna basın.")
        lbl_info.setStyleSheet("color: #888; font-size: 8pt; font-style: italic;")
        layout.addWidget(lbl_info, 4, 0, 1, 2)
        
        # --- YENİ BÖLÜM: KALKAN/ENVANTER AYARLARI ---
        grp_inv = QGroupBox("Kalkan/Envanter Ayarları")
        g_inv = QGridLayout(grp_inv)

        # 1. Çanta Zaten Açık
        self.chk_inv_mode = QCheckBox("Çanta Zaten Açık (I Basma)")
        self.chk_inv_mode.setChecked(inv_mode)
        g_inv.addWidget(self.chk_inv_mode, 0, 0)
        
        # 2. Mouse Geri Dön
        self.chk_mouse_return = QCheckBox("Mouse Geri Dönsün")
        self.chk_mouse_return.setChecked(mouse_mode)
        g_inv.addWidget(self.chk_mouse_return, 0, 1)

        # 3. Envanter Açılış Gecikmesi
        g_inv.addWidget(QLabel("Envanter Gecikmesi (sn):"), 1, 0)
        self.spin_inv_delay = QDoubleSpinBox()
        self.spin_inv_delay.setRange(0.05, 1.0); self.spin_inv_delay.setSingleStep(0.01)
        self.spin_inv_delay.setValue(inv_delay)
        g_inv.addWidget(self.spin_inv_delay, 1, 1)

        # 4. Tıklama Süresi
        g_inv.addWidget(QLabel("Sağ Tık Basılı Süresi (sn):"), 2, 0)
        self.spin_click_dur = QDoubleSpinBox()
        self.spin_click_dur.setRange(0.01, 1.0); self.spin_click_dur.setSingleStep(0.01)
        self.spin_click_dur.setValue(click_dur)
        g_inv.addWidget(self.spin_click_dur, 2, 1)
        
        layout.addWidget(grp_inv, 5, 0, 1, 2)

        # Butonlar
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.save_and_close)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns, 6, 0, 1, 2)

        # Hook
        if keyboard:
            try: self.hook_f = keyboard.on_press_key("F", self.on_f_press)
            except: self.hook_f = None

    def closeEvent(self, event):
        if keyboard and hasattr(self, 'hook_f') and self.hook_f: 
            try: keyboard.unhook(self.hook_f)
            except: pass
        super().closeEvent(event)

    def start_coord_capture(self):
        self.capture_active = True
        self.lbl_coord_val.setText("F Bas...")

    def on_f_press(self, e):
        # BU KISIM wari_kalkan.py İLE AYNI HALE GETİRİLDİ
        if self.capture_active:
            x, y = pyautogui.position()
            self.temp_coords = [x, y]
            
            # QTimer ve import kaldırıldı, doğrudan yazdırılıyor
            self.lbl_coord_val.setText(f"{x}, {y}")
            
            self.capture_active = False

    def start_hotkey_capture(self):
        self.hotkey_capture_mode = True
        self.txt_hotkey.setText("...")

    def keyPressEvent(self, e):
        if hasattr(self, 'hotkey_capture_mode') and self.hotkey_capture_mode:
            key_text = None
            if e.key() == Qt.Key_F1: key_text = "F1"
            elif e.key() == Qt.Key_CapsLock: key_text = "CAPSLOCK"
            else:
                t = e.text()
                if t: key_text = t.upper()
            if key_text:
                self.txt_hotkey.setText(key_text)
                self.hotkey_capture_mode = False
        else:
            super().keyPressEvent(e)

    def save_and_close(self):
        self.result_config = {
            "key": self.txt_hotkey.text(),
            "mode": self.cmb_mode.currentText(),
            "retry_key": self.cmb_retry.currentText(),
            "shield_coords": tuple(self.temp_coords),
            # YENİ KAYITLAR
            "inv_open_mode": self.chk_inv_mode.isChecked(),
            "return_mouse": self.chk_mouse_return.isChecked(),
            "inv_delay": self.spin_inv_delay.value(),
            "click_duration": self.spin_click_dur.value()
        }
        self.accept()


# ---------------------------------------------------------
# 3. WIDGET (ANA EKRAN KARTI)
# ---------------------------------------------------------
class WarriorSilmeWidget(QFrame):
    update_signal = pyqtSignal()
    
    def __init__(self, parent=None, macro_instance=None, config=None):
        super().__init__(parent)
        self.macro = macro_instance
        self.config = config or {}
        self.listen_active = False
        self._hooks = []
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
        v.setContentsMargins(6,6,6,6)
        v.setSpacing(4)

        h = QHBoxLayout(); h.setSpacing(4)
        for icon_name in ["kilic.png", "kalkan1.png"]:
            icon_lbl = QLabel(); icon_lbl.setFixedSize(25, 25)
            pix = QPixmap(f"icons/wari/{icon_name}")
            if not pix.isNull():
                icon_lbl.setPixmap(pix.scaled(25, 25, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            h.addWidget(icon_lbl)

        lbl = QLabel("DEBUFF SİLME"); lbl.setObjectName("MinorHeaderLabel") 
        h.addStretch(); h.addWidget(lbl); v.addLayout(h)

        self.btn_listen = QPushButton("TUŞ DİNLEMEYİ BAŞLAT")
        self.btn_listen.setObjectName("ThreeFiveListenButton")
        self.btn_listen.setProperty("active", False)
        self.btn_listen.clicked.connect(self.toggle_listen)
        v.addWidget(self.btn_listen)

        self.lbl_status = QLabel("DURUM: PASİF"); self.lbl_status.setObjectName("MinorStatusLabel")
        v.addWidget(self.lbl_status)

        row = QHBoxLayout(); row.setSpacing(4); row.addWidget(QLabel("AKTIF TUŞ:"))
        self.lbl_key = QLabel(self.config.get("key", "F9")); self.lbl_key.setObjectName("HotkeyLabel")
        row.addWidget(self.lbl_key)

        btn_set = QPushButton("⚙ AYARLAR")
        btn_set.setObjectName("MinorSettingsButton")
        btn_set.setFlat(True)
        btn_set.setIcon(QIcon("icons/gear.png"))
        btn_set.clicked.connect(self.open_settings)
        row.addWidget(btn_set); v.addLayout(row)

    def open_settings(self):
        d = WarriorSilmeSettings(self, self.config)
        if d.exec_():
            self.config.update(d.result_config)
            self.macro.update_config(self.config)
            self.lbl_key.setText(self.config["key"])
            if self.listen_active: self.toggle_listen(); self.toggle_listen()

    def toggle_listen(self):
        if keyboard is None:
            return QMessageBox.warning(self, "Hata", "'keyboard' kütüphanesi eksik.")

        if not self.listen_active:
            try:
                k = self.config.get("key", "F9").lower()
                self._hooks.append(keyboard.on_press_key(k, lambda e: self.macro.toggle()))
                self.listen_active = True
                print(f"[SILME] Dinleniyor: {k}")
            except Exception as e:
                print(f"[SILME] Hata: {e}")
                self.listen_active = False
        else:
            for h in self._hooks: keyboard.unhook(h)
            self._hooks = []
            self.listen_active = False
            self.macro.stop()
        self._safe_update_status()
    

    def apply_status_style(self, color: str):
        self.lbl_status.setStyleSheet(f"color: {color}; font-weight: bold;")

    def _safe_update_status(self):
        if not self.listen_active:
            self.lbl_status.setText("DURUM: PASİF")
            self.btn_listen.setText("TUŞ DİNLEMEYİ BAŞLAT")
            self.apply_status_style("#ff5555")
            active = False
        else:
            if self.macro.is_running:
                self.lbl_status.setText("DURUM: ÇALIŞIYOR")
                self.apply_status_style("#00ff4c")
            else:
                self.lbl_status.setText("DURUM: BEKLİYOR")
                self.apply_status_style("#ffff55")

            self.btn_listen.setText("TUŞ DİNLEMEYİ DURDUR")
            active = True
        
        self.btn_listen.setProperty("active", active)
        self.btn_listen.style().unpolish(self.btn_listen)
        self.btn_listen.style().polish(self.btn_listen)
        
        if self.listen_active:
            QTimer.singleShot(200, self._safe_update_status)
