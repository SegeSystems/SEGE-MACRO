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
import json
import win32api

# PyQt5
from PyQt5.QtWidgets import (
    QDialog, QGridLayout, QLabel, QComboBox, 
    QLineEdit, QPushButton, QDoubleSpinBox, 
    QDialogButtonBox, QHBoxLayout, QWidget,
    QFrame, QVBoxLayout, QSizePolicy, QMessageBox,
    QCheckBox, QGroupBox, QSpinBox, QApplication, QRubberBand
)
from PyQt5.QtGui import QPixmap, QIcon, QPainter, QPen, QColor, QBrush, QPalette
from PyQt5.QtCore import Qt, QSize, pyqtSignal, QRect, QPoint, QTimer

# Surucu Kontrolu
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

# Tus Kodlari
SC_W = 0x11
SC_S = 0x1F
SC_ESC = 0x01

# =========================================================
# YARDIMCI: ALAN SECICI
# =========================================================
class SnippingOverlay(QWidget):
    def __init__(self, on_selected_callback):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setGeometry(QApplication.desktop().geometry())
        self.setCursor(Qt.CrossCursor)
        self.on_selected_callback = on_selected_callback
        self.start_pos = None
        self.current_pos = None
        self.setStyleSheet("background-color: black;")
        self.setWindowOpacity(0.3) 
        self.show()
        self.activateWindow()
        self.raise_()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.start_pos = event.pos(); self.current_pos = event.pos(); self.update()
        elif event.button() == Qt.RightButton:
            self.close()

    def mouseMoveEvent(self, event):
        if self.start_pos:
            self.current_pos = event.pos(); self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.start_pos:
            x = min(self.start_pos.x(), event.pos().x())
            y = min(self.start_pos.y(), event.pos().y())
            w = abs(self.start_pos.x() - event.pos().x())
            h = abs(self.start_pos.y() - event.pos().y())
            self.close()
            if w > 5 and h > 5:
                rect = QRect(self.mapToGlobal(QPoint(x, y)), QSize(w, h))
                self.on_selected_callback(rect)

    def paintEvent(self, event):
        if self.start_pos and self.current_pos:
            painter = QPainter(self)
            painter.setPen(QPen(QColor(255, 0, 0), 3))
            painter.setBrush(Qt.NoBrush)
            rect = QRect(self.start_pos, self.current_pos).normalized()
            painter.drawRect(rect)

# =========================================================
# 1. LOGIC (MAKRO MOTORU)
# =========================================================
class UpgradeMacro:
    def __init__(self):
        self.config = {}
        self._running = False
        self._stop_event = threading.Event()
        self.kb = _ClicksendKeyboardDriver() if _ClicksendKeyboardDriver else None
        self.mouse = _ClicksendMouseDriver() if _ClicksendMouseDriver else None
        self.images = {}

    def update_config(self, cfg):
        self.config = cfg.copy()

    def _load_resources(self):
        self.images = {}
        keys = ["path_upgrade_btn", "path_bus", "path_confirm1", "path_confirm2", "path_empty"]
        for k in keys:
            path = self.config.get(k)
            if path and os.path.exists(path):
                try:
                    img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
                    if img is not None: self.images[k] = img
                except: pass

    @property
    def is_running(self): return self._running

    def stop(self): self._stop_event.set(); self._running = False

    def toggle(self):
        if self._running: self.stop()
        else:
            self._stop_event.clear(); self._running = True
            threading.Thread(target=self._loop, daemon=True).start()

    def _wait(self, seconds):
        multiplier = float(self.config.get("speed_multiplier", 1.0))
        final_wait = max(0.01, seconds * multiplier)
        time.sleep(final_wait)

    def _press_esc(self):
        if self.kb: self.kb.tusbas(SC_ESC, 0.1)
        else: pyautogui.press('esc')

    def _find(self, sct, template_key, confidence=0.75):
        template = self.images.get(template_key)
        if template is None: return None
        try:
            scr = np.array(sct.grab(sct.monitors[1]))
            gray = cv2.cvtColor(scr, cv2.COLOR_BGRA2GRAY)
            res = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
            _, val, _, loc = cv2.minMaxLoc(res)
            if val > confidence:
                return (loc[0] + template.shape[1]//2, loc[1] + template.shape[0]//2)
        except: pass
        return None

    def _is_slot_empty(self, sct, x, y):
        """BOS SLOT ANALIZI: DUZELTILDI"""
        template = self.images.get("path_empty")
        
        # Eger bos slot resmi hic secilmediyse, mecburen DOLU kabul etsin (hata basmasin) ama kullaniciya uyari versin
        if template is None: 
            print("[HATA] 'Bos Slot Resmi' secili degil! Her seye basar.")
            return False 

        # Hassasiyet ayari: 0.85'ten 0.65'e dusuruldu.
        # Bu sayede slot biraz bile bos kutuya benziyorsa "Bos" olarak isaretleyip gececek.
        confidence = 0.65 

        try:
            # 30x30'luk alani al
            region = {"left": int(x-15), "top": int(y-15), "width": 30, "height": 30}
            scr = np.array(sct.grab(region))
            gray = cv2.cvtColor(scr, cv2.COLOR_BGRA2GRAY)
            res = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
            _, val, _, _ = cv2.minMaxLoc(res)
            
            # Konsola yazdir (Takip etmen icin)
            if val > confidence:
                print(f"[KONTROL] Slot BOS algilandi. (Benzerlik: {val:.2f}) -> ATLANACAK")
                return True
            else:
                # Buraya cok dikkat et: Eger bos oldugu halde dusuk cikiyorsa resim kotudur.
                print(f"[KONTROL] Slot DOLU algilandi. (Benzerlik: {val:.2f}) -> BASILACAK")
                return False
        except Exception as e: 
            print(f"Hata: {e}")
            return False

    def _mouse_action(self, x, y, right=False):
        if self._stop_event.is_set(): return
        try:
            if self.mouse:
                self.mouse.mouse_left_up(0, 0); self.mouse.mouse_right_up(0, 0)
            else:
                pyautogui.mouseUp(button='left'); pyautogui.mouseUp(button='right')

            # Hareket et - hiçbir tuş basılmadan
            time.sleep(0.05)
            if self.mouse and hasattr(self.mouse, 'move'): self.mouse.move(int(x), int(y))
            else: pyautogui.moveTo(x, y)

            self._wait(0.18)

            # Hareket bittiğinde click yap
            btn = 'right' if right else 'left'
            if self.mouse:
                if right: self.mouse.rightclick(0.05, int(x), int(y))
                else: self.mouse.leftclick(0.05, int(x), int(y))
            else:
                pyautogui.mouseDown(button=btn); time.sleep(0.05); pyautogui.mouseUp(button=btn)
            
            self._wait(0.15)
        except: pass

    def _loop(self):
        print("[UPG] Kaynaklar yukleniyor...")
        self._load_resources()
        
        count = 0
        limit = int(self.config.get("item_limit", 1))
        anvil_pos = self.config.get("anvil_pos", (0,0))
        offset = self.config.get("slot_offset", (0,0))
        slot_index = 0

        with mss.mss() as sct:
            while not self._stop_event.is_set() and count < limit:
                if slot_index >= 28: 
                    print("[UPG] Tum slotlar bitti, limit dolmadi.")
                    break 

                # 1. ANVIL AC
                self._mouse_action(anvil_pos[0], anvil_pos[1], right=True)
                self._wait(0.8)
                
                # 2. UPGRADE BUTONUNA BAS
                pos_upg = self._find(sct, "path_upgrade_btn")
                if pos_upg: self._mouse_action(pos_upg[0], pos_upg[1])
                else: 
                    self._press_esc(); self._wait(0.2); continue
                
                self._wait(0.6)
                # 3. CONFIRM 1 BUL
                c1_pos = self._find(sct, "path_confirm1", 0.70)
                if not c1_pos:
                    self._press_esc(); self._wait(0.2); continue

                # 4. SLOT ANALIZI (Dolu bulana kadar gez)
                found_full_slot = False
                while slot_index < 28 and not found_full_slot:
                    if self._stop_event.is_set(): break
                    
                    col, row = slot_index % 7, slot_index // 7
                    target_x = c1_pos[0] + offset[0] + (col * 50)
                    target_y = c1_pos[1] + offset[1] + (row * 50)

                    # Bos mu kontrol et?
                    if self._is_slot_empty(sct, target_x, target_y):
                        # Bossa bir sonrakine gec
                        slot_index += 1
                        self._wait(0.05)
                    else:
                        # Bos DEGILSE (Doluysa) islemi baslat
                        found_full_slot = True
                        self._mouse_action(target_x, target_y, right=True)
                
                if not found_full_slot: break 

                # 5. BUS VE ONAYLAR
                self._wait(0.2)
                bus_pos = self._find(sct, "path_bus")
                if bus_pos: self._mouse_action(bus_pos[0], bus_pos[1], right=True)
                
                self._wait(0.2)
                self._mouse_action(c1_pos[0], c1_pos[1]) # Onay 1
                self._wait(0.6)
                c2_pos = self._find(sct, "path_confirm2")
                if c2_pos: self._mouse_action(c2_pos[0], c2_pos[1]) # Onay 2
                
                self._wait(0.5)
                # 6. RESET
                self._press_esc()
                
                slot_index += 1
                count += 1
                self._wait(0.5)
                
        self._running = False

# =========================================================
# 2. GUI (AYAR PENCERESI)
# =========================================================
class UpgradeSettingsDialog(QDialog):
    def __init__(self, parent, config, macro):
        super().__init__(parent)
        self.setWindowTitle("UPGRADE AYARLARI")
        self.setFixedSize(480, 650)
        self.config, self.macro = config, macro
        self.overlay, self.capture_mode, self.capture_hotkey = None, 0, False

        self.setStyleSheet("""
            QDialog { background-color: #121212; }
            QGroupBox { border: 1px solid #333; border-radius: 5px; margin-top: 10px; color: #00e676; font-weight: bold; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; top: -5px; padding: 0 5px; }
            QLabel { color: #ccc; }
            QLineEdit { background: #000; border: 1px solid #333; color: #00ff4c; padding: 5px; font-family: Consolas; }
            QPushButton { background-color: #252525; color: white; border: 1px solid #444; padding: 6px; border-radius: 4px; }
            QPushButton:hover { background-color: #333; border-color: #00e676; }
            QDoubleSpinBox { background: #000; color: #fff; border: 1px solid #333; padding: 4px; }
        """)

        main_layout = QVBoxLayout(self)
        grp_genel = QGroupBox("Temel Ayarlar")
        gl = QGridLayout(grp_genel)
        gl.addWidget(QLabel("BASLATMA TUSU:"), 0, 0)
        self.txt_hotkey = QLineEdit(self.config.get("hotkey", "G"))
        self.txt_hotkey.setReadOnly(True); self.txt_hotkey.setFixedWidth(80)
        btn_hk = QPushButton("TUS SEC"); btn_hk.clicked.connect(self.start_hotkey_capture)
        gl.addWidget(self.txt_hotkey, 0, 1); gl.addWidget(btn_hk, 0, 2)
        
        gl.addWidget(QLabel("BASILACAK ADET:"), 1, 0)
        self.sp_count = QSpinBox(); self.sp_count.setRange(1, 28); self.sp_count.setValue(int(self.config.get("item_limit", 1)))
        gl.addWidget(self.sp_count, 1, 1, 1, 2)
        
        gl.addWidget(QLabel("GECIKME CARPANI:"), 2, 0)
        self.dsp_speed = QDoubleSpinBox()
        self.dsp_speed.setRange(0.1, 5.0); self.dsp_speed.setSingleStep(0.1)
        self.dsp_speed.setValue(float(self.config.get("speed_multiplier", 1.0)))
        self.dsp_speed.setSuffix("x")
        gl.addWidget(self.dsp_speed, 2, 1, 1, 2)
        
        main_layout.addWidget(grp_genel)

        grp_img = QGroupBox("Gorsel Tanimlama (Kirp)")
        il = QGridLayout(grp_img)
        btns_data = [("path_upgrade_btn", "1. Upgrade Butonu"), ("path_bus", "2. Bus Resmi"), ("path_confirm1", "3. Confirm 1"), ("path_confirm2", "4. Confirm 2"), ("path_empty", "5. Bos Slot Resmi")]
        for i, (key, name) in enumerate(btns_data):
            il.addWidget(QLabel(name), i, 0)
            st = QLabel("✅" if self.config.get(key) and os.path.exists(self.config.get(key)) else "❌")
            if st.text() == "✅": st.setStyleSheet("color: #00ff00")
            btn = QPushButton("KIRP"); btn.setFixedWidth(80); btn.clicked.connect(lambda _, k=key: self.cap(k))
            il.addWidget(st, i, 1); il.addWidget(btn, i, 2)
        main_layout.addWidget(grp_img)

        grp_loc = QGroupBox("Konum ve Kalibrasyon")
        ll = QGridLayout(grp_loc)
        self.lbl_anvil_st = QLabel(f"Anvil: {'✅' if self.config.get('anvil_pos') else '❌'}")
        btn_anvil = QPushButton("ANVIL SEC (F)"); btn_anvil.clicked.connect(self.start_anvil)
        self.lbl_off_st = QLabel(f"Offset: {'✅' if self.config.get('slot_offset') else '❌'}")
        btn_cal = QPushButton("OFFSET YAP (F)"); btn_cal.clicked.connect(self.start_cal)
        ll.addWidget(self.lbl_anvil_st, 0, 0); ll.addWidget(btn_anvil, 0, 1)
        ll.addWidget(self.lbl_off_st, 1, 0); ll.addWidget(btn_cal, 1, 1)
        main_layout.addWidget(grp_loc)

        main_layout.addStretch()
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject); main_layout.addWidget(btns)

        self.timer = QTimer(self); self.timer.timeout.connect(self.check_native_f); self.tmp_c = (0,0)

    def cap(self, key):
        self.hide(); time.sleep(0.2)
        self.overlay = SnippingOverlay(lambda rect: self.finish_cap(rect, key))

    def finish_cap(self, rect, key):
        self.overlay = None
        if rect:
            with mss.mss() as sct:
                img = np.array(sct.grab({"left": rect.x(), "top": rect.y(), "width": rect.width(), "height": rect.height()}))
                if not os.path.exists("upgrade_data"): os.makedirs("upgrade_data")
                path = f"upgrade_data/{key}.png"; cv2.imwrite(path, cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY))
                self.config[key] = path
        self.show()

    def start_cal(self): self.hide(); self.capture_mode = 1; self.timer.start(50)
    def start_anvil(self): self.hide(); self.capture_mode = 2; self.timer.start(50)

    def check_native_f(self):
        if win32api.GetAsyncKeyState(0x46): 
            p = pyautogui.position()
            if self.capture_mode == 1:
                if self.tmp_c == (0,0): self.tmp_c = (p.x, p.y); time.sleep(0.5)
                else:
                    self.config["slot_offset"] = (p.x - self.tmp_c[0], p.y - self.tmp_c[1])
                    self.timer.stop(); self.capture_mode = 0; self.tmp_c = (0,0); self.show()
            elif self.capture_mode == 2:
                self.config["anvil_pos"] = (p.x, p.y); self.timer.stop(); self.capture_mode = 0; self.show()

    def start_hotkey_capture(self): self.capture_hotkey = True; self.txt_hotkey.setText("..."); self.grabKeyboard()
    def keyPressEvent(self, e):
        if self.capture_hotkey:
            k = e.text().upper() or ("F10" if e.key() == Qt.Key_F10 else "")
            if k: self.txt_hotkey.setText(k); self.capture_hotkey = False; self.releaseKeyboard()
        else: super().keyPressEvent(e)

    def accept(self):
        self.config["item_limit"] = self.sp_count.value()
        self.config["hotkey"] = self.txt_hotkey.text()
        self.config["speed_multiplier"] = self.dsp_speed.value()
        self.macro.update_config(self.config); super().accept()

class UpgradeWidget(QFrame):
    update_signal = pyqtSignal()
    def __init__(self, parent=None, macro_instance=None, config=None):
        super().__init__(parent); self.macro, self.config = (macro_instance or UpgradeMacro()), (config or {})
        self.macro.update_config(self.config); self.listen_active, self._hook = False, None
        self.setup_ui(); self.update_signal.connect(self._safe_update); self._safe_update()

    def setup_ui(self):
        self.setFrameShape(QFrame.Box); self.setMaximumWidth(260); self.setStyleSheet("QFrame { background-color: #101010; border: 1px solid #444; border-radius: 4px; }")
        v = QVBoxLayout(self); v.setContentsMargins(6,6,6,6); v.setSpacing(4)
        h = QHBoxLayout(); h.setSpacing(4); icon = QLabel("🔨"); icon.setStyleSheet("font-size:20px; border:none;")
        h.addWidget(icon); h.addStretch(); h.addWidget(QLabel("UPGRADE", objectName="MinorHeaderLabel")); v.addLayout(h)
        self.btn = QPushButton("TUS DINLEMEYI BASLAT"); self.btn.setObjectName("ThreeFiveListenButton")
        self.btn.clicked.connect(self.toggle_listen); v.addWidget(self.btn)
        self.st = QLabel("PASIF"); self.st.setObjectName("MinorStatusLabel"); v.addWidget(self.st)
        r = QHBoxLayout(); r.addWidget(QLabel("TUS:")); self.hk = QLabel(self.config.get("hotkey", "G")); self.hk.setObjectName("HotkeyLabel"); r.addWidget(self.hk)
        btn_set = QPushButton("⚙"); btn_set.setObjectName("MinorSettingsButton"); btn_set.clicked.connect(self.open_settings)
        r.addWidget(btn_set); v.addLayout(r)

    def open_settings(self):
        dlg = UpgradeSettingsDialog(self, self.config, self.macro)
        if dlg.exec_(): self.hk.setText(self.config["hotkey"]); self.toggle_listen() if self.listen_active else None

    def toggle_listen(self):
        if not keyboard: return
        if not self.listen_active:
            try: self._hook = keyboard.on_press_key(self.config.get("hotkey", "G").lower(), lambda e: self.macro.toggle(), suppress=False); self.listen_active = True
            except: self.listen_active = False
        else: 
            if self._hook: keyboard.unhook(self._hook)
            self._hook, self.listen_active = None, False; self.macro.stop()
        self._safe_update()

    def _safe_update(self):
        if not self.listen_active: self.st.setText("PASIF"); self.st.setStyleSheet("color:#ff5555;font-weight:bold;"); self.btn.setText("TUS DINLEMEYI BASLAT"); self.btn.setProperty("active", False)
        else:
            self.st.setText("CALISIYOR..." if self.macro.is_running else "BEKLIYOR"); self.st.setStyleSheet(f"color:{'#00ff4c' if self.macro.is_running else '#ffff55'};font-weight:bold;"); self.btn.setText("DURDUR"); self.btn.setProperty("active", True)
        self.btn.style().unpolish(self.btn); self.btn.style().polish(self.btn)
        if self.listen_active: QTimer.singleShot(500, self._safe_update)
