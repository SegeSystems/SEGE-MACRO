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
import cv2
import numpy as np
import mss
import pyautogui
from PyQt5.QtWidgets import (
    QDialog, QGridLayout, QLabel, QComboBox, 
    QLineEdit, QPushButton, QDoubleSpinBox, 
    QDialogButtonBox, QHBoxLayout, QWidget,
    QFrame, QVBoxLayout, QSizePolicy, QMessageBox,
    QCheckBox, QGroupBox, QScrollArea, QSpinBox, QFileDialog, QApplication, QListWidget
)
from PyQt5.QtGui import QPixmap, QIcon, QPainter, QPen, QColor
from PyQt5.QtCore import Qt, QSize, pyqtSignal, QTimer, QPoint

# Sürücü Kontrolü
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
KEY_SCANCODES = {"W": 0x11, "S": 0x1F, "Z": 0x2C}

class MageFarmMacro:
    def __init__(self):
        self.config = {}
        self._running = False
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._sct = mss.mss()
        
        self.img_mob_name = None     
        self.mob_region = None       
        self.nova_coords = [] 
        self.last_used_times = {}

    def update_config(self, cfg):
        with self._lock:
            self.config = cfg
            self.mob_region = cfg.get("mob_region")
            self.nova_coords = cfg.get("nova_coords", [])
            path = cfg.get("path_mob_name")
            if path and os.path.exists(path):
                self.img_mob_name = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
            else:
                self.img_mob_name = None

    @property
    def is_running(self): return self._running

    def _check_target(self, sct):
        if self.img_mob_name is None or self.mob_region is None: return False
        x, y, w, h = self.mob_region
        try:
            scr = np.array(sct.grab({"left": int(x), "top": int(y), "width": int(w), "height": int(h)}))
            gray = cv2.cvtColor(scr, cv2.COLOR_BGRA2GRAY)
            res = cv2.matchTemplate(gray, self.img_mob_name, cv2.TM_CCOEFF_NORMED)
            return cv2.minMaxLoc(res)[1] > 0.75
        except: return False

    def start(self):
        if not self._running:
            self.last_used_times = {}
            self._stop_event.clear()
            self._running = True
            threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._stop_event.set()
        self._running = False

    def toggle(self):
        if self._running: self.stop()
        else: self.start()

    def _loop(self):
        with mss.mss() as sct:
            while not self._stop_event.is_set():
                try:
                    if _ClicksendKeyboardDriver: _ClicksendKeyboardDriver().tusbas(KEY_SCANCODES["Z"], 0.02)
                    else: pyautogui.press('z')
                    time.sleep(0.15)

                    if self._check_target(sct):
                        now = time.time()
                        # --- NOVA (ALAN) ATAK ---
                        area_list = self.config.get("area_skills", [])
                        click_wait = self.config.get("nova_click_wait", 1.0)
                        reset_dur = self.config.get("nova_reset_dur", 0.5)

                        for idx, skill in enumerate(area_list):
                            if self._stop_event.is_set(): break
                            s_id = f"area_{skill['f']}_{skill['d']}"
                            if now - self.last_used_times.get(s_id, 0) < skill.get('cooldown', 0):
                                continue

                            if self.nova_coords:
                                tx, ty = self.nova_coords[idx % len(self.nova_coords)]
                                if skill['f'] > 0:
                                    _ClicksendKeyboardDriver().tusbas(F_SCANCODES[skill['f']], 0.02)
                                    time.sleep(0.05)
                                _ClicksendKeyboardDriver().tusbas(DIGIT_SCANCODES[skill['d']], 0.02)
                                time.sleep(0.15)
                                if _ClicksendMouseDriver: _ClicksendMouseDriver().leftclick(0.03, int(tx), int(ty))
                                else: pyautogui.click(tx, ty)
                                self.last_used_times[s_id] = time.time()
                                time.sleep(click_wait)
                                if _ClicksendKeyboardDriver:
                                    _ClicksendKeyboardDriver().tusbas(KEY_SCANCODES["S"], reset_dur)
                                    time.sleep(0.02)
                                    _ClicksendKeyboardDriver().tusbas(KEY_SCANCODES["W"], reset_dur)
                                time.sleep(skill['delay'])

                        # --- TEKLİ ATAK ---
                        single_list = self.config.get("single_skills", [])
                        for skill in single_list:
                            if self._stop_event.is_set() or not self._check_target(sct): break
                            s_id = f"single_{skill['f']}_{skill['d']}"
                            if now - self.last_used_times.get(s_id, 0) < skill.get('cooldown', 0):
                                continue
                            if skill['f'] > 0:
                                _ClicksendKeyboardDriver().tusbas(F_SCANCODES[skill['f']], 0.02)
                                time.sleep(0.05)
                            _ClicksendKeyboardDriver().tusbas(DIGIT_SCANCODES[skill['d']], 0.02)
                            self.last_used_times[s_id] = time.time()
                            time.sleep(skill['delay'])
                    time.sleep(0.05)
                except: time.sleep(1)

class AreaSelector(QDialog):
    def __init__(self, title=""):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setWindowState(Qt.WindowFullScreen)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.CrossCursor)
        self.title = title
        self.start_pos = None
        self.current_pos = QPoint(0,0)
        self.result = None
    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape: self.reject()
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton: self.start_pos = e.pos(); self.current_pos = e.pos(); self.update()
    def mouseMoveEvent(self, e):
        self.current_pos = e.pos()
        if self.start_pos: self.update()
    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.start_pos:
            x, y = min(self.start_pos.x(), e.pos().x()), min(self.start_pos.y(), e.pos().y())
            w, h = abs(self.start_pos.x() - e.pos().x()), abs(self.start_pos.y() - e.pos().y())
            if w > 5 and h > 5: self.result = (x, y, w, h); self.accept()
            else: self.start_pos = None; self.update()
    def paintEvent(self, e):
        p = QPainter(self); p.fillRect(self.rect(), QColor(0, 0, 0, 150))
        if self.start_pos and self.current_pos:
            x, y, w, h = min(self.start_pos.x(), self.current_pos.x()), min(self.start_pos.y(), self.current_pos.y()), abs(self.start_pos.x() - self.current_pos.x()), abs(self.start_pos.y() - self.current_pos.y())
            p.setCompositionMode(QPainter.CompositionMode_Clear); p.fillRect(x, y, w, h, Qt.transparent); p.setCompositionMode(QPainter.CompositionMode_SourceOver); p.setPen(QPen(Qt.green, 2)); p.drawRect(x, y, w, h)
        p.setPen(Qt.yellow); p.drawText(self.rect(), Qt.AlignCenter, self.title + "\n(Sol Tık Sürükle | ESC İptal)")

class MageFarmWidget(QFrame):
    def __init__(self, parent=None, macro_instance=None, config=None):
        super().__init__(parent)
        self.macro = macro_instance or MageFarmMacro()
        self.config = config or {}
        self.macro.update_config(self.config)
        self.listen_active = False
        self._hotkey_hook = None
        
        self.setup_ui()
        
        # Durum güncelleme zamanlayıcısı
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_status)
        self.timer.start(200)

    def setup_ui(self):
        # STANDART BOYUT VE STİL
        self.setFrameShape(QFrame.Box)
        self.setMaximumWidth(260)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setStyleSheet("QFrame { background-color: #101010; border: 1px solid #444; border-radius: 4px; }")
        
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(4)

        # HEADER (4 İkon + Başlık)
        h = QHBoxLayout()
        h.setSpacing(2) # İkonlar arası mesafe daraltıldı
        
        import os
        icon_names = ["51fire.png", "52ice.png", "firenova.png", "icenova.png"]
        
        for name in icon_names:
            lbl = QLabel()
            lbl.setFixedSize(22, 22) # 4 ikon sığması için hafif küçültüldü
            lbl.setAlignment(Qt.AlignCenter)
            
            path = os.path.join("icons", "mage", name)
            pix = QPixmap(path)
            
            if not pix.isNull():
                lbl.setPixmap(pix.scaled(22, 22, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                lbl.setText("✨") # İkon yoksa parıltı emojisi
                lbl.setStyleSheet("font-size:12px; border:none;")
            h.addWidget(lbl)
        
        h.addStretch() # İkonları sola, başlığı sağa iter
        
        title = QLabel("MAGE FARM")
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

        # FOOTER (Alt Satır)
        row = QHBoxLayout()
        row.setSpacing(4)
        
        row.addWidget(QLabel("AKTİF TUŞ:"))
        
        self.lbl_key = QLabel(self.config.get("hotkey", "CAPS LOCK"))
        self.lbl_key.setObjectName("HotkeyLabel")
        self.lbl_key.setAlignment(Qt.AlignCenter)
        row.addWidget(self.lbl_key)
        
        btn_set = QPushButton("⚙ AYARLAR")
        btn_set.setObjectName("MinorSettingsButton")
        btn_set.clicked.connect(self.open_settings)
        row.addWidget(btn_set)
        
        v.addLayout(row)

    def open_settings(self):
        dlg = MageFarmSettingsDialog(self, self.config, self.macro)
        if dlg.exec_() == QDialog.Accepted:
            self.config = dlg.config
            self.macro.update_config(self.config)
            self.lbl_key.setText(self.config.get("hotkey"))

    def toggle_listen(self):
        if not self.listen_active:
            if not self.config.get("path_mob_name"):
                return QMessageBox.warning(self, "Eksik", "Lütfen ayarlardan MOB resmini yakalayın!")
            
            hk = self.config.get("hotkey", "CAPS LOCK").lower()
            try:
                self._hotkey_hook = keyboard.on_press_key(hk, lambda e: self.on_hotkey(), suppress=False)
                self.listen_active = True
            except:
                self.listen_active = False
        else:
            if self._hotkey_hook:
                try: keyboard.unhook(self._hotkey_hook)
                except: pass
            self._hotkey_hook = None
            self.listen_active = False
            self.macro.stop()

    def on_hotkey(self):
        self.macro.toggle()

    def update_status(self):
        # Standardize Renkler
        if not self.listen_active:
            self.lbl_st.setText("DURUM: PASİF")
            self.lbl_st.setStyleSheet("color:#ff5555; font-weight:bold;")
            self.btn_listen.setText("TUŞ DİNLEMEYİ BAŞLAT")
            self.btn_listen.setProperty("active", False)
        else:
            if self.macro.is_running:
                self.lbl_st.setText("DURUM: ÇALIŞIYOR")
                self.lbl_st.setStyleSheet("color:#00ff4c; font-weight:bold;")
            else:
                self.lbl_st.setText("DURUM: BEKLİYOR")
                self.lbl_st.setStyleSheet("color:#ffff55; font-weight:bold;")
            self.btn_listen.setText("DURDUR")
            self.btn_listen.setProperty("active", True)
        
        self.btn_listen.style().unpolish(self.btn_listen)
        self.btn_listen.style().polish(self.btn_listen)

class MageFarmSettingsDialog(QDialog):
    def __init__(self, parent, config, macro):
        super().__init__(parent)
        self.setWindowTitle("MAGE FARM AYARLARI")
        self.resize(650, 750)
        self.config, self.macro = config, macro
        self.capture_hotkey = False
        self.temp_coords = self.config.get("nova_coords", [])
        
        layout = QVBoxLayout(self)
        grp_top = QGroupBox("1. Başlatma ve Hedef")
        tl = QGridLayout(grp_top)
        self.txt_hotkey = QLineEdit(self.config.get("hotkey", "CAPS LOCK")); self.txt_hotkey.setReadOnly(True)
        btn_hk = QPushButton("TUŞ SEÇ"); btn_hk.clicked.connect(self.start_hotkey_capture)
        tl.addWidget(QLabel("BAŞLATMA TUŞU:"), 0, 0); tl.addWidget(self.txt_hotkey, 0, 1); tl.addWidget(btn_hk, 0, 2)
        btn_mob = QPushButton("MOB İSMİNİ YAKALA"); btn_mob.clicked.connect(self.safe_capture_mob)
        btn_reg = QPushButton("TARAMA ALANI SEÇ"); btn_reg.clicked.connect(self.safe_select_region)
        tl.addWidget(btn_mob, 1, 0); tl.addWidget(btn_reg, 1, 1, 1, 2)
        layout.addWidget(grp_top)

        grp_nova_cfg = QGroupBox("2. Nova Hareket / Reset Ayarları (S + W)")
        ncl = QGridLayout(grp_nova_cfg)
        ncl.addWidget(QLabel("Tıklama Sonrası Bekleme:"), 0, 0)
        self.sp_click_wait = QDoubleSpinBox(); self.sp_click_wait.setRange(0.01, 10.0); self.sp_click_wait.setValue(self.config.get("nova_click_wait", 1.0))
        ncl.addWidget(self.sp_click_wait, 0, 1)
        ncl.addWidget(QLabel("Reset Tuşu Basma Süresi:"), 1, 0)
        self.sp_reset_dur = QDoubleSpinBox(); self.sp_reset_dur.setRange(0.01, 5.0); self.sp_reset_dur.setValue(self.config.get("nova_reset_dur", 0.50))
        ncl.addWidget(self.sp_reset_dur, 1, 1)
        layout.addWidget(grp_nova_cfg)

        grp_coord = QGroupBox("3. Nova Koordinatları")
        cl = QVBoxLayout(grp_coord)
        self.coord_list = QListWidget(); self.refresh_list()
        cl.addWidget(self.coord_list)
        hb = QHBoxLayout()
        btn_add = QPushButton("KOORDİNAT EKLE (F)"); btn_add.clicked.connect(self.safe_add_coord)
        btn_clr = QPushButton("TEMİZLE"); btn_clr.clicked.connect(self.clear_coords)
        hb.addWidget(btn_add); hb.addWidget(btn_clr); cl.addLayout(hb)
        layout.addWidget(grp_coord)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        content = QWidget(); sl = QVBoxLayout(content)
        self.single_ui, self.area_ui = [], []
        grp_s = QGroupBox("4. Tekli Skiller"); ssl = QGridLayout(grp_s)
        ssl.addWidget(QLabel("F"), 0, 1); ssl.addWidget(QLabel("Delay"), 0, 2); ssl.addWidget(QLabel("CD (Sn)"), 0, 3)
        for i in range(1, 10):
            chk = QCheckBox(f"Tuş {i}"); cmb_f = QComboBox(); cmb_f.addItem("F YOK", 0)
            for f in range(1, 9): cmb_f.addItem(f"F{f}", f)
            sp = QDoubleSpinBox(); sp.setRange(0.1, 5.0); sp.setValue(1.0)
            cd = QDoubleSpinBox(); cd.setRange(0.0, 900.0); cd.setValue(0.0)
            ssl.addWidget(chk, i, 0); ssl.addWidget(cmb_f, i, 1); ssl.addWidget(sp, i, 2); ssl.addWidget(cd, i, 3)
            self.single_ui.append((chk, cmb_f, sp, i, cd))
        sl.addWidget(grp_s)
        grp_a = QGroupBox("5. Nova Skilleri"); asl = QGridLayout(grp_a)
        asl.addWidget(QLabel("F"), 0, 1); asl.addWidget(QLabel("Delay"), 0, 2); asl.addWidget(QLabel("CD (Sn)"), 0, 3)
        for i in range(1, 10):
            chk = QCheckBox(f"Tuş {i}"); cmb_f = QComboBox(); cmb_f.addItem("F YOK", 0)
            for f in range(1, 9): cmb_f.addItem(f"F{f}", f)
            sp = QDoubleSpinBox(); sp.setRange(0.1, 10.0); sp.setValue(1.5)
            cd = QDoubleSpinBox(); cd.setRange(0.0, 900.0); cd.setValue(45.0)
            asl.addWidget(chk, i, 0); asl.addWidget(cmb_f, i, 1); asl.addWidget(sp, i, 2); asl.addWidget(cd, i, 3)
            self.area_ui.append((chk, cmb_f, sp, i, cd))
        sl.addWidget(grp_a)
        scroll.setWidget(content); layout.addWidget(scroll)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject); layout.addWidget(btns)
        self.load_saved_data()

    def load_saved_data(self):
        for s in self.config.get("single_skills", []):
            idx = s["d"] - 1
            if 0 <= idx < 9: self.single_ui[idx][0].setChecked(True); self.single_ui[idx][1].setCurrentIndex(self.single_ui[idx][1].findData(s["f"])); self.single_ui[idx][2].setValue(s["delay"]); self.single_ui[idx][4].setValue(s.get("cooldown", 0.0))
        for s in self.config.get("area_skills", []):
            idx = s["d"] - 1
            if 0 <= idx < 9: self.area_ui[idx][0].setChecked(True); self.area_ui[idx][1].setCurrentIndex(self.area_ui[idx][1].findData(s["f"])); self.area_ui[idx][2].setValue(s["delay"]); self.area_ui[idx][4].setValue(s.get("cooldown", 45.0))
    def refresh_list(self):
        self.coord_list.clear()
        for i, pt in enumerate(self.temp_coords): self.coord_list.addItem(f"Nova {i+1}: {pt}")
    def clear_coords(self): self.temp_coords = []; self.refresh_list()
    def safe_add_coord(self):
        QApplication.setQuitOnLastWindowClosed(False); self.setWindowOpacity(0); QApplication.processEvents(); time.sleep(0.3)
        msg = QMessageBox(self); msg.setText("F tuşuna bastığınız yer eklenir. Bitince ESC basın."); msg.show()
        while True:
            if keyboard.is_pressed('f'):
                x, y = pyautogui.position(); self.temp_coords.append((x, y)); self.refresh_list(); time.sleep(0.3)
            if keyboard.is_pressed('esc'): break
            QApplication.processEvents(); time.sleep(0.01)
        msg.close(); self.setWindowOpacity(1); self.showNormal(); self.raise_(); self.activateWindow()
    def safe_capture_mob(self):
        QApplication.setQuitOnLastWindowClosed(False); self.setWindowOpacity(0); QApplication.processEvents(); time.sleep(0.3)
        d = AreaSelector("MOB İSMİNİ ÇİZİN")
        if d.exec_() == QDialog.Accepted and d.result:
            x,y,w,h = d.result
            with mss.mss() as sct:
                img = np.array(sct.grab({"left":x,"top":y,"width":w,"height":h}))
                if not os.path.exists("farm_data"): os.makedirs("farm_data")
                path = "farm_data/mage_mob.png"; cv2.imwrite(path, cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY))
                self.config["path_mob_name"] = path
        self.setWindowOpacity(1); self.showNormal(); self.raise_(); self.activateWindow()
    def safe_select_region(self):
        QApplication.setQuitOnLastWindowClosed(False); self.setWindowOpacity(0); QApplication.processEvents(); time.sleep(0.3)
        d = AreaSelector("TARAMA ALANINI ÇİZİN")
        if d.exec_() == QDialog.Accepted: self.config["mob_region"] = d.result
        self.setWindowOpacity(1); self.showNormal(); self.raise_(); self.activateWindow()
    def start_hotkey_capture(self): self.capture_hotkey = True; self.txt_hotkey.setText("BAS..."); self.grabKeyboard()
    def keyPressEvent(self, e):
        if self.capture_hotkey:
            k = e.text().upper()
            if not k and e.key() == Qt.Key_CapsLock: k = "CAPS LOCK"
            if k: self.txt_hotkey.setText(k); self.capture_hotkey = False; self.releaseKeyboard()
        else: super().keyPressEvent(e)
    def accept(self):
        self.config["hotkey"] = self.txt_hotkey.text()
        self.config["nova_coords"] = self.temp_coords
        self.config["nova_click_wait"] = self.sp_click_wait.value()
        self.config["nova_reset_dur"] = self.sp_reset_dur.value()
        self.config["single_skills"] = [{"f": u[1].currentData(), "d": u[3], "delay": u[2].value(), "cooldown": u[4].value()} for u in self.single_ui if u[0].isChecked()]
        self.config["area_skills"] = [{"f": u[1].currentData(), "d": u[3], "delay": u[2].value(), "cooldown": u[4].value()} for u in self.area_ui if u[0].isChecked()]
        super().accept()
