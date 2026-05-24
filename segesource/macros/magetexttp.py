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
import re
import difflib 

# Tesseract OCR
try:
    import pytesseract
    from pytesseract import Output
    # Tesseract yolunu buraya yaz
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    HAS_OCR = True
except ImportError:
    HAS_OCR = False

# PyQt5
from PyQt5.QtWidgets import (
    QDialog, QGridLayout, QLabel, QComboBox, 
    QLineEdit, QPushButton, QDoubleSpinBox, 
    QDialogButtonBox, QHBoxLayout, QWidget,
    QFrame, QVBoxLayout, QSizePolicy, QMessageBox,
    QCheckBox, QGroupBox, QPlainTextEdit
)
from PyQt5.QtGui import QPainter, QPen, QColor, QPixmap
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
SC_ENTER = 0x1C; SC_O = 0x18; SC_K = 0x25

# =========================================================
# 1. LOGIC (MAKRO MOTORU)
# =========================================================
class MageStaffSettingsDialog(QDialog):
    def __init__(self, parent=None, current_config=None):
        super().__init__(parent)
        self.setWindowTitle("MAGE STAFF AYARLARI")
        self.setModal(True)
        self._capture_next_key = False
        
        if current_config is None: current_config = {}

        key = current_config.get("key", "Z")
        z_enabled = bool(current_config.get("z_enabled", False))
        z_key_duration = float(current_config.get("z_key_duration", 0.05))
        key_2_duration = float(current_config.get("key_2_duration", 0.05))
        key_r_duration = float(current_config.get("key_r_duration", 0.02))
        skill_key = current_config.get("skill_key", 1)
        order = current_config.get("order", "2rr")
        mode = current_config.get("mode", "toggle")
        skill_bar = current_config.get("skill_bar", "FYOK")

        layout = QGridLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # 0. Aktif Tuş
        layout.addWidget(QLabel("BAŞLATMA TUŞU:"), 0, 0)
        self.edit_hotkey = QLineEdit(key)
        self.edit_hotkey.setReadOnly(True)
        btn_cap = QPushButton("TUŞ SEÇ")
        btn_cap.clicked.connect(self.start_capture_hotkey)
        h_key = QHBoxLayout(); h_key.addWidget(self.edit_hotkey); h_key.addWidget(btn_cap)
        layout.addLayout(h_key, 0, 1)

        # 1. Mod
        layout.addWidget(QLabel("MOD:"), 1, 0)
        self.cmb_mode = QComboBox(); self.cmb_mode.addItems(["TOGGLE (AÇ/KAPA)", "HOLD (BASILI TUT)"])
        idx_m = 0 if mode == "toggle" else 1
        self.cmb_mode.setCurrentIndex(idx_m)
        layout.addWidget(self.cmb_mode, 1, 1)

        # 2. Skill Bar
        layout.addWidget(QLabel("F BAR:"), 2, 0)
        self.cmb_bar = QComboBox(); self.cmb_bar.addItems(["FYOK"] + [f"F{i}" for i in range(1,9)])
        self.cmb_bar.setCurrentText(skill_bar)
        layout.addWidget(self.cmb_bar, 2, 1)

        # 3. Z Ayarı
        self.chk_z = QCheckBox("OTO Z BAS")
        self.chk_z.setChecked(z_enabled)
        layout.addWidget(self.chk_z, 3, 0)
        self.spin_z = QDoubleSpinBox(); self.spin_z.setRange(0.01, 1.0); self.spin_z.setValue(z_key_duration)
        layout.addWidget(self.spin_z, 3, 1)

        # 4. Skill Slotu
        layout.addWidget(QLabel("STAFF SKILL (0-9):"), 4, 0)
        self.cmb_skill_key = QComboBox(); self.cmb_skill_key.addItems([str(i) for i in range(10)])
        self.cmb_skill_key.setCurrentText(str(skill_key))
        layout.addWidget(self.cmb_skill_key, 4, 1)

        # 5. Skill Süresi
        layout.addWidget(QLabel("SKILL SÜRESİ (SN):"), 5, 0)
        self.spin_s = QDoubleSpinBox(); self.spin_s.setRange(0.01, 1.0); self.spin_s.setValue(key_2_duration)
        layout.addWidget(self.spin_s, 5, 1)

        # 6. R Süresi
        layout.addWidget(QLabel("R SÜRESİ (SN):"), 6, 0)
        self.spin_r = QDoubleSpinBox(); self.spin_r.setRange(0.01, 1.0); self.spin_r.setValue(key_r_duration)
        layout.addWidget(self.spin_r, 6, 1)

        # 7. Kombo Tipi
        layout.addWidget(QLabel("KOMBO TİPİ:"), 7, 0)
        self.cmb_order = QComboBox()
        self.cmb_order.addItem("Skill - R - R", "2rr")
        self.cmb_order.addItem("R - R - Skill", "rr2")
        self.cmb_order.addItem("W - R - Skill (Slide)", "wr2")
        self.cmb_order.addItem("W-R-Skill-S-R-Skill", "wr2sr2")
        idx_o = self.cmb_order.findData(order)
        if idx_o >= 0: self.cmb_order.setCurrentIndex(idx_o)
        layout.addWidget(self.cmb_order, 7, 1)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        layout.addWidget(btns, 8, 0, 1, 2)

    def start_capture_hotkey(self):
        self._capture_next_key = True; self.edit_hotkey.setText("BAS...")
    
    def keyPressEvent(self, e):
        if self._capture_next_key:
            k = e.text().upper()
            if not k:
                if e.key() == Qt.Key_F1: k = "F1"
                elif e.key() == Qt.Key_CapsLock: k = "CAPS LOCK"
            if k:
                self.edit_hotkey.setText(k)
                self._capture_next_key = False
            return
        super().keyPressEvent(e)

    def accept(self):
        self.result_config = {
            "key": self.edit_hotkey.text(),
            "mode": "toggle" if self.cmb_mode.currentIndex() == 0 else "hold",
            "skill_bar": self.cmb_bar.currentText(),
            "z_enabled": self.chk_z.isChecked(),
            "z_key_duration": self.spin_z.value(),
            "skill_key": int(self.cmb_skill_key.currentText()),
            "key_2_duration": self.spin_s.value(),
            "key_r_duration": self.spin_r.value(),
            "order": self.cmb_order.currentData()
        }
        super().accept()



class MageTextTpMacro:
    def __init__(self):
        self.chat_region = None
        self.party_region = None
        self.keywords = ["44", "tp", "çek", "cek", "tptp", "4444"]
        self.processed_logs = [] 
        
        # Ayarlar
        self.skill_f = 1
        self.skill_d = 1
        
        self._driver = _ClicksendKeyboardDriver() if _ClicksendKeyboardDriver else None
        self._mouse = _ClicksendMouseDriver() if _ClicksendMouseDriver else None
        self._sct = mss.mss()
        
        self._running = False
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        
        # --- DÜZELTME: KÜÇÜK HARFLER EKLENDİ ---
        self.ocr_config_party = r'--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
        self.ocr_config_chat = r'--psm 7'

    def update_config(self, cfg):
        with self._lock:
            if cfg.get("region_chat"): self.chat_region = cfg["region_chat"]
            if cfg.get("region_party"): self.party_region = cfg["region_party"]
            
            kw = cfg.get("keywords", "44,tp")
            if isinstance(kw, str):
                self.keywords = [k.strip().lower() for k in kw.split(",")]
            
            self.skill_f = cfg.get("f", 1)
            self.skill_d = cfg.get("d", 1)

    def _preprocess_image(self, img):
        """
        Görüntü İşleme (Hassasiyet Artırıldı)
        """
        # Büyütme (Scale x3)
        scale = 3
        width = int(img.shape[1] * scale)
        height = int(img.shape[0] * scale)
        resized = cv2.resize(img, (width, height), interpolation=cv2.INTER_CUBIC)
        
        # Griye Çevir
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)

        # --- DÜZELTME: EŞİK DEĞERİ DÜŞÜRÜLDÜ (145 -> 115) ---
        # Bu sayede biraz daha gri/sönük duran küçük harfler de yakalanacak.
        _, binary = cv2.threshold(gray, 140, 255, cv2.THRESH_BINARY)
        
        # Harfleri Birleştir (Dilation)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 3))
        dilated = cv2.dilate(binary, kernel, iterations=1)
        
        # Konturları Bul
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        text_blocks = []
        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            
            # --- FİLTRELER ---
            if w < 25 or h < 10: continue # Çok küçükleri at
            if h > w: continue # Dikey çizgileri at
            
            text_blocks.append((x, y, w, h))
        
        # Yukarıdan aşağıya sırala
        text_blocks.sort(key=lambda b: b[1])
        
        # OCR için ters çevrilmiş (Siyah yazı / Beyaz zemin) görüntü
        ocr_ready_img = cv2.bitwise_not(binary)
        
        return text_blocks, ocr_ready_img, scale

    def debug_party_read(self):
        if not self.party_region: return
        x, y, w, h = self.party_region
        
        try:
            with mss.mss() as sct:
                scr = np.array(sct.grab({"left": x, "top": y, "width": w, "height": h}))
            
            scr_bgr = cv2.cvtColor(scr, cv2.COLOR_BGRA2BGR)
            debug_view = scr_bgr.copy()
            
            text_blocks, processed_img, scale = self._preprocess_image(scr_bgr)
            
            print(f"--- PARTY OKUMA TESTİ ({len(text_blocks)} Blok) ---")
            
            # Görselleştirme için küçültülmüş processed image
            debug_bw_view = cv2.resize(processed_img, (0,0), fx=0.5, fy=0.5)

            for i, (bx, by, bw, bh) in enumerate(text_blocks):
                roi = processed_img[by:by+bh, bx:bx+bw]
                padded = cv2.copyMakeBorder(roi, 10, 10, 10, 10, cv2.BORDER_CONSTANT, value=[255, 255, 255])
                
                text = pytesseract.image_to_string(padded, config=self.ocr_config_party, lang='eng')
                
                # --- DÜZELTME: SADECE TEMİZLE, BÜYÜTME ---
                # .upper() kaldırdık ki küçük harf ile de eşleşebilsin, ama karşılaştırırken upper yapacağız.
                clean_name = re.sub(r'[^a-zA-Z0-9]', '', text)
                
                # Orijinal resim üzerine çizim
                orig_x = int(bx / scale)
                orig_y = int(by / scale)
                orig_w = int(bw / scale)
                orig_h = int(bh / scale)
                
                cv2.rectangle(debug_view, (orig_x, orig_y), (orig_x+orig_w, orig_y+orig_h), (0, 255, 0), 2)
                
                status = clean_name if len(clean_name) > 2 else "[...]"
                print(f"Slot {i+1}: {status} (Ham: {text.strip()})")
                
                cv2.putText(debug_view, f"{i+1}:{status}", (orig_x, orig_y - 5), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)

            
            if False:  # opencv-headless: imshow/waitKey/destroyAllWindows yok
                cv2.imshow("TEST SONUCU (Q ile kapat)", debug_view)
                cv2.waitKey(0)
                cv2.destroyAllWindows()
            
        except Exception as e:
            print(f"Debug hatası: {e}")

    def _get_party_members_fixed(self):
        if not self.party_region: return []
        x, y, w, h = self.party_region
        
        try:
            with mss.mss() as sct:
                scr = np.array(sct.grab({"left": x, "top": y, "width": w, "height": h}))
            scr_bgr = cv2.cvtColor(scr, cv2.COLOR_BGRA2BGR)
            
            text_blocks, processed_img, scale = self._preprocess_image(scr_bgr)
            
            members = []
            for (bx, by, bw, bh) in text_blocks:
                roi = processed_img[by:by+bh, bx:bx+bw]
                padded = cv2.copyMakeBorder(roi, 10, 10, 10, 10, cv2.BORDER_CONSTANT, value=[255, 255, 255])
                
                text = pytesseract.image_to_string(padded, config=self.ocr_config_party, lang='eng')
                clean_name = re.sub(r'[^a-zA-Z0-9]', '', text) # upper() yapmadık, olduğu gibi al
                
                if len(clean_name) >= 3:
                    orig_x = int((bx + bw/2) / scale)
                    orig_y = int((by + bh/2) / scale)
                    center_x = x + orig_x
                    center_y = y + orig_y
                    members.append({"name": clean_name, "pos": (center_x, center_y)})
            return members
        except: return []

    def _scan_chat_for_request(self):
        if not self.chat_region: return None
        x, y, w, h = self.chat_region
        
        try:
            with mss.mss() as sct:
                scr = np.array(sct.grab({"left": x, "top": y, "width": w, "height": h}))
            scr_bgr = cv2.cvtColor(scr, cv2.COLOR_BGRA2BGR)
            
            # Chatte her şeyi okuyalım
            gray = cv2.cvtColor(scr_bgr, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray, 90, 255, cv2.THRESH_BINARY)
            processed = cv2.bitwise_not(thresh)
            processed = cv2.resize(processed, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
            
            text = pytesseract.image_to_string(processed, lang='eng', config=self.ocr_config_chat)
            
            for line in text.split('\n'):
                line = line.strip()
                if not line: continue
                
                split_char = None
                if ":" in line: split_char = ":"
                elif ">" in line: split_char = ">"
                
                if split_char:
                    parts = line.split(split_char, 1)
                    nick_raw = parts[0]
                    msg = parts[1].lower().strip()
                    nick = re.sub(r'[^a-zA-Z0-9]', '', nick_raw) # Burada da upper() kaldırdım, kıyaslarken yapacağız
                    
                    log_id = f"{nick}_{msg}_{int(time.time() / 15)}" 
                    if log_id in self.processed_logs: continue
                    
                    for kw in self.keywords:
                        if kw in msg:
                            self.processed_logs.append(log_id)
                            if len(self.processed_logs) > 50: self.processed_logs.pop(0)
                            return nick
        except: pass
        return None

    def start(self):
        if not self.chat_region or not self.party_region: return
        if not HAS_OCR: return
        self._stop_event.clear(); self._running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self): self._stop_event.set(); self._running = False
    def toggle(self): self.stop() if self._running else self.start()

    def _loop(self):
        print("[YAZI TP] Başladı.")
        while not self._stop_event.is_set():
            try:
                requester_name = self._scan_chat_for_request()
                if requester_name:
                    print(f"[TP İSTEĞİ] {requester_name}")
                    
                    party_members = self._get_party_members_fixed()
                    target_pos = None
                    best_ratio = 0
                    
                    for member in party_members:
                        # Kıyaslarken ikisini de UPPER yapıyoruz
                        ratio = difflib.SequenceMatcher(None, requester_name.upper(), member["name"].upper()).ratio()
                        
                        # Debug
                        print(f"Kıyas: {requester_name} vs {member['name']} -> {ratio:.2f}")

                        if ratio > 0.70 and ratio > best_ratio:
                            best_ratio = ratio
                            target_pos = member["pos"]
                    
                    if target_pos:
                        print(f"[TP] Çekiliyor... ({best_ratio:.2f})")
                        self._perform_tp(target_pos)
                    else:
                        print(f"[TP HATA] {requester_name} partide bulunamadı.")
            except Exception as e:
                print(f"[TP ERROR] {e}")
            time.sleep(1.0) 
        print("[YAZI TP] Durdu.")

    def _perform_tp(self, pos):
        orig_x, orig_y = pyautogui.position()
        tx, ty = pos
        
        try:
             pyautogui.mouseUp()
             if self._mouse: self._mouse.mouse_left_up(0,0)
        except: pass

        if self._mouse: self._mouse.leftclick(0.05, int(tx), int(ty))
        else: pyautogui.click(tx, ty)
        time.sleep(0.1)
        
        if self.skill_f > 0:
            sc_f = F_SCANCODES.get(self.skill_f)
            if self._driver: self._driver.tusbas(sc_f, 0.02)
            time.sleep(0.05)
        
        sc_d = DIGIT_SCANCODES.get(self.skill_d)
        if self._driver: self._driver.tusbas(sc_d, 0.02)
        time.sleep(0.2)
        
        try:
            if self._mouse and hasattr(self._mouse, 'move'): 
                self._mouse.move(orig_x, orig_y)
            else: 
                pyautogui.moveTo(orig_x, orig_y)
        except: 
            pyautogui.moveTo(orig_x, orig_y)
            
        self._type_ok()

    def _type_ok(self):
        if self._driver:
            self._driver.tusbas(SC_ENTER, 0.05); time.sleep(0.1)
            self._driver.tusbas(SC_O, 0.05); time.sleep(0.05) 
            self._driver.tusbas(SC_K, 0.05); time.sleep(0.05) 
            self._driver.tusbas(SC_ENTER, 0.05)
        else:
            pyautogui.press('enter'); time.sleep(0.1)
            pyautogui.write('ok'); time.sleep(0.1)
            pyautogui.press('enter')

# =========================================================
# 2. GUI - AYARLAR
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
            p.setCompositionMode(QPainter.CompositionMode_SourceOver); p.setPen(QPen(Qt.cyan, 2)); p.drawRect(x,y,w,h)

class MageTextTpSettingsDialog(QDialog):
    def __init__(self, parent, config, macro):
        super().__init__(parent)
        self.setWindowTitle("YAZI İLE TP AYARLARI")
        self.setModal(True); self.resize(500, 500)
        self.config = config
        self.macro = macro
        self.capture_hotkey = False
        
        layout = QVBoxLayout(self)
        
        if not HAS_OCR:
            lbl_err = QLabel("UYARI: Tesseract OCR Bulunamadı!\nBu özellik çalışmayabilir.")
            lbl_err.setStyleSheet("color: red; font-weight: bold;")
            layout.addWidget(lbl_err)

        grp_hot = QGroupBox("1. Başlatma Tuşu")
        gh = QHBoxLayout(grp_hot)
        self.txt_hotkey = QLineEdit(self.config.get("hotkey", "PAGE DOWN"))
        self.txt_hotkey.setReadOnly(True)
        btn_hk = QPushButton("TUŞ SEÇ"); btn_hk.clicked.connect(self.start_hotkey_capture)
        gh.addWidget(self.txt_hotkey); gh.addWidget(btn_hk)
        layout.addWidget(grp_hot)

        grp_area = QGroupBox("2. Alan Seçimleri")
        ga = QGridLayout(grp_area)
        self.lbl_chat = QLabel(f"Chat: {self.config.get('region_chat', 'Seçilmedi')}")
        btn_chat = QPushButton("CHAT KUTUSUNU SEÇ"); btn_chat.clicked.connect(self.sel_chat)
        self.lbl_party = QLabel(f"Party: {self.config.get('region_party', 'Seçilmedi')}")
        btn_party = QPushButton("PARTY LİSTESİNİ SEÇ"); btn_party.clicked.connect(self.sel_party)
        btn_test = QPushButton("PARTY OKUMA TESTİ (GÖRSEL)"); btn_test.setStyleSheet("background: #d500f9; color: white;")
        btn_test.clicked.connect(self.test_party)
        ga.addWidget(self.lbl_chat, 0, 0); ga.addWidget(btn_chat, 0, 1)
        ga.addWidget(self.lbl_party, 1, 0); ga.addWidget(btn_party, 1, 1)
        ga.addWidget(btn_test, 2, 0, 1, 2)
        layout.addWidget(grp_area)
        
        grp_kw = QGroupBox("3. Anahtar Kelimeler")
        gw = QVBoxLayout(grp_kw)
        self.txt_kw = QPlainTextEdit()
        kw_list = self.config.get("keywords", ["44", "tp"])
        if isinstance(kw_list, list): kw_str = ", ".join(kw_list)
        else: kw_str = kw_list
        self.txt_kw.setPlainText(kw_str)
        self.txt_kw.setFixedHeight(50)
        gw.addWidget(self.txt_kw)
        layout.addWidget(grp_kw)
        
        grp_skill = QGroupBox("4. TP Skill Ayarı")
        gs = QHBoxLayout(grp_skill)
        self.cmb_f = QComboBox(); self.cmb_f.addItem("F YOK", 0)
        for i in range(1, 9): self.cmb_f.addItem(f"F{i}", i)
        self.cmb_f.setCurrentIndex(self.cmb_f.findData(self.config.get("f", 1)))
        self.cmb_d = QComboBox()
        for i in range(10): self.cmb_d.addItem(str(i), i)
        self.cmb_d.setCurrentIndex(self.config.get("d", 1))
        gs.addWidget(QLabel("F Sayfası:")); gs.addWidget(self.cmb_f)
        gs.addWidget(QLabel("Tuş:")); gs.addWidget(self.cmb_d)
        layout.addWidget(grp_skill)
        
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def sel_chat(self):
        self.hide(); time.sleep(0.2)
        d = RectSelectDialog()
        if d.exec_() == QDialog.Accepted:
            self.config["region_chat"] = d.result
            self.lbl_chat.setText(f"Chat: {d.result}")
        self.show()

    def sel_party(self):
        self.hide(); time.sleep(0.2)
        d = RectSelectDialog()
        if d.exec_() == QDialog.Accepted:
            self.config["region_party"] = d.result
            self.lbl_party.setText(f"Party: {d.result}")
            self.macro.party_region = d.result 
        self.show()

    def test_party(self):
        self.macro.party_region = self.config.get("region_party")
        if not self.macro.party_region:
            QMessageBox.warning(self, "Hata", "Önce Party Alanını Seçin!")
            return
        self.macro.debug_party_read()

    def start_hotkey_capture(self):
        self.capture_hotkey = True; self.txt_hotkey.setText("BAS..."); self.grabKeyboard()

    def keyPressEvent(self, e):
        if self.capture_hotkey:
            k = e.text().upper()
            if not k:
                if e.key() == Qt.Key_PageUp: k = "PAGE UP"
                elif e.key() == Qt.Key_PageDown: k = "PAGE DOWN"
            if k:
                self.txt_hotkey.setText(k); self.capture_hotkey = False; self.releaseKeyboard()
        else: super().keyPressEvent(e)

    def accept(self):
        self.config["keywords"] = self.txt_kw.toPlainText()
        self.config["f"] = self.cmb_f.currentData()
        self.config["d"] = int(self.cmb_d.currentText())
        self.config["hotkey"] = self.txt_hotkey.text()
        super().accept()

class MageTextTpWidget(QFrame):
    update_signal = pyqtSignal()

    def __init__(self, parent=None, macro_instance=None, config=None):
        super().__init__(parent)
        self.macro = macro_instance or MageTextTpMacro()
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

        # HEADER (💬 Emoji + tp.png + Başlık)
        h = QHBoxLayout()
        h.setSpacing(4)
        
        # 1. Mevcut Emoji
        icon_emoji = QLabel("💬")
        icon_emoji.setStyleSheet("font-size:16px; border:none; background:transparent;")
        h.addWidget(icon_emoji)
        
        # 2. tp.png İkonu
        import os
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(22, 22)
        self.icon_label.setAlignment(Qt.AlignCenter)
        
        icon_path = os.path.join("icons", "mage", "tp.png")
        pix = QPixmap(icon_path)
        if not pix.isNull():
            self.icon_label.setPixmap(pix.scaled(22, 22, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.icon_label.setText("🌀") # png yoksa yedek
            self.icon_label.setStyleSheet("font-size:14px; border:none;")
        h.addWidget(self.icon_label)
        
        h.addStretch() # Başlığı sağa yasla
        
        title = QLabel("YAZI İLE TP (CHAT)")
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

        # FOOTER (Alt Satır - Diğerleriyle birebir aynı yapı)
        row = QHBoxLayout()
        row.setSpacing(4)
        
        row.addWidget(QLabel("AKTİF TUŞ:"))
        
        self.lbl_hk = QLabel(self.config.get("hotkey", "PAGE DOWN"))
        self.lbl_hk.setObjectName("HotkeyLabel")
        self.lbl_hk.setAlignment(Qt.AlignCenter)
        row.addWidget(self.lbl_hk)
        
        btn_set = QPushButton("⚙ AYARLAR")
        btn_set.setObjectName("MinorSettingsButton")
        btn_set.clicked.connect(self.settings)
        row.addWidget(btn_set)
        
        v.addLayout(row)

        # OCR Uyarı Mesajı (Varsa altına ekle)
        if not HAS_OCR:
            lbl_err = QLabel("⚠️ OCR EKSİK!")
            lbl_err.setStyleSheet("color:red; font-weight:bold; font-size:10px;")
            lbl_err.setAlignment(Qt.AlignCenter)
            v.addWidget(lbl_err)

    def settings(self):
        dlg = MageTextTpSettingsDialog(self, self.config, self.macro)
        if dlg.exec_():
            self.config = dlg.config
            self.macro.update_config(self.config)
            self.lbl_hk.setText(self.config.get("hotkey"))
            if self.listen_active: self.toggle_listen(); self.toggle_listen()

    def toggle_listen(self):
        if not HAS_OCR: return QMessageBox.critical(self, "Hata", "Tesseract OCR yüklü değil!")
        if not keyboard: return QMessageBox.warning(self, "Hata", "Keyboard kütüphanesi eksik!")
        if not self.listen_active:
            if not self.config.get("region_chat") or not self.config.get("region_party"):
                return QMessageBox.warning(self, "Eksik", "Alanları seçin!")
            hk = self.config.get("hotkey", "PAGE DOWN").lower()
            try:
                self._hooks = []
                self._hooks.append(keyboard.on_press_key(hk, lambda e: self.on_hotkey(), suppress=False))
                self.listen_active = True
            except Exception as e:
                print(f"[CHAT TP] Hotkey hatası: {e}")
                self.listen_active = False
        else:
            for h in self._hooks: 
                try: keyboard.unhook(h)
                except: pass
            self._hooks = []
            self.listen_active = False
            self.macro.stop()
        self._update_status()

    def on_hotkey(self):
        self.macro.toggle()
        self.update_signal.emit()

    def _update_status(self):
        # Renkler ve metinler tüm modüllerle eşlendi
        if not self.listen_active:
             self.lbl_st.setText("DURUM: PASİF")
             self.lbl_st.setStyleSheet("color:#ff5555; font-weight:bold;")
             self.btn_listen.setText("TUŞ DİNLEMEYİ BAŞLAT")
             self.btn_listen.setProperty("active", False)
        else:
            if self.macro._running:
                self.lbl_st.setText("DURUM: OKUNUYOR...")
                self.lbl_st.setStyleSheet("color:#00ff4c; font-weight:bold;")
                self.btn_listen.setText("DURDUR")
            else:
                self.lbl_st.setText("DURUM: BEKLİYOR")
                self.lbl_st.setStyleSheet("color:#ffff55; font-weight:bold;")
                self.btn_listen.setText("DURDUR")
            self.btn_listen.setProperty("active", True)
            
        self.btn_listen.style().unpolish(self.btn_listen)
        self.btn_listen.style().polish(self.btn_listen)
