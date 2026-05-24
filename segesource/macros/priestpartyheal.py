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
    QCheckBox, QGroupBox, QScrollArea, QSpinBox
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
class PriestPartyHealMacro:
    def __init__(self):
        self.region = None
        self.member_ratios = [] 
        self.show_debug = False 
        
        # --- YENİ: SABİT SLOTLAR ---
        # Tarama yapıldığında bulunan barların koordinatları buraya sabitlenir.
        # Format: [{'rect': (x, y, w, h), 'center': (cx, cy)}, ...]
        self.fixed_slots = []
        
        # AYARLAR
        self.s1920_active = False; self.s1920_f = 1; self.s1920_d = 1; self.s1920_hp = 0.80
        self.p10k_active = False; self.p10k_f = 1; self.p10k_d = 2; self.p10k_hp = 0.70; self.p10k_count = 2
        self.rest_active = False; self.rest_f = 1; self.rest_d = 3; self.rest_hp = 0.75; self.rest_count = 2
        self.s10k_active = False; self.s10k_f = 1; self.s10k_d = 4; self.s10k_hp = 0.40

        self._driver = _ClicksendKeyboardDriver() if _ClicksendKeyboardDriver else None
        self._mouse = _ClicksendMouseDriver() if _ClicksendKeyboardDriver else None
        
        self._running = False
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        
        self.last_cast_time = {"s1920": 0, "s10k": 0, "p10k": 0, "rest": 0}
        self.COOLDOWNS = {"s1920": 1.0, "s10k": 3.0, "p10k": 5.0, "rest": 10.0}

    def update_config(self, cfg):
        with self._lock:
            if cfg.get("region"): self.region = cfg["region"]
            c = cfg.get("single_1920", {}); self.s1920_active = c.get("active", False); self.s1920_f = c.get("f", 1); self.s1920_d = c.get("d", 1); self.s1920_hp = c.get("hp", 0.80)
            c = cfg.get("party_10k", {}); self.p10k_active = c.get("active", False); self.p10k_f = c.get("f", 1); self.p10k_d = c.get("d", 2); self.p10k_hp = c.get("hp", 0.70); self.p10k_count = c.get("count", 2)
            c = cfg.get("party_restore", {}); self.rest_active = c.get("active", False); self.rest_f = c.get("f", 1); self.rest_d = c.get("d", 3); self.rest_hp = c.get("hp", 0.75); self.rest_count = c.get("count", 2)
            c = cfg.get("single_10k", {}); self.s10k_active = c.get("active", False); self.s10k_f = c.get("f", 1); self.s10k_d = c.get("d", 4); self.s10k_hp = c.get("hp", 0.40)

    def _detect_bars_once(self, scr, w, h, x_offset, y_offset):
        """
        Başlangıçta bir kere çalışır.
        Görüntüdeki tüm barları bulur ve koordinatlarını kaydeder.
        """
        hsv = cv2.cvtColor(cv2.cvtColor(scr, cv2.COLOR_BGRA2BGR), cv2.COLOR_BGR2HSV)

        # Geniş Kırmızı Maskesi (Bulmak için toleransı yüksek tutuyoruz)
        lower1 = np.array([0, 80, 60]); upper1 = np.array([20, 255, 255])
        lower2 = np.array([160, 80, 60]); upper2 = np.array([180, 255, 255])
        mask = cv2.bitwise_or(cv2.inRange(hsv, lower1, upper1), cv2.inRange(hsv, lower2, upper2))

        # Yatay Birleştirme (İsim yazısını yutması için)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (30, 2))
        closed_mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(closed_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        potential_slots = []
        for cnt in contours:
            cx, cy, cw, ch = cv2.boundingRect(cnt)
            # Filtre: Genişlik ve Yükseklik makul olmalı
            if cw > (w * 0.20) and ch > 4:
                potential_slots.append((cx, cy, cw, ch))

        # Y koordinatına göre sırala
        potential_slots.sort(key=lambda b: b[1])

        confirmed_slots = []
        last_y = -999

        for (cx, cy, cw, ch) in potential_slots:
            if abs(cy - last_y) < 5: continue # Çakışanları atla
            
            # Tıklama noktası (Merkez)
            click_x = x_offset + cx + (cw // 2)
            click_y = y_offset + cy + (ch // 2)

            confirmed_slots.append({
                # Relatif rect (Döngüde kırpmak için)
                "rect": (cx, cy, cw, ch), 
                # Global tıklama noktası
                "center": (click_x, click_y)
            })
            last_y = cy
            
        return confirmed_slots

    def calibrate(self):
        """
        Sistemi başlatırken mevcut barları tarar ve sabitler.
        """
        if not self.region: return 0
        x, y, w, h = self.region
        with mss.mss() as sct:
            scr = np.array(sct.grab({"left": x, "top": y, "width": w, "height": h}))
        
        # Slotları bul ve kaydet
        self.fixed_slots = self._detect_bars_once(scr, w, h, x, y)
        print(f"[PARTY] Kalibrasyon tamamlandı. {len(self.fixed_slots)} bar sabitlendi.")
        return len(self.fixed_slots)

    @property
    def is_running(self): return self._running

    def toggle(self): self.stop() if self._running else self.start()

    def start(self):
        if not self.region: return
        if not self._running:
            # Başlarken kalibrasyon yap (Barları kilitle)
            if not self.fixed_slots:
                count = self.calibrate()
                if count == 0:
                    print("[PARTY] Bar bulunamadı! Lütfen alanı doğru seçin.")
                    return

            self._stop_event.clear(); self._running = True
            threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self._stop_event.set(); self._running = False
        # PRODUCTION: cv2.destroyAllWindows() opencv-python-headless'ta yok, debug devre dışı

    def _loop(self):
        while not self._stop_event.is_set():
            try: self._analyze_fixed_slots()
            except Exception as e: print(f"[PARTY ERROR] {e}")

            if False:  # PRODUCTION: cv2.imshow/waitKey opencv-python-headless'ta yok, debug devre dışı
                if self.show_debug:
                    if cv2.waitKey(1) & 0xFF == ord('q'): self.show_debug = False; cv2.destroyAllWindows()
                else: cv2.destroyAllWindows()
            time.sleep(0.05)

    def _analyze_fixed_slots(self):
        if self._stop_event.is_set(): return
        
        # Eğer slotlar kaybolduysa tekrar dene (nadiren olur)
        if not self.fixed_slots: return 

        x, y, w, h = self.region
        try:
            with mss.mss() as sct:
                scr = np.array(sct.grab({"left": x, "top": y, "width": w, "height": h}))
        except: return
        
        debug_img = None
        if self.show_debug: debug_img = cv2.cvtColor(scr, cv2.COLOR_BGRA2BGR)

        # --- YENİ MANTIK: Sadece Sabit Kutucukların İçine Bak ---
        members_status = []
        
        for idx, slot in enumerate(self.fixed_slots):
            sx, sy, sw, sh = slot["rect"]
            
            # Ana resimden sadece o barın olduğu yeri kırp
            # Hata payı için dikeyde 2px içeri giriyorum
            bar_img = scr[sy+2 : sy+sh-2, sx : sx+sw]
            
            # Kırpılan alanda renk analizi
            hsv = cv2.cvtColor(cv2.cvtColor(bar_img, cv2.COLOR_BGRA2BGR), cv2.COLOR_BGR2HSV)
            
            # Kırmızı Maskesi (Daha geniş tolerans)
            lower1 = np.array([0, 60, 40]); upper1 = np.array([25, 255, 255])
            lower2 = np.array([155, 60, 40]); upper2 = np.array([180, 255, 255])
            mask = cv2.bitwise_or(cv2.inRange(hsv, lower1, upper1), cv2.inRange(hsv, lower2, upper2))
            
            # Mor/Siyah Debuff Yemiş Olabilir (Parlaklık kontrolü ekle)
            # Eğer HP barı doluysa renkli veya parlak olmalı. Boşsa siyahtır.
            # Basitçe kırmızı yoğunluğuna bakalım, yetmezse doluluk oranına bakarız.
            
            # Kırmızı piksel sayısı / Toplam piksel sayısı
            total_pixels = bar_img.shape[0] * bar_img.shape[1]
            red_pixels = cv2.countNonZero(mask)
            
            if total_pixels > 0:
                ratio = red_pixels / float(total_pixels)
                # İsim yazısı vs yüzünden kırmızı %100 olmaz. %70 üzeri kırmızıysa dolu say.
                # Ancak biz "barın ne kadarı dolu"yu arıyoruz.
                # Bu yöntem (piksel sayma) barın sağdan sola azaldığını varsayar.
                
                # DAHA İYİ YÖNTEM: En sağdaki kırmızıyı bul.
                # Maskedeki en sağdaki beyaz pikselin X koordinatı / Genişlik = Oran
                points = cv2.findNonZero(mask)
                if points is not None:
                    max_x = np.max(points[:,:,0])
                    # Barın genişliğine oranla
                    ratio_width = max_x / float(sw)
                    ratio = ratio_width
                else:
                    ratio = 0.0 # Hiç kırmızı yok
            else:
                ratio = 0.0

            members_status.append({
                "ratio": ratio,
                "center": slot["center"],
                "rect": slot["rect"]
            })
            
            # Debug Çizimi (Sadece bu kutuyu boya)
            if debug_img is not None:
                cv2.rectangle(debug_img, (sx, sy), (sx+sw, sy+sh), (0, 255, 0), 1)
                cv2.putText(debug_img, f"%{int(ratio*100)}", (sx, sy-2), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0,255,255), 1)

        if False:  # PRODUCTION: cv2.imshow opencv-python-headless'ta yok, debug devre dışı
            if self.show_debug and debug_img is not None:
                cv2.imshow("SEGE FIXED MODE", debug_img)

        self.member_ratios = [m["ratio"] for m in members_status]
        low_hp_members = [m for m in members_status if m["ratio"] < 0.98]
        now = time.time()
        
        # --- HEAL KARARLARI (AYNI) ---
        p10k_targets = [m for m in low_hp_members if m["ratio"] <= self.p10k_hp]
        if len(p10k_targets) >= self.p10k_count:
            if self.p10k_active and (now - self.last_cast_time["p10k"] > self.COOLDOWNS["p10k"]):
                print(f"[PARTY] Toplu 10k! ({len(p10k_targets)} kişi)")
                self._cast(self.p10k_f, self.p10k_d); self.last_cast_time["p10k"] = now; return

        rest_targets = [m for m in low_hp_members if m["ratio"] <= self.rest_hp]
        if len(rest_targets) >= self.rest_count:
            if self.rest_active and (now - self.last_cast_time["rest"] > self.COOLDOWNS["rest"]):
                print(f"[PARTY] Toplu Restore! ({len(rest_targets)} kişi)")
                self._cast(self.rest_f, self.rest_d); self.last_cast_time["rest"] = now; return

        if low_hp_members:
            target = min(low_hp_members, key=lambda x: x["ratio"])
            ratio = target["ratio"]
            if self.s10k_active and ratio <= self.s10k_hp:
                if now - self.last_cast_time["s10k"] > self.COOLDOWNS["s10k"]:
                    print(f"[PARTY] Tekli 10k -> %{ratio*100:.0f}")
                    self._click_and_cast(target["center"], self.s10k_f, self.s10k_d); self.last_cast_time["s10k"] = now; return

            if self.s1920_active and ratio <= self.s1920_hp:
                if now - self.last_cast_time["s1920"] > self.COOLDOWNS["s1920"]:
                    print(f"[PARTY] Tekli 1920 -> %{ratio*100:.0f}")
                    self._click_and_cast(target["center"], self.s1920_f, self.s1920_d); self.last_cast_time["s1920"] = now; return

    def _cast(self, f, d):
        if self._stop_event.is_set(): return
        if f > 0:
            sc = F_SCANCODES.get(f)
            if self._driver: self._driver.tusbas(sc, 0.02)
            time.sleep(0.05)
        sc_d = DIGIT_SCANCODES.get(d)
        if self._driver: self._driver.tusbas(sc_d, 0.02)
        time.sleep(0.4) 

    def _click_and_cast(self, center_pos, f, d):
        if self._stop_event.is_set(): return
        tx, ty = center_pos
        try:
            # Mouse Koruması: Basılıysa bırak
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
    
    def set_value(self, ratio):
        self.ratio = max(0.0, min(1.0, ratio))
        self.update()

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        rect = self.rect()
        w = int(rect.width() * self.ratio)
        col = QColor(255, 0, 0)
        p.fillRect(rect.x(), rect.y(), w, rect.height(), col)
        p.setPen(Qt.white); p.setFont(self.font())
        p.drawText(rect, Qt.AlignCenter, f"P{self.index+1}: %{int(self.ratio*100)}")

class PriestPartyHealSettingsDialog(QDialog):
    def __init__(self, parent, config, macro):
        super().__init__(parent)
        self.setWindowTitle("PARTY HEAL AYARLARI")
        self.setModal(True); self.resize(750, 500)
        self.config = config; self.macro = macro
        self.capture_hotkey = False
        
        layout = QVBoxLayout(self)
        
        # --- HOTKEY SEÇİMİ ---
        h_key = QHBoxLayout()
        h_key.addWidget(QLabel("BAŞLATMA TUŞU:"))
        self.txt_hotkey = QLineEdit(self.config.get("hotkey", "PAGE UP"))
        self.txt_hotkey.setReadOnly(True)
        btn_hk = QPushButton("SEÇ")
        btn_hk.clicked.connect(self.start_hotkey_capture)
        h_key.addWidget(self.txt_hotkey); h_key.addWidget(btn_hk)
        layout.addLayout(h_key)

        # --- ALAN SEÇİMİ ---
        grp_area = QGroupBox("1. Tarama Alanı")
        ga = QHBoxLayout(grp_area)
        self.lbl_area = QLabel(f"Seçili Alan: {self.config.get('region', 'YOK')}")
        btn_scan = QPushButton("PARTY BARINI SEÇ"); btn_scan.clicked.connect(self.select_area)
        btn_debug = QPushButton("GÖRÜŞÜ AÇ (DEBUG)"); btn_debug.setStyleSheet("background-color: #d500f9; color: white;")
        btn_debug.clicked.connect(self.toggle_debug)
        
        # Manuel resetleme butonu (Party değişirse)
        btn_reset = QPushButton("YENİDEN TARA"); btn_reset.clicked.connect(self.reset_slots)
        
        ga.addWidget(self.lbl_area); ga.addWidget(btn_scan); ga.addWidget(btn_reset); ga.addWidget(btn_debug)
        layout.addWidget(grp_area)

        # --- SKILL AYARLARI ---
        grp_skill = QGroupBox("2. Skill Ayarları")
        gl = QGridLayout(grp_skill)
        
        headers = ["SKILL ADI", "AKTİF", "F SAYFASI", "TUŞ (0-9)", "HP TETİK (%)", "TETİK ADET"]
        for i, h in enumerate(headers): gl.addWidget(QLabel(h, styleSheet="color:#00e676; font-weight:bold;"), 0, i)

        self.rows = {}
        skills = [("single_1920", "Tekli 1920 Heal", False), ("party_10k", "Toplu 10k Heal", True), ("party_restore","Toplu Restore", True), ("single_10k", "Tekli 10k Heal", False)]

        for idx, (key, label, has_count) in enumerate(skills, 1):
            data = self.config.get(key, {})
            chk = QCheckBox(label); chk.setChecked(data.get("active", False))
            cmb_f = QComboBox(); cmb_f.addItem("F YOK", 0)
            for i in range(1, 10): cmb_f.addItem(f"F{i}", i)
            idx_f = cmb_f.findData(data.get("f", 1)); cmb_f.setCurrentIndex(idx_f if idx_f>=0 else 0)
            cmb_d = QComboBox(); 
            for i in range(10): cmb_d.addItem(str(i), i)
            cmb_d.setCurrentIndex(data.get("d", 1))
            sp_hp = QDoubleSpinBox(); sp_hp.setRange(1, 100); sp_hp.setValue(data.get("hp", 0.8)*100)
            sp_count = QSpinBox(); sp_count.setRange(1, 8)
            if has_count: sp_count.setValue(data.get("count", 2))
            else: sp_count.setValue(1); sp_count.setEnabled(False)

            gl.addWidget(chk, idx, 0); gl.addWidget(cmb_f, idx, 2)
            gl.addWidget(cmb_d, idx, 3); gl.addWidget(sp_hp, idx, 4)
            gl.addWidget(sp_count, idx, 5)
            self.rows[key] = (chk, cmb_f, cmb_d, sp_hp, sp_count)

        layout.addWidget(grp_skill)
        
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
            # Alan değişince sabit slotları sıfırla ki tekrar tarasın
            self.macro.fixed_slots = []
        self.show()

    def reset_slots(self):
        # Manuel olarak slotları sıfırla ve tekrar tarat
        self.macro.fixed_slots = []
        count = self.macro.calibrate()
        QMessageBox.information(self, "Bilgi", f"Yeniden tarandı. {count} kişi bulundu.")

    def toggle_debug(self):
        self.macro.show_debug = not self.macro.show_debug
        QMessageBox.information(self, "Debug", f"Görsel Debug Modu: {'AÇIK' if self.macro.show_debug else 'KAPALI'}\nMakro çalışırken pencere açılacak.")

    def start_hotkey_capture(self):
        self.capture_hotkey = True
        self.txt_hotkey.setText("BAS...")
        self.grabKeyboard()

    def keyPressEvent(self, e):
        if self.capture_hotkey:
            k = e.text().upper()
            if not k:
                if e.key() == Qt.Key_PageUp: k = "PAGE UP"
                elif e.key() == Qt.Key_PageDown: k = "PAGE DOWN"
                elif e.key() == Qt.Key_F10: k = "F10"
            if k:
                self.txt_hotkey.setText(k)
                self.capture_hotkey = False
                self.releaseKeyboard()
        else: super().keyPressEvent(e)

    def accept(self):
        self.config["hotkey"] = self.txt_hotkey.text()
        for key, (chk, cf, cd, shp, scnt) in self.rows.items():
            self.config[key] = {
                "active": chk.isChecked(), "f": cf.currentData(), "d": int(cd.currentText()),
                "hp": shp.value() / 100.0, "count": scnt.value()
            }
        super().accept()

class PriestPartyHealWidget(QFrame):
    update_signal = pyqtSignal()

    def __init__(self, parent=None, macro_instance=None, config=None):
        super().__init__(parent)
        self.macro = macro_instance or PriestPartyHealMacro()
        self.config = config or {}
        self.macro.update_config(self.config)
        self.listen_active = False
        
        self.bars = []
        self.bar_container = QWidget()
        self.bar_layout = QVBoxLayout(self.bar_container)
        self.bar_layout.setContentsMargins(0, 5, 0, 5)
        self.bar_layout.setSpacing(2)
        
        self.update_signal.connect(self._safe_update)
        self.setup_ui(); self._safe_update()

    def setup_ui(self):
        self.setFrameShape(QFrame.Box)
        self.setMaximumWidth(260)
        # Stil tanımlaması
        self.setStyleSheet("""
            QFrame { 
                background-color: #101010; 
                border: 1px solid #444; 
                border-radius: 4px; 
            }
        """)

        v = QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(4)

        # ---------------- HEADER (4 PNG'Lİ KISIM) ----------------
        header = QHBoxLayout()
        header.setSpacing(6)

        icon_row = QHBoxLayout()
        icon_row.setSpacing(3)

        # İstediğiniz 4 adet ikonun yolları
        icon_paths = [
            "icons/priest/45heal.png",
            "icons/priest/party10k.png",
            "icons/priest/75restore.png",
            "icons/priest/tek10k.png"
        ]

        for path in icon_paths:
            lbl = QLabel()
            lbl.setFixedSize(25, 25)
            pix = QPixmap(path)
            if not pix.isNull():
                lbl.setPixmap(
                    pix.scaled(25, 25, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
            else:
                # Resim bulunamazsa yedek emoji
                lbl.setText("🚑")
                lbl.setStyleSheet("border:none; font-size:16px;")
            icon_row.addWidget(lbl)

        header.addLayout(icon_row)
        header.addStretch(1)

        title = QLabel("PARTY HEAL ASSIST")
        title.setObjectName("MinorHeaderLabel")
        header.addWidget(title)

        v.addLayout(header)

        self.btn_listen = QPushButton("TUŞ DİNLEMEYİ BAŞLAT")
        self.btn_listen.setObjectName("ThreeFiveListenButton")
        self.btn_listen.clicked.connect(self.toggle_listen)
        v.addWidget(self.btn_listen)

        self.lbl_status = QLabel("PASİF"); self.lbl_status.setObjectName("MinorStatusLabel")
        v.addWidget(self.lbl_status)
        v.addWidget(self.bar_container)

        h_hk = QHBoxLayout(); h_hk.addWidget(QLabel("TUŞ:"))
        self.lbl_hk = QLabel(self.config.get("hotkey", "PAGE UP")); self.lbl_hk.setObjectName("HotkeyLabel")
        h_hk.addWidget(self.lbl_hk)
        v.addLayout(h_hk)

        btn_set = QPushButton("AYARLAR / ALAN SEÇ"); btn_set.setObjectName("MinorSettingsButton")
        btn_set.clicked.connect(self.open_settings)
        v.addWidget(btn_set)

    def open_settings(self):
        dlg = PriestPartyHealSettingsDialog(self, self.config, self.macro)
        if dlg.exec_():
            self.config = dlg.config; self.macro.update_config(self.config)
            self.lbl_hk.setText(self.config.get("hotkey"))
            if self.listen_active: self.toggle_listen(); self.toggle_listen()

    def toggle_listen(self):
        if not keyboard:
            QMessageBox.warning(self, "Hata", "Keyboard modülü eksik!")
            return

        if not self.listen_active:
            hk = self.config.get("hotkey", "PAGE UP").lower()
            try:
                self._hooks = []
                self._hooks.append(keyboard.on_press_key(hk, lambda e: self.on_hotkey(), suppress=False))
                self.listen_active = True
            except Exception as e:
                print(f"[PARTY] Hotkey hatası: {e}")
                self.listen_active = False
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
        if not self.listen_active:
            self.lbl_status.setText("PASİF"); self.lbl_status.setStyleSheet("color:#ff5555;font-weight:bold;")
            self.btn_listen.setText("TUŞ DİNLEMEYİ BAŞLAT"); self.btn_listen.setProperty("active", False)
        else:
            if self.macro.is_running:
                count = len(self.macro.member_ratios)
                self.lbl_status.setText(f"ÇALIŞIYOR (ÜYE: {count})")
                self.lbl_status.setStyleSheet("color:#00ff4c;font-weight:bold;")
                self.btn_listen.setText("TUŞ DİNLEMEYİ DURDUR"); self.btn_listen.setProperty("active", True)
            else:
                self.lbl_status.setText("BEKLİYOR (TUŞA BAS)")
                self.lbl_status.setStyleSheet("color:#ffff55;font-weight:bold;")
                self.btn_listen.setText("TUŞ DİNLEMEYİ DURDUR"); self.btn_listen.setProperty("active", True)
        
        self.btn_listen.style().unpolish(self.btn_listen); self.btn_listen.style().polish(self.btn_listen)
        
        current_ratios = self.macro.member_ratios
        while len(self.bars) < len(current_ratios):
            bar = PartyMemberBar(len(self.bars))
            self.bar_layout.addWidget(bar); self.bars.append(bar)
            
        for i, bar in enumerate(self.bars):
            if i < len(current_ratios):
                bar.show(); bar.set_value(current_ratios[i])
            else: bar.hide()

        if self.listen_active: QTimer.singleShot(100, self._safe_update)
