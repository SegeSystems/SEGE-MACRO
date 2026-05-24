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
import ctypes
import sys

from PyQt5.QtWidgets import (
    QDialog, QGridLayout, QLabel, QComboBox, QLineEdit, QPushButton, 
    QDoubleSpinBox, QDialogButtonBox, QHBoxLayout, QWidget, QFrame, 
    QVBoxLayout, QSizePolicy, QMessageBox, QTreeWidget, QTreeWidgetItem,
    QGroupBox, QScrollArea, QAbstractItemView, QApplication, QToolButton,
    QRadioButton, QButtonGroup, QSpinBox, QCheckBox
)
from PyQt5.QtGui import QPixmap, QIcon, QColor, QPainter, QPen, QFont, QBrush, QCursor
from PyQt5.QtCore import Qt, QSize, pyqtSignal, QTimer, QPoint, QRect

# =========================================================
# SÜRÜCÜ KONTROLÜ
# =========================================================
try:
    from clicksend import KeyboardDriver, MouseDriver
    DRIVER_AVAILABLE = True
except ImportError:
    KeyboardDriver = None
    MouseDriver = None
    DRIVER_AVAILABLE = False
    print("[UYARI] clicksend sürücüsü bulunamadı! Fallback mod aktif.")

try:
    import keyboard
    KEYBOARD_LIB = True
except ImportError:
    keyboard = None
    KEYBOARD_LIB = False
    print("[UYARI] keyboard kütüphanesi bulunamadı!")

# =========================================================
# SCANCODES (GENİŞLETİLMİŞ)
# =========================================================
SCANCODES = {
    '1': 0x02, '2': 0x03, '3': 0x04, '4': 0x05, '5': 0x06, 
    '6': 0x07, '7': 0x08, '8': 0x09, '9': 0x0A, '0': 0x0B,
    'Q': 0x10, 'W': 0x11, 'E': 0x12, 'R': 0x13, 'T': 0x14,
    'Y': 0x15, 'U': 0x16, 'I': 0x17, 'O': 0x18, 'P': 0x19,
    'A': 0x1E, 'S': 0x1F, 'D': 0x20, 'F': 0x21, 'G': 0x22,
    'H': 0x23, 'J': 0x24, 'K': 0x25, 'L': 0x26,
    'Z': 0x2C, 'X': 0x2D, 'C': 0x2E, 'V': 0x2F, 'B': 0x30,
    'N': 0x31, 'M': 0x32,
    'F1': 0x3B, 'F2': 0x3C, 'F3': 0x3D, 'F4': 0x3E, 
    'F5': 0x3F, 'F6': 0x40, 'F7': 0x41, 'F8': 0x42,
    'ESC': 0x01, 'TAB': 0x0F, 'CAPSLOCK': 0x3A,
    'LSHIFT': 0x2A, 'LCTRL': 0x1D, 'LALT': 0x38,
    'SPACE': 0x39, 'ENTER': 0x1C, 'BACKSPACE': 0x0E,
}

# =========================================================
# YARDIMCI: TAM EKRAN ALAN SEÇİCİ (ÇÖKME ÖNLEMLI)
# =========================================================
class SafeScreenSelector(QDialog):
    """
    Stabilize edilmiş ekran seçici
    - Alan seçimi
    - Görsel kesme
    - Pixel renk seçimi
    """
    def __init__(self, mode="area", parent=None):
        super().__init__(parent)
        self.mode = mode  # "area", "image", "pixel"
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setFocus()  # Tuş olayları için focus al
        
        # Ekran görüntüsü al
        screen = QApplication.primaryScreen()
        self.screen_geo = screen.geometry()
        self.setGeometry(self.screen_geo)
        
        try:
            self.full_screenshot = screen.grabWindow(0)
        except:
            # Fallback: MSS kullan
            with mss.mss() as sct:
                mon = sct.monitors[1]
                img = np.array(sct.grab(mon))
                height, width, channel = img.shape
                bytesPerLine = 3 * width
                from PyQt5.QtGui import QImage
                qImg = QImage(img.data, width, height, bytesPerLine, QImage.Format_RGB888)
                self.full_screenshot = QPixmap.fromImage(qImg)
        
        self.start_pos = None
        self.current_pos = None
        self.mouse_pos = None  # Pixel modu için mouse takibi
        self.result = None
        self.setCursor(Qt.CrossCursor)
        
        # Pixel modu için mouse tracking
        if self.mode == "pixel":
            self.setMouseTracking(True)

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self.full_screenshot)
        
        if self.mode == "area":
            if self.start_pos and self.current_pos:
                selection_rect = QRect(self.start_pos, self.current_pos).normalized()
                
                # Overlay
                overlay = QColor(0, 0, 0, 120)
                painter.setBrush(QBrush(overlay))
                painter.setPen(Qt.NoPen)
                
                # Seçim dışı karart
                painter.drawRect(0, 0, self.width(), selection_rect.top())
                painter.drawRect(0, selection_rect.bottom(), self.width(), self.height() - selection_rect.bottom())
                painter.drawRect(0, selection_rect.top(), selection_rect.left(), selection_rect.height())
                painter.drawRect(selection_rect.right(), selection_rect.top(), self.width() - selection_rect.right(), selection_rect.height())
                
                # Çerçeve
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(QColor(0, 255, 0), 2))
                painter.drawRect(selection_rect)
                
                # Boyut yazısı
                painter.setPen(QColor(255, 255, 0))
                painter.setFont(QFont("Arial", 12, QFont.Bold))
                painter.drawText(selection_rect.topLeft() + QPoint(5, -5), 
                                f"{selection_rect.width()}x{selection_rect.height()}")
            else:
                painter.fillRect(self.rect(), QColor(0, 0, 0, 100))
        
        elif self.mode == "pixel":
            # Hafif overlay
            painter.fillRect(self.rect(), QColor(0, 0, 0, 50))
            
            # Talimat yazısı
            painter.setPen(QColor(0, 255, 100))
            painter.setFont(QFont("Arial", 20, QFont.Bold))
            painter.drawText(self.rect().center() + QPoint(-200, -250), 
                           "MOB ÜZERİNE TIKLA")
            painter.setPen(QColor(255, 255, 255))
            painter.setFont(QFont("Arial", 14))
            painter.drawText(self.rect().center() + QPoint(-150, -220), 
                           "ESC ile iptal")
            
            # Mouse takibi
            if self.mouse_pos:
                # Mouse etrafında büyütülmüş alan
                zoom_size = 100
                zoom_x = self.mouse_pos.x()
                zoom_y = self.mouse_pos.y()
                
                # Büyütme kutusu
                painter.setPen(QPen(QColor(0, 255, 0), 3))
                painter.setBrush(Qt.NoBrush)
                painter.drawRect(zoom_x - 50, zoom_y - 50, zoom_size, zoom_size)
                
                # Artı işareti (hedef)
                painter.setPen(QPen(QColor(255, 0, 0), 2))
                painter.drawLine(zoom_x - 15, zoom_y, zoom_x + 15, zoom_y)
                painter.drawLine(zoom_x, zoom_y - 15, zoom_x, zoom_y + 15)
                
                # Renk bilgisi göster
                img = self.full_screenshot.toImage()
                if 0 <= zoom_x < img.width() and 0 <= zoom_y < img.height():
                    color = QColor(img.pixel(zoom_x, zoom_y))
                    r, g, b = color.red(), color.green(), color.blue()
                    
                    # Renk kutusu
                    info_x = zoom_x + 60
                    info_y = zoom_y - 30
                    
                    painter.setBrush(QBrush(QColor(0, 0, 0, 180)))
                    painter.setPen(QPen(QColor(255, 255, 255), 1))
                    painter.drawRect(info_x, info_y, 120, 60)
                    
                    # Renk örneği
                    painter.setBrush(QBrush(color))
                    painter.drawRect(info_x + 5, info_y + 5, 30, 30)
                    
                    # RGB değerleri
                    painter.setPen(QColor(255, 255, 255))
                    painter.setFont(QFont("Arial", 10))
                    painter.drawText(info_x + 40, info_y + 15, f"R: {r}")
                    painter.drawText(info_x + 40, info_y + 28, f"G: {g}")
                    painter.drawText(info_x + 40, info_y + 41, f"B: {b}")

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            if self.mode == "area":
                self.start_pos = e.pos()
            elif self.mode == "pixel":
                # Renk al
                img = self.full_screenshot.toImage()
                color = QColor(img.pixel(e.x(), e.y()))
                self.result = [color.red(), color.green(), color.blue()]
                self.accept()
        elif e.button() == Qt.RightButton:
            # reject() yerine result=None yapıp accept et
            self.result = None
            self.accept()

    def mouseMoveEvent(self, e):
        if self.mode == "area" and self.start_pos:
            self.current_pos = e.pos()
            self.update()
        elif self.mode == "pixel":
            self.mouse_pos = e.pos()
            self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.mode == "area":
            if self.start_pos and self.current_pos:
                rect = QRect(self.start_pos, self.current_pos).normalized()
                if rect.width() > 5 and rect.height() > 5:
                    self.result = rect
                    self.accept()
                else:
                    QMessageBox.warning(self, "Hata", "Çok küçük alan!")
                    self.reject()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            # ESC tuşu - iptal et
            self.result = None
            print("[DEBUG] Pixel selector ESC ile kapatıldı")
            self.accept()
        else:
            super().keyPressEvent(e)

# =========================================================
# KLAVYE EYLEM DİYALOĞU
# =========================================================
class KeyActionDialog(QDialog):
    """Tuş seçimi - Klavye görseli ile direkt seçim"""
    def __init__(self, parent=None, initial_data=None):
        super().__init__(parent)
        self.setWindowTitle("⌨️ Klavye Eylemi")
        self.setStyleSheet("background-color: #1a1a1a; color: white;")
        self.setMinimumWidth(700)
        
        self.selected_key = initial_data.get("key", "R") if initial_data else "R"
        self.selected_duration = initial_data.get("duration", 0.05) if initial_data else 0.05
        
        layout = QVBoxLayout(self)
        
        # === KLAVYE DÜZENI ===
        layout.addWidget(QLabel("Direkt tuşa tıkla:"))
        
        # Klavye grid
        keyboard_layout = QGridLayout()
        
        # TÜM TUŞLAR - İŞLEVSEL TUŞLAR ÜST SIRA
        rows = [
            ["Esc", "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12"],
            ["~", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "=", "⌫"],
            ["Tab", "Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P", "[", "]", "\\"],
            ["⇧Caps", "A", "S", "D", "F", "G", "H", "J", "K", "L", ";", "'", "⏎"],
            ["⇧Shift", "Z", "X", "C", "V", "B", "N", "M", ",", ".", "/", "⇧Shift"],
            ["Ctrl", "Alt", "Space", "Alt", "Ctrl", "Home", "↑", "End"],
            ["PgUp", "←", "↓", "→", "PgDn", "Ins", "Del"],
            ["/", "*", "-", "+", "Num", ".", "⏎"]
        ]
        
        self.key_buttons = {}
        
        for row_idx, row in enumerate(rows):
            for col_idx, key in enumerate(row):
                btn = QPushButton(key)
                btn.setMinimumSize(40, 40)
                btn.setMaximumSize(40, 40)
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: #333;
                        color: white;
                        border: 1px solid #555;
                        border-radius: 3px;
                        font-weight: bold;
                    }}
                    QPushButton:hover {{
                        background-color: #444;
                    }}
                """)
                
                if key == self.selected_key:
                    btn.setStyleSheet("""
                        QPushButton {
                            background-color: #00e676;
                            color: black;
                            border: 2px solid #00c853;
                            border-radius: 3px;
                            font-weight: bold;
                        }
                    """)
                
                def make_click_handler(k):
                    def click():
                        self.select_key(k)
                    return click
                
                btn.clicked.connect(make_click_handler(key))
                self.key_buttons[key] = btn
                keyboard_layout.addWidget(btn, row_idx, col_idx)
        
        keyboard_frame = QFrame()
        keyboard_frame.setLayout(keyboard_layout)
        layout.addWidget(keyboard_frame)
        
        # === SÜRE AYARI ===
        duration_layout = QHBoxLayout()
        duration_layout.addWidget(QLabel("Basma Süresi (saniye):"))
        self.spin_duration = QDoubleSpinBox()
        self.spin_duration.setRange(0.01, 10.0)
        self.spin_duration.setValue(self.selected_duration)
        self.spin_duration.setSingleStep(0.01)
        duration_layout.addWidget(self.spin_duration)
        layout.addLayout(duration_layout)
        
        # === SEÇİLİ TUŞ GÖSTERGE ===
        self.lbl_selected = QLabel(f"Seçili Tuş: {self.selected_key}")
        self.lbl_selected.setStyleSheet("color: #00e676; font-weight: bold;")
        layout.addWidget(self.lbl_selected)
        
        # === BUTONLAR ===
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def select_key(self, key):
        """Tuş seçimi - renk değiştir ve tuş koduna çevir"""
        # Görsel tuşu gerçek tuş koduna çevir
        key_mapping = {
            "Esc": "esc", "F1": "f1", "F2": "f2", "F3": "f3", "F4": "f4", 
            "F5": "f5", "F6": "f6", "F7": "f7", "F8": "f8", "F9": "f9", 
            "F10": "f10", "F11": "f11", "F12": "f12",
            "~": "`", "1": "1", "2": "2", "3": "3", "4": "4", "5": "5",
            "6": "6", "7": "7", "8": "8", "9": "9", "0": "0", "-": "-", "=": "=",
            "⌫": "backspace",
            "Tab": "tab",
            "Q": "q", "W": "w", "E": "e", "R": "r", "T": "t", "Y": "y",
            "U": "u", "I": "i", "O": "o", "P": "p", "[": "[", "]": "]", "\\": "\\",
            "⇧Caps": "capslock",
            "A": "a", "S": "s", "D": "d", "F": "f", "G": "g", "H": "h",
            "J": "j", "K": "k", "L": "l", ";": ";", "'": "'", "⏎": "enter",
            "⇧Shift": "shift",
            "Z": "z", "X": "x", "C": "c", "V": "v", "B": "b", "N": "n", "M": "m",
            ",": ",", ".": ".", "/": "/",
            "Ctrl": "ctrl", "Alt": "alt", "Space": "space",
            "Home": "home", "↑": "up", "End": "end", "←": "left", "↓": "down", "→": "right",
            "PgUp": "pageup", "PgDn": "pagedown", "Ins": "insert", "Del": "delete",
            "Num": "numlock", "/": "/", "*": "*", "-": "-", "+": "+"
        }
        
        # Tuş koduna çevir
        actual_key = key_mapping.get(key, key)
        
        # Eski seçimi eski renge geri döndür
        old_btn = self.key_buttons.get(self.selected_key)
        if old_btn:
            old_btn.setStyleSheet("""
                QPushButton {
                    background-color: #333;
                    color: white;
                    border: 1px solid #555;
                    border-radius: 3px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #444;
                }
            """)
        
        # Yeni seçimi yeşile boya
        self.selected_key = key
        new_btn = self.key_buttons.get(key)
        if new_btn:
            new_btn.setStyleSheet("""
                QPushButton {
                    background-color: #00e676;
                    color: black;
                    border: 2px solid #00c853;
                    border-radius: 3px;
                    font-weight: bold;
                }
            """)
        
        # Etiket güncelle
        self.lbl_selected.setText(f"Seçili Tuş: {key} ({actual_key})")
        self.actual_key_code = actual_key
        
        self.selected_key = key
        self.lbl_selected.setText(f"Seçili Tuş: {key}")
        print(f"[✓] Tuş seçildi: {key}")

    def get_data(self):
        # actual_key_code varsa (mapping yapıldıysa) onu kullan
        actual_key = getattr(self, 'actual_key_code', self.selected_key)
        
        # Scancode hesapla (SCANCODES sözlüğünden)
        scancode = SCANCODES.get(actual_key.upper(), None)
        if scancode is None:
            # Bazı özel tuşlar için
            special_scancodes = {
                'esc': 0x01, 'tab': 0x0F, 'enter': 0x1C, 'space': 0x39,
                'backspace': 0x0E, 'capslock': 0x3A, 'shift': 0x2A,
                'ctrl': 0x1D, 'alt': 0x38,
                'f1': 0x3B, 'f2': 0x3C, 'f3': 0x3D, 'f4': 0x3E,
                'f5': 0x3F, 'f6': 0x40, 'f7': 0x41, 'f8': 0x42,
                'f9': 0x43, 'f10': 0x44, 'f11': 0x57, 'f12': 0x58,
                'up': 0x48, 'down': 0x50, 'left': 0x4B, 'right': 0x4D,
                'home': 0x47, 'end': 0x4F, 'pageup': 0x49, 'pagedown': 0x51,
                'insert': 0x52, 'delete': 0x53, 'numlock': 0x45,
                '1': 0x02, '2': 0x03, '3': 0x04, '4': 0x05, '5': 0x06,
                '6': 0x07, '7': 0x08, '8': 0x09, '9': 0x0A, '0': 0x0B,
            }
            scancode = special_scancodes.get(actual_key.lower(), 0x13)  # Varsayılan: R tuşu
        
        return {
            "type": "key",
            "key": actual_key,
            "scancode": scancode,  # EKLENDI!
            "display_name": self.selected_key,
            "duration": self.spin_duration.value()
        }

# =========================================================
# MOUSE EYLEM DİYALOĞU
# =========================================================
class MouseActionDialog(QDialog):
    """Mouse tıklama ayarları"""
    def __init__(self, parent=None, initial_data=None):
        super().__init__(parent)
        self.setWindowTitle("🖱️ Mouse Eylemi")
        self.setStyleSheet("background-color: #1a1a1a; color: white;")
        self.setMinimumWidth(450)
        
        layout = QVBoxLayout(self)
        
        # Tıklama tipi
        layout.addWidget(QLabel("Tıklama Türü:"))
        self.combo_click = QComboBox()
        self.combo_click.addItems(["Sol Tık", "Sağ Tık", "Çift Tık"])
        layout.addWidget(self.combo_click)
        
        # Konum modu
        layout.addWidget(QLabel("\nKonum Seçimi:"))
        self.radio_fixed = QRadioButton("Sabit Koordinat (F tuşu ile seç)")
        self.radio_current = QRadioButton("Mevcut Konum")
        self.radio_image = QRadioButton("Bulunan Görselin Ortası")
        self.radio_pixel = QRadioButton("Pixel Kontrolü ile (Bulunduğu Konuma Git)")
        
        self.btn_group = QButtonGroup()
        self.btn_group.addButton(self.radio_fixed)
        self.btn_group.addButton(self.radio_current)
        self.btn_group.addButton(self.radio_image)
        self.btn_group.addButton(self.radio_pixel)
        
        layout.addWidget(self.radio_fixed)
        layout.addWidget(self.radio_current)
        layout.addWidget(self.radio_image)
        layout.addWidget(self.radio_pixel)
        
        # Koordinat label
        self.lbl_coords = QLabel("Koordinat: Seçilmedi")
        self.lbl_coords.setStyleSheet("color: yellow; margin: 10px;")
        layout.addWidget(self.lbl_coords)
        
        # === YENİ: OFFSET ÖZELLIKLERI (Pixel/Görsel için) ===
        self.offset_group = QGroupBox("🎯 Tıklama Offset (-200 ~ +200px)")
        self.offset_group.setStyleSheet("QGroupBox { color: white; border: 1px solid #444; padding: 10px; }")
        offset_layout = QVBoxLayout(self.offset_group)
        
        # X Offset
        hbox_x = QHBoxLayout()
        hbox_x.addWidget(QLabel("X Offset:"))
        self.spin_offset_x = QSpinBox()
        self.spin_offset_x.setRange(-200, 200)
        self.spin_offset_x.setValue(0)
        self.spin_offset_x.setSuffix(" px")
        hbox_x.addWidget(self.spin_offset_x)
        hbox_x.addStretch()
        offset_layout.addLayout(hbox_x)
        
        # Y Offset
        hbox_y = QHBoxLayout()
        hbox_y.addWidget(QLabel("Y Offset:"))
        self.spin_offset_y = QSpinBox()
        self.spin_offset_y.setRange(-200, 200)
        self.spin_offset_y.setValue(0)
        self.spin_offset_y.setSuffix(" px")
        hbox_y.addWidget(self.spin_offset_y)
        hbox_y.addStretch()
        offset_layout.addLayout(hbox_y)
        
        self.offset_group.setEnabled(False)  # Varsayılan olarak gizli
        layout.addWidget(self.offset_group)
        
        # Offset'i göster/gizle logic
        self.radio_image.toggled.connect(self.on_mode_change)
        self.radio_pixel.toggled.connect(self.on_mode_change)
        self.radio_fixed.toggled.connect(self.on_mode_change)
        self.radio_current.toggled.connect(self.on_mode_change)
        
        # Butonlar
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        # Koordinat seçimi
        self.coord_x = 0
        self.coord_y = 0
        self.radio_fixed.toggled.connect(self.on_fixed_mode)
        
        # Varsayılan seçim
        self.radio_current.setChecked(True)
        
        # Mevcut veri varsa yükle
        if initial_data:
            mode = initial_data.get("mode", "current")
            if mode == "fixed":
                self.radio_fixed.setChecked(True)
                self.coord_x = initial_data.get("x", 0)
                self.coord_y = initial_data.get("y", 0)
                self.lbl_coords.setText(f"Koordinat: {self.coord_x}, {self.coord_y}")
            elif mode == "image":
                self.radio_image.setChecked(True)
            elif mode == "pixel":
                self.radio_pixel.setChecked(True)
            else:
                self.radio_current.setChecked(True)
            
            click_type = initial_data.get("click_type", "left")
            if click_type == "right":
                self.combo_click.setCurrentIndex(1)
            elif click_type == "double":
                self.combo_click.setCurrentIndex(2)
            
            # Offset'i yükle
            if "offset_x" in initial_data:
                self.spin_offset_x.setValue(initial_data["offset_x"])
            if "offset_y" in initial_data:
                self.spin_offset_y.setValue(initial_data["offset_y"])

    def on_mode_change(self, checked):
        """Mode değiştiğinde offset göster/gizle"""
        if checked:
            # Offset'i sadece pixel veya image modunda göster
            if self.radio_pixel.isChecked() or self.radio_image.isChecked():
                self.offset_group.setEnabled(True)
            else:
                self.offset_group.setEnabled(False)
            
            # Fixed mode için koordinat seçimi
            if self.radio_fixed.isChecked() and KEYBOARD_LIB:
                self.hide()
                QTimer.singleShot(100, self.capture_coordinate)
    
    def on_fixed_mode(self, checked):
        """Fixed mode seçildiğinde offset devre dışı bırak"""
        if checked:
            self.offset_group.setEnabled(False)

    def capture_coordinate(self):
        if not KEYBOARD_LIB:
            QMessageBox.warning(self, "Hata", "keyboard kütüphanesi yüklenmemiş!")
            self.show()
            return
        
        QMessageBox.information(None, "Koordinat Seç", 
                               "Mouse'u hedef noktaya getirin ve 'F' tuşuna basın.\nESC ile iptal.")
        
        # Timer ile F tuşunu kontrol et (non-blocking)
        self.coord_timer = QTimer()
        self.coord_timer.timeout.connect(self.check_f_key)
        self.coord_timer.start(50)  # Her 50ms kontrol et
    
    def check_f_key(self):
        """F tuşu veya ESC kontrolü (non-blocking)"""
        if keyboard.is_pressed('f'):
            self.coord_x, self.coord_y = pyautogui.position()
            self.lbl_coords.setText(f"Koordinat: {self.coord_x}, {self.coord_y}")
            self.coord_timer.stop()
            self.show()
        elif keyboard.is_pressed('esc'):
            self.radio_current.setChecked(True)
            self.coord_timer.stop()
            self.show()

    def validate_and_accept(self):
        if self.radio_fixed.isChecked():
            if self.coord_x == 0 and self.coord_y == 0:
                QMessageBox.warning(self, "Hata", "Lütfen koordinat seçin!")
                return
        self.accept()

    def get_data(self):
        click_type = "left"
        if self.combo_click.currentIndex() == 1:
            click_type = "right"
        elif self.combo_click.currentIndex() == 2:
            click_type = "double"
        
        mode = "current"
        if self.radio_fixed.isChecked():
            mode = "fixed"
        elif self.radio_image.isChecked():
            mode = "image"
        elif self.radio_pixel.isChecked():
            mode = "pixel"
        
        return {
            "type": "mouse",
            "click_type": click_type,
            "mode": mode,
            "x": self.coord_x,
            "y": self.coord_y,
            "offset_x": self.spin_offset_x.value(),
            "offset_y": self.spin_offset_y.value()
        }

# =========================================================
# GECİKME DİYALOĞU
# =========================================================
class DelayDialog(QDialog):
    """Bekleme süresi ayarı"""
    def __init__(self, parent=None, initial_value=0.5):
        super().__init__(parent)
        self.setWindowTitle("⏱️ Gecikme")
        self.setStyleSheet("background-color: #1a1a1a; color: white;")
        
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Bekleme Süresi (saniye):"))
        
        self.spin = QDoubleSpinBox()
        self.spin.setRange(0.01, 60.0)
        self.spin.setValue(initial_value)
        self.spin.setSingleStep(0.1)
        layout.addWidget(self.spin)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_value(self):
        return self.spin.value()

class LoopDialog(QDialog):
    """Döngü ayarı"""
    def __init__(self, parent=None, initial_count=10):
        super().__init__(parent)
        self.setWindowTitle("🔁 Döngü")
        self.setStyleSheet("background-color: #1a1a1a; color: white;")
        self.setMinimumWidth(300)
        
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Kaç Kez Tekrarlanacak:"))
        
        self.spin = QSpinBox()
        self.spin.setRange(1, 10000)
        self.spin.setValue(initial_count)
        layout.addWidget(self.spin)
        
        layout.addWidget(QLabel("Döngü içindeki adımlar alt seviyeye eklenecek.", styleSheet="color: #888; font-size: 10px;"))
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def get_count(self):
        return self.spin.value()

class PixelDialog(QDialog):
    """Pixel renk kontrolü"""
    def __init__(self, parent=None, initial_data=None):
        super().__init__(parent)
        self.setWindowTitle("🎨 Pixel Kontrol")
        self.setStyleSheet("background-color: #1a1a1a; color: white;")
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout(self)
        
        # Pixel renk seçimi
        hbox = QHBoxLayout()
        hbox.addWidget(QLabel("Hedef Renk:"))
        self.lbl_color = QLabel("Seçilmedi")
        self.lbl_color.setStyleSheet("border: 1px solid #444; padding: 5px;")
        hbox.addWidget(self.lbl_color)
        
        btn_pick = QPushButton("RENGİ SEÇ")
        btn_pick.clicked.connect(self.pick_color)
        hbox.addWidget(btn_pick)
        layout.addLayout(hbox)
        
        # Tolerans
        layout.addWidget(QLabel("Renk Toleransı (0-255):"))
        self.spin_tolerance = QSpinBox()
        self.spin_tolerance.setRange(0, 255)
        self.spin_tolerance.setValue(30)
        layout.addWidget(self.spin_tolerance)
        
        # Koşul tipi
        layout.addWidget(QLabel("Koşul:"))
        self.combo = QComboBox()
        self.combo.addItems(["Pixel VARSA", "Pixel YOKSA"])
        layout.addWidget(self.combo)
        
        # === YENİ: OFFSET ÖZELLIKLERI ===
        layout.addWidget(QLabel("\n🎯 Tıklama Offset (0-200px):"))
        
        # X Offset
        hbox_x = QHBoxLayout()
        hbox_x.addWidget(QLabel("X Offset:"))
        self.spin_offset_x = QSpinBox()
        self.spin_offset_x.setRange(-200, 200)
        self.spin_offset_x.setValue(0)
        self.spin_offset_x.setSuffix(" px")
        hbox_x.addWidget(self.spin_offset_x)
        hbox_x.addStretch()
        layout.addLayout(hbox_x)
        
        # Y Offset
        hbox_y = QHBoxLayout()
        hbox_y.addWidget(QLabel("Y Offset:"))
        self.spin_offset_y = QSpinBox()
        self.spin_offset_y.setRange(-200, 200)
        self.spin_offset_y.setValue(0)
        self.spin_offset_y.setSuffix(" px")
        hbox_y.addWidget(self.spin_offset_y)
        hbox_y.addStretch()
        layout.addLayout(hbox_y)
        
        self.pixel_rgb = None
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
        # Önceki veri varsa yükle
        if initial_data:
            if "rgb" in initial_data:
                self.pixel_rgb = initial_data["rgb"]
                r, g, b = self.pixel_rgb
                self.lbl_color.setText(f"RGB({r}, {g}, {b})")
                self.lbl_color.setStyleSheet(
                    f"background-color: rgb({r}, {g}, {b}); "
                    f"border: 1px solid #444; padding: 5px; color: white;"
                )
            
            if "tolerance" in initial_data:
                self.spin_tolerance.setValue(initial_data["tolerance"])
            
            if "trigger_on_missing" in initial_data:
                self.combo.setCurrentIndex(1 if initial_data["trigger_on_missing"] else 0)
            
            if "offset_x" in initial_data:
                self.spin_offset_x.setValue(initial_data["offset_x"])
            
            if "offset_y" in initial_data:
                self.spin_offset_y.setValue(initial_data["offset_y"])
    
    def pick_color(self):
        """Renk seçici aç"""
        # Dialog'u gizlemek yerine opacity 0 yap
        self.setWindowOpacity(0)
        QApplication.processEvents()
        # NON-BLOCKING bekle
        QTimer.singleShot(300, self._do_pick)
    
    def _do_pick(self):
        try:
            selector = SafeScreenSelector(mode="pixel", parent=self)
            
            # Selector'ı zorla göster
            selector.showFullScreen()
            selector.raise_()
            selector.activateWindow()
            selector.setFocus()
            QApplication.processEvents()
            
            print("[DEBUG] Pixel selector açıldı, bekleniyor...")
            
            result = selector.exec_()
            
            print(f"[DEBUG] Selector kapandı, result={result}, selector.result={selector.result}")
            
            if result == QDialog.Accepted and selector.result:
                self.pixel_rgb = selector.result
                r, g, b = self.pixel_rgb
                self.lbl_color.setText(f"RGB({r}, {g}, {b})")
                self.lbl_color.setStyleSheet(
                    f"background-color: rgb({r}, {g}, {b}); "
                    f"border: 1px solid #444; padding: 5px; color: white;"
                )
                print(f"[INFO] Pixel rengi seçildi: RGB({r}, {g}, {b})")
            else:
                print("[INFO] Pixel seçimi iptal edildi")
            
            # Mouse'u ekranın ortasına getir (antiafk.py gibi)
            screen_w, screen_h = pyautogui.size()
            pyautogui.moveTo(int(screen_w / 2), int(screen_h / 2))
            print(f"[DEBUG] Mouse ekranın ortasına döndürüldü: ({int(screen_w/2)}, {int(screen_h/2)})")
                
        except Exception as e:
            print(f"[HATA] Pixel seçici hatası: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.warning(None, "Hata", f"Pixel seçici açılamadı:\n{e}")
        finally:
            # Dialog'u tekrar görünür yap
            self.setWindowOpacity(1)
            self.raise_()
            self.activateWindow()
    
    def accept(self):
        """OK butonuna basıldığında - pixel seçilmiş mi kontrol et"""
        if not self.pixel_rgb:
            QMessageBox.warning(self, "Hata", "Lütfen önce renk seçin!")
            return
        super().accept()
    
    def get_data(self):
        if not self.pixel_rgb:
            return None
        return {
            "type": "pixel_check",
            "rgb": self.pixel_rgb,
            "tolerance": self.spin_tolerance.value(),
            "trigger_on_missing": self.combo.currentIndex() == 1,
            "offset_x": self.spin_offset_x.value(),
            "offset_y": self.spin_offset_y.value(),
            "sub_steps": []
        }

# =========================================================
# MAKRO MOTORU (GELİŞMİŞ)
# =========================================================
class MacroEngine:
    """
    Gelişmiş macro çalıştırma motoru
    - Interception driver desteği
    - Görsel tarama
    - Koşullu işlemler
    - Alt-adımlar
    - ANTI-AFK: Blacklist + Target validation
    """
    def __init__(self):
        self.kb_driver = KeyboardDriver() if DRIVER_AVAILABLE else None
        self.mouse_driver = MouseDriver() if DRIVER_AVAILABLE else None
        
        self.steps = []
        self.running = False
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        
        # Son bulunan görsel konumu (image mode için)
        self.last_image_pos = None
        
        # Son bulunan pixel konumu (pixel mode için)
        self.last_pixel_pos = None
        
        # Son kontrol edilen pixel rengi (validasyon için)
        self.last_pixel_rgb = None
        
        # Mevcut tarama alanı (aktif olarak kullanılan region)
        self.current_region = None
        
        # Tarama cache (performans için)
        self.scan_regions = {}
        
        # === ANTI-AFK FARM STİLİ EKLENTILER ===
        # Blacklist: (x, y, timestamp) - 20 saniye boyunca o koordinatları tercih etme
        self.blacklist_coords = []
        
        # Şu anki hedef mob koordinatı - aynı mobu kesmeye devam et
        self.current_target_pos = None
        
        # Şu anki hedef mob'u tıklamaya başlanan zaman (HP check için)
        self.target_attack_start_time = None
        
        # HP kontrol yapıldı mı? (tekrar kontrol etme)
        self.hp_check_done = False
        
        # === HP BAR VISUAL TRACKING ===
        # HP region (x, y, w, h) - UI'dan seçilecek
        self.hp_region = None
        
        # HP kontrol modu: "dynamic" (azalıyor mu) vs "static" (var mı)
        self.hp_mode = "dynamic"
        
        # HP başlangıç piksel sayısı (ilk HP bars)
        self.hp_reference = None
        
        # Şu anki HP piksel sayısı
        self.current_hp_ratio = 1.0

    def update_config(self, config):
        """Konfigürasyonu güncelle"""
        with self.lock:
            self.steps = config.get("steps", [])
            self.scan_regions = config.get("scan_regions", {})
            
            # === HP BAR REGION ===
            if "hp_region" in config and config["hp_region"]:
                self.set_hp_region(tuple(config["hp_region"]))
                print(f"[HP] Region set from config: {config['hp_region']}")
            
            # === HP MODE (DİNAMİK vs STATİK) ===
            if "hp_mode" in config:
                self.hp_mode = config["hp_mode"]
                print(f"[HP] Mode set to: {self.hp_mode.upper()}")

    def start(self):
        """Macro'yu başlat"""
        if not self.running:
            self.stop_event.clear()
            self.running = True
            threading.Thread(target=self._run_loop, daemon=True).start()

    def stop(self):
        """Macro'yu durdur"""
        self.stop_event.set()
        self.running = False

    def is_running(self):
        return self.running

    def _run_loop(self):
        """Ana döngü"""
        while not self.stop_event.is_set():
            for step in self.steps:
                if self.stop_event.is_set():
                    break
                self._execute_step(step)
            
            # Döngü arası kısa bekleme
            time.sleep(0.005)

    def _execute_step(self, step):
        """Tek bir adımı çalıştır"""
        step_type = step.get("type")
        
        try:
            if step_type == "key":
                self._execute_key(step)
            
            elif step_type == "mouse":
                self._execute_mouse(step)
            
            elif step_type == "delay":
                time.sleep(step.get("value", 0.5))
            
            elif step_type == "scan_region":
                self._execute_scan_region(step)
            
            elif step_type == "image_check":
                self._execute_image_check(step)
            
            elif step_type == "pixel_check":
                self._execute_pixel_check(step)
            
            elif step_type == "loop":
                self._execute_loop(step)
        
        except Exception as e:
            print(f"[HATA] Adım çalıştırılamadı: {e}")

    def _execute_key(self, step):
        """Tuş bas"""
        scancode = step.get("scancode")
        duration = step.get("duration", 0.05)
        key_name = step.get("key", "r").lower()
        
        print(f"[DEBUG] Tuş basılıyor: key={key_name}, scancode={scancode}, duration={duration}")
        
        if self.kb_driver and scancode is not None:
            try:
                self.kb_driver.tusbas(scancode, duration)
                print(f"[✓] Driver ile tuş basıldı: {key_name}")
            except Exception as e:
                print(f"[UYARI] Driver hatası, pyautogui kullanılıyor: {e}")
                pyautogui.press(key_name)
        else:
            # Fallback: pyautogui
            print(f"[INFO] PyAutoGUI ile tuş basılıyor: {key_name}")
            pyautogui.keyDown(key_name)
            time.sleep(duration)
            pyautogui.keyUp(key_name)

    def _execute_mouse(self, step):
        """Mouse tıklama"""
        click_type = step.get("click_type", "left")
        mode = step.get("mode", "current")
        
        x, y = 0, 0
        print(f"[DEBUG] Mouse eylemi: Mode={mode}, ClickType={click_type}")
        
        if mode == "fixed":
            x = step.get("x", 0)
            y = step.get("y", 0)
            print(f"[DEBUG] Fixed mode: ({x}, {y})")
        
        elif mode == "image":
            if self.last_image_pos:
                x, y = self.last_image_pos
                print(f"[DEBUG] Image mode: ({x}, {y})")
            else:
                print("[UYARI] Görsel konumu bulunamadı, tıklama atlandı")
                return
        
        elif mode == "pixel":
            print(f"[DEBUG] Pixel mode başladı. last_pixel_pos={self.last_pixel_pos}")
            if self.last_pixel_pos:
                x, y = self.last_pixel_pos
                # np.int64 -> int dönüştür
                x, y = int(x), int(y)
                print(f"[✓] Pixel modu: ({x}, {y}) konumuna gidiliyor")
                
                # === YENİ: Centroid etrafında (±20px) piksel kontrolü ===
                # Pixel kontrolünün RGB değerini al
                target_rgb = self.last_pixel_rgb  # Son kontrol edilen renk
                
                if target_rgb and self.current_region:
                    # Hedef konuma offset UYGULANMASIN - last_pixel_pos zaten tam konumdur
                    check_x = x
                    check_y = y
                    
                    # Centroid etrafı validasyonu
                    print(f"[DEBUG] Centroid etrafı validasyonu: ({check_x}, {check_y}) ±60px içinde RGB{tuple(target_rgb)} aranıyor...")
                    
                    # Ekran snapshot al
                    try:
                        with mss.mss() as sct:
                            screenshot = np.array(sct.grab(sct.monitors[1]))
                            tolerance = step.get("tolerance", 20)
                            
                            # Centroid etrafında ±60px içinde ara (oyun hareket ediyor)
                            validation_radius = 60
                            found_pixel = False
                            
                            validated_pixel_x = None
                            validated_pixel_y = None
                            min_distance = float('inf')  # === EN YAKIN SEÇMEK İÇİN ===
                            
                            for dy in range(-validation_radius, validation_radius + 1, 2):
                                for dx in range(-validation_radius, validation_radius + 1, 2):
                                    test_x = check_x + dx
                                    test_y = check_y + dy
                                    
                                    if 0 <= test_x < screenshot.shape[1] and 0 <= test_y < screenshot.shape[0]:
                                        pixel_color = screenshot[test_y, test_x, :3]
                                        
                                        r_diff = abs(int(pixel_color[2]) - target_rgb[0])
                                        g_diff = abs(int(pixel_color[1]) - target_rgb[1])
                                        b_diff = abs(int(pixel_color[0]) - target_rgb[2])
                                        
                                        if r_diff <= tolerance and g_diff <= tolerance and b_diff <= tolerance:
                                            # === EN YAKIN OLANINI SEÇ ===
                                            distance = abs(test_x - check_x) + abs(test_y - check_y)
                                            if distance < min_distance:
                                                print(f"[✓] BULUNDU! ({test_x}, {test_y}) konumunda canavarın rengi! (Uzaklık: {distance})")
                                                validated_pixel_x = test_x
                                                validated_pixel_y = test_y
                                                found_pixel = True
                                                min_distance = distance
                            
                            if not found_pixel:
                                print(f"[✗] UYARI! Centroid ±60px etrafında canavarın rengi bulunamadı! Tıklama İPTAL!")
                                return
                            
                            # === Centroid'e EN YAKIN validasyon pikseline tıkla ===
                            if validated_pixel_x is not None and validated_pixel_y is not None:
                                x = validated_pixel_x
                                y = validated_pixel_y
                                print(f"[DEBUG] Centroid'e EN YAKIN piksel ile güncellendi: ({x}, {y}) - Uzaklık: {min_distance}")
                    except Exception as e:
                        print(f"[HATA] Validasyon başarısız: {e}")
            else:
                print("[UYARI] ⚠️ Pixel konumu bulunamadı! last_pixel_pos=None")
                return
        
        else:  # current
            x, y = pyautogui.position()
            print(f"[DEBUG] Current mode: ({x}, {y})")
        
        # === OFFSET'İ EKLE (SADECE Image/Current modları için, Pixel için değil!) ===
        # Pixel mode'da offset zaten pixel detection'da eklendi!
        if mode != "pixel":
            offset_x = step.get("offset_x", 0)
            offset_y = step.get("offset_y", 0)
            
            if offset_x != 0 or offset_y != 0:
                original_x, original_y = x, y
                x = int(x) + offset_x
                y = int(y) + offset_y
                print(f"[DEBUG] Offset uygulandı: ({original_x}, {original_y}) + ({offset_x}, {offset_y}) = ({x}, {y})")
        
        # Tıkla
        print(f"[ACTION] Tıklama yapılıyor: {click_type} @ ({x}, {y})")
        
        x_int = int(x)
        y_int = int(y)
        
        # === DRIVER-FIRST APPROACH: Interception Mouse Driver var mı? ===
        if self.mouse_driver:
            print(f"[✓] Interception MouseDriver kullanılıyor: {click_type} @ ({x_int}, {y_int})")
            try:
                if click_type == "left":
                    self.mouse_driver.leftclick(0.05, x_int, y_int)
                elif click_type == "right":
                    self.mouse_driver.rightclick(0.05, x_int, y_int)
                elif click_type == "double":
                    self.mouse_driver.leftclick(0.05, x_int, y_int)
                    time.sleep(0.1)
                    self.mouse_driver.leftclick(0.05, x_int, y_int)
                print(f"[✓] Driver tıklaması başarılı!")
            except Exception as e:
                print(f"[UYARI] Driver hatası: {e}, SendInput fallback'e geçiliyor...")
                self._fallback_mouse_click(click_type, x_int, y_int)
        else:
            print(f"[INFO] Driver yok, SendInput kullanılıyor")
            self._fallback_mouse_click(click_type, x_int, y_int)
        
        print(f"[✓] Tık başarılı! ({x_int}, {y_int})")
        
        # === ANTI-AFK: Target tracking başlat ===
        if click_type == "left":
            self.current_target_pos = (x_int, y_int)
            self.target_attack_start_time = time.time()
            self.hp_check_done = False
            print(f"[ANTI-AFK] Target lock: ({x_int}, {y_int}) - HP check 2 saniye sonra yapılacak")
            
            # === ANTI-AFK: 2 SANIYE SONRA HP CHECK ===
            # NOT: time.sleep UI'yi dondurur - threading ile yap
            def delayed_hp_check():
                time.sleep(2.0)
                try:
                    has_damage = self.check_hp_damage()
                    if not has_damage:
                        print(f"[⚠️ ANTI-AFK] Mob hasar almıyor! ({x_int}, {y_int}) → BLACKLIST!")
                        self.blacklist_coords.append((x_int, y_int, time.time()))
                        self.current_target_pos = None
                    else:
                        print(f"[✓ ANTI-AFK] Mob hasar alıyor!")
                        self.hp_check_done = True
                except Exception as e:
                    print(f"[ERROR] HP check thread: {e}")
            
            # Thread'de yap (UI donmasın)
            import threading
            t = threading.Thread(target=delayed_hp_check, daemon=True)
            t.start()
            
            # İlk kontrolü yap (2 saniye beklemeden)
            has_damage = True  # Varsayılan True

            # HP check thread'de yapılıyor (yukarıda delayed_hp_check)

    def _execute_image_check(self, step):
        """Görsel kontrolü ve alt işlemler"""
        image_path = step.get("image_path")
        region = step.get("region")
        threshold = step.get("threshold", 0.75)
        trigger_on_missing = step.get("trigger_on_missing", False)
        sub_steps = step.get("sub_steps", [])
        check_count = step.get("check_count", 3)  # Kaç kez kontrol edilecek
        check_delay = step.get("check_delay", 0.1)  # Kontroller arası bekleme
        
        if not image_path or not os.path.exists(image_path):
            print(f"[HATA] Görsel bulunamadı: {image_path}")
            return
        
        print(f"[DEBUG] Görsel kontrol: {os.path.basename(image_path)}")
        print(f"[DEBUG] Region: {region}")
        print(f"[DEBUG] Trigger on missing: {trigger_on_missing}")
        print(f"[DEBUG] Check count: {check_count}x")
        
        # Birkaç kez kontrol et
        found_count = 0
        for i in range(check_count):
            found = self._check_image(image_path, region, threshold)
            if found:
                found_count += 1
            time.sleep(check_delay)
        
        # Çoğunlukla bulundu mu?
        mostly_found = found_count >= (check_count / 2)
        
        print(f"[DEBUG] Görsel bulunma oranı: {found_count}/{check_count}")
        print(f"[DEBUG] Sonuç: {'BULUNDU' if mostly_found else 'BULUNAMADI'}")
        
        # Koşul kontrolü
        should_execute = (mostly_found and not trigger_on_missing) or (not mostly_found and trigger_on_missing)
        
        print(f"[DEBUG] Alt adımlar çalışacak mı: {should_execute}")
        
        if should_execute:
            print(f"[INFO] ✅ Alt adımlar çalıştırılıyor ({len(sub_steps)} adım)")
            for sub_step in sub_steps:
                if self.stop_event.is_set():
                    break
                self._execute_step(sub_step)
        else:
            print(f"[INFO] ⏭️ Koşul sağlanmadı, atlandı")

    def _check_image(self, image_path, region, threshold):
        """Template matching ile görsel ara"""
        try:
            with mss.mss() as sct:
                # Ekran görüntüsü al
                if region and len(region) == 4 and region[2] > 0 and region[3] > 0:
                    # Belirtilen alan
                    mon = {
                        "left": int(region[0]),
                        "top": int(region[1]),
                        "width": int(region[2]),
                        "height": int(region[3])
                    }
                else:
                    # Tam ekran (region belirtilmemişse)
                    mon = sct.monitors[1]
                    region = [mon["left"], mon["top"], mon["width"], mon["height"]]
                
                screenshot = np.array(sct.grab(mon))
                
                # Gri tonlamaya çevir
                gray_screen = cv2.cvtColor(screenshot, cv2.COLOR_BGRA2GRAY)
                
                # Template yükle
                template = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
                
                if template is None:
                    print(f"[HATA] Template okunamadı: {image_path}")
                    return False
                
                # Template matching
                result = cv2.matchTemplate(gray_screen, template, cv2.TM_CCOEFF_NORMED)
                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
                
                if max_val >= threshold:
                    # Görselin merkez koordinatını kaydet
                    h, w = template.shape
                    center_x = region[0] + max_loc[0] + w // 2
                    center_y = region[1] + max_loc[1] + h // 2
                    self.last_image_pos = (center_x, center_y)
                    return True
                
                return False
        
        except Exception as e:
            print(f"[HATA] Görsel tarama hatası: {e}")
            return False

    def _execute_pixel_check(self, step):
        """Pixel renk kontrolü"""
        rgb = step.get("rgb", [255, 255, 255])
        tolerance = step.get("tolerance", 30)  # Varsayılan 30
        trigger_on_missing = step.get("trigger_on_missing", False)
        sub_steps = step.get("sub_steps", [])
        
        # Region parametresini al, yoksa current_region'u kullan
        region = step.get("region")
        if not region and self.current_region:
            region = self.current_region
            print(f"[DEBUG] Region parametresi yok, current_region kullanılıyor: {region}")
        
        print(f"[DEBUG] Pixel Check Başlıyor: RGB{tuple(rgb)}, Tolerans={tolerance}, TriggerMissing={trigger_on_missing}, Region={region}")
        
        try:
            with mss.mss() as sct:
                # Tarama alanı varsa o bölgeyi al, yoksa tam ekran al
                if region:
                    x, y, w, h = region
                    screenshot = np.array(sct.grab({"left": x, "top": y, "width": w, "height": h}))
                    region_offset_x, region_offset_y = x, y
                else:
                    screenshot = np.array(sct.grab(sct.monitors[1]))
                    region_offset_x, region_offset_y = 0, 0
                
                # === ANTI-AFK FARM STİLİ: HSV COLOR SPACE + CONNECTED COMPONENTS ===
                print(f"[DEBUG] HSV color space kullanılıyor...")
                
                # RGB -> HSV dönüşümü (Antiafk farm tarzı)
                scr_hsv = cv2.cvtColor(screenshot[:, :, :3], cv2.COLOR_BGR2HSV)
                target_bgr = np.array([[[rgb[2], rgb[1], rgb[0]]]], dtype=np.uint8)
                target_hsv = cv2.cvtColor(target_bgr, cv2.COLOR_BGR2HSV)[0][0]
                
                h = int(target_hsv[0])
                s = int(target_hsv[1])
                v = int(target_hsv[2])
                
                # HSV tolerans (antiafk farm'a benzer)
                h_tol = 8
                s_tol = 50
                v_tol = 50
                
                h_min = max(0, h - h_tol)
                s_min = max(0, s - s_tol)
                v_min = max(10, v - v_tol)
                
                h_max = min(180, h + h_tol)
                s_max = min(255, s + s_tol)
                v_max = min(255, v + v_tol)
                
                lower = np.array([h_min, s_min, v_min], dtype=np.uint8)
                upper = np.array([h_max, s_max, v_max], dtype=np.uint8)
                
                print(f"[DEBUG] HSV Aralığı: H({h_min}-{h_max}), S({s_min}-{s_max}), V({v_min}-{v_max})")
                print(f"[DEBUG] Region Offset: ({region_offset_x}, {region_offset_y})")
                
                # Maske oluştur
                mask = cv2.inRange(scr_hsv, lower, upper)
                
                # Morphological Operations (antiafk farm'a benzer)
                kernel = np.ones((4, 4), np.uint8)
                mask = cv2.erode(mask, kernel, iterations=1)
                mask = cv2.dilate(mask, kernel, iterations=3)
                
                # Connected Components (antiafk farm'a benzer)
                num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
                
                pixel_found = False
                abs_x = None
                abs_y = None
                valid_components = 0
                
                # === ANTI-AFK: Blacklist temizle (20 saniyeden eski girdileri sil) ===
                now = time.time()
                self.blacklist_coords = [c for c in self.blacklist_coords if now - c[2] < 20.0]
                print(f"[DEBUG] Blacklist koordinat sayısı: {len(self.blacklist_coords)}")
                
                # === ANTI-AFK: Şu anki target hala alive mi? ===
                if self.current_target_pos:
                    target_x, target_y = self.current_target_pos
                    
                    # Target'in etrafında renk kontrol et
                    check_radius = 40
                    target_still_alive = False
                    
                    for dy in range(-check_radius, check_radius + 1, 5):
                        for dx in range(-check_radius, check_radius + 1, 5):
                            test_x = target_x + dx
                            test_y = target_y + dy
                            
                            if 0 <= test_x < screenshot.shape[1] and 0 <= test_y < screenshot.shape[0]:
                                pixel_color = screenshot[test_y, test_x, :3]
                                
                                r_diff = abs(int(pixel_color[2]) - rgb[0])
                                g_diff = abs(int(pixel_color[1]) - rgb[1])
                                b_diff = abs(int(pixel_color[0]) - rgb[2])
                                
                                if r_diff <= 25 and g_diff <= 25 and b_diff <= 25:
                                    target_still_alive = True
                                    break
                        if target_still_alive:
                            break
                    
                    if target_still_alive:
                        # Target hala alive - aynı mobu devam et (yeni mob seçme)
                        print(f"[🎯 ANTI-AFK] Current target ({target_x}, {target_y}) hala alive! Devam ediliyor...")
                        self.last_pixel_pos = self.current_target_pos
                        pixel_found = True
                        abs_x, abs_y = target_x, target_y
                    else:
                        # Target ölmüş - blacklist'e ekle ve yeni mob ara
                        print(f"[💀 ANTI-AFK] Target ({target_x}, {target_y}) öldü! Blacklist'e ekleniyor...")
                        self.blacklist_coords.append((target_x, target_y, time.time()))
                        self.current_target_pos = None
                        pixel_found = False
                else:
                    # Target yok, normal arama yapılacak
                    pass
                
                # === ANTI-AFK: Eğer target alive ise bu aşamaları skip et ===
                if not (self.current_target_pos and pixel_found):
                    # Area filtering (antiafk farm'a benzer: 40 < area < 10000)
                    best_coord = None
                    for i in range(1, num_labels):
                        area = stats[i, cv2.CC_STAT_AREA]
                        if 40 < area < 10000:
                            cx, cy = centroids[i]
                            final_x = int(region_offset_x + cx)
                            final_y = int(region_offset_y + cy)
                            
                            # === ANTI-AFK: Blacklist kontrol - bu koordinat son 20 saniyede tıklandı mı? ===
                            is_blacklisted = any(abs(final_x - bx) < 40 and abs(final_y - by) < 40 for bx, by, bt in self.blacklist_coords)
                            
                            if not is_blacklisted:
                                best_coord = (final_x, final_y)
                                valid_components += 1
                                pixel_found = True
                                # İlk geçerli (blacklist'e girmemiş) bileşeni al
                                abs_x, abs_y = final_x, final_y
                                break
                
                if pixel_found and abs_x is not None and abs_y is not None:
                    self.last_pixel_rgb = rgb
                    self.last_pixel_pos = (abs_x, abs_y)
                    
                    # === YENİ MOB SEÇILDI (veya target alive) ===
                    if not self.current_target_pos:
                        # Yeni mob seçildi
                        self.current_target_pos = (abs_x, abs_y)
                        self.target_attack_start_time = time.time()
                        self.hp_check_done = False
                    
                    print(f"[✓] Pixel BULUNDU: ({abs_x}, {abs_y}) - ConnectedComponents ile bulundu!")
                    print(f"[DEBUG] Geçerli bileşen sayısı: {valid_components}, Area Filtering: 40 < area < 10000")
                    print(f"[DEBUG] ⭐ YENİ MOB HEDEFI AYARLANDI: ({abs_x}, {abs_y})")
                else:
                    print(f"[✗] Pixel BULUNAMADI (Area filtering başarısız veya tümü blacklist'te)")
                    self.last_pixel_pos = None
                
                print(f"[DEBUG] Pixel kontrolü: HSV{tuple([h,s,v])}, Bulundu: {pixel_found}")
                
                # Koşul kontrolü
                should_execute = (pixel_found and not trigger_on_missing) or (not pixel_found and trigger_on_missing)
                
                if should_execute:
                    print(f"[INFO] ✅ Pixel kontrolü GEÇTI, alt adımlar çalışıyor")
                    print(f"[INFO] Son pixel konumu: {self.last_pixel_pos}")
                    for sub_step in sub_steps:
                        if self.stop_event.is_set():
                            break
                        print(f"[DEBUG] Alt adım çalıştırılıyor: {sub_step.get('type')}")
                        self._execute_step(sub_step)
                else:
                    print(f"[INFO] ⏭️ Pixel kontrolü atlandı (koşul sağlanmadı)")
                
        except Exception as e:
            print(f"[HATA] Pixel kontrolü hatası: {e}")
            import traceback
            traceback.print_exc()

    def _execute_loop(self, step):
        """Döngü işlemi"""
        count = step.get("count", 1)
        sub_steps = step.get("sub_steps", [])
        
        for i in range(count):
            if self.stop_event.is_set():
                break
            for sub_step in sub_steps:
                if self.stop_event.is_set():
                    break
                self._execute_step(sub_step)
    
    def _execute_scan_region(self, step):
        """Tarama alanı belirle ve alt adımları çalıştır"""
        region = step.get("region")
        sub_steps = step.get("sub_steps", [])
        
        # Global region'u ayarla (çocuk adımlara otomatik uygulanacak)
        self.current_region = region
        
        print(f"[INFO] 📐 Tarama alanı ayarlandı: {region}")
        
        # Tüm alt adımlara bu region'u aktar (varsa)
        for sub_step in sub_steps:
            if self.stop_event.is_set():
                break
            
            # Eğer alt adımda region yoksa, current_region'u kullan
            if not sub_step.get("region") and self.current_region:
                sub_step["region"] = self.current_region
                print(f"[INFO] → {sub_step.get('type')} kontrolüne region aktarıldı")
            
            self._execute_step(sub_step)
        
        # Tarama alanını sıfırla
        self.current_region = None
    
    def test_hp_region(self, region):
        """HP region'ı test et ve sonuçları göster"""
        try:
            print(f"\n[🧪 TEST] HP Region test başladı: {region}")
            print(f"[TEST] 3 saniye içinde HP bar'ı göster...")
            
            import time
            time.sleep(1)
            
            # 3 tane screenshot al
            for i in range(3):
                time.sleep(1)
                x, y, w, h = region
                
                with mss.mss() as sct:
                    img = np.array(sct.grab({"left": x, "top": y, "width": w, "height": h}))
                    hp_count, total = self._count_hp_pixels(img)
                    
                    print(f"[TEST {i+1}/3] HP Pikselleri: {hp_count} / {total:.0f}")
            
            print(f"[✓ TEST] HP Region testi TAMAMLANDI!")
            print(f"Sonuç: Eğer yukarıda sayılar DEĞİŞİYORSA → DİNAMİK modunu seç")
            print(f"Sonuç: Eğer sayılar AYNI KALIYORSA → STATİK modunu seç\n")
            
        except Exception as e:
            print(f"[ERROR] HP Region test error: {e}")
            import traceback
            traceback.print_exc()
    
    # === HP BAR VISUAL TRACKING FONKSİYONLARI (hpmp.py'den uyarlanmış) ===
    
    def set_hp_region(self, region):
        """HP bar alanını ayarla (x, y, w, h)"""
        # NOT: Lock update_config'de alınıyor, burada tekrar alma!
        self.hp_region = region
        self.hp_reference = None  # Referansı sıfırla
    
    def _count_hp_pixels(self, img_np):
        """HP pikselleri say - ANY RENK (seçilen alanda hangi renk varsa onu takip et)"""
        try:
            # === RGBA varsa RGB'ye çevir ===
            if img_np.shape[2] == 4:  # RGBA
                img_np = cv2.cvtColor(img_np, cv2.COLOR_RGBA2RGB)
            
            img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
            img_hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
            
            # === DİNAMİK RENK ALGILAMA ===
            # Siyah olmayan (arka plan) pikselleri say
            # Siyah = H:?, S:?, V:0-50
            # Bar = V:50+ (parlak renk)
            
            lower_black = np.array([0, 0, 0])
            upper_black = np.array([255, 255, 50])  # Siyah (V düşük)
            
            black_mask = cv2.inRange(img_hsv, lower_black, upper_black)
            inverted = cv2.bitwise_not(black_mask)
            
            # === AŞIRı beyazları da hariç tut ===
            lower_white = np.array([0, 0, 200])
            upper_white = np.array([255, 50, 255])
            white_mask = cv2.inRange(img_hsv, lower_white, upper_white)
            
            # Siyah DEĞİL + Beyaz DEĞİL = Bar renginin pikselleri
            bar_mask = cv2.bitwise_and(inverted, cv2.bitwise_not(white_mask))
            
            hp_pixels = cv2.countNonZero(bar_mask)
            total_pixels = img_hsv.size / 3
            
            # DEBUG (basitleştirildi - donma engellendi)
            # print(f"[DEBUG HP] Piksel={hp_pixels}/{total_pixels}")  # Yorum - çok yavaş
            
            return hp_pixels, total_pixels
        except Exception as e:
            print(f"[ERROR] HP pixel count failed: {e}")
            import traceback
            traceback.print_exc()
            return 0, 1
    
    def _update_hp_reference(self, current_count):
        """HP referans değerini güncelle"""
        if self.hp_reference is None:
            self.hp_reference = current_count
            print(f"[HP] Reference set: {self.hp_reference} pixels")
        elif current_count >= self.hp_reference * 0.97:
            # Maks HP'ye yakınsa, reference'ı biraz arttır
            self.hp_reference = 0.90 * self.hp_reference + 0.10 * current_count

    def _fallback_mouse_click(self, click_type, x_int, y_int):
        """SendInput fallback - driver yok veya başarısız oldu"""
        # İmleci konuma taşı
        ctypes.windll.user32.SetCursorPos(x_int, y_int)
        time.sleep(0.05)
        
        # === SendInput ile yapılandırma (en güvenilir yöntem) ===
        PUL = ctypes.POINTER(ctypes.c_ulong)
        class MouseInput(ctypes.Structure):
            _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long), ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong), ("dwExtraInfo", PUL)]
        class Input_I(ctypes.Union):
            _fields_ = [("mi", MouseInput)]
        class Input(ctypes.Structure):
            _fields_ = [("type", ctypes.c_ulong), ("ii", Input_I)]
        
        extra = ctypes.c_ulong(0)
        
        if click_type == "left":
            # Sol tık DOWN
            ii = Input_I()
            ii.mi = MouseInput(0, 0, 0, 0x0002, 0, ctypes.pointer(extra))
            x_input = Input(ctypes.c_ulong(0), ii)
            ctypes.windll.user32.SendInput(1, ctypes.pointer(x_input), ctypes.sizeof(x_input))
            time.sleep(0.05)
            # Sol tık UP
            ii.mi = MouseInput(0, 0, 0, 0x0004, 0, ctypes.pointer(extra))
            x_input = Input(ctypes.c_ulong(0), ii)
            ctypes.windll.user32.SendInput(1, ctypes.pointer(x_input), ctypes.sizeof(x_input))
            
        elif click_type == "right":
            # Sağ tık DOWN
            ii = Input_I()
            ii.mi = MouseInput(0, 0, 0, 0x0008, 0, ctypes.pointer(extra))
            x_input = Input(ctypes.c_ulong(0), ii)
            ctypes.windll.user32.SendInput(1, ctypes.pointer(x_input), ctypes.sizeof(x_input))
            time.sleep(0.05)
            # Sağ tık UP
            ii.mi = MouseInput(0, 0, 0, 0x0010, 0, ctypes.pointer(extra))
            x_input = Input(ctypes.c_ulong(0), ii)
            ctypes.windll.user32.SendInput(1, ctypes.pointer(x_input), ctypes.sizeof(x_input))
            
        elif click_type == "double":
            # Çift tık (Sol DOWN + UP + DOWN + UP)
            ii = Input_I()
            # Birinci DOWN
            ii.mi = MouseInput(0, 0, 0, 0x0002, 0, ctypes.pointer(extra))
            x_input = Input(ctypes.c_ulong(0), ii)
            ctypes.windll.user32.SendInput(1, ctypes.pointer(x_input), ctypes.sizeof(x_input))
            time.sleep(0.05)
            # Birinci UP
            ii.mi = MouseInput(0, 0, 0, 0x0004, 0, ctypes.pointer(extra))
            x_input = Input(ctypes.c_ulong(0), ii)
            ctypes.windll.user32.SendInput(1, ctypes.pointer(x_input), ctypes.sizeof(x_input))
            time.sleep(0.1)
            # İkinci DOWN
            ii.mi = MouseInput(0, 0, 0, 0x0002, 0, ctypes.pointer(extra))
            x_input = Input(ctypes.c_ulong(0), ii)
            ctypes.windll.user32.SendInput(1, ctypes.pointer(x_input), ctypes.sizeof(x_input))
            time.sleep(0.05)
            # İkinci UP
            ii.mi = MouseInput(0, 0, 0, 0x0004, 0, ctypes.pointer(extra))
            x_input = Input(ctypes.c_ulong(0), ii)
            ctypes.windll.user32.SendInput(1, ctypes.pointer(x_input), ctypes.sizeof(x_input))

    def check_hp_damage(self):
        """HP bar'ı kontrol et - Mode: dinamik (azalıyor mu) vs statik (var mı)"""
        if not self.hp_region or not self.last_pixel_pos:
            return True  # HP kontrol yapılamıyorsa, normal devam et
        
        # Performans: Son kontrolden 0.5 saniye geçmemişse atla
        if hasattr(self, '_last_hp_check_time'):
            if time.time() - self._last_hp_check_time < 0.5:
                return True
        
        self._last_hp_check_time = time.time()
        hp_mode = getattr(self, 'hp_mode', 'dynamic')  # Config'ten al
        
        try:
            x, y, w, h = self.hp_region
            with mss.mss() as sct:
                img = np.array(sct.grab({"left": x, "top": y, "width": w, "height": h}))
                hp_count, total = self._count_hp_pixels(img)
                
                # === STATIK MOD: HP bar'ı var mı? ===
                if hp_mode == "static":
                    # Eğer HP pikseli varsa (> 0) mob canlı
                    if hp_count > 0:
                        print(f"[✓ STATIC MODE] HP bar bulundu: {hp_count} pixels - Mob CANLI")
                        return True
                    else:
                        print(f"[✗ STATIC MODE] HP bar bulunamadı - Mob ÖLÜ")
                        return False
                
                # === DİNAMİK MOD: HP azalıyor mu? ===
                else:  # dynamic
                    # İlk kez ise referansı ayarla
                    self._update_hp_reference(hp_count)
                    
                    if self.hp_reference and self.hp_reference > 0:
                        ratio = hp_count / self.hp_reference
                        self.current_hp_ratio = max(0.0, min(1.0, ratio))
                        
                        print(f"[HP CHECK] HP: {hp_count}/{self.hp_reference} pixels ({self.current_hp_ratio*100:.1f}%)")
                        
                        # HP'nin %5'den fazla azaldı mı?
                        if self.current_hp_ratio < 0.95:
                            print(f"[✓ DYNAMIC MODE] Mob hasar alıyor! (HP: {self.current_hp_ratio*100:.1f}%)")
                            return True
                        else:
                            print(f"[✗ DYNAMIC MODE] Mob hasar almıyor! HP değişmemiş!")
                            return False
        except Exception as e:
            print(f"[ERROR] HP check failed: {e}")
            return True  # Error olursa devam et
        
        return True

# =========================================================
# MACRO EDİTÖRÜ (RAZER SYNAPSE TARZI)
# =========================================================
class MacroEditor(QDialog):
    """
    Razer Synapse benzeri macro editörü
    Sol panel: Araçlar
    Sağ panel: Timeline/Akış
    """
    def __init__(self, parent, config):
        super().__init__(parent)
        self.setWindowTitle("🧠 SEGE MACRO STUDIO v1.0")
        self.resize(1200, 800)
        self.config = config
        
        self.setStyleSheet("""
            QDialog {
                background-color: #0a0a0a;
                color: white;
            }
            QLabel {
                color: white;
            }
            QPushButton {
                background-color: #1a1a1a;
                color: white;
                border: 1px solid #333;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #2a2a2a;
            }
            QTreeWidget {
                background-color: #0f0f0f;
                border: 1px solid #333;
                font-size: 10pt;
            }
            QTreeWidget::item {
                padding: 8px;
                border-bottom: 1px solid #1a1a1a;
            }
            QTreeWidget::item:selected {
                background-color: #1e88e5;
            }
        """)
        
        # Overlay kapatma güvenliği
        self.active_overlay = None
        self.temp_data = {}
        
        self.setup_ui()
        self.load_from_config()

    def setup_ui(self):
        """UI kurulumu"""
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Sol Panel (Araçlar)
        left_panel = self.create_left_panel()
        main_layout.addWidget(left_panel)
        
        # Sağ Panel (Timeline)
        right_panel = self.create_right_panel()
        main_layout.addWidget(right_panel)

    def create_left_panel(self):
        """Sol araç paneli"""
        panel = QFrame()
        panel.setFixedWidth(280)
        panel.setStyleSheet("background-color: #111; border-right: 1px solid #333;")
        
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Başlık
        title = QLabel("MAKRO ARAÇLARI")
        title.setStyleSheet("font-size: 14pt; font-weight: bold; color: #00e676; margin-bottom: 10px;")
        layout.addWidget(title)
        
        # GİRDİLER
        layout.addWidget(QLabel("GİRDİLER (KOŞULLAR)", styleSheet="color: #d500f9; font-weight: bold; margin-top: 15px;"))
        self.add_tool_button(layout, "📐 TARAMA ALANI SEÇ", self.cmd_select_area, "#d500f9")
        self.add_tool_button(layout, "❤️ HP BAR ALANI SEÇ", self.cmd_select_hp_region, "#ff5252")
        self.add_tool_button(layout, "🖼️ GÖRSEL EKLE", self.cmd_add_image, "#d500f9")
        
        # EYLEMLER
        layout.addWidget(QLabel("EYLEMLER", styleSheet="color: #00e676; font-weight: bold; margin-top: 20px;"))
        self.add_tool_button(layout, "⌨️ TUŞ BAS", self.cmd_add_key, "#00e676")
        self.add_tool_button(layout, "🖱️ MOUSE TIK", self.cmd_add_mouse, "#00e676")
        self.add_tool_button(layout, "⏱️ GECİKME", self.cmd_add_delay, "#ffa000")
        
        # KONTROL YAPILARI
        layout.addWidget(QLabel("KONTROL", styleSheet="color: #ff9800; font-weight: bold; margin-top: 20px;"))
        self.add_tool_button(layout, "🔁 DÖNGÜ", self.cmd_add_loop, "#ff9800")
        self.add_tool_button(layout, "🎨 PİKSEL KONTROL", self.cmd_add_pixel, "#9c27b0")
        
        layout.addStretch()
        
        # Makro bilgileri
        layout.addWidget(QLabel("MAKRO ADI:", styleSheet="margin-top: 20px;"))
        self.edit_name = QLineEdit(self.config.get("name", "Yeni Makro"))
        layout.addWidget(self.edit_name)
        
        layout.addWidget(QLabel("TETİKLEME TUŞU:"))
        hbox_hotkey = QHBoxLayout()
        self.lbl_hotkey = QLabel(self.config.get("hotkey", "G"))
        self.lbl_hotkey.setStyleSheet("border: 1px solid #444; padding: 8px; color: #00ff4c; font-weight: bold;")
        btn_hotkey = QPushButton("DEĞİŞTİR")
        btn_hotkey.clicked.connect(self.change_hotkey)
        hbox_hotkey.addWidget(self.lbl_hotkey)
        hbox_hotkey.addWidget(btn_hotkey)
        layout.addLayout(hbox_hotkey)
        
        return panel

    def add_tool_button(self, layout, text, func, color):
        """Sol panele araç butonu ekle"""
        btn = QPushButton(text)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                text-align: left;
                padding: 12px;
                border: 1px solid #333;
                border-left: 4px solid {color};
                background: #1a1a1a;
            }}
            QPushButton:hover {{
                background: #252525;
            }}
        """)
        btn.clicked.connect(func)
        layout.addWidget(btn)

    def create_right_panel(self):
        """Sağ timeline paneli"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Header
        header_layout = QHBoxLayout()
        title = QLabel("MAKRO AKIŞI")
        title.setStyleSheet("font-size: 16pt; font-weight: bold;")
        header_layout.addWidget(title)
        header_layout.addStretch()
        
        btn_delete = QPushButton("🗑️ SİL")
        btn_delete.clicked.connect(self.delete_step)
        header_layout.addWidget(btn_delete)
        
        layout.addLayout(header_layout)
        
        # Tree widget (akış)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["İşlem", "Detay"])
        self.tree.setColumnWidth(0, 450)
        self.tree.setDragDropMode(QAbstractItemView.InternalMove)
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        layout.addWidget(self.tree)
        
        # Alt butonlar
        bottom_layout = QHBoxLayout()
        
        btn_edit = QPushButton("✏️ DÜZENLE")
        btn_edit.clicked.connect(self.edit_step)
        bottom_layout.addWidget(btn_edit)
        
        bottom_layout.addStretch()
        
        btn_save = QPushButton("💾 KAYDET VE ÇIK")
        btn_save.setStyleSheet("background: #00e676; color: black; font-weight: bold; font-size: 12pt; padding: 12px;")
        btn_save.clicked.connect(self.save_and_close)
        bottom_layout.addWidget(btn_save)
        
        layout.addLayout(bottom_layout)
        
        return panel

    # ========== KOMUTLAR ==========
    
    def cmd_select_area(self):
        """Tarama alanı seç"""
        self.setWindowOpacity(0)
        QTimer.singleShot(200, self._start_area_selection)
    
    def cmd_select_hp_region(self):
        """HP bar alanı seç"""
        self.setWindowOpacity(0)
        QTimer.singleShot(200, self._start_hp_region_selection)
    
    def _start_hp_region_selection(self, parent_item=None):
        """HP bar region'ı seç ve config'e kaydet"""
        print(f"[DEBUG] _start_hp_region_selection başlama, parent_item={parent_item}")
        try:
            selector = SafeScreenSelector(mode="area", parent=None)
            if selector.exec_():
                rect = selector.result
                print(f"[DEBUG] Selector sonucu: rect={rect}")
                
                if rect is None:
                    print("[UYARI] Rect seçilmedi (None)")
                    self.setWindowOpacity(1)
                    return
                
                region = [rect.x(), rect.y(), rect.width(), rect.height()]
                print(f"[DEBUG] Region ayarlandı: {region}")
                self.config["hp_region"] = region
                
                # HP bar'ın screenshot'ını kaydet
                try:
                    x, y, w, h = region
                    with mss.mss() as sct:
                        hp_screenshot = np.array(sct.grab({"left": x, "top": y, "width": w, "height": h}))
                        import os
                        if not os.path.exists("hp_data"):
                            os.makedirs("hp_data")
                        hp_image_path = f"hp_data/hp_bar_{int(time.time())}.png"
                        cv2.imwrite(hp_image_path, hp_screenshot)
                        self.config["hp_image"] = hp_image_path
                        print(f"[✓] HP bar screenshot kaydedildi: {hp_image_path}")
                except Exception as e:
                    print(f"[UYARI] HP screenshot kaydetme hatası: {e} - Devam ediliyor...")
                    self.config["hp_image"] = None
                
                # === parent_item varsa (TARAMA ALANI altında ekle), yoksa root'a ekle ===
                if parent_item is None:
                    parent = self.tree.invisibleRootItem()
                else:
                    parent = parent_item
                
                # Tree'ye ekle
                hp_item = QTreeWidgetItem(parent)
                hp_item.setText(0, "❤️ HP BAR ALANI")
                hp_item.setText(1, f"[{rect.width()}x{rect.height()}] @({rect.x()}, {rect.y()})")
                hp_item.setData(0, Qt.UserRole, {
                    "type": "hp_region",
                    "region": region,
                    "sub_steps": []
                })
                hp_item.setExpanded(True)
                
                # GÖRSEL VARSA alt öğesi ekle (eğer screenshot varsa)
                if self.config.get("hp_image"):
                    img_item = QTreeWidgetItem(hp_item)
                    img_item.setText(0, "👁️ GÖRSEL VARSA")
                    img_item.setText(1, self.config["hp_image"])
                    img_item.setData(0, Qt.UserRole, {
                        "type": "image",
                        "path": self.config["hp_image"],
                        "sub_steps": []
                    })
                
                # HP kontrol modu seç
                dlg = QDialog(self)
                dlg.setWindowTitle("HP Kontrol Modu")
                dlg.setModal(True)
                dlg.setGeometry(100, 100, 400, 200)
                layout = QVBoxLayout(dlg)
                
                layout.addWidget(QLabel("HP Kontrolü Nasıl Yapılsın?"))
                
                btn_dynamic = QPushButton("🔄 DİNAMİK (HP Azalırsa Atak Et)")
                btn_static = QPushButton("🛑 STATİK (HP Varsa Devam, Yoksa Bitir)")
                btn_test = QPushButton("🧪 TEST ET (Seçilen Alanı Görüntüle)")
                
                mode_result = {"mode": "dynamic"}
                
                def choose_dynamic():
                    mode_result["mode"] = "dynamic"
                    dlg.accept()
                
                def choose_static():
                    mode_result["mode"] = "static"
                    dlg.accept()
                
                def test_hp_region():
                    """Seçilen HP region'ı test et"""
                    self._test_hp_region(region)
                
                btn_dynamic.clicked.connect(choose_dynamic)
                btn_static.clicked.connect(choose_static)
                btn_test.clicked.connect(test_hp_region)
                
                layout.addWidget(btn_dynamic)
                layout.addWidget(btn_static)
                layout.addWidget(btn_test)
                layout.addStretch()
                
                dlg.exec_()
                
                self.config["hp_mode"] = mode_result["mode"]
                
                # Tree'de HP mode'unu güncelle
                hp_item.setText(0, f"❤️ HP BAR ALANI ({mode_result['mode'].upper()})")
                
                # Parent'ı genişlet
                if parent != self.tree.invisibleRootItem():
                    parent.setExpanded(True)
                
                print(f"[✓] HP BAR REGION AYARLANDI: {region}")
                print(f"[✓] HP MODE: {self.config.get('hp_mode', 'dynamic').upper()}")
        except Exception as e:
            print(f"[ERROR] HP Region selection error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.setWindowOpacity(1)
    
    def _test_hp_region(self, region):
        """HP region'ı test et - MacroEngine aracılığıyla"""
        try:
            # Temporary engine oluştur (aynı dosyada tanımlı)
            temp_engine = MacroEngine()
            temp_engine.test_hp_region(region)
        except Exception as e:
            print(f"[ERROR] HP test error: {e}")
            import traceback
            traceback.print_exc()

    def _start_area_selection(self):
        try:
            selector = SafeScreenSelector(mode="area", parent=None)
            if selector.exec_():
                rect = selector.result
                if rect:
                    region = [rect.x(), rect.y(), rect.width(), rect.height()]
                    self.temp_data["last_region"] = region
                    
                    # Seçili item varsa onun altına, yoksa root'a ekle
                    parent = self.tree.currentItem()
                    if not parent:
                        parent = self.tree.invisibleRootItem()
                    
                    item = QTreeWidgetItem(parent)
                    item.setText(0, "📐 TARAMA ALANI")
                    item.setText(1, f"[{rect.width()}x{rect.height()}] @({rect.x()}, {rect.y()})")
                    item.setData(0, Qt.UserRole, {
                        "type": "scan_region",
                        "region": region,
                        "sub_steps": []
                    })
                    item.setExpanded(True)
                    
                    # Seçili item'ı genişlet
                    if parent != self.tree.invisibleRootItem():
                        parent.setExpanded(True)
                    
                    # === TARAMA ALANI seçildikten sonra HP bar sorusu ===
                    try:
                        dlg = QDialog(self)
                        dlg.setWindowTitle("HP Bar Alanı")
                        dlg.setModal(True)
                        dlg.setGeometry(100, 100, 400, 150)
                        layout = QVBoxLayout(dlg)
                        
                        layout.addWidget(QLabel("Bu tarama alanında HP bar'ı da seçmek ister misin?"))
                        
                        btn_yes = QPushButton("✅ EVET, HP BAR SEÇ")
                        btn_no = QPushButton("❌ HAYIR, DEVAM ET")
                        
                        def select_hp():
                            try:
                                dlg.accept()
                                # HP region seçimini başlat
                                self.setWindowOpacity(0)
                                QTimer.singleShot(200, lambda: self._start_hp_region_selection(parent_item=item))
                            except Exception as e:
                                print(f"[ERROR] select_hp callback: {e}")
                                import traceback
                                traceback.print_exc()
                        
                        def skip_hp():
                            try:
                                dlg.accept()
                            except Exception as e:
                                print(f"[ERROR] skip_hp callback: {e}")
                        
                        btn_yes.clicked.connect(select_hp)
                        btn_no.clicked.connect(skip_hp)
                        
                        layout.addWidget(btn_yes)
                        layout.addWidget(btn_no)
                        layout.addStretch()
                        
                        dlg.exec_()
                    except Exception as e:
                        print(f"[ERROR] HP bar dialog creation: {e}")
                        import traceback
                        traceback.print_exc()
        except Exception as e:
            print(f"[ERROR] _start_area_selection: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.setWindowOpacity(1)

    def cmd_add_image(self):
        """Görsel koşulu ekle"""
        # Seçili item'dan region bul (varsa)
        current = self.tree.currentItem()
        region = None
        
        # Üst parent'larda scan_region ara
        temp = current
        while temp and not region:
            data = temp.data(0, Qt.UserRole)
            if data and data.get("type") == "scan_region":
                region = data.get("region")
                break
            temp = temp.parent()
        
        # Region yoksa kullanıcıya sor
        if not region:
            reply = QMessageBox.question(
                self,
                "Tarama Alanı",
                "Tarama alanı belirtilmemiş. Tam ekran tarama yapılsın mı?\n\n(EVET = Tam ekran)\n(HAYIR = İptal)",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.No:
                return
        
        # Görsel kes
        self.setWindowOpacity(0)
        QTimer.singleShot(200, lambda: self._capture_image(region, current))

    def _capture_image(self, region, parent_item):
        """Ekrandan görsel kes ve kaydet"""
        selector = SafeScreenSelector(mode="area", parent=None)
        if selector.exec_():
            rect = selector.result
            if rect:
                # Görseli kaydet
                with mss.mss() as sct:
                    mon = {
                        "left": rect.x(),
                        "top": rect.y(),
                        "width": rect.width(),
                        "height": rect.height()
                    }
                    screenshot = np.array(sct.grab(mon))
                    
                    # Dosya yolu
                    if not os.path.exists("custom_macros_data"):
                        os.makedirs("custom_macros_data")
                    
                    image_path = f"custom_macros_data/img_{int(time.time())}.png"
                    cv2.imwrite(image_path, cv2.cvtColor(screenshot, cv2.COLOR_BGRA2GRAY))
                
                # Koşul tipi sor
                reply = QMessageBox.question(
                    self, 
                    "Koşul Tipi", 
                    "Bu görsel EKRANDA OLMAYINCA mı işlem yapılsın?\n\n(EVET = Görsel yoksa çalış)\n(HAYIR = Görsel varsa çalış)",
                    QMessageBox.Yes | QMessageBox.No
                )
                trigger_on_missing = (reply == QMessageBox.Yes)
                
                # Parent yoksa root'a ekle
                if not parent_item:
                    parent_item = self.tree.invisibleRootItem()
                
                # Tree'ye ekle
                text = "🔍 GÖRSEL YOKSA" if trigger_on_missing else "🔍 GÖRSEL VARSA"
                item = QTreeWidgetItem(parent_item)
                item.setText(0, text)
                item.setText(1, os.path.basename(image_path))
                item.setData(0, Qt.UserRole, {
                    "type": "image_check",
                    "image_path": image_path,
                    "region": region,
                    "threshold": 0.75,
                    "trigger_on_missing": trigger_on_missing,
                    "check_count": 5,  # 5 kez kontrol et
                    "check_delay": 0.15,  # Her kontrol arası 0.15sn bekle
                    "sub_steps": []
                })
                item.setExpanded(True)
                
                # Parent'ı genişlet
                if parent_item != self.tree.invisibleRootItem():
                    parent_item.setExpanded(True)
        
        self.setWindowOpacity(1)

    def cmd_add_key(self):
        """Tuş eylemi ekle"""
        dlg = KeyActionDialog(self)
        if dlg.exec_():
            data = dlg.get_data()
            
            # Seçili item varsa onun altına, yoksa root'a ekle
            parent = self.tree.currentItem()
            if not parent:
                parent = self.tree.invisibleRootItem()
            
            item = QTreeWidgetItem(parent)
            item.setText(0, "⌨️ TUŞ BAS")
            item.setText(1, f"{data['key']} ({data['duration']}sn)")
            item.setData(0, Qt.UserRole, data)
            
            # Seçili item'ı genişlet
            if parent != self.tree.invisibleRootItem():
                parent.setExpanded(True)

    def cmd_add_mouse(self):
        """Mouse eylemi ekle"""
        dlg = MouseActionDialog(self)
        if dlg.exec_():
            data = dlg.get_data()
            
            # Seçili item varsa onun altına, yoksa root'a ekle
            parent = self.tree.currentItem()
            if not parent:
                parent = self.tree.invisibleRootItem()
            
            # Açıklama
            if data['mode'] == 'fixed':
                detail = f"{data['click_type'].upper()} @ ({data['x']}, {data['y']})"
            elif data['mode'] == 'image':
                detail = f"{data['click_type'].upper()} (Görsel Üzerine)"
            elif data['mode'] == 'pixel':
                detail = f"{data['click_type'].upper()} (Pixel Bulunduğu Yerde)"
            else:
                detail = f"{data['click_type'].upper()} (Mevcut Konum)"
            
            item = QTreeWidgetItem(parent)
            item.setText(0, "🖱️ MOUSE TIK")
            item.setText(1, detail)
            item.setData(0, Qt.UserRole, data)
            
            # Seçili item'ı genişlet
            if parent != self.tree.invisibleRootItem():
                parent.setExpanded(True)

    def cmd_add_delay(self):
        """Gecikme ekle"""
        dlg = DelayDialog(self)
        if dlg.exec_():
            value = dlg.get_value()
            
            # Seçili item varsa onun altına, yoksa root'a ekle
            parent = self.tree.currentItem()
            if not parent:
                parent = self.tree.invisibleRootItem()
            
            item = QTreeWidgetItem(parent)
            item.setText(0, "⏱️ GECİKME")
            item.setText(1, f"{value} saniye")
            item.setData(0, Qt.UserRole, {
                "type": "delay",
                "value": value
            })
            
            # Seçili item'ı genişlet
            if parent != self.tree.invisibleRootItem():
                parent.setExpanded(True)

    def cmd_add_loop(self):
        """Döngü ekle"""
        dlg = LoopDialog(self)
        if dlg.exec_():
            count = dlg.get_count()
            
            # Seçili item varsa onun altına, yoksa root'a ekle
            parent = self.tree.currentItem()
            if not parent:
                parent = self.tree.invisibleRootItem()
            
            item = QTreeWidgetItem(parent)
            item.setText(0, "🔁 DÖNGÜ")
            item.setText(1, f"{count}x tekrar")
            item.setData(0, Qt.UserRole, {
                "type": "loop",
                "count": count,
                "sub_steps": []
            })
            item.setExpanded(True)
            
            # Seçili item'ı genişlet
            if parent != self.tree.invisibleRootItem():
                parent.setExpanded(True)
    
    def cmd_add_pixel(self):
        """Pixel kontrolü ekle"""
        dlg = PixelDialog(self)
        if dlg.exec_():
            data = dlg.get_data()
            if not data:
                QMessageBox.warning(self, "Hata", "Lütfen renk seçin!")
                return
            
            # Seçili item varsa onun altına, yoksa root'a ekle
            parent = self.tree.currentItem()
            if not parent:
                parent = self.tree.invisibleRootItem()
            
            r, g, b = data["rgb"]
            text = "🎨 PİKSEL YOKSA" if data["trigger_on_missing"] else "🎨 PİKSEL VARSA"
            
            item = QTreeWidgetItem(parent)
            item.setText(0, text)
            item.setText(1, f"RGB({r},{g},{b})")
            item.setData(0, Qt.UserRole, data)
            item.setExpanded(True)
            
            # Seçili item'ı genişlet
            if parent != self.tree.invisibleRootItem():
                parent.setExpanded(True)

    def delete_step(self):
        """Seçili adımı sil"""
        current = self.tree.currentItem()
        if current:
            parent = current.parent() or self.tree.invisibleRootItem()
            parent.removeChild(current)

    def edit_step(self):
        """Adımı düzenle"""
        current = self.tree.currentItem()
        if not current:
            return
        
        data = current.data(0, Qt.UserRole)
        step_type = data.get("type")
        
        if step_type == "key":
            dlg = KeyActionDialog(self, data)
            if dlg.exec_():
                new_data = dlg.get_data()
                current.setText(1, f"{new_data['key']} ({new_data['duration']}sn)")
                current.setData(0, Qt.UserRole, new_data)
        
        elif step_type == "mouse":
            dlg = MouseActionDialog(self, data)
            if dlg.exec_():
                new_data = dlg.get_data()
                if new_data['mode'] == 'fixed':
                    detail = f"{new_data['click_type'].upper()} @ ({new_data['x']}, {new_data['y']})"
                elif new_data['mode'] == 'image':
                    detail = f"{new_data['click_type'].upper()} (Görsel Üzerine)"
                elif new_data['mode'] == 'pixel':
                    detail = f"{new_data['click_type'].upper()} (Pixel Bulunduğu Yerde)"
                else:
                    detail = f"{new_data['click_type'].upper()} (Mevcut Konum)"
                current.setText(1, detail)
                current.setData(0, Qt.UserRole, new_data)
        
        elif step_type == "delay":
            dlg = DelayDialog(self, data.get("value", 0.5))
            if dlg.exec_():
                value = dlg.get_value()
                current.setText(1, f"{value} saniye")
                current.setData(0, Qt.UserRole, {"type": "delay", "value": value})
        
        elif step_type == "pixel_check":
            dlg = PixelDialog(self, data)
            if dlg.exec_():
                new_data = dlg.get_data()
                if new_data:
                    r, g, b = new_data["rgb"]
                    text = "🎨 PİKSEL YOKSA" if new_data["trigger_on_missing"] else "🎨 PİKSEL VARSA"
                    current.setText(0, text)
                    current.setText(1, f"RGB({r},{g},{b})")
                    current.setData(0, Qt.UserRole, new_data)
        
        elif step_type == "hp_region":
            # HP region'ı tekrar seçebilme
            self.setWindowOpacity(0)
            QTimer.singleShot(200, lambda: self._edit_hp_region(current))

    def _edit_hp_region(self, item):
        """HP region'ı düzenle - yeni alan seç"""
        try:
            selector = SafeScreenSelector(mode="area", parent=None)
            if selector.exec_():
                rect = selector.result
                if rect:
                    region = [rect.x(), rect.y(), rect.width(), rect.height()]
                    self.config["hp_region"] = region
                    
                    # HP bar'ın yeni screenshot'ını kaydet
                    hp_image_path = None
                    try:
                        x, y, w, h = region
                        with mss.mss() as sct:
                            hp_screenshot = np.array(sct.grab({"left": x, "top": y, "width": w, "height": h}))
                            import os
                            if not os.path.exists("hp_data"):
                                os.makedirs("hp_data")
                            hp_image_path = f"hp_data/hp_bar_{int(time.time())}.png"
                            cv2.imwrite(hp_image_path, hp_screenshot)
                            self.config["hp_image"] = hp_image_path
                            print(f"[✓] HP bar screenshot güncellendi: {hp_image_path}")
                    except Exception as e:
                        print(f"[UYARI] HP screenshot güncelleme hatası: {e}")
                        hp_image_path = None
                    
                    # Tree update
                    item.setText(0, f"❤️ HP BAR ALANI ({self.config.get('hp_mode', 'DYNAMIC').upper()})")
                    item.setText(1, f"[{rect.width()}x{rect.height()}] @({rect.x()}, {rect.y()})")
                    item.setData(0, Qt.UserRole, {
                        "type": "hp_region",
                        "region": region,
                        "sub_steps": item.data(0, Qt.UserRole).get("sub_steps", [])
                    })
                    
                    # GÖRSEL VARSA çocuğunu güncelle veya oluştur
                    img_item = None
                    for i in range(item.childCount()):
                        child = item.child(i)
                        if child.data(0, Qt.UserRole).get("type") == "image":
                            img_item = child
                            break
                    
                    if hp_image_path:
                        if img_item is None:
                            img_item = QTreeWidgetItem(item)
                        img_item.setText(0, "👁️ GÖRSEL VARSA")
                        img_item.setText(1, hp_image_path)
                        img_item.setData(0, Qt.UserRole, {
                            "type": "image",
                            "path": hp_image_path,
                            "sub_steps": []
                        })
                    elif img_item:
                        # Screenshot başarısız oldu, GÖRSEL VARSA'yı sil
                        index = item.indexOfChild(img_item)
                        item.removeChild(img_item)
                    
                    print(f"[✓] HP BAR REGION GÜNCELLENDİ: {region}")
        except Exception as e:
            print(f"[ERROR] HP Region edit error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.setWindowOpacity(1)
    
    def change_hotkey(self):
        """Tuş değiştir"""
        self.lbl_hotkey.setText("BASIN...")
        self.grabKeyboard()
    
    def keyPressEvent(self, e):
        """Tuş yakalama"""
        if self.lbl_hotkey.text() == "BASIN...":
            key_text = e.text().upper()
            if not key_text:
                # F tuşları için
                key = e.key()
                if Qt.Key_F1 <= key <= Qt.Key_F12:
                    key_text = f"F{key - Qt.Key_F1 + 1}"
            
            if key_text:
                self.lbl_hotkey.setText(key_text)
            self.releaseKeyboard()
        elif e.key() == Qt.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(e)
        """Tuş değiştir"""
        self.lbl_hotkey.setText("BASIN...")
        self.grabKeyboard()

    def keyPressEvent(self, e):
        """Tuş yakalama"""
        if self.lbl_hotkey.text() == "BASIN...":
            key_text = e.text().upper()
            if not key_text:
                # F tuşları için
                key = e.key()
                if Qt.Key_F1 <= key <= Qt.Key_F12:
                    key_text = f"F{key - Qt.Key_F1 + 1}"
            
            if key_text:
                self.lbl_hotkey.setText(key_text)
            self.releaseKeyboard()
        elif e.key() == Qt.Key_Escape:
            # ESC tuşunu engelle - editör kapanmasın
            # Kullanıcı "X" butonuna veya Cancel'a bassın
            print("[DEBUG] ESC tuşu engellendi - editör açık kaldı")
            return  # super() çağırma!
        else:
            super().keyPressEvent(e)

    def save_and_close(self):
        """Kaydet ve kapat - donma koruması ile"""
        import time
        start_time = time.time()
        timeout = 5  # 5 saniye timeout
        
        try:
            print(f"[SAVE] Başlama zamanı: {start_time}")
            
            # Tree'yi parse et
            def parse_item(item):
                try:
                    data = item.data(0, Qt.UserRole)
                    if not data or not isinstance(data, dict):
                        return None
                    result = dict(data)
                    children = []
                    for i in range(item.childCount()):
                        child = parse_item(item.child(i))
                        if child:
                            children.append(child)
                    result["sub_steps"] = children
                    return result
                except:
                    return None
            
            steps = []
            for i in range(self.tree.topLevelItemCount()):
                step = parse_item(self.tree.topLevelItem(i))
                if step:
                    steps.append(step)
            
            self.config["name"] = self.edit_name.text()
            self.config["hotkey"] = self.lbl_hotkey.text()
            self.config["steps"] = steps
            
            # HP region ve HP mode zaten config'te
            print(f"[✓] Config saved (HIZLI)!")
            print(f"    - Hotkey: {self.config.get('hotkey')}")
            print(f"    - HP Region: {self.config.get('hp_region')}")
            print(f"    - HP Mode: {self.config.get('hp_mode')}")
            print(f"    - Steps: {len(self.config.get('steps', []))}")
            
            elapsed = time.time() - start_time
            print(f"[SAVE] Tamamlandı: {elapsed:.3f}s")
            
            if elapsed > timeout:
                print(f"[UYARI] Timeout geçildi! {elapsed}s")
            
            self.accept()
        except Exception as e:
            print(f"[ERROR] Save error: {e}")
            import traceback
            traceback.print_exc()
            self.accept()  # Hata olsa da kapat!

    def load_from_config(self):
        """Config'den yükle"""
        def build_tree(steps, parent):
            for step in steps:
                item = QTreeWidgetItem(parent)
                
                # Tip'e göre görsel
                step_type = step.get("type")
                if step_type == "key":
                    item.setText(0, "⌨️ TUŞ BAS")
                    item.setText(1, f"{step['key']} ({step['duration']}sn)")
                
                elif step_type == "mouse":
                    item.setText(0, "🖱️ MOUSE TIK")
                    if step['mode'] == 'fixed':
                        detail = f"{step['click_type'].upper()} @ ({step['x']}, {step['y']})"
                    elif step['mode'] == 'image':
                        detail = f"{step['click_type'].upper()} (Görsel Üzerine)"
                    elif step['mode'] == 'pixel':
                        detail = f"{step['click_type'].upper()} (Pixel Bulunduğu Yerde)"
                    else:
                        detail = f"{step['click_type'].upper()} (Mevcut Konum)"
                    item.setText(1, detail)
                
                elif step_type == "delay":
                    item.setText(0, "⏱️ GECİKME")
                    item.setText(1, f"{step['value']} saniye")
                
                elif step_type == "image_check":
                    text = "🔍 GÖRSEL YOKSA" if step.get("trigger_on_missing") else "🔍 GÖRSEL VARSA"
                    item.setText(0, text)
                    item.setText(1, os.path.basename(step.get("image_path", "")))
                
                elif step_type == "scan_region":
                    item.setText(0, "📐 TARAMA ALANI")
                    reg = step.get("region", [0, 0, 0, 0])
                    item.setText(1, f"[{reg[2]}x{reg[3]}] @({reg[0]}, {reg[1]})")
                
                elif step_type == "loop":
                    item.setText(0, "🔁 DÖNGÜ")
                    item.setText(1, f"{step.get('count', 1)}x tekrar")
                
                elif step_type == "pixel_check":
                    text = "🎨 PİKSEL YOKSA" if step.get("trigger_on_missing") else "🎨 PİKSEL VARSA"
                    item.setText(0, text)
                    rgb = step.get("rgb", [255, 255, 255])
                    item.setText(1, f"RGB({rgb[0]},{rgb[1]},{rgb[2]})")
                
                elif step_type == "hp_region":
                    # HP BAR ALANI
                    hp_mode = step.get("hp_mode", "dynamic").upper()
                    item.setText(0, f"❤️ HP BAR ALANI ({hp_mode})")
                    reg = step.get("region", [0, 0, 0, 0])
                    item.setText(1, f"[{reg[2]}x{reg[3]}] @({reg[0]}, {reg[1]})")
                
                elif step_type == "image":
                    # GÖRSEL VARSA (HP bar'ın görseli)
                    item.setText(0, "👁️ GÖRSEL VARSA")
                    item.setText(1, step.get("path", ""))
                    # NOT: Alt adımlar (GÖRSEL VARSA) otomatik yüklenecek (build_tree tarafından)
                
                item.setData(0, Qt.UserRole, step)
                item.setExpanded(True)
                
                # Alt adımlar
                if "sub_steps" in step:
                    build_tree(step["sub_steps"], item)
        
        # Sadece steps'i yükle (HP region config'ten bağımsız)
        build_tree(self.config.get("steps", []), self.tree.invisibleRootItem())

# =========================================================
# WİDGET (ANA PROGRAM İÇİN)
# =========================================================
class MacronuKendinYapWidget(QFrame):
    """
    Ana program içinde kullanılacak widget
    self_macro.py stilinde standardize edilmiş
    """
    update_signal = pyqtSignal()
    
    def __init__(self, parent=None, macro_instance=None, config=None):
        super().__init__(parent)
        
        self.macro = macro_instance or MacroEngine()
        self.config = config or {
            "name": "ÖZEL MAKRO PANELİ",
            "hotkey": "G",
            "steps": []
        }
        self.macro.update_config(self.config)
        
        self.listening = False
        self.hook = None
        
        self.update_signal.connect(self._safe_update_status)
        self.setup_ui()
        self._safe_update_status()

    def setup_ui(self):
        """Widget UI - Standardize edilmiş stil"""
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

        # --- HEADER (Standart Stil) ---
        h = QHBoxLayout()
        h.setSpacing(6)
        
        # İkon
        icon = QLabel()
        icon.setText("🚀")
        icon.setStyleSheet("font-size: 25px;")
        h.addWidget(icon)

        # Başlık
        lbl_title = QLabel("V5 MACRO EDITOR") 
        lbl_title.setObjectName("MinorHeaderLabel")
        lbl_title.setStyleSheet("color: white; font-weight: bold;")
        h.addStretch(1)
        h.addWidget(lbl_title)
        
        v.addLayout(h)

        # --- BUTON (Standart Stil) ---
        self.btn_listen = QPushButton("TUŞ DİNLEMEYİ BAŞLAT")
        self.btn_listen.setObjectName("ThreeFiveListenButton")
        self.btn_listen.setProperty("active", False)
        self.btn_listen.clicked.connect(self.toggle_listening)
        v.addWidget(self.btn_listen)

        # --- DURUM ---
        self.lbl_status = QLabel("DURUM: PASİF")
        self.lbl_status.setObjectName("MinorStatusLabel")
        v.addWidget(self.lbl_status)

        # --- ALT KISIM ---
        row = QHBoxLayout()
        row.setSpacing(4)
        row.addWidget(QLabel("AKTİF TUŞ:"))
        
        self.lbl_key = QLabel(self.config.get("hotkey", "G"))
        self.lbl_key.setObjectName("HotkeyLabel")
        self.lbl_key.setStyleSheet("border: 1px solid #444; padding: 4px; color: #00ff4c; font-weight: bold;")
        self.lbl_key.setAlignment(Qt.AlignCenter)
        row.addWidget(self.lbl_key)
        
        btn_set = QPushButton("⚙ EDİTÖR")
        btn_set.setObjectName("MinorSettingsButton")
        btn_set.setFlat(True)
        btn_set.clicked.connect(self.open_editor)
        row.addWidget(btn_set)
        
        v.addLayout(row)

    def open_editor(self):
        """Editörü aç"""
        editor = MacroEditor(self, self.config)
        if editor.exec_():
            # Config güncellendi
            self.macro.update_config(self.config)
            self.lbl_key.setText(self.config["hotkey"])
            
            if self.listening: 
                self.toggle_listening()  # Kapat
                self.toggle_listening()  # Aç

    def toggle_listening(self):
        """Dinlemeyi aç/kapat"""
        if self.listening:
            # Kapat
            if self.hook and KEYBOARD_LIB:
                try:
                    keyboard.unhook(self.hook)
                except:
                    pass
            self.listening = False
            self.macro.stop()
        else:
            # Aç
            if not KEYBOARD_LIB:
                QMessageBox.warning(self, "Hata", "keyboard kütüphanesi yüklenmemiş!")
                return
            
            try:
                hotkey = self.config.get("hotkey", "G").lower()
                
                def on_hotkey_pressed(e):
                    """Hotkey basıldığında macro başlat/durdur"""
                    if not self.macro.is_running():
                        self.macro.start()
                    else:
                        self.macro.stop()
                    # UI güncelleme sinyali gönder
                    self.update_signal.emit()
                
                self.hook = keyboard.on_press_key(hotkey, on_hotkey_pressed)
                self.listening = True
            except Exception as e:
                QMessageBox.critical(self, "Hata", f"Tuş dinleme başlatılamadı: {e}")
        
        self._safe_update_status()

    def apply_status_style(self, color: str = "#8d95c7"):
        """Durum label rengini ayarla"""
        self.lbl_status.setStyleSheet(f"color: {color}; font-weight: bold;")

    def _safe_update_status(self):
        """Durumu güvenli şekilde güncelle"""
        if not self.listening:
            self.lbl_status.setText("DURUM: PASİF")
            self.apply_status_style("#ff5555")  # KIRMIZI
            self.btn_listen.setText("TUŞ DİNLEMEYİ BAŞLAT")
            is_active = False
        else:
            if self.macro.is_running():
                self.lbl_status.setText("DURUM: ÇALIŞIYOR")
                self.apply_status_style("#00ff4c")  # YEŞİL
            else:
                self.lbl_status.setText("DURUM: BEKLİYOR")
                self.apply_status_style("#ffff55")  # SARI
            
            self.btn_listen.setText("TUŞ DİNLEMEYİ DURDUR")
            is_active = True
        
        # Buton stilini güncelle
        self.btn_listen.setProperty("active", is_active)
        self.btn_listen.style().unpolish(self.btn_listen)
        self.btn_listen.style().polish(self.btn_listen)
        
        # Döngüsel kontrol
        if self.listening:
            QTimer.singleShot(500, self._safe_update_status)
    
    def closeEvent(self, event):
        """Program kapatılırken cleanup"""
        try:
            if self.macro and self.macro.is_running():
                self.macro.stop()
            if hasattr(self, 'hook') and self.listening and KEYBOARD_LIB:
                keyboard.unhook(self.hook)
        except:
            pass
        event.accept()

# =========================================================
# TEST KODU
# =========================================================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Test config
    test_config = {
        "name": "TEST MAKRO",
        "hotkey": "G",
        "steps": []
    }
    
    # Widget test
    widget = MacronuKendinYapWidget(config=test_config)
    widget.show()
    
    sys.exit(app.exec_())
