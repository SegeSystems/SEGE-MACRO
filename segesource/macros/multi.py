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
import win32gui
import win32api
import win32con
import ctypes
import sys
import socket
import json
from typing import List

# PyQt5 Imports
from PyQt5.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QCheckBox, QListWidget, QAbstractItemView, QMessageBox, 
    QGroupBox, QGridLayout, QWidget, QLineEdit, QListWidgetItem,
    QDialog, QDialogButtonBox, QSizePolicy, QScrollArea,
    QRadioButton, QButtonGroup
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QObject

# --- INTERCEPTION HOOK ---
try:
    import clicksend
    HAS_INTERCEPTION = True
except ImportError:
    HAS_INTERCEPTION = False

# Dinleme
try:
    import keyboard
except ImportError:
    keyboard = None

try:
    from pynput import mouse as pynput_mouse
except ImportError:
    pynput_mouse = None

# ---------------------------------------------------------
# YARDIMCI FONKSİYONLAR
# ---------------------------------------------------------
def get_local_ip():
    """Bu bilgisayarın modemsel IP adresini bulur (192.168.x.x)"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Aslında bağlanmıyoruz, sadece route'u öğreniyoruz
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

def make_lparam(scancode, is_down):
    lparam = 1 
    lparam |= (scancode << 16)
    if not is_down:
        lparam |= (1 << 30) 
        lparam |= (1 << 31) 
    return lparam

def send_background_key_direct(hwnd, scan_code, is_down=True):
    vk_code = win32api.MapVirtualKey(scan_code, 1)
    if vk_code == 0: return
    msg = win32con.WM_KEYDOWN if is_down else win32con.WM_KEYUP
    lparam = make_lparam(scan_code, is_down)
    try:
        win32api.PostMessage(hwnd, win32con.WM_ACTIVATE, win32con.WA_ACTIVE, 0)
        win32api.PostMessage(hwnd, msg, vk_code, lparam)
    except: pass

# ---------------------------------------------------------
# LOGIC CLASS (LAN Network)
# ---------------------------------------------------------
class MultiBoxMacro(QObject):
    status_changed = pyqtSignal() # UI tetikleme sinyali
    network_msg_signal = pyqtSignal(str) # Ağ durum mesajları

    def __init__(self):
        super().__init__()
        global _MULTI_INSTANCE
        _MULTI_INSTANCE = self 
        
        self.target_hwnds = [] 
        self.broadcast_keyboard = True
        self.mouse_follow_active = True 
        self.is_following = False       
        self.is_user_pressing = False 
        self._running = False
        self._lock = threading.Lock()
        
        self.SCAN_W = 0x11
        self.SCAN_X = 0x2D

        # --- NETWORK (LAN) AYARLARI ---
        self.net_mode = "LOCAL" # LOCAL, MASTER, SLAVE
        self.net_ip = ""        # Slave isek bağlanacağımız IP
        self.net_port = 6006    # Sabit port
        self.server_socket = None
        self.client_socket = None
        self.clients = []       # Master için bağlı istemciler

    def set_targets(self, hwnds):
        with self._lock: self.target_hwnds = hwnds

    def set_network_config(self, mode, ip):
        self.net_mode = mode
        self.net_ip = ip

    def start(self):
        if self._running: return
        self._running = True
        self.is_following = False
        self.is_user_pressing = False
        
        if keyboard: keyboard.hook(self._on_physical_event)
        if pynput_mouse:
            self._mouse_listener = pynput_mouse.Listener(on_click=self._on_click_event)
            self._mouse_listener.start()
        
        threading.Thread(target=self._follow_loop, daemon=True).start()

        # AĞ BAŞLATMA
        if self.net_mode == "MASTER":
            threading.Thread(target=self._start_server_thread, daemon=True).start()
        elif self.net_mode == "SLAVE":
            threading.Thread(target=self._start_client_thread, daemon=True).start()

    def stop(self):
        self._running = False
        time.sleep(0.02)
        
        # Tuşları bırak
        self._send_to_slaves(self.SCAN_W, False)
        self._send_to_slaves(self.SCAN_X, False)
        
        if keyboard:
            try: keyboard.unhook(self._on_physical_event)
            except: pass
        if hasattr(self, '_mouse_listener') and self._mouse_listener:
            self._mouse_listener.stop()
            
        self._close_network()

    def _close_network(self):
        # Server kapat
        if self.server_socket:
            try: self.server_socket.close()
            except: pass
        self.server_socket = None
        
        # Client kapat
        if self.client_socket:
            try: self.client_socket.close()
            except: pass
        self.client_socket = None
        
        # Bağlıları temizle
        for c in self.clients:
            try: c.close()
            except: pass
        self.clients = []

    @property
    def is_running(self): return self._running

    # --- FİZİKSEL TUŞ BASILINCA ---
    def _on_physical_event(self, e):
        if not self._running or not self.broadcast_keyboard: return
        is_down = (e.event_type == 'down')
        self.is_user_pressing = is_down
        
        # 1. Yerel pencerelere bas
        self._send_to_slaves(e.scan_code, is_down)
        
        # 2. Master isek ağdaki diğer PC'ye gönder
        if self.net_mode == "MASTER":
            self._network_broadcast(e.scan_code, is_down)

    def _send_to_slaves(self, scan_code, is_down):
        """Bu bilgisayardaki pencerelere sinyal gönder"""
        try:
            fg_win = win32gui.GetForegroundWindow()
            with self._lock:
                targets = list(self.target_hwnds)
            for slave_hwnd in targets:
                if slave_hwnd == fg_win: continue
                send_background_key_direct(slave_hwnd, scan_code, is_down)
        except: pass
            
    def _follow_loop(self):
        last_x = 0
        last_w_refresh = 0
        w_state_on_slaves = False
        
        try:
            while self._running:
                time.sleep(0.05)
                now = time.time()

                if (not self.is_following) or (self.is_user_pressing):
                    if w_state_on_slaves:
                        self._send_to_slaves(self.SCAN_W, False)
                        if self.net_mode == "MASTER": self._network_broadcast(self.SCAN_W, False)
                        w_state_on_slaves = False
                    continue
                
                # --- X TUŞU ---
                if now - last_x > 1.5:
                    self._send_to_slaves(self.SCAN_X, True)
                    if self.net_mode == "MASTER": self._network_broadcast(self.SCAN_X, True)
                    time.sleep(0.02)
                    self._send_to_slaves(self.SCAN_X, False)
                    if self.net_mode == "MASTER": self._network_broadcast(self.SCAN_X, False)
                    last_x = now
                
                # --- W TUŞU ---
                if not w_state_on_slaves:
                    self._send_to_slaves(self.SCAN_W, True)
                    if self.net_mode == "MASTER": self._network_broadcast(self.SCAN_W, True)
                    w_state_on_slaves = True
                    last_w_refresh = now
                elif now - last_w_refresh > 2.0:
                    self._send_to_slaves(self.SCAN_W, True)
                    if self.net_mode == "MASTER": self._network_broadcast(self.SCAN_W, True)
                    last_w_refresh = now

        finally:
            for _ in range(2):
                self._send_to_slaves(self.SCAN_W, False)
                self._send_to_slaves(self.SCAN_X, False)
                if self.net_mode == "MASTER":
                    self._network_broadcast(self.SCAN_W, False)
                    self._network_broadcast(self.SCAN_X, False)
                time.sleep(0.01)
            w_state_on_slaves = False

    def _on_click_event(self, x, y, button, pressed):
        if not self._running or not pressed: return
        if not self.mouse_follow_active: return
        try:
            fg_win = win32gui.GetForegroundWindow()
            title = win32gui.GetWindowText(fg_win).lower()
            if not any(word in title for word in ["knight", "client", "rexe", "realko", "online"]): return
        except: return

        old_state = self.is_following
        if button == pynput_mouse.Button.left: self.is_following = True
        elif button == pynput_mouse.Button.right: self.is_following = False
        if old_state != self.is_following: self.status_changed.emit()

    # ---------------------------------------------------------
    # NETWORK LOGIC (MASTER)
    # ---------------------------------------------------------
    def _start_server_thread(self):
        """Bu bilgisayar sunucu olur, diğerleri bağlanır."""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            # 0.0.0.0 diyerek ağdaki herkesin bağlanmasına izin veriyoruz
            self.server_socket.bind(('0.0.0.0', self.net_port))
            self.server_socket.listen(5)
            
            local_ip = get_local_ip()
            self.network_msg_signal.emit(f"MASTER AÇIK\nIP'niz: {local_ip}")
            
            while self._running:
                try:
                    client, addr = self.server_socket.accept()
                    client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    self.clients.append(client)
                    self.network_msg_signal.emit(f"BAĞLANDI: {addr[0]}")
                except: break
        except Exception as e:
            self.network_msg_signal.emit(f"HATA: {e}")

    def _network_broadcast(self, scan_code, is_down):
        """Bağlı kölelere tuş gönder"""
        if not self.clients: return
        try:
            data = json.dumps({"s": scan_code, "d": is_down}) + "\n"
            b_data = data.encode('utf-8')
            
            dead = []
            for c in self.clients:
                try: c.sendall(b_data)
                except: dead.append(c)
            for d in dead:
                if d in self.clients: self.clients.remove(d)
        except: pass

    # ---------------------------------------------------------
    # NETWORK LOGIC (SLAVE)
    # ---------------------------------------------------------
    def _start_client_thread(self):
        """Bu bilgisayar köle olur, Master'ın IP'sine bağlanır."""
        while self._running:
            try:
                self.network_msg_signal.emit(f"Bağlanıyor -> {self.net_ip}...")
                self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                self.client_socket.settimeout(5)
                self.client_socket.connect((self.net_ip, self.net_port))
                self.client_socket.settimeout(None)
                
                self.network_msg_signal.emit(f"BAĞLANDI!\n(Master: {self.net_ip})")
                
                buffer = ""
                while self._running:
                    data = self.client_socket.recv(4096).decode('utf-8')
                    if not data: break
                    buffer += data
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        if not line.strip(): continue
                        try:
                            pkg = json.loads(line)
                            # Master'dan gelen tuşu burada uygula
                            self._send_to_slaves(pkg["s"], pkg["d"])
                        except: pass
            except:
                self.network_msg_signal.emit("Bağlantı Aranıyor...")
                time.sleep(3)
            finally:
                if self.client_socket:
                    try: self.client_socket.close()
                    except: pass

# ---------------------------------------------------------
# UI SINIFI
# ---------------------------------------------------------
class MultiWidget(QFrame):
    update_signal = pyqtSignal()

    def __init__(self, parent=None, macro_instance=None, config=None):
        super().__init__(parent)
        self.macro = macro_instance or MultiBoxMacro()
        self.config = config or {"hotkey": "INSERT"}
        self.listen_active = False
        self._hooks = []

        self.setFrameShape(QFrame.Box)
        self.setFrameShadow(QFrame.Plain)
        self.setMaximumWidth(260)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setStyleSheet("QFrame { background-color: #101010; border: 1px solid #444; border-radius: 4px; }")
        
        self.setup_ui()
        
        self.macro.status_changed.connect(self.update_status_ui)
        self.macro.network_msg_signal.connect(self.update_net_info) 
        self.update_signal.connect(self.update_status_ui)
        self.update_status_ui()

    def setup_ui(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(4)
        
        h = QHBoxLayout(); h.setSpacing(6)
        icon = QLabel("🏠") # Ev ikonu (LAN)
        icon.setFixedSize(30, 30)
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("border: none; background: transparent;") 
        h.addWidget(icon)
        h.addStretch(1)
        lbl_title = QLabel("YEREL AĞ (LAN)"); lbl_title.setObjectName("MinorHeaderLabel"); h.addWidget(lbl_title)
        v.addLayout(h)

        self.btn_listen = QPushButton("SİSTEMİ BAŞLAT")
        self.btn_listen.setObjectName("ThreeFiveListenButton")
        self.btn_listen.setProperty("active", False)
        self.btn_listen.clicked.connect(self.toggle_listen)
        v.addWidget(self.btn_listen)

        self.st = QLabel("DURUM: PASİF")
        self.st.setObjectName("MinorStatusLabel")
        v.addWidget(self.st)

        # Network bilgi satırı
        self.lbl_net_info = QLabel("Mod: TEK BİLGİSAYAR")
        self.lbl_net_info.setStyleSheet("color: #00e5ff; font-size: 8pt; border: none;")
        self.lbl_net_info.setAlignment(Qt.AlignCenter)
        self.lbl_net_info.setWordWrap(True)
        v.addWidget(self.lbl_net_info)

        row = QHBoxLayout(); row.setSpacing(4)
        row.addWidget(QLabel("AKTİF TUŞ:"))
        self.lbl_hotkey = QLabel(self.config.get("hotkey", "INSERT"))
        self.lbl_hotkey.setStyleSheet("color: #00e676; font-weight: bold; font-family: Consolas;")
        self.lbl_hotkey.setAlignment(Qt.AlignCenter)
        row.addWidget(self.lbl_hotkey)
        
        btn_set = QPushButton("⚙ AYARLAR"); btn_set.setObjectName("MinorSettingsButton")
        btn_set.setFlat(True); btn_set.clicked.connect(self.open_settings)
        row.addWidget(btn_set)
        v.addLayout(row)

    def toggle_listen(self):
        if not keyboard: return
        if not self.listen_active:
            hk = self.config.get("hotkey", "INSERT").lower()
            try:
                h = keyboard.on_press_key(hk, lambda e: self.toggle())
                self._hooks.append(h)
                self.listen_active = True
            except: self.listen_active = False
        else:
            for h in self._hooks: keyboard.unhook(h)
            self._hooks = []; self.listen_active = False
            if self.macro.is_running: self.macro.stop()
        self.update_status_ui()

    def update_status_ui(self):
        if not self.listen_active:
            self.st.setText("DURUM: PASİF")
            self.st.setStyleSheet("color: #ff5555; font-weight: bold;")
            self.btn_listen.setText("SİSTEMİ BAŞLAT")
            self.btn_listen.setProperty("active", False)
        else:
            if self.macro.is_running:
                c = len(self.macro.target_hwnds)
                self.st.setText(f"AKTİF ({c} Win)")
                self.st.setStyleSheet("color: #00ff4c; font-weight: bold;")
            else:
                self.st.setText("DURUM: BEKLİYOR")
                self.st.setStyleSheet("color: #ffff55; font-weight: bold;")
            self.btn_listen.setText("SİSTEMİ DURDUR")
            self.btn_listen.setProperty("active", True)
        
        self.btn_listen.style().unpolish(self.btn_listen); self.btn_listen.style().polish(self.btn_listen)
    
    def update_net_info(self, msg):
        self.lbl_net_info.setText(msg)

    def toggle(self):
        if self.macro.is_running: self.macro.stop()
        else:
            self.macro.start()
        self.update_signal.emit()

    def open_settings(self):
        dlg = MultiSettingsDialog(self, self.config, self.macro)
        if dlg.exec_():
            self.config.update(dlg.result_config)
            self.lbl_hotkey.setText(self.config.get("hotkey"))
            self.update_status_ui()
            if self.listen_active: self.toggle_listen(); self.toggle_listen()

    def closeEvent(self, event):
        self.macro.stop() 
        if self.listen_active:
            for h in self._hooks: keyboard.unhook(h)
        event.accept()

# ---------------------------------------------------------
# AYARLAR PENCERESİ
# ---------------------------------------------------------
class MultiSettingsDialog(QDialog):
    def __init__(self, parent, config, macro):
        super().__init__(parent)
        self.macro = macro; self.config = config; self.capture_mode = False
        self.setWindowTitle("YEREL AĞ (LAN) AYARLARI"); self.resize(450, 650)
        self.setStyleSheet("background-color: #161616; color: white;")
        layout = QVBoxLayout(self)

        # GRUP 1: TUŞ SEÇİMİ
        grp_hk = QGroupBox("1. Başlatma Tuşu"); grp_hk.setStyleSheet("color: #00e676; font-weight: bold;")
        hk_lay = QHBoxLayout(grp_hk)
        self.txt_hk = QLineEdit(self.config.get("hotkey", "INSERT")); self.txt_hk.setReadOnly(True)
        self.txt_hk.setStyleSheet("background: #000; color: #00e676; font-family: Consolas; font-weight: bold; border: 1px solid #333;")
        btn_cap = QPushButton("TUŞ SEÇ"); btn_cap.setStyleSheet("background: #252525; color: #00e676; border: 1px solid #00e676; font-weight: bold;")
        btn_cap.clicked.connect(self.start_hk_cap)
        hk_lay.addWidget(QLabel("Aktif Tuş:")); hk_lay.addWidget(self.txt_hk); hk_lay.addWidget(btn_cap); layout.addWidget(grp_hk)

        # GRUP 2: PENCERELER
        grp_win = QGroupBox("2. Yönetilecek Pencereler (Bu PC)"); grp_win.setStyleSheet("color: #00e676; font-weight: bold;")
        win_lay = QVBoxLayout(grp_win)
        self.win_scroll = QScrollArea(); self.win_scroll.setWidgetResizable(True); self.win_scroll.setMinimumHeight(150)
        self.win_scroll.setStyleSheet("background: #000; border: 1px solid #333;")
        self.win_container = QWidget(); self.win_list_lay = QVBoxLayout(self.win_container)
        self.win_list_lay.setAlignment(Qt.AlignTop); self.win_scroll.setWidget(self.win_container)
        self.window_checks = []; win_lay.addWidget(self.win_scroll)
        h_btns = QHBoxLayout(); btn_ref = QPushButton("Yenile"); btn_ref.clicked.connect(self.refresh)
        btn_all = QPushButton("Tümünü Seç"); btn_all.clicked.connect(self.select_all_checks)
        h_btns.addWidget(btn_ref); h_btns.addWidget(btn_all); win_lay.addLayout(h_btns); layout.addWidget(grp_win)

        # GRUP 3: YEREL AĞ AYARLARI
        grp_net = QGroupBox("3. Aynı Ev/İnternet Bağlantısı"); grp_net.setStyleSheet("color: #00e676; font-weight: bold;")
        net_lay = QVBoxLayout(grp_net)
        
        # Mod Seçimi
        rb_layout = QHBoxLayout()
        self.bg_net = QButtonGroup(self)
        self.rb_local = QRadioButton("Sadece Bu PC")
        self.rb_master = QRadioButton("ANA PC (Master)")
        self.rb_slave = QRadioButton("YAN PC (Slave)")
        
        self.bg_net.addButton(self.rb_local)
        self.bg_net.addButton(self.rb_master)
        self.bg_net.addButton(self.rb_slave)
        
        # Mevcut ayarı yükle
        curr_mode = getattr(self.macro, "net_mode", "LOCAL")
        if curr_mode == "MASTER": self.rb_master.setChecked(True)
        elif curr_mode == "SLAVE": self.rb_slave.setChecked(True)
        else: self.rb_local.setChecked(True)
        
        rb_layout.addWidget(self.rb_local)
        rb_layout.addWidget(self.rb_master)
        rb_layout.addWidget(self.rb_slave)
        net_lay.addLayout(rb_layout)
        
        # IP Bilgisi ve Girişi
        self.local_ip_val = get_local_ip()
        
        # Master için bilgi
        self.lbl_master_info = QLabel(f"Sizin Yerel IP Adresiniz: {self.local_ip_val}\n(Yan bilgisayara bu numarayı girin)")
        self.lbl_master_info.setStyleSheet("color: #00ffff; font-size: 9pt; background: #222; padding: 5px;")
        net_lay.addWidget(self.lbl_master_info)
        
        # Slave için giriş
        self.inp_ip = QLineEdit()
        self.inp_ip.setPlaceholderText("Ana PC'nin IP Adresini Girin (Örn: 192.168.1.25)")
        self.inp_ip.setText(getattr(self.macro, "net_ip", ""))
        self.inp_ip.setStyleSheet("background: #222; color: white; padding: 5px;")
        
        self.lbl_slave_info = QLabel("Ana PC'nin IP Adresi:")
        net_lay.addWidget(self.lbl_slave_info)
        net_lay.addWidget(self.inp_ip)
        
        # Görünürlük ayarı
        self.rb_local.toggled.connect(self.update_net_ui)
        self.rb_master.toggled.connect(self.update_net_ui)
        self.rb_slave.toggled.connect(self.update_net_ui)
        self.update_net_ui()
        
        layout.addWidget(grp_net)

        # GRUP 4: ÖZELLİKLER
        grp_feat = QGroupBox("4. Özellikler"); grp_feat.setStyleSheet("color: #00e676; font-weight: bold;")
        feat_lay = QVBoxLayout(grp_feat)
        self.chk_follow = QCheckBox("Mouse Sol/Sağ Tık Takip Kontrolü (Z Atak / Durdur)")
        self.chk_follow.setChecked(getattr(self.macro, 'mouse_follow_active', True))
        self.chk_follow.toggled.connect(lambda v: setattr(self.macro, 'mouse_follow_active', v))
        feat_lay.addWidget(self.chk_follow); layout.addWidget(grp_feat)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel); btns.accepted.connect(self.save_and_accept); btns.rejected.connect(self.reject); layout.addWidget(btns)
        self.refresh()

    def update_net_ui(self):
        # Master seçilirse kendi IP'sini göster
        self.lbl_master_info.setVisible(self.rb_master.isChecked())
        
        # Slave seçilirse IP girme kutusunu göster
        self.lbl_slave_info.setVisible(self.rb_slave.isChecked())
        self.inp_ip.setVisible(self.rb_slave.isChecked())

    def start_hk_cap(self):
        self.capture_mode = True; self.txt_hk.setText("..."); self.grabKeyboard()

    def keyPressEvent(self, e):
        if self.capture_mode:
            key = e.key(); name = None
            if key == Qt.Key_CapsLock: name = "CAPS LOCK"
            elif key == Qt.Key_Insert: name = "INSERT"
            elif Qt.Key_F1 <= key <= Qt.Key_F12: name = f"F{key - Qt.Key_F1 + 1}"
            else: text = e.text().upper(); name = text if text else None
            if name: self.txt_hk.setText(name); self.capture_mode = False; self.releaseKeyboard()
        else: super().keyPressEvent(e)

    def select_all_checks(self):
        for cb in self.window_checks: cb.setChecked(True)

    def refresh(self):
        while self.win_list_lay.count():
            it = self.win_list_lay.takeAt(0); 
            if it.widget(): it.widget().deleteLater()
        self.window_checks = []
        def enum_handler(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd); cls = win32gui.GetClassName(hwnd)
                target_keys = ["knight", "client", "rexe", "soacs", "realko", "online"]
                if any(k in title.lower() or k in cls.lower() for k in target_keys):
                    cb = QCheckBox(f"[{hwnd}] {title if title.strip() else cls}"); cb.setProperty("hwnd", hwnd)
                    cb.setStyleSheet("QCheckBox { color: white; padding: 5px; } QCheckBox:checked { color: #00e676; }")
                    if hwnd in self.macro.target_hwnds: cb.setChecked(True)
                    self.win_list_lay.addWidget(cb); self.window_checks.append(cb)
        win32gui.EnumWindows(enum_handler, None); self.win_list_lay.addStretch(1)

    def save_and_accept(self):
        hwnds = [cb.property("hwnd") for cb in self.window_checks if cb.isChecked()]
        self.macro.set_targets(hwnds)
        
        # Ağ Ayarlarını Kaydet
        mode = "LOCAL"
        if self.rb_master.isChecked(): mode = "MASTER"
        elif self.rb_slave.isChecked(): mode = "SLAVE"
        
        ip = self.inp_ip.text().strip()
        self.macro.set_network_config(mode, ip)
        
        self.result_config = {"hotkey": self.txt_hk.text()}
        self.accept()
