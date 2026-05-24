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
import io
import datetime
import re
import requests
import pyautogui
import cv2
import numpy as np
import pytesseract
import sys  # Uygulama yolu için eklendi
from PIL import Image
from PyQt5.QtWidgets import (
    QDialog, QLabel, QComboBox, QLineEdit, QPushButton, QHBoxLayout, 
    QWidget, QFrame, QVBoxLayout, QSizePolicy, QScrollArea, QCheckBox, 
    QGroupBox, QSpinBox, QDoubleSpinBox, QFileDialog, QApplication, QFormLayout,
    QTabWidget, QRubberBand 
)
from PyQt5.QtGui import QPixmap, QPainter, QPen, QColor, QPalette 
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QRect, QPoint, QSize 

# Tesseract Yolu
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# ============================================================
# DİZİN AYARI (Icons Klasörü)
# ============================================================
def get_icons_dir():
    # .exe olarak çalışıyorsa exe dizini, .py olarak çalışıyorsa script dizini
    if getattr(sys, 'frozen', False):
        base_path = os.path.dirname(sys.executable)
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    
    icons_path = os.path.join(base_path, "icons")
    
    # Klasör yoksa hata vermemesi için oluşturulabilir (Opsiyonel)
    if not os.path.exists(icons_path):
        os.makedirs(icons_path, exist_ok=True)
    return icons_path

ICONS_DIR = get_icons_dir()

# ============================================================
# YARDIMCI GÖRSEL FONKSİYONLAR
# ============================================================
def capture_screen():
    screenshot = pyautogui.screenshot()
    return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)

def find_template(screen, template_name, threshold=0.75):
    template_path = os.path.join(ICONS_DIR, template_name)
    if not os.path.exists(template_path): 
        return None
    template = cv2.imread(template_path)
    if template is None: return None
    res = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
    if max_val >= threshold:
        return max_loc
    return None

# ============================================================
# ALAN SEÇİCİ (REGION SELECTOR)
# ============================================================
class SnippingOverlay(QWidget):
    def __init__(self, on_selected_callback):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        desktop = QApplication.desktop()
        self.setGeometry(desktop.geometry())
        self.setWindowOpacity(0.3) # Ekranı hafif karartır
        self.setStyleSheet("background-color: black;")
        self.on_selected_callback = on_selected_callback
        self.origin = QPoint()
        self.rubberBand = QRubberBand(QRubberBand.Rectangle, self)
        
        # Kırmızı Çerçeve Ayarı
        red_palette = QPalette()
        red_palette.setColor(QPalette.Highlight, QColor(255, 0, 0)) 
        self.rubberBand.setPalette(red_palette)
        self.setCursor(Qt.CrossCursor)
        self.show()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.origin = event.pos()
            self.rubberBand.setGeometry(QRect(self.origin, QSize()))
            self.rubberBand.show()
        elif event.button() == Qt.RightButton: self.close()

    def mouseMoveEvent(self, event):
        if not self.origin.isNull():
            self.rubberBand.setGeometry(QRect(self.origin, event.pos()).normalized())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            rect = self.rubberBand.geometry()
            self.close()
            global_pos = self.mapToGlobal(rect.topLeft())
            final_rect = QRect(global_pos, rect.size())
            self.on_selected_callback(final_rect)
# ============================================================
# LOGIC: NotificationMacro
# ============================================================
class NotificationMacro:
    def __init__(self):
        self.config = {}
        self._running = False
        self._stop_event = threading.Event()
        self._thread = None
        self.status = "HAZIR"
        self._cooldowns = {"death": 0, "dc": 0, "gm": 0, "number": 0}
        self._last_number_value = None
        self.last_read_coord = "---"

    def update_config(self, cfg):
        self.config = cfg

    @property
    def is_running(self):
        return self._running

    def start(self):
        if not self._running:
            self._stop_event.clear()
            self._running = True
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()

    def stop(self):
        self._stop_event.set()
        self._running = False
        self.status = "DURDURULDU"

    def _run_loop(self):
        while not self._stop_event.is_set():
            try:
                screen = None
                now = time.time()
                
                # 1. Death & DC Kontrolü
                if self.config.get("enable_death_watch") or self.config.get("enable_dc_watch"):
                    screen = capture_screen()
                    
                    if self.config.get("enable_death_watch") and now > self._cooldowns["death"]:
                        # icons/death.png otomatik aranır
                        if find_template(screen, "death.png", self.config.get("match_threshold", 0.75)):
                            self._trigger_event("death", self.config.get("msg_death", "Press OK!"))
                            self._cooldowns["death"] = now + self.config.get("msg_cooldown_s", 60)

                    if self.config.get("enable_dc_watch") and now > self._cooldowns["dc"]:
                        # icons/disconnected.png otomatik aranır
                        if find_template(screen, "disconnected.png", self.config.get("match_threshold", 0.75)):
                            self._trigger_event("dc", self.config.get("msg_dc", "Disconnected from Server!"))
                            self._cooldowns["dc"] = now + self.config.get("msg_cooldown_s", 60)


                    
                self.status = "TARANIYOR..."
            except Exception as e:
                self.status = f"HATA: {str(e)[:20]}"

            if self.config.get("enable_number_watch"):
                self._check_number_change()

            self._stop_event.wait(self.config.get("scan_interval_ms", 10000) / 1000.0)


            
    def _trigger_event(self, event_type, base_msg):
        final_msg = base_msg
        if self.config.get("append_character_name") and self.config.get("character_name"):
            final_msg = f"[{self.config['character_name']}] {final_msg}"
        if self.config.get("append_time"):
            final_msg += f" ({datetime.datetime.now().strftime('%H:%M:%S')})"

        screenshot = None
        if self.config.get("include_screenshot"):
            buf = io.BytesIO()
            pyautogui.screenshot().save(buf, format="PNG")
            screenshot = buf.getvalue()

        if self.config.get("enabled_discord"):
            self._send_discord(final_msg, screenshot)
        if self.config.get("enabled_telegram"):
            self._send_telegram(final_msg, screenshot)

    def _send_discord(self, msg, ss):
        url = self.config.get("discord_webhook_url")
        if not url: return
        try:
            payload = {"content": msg}
            files = {"file": ("screen.png", ss, "image/png")} if ss else None
            requests.post(url, data=payload, files=files, timeout=10)
        except: pass

    def _send_telegram(self, msg, ss):
        token = self.config.get("telegram_bot_token")
        chat_id = self.config.get("telegram_chat_id")
        if not token or not chat_id: return
        try:
            if ss:
                url = f"https://api.telegram.org/bot{token}/sendPhoto"
                requests.post(url, data={"chat_id": chat_id, "caption": msg}, files={"photo": ss}, timeout=10)
            else:
                url = f"https://api.telegram.org/bot{token}/sendMessage"
                requests.post(url, data={"chat_id": chat_id, "text": msg}, timeout=10)
        except: pass

# ============================================================
# SETTINGS DIALOG
# ============================================================
class NotificationSettingsDialog(QDialog):
    def __init__(self, parent, config, macro_instance): # macro_instance eklendi
        super().__init__(parent)
        self.macro = macro_instance # Macro'yu içeri aldık
        self.setWindowTitle("BİLDİRİM YAPILANDIRMASI")
        self.setFixedSize(550, 720) 
        self.config = config
        self.result_config = {}
        
        self.update_timer = QTimer()
        # HATALI SATIR DÜZELTİLDİ:
        self.update_timer.timeout.connect(self._update_ocr_display) 
        self.update_timer.start(1000)
        
        self.setStyleSheet("""
            QDialog { background-color: #121212; color: #e0e0e0; font-family: 'Segoe UI'; }
            QTabWidget::pane { border: 1px solid #333; background: #181818; top: -1px; }
            QTabBar::tab { background: #252525; color: #aaa; padding: 10px 20px; border: 1px solid #333; margin-right: 2px; }
            QTabBar::tab:selected { background: #181818; color: #00ff4c; border-bottom: 2px solid #00ff4c; }
            QLabel { color: #bbb; font-size: 11px; }
            QLineEdit, QSpinBox, QComboBox { 
                background: #222; border: 1px solid #444; color: #00ff4c; 
                padding: 6px; border-radius: 3px; 
            }
            QCheckBox { color: #ccc; spacing: 8px; }
            QGroupBox { 
                border: 1px solid #333; margin-top: 10px; padding-top: 15px; 
                font-weight: bold; color: #00ff4c; 
            }
            QPushButton { 
                background-color: #1a1a2e; color: white; border: 1px solid #444; 
                padding: 10px; border-radius: 4px; font-weight: bold;
            }
            QPushButton:hover { border-color: #00ff4c; background-color: #222; }
            QPushButton#saveBtn { background-color: #053d1a; border: 1px solid #00ff4c; margin-top: 10px; }
            QPushButton#discordTestBtn, QPushButton#telegramTestBtn { background-color: #252525; border-color: #555; margin-top: 5px;}
            QPushButton#discordTestBtn:hover, QPushButton#telegramTestBtn:hover { border-color: #00ff4c; }
        """)
        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        self.tabs = QTabWidget()

        # --- SEKME 1: BAĞLANTILAR & GENEL ---
        tab_conn = QWidget()
        l_conn = QVBoxLayout(tab_conn)
        
        gb_channels = QGroupBox("BİLDİRİM KANALLARI")
        v_chan = QVBoxLayout(gb_channels)

        # 1. DISCORD BÖLÜMÜ (Alt alta form düzeni)
        f_disc = QFormLayout()
        self.chk_disc = QCheckBox("Discord Aktif")
        self.chk_disc.setChecked(self.config.get("enabled_discord", False))
        self.txt_disc = QLineEdit(self.config.get("discord_webhook_url", ""))
        self.txt_disc.setPlaceholderText("Webhook URL buraya...")
        
        self.btn_discord_test = QPushButton("▶ Discord Test Mesajı Gönder")
        self.btn_discord_test.setObjectName("discordTestBtn")
        self.btn_discord_test.clicked.connect(self._test_discord)
        self.btn_discord_test.setEnabled(False) # Başlangıçta devre dışı
        
        f_disc.addRow(self.chk_disc)
        f_disc.addRow("Webhook URL:", self.txt_disc)
        f_disc.addRow(self.btn_discord_test)
        v_chan.addLayout(f_disc)

        # AYIRICI ÇİZGİ
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setStyleSheet("background-color: #333; margin: 10px 0px;")
        v_chan.addWidget(line)

        # 2. TELEGRAM BÖLÜMÜ (Alt alta form düzeni)
        f_tele = QFormLayout()
        self.chk_tele = QCheckBox("Telegram Aktif")
        self.chk_tele.setChecked(self.config.get("enabled_telegram", False))
        self.txt_chat = QLineEdit(self.config.get("telegram_chat_id", ""))
        self.txt_chat.setPlaceholderText("Chat ID buraya...")
        self.txt_token = QLineEdit(self.config.get("telegram_bot_token", ""))
        self.txt_token.setPlaceholderText("Bot Token buraya...")
        
        self.btn_telegram_test = QPushButton("▶ Telegram Test Mesajı Gönder")
        self.btn_telegram_test.setObjectName("telegramTestBtn")
        self.btn_telegram_test.clicked.connect(self._test_telegram)
        self.btn_telegram_test.setEnabled(False) # Başlangıçta devre dışı

        f_tele.addRow(self.chk_tele)
        f_tele.addRow("Chat ID:", self.txt_chat)
        f_tele.addRow("Bot Token:", self.txt_token)
        f_tele.addRow(self.btn_telegram_test)
        v_chan.addLayout(f_tele)
        
        l_conn.addWidget(gb_channels)

        # TARAMA AYARLARI
        gb_gen = QGroupBox("TARAMA AYARLARI")
        f_gen = QFormLayout(gb_gen)
        self.spn_interval = QSpinBox()
        self.spn_interval.setRange(1, 600)
        self.spn_interval.setSuffix(" Saniye")
        current_ms = self.config.get("scan_interval_ms", 10000)
        self.spn_interval.setValue(int(current_ms / 1000))
        

        
                # 2. Bildirim Sıklığı (Mesaj gönderme aralığı) - YENİ EKLENEN
        self.spn_cooldown = QSpinBox()
        self.spn_cooldown.setRange(5, 3600) # En az 5 saniye, en çok 1 saat
        self.spn_cooldown.setSuffix(" Saniye")
        self.spn_cooldown.setValue(self.config.get("msg_cooldown_s", 60))
        
        f_gen.addRow("Kontrol Sıklığı:", self.spn_interval)
        f_gen.addRow("Bildirim Sıklığı:", self.spn_cooldown) # Altına eklendi
        l_conn.addWidget(gb_gen)

        # --- SEKME 2: MESAJLAR & TAKİP ---
        tab_msg = QWidget()
        l_msg = QVBoxLayout(tab_msg)
        
        h_char = QHBoxLayout()
        self.txt_char = QLineEdit(self.config.get("character_name", ""))
        h_char.addWidget(QLabel("Karakter Adı:")); h_char.addWidget(self.txt_char)
        l_msg.addLayout(h_char)

        gb_watch = QGroupBox("DURUM TAKİBİ")
        v_watch = QVBoxLayout(gb_watch)
        h_death = QHBoxLayout()
        self.chk_w_death = QCheckBox("Death")
        self.chk_w_death.setChecked(self.config.get("enable_death_watch", True))
        self.txt_m_death = QLineEdit(self.config.get("msg_death", "Press OK!."))
        h_death.addWidget(self.chk_w_death); h_death.addWidget(self.txt_m_death)
        h_dc = QHBoxLayout()
        self.chk_w_dc = QCheckBox("Disconnect")
        self.chk_w_dc.setChecked(self.config.get("enable_dc_watch", True))
        self.txt_m_dc = QLineEdit(self.config.get("msg_dc", "Disconnectd from Server!"))
        h_dc.addWidget(self.chk_w_dc); h_dc.addWidget(self.txt_m_dc)
        v_watch.addLayout(h_death); v_watch.addLayout(h_dc)
        l_msg.addWidget(gb_watch)

        gb_extra = QGroupBox("BİLDİRİM İÇERİĞİ")
        h_extra = QHBoxLayout(gb_extra)
        self.chk_app_char = QCheckBox("İsim Ekle"); self.chk_app_char.setChecked(self.config.get("append_character_name", True))
        self.chk_app_time = QCheckBox("Saat Ekle"); self.chk_app_time.setChecked(self.config.get("append_time", True))
        self.chk_ss = QCheckBox("SS Ekle"); self.chk_ss.setChecked(self.config.get("include_screenshot", False))
        h_extra.addWidget(self.chk_app_char); h_extra.addWidget(self.chk_app_time); h_extra.addWidget(self.chk_ss)
        l_msg.addWidget(gb_extra)
        l_msg.addStretch()

        self.tabs.addTab(tab_conn, "🔗 BAĞLANTILAR & GENEL")
        self.tabs.addTab(tab_msg, "✉ MESAJLAR & TAKİP")
        main_layout.addWidget(self.tabs)

        self.btn_save = QPushButton("💾 AYARLARI KAYDET")
        self.btn_save.setObjectName("saveBtn")
        self.btn_save.clicked.connect(self.accept)
        main_layout.addWidget(self.btn_save)
        
        # Başlangıçta butonların durumunu ayarla
        self._update_test_button_states()
        
        # Checkbox değişikliklerinde butonları güncelle
        self.chk_disc.stateChanged.connect(self._update_test_button_states)
        self.txt_disc.textChanged.connect(self._update_test_button_states)
        self.chk_tele.stateChanged.connect(self._update_test_button_states)
        self.txt_chat.textChanged.connect(self._update_test_button_states)
        self.txt_token.textChanged.connect(self._update_test_button_states)


    def _update_test_button_states(self):
        # Discord test butonu aktiflik kontrolü
        discord_ready = self.chk_disc.isChecked() and bool(self.txt_disc.text())
        self.btn_discord_test.setEnabled(discord_ready)
        if discord_ready:
            self.btn_discord_test.setStyleSheet("QPushButton#discordTestBtn { background-color: #1a1a2e; border-color: #00ff4c; }")
        else:
            self.btn_discord_test.setStyleSheet("QPushButton#discordTestBtn { background-color: #252525; border-color: #555; }")

        # Telegram test butonu aktiflik kontrolü
        telegram_ready = self.chk_tele.isChecked() and bool(self.txt_chat.text()) and bool(self.txt_token.text())
        self.btn_telegram_test.setEnabled(telegram_ready)
        if telegram_ready:
            self.btn_telegram_test.setStyleSheet("QPushButton#telegramTestBtn { background-color: #1a1a2e; border-color: #00ff4c; }")
        else:
            self.btn_telegram_test.setStyleSheet("QPushButton#telegramTestBtn { background-color: #252525; border-color: #555; }")

    def _test_discord(self):
        # Test mesajı gönderme fonksiyonu
        msg = "✅ Discord Test Mesajı Başarılı!"
        ss = None # Test mesajına ekran görüntüsü eklemeyelim şimdilik
        
        # Bu kısım NotificationMacro sınıfındaki _send_discord metodunu kullanıyor
        # Eğer NotificationMacro instance'ına erişimimiz yoksa, burada request yapmamız gerekir.
        # Şimdilik NotificationMacro'nun metoduyla çalıştırıyorum.
        
        # NotificationMacro'ya bu ayarları geçici olarak verip test gönderelim
        # (Aslında bu kısım daha optimize edilebilir, belki ayar dialogu içinden doğrudan istek gönderilebilir.)
        temp_macro = NotificationMacro() # Geçici bir instance oluştur
        temp_macro.update_config({
            "enabled_discord": True,
            "discord_webhook_url": self.txt_disc.text(),
            "include_screenshot": False # Test mesajı için SS kapalı
        })
        temp_macro._send_discord(msg, ss)
        
        # Kullanıcıya geri bildirim
        self.btn_discord_test.setText("✅ Gönderildi!")
        self.btn_discord_test.setEnabled(False)
        QTimer.singleShot(2000, lambda: self.btn_discord_test.setText("▶ Discord Test Mesajı Gönder"))
        QTimer.singleShot(2000, self._update_test_button_states) # Tekrar aktifleşme kontrolü

    def _test_telegram(self):
        # Test mesajı gönderme fonksiyonu
        msg = "✅ Telegram Test Mesajı Başarılı!"
        ss = None # Test mesajına ekran görüntüsü eklemeyelim şimdilik

        # NotificationMacro'ya bu ayarları geçici olarak verip test gönderelim
        temp_macro = NotificationMacro() # Geçici bir instance oluştur
        temp_macro.update_config({
            "enabled_telegram": True,
            "telegram_chat_id": self.txt_chat.text(),
            "telegram_bot_token": self.txt_token.text(),
            "include_screenshot": False # Test mesajı için SS kapalı
        })
        temp_macro._send_telegram(msg, ss)

        # Kullanıcıya geri bildirim
        self.btn_telegram_test.setText("✅ Gönderildi!")
        self.btn_telegram_test.setEnabled(False)
        QTimer.singleShot(2000, lambda: self.btn_telegram_test.setText("▶ Telegram Test Mesajı Gönder"))
        QTimer.singleShot(2000, self._update_test_button_states) # Tekrar aktifleşme kontrolü

    def _select_region(self):
        # 1. Ayarlar penceresini gizle (ekranı rahat seçmek için)
        self.hide()
        time.sleep(0.2)
        
        # 2. Yeni nesil Snipping Tool'u başlat
        # Seçim bitince otomatik olarak 'self._on_region_selected' fonksiyonuna gidecek
        self.snipper = SnippingOverlay(self._on_region_selected)

    def _on_region_selected(self, rect):
        # 3. Seçim bitince burası çalışır. Ayarlar penceresini geri getir.
        self.show()
        
        if rect.width() > 5 and rect.height() > 5:
            # Koordinatları listeye çevirip kaydet
            res = [rect.x(), rect.y(), rect.width(), rect.height()]
            self.config["number_region"] = res
            
            # Arayüzdeki "Alan: ..." yazısını güncelle
            if hasattr(self, 'lbl_region_info'):
                self.lbl_region_info.setText(f"Alan: {res[0]},{res[1]} | {res[2]}x{res[3]}")
        else:
            # Eğer kullanıcı sağ tıkla iptal ettiyse veya çok küçük yer seçtiyse
            if hasattr(self, 'lbl_region_info'):
                self.lbl_region_info.setText("Alan: Seçim İptal Edildi")


    def showEvent(self, event):
        """Pencere açıldığında timer'ı başlat"""
        super().showEvent(event)
        self.ui_timer = QTimer(self)
        self.ui_timer.timeout.connect(self._update_ocr_display)
        self.ui_timer.start(1000) # 1 saniyede bir güncelleme (Kasmayı engeller)

    def hideEvent(self, event):
        """Pencere kapandığında timer'ı durdur ve sil"""
        if hasattr(self, 'ui_timer'):
            self.ui_timer.stop()
            self.ui_timer.deleteLater()
        super().hideEvent(event)

    def _update_ocr_display(self):
        """Sadece makrodaki veriyi etikete yansıtır (İşlem yapmaz, yormaz)"""
        if hasattr(self, 'lbl_ocr'):
            self.lbl_ocr.setText(f"Canlı Koordinat: {self.macro.last_read_coord}")

    def accept(self):
        interval_ms = self.spn_interval.value() * 1000
        self.result_config = {
            **self.config,
            "enabled_discord": self.chk_disc.isChecked(),
            "discord_webhook_url": self.txt_disc.text(),
            "enabled_telegram": self.chk_tele.isChecked(),
            "telegram_bot_token": self.txt_token.text(),
            "telegram_chat_id": self.txt_chat.text(),
            "character_name": self.txt_char.text(),
            "msg_death": self.txt_m_death.text(),
            "msg_dc": self.txt_m_dc.text(),
            "append_character_name": self.chk_app_char.isChecked(),
            "append_time": self.chk_app_time.isChecked(),
            "include_screenshot": self.chk_ss.isChecked(),
            "scan_interval_ms": interval_ms,
            "msg_cooldown_s": self.spn_cooldown.value(),
            "enable_death_watch": self.chk_w_death.isChecked(),
            "enable_dc_watch": self.chk_w_dc.isChecked()

        }
        super().accept()
# ============================================================
# WIDGET (Ana Arayüz Kartı)
# ============================================================
class NotificationWidget(QFrame):
    def __init__(self, parent=None, macro_instance=None, config=None):
        super().__init__(parent)
        self.macro = macro_instance
        self.config = config or {}
        self.setup_ui()
        self.timer = QTimer()
        self.timer.timeout.connect(self._update_status)
        self.timer.start(250)

    def setup_ui(self):
        # 1. Çerçeve ve Genel Stil
        self.setFrameShape(QFrame.Box)
        self.setMaximumWidth(260)
        self.setStyleSheet("QFrame { background-color: #101010; border: 1px solid #444; border-radius: 4px; }")
        
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(4)

        # 2. ÇİFT İKONLU BAŞLIK ALANI
        h_header = QHBoxLayout()
        h_header.setSpacing(4) # İkonlar arası mesafe
        
        # --- Discord İkonu ---
        icon_discord = QLabel()
        icon_discord.setFixedSize(28, 28)
        icon_discord.setStyleSheet("border: none; background: transparent;")
        
        import os
        path_disc = os.path.join("icons", "discord.png")
        if os.path.exists(path_disc):
            pix_d = QPixmap(path_disc)
            icon_discord.setPixmap(pix_d.scaled(28, 28, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        
        # --- Telegram İkonu ---
        icon_telegram = QLabel()
        icon_telegram.setFixedSize(28, 28)
        icon_telegram.setStyleSheet("border: none; background: transparent;")
        
        path_tele = os.path.join("icons", "telegram.png")
        if os.path.exists(path_tele):
            pix_t = QPixmap(path_tele)
            icon_telegram.setPixmap(pix_t.scaled(28, 28, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        
        # --- Başlık Metni ---
        title = QLabel("NOTIFICATION")
        title.setObjectName("MinorHeaderLabel")
        
        # Düzen: İkon1 - İkon2 - Esnek Boşluk - Başlık
        h_header.addWidget(icon_discord)
        h_header.addWidget(icon_telegram)
        h_header.addStretch()
        h_header.addWidget(title)
        v.addLayout(h_header)

        # 3. Ana İşlem Butonu
        self.btn_main = QPushButton("TUŞ DİNLEMEYİ BAŞLAT")
        self.btn_main.setObjectName("ThreeFiveListenButton")
        self.btn_main.clicked.connect(self.toggle_macro)
        v.addWidget(self.btn_main)

        # 4. Durum Etiketi
        self.lbl_status = QLabel("PASİF")
        self.lbl_status.setObjectName("MinorStatusLabel")
        v.addWidget(self.lbl_status)

        # 5. Alt Satır (Bilgi ve Ayarlar)
        r = QHBoxLayout()
        r.addWidget(QLabel("DURUM:"))
        
        self.lbl_mode = QLabel("OTOMATİK")
        self.lbl_mode.setStyleSheet("color: #888; font-size: 10px;")
        r.addWidget(self.lbl_mode)
        r.addStretch()
        
        btn_set = QPushButton("⚙ AYARLAR")
        btn_set.setObjectName("MinorSettingsButton")
        btn_set.clicked.connect(self.open_settings)
        r.addWidget(btn_set)
        
        v.addLayout(r)

    def _update_status(self):
        if self.macro.is_running:
            self.lbl_status.setText(f"DURUM: {self.macro.status}")
            self.lbl_status.setStyleSheet("color: #00ff4c; font-weight: bold;")
            self.btn_main.setText("TUŞ DİNLEMEYİ DURDUR")
            self.btn_main.setProperty("active", True)
        else:
            self.lbl_status.setText("DURUM: PASİF")
            self.lbl_status.setStyleSheet("color: #ff5555; font-weight: bold;")
            self.btn_main.setText("TUŞ DİNLEMEYİ BAŞLAT")
            self.btn_main.setProperty("active", False)
        
        # QSS Durumunu güncellemek için polişleme
        self.btn_main.style().unpolish(self.btn_main)
        self.btn_main.style().polish(self.btn_main)

    def toggle_macro(self):
        if self.macro.is_running: 
            self.macro.stop()
        else: 
            self.macro.start()

    def open_settings(self):
        d = NotificationSettingsDialog(self, self.config, self.macro) 
        if d.exec_():
            self.config.update(d.result_config)
            self.macro.update_config(self.config)
