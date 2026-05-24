# -*- coding: utf-8 -*-
# --- hud.py ---

import os
import re

from PyQt5.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QDialog, QCheckBox, 
    QDialogButtonBox, QApplication, QGroupBox, QGridLayout, 
    QWidget, QScrollArea, QPushButton, QSizePolicy
)
from PyQt5.QtCore import Qt, QRect, QTimer, QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt5.QtGui import QColor, QPainter, QBrush, QPen, QFont, QLinearGradient, QPixmap

# ==============================================================================
# ICON MAPPING - Makro key'lerine göre icon dosyaları
# Her modülün widget'ındaki icon_paths'ten alındı
# ==============================================================================
MACRO_ICONS = {
    # ===== WARRIOR =====
    "wari_seriskill": "icons/wari/83.png",
    "wari_des": "icons/wari/yv1.png",
    "wari_kafa": "icons/wari/kafa.png",
    "wari_kalkan": "icons/wari/kalkan1.png",
    "wari_silme": "icons/wari/kilic.png",
    "firfir": "icons/firfir.png",
    "crazydes": "icons/wari/des.png",
    
    # ===== ASAS =====
    "asas": "icons/spike.png",
    "styx": "icons/styx.png",
    "otobicak": "icons/bicak62.png",
    
    # ===== OKÇU =====
    "threefive": "icons/ok5li.png",
    "ok72": "icons/ok72.png",
    "icelr": "icons/iceshoot.png",
    
    # ===== PRIEST =====
    "hpmp": "icons/hp.png",
    "priestattack": "icons/priest/pri62.png",
    "priestpartyheal": "icons/priest/party10k.png",
    "priestgoatmod": "icons/priest/pri72.png",
    "restore": "icons/restore.png",
    "otocure": "icons/cure.png",
    "smarthpmppriest": "icons/priest/hp.png",
    "pri_kalkan": "icons/wari/kalkan1.png",
    
    # ===== MAGE =====
    "icelr": "icons/iceshoot.png",
    "magestaff": "icons/mage/staff.png",
    "magetexttp": "icons/mage/tp.png",
    "patlama": "icons/patlama80.png",
    "m20": "icons/m20.png",
    
    # ===== KURIAN =====
    "kurianseriskill": "icons/kurian/kuri63a.png",
    
    # ===== POT / SELF / MINOR =====
    "minor": "icons/minor.png",
    "self_macro": "icons/self.png",
    "oto_explore": "icons/lightfeet.png",
    "otodef": "icons/def800.png",
    "otodurat": "icons/durat.png",
    "otorpr": "icons/hammer.png",
    
    # ===== GENEL / BOT =====
    "antiafk": "icons/gui/antiafk.png",
    "farm": "icons/gui/farm.png",
    "pet": "icons/pet.png",
    "multi": "icons/gui/multi.png",
    "background_bot": "icons/gui/background.png",
    "upgrade_bot": "icons/gui/upgrade.png",
    "narki": "icons/gui/narki.png",
    "notification": "icons/gui/notification.png",
    "flood_plus": "icons/gui/chat.png",
    "usko_otologin": "icons/gui/login.png",
    "ototiklama": "icons/tik.png",
    "otokontrol": "icons/tiklama/obj_1.png",
    
    # ===== TRADE =====
    "itemchange": "icons/item_raptor.png",
    "birli": "icons/birli.png",
    "clan_storage": "icons/clan.png",
    "vip_storage": "icons/vip.png",
    "loot_macro": "icons/loot.png",
    
    # ===== CUSTOM / KENDİN YAP =====
    "macro_tasarimci": "icons/v5.png",
    "self_macro_1": "icons/self.png",
    "self_macro_2": "icons/self.png",
    "self_macro_3": "icons/self.png",
}

# ==============================================================================
# MODERN HUD OVERLAY
# ==============================================================================
class HUDOverlay(QFrame):
    def __init__(self, parent=None):
        # Parent'ı None yap ki bağımsız pencere olsun
        super().__init__(None)
        
        # FIX #33: PyQt6 namespace yerine PyQt5 düz namespace
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool |
            Qt.X11BypassWindowManagerHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        
        self.setGeometry(50, 50, 240, 180)
        self.setMouseTracking(True)
        self.setMinimumWidth(220)

        # Ana layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(12, 10, 12, 10)
        self.main_layout.setSpacing(0)
        
        # Header
        self._create_header()
        
        # Makro listesi container
        self.macro_container = QWidget()
        self.macro_layout = QVBoxLayout(self.macro_container)
        self.macro_layout.setContentsMargins(0, 8, 0, 4)
        self.macro_layout.setSpacing(3)
        self.main_layout.addWidget(self.macro_container)
        
        # Footer (ping vs.)
        self._create_footer()
        
        # Sürükleme için
        self.start_pos = None
        self.dragging = False
        
        # Kompakt mod (sadece aktifler)
        self.compact_mode = False
        
        # İlk güncelleme
        self.update_hud_data(None)

    def _create_header(self):
        """Başlık satırı"""
        header = QWidget()
        header.setFixedHeight(24)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.setSpacing(6)
        
        # Logo/İkon
        icon_lbl = QLabel("◉")
        icon_lbl.setStyleSheet("color: #00e676; font-size: 12px; border: none;")
        h_layout.addWidget(icon_lbl)
        
        # Başlık
        title = QLabel("MAKRO DURUMU")
        title.setStyleSheet("""
            color: #ffffff; 
            font-size: 10px; 
            font-weight: bold; 
            letter-spacing: 1px;
            border: none;
        """)
        h_layout.addWidget(title)
        h_layout.addStretch()
        
        # Kompakt mod butonu
        self.btn_compact = QPushButton("◫")
        self.btn_compact.setFixedSize(18, 18)
        self.btn_compact.setCursor(Qt.PointingHandCursor)
        self.btn_compact.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #666;
                border: none;
                font-size: 10px;
            }
            QPushButton:hover {
                color: #00e676;
            }
        """)
        self.btn_compact.setToolTip("Kompakt Mod (Sadece Aktifler)")
        self.btn_compact.clicked.connect(self.toggle_compact_mode)
        h_layout.addWidget(self.btn_compact)
        
        self.main_layout.addWidget(header)
        
        # Ayırıcı çizgi
        separator = QFrame()
        separator.setFixedHeight(1)
        separator.setStyleSheet("background-color: rgba(255,255,255,0.1); border: none;")
        self.main_layout.addWidget(separator)

    def _create_footer(self):
        """Alt bilgi satırı"""
        separator = QFrame()
        separator.setFixedHeight(1)
        separator.setStyleSheet("background-color: rgba(255,255,255,0.1); border: none;")
        self.main_layout.addWidget(separator)
        
        footer = QWidget()
        footer.setFixedHeight(22)
        f_layout = QHBoxLayout(footer)
        f_layout.setContentsMargins(0, 4, 0, 0)
        f_layout.setSpacing(8)
        
        # Aktif sayısı
        self.lbl_active_count = QLabel("0 AKTİF")
        self.lbl_active_count.setStyleSheet("""
            color: #888; 
            font-size: 9px; 
            border: none;
        """)
        f_layout.addWidget(self.lbl_active_count)
        
        f_layout.addStretch()
        
        # Ping
        self.lbl_ping_hud = QLabel("--ms")
        self.lbl_ping_hud.setStyleSheet("""
            color: #888; 
            font-size: 9px;
            border: none;
        """)
        f_layout.addWidget(self.lbl_ping_hud)
        
        self.main_layout.addWidget(footer)

    def toggle_compact_mode(self):
        """Kompakt mod aç/kapa"""
        self.compact_mode = not self.compact_mode
        if self.compact_mode:
            self.btn_compact.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    color: #00e676;
                    border: none;
                    font-size: 10px;
                }
            """)
        else:
            self.btn_compact.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    color: #666;
                    border: none;
                    font-size: 10px;
                }
                QPushButton:hover {
                    color: #00e676;
                }
            """)
        # Yeniden çiz - main_window referansını sakla
        if hasattr(self, '_last_main_window'):
            self.update_hud_data(self._last_main_window)

    def paintEvent(self, event):
        """Arka plan çizimi - gradient efektli"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Gradient arka plan
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0, QColor(20, 20, 25, 240))
        gradient.setColorAt(1, QColor(15, 15, 18, 245))
        
        painter.setBrush(QBrush(gradient))
        painter.setPen(QPen(QColor(60, 60, 70), 1))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 10, 10)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.start_pos = event.globalPos() - self.pos()
            event.accept()

    def mouseMoveEvent(self, event):
        if self.dragging:
            self.move(event.globalPos() - self.start_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self.dragging = False

    def update_hud_data(self, main_window):
        """HUD verilerini güncelle"""
        # Eski widget'ları temizle
        for i in reversed(range(self.macro_layout.count())): 
            widget = self.macro_layout.itemAt(i).widget()
            if widget: 
                widget.deleteLater()
        
        if not main_window:
            lbl = QLabel("Bekleniyor...")
            lbl.setStyleSheet("color: #666; font-size: 9px; border: none; padding: 8px 0;")
            lbl.setAlignment(Qt.AlignCenter)
            self.macro_layout.addWidget(lbl)
            self.adjustSize()
            return
        
        # main_window referansını sakla (compact mode için)
        self._last_main_window = main_window
        
        visible_macros = main_window.hud_settings_config.get("visible_macros", [])
        active_count = 0
        
        for macro_key in visible_macros:
            display_name = main_window.MACRO_MAP.get(macro_key, macro_key)
            macro_instance = getattr(main_window, f"{macro_key}_macro", None)
            
            if macro_instance is None: 
                continue
            
            # is_running kontrolü - hem property hem method olabilir
            is_running_attr = getattr(macro_instance, 'is_running', None)
            if callable(is_running_attr):
                # Method ise çağır
                is_running = is_running_attr()
            elif is_running_attr is not None:
                # Property ise direkt kullan
                is_running = bool(is_running_attr)
            else:
                # Yoksa False
                is_running = False
            
            # Hotkey bilgisini al
            hotkey = self._get_hotkey(macro_instance, macro_key, main_window)
            
            # Icon path - MACRO_ICONS'dan al
            icon_path = MACRO_ICONS.get(macro_key, "")
            
            if is_running:
                active_count += 1
            
            # Kompakt modda sadece aktif olanları göster
            if self.compact_mode and not is_running:
                continue
            
            # Makro satırı oluştur
            row = self._create_macro_row(display_name, is_running, hotkey, icon_path)
            self.macro_layout.addWidget(row)
        
        # Kompakt modda hiç aktif yoksa mesaj göster
        if self.compact_mode and active_count == 0:
            lbl = QLabel("Aktif makro yok")
            lbl.setStyleSheet("color: #666; font-size: 9px; border: none; padding: 8px 0;")
            lbl.setAlignment(Qt.AlignCenter)
            self.macro_layout.addWidget(lbl)
        
        # Footer güncelle
        self.lbl_active_count.setText(f"{active_count} AKTİF")
        if active_count > 0:
            self.lbl_active_count.setStyleSheet("color: #00e676; font-size: 9px; font-weight: bold; border: none;")
        else:
            self.lbl_active_count.setStyleSheet("color: #888; font-size: 9px; border: none;")
        
        # Ping güncelle
        if hasattr(main_window, 'lbl_ping'):
            ping_text = main_window.lbl_ping.text()
            self.lbl_ping_hud.setText(ping_text if ping_text else "--ms")
        
        self.adjustSize()

    def _get_hotkey(self, macro_instance, macro_key, main_window):
        """Makronun hotkey'ini bul"""
        hotkey = ""
        
        # 1. Önce macro instance'ın config'inden bak
        if hasattr(macro_instance, 'config') and isinstance(macro_instance.config, dict):
            hotkey = macro_instance.config.get("hotkey", "") or macro_instance.config.get("key", "")
        
        # 2. main_window config'inden bak
        if not hotkey and hasattr(main_window, 'config'):
            macro_cfg = main_window.config.get(macro_key, {})
            if isinstance(macro_cfg, dict):
                hotkey = macro_cfg.get("hotkey", "") or macro_cfg.get("key", "")
        
        # 3. MODULE_REGISTRY default'larından bak
        if not hotkey and hasattr(main_window, 'MODULE_REGISTRY'):
            for mod in main_window.MODULE_REGISTRY:
                if mod.get("key") == macro_key:
                    default = mod.get("default", {})
                    hotkey = default.get("hotkey", "") or default.get("key", "")
                    break
        
        return str(hotkey).upper() if hotkey else ""

    def _create_macro_row(self, name, is_active, hotkey="", icon_path=""):
        """Tek bir makro satırı oluştur - icon ve hotkey ile"""
        row = QWidget()
        row.setFixedHeight(26)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)
        
        # Icon (varsa)
        if icon_path and os.path.exists(icon_path):
            icon_lbl = QLabel()
            icon_lbl.setFixedSize(18, 18)
            pixmap = QPixmap(icon_path)
            if not pixmap.isNull():
                icon_lbl.setPixmap(pixmap.scaled(18, 18, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            icon_lbl.setStyleSheet("border: none;")
            layout.addWidget(icon_lbl)
        else:
            # Durum göstergesi (icon yoksa pill badge)
            status = QLabel()
            status.setFixedSize(8, 8)
            if is_active:
                status.setStyleSheet("""
                    background-color: #00e676;
                    border-radius: 4px;
                    border: none;
                """)
            else:
                status.setStyleSheet("""
                    background-color: #444;
                    border-radius: 4px;
                    border: none;
                """)
            layout.addWidget(status)
        
        # Makro adı (kısaltılmış)
        short_name = self._shorten_name(name)
        name_lbl = QLabel(short_name)
        name_lbl.setStyleSheet(f"""
            color: {'#fff' if is_active else '#666'};
            font-size: 9px;
            font-weight: {'bold' if is_active else 'normal'};
            border: none;
        """)
        layout.addWidget(name_lbl)
        
        layout.addStretch()
        
        # Hotkey badge (varsa)
        if hotkey:
            hotkey_lbl = QLabel(hotkey)
            hotkey_lbl.setStyleSheet(f"""
                color: {'#fff' if is_active else '#555'};
                font-size: 8px;
                font-weight: bold;
                background-color: {'rgba(255,255,255,0.15)' if is_active else 'rgba(255,255,255,0.05)'};
                padding: 2px 5px;
                border-radius: 3px;
                border: none;
            """)
            layout.addWidget(hotkey_lbl)
        
        # Durum etiketi
        status_text = QLabel("ON" if is_active else "OFF")
        if is_active:
            status_text.setStyleSheet("""
                color: #00e676;
                font-size: 8px;
                font-weight: bold;
                background-color: rgba(0, 230, 118, 0.15);
                padding: 2px 6px;
                border-radius: 3px;
                border: none;
            """)
        else:
            status_text.setStyleSheet("""
                color: #555;
                font-size: 8px;
                background-color: rgba(255, 255, 255, 0.05);
                padding: 2px 6px;
                border-radius: 3px;
                border: none;
            """)
        layout.addWidget(status_text)
        
        return row

    def _shorten_name(self, name):
        """Uzun isimleri kısalt"""
        # Parantez içini kaldır
        name = re.sub(r'\s*\([^)]*\)', '', name)
        
        # Maksimum 15 karakter
        if len(name) > 15:
            return name[:14] + "…"
        return name


# ==============================================================================
# HUD AYARLAR PENCERESİ (GELİŞTİRİLMİŞ)
# ==============================================================================
class HUDSettingsDialog(QDialog):
    def __init__(self, parent, current_config, module_registry):
        super().__init__(parent)
        
        self.setWindowTitle("HUD GÖRÜNÜM AYARLARI")
        self.setModal(True)
        self.resize(450, 550)
        
        self.result_config = {"visible_macros": current_config.get("visible_macros", [])}
        self.all_checkboxes = []

        # Ana Layout
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(15, 15, 15, 15)
        
        # Header
        header = QWidget()
        h_layout = QVBoxLayout(header)
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.setSpacing(4)
        
        title = QLabel("🎮 HUD Görünüm Ayarları")
        title.setStyleSheet("color: #fff; font-size: 14px; font-weight: bold;")
        h_layout.addWidget(title)
        
        subtitle = QLabel("Ekranda görmek istediğiniz makroları seçin")
        subtitle.setStyleSheet("color: #888; font-size: 10px;")
        h_layout.addWidget(subtitle)
        
        main_layout.addWidget(header)
        
        # Hızlı seçim butonları
        quick_btns = QWidget()
        qb_layout = QHBoxLayout(quick_btns)
        qb_layout.setContentsMargins(0, 0, 0, 0)
        qb_layout.setSpacing(8)
        
        btn_all = QPushButton("✓ Tümünü Seç")
        btn_all.setStyleSheet(self._get_quick_btn_style())
        btn_all.clicked.connect(self.select_all)
        qb_layout.addWidget(btn_all)
        
        btn_none = QPushButton("✗ Tümünü Kaldır")
        btn_none.setStyleSheet(self._get_quick_btn_style())
        btn_none.clicked.connect(self.select_none)
        qb_layout.addWidget(btn_none)
        
        qb_layout.addStretch()
        main_layout.addWidget(quick_btns)

        # Scroll Area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea {
                background-color: #1a1a1a;
                border: 1px solid #333;
                border-radius: 6px;
            }
            QScrollBar:vertical {
                background: #1a1a1a;
                width: 8px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #444;
                border-radius: 4px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background: #555;
            }
        """)
        
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setSpacing(12)
        content_layout.setContentsMargins(10, 10, 10, 10)

        # Sayfa isimleri
        page_titles = {
            1: "⚔️ WARRIOR",
            2: "🗡️ ASAS / VS",
            3: "🏹 OKÇU",
            4: "💊 AKILLI POT",
            5: "🛡️ SELF / EKSTRA",
            6: "📦 TRADE",
            7: "🎯 PVP",
            8: "🔧 ARAÇLAR",
            9: "🤖 BOT",
            10: "⚙️ GENEL"
        }

        # Modülleri grupla
        grouped_modules = {}
        for mod in module_registry:
            raw_pid = mod.get("page_index", 99)
            target_pids = raw_pid if isinstance(raw_pid, list) else [raw_pid]
            
            for pid in target_pids:
                if pid not in grouped_modules:
                    grouped_modules[pid] = []
                grouped_modules[pid].append(mod)
        
        # Grupları ekrana bas
        for pid in sorted(grouped_modules.keys()):
            page_name = page_titles.get(pid, f"📁 SAYFA {pid}")
            modules_in_page = grouped_modules[pid]

            group_box = QGroupBox(page_name)
            group_box.setStyleSheet("""
                QGroupBox {
                    border: 1px solid #333;
                    border-radius: 8px;
                    margin-top: 12px;
                    font-weight: bold;
                    font-size: 11px;
                    color: #00e676;
                    padding-top: 8px;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 12px;
                    top: -6px;
                    padding: 0 6px;
                    background-color: #1a1a1a;
                }
            """)
            
            grid = QGridLayout(group_box)
            grid.setSpacing(6)
            grid.setContentsMargins(10, 15, 10, 10)
            
            row, col = 0, 0
            for mod in modules_in_page:
                key = mod["key"]
                name = mod["name"]
                
                cb = QCheckBox(name)
                cb.setStyleSheet("""
                    QCheckBox {
                        color: #ddd;
                        spacing: 8px;
                        font-size: 10px;
                        padding: 4px;
                    }
                    QCheckBox:hover {
                        color: #fff;
                    }
                    QCheckBox::indicator {
                        width: 16px;
                        height: 16px;
                        border: 2px solid #444;
                        border-radius: 4px;
                        background: #222;
                    }
                    QCheckBox::indicator:hover {
                        border-color: #00e676;
                    }
                    QCheckBox::indicator:checked {
                        background: #00e676;
                        border-color: #00e676;
                        image: url(none);
                    }
                """)
                
                if key in self.result_config["visible_macros"]:
                    cb.setChecked(True)
                
                cb.toggled.connect(lambda state, k=key: self.sync_selection(k, state))
                self.all_checkboxes.append((key, cb))
                
                grid.addWidget(cb, row, col)
                col += 1
                if col > 1:
                    col = 0
                    row += 1
            
            content_layout.addWidget(group_box)

        content_layout.addStretch()
        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)

        # Butonlar
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        btn_cancel = QPushButton("İptal")
        btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #333;
                color: #fff;
                border: 1px solid #444;
                padding: 10px 30px;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #444;
                border-color: #555;
            }
        """)
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)
        
        btn_layout.addStretch()
        
        btn_ok = QPushButton("✓ Kaydet")
        btn_ok.setStyleSheet("""
            QPushButton {
                background-color: #00e676;
                color: #000;
                border: none;
                padding: 10px 30px;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #00c853;
            }
        """)
        btn_ok.clicked.connect(self.accept)
        btn_layout.addWidget(btn_ok)
        
        main_layout.addLayout(btn_layout)
        
        # Dialog stili
        self.setStyleSheet("""
            QDialog {
                background-color: #121212;
                color: #fff;
            }
        """)

    def _get_quick_btn_style(self):
        return """
            QPushButton {
                background-color: #252525;
                color: #aaa;
                border: 1px solid #333;
                padding: 6px 12px;
                border-radius: 4px;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #333;
                color: #fff;
                border-color: #444;
            }
        """

    def select_all(self):
        """Tümünü seç"""
        for key, cb in self.all_checkboxes:
            cb.blockSignals(True)
            cb.setChecked(True)
            cb.blockSignals(False)

    def select_none(self):
        """Tümünü kaldır"""
        for key, cb in self.all_checkboxes:
            cb.blockSignals(True)
            cb.setChecked(False)
            cb.blockSignals(False)

    def sync_selection(self, target_key, state):
        """Aynı key'e sahip checkboxları senkronize et"""
        for key, cb in self.all_checkboxes:
            if key == target_key:
                cb.blockSignals(True)
                cb.setChecked(state)
                cb.blockSignals(False)

    def accept(self):
        selected_set = set()
        for key, cb in self.all_checkboxes:
            if cb.isChecked():
                selected_set.add(key)
        
        self.result_config["visible_macros"] = list(selected_set)
        super().accept()
