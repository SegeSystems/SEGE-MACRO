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
import numpy as np
import cv2
import mss
import win32api

# PyQt5
from PyQt5.QtWidgets import (
    QDialog, QGridLayout, QLabel, QComboBox, 
    QLineEdit, QPushButton, QDoubleSpinBox, 
    QDialogButtonBox, QHBoxLayout, QWidget,
    QFrame, QVBoxLayout, QSizePolicy, QMessageBox,
    QCheckBox, QGroupBox, QScrollArea, QRadioButton, QButtonGroup
)
from PyQt5.QtGui import QPixmap, QIcon, QPainter, QPen, QColor, QBrush
from PyQt5.QtCore import Qt, QSize, pyqtSignal, QTimer, QRect

# Sürücü
try:
    from clicksend import KeyboardDriver as _ClicksendKeyboardDriver
    from clicksend import MouseDriver as _ClicksendMouseDriver
except ImportError:
    _ClicksendKeyboardDriver = None
    _ClicksendMouseDriver = None

# Keyboard
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
class MageOtoTpMacro:
    def __init__(self):
        self.region = None
        self.member_ratios = [] 
        self.fixed_slots = []
        self.show_debug = False 
        
        # AYARLAR
        self.tp_active = False
        self.tp_f = 1
        self.tp_d = 1
        self.tp_hp_threshold = 0.40 # %40 altı
        self.tp_mode = "single" # "single" veya "continuous"
        
        # Runtime
        self._driver = _ClicksendKeyboardDriver() if _ClicksendKeyboardDriver else None
        self._mouse = _ClicksendMouseDriver() if _ClicksendMouseDriver else None
        self._running = False
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        
        # TP yiyenleri hatırlamak için (Single modda spamı önlemek için)
        self.tp_cooldowns = {} # {member_index: timestamp}
        self.GLOBAL_CD = 2.0 # TP Skilli dolum süresi

    def update_config(self, cfg):
        with self._lock:
            if cfg.get("region"): self.region = cfg["region"]
            self.tp_active = cfg.get("active", False)
            self.tp_f = cfg.get("f", 1)
            self.tp_d = cfg.get("d", 1)
            self.tp_hp_threshold = cfg.get("hp", 0.40)
            self.tp_mode = cfg.get("mode", "single")

    def _detect_bars_once(self, scr, w, h, x_offset, y_offset):
        hsv = cv2.cvtColor(cv2.cvtColor(scr, cv2.COLOR_BGRA2BGR), cv2.COLOR_BGR2HSV)
        lower1 = np.array([0, 80, 60]); upper1 = np.array([20, 255, 255])
        lower2 = np.array([160, 80, 60]); upper2 = np.array([180, 255, 255])
        mask = cv2.bitwise_or(cv2.inRange(hsv, lower1, upper1), cv2.inRange(hsv, lower2, upper2))
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (30, 2))
        closed_mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(closed_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        potential_slots = []
        for cnt in contours:
            cx, cy, cw, ch = cv2.boundingRect(cnt)
            if cw > (w * 0.20) and ch > 4:
                potential_slots.append((cx, cy, cw, ch))
        potential_slots.sort(key=lambda b: b[1])

        confirmed_slots = []
        last_y = -999
        for (cx, cy, cw, ch) in potential_slots:
            if abs(cy - last_y) < 5: continue
            click_x = x_offset + cx + (cw // 2); click_y = y_offset + cy + (ch // 2)
            confirmed_slots.append({"rect": (cx, cy, cw, ch), "center": (click_x, click_y)})
            last_y = cy
        return confirmed_slots

    def calibrate(self):
        if not self.region: return 0
        x, y, w, h = self.region
        with mss.mss() as sct: scr = np.array(sct.grab({"left": x, "top": y, "width": w, "height": h}))
        self.fixed_slots = self._detect_bars_once(scr, w, h, x, y)
        print(f"[MAGE TP] Kalibrasyon: {len(self.fixed_slots)} üye bulundu.")
        return len(self.fixed_slots)

    @property
    def is_running(self): return self._running

    def toggle(self): self.stop() if self._running else self.start()

    def start(self):
        if not self.region: return
        if not self._running:
            if not self.fixed_slots:
                if self.calibrate() == 0: return
            self._stop_event.clear(); self._running = True
            threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._stop_event.set(); self._running = False
        # cv2.destroyAllWindows() — opencv-python-headless'da yok, debug kaldırıldı

    def _loop(self):
        while not self._stop_event.is_set():
            try: self._analyze_fixed_slots()
            except Exception as e: print(f"[TP ERROR] {e}")
            if False:  # opencv-headless: imshow/waitKey/destroyAllWindows yok
                if self.show_debug:
                    if cv2.waitKey(1) & 0xFF == ord('q'): self.show_debug = False; cv2.destroyAllWindows()
                else:
                    cv2.destroyAllWindows()
            time.sleep(0.05)

    def _analyze_fixed_slots(self):
        if self._stop_event.is_set() or not self.fixed_slots: return
        x, y, w, h = self.region
        try:
            with mss.mss() as sct: scr = np.array(sct.grab({"left": x, "top": y, "width": w, "height": h}))
        except: return
        
        debug_img = None
        if self.show_debug: debug_img = cv2.cvtColor(scr, cv2.COLOR_BGRA2BGR)

        members_status = []
        for idx, slot in enumerate(self.fixed_slots):
            sx, sy, sw, sh = slot["rect"]
            bar_img = scr[sy+2 : sy+sh-2, sx : sx+sw]
            hsv = cv2.cvtColor(cv2.cvtColor(bar_img, cv2.COLOR_BGRA2BGR), cv2.COLOR_BGR2HSV)
            lower1 = np.array([0, 60, 40]); upper1 = np.array([25, 255, 255])
            lower2 = np.array([155, 60, 40]); upper2 = np.array([180, 255, 255])
            mask = cv2.bitwise_or(cv2.inRange(hsv, lower1, upper1), cv2.inRange(hsv, lower2, upper2))
            
            points = cv2.findNonZero(mask)
            if points is not None:
                max_x = np.max(points[:,:,0])
                ratio = max_x / float(sw)
            else: ratio = 0.0

            members_status.append({"ratio": ratio, "center": slot["center"], "rect": slot["rect"], "index": idx})
            
            if debug_img is not None:
                cv2.rectangle(debug_img, (sx, sy), (sx+sw, sy+sh), (0, 255, 0), 1)
                cv2.putText(debug_img, f"%{int(ratio*100)}", (sx, sy-2), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0,255,255), 1)

        if False and self.show_debug and debug_img is not None: cv2.imshow("MAGE TP DEBUG", debug_img)  # opencv-headless: imshow yok

        self.member_ratios = [m["ratio"] for m in members_status]
        now = time.time()
        
        # --- TP KARARI ---
        if self.tp_active:
            for m in members_status:
                if self._stop_event.is_set(): break
                
                # Kendini (veya dolu canları) atla
                if m["ratio"] >= 0.98: continue

                # Can Eşiğin Altındaysa
                if m["ratio"] <= self.tp_hp_threshold:
                    idx = m["index"]
                    
                    # Cooldown Kontrolü
                    last = self.tp_cooldowns.get(idx, 0)
                    
                    # Eğer Single Moddaysa ve son 10 saniye içinde çekildiyse çekme
                    if self.tp_mode == "single" and (now - last < 10.0):
                        continue
                    
                    # Eğer Continuous ise veya Single süresi dolmuşsa
                    if now - last > self.GLOBAL_CD:
                        print(f"[MAGE TP] Üye {idx+1} çekiliyor! HP: %{int(m['ratio']*100)}")
                        self._click_and_cast(m["center"], self.tp_f, self.tp_d)
                        self.tp_cooldowns[idx] = now
                        time.sleep(0.5) # Global CD bekle
                        return # Bir turda bir kişi çek

    def _cast(self, f, d):
        if self._stop_event.is_set(): return
        if f > 0:
            sc = F_SCANCODES.get(f)
            if self._driver: self._driver.tusbas(sc, 0.02)
            time.sleep(0.05)
        sc_d = DIGIT_SCANCODES.get(d)
        if self._driver: self._driver.tusbas(sc_d, 0.02)
        time.sleep(0.2)

    def _click_and_cast(self, center_pos, f, d):
        if self._stop_event.is_set(): return
        tx, ty = center_pos
        try:
            l_down = win32api.GetKeyState(0x01) < 0
            if l_down:
                if self._mouse: self._mouse.mouse_left_up(0,0)
                else: pyautogui.mouseUp()
                time.sleep(0.01)
        except: pass

        if self._mouse: self._mouse.leftclick(0.05, int(tx), int(ty))
        else: pyautogui.click(tx, ty)
        
        time.sleep(0.05) 
        self._cast(f, d)

# =========================================================
# 2. GUI (AYAR PENCERESİ VE WIDGET)
# =========================================================
class RectSelectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setWindowState(Qt.WindowFullScreen)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.CrossCursor)
        self.start_pos = None; self.current_pos = None; self.result = None

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton: self.start_pos = e.pos(); self.current_pos = e.pos(); self.update()
        elif e.button() == Qt.RightButton: self.reject()

    def mouseMoveEvent(self, e):
        if self.start_pos: self.current_pos = e.pos(); self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.start_pos:
            x = min(self.start_pos.x(), e.pos().x()); y = min(self.start_pos.y(), e.pos().y())
            w = abs(self.start_pos.x() - e.pos().x()); h = abs(self.start_pos.y() - e.pos().y())
            if w > 10 and h > 10: self.result = (x, y, w, h); self.accept()
            else: self.start_pos = None; self.update()

    def paintEvent(self, e):
        p = QPainter(self); p.fillRect(self.rect(), QColor(0,0,0,100))
        if self.start_pos and self.current_pos:
            x = min(self.start_pos.x(), self.current_pos.x()); y = min(self.start_pos.y(), self.current_pos.y())
            w = abs(self.start_pos.x() - self.current_pos.x()); h = abs(self.start_pos.y() - self.current_pos.y())
            p.setCompositionMode(QPainter.CompositionMode_Clear); p.fillRect(x,y,w,h,Qt.transparent)
            p.setCompositionMode(QPainter.CompositionMode_SourceOver); p.setPen(QPen(Qt.green, 2)); p.drawRect(x,y,w,h)

class PartyMemberBar(QFrame):
    def __init__(self, index, parent=None):
        super().__init__(parent)
        self.setFixedHeight(12) 
        self.ratio = 1.0
        self.index = index
        self.setStyleSheet("background-color: #330000; border: 1px solid #444; margin-bottom: 2px;")
    def set_value(self, ratio): self.ratio = max(0.0, min(1.0, ratio)); self.update()
    def paintEvent(self, e):
        super().paintEvent(e); p = QPainter(self); rect = self.rect(); w = int(rect.width() * self.ratio)
        col = QColor(255, 0, 0); p.fillRect(rect.x(), rect.y(), w, rect.height(), col)
        p.setPen(Qt.white); p.setFont(self.font()); p.drawText(rect, Qt.AlignCenter, f"P{self.index+1}: %{int(self.ratio*100)}")

class MageOtoTpSettingsDialog(QDialog):
    def __init__(self, parent, config, macro):
        super().__init__(parent)
        self.setWindowTitle("MAGE OTO TP AYARLARI")
        self.setModal(True); self.resize(600, 450)
        self.config = config; self.macro = macro
        self.capture_hotkey = False
        
        layout = QVBoxLayout(self)
        
        h_key = QHBoxLayout()
        h_key.addWidget(QLabel("BAŞLATMA TUŞU:"))
        self.txt_hotkey = QLineEdit(self.config.get("hotkey", "PAGE UP")); self.txt_hotkey.setReadOnly(True)
        btn_hk = QPushButton("SEÇ"); btn_hk.clicked.connect(self.start_hotkey_capture)
        h_key.addWidget(self.txt_hotkey); h_key.addWidget(btn_hk)
        layout.addLayout(h_key)

        grp_area = QGroupBox("1. Tarama Alanı")
        ga = QHBoxLayout(grp_area)
        self.lbl_area = QLabel(f"Seçili Alan: {self.config.get('region', 'YOK')}")
        btn_scan = QPushButton("PARTY BARINI SEÇ"); btn_scan.clicked.connect(self.select_area)
        btn_debug = QPushButton("DEBUG"); btn_debug.clicked.connect(self.toggle_debug)
        btn_reset = QPushButton("YENİDEN TARA"); btn_reset.clicked.connect(self.reset_slots)
        ga.addWidget(self.lbl_area); ga.addWidget(btn_scan); ga.addWidget(btn_reset); ga.addWidget(btn_debug)
        layout.addWidget(grp_area)

        grp_skill = QGroupBox("2. TP Ayarları")
        gl = QGridLayout(grp_skill)
        
        self.chk_active = QCheckBox("OTO TP AKTİF"); self.chk_active.setChecked(self.config.get("active", False))
        gl.addWidget(self.chk_active, 0, 0, 1, 2)

        gl.addWidget(QLabel("TP SKILL SAYFASI (F):"), 1, 0)
        self.cmb_f = QComboBox(); self.cmb_f.addItem("F YOK", 0)
        for i in range(1, 10): self.cmb_f.addItem(f"F{i}", i)
        idx_f = self.cmb_f.findData(self.config.get("f", 1)); self.cmb_f.setCurrentIndex(idx_f if idx_f>=0 else 0)
        gl.addWidget(self.cmb_f, 1, 1)

        gl.addWidget(QLabel("TP SKILL TUŞU (0-9):"), 2, 0)
        self.cmb_d = QComboBox()
        for i in range(10): self.cmb_d.addItem(str(i), i)
        self.cmb_d.setCurrentIndex(self.config.get("d", 1))
        gl.addWidget(self.cmb_d, 2, 1)

        gl.addWidget(QLabel("CAN EŞİĞİ (%):"), 3, 0)
        self.sp_hp = QDoubleSpinBox(); self.sp_hp.setRange(1, 100); self.sp_hp.setValue(self.config.get("hp", 0.40)*100)
        gl.addWidget(self.sp_hp, 3, 1)
        
        layout.addWidget(grp_skill)
        
        grp_mode = QGroupBox("3. Çekme Modu")
        gm = QHBoxLayout(grp_mode)
        self.rb_single = QRadioButton("Tek Seferlik (Bir Kere Çek)")
        self.rb_cont = QRadioButton("Sürekli (Can Düşükse Çekmeye Devam Et)")
        bg = QButtonGroup(self); bg.addButton(self.rb_single); bg.addButton(self.rb_cont)
        
        if self.config.get("mode") == "continuous": self.rb_cont.setChecked(True)
        else: self.rb_single.setChecked(True)
        gm.addWidget(self.rb_single); gm.addWidget(self.rb_cont)
        layout.addWidget(grp_mode)
        
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def select_area(self):
        self.hide(); time.sleep(0.2)
        d = RectSelectDialog()
        if d.exec_() == QDialog.Accepted:
            self.config["region"] = d.result
            self.macro.region = d.result
            self.lbl_area.setText(f"Seçili: {d.result}")
            self.macro.fixed_slots = []
        self.show()

    def reset_slots(self):
        self.macro.fixed_slots = []
        count = self.macro.calibrate()
        QMessageBox.information(self, "Bilgi", f"Yeniden tarandı. {count} kişi bulundu.")

    def toggle_debug(self):
        self.macro.show_debug = not self.macro.show_debug
        QMessageBox.information(self, "Debug", f"Debug: {self.macro.show_debug}")

    def start_hotkey_capture(self):
        self.capture_hotkey = True; self.txt_hotkey.setText("BAS..."); self.grabKeyboard()

    def keyPressEvent(self, e):
        if self.capture_hotkey:
            k = e.text().upper()
            if not k:
                if e.key() == Qt.Key_PageUp: k = "PAGE UP"
                elif e.key() == Qt.Key_PageDown: k = "PAGE DOWN"
            if k: self.txt_hotkey.setText(k); self.capture_hotkey = False; self.releaseKeyboard()
        else: super().keyPressEvent(e)

    def accept(self):
        self.config["hotkey"] = self.txt_hotkey.text()
        self.config["active"] = self.chk_active.isChecked()
        self.config["f"] = self.cmb_f.currentData()
        self.config["d"] = int(self.cmb_d.currentText())
        self.config["hp"] = self.sp_hp.value() / 100.0
        self.config["mode"] = "continuous" if self.rb_cont.isChecked() else "single"
        super().accept()

class MageOtoTpWidget(QFrame):
    update_signal = pyqtSignal()

    def __init__(self, parent=None, macro_instance=None, config=None):
        super().__init__(parent)
        self.macro = macro_instance or MageOtoTpMacro()
        self.config = config or {}
        self.macro.update_config(self.config)
        self.listen_active = False
        self.bars = []
        
        # HP Barlarını tutan konteyner (TP'ye özel)
        self.bar_container = QWidget()
        self.bar_layout = QVBoxLayout(self.bar_container)
        self.bar_layout.setContentsMargins(0, 2, 0, 2)
        self.bar_layout.setSpacing(1)
        
        self.update_signal.connect(self._safe_update)
        self.setup_ui()
        self._safe_update()

    def setup_ui(self):
        # STANDART BOYUT VE STİL
        self.setFrameShape(QFrame.Box)
        self.setMaximumWidth(260)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setStyleSheet("QFrame { background-color: #101010; border: 1px solid #444; border-radius: 4px; }")
        
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(4)

        # HEADER (tp.png ve notp.png ikonları + Başlık)
        h = QHBoxLayout()
        h.setSpacing(4)
        
        import os
        icon_names = ["tp.png", "notp.png"]
        for name in icon_names:
            lbl = QLabel()
            lbl.setFixedSize(22, 22)
            lbl.setAlignment(Qt.AlignCenter)
            path = os.path.join("icons", "mage", name)
            pix = QPixmap(path)
            if not pix.isNull():
                lbl.setPixmap(pix.scaled(22, 22, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                lbl.setText("🌀") # İkon yoksa fallback
                lbl.setStyleSheet("font-size:14px; border:none;")
            h.addWidget(lbl)
            
        h.addStretch()
        
        title = QLabel("OTO TP (TELEPORT)")
        title.setObjectName("MinorHeaderLabel")
        h.addWidget(title)
        v.addLayout(h)

        # Dinleme Butonu
        self.btn_listen = QPushButton("TUŞ DİNLEMEYİ BAŞLAT")
        self.btn_listen.setObjectName("ThreeFiveListenButton")
        self.btn_listen.clicked.connect(self.toggle_listen)
        v.addWidget(self.btn_listen)

        # Durum Yazısı
        self.lbl_status = QLabel("DURUM: PASİF")
        self.lbl_status.setObjectName("MinorStatusLabel")
        v.addWidget(self.lbl_status)

        # HP Barlarını ekle (Status'un altında)
        v.addWidget(self.bar_container)

        # FOOTER (Alt Satır - Diğerleriyle birebir aynı)
        row = QHBoxLayout()
        row.setSpacing(4)
        
        row.addWidget(QLabel("AKTİF TUŞ:"))
        
        self.lbl_hk = QLabel(self.config.get("hotkey", "PAGE UP"))
        self.lbl_hk.setObjectName("HotkeyLabel")
        self.lbl_hk.setAlignment(Qt.AlignCenter)
        row.addWidget(self.lbl_hk)
        
        btn_set = QPushButton("⚙ AYARLAR") # Diğerleriyle aynı isim
        btn_set.setObjectName("MinorSettingsButton")
        btn_set.clicked.connect(self.open_settings)
        row.addWidget(btn_set)
        
        v.addLayout(row)

    def open_settings(self):
        dlg = MageOtoTpSettingsDialog(self, self.config, self.macro)
        if dlg.exec_() == QDialog.Accepted:
            self.config = dlg.config
            self.macro.update_config(self.config)
            self.lbl_hk.setText(self.config.get("hotkey"))
            if self.listen_active: self.toggle_listen(); self.toggle_listen()

    def toggle_listen(self):
        if not keyboard: return QMessageBox.warning(self, "Hata", "Keyboard eksik!")
        if not self.listen_active:
            hk = self.config.get("hotkey", "PAGE UP").lower()
            try:
                self._hooks = []
                self._hooks.append(keyboard.on_press_key(hk, lambda e: self.on_hotkey(), suppress=False))
                self.listen_active = True
            except: self.listen_active = False
        else:
            if hasattr(self, '_hooks'):
                for h in self._hooks: 
                    try: keyboard.unhook(h)
                    except: pass
            self._hooks = []; self.listen_active = False; self.macro.stop()
        self._safe_update()

    def on_hotkey(self):
        self.macro.toggle()
        self.update_signal.emit()

    def _safe_update(self):
        # Renkler ve metinler Staff/Farm/Restore ile eşlendi
        if not self.listen_active:
            self.lbl_status.setText("DURUM: PASİF")
            self.lbl_status.setStyleSheet("color:#ff5555; font-weight:bold;")
            self.btn_listen.setText("TUŞ DİNLEMEYİ BAŞLAT")
            self.btn_listen.setProperty("active", False)
        else:
            if self.macro.is_running:
                count = len(self.macro.member_ratios)
                self.lbl_status.setText(f"DURUM: ÇALIŞIYOR ({count} ÜYE)")
                self.lbl_status.setStyleSheet("color:#00ff4c; font-weight:bold;")
                self.btn_listen.setText("DURDUR")
            else:
                self.lbl_status.setText("DURUM: BEKLİYOR")
                self.lbl_status.setStyleSheet("color:#ffff55; font-weight:bold;")
                self.btn_listen.setText("DURDUR")
            self.btn_listen.setProperty("active", True)
        
        self.btn_listen.style().unpolish(self.btn_listen)
        self.btn_listen.style().polish(self.btn_listen)
        
        # HP Barlarını Güncelle (Sadece TP'ye özel fonksiyon)
        current_ratios = self.macro.member_ratios
        while len(self.bars) < len(current_ratios):
            bar = PartyMemberBar(len(self.bars))
            self.bar_layout.addWidget(bar)
            self.bars.append(bar)
            
        for i, bar in enumerate(self.bars):
            if i < len(current_ratios):
                bar.show()
                bar.set_value(current_ratios[i])
            else:
                bar.hide()

        if self.listen_active:
            QTimer.singleShot(100, self._safe_update)
