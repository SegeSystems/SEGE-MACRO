# -*- coding: utf-8 -*-
# ════════════════════════════════════════════════════════════════════════════
# SEGE OPEN SOURCE — Main window (ported from closed-source client/app/app.py)
# ════════════════════════════════════════════════════════════════════════════
#
# EN: This is the full main-window UI ported from the closed-source build.
#     All DRM, license, heartbeat, anti-debug, distress beacon and DLL
#     integrity calls have been stripped; the visual layer (dark theme,
#     sidebar, tabs, dashboard cards, dialogs, scanner boxes) is preserved
#     byte-for-byte where possible. Module loading goes through the plain
#     `load_all_modules()` from segesource.app.modules — no session token,
#     no hwid, no encrypted blobs.
#
# TR: Bu, kapalı kaynak sürümden port edilmiş tam ana pencere arayüzüdür.
#     Tüm DRM, lisans, heartbeat, anti-debug, distress beacon ve DLL
#     bütünlük çağrıları kaldırıldı; görsel katman (karanlık tema,
#     sidebar, sekmeler, dashboard kartları, dialoglar, tarama kutuları)
#     mümkün olduğu kadar bire bir korundu. Modül yükleme düz
#     `load_all_modules()` üzerinden yapılır — session token, hwid veya
#     şifreli blob yok.
# ════════════════════════════════════════════════════════════════════════════

from __future__ import annotations

# EN: Ensure segesource/ is on sys.path so macros can `import clicksend`.
# TR: Makroların `import clicksend` yapabilmesi için segesource/'u sys.path'e ekle.
import os
import sys
_PKG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PKG_DIR not in sys.path:
    sys.path.insert(0, _PKG_DIR)

import json
import datetime
import subprocess
import re

try:
    import winsound  # noqa: F401  (Windows-only beep helper used elsewhere)
except Exception:
    winsound = None

from translation_system import get_translation_manager
from core.logger import get_logger

log = get_logger(__name__)

# Open-source: no DRM. Application version string is package-derived.
try:
    from segesource import __version__ as CURRENT_VERSION
except Exception:
    CURRENT_VERSION = "0.1.0"


def get_resource(filename: str) -> str:
    """EN/TR: Resolve a packaged resource path; falls back to module dir."""
    try:
        from core.paths import resource_path
        return resource_path(filename)
    except Exception:
        base = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base, filename)


try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QDialog, QMessageBox,
    QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea,
    QPushButton, QLabel, QLineEdit, QCheckBox, QProgressBar,
    QComboBox, QSpinBox, QTextBrowser, QFrame, QGroupBox,
    QStackedWidget, QTabWidget, QListWidget, QListWidgetItem,
    QTreeWidget, QTreeWidgetItem, QDialogButtonBox, QAbstractItemView,
    QButtonGroup,
)
from PyQt5.QtCore import (
    Qt, QTimer, QTime, QCoreApplication,
    QPoint, QUrl, QPropertyAnimation, QSize,
    QBuffer, QIODevice, QByteArray,
)
from PyQt5.QtGui import QIcon, QPixmap, QDesktopServices, QColor

# --- Module registry (open-source: plain importlib) ---
from .modules import MODULE_REGISTRY, load_all_modules

# --- Tarama (scanner) + HUD optional imports ---
try:
    from shared.taramaalani import BuffScanner, SingleScanner
except ImportError:
    BuffScanner = None
    SingleScanner = None

try:
    from shared.hud import HUDOverlay, HUDSettingsDialog
except ImportError:
    HUDOverlay = None
    HUDSettingsDialog = None


# ────────────────────────────────────────────────────────────────────────────
# STYLE SHEET (verbatim from closed-source build)
# ────────────────────────────────────────────────────────────────────────────
STYLE_SHEET = """
/* GENEL */
QWidget { background-color: #121212; color: #e0e0e0; font-family: "Segoe UI Semibold", sans-serif; font-size: 10pt; }

/* HEADER & SIDEBAR */
#HeaderFrame { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #050505, stop:1 #1a1a1a); border-bottom: 2px solid #00e676; }
#SidebarFrame { background-color: #0f0f0f; border-right: 1px solid #222; }
QPushButton#SidebarBtn { background-color: transparent; color: #888; border: none; padding: 15px 20px; text-align: left; font-weight: bold; }
QPushButton#SidebarBtn:checked { color: #00e676; border-left: 4px solid #00e676; background: rgba(0, 230, 118, 0.1); }

/* GROUPBOX & CARDS */
QGroupBox { border: 1px solid #333; border-radius: 8px; margin-top: 15px; background-color: #161616; font-weight: bold; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; top: -5px; padding: 0 5px; background-color: #161616; color: #00e676; }
QFrame#DashCardFrame { background-color: #161616; border: 1px solid #333; border-radius: 8px; }

/* GLOBAL SETTINGS CARD */
QFrame#GlobalSettingsFrame {
    background-color: #161616;
    border: 1px solid #444;
    border-left: 4px solid #ff9100;
    border-radius: 8px;
}
QLabel#GlobalHeader {
    color: #2979ff;
    font-size: 12pt;
    font-weight: bold;
    border-bottom: 1px solid #333;
    padding-bottom: 5px;
}
QLineEdit#GlobalInput {
    background-color: #000;
    border: 1px solid #333;
    color: #00e676;
    font-family: "Consolas", monospace;
    font-size: 11pt;
    padding: 5px;
    border-radius: 4px;
}
QPushButton#GlobalSaveBtn {
    background-color: #2979ff;
    color: #fff;
    font-weight: bold;
    border-radius: 4px;
    padding: 8px;
}
QPushButton#GlobalSaveBtn:hover { background-color: #448aff; }

/* HUD BOX */
QFrame#HudBoxFrame { background-color: #161616; border: 1px solid #444; border-left: 4px solid #ff9100; border-radius: 8px; }

/* STANDARD ELEMENTS */
QLineEdit, QDoubleSpinBox, QComboBox { background-color: #222; border: 1px solid #444; color: #fff; padding: 2px; }
QPushButton { background-color: #252525; border: 1px solid #333; color: #eee; border-radius: 4px; padding: 6px; }
QPushButton:hover { border-color: #00e676; }
QPushButton[active="true"] { background-color: #d500f9; border-color: #d500f9; color: #fff; }
QPushButton#BottomSaveBtn { background-color: #00e676; color: #000; font-weight: bold; }
#StatusBar { background-color: #080808; border-top: 1px solid #222; color: #666; padding: 5px; }
"""


# ────────────────────────────────────────────────────────────────────────────
# Interface settings dialog (sidebar order, module placement, resolution)
# ────────────────────────────────────────────────────────────────────────────
class InterfaceSettingsDialog(QDialog):
    def __init__(self, current_ui_config, module_registry, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ARAYÜZ VE MODÜL AYARLARI")
        self.resize(800, 700)
        self.config = current_ui_config or {}
        self.module_registry = module_registry

        self.page_names = {
            "dashboard": "⚡ DASHBOARD",
            "pk_container": "⚔️ PK MODU",
            "farm": "🚜 FARM MODU",
            "pot": "💊 SMART HPMP",
            "self": "🧠 SELF MACRO",
            "general": "🔨 GENEL",
            "warrior": "⚔️ WARRIOR", "asas": "🔪 ASSASSIN", "okcu": "🏹 ARCHER",
            "priest": "🛡️ PRIEST", "mage": "🔥 MAGICIAN", "kurian": "👹 KURIAN",
        }

        self.pk_sub_pages = ["warrior", "asas", "okcu", "priest", "mage", "kurian"]

        pages_from_config = self.config.get("pages")
        self.pages_data = pages_from_config if pages_from_config else [
            {"id": "dashboard", "name": "⚡ DASHBOARD", "visible": True},
            {"id": "pk_container", "name": "⚔️ PK MODU", "visible": True},
            {"id": "farm", "name": "🚜 FARM MODU", "visible": True},
            {"id": "pot", "name": "💊 SMART HPMP", "visible": True},
            {"id": "self", "name": "🧠 SELF MACRO", "visible": True},
            {"id": "general", "name": "🔨 GENEL", "visible": True},
        ]

        self.current_layouts = self.config.get("page_layouts", {})

        main_layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.tab_ui = QWidget()
        self.tab_modules = QWidget()
        self.tabs.addTab(self.tab_ui, "Görünüm ve Sayfalar")
        self.tabs.addTab(self.tab_modules, "Kategoriler ve Modüller")
        main_layout.addWidget(self.tabs)

        self.setup_ui_tab()
        self.setup_module_tab()

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.save_and_accept)
        btns.rejected.connect(self.reject)
        main_layout.addWidget(btns)

        self.setStyleSheet("""
            QDialog { background: #161616; color: #eee; }
            QComboBox, QSpinBox { background: #222; color: #fff; padding: 5px; border: 1px solid #444; }
            QTabWidget::pane { border: 1px solid #444; }
            QTabBar::tab { background: #222; color: #888; padding: 10px; }
            QTabBar::tab:selected { background: #00e676; color: #000; font-weight: bold; }
            QTreeWidget { background: #111; border: 1px solid #333; font-size: 10pt; }
            QTreeWidget::item { padding: 8px; }
            QPushButton { background-color: #333; color: white; border: 1px solid #555; padding: 8px; border-radius: 4px; }
            QPushButton:hover { background-color: #444; border-color: #00e676; }
        """)

    def setup_ui_tab(self):
        layout = QVBoxLayout(self.tab_ui)
        gb_res = QGroupBox("Pencere Boyutu")
        res_layout = QHBoxLayout(gb_res)
        self.combo_res = QComboBox()
        self.combo_res.addItems(["1280x850 (Varsayılan)", "1024x768", "1366x768", "1600x900", "1920x1080", "Özel..."])
        self.spin_w = QSpinBox(); self.spin_w.setRange(800, 2560); self.spin_w.setSuffix(" px")
        self.spin_h = QSpinBox(); self.spin_h.setRange(600, 1440); self.spin_h.setSuffix(" px")
        self.spin_w.setValue(self.config.get("width", 1280)); self.spin_h.setValue(self.config.get("height", 850))
        res_layout.addWidget(QLabel("Hazır:")); res_layout.addWidget(self.combo_res); res_layout.addWidget(QLabel("G:")); res_layout.addWidget(self.spin_w); res_layout.addWidget(QLabel("Y:")); res_layout.addWidget(self.spin_h)
        self.combo_res.currentIndexChanged.connect(self.on_preset_change)
        layout.addWidget(gb_res)

        gb_pages = QGroupBox("Sol Menü Sıralama ve Görünürlük")
        p_layout = QVBoxLayout(gb_pages)
        self.list_widget = QListWidget()
        self.list_widget.setDragDropMode(QAbstractItemView.InternalMove)
        for p in self.pages_data:
            item = QListWidgetItem(p["name"]); item.setData(Qt.UserRole, p["id"])
            item.setCheckState(Qt.Checked if p.get("visible", True) else Qt.Unchecked)
            self.list_widget.addItem(item)
        p_layout.addWidget(QLabel("Sürükleyerek sidebar sırasını değiştirebilirsiniz."))
        p_layout.addWidget(self.list_widget)
        layout.addWidget(gb_pages)

    def setup_module_tab(self):
        layout = QHBoxLayout(self.tab_modules)
        left_layout = QVBoxLayout()
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(25)

        self.leaf_nodes = {}
        mod_name_map = {m["key"]: m["name"] for m in self.module_registry}

        for p in self.pages_data:
            if p["id"] == "dashboard":
                continue
            root = QTreeWidgetItem(self.tree)
            root.setText(0, p["name"])
            root.setData(0, Qt.UserRole, f"CAT:{p['id']}")
            root.setForeground(0, QColor("#00e676"))
            font = root.font(0); font.setBold(True); root.setFont(0, font)
            root.setExpanded(True)

            if p["id"] == "pk_container":
                for sub_id in self.pk_sub_pages:
                    sub_item = QTreeWidgetItem(root)
                    sub_item.setText(0, self.page_names.get(sub_id, sub_id))
                    sub_item.setData(0, Qt.UserRole, f"PAGE:{sub_id}")
                    sub_item.setForeground(0, QColor("#2979ff"))
                    self.leaf_nodes[sub_id] = sub_item
            else:
                self.leaf_nodes[p["id"]] = root

        processed_keys = set()
        for page_id, mod_keys in self.current_layouts.items():
            target_node = self.leaf_nodes.get(page_id)
            if not target_node:
                continue
            for mk in mod_keys:
                name = mod_name_map.get(mk)
                if name:
                    child = QTreeWidgetItem(target_node)
                    child.setText(0, f"🔸 {name}")
                    child.setData(0, Qt.UserRole, f"MOD:{mk}")
                    processed_keys.add(mk)

        for mod in self.module_registry:
            if mod["key"] not in processed_keys:
                self.add_mod_to_node("self", mod["key"], mod["name"])

        left_layout.addWidget(self.tree)

        right_panel = QFrame()
        right_panel.setFixedWidth(240)
        right_panel.setStyleSheet("background-color: #1a1a1a; border-radius: 8px;")
        rv = QVBoxLayout(right_panel)

        rv.addWidget(QLabel("SIRALAMA (SEÇİLEN ÖĞE)"))
        btn_up = QPushButton("⬆️ YUKARI"); btn_up.clicked.connect(lambda: self.move_item(-1))
        btn_down = QPushButton("⬇️ AŞAĞI"); btn_down.clicked.connect(lambda: self.move_item(1))
        rv.addWidget(btn_up); rv.addWidget(btn_down)

        rv.addSpacing(20)
        rv.addWidget(QLabel("MODÜLÜ TAŞI"))
        self.combo_move = QComboBox()
        move_targets = ["warrior", "asas", "okcu", "priest", "mage", "kurian", "farm", "pot", "self", "general"]
        for mt in move_targets:
            self.combo_move.addItem(self.page_names.get(mt, mt), mt)
        rv.addWidget(self.combo_move)

        btn_move = QPushButton("➡️ BU SAYFAYA TAŞI")
        btn_move.setStyleSheet("background-color: #004d40;")
        btn_move.clicked.connect(self.move_to_page)
        rv.addWidget(btn_move)

        rv.addStretch()
        layout.addLayout(left_layout, 1)
        layout.addWidget(right_panel)

    def add_mod_to_node(self, node_id, key, name):
        node = self.leaf_nodes.get(node_id)
        if node:
            child = QTreeWidgetItem(node)
            child.setText(0, f"🔸 {name}")
            child.setData(0, Qt.UserRole, f"MOD:{key}")

    def move_item(self, direction):
        item = self.tree.currentItem()
        if not item:
            return
        parent = item.parent() or self.tree.invisibleRootItem()
        idx = parent.indexOfChild(item)
        new_idx = idx + direction
        if 0 <= new_idx < parent.childCount():
            it = parent.takeChild(idx)
            parent.insertChild(new_idx, it)
            self.tree.setCurrentItem(it)

    def move_to_page(self):
        item = self.tree.currentItem()
        if not item or not item.data(0, Qt.UserRole).startswith("MOD:"):
            QMessageBox.warning(self, "Hata", "Lütfen taşımak için bir modül seçin.")
            return
        target_id = self.combo_move.currentData()
        target_node = self.leaf_nodes.get(target_id)
        if target_node and item.parent() != target_node:
            old_parent = item.parent()
            it = old_parent.takeChild(old_parent.indexOfChild(item))
            target_node.addChild(it)
            target_node.setExpanded(True)
            self.tree.setCurrentItem(it)

    def on_preset_change(self):
        txt = self.combo_res.currentText()
        res = {"1280": (1280, 850), "1024": (1024, 768), "1366": (1366, 768), "1600": (1600, 900), "1920": (1920, 1080)}
        for k, v in res.items():
            if k in txt:
                self.spin_w.setValue(v[0]); self.spin_h.setValue(v[1])

    def save_and_accept(self):
        self.config["width"] = self.spin_w.value()
        self.config["height"] = self.spin_h.value()
        new_pages = []
        for i in range(self.list_widget.count()):
            it = self.list_widget.item(i)
            new_pages.append({"id": it.data(Qt.UserRole), "name": it.text(), "visible": (it.checkState() == Qt.Checked)})
        self.config["pages"] = new_pages

        new_layouts = {}
        for page_id, node in self.leaf_nodes.items():
            mod_list = []
            for j in range(node.childCount()):
                child = node.child(j)
                data = child.data(0, Qt.UserRole)
                if data and data.startswith("MOD:"):
                    mod_list.append(data.split(":")[1])
            new_layouts[page_id] = mod_list

        self.config["page_layouts"] = new_layouts
        self.accept()


# ────────────────────────────────────────────────────────────────────────────
# Rich notification dialog — kept for parity (open-source: shown locally only)
# ────────────────────────────────────────────────────────────────────────────
class RichNotificationDialog(QDialog):
    def __init__(self, message, size_mode="M", is_blocking=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("BİLDİRİM")

        if size_mode == "S":
            w, h = 350, 250; self.max_img_w = 310; self.max_img_h = 130
        elif size_mode == "L":
            w, h = 800, 600; self.max_img_w = 760; self.max_img_h = 450
        else:
            w, h = 500, 450; self.max_img_w = 460; self.max_img_h = 280

        self.setFixedSize(w, h)
        flags = Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
        if is_blocking:
            self.setWindowModality(Qt.ApplicationModal)
        self.setWindowFlags(flags)

        self.setStyleSheet("""
            QDialog { background-color: #1a1a1a; border: 2px solid #ff0000; border-radius: 10px; }
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(5, 5, 5, 5)

        lbl_title = QLabel("📢 BİLDİRİM")
        lbl_title.setStyleSheet("color: #ff0000; font-weight: bold; font-size: 14pt; border: none; background: transparent; padding-bottom: 5px;")
        lbl_title.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl_title)

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.setFrameShape(QFrame.NoFrame)
        self.browser.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.browser.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        css_style = f"""
            body {{ margin: 0; padding: 5px; color: #e0e0e0; font-family: 'Segoe UI', sans-serif; font-size: 11pt; text-align: center; }}
            td {{ text-align: center; }}
            a {{ text-decoration: none; }}
            img {{ max-width: 100%; max-height: {self.max_img_h}px; width: auto; height: auto; }}
        """
        self.browser.document().setDefaultStyleSheet(css_style)
        layout.addWidget(self.browser)

        final_html = self.resize_base64_images(str(message))
        self.browser.setHtml(final_html)

        layout.addSpacing(5)
        btn_ok = QPushButton("TAMAM")
        btn_ok.setCursor(Qt.PointingHandCursor)
        btn_ok.setMinimumHeight(40)
        btn_ok.setStyleSheet("""
            QPushButton { background-color: #d32f2f; color: white; font-weight: bold; border-radius: 5px; border: 1px solid #b71c1c; font-size: 11pt; }
            QPushButton:hover { background-color: #f44336; border: 1px solid #d32f2f; }
            QPushButton:pressed { background-color: #b71c1c; }
        """)
        btn_ok.clicked.connect(self.accept)
        layout.addWidget(btn_ok)

    def resize_base64_images(self, html_content):
        import base64, hashlib
        if not hasattr(self, '_scaled_cache'):
            self._scaled_cache = {}
        cache = self._scaled_cache
        pattern = r'src="data:image/(\w+);base64,([^"]+)"'

        def replace_match(match):
            try:
                fmt = match.group(1)
                b64_str = match.group(2)
                cache_key = (fmt, self.max_img_w, self.max_img_h,
                             hashlib.md5(b64_str.encode()).hexdigest())
                if cache_key in cache:
                    return f'src="data:image/{fmt};base64,{cache[cache_key]}"'
                img_data = base64.b64decode(b64_str)
                pixmap = QPixmap()
                pixmap.loadFromData(img_data)
                if pixmap.isNull():
                    return match.group(0)
                scaled_pix = pixmap.scaled(self.max_img_w, self.max_img_h,
                                           Qt.KeepAspectRatio, Qt.SmoothTransformation)
                ba = QByteArray()
                buf = QBuffer(ba)
                buf.open(QIODevice.WriteOnly)
                scaled_pix.save(buf, fmt.upper())
                new_b64 = ba.toBase64().data().decode()
                cache[cache_key] = new_b64
                return f'src="data:image/{fmt};base64,{new_b64}"'
            except Exception:
                return match.group(0)

        return re.sub(pattern, replace_match, html_content)


# ────────────────────────────────────────────────────────────────────────────
# Custom title bar (frameless window header)
# ────────────────────────────────────────────────────────────────────────────
class CustomTitleBar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setObjectName("HeaderFrame")
        self.setFixedHeight(45)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 10, 0)
        layout.setSpacing(10)

        title = QLabel("SEGE OPEN SOURCE")
        title.setStyleSheet("color:#00e676; font-family:Impact; font-size:14pt; font-weight:bold; background:transparent;")
        layout.addWidget(title)
        layout.addStretch()

        # Language toggle button
        self.btn_language = QPushButton("🌐 TR")
        self.btn_language.setFixedSize(70, 30)
        self.btn_language.setCursor(Qt.PointingHandCursor)
        self.btn_language.setStyleSheet("""
            QPushButton {
                background-color: #2979ff; color: white; font-weight: bold;
                border-radius: 4px; border: 1px solid #1565c0; font-size: 9pt;
            }
            QPushButton:hover { background-color: #448aff; border: 1px solid #2979ff; }
        """)
        self.btn_language.clicked.connect(self.change_language)
        layout.addWidget(self.btn_language)
        self.update_language_button()

        # Social links
        social_links = [
            ("social_web.png",       "#00e676", "https://segemacro.com/"),
            ("social_discord.png",   "#5865F2", "https://discord.com/invite/Gc9aejarTH"),
            ("social_youtube.png",   "#FF0000", "https://www.youtube.com/@segemacro"),
            ("social_instagram.png", "#E1306C", "https://www.instagram.com/segemacro/"),
            ("social_tiktok.png",    "#E1306C", "https://www.tiktok.com/@segemacro"),
        ]
        for icon_file, color, url in social_links:
            btn = QPushButton()
            btn.setFixedSize(30, 30)
            btn.setCursor(Qt.PointingHandCursor)
            icon_path = get_resource(icon_file)
            if not os.path.exists(icon_path):
                btn.setText("•")
                btn.setStyleSheet(f"color:{color}; border:1px solid {color};")
            else:
                btn.setIcon(QIcon(icon_path))
                btn.setIconSize(QSize(18, 18))
            btn.setStyleSheet(f"QPushButton {{ background: transparent; border: 1px solid {color}; border-radius: 5px; }} QPushButton:hover {{ background-color: {color}; }}")
            btn.clicked.connect(lambda _, u=url: QDesktopServices.openUrl(QUrl(u)))
            layout.addWidget(btn)

        layout.addSpacing(10)
        line = QFrame()
        line.setFrameShape(QFrame.VLine)
        line.setFixedSize(1, 25)
        line.setStyleSheet("background-color: #333;")
        layout.addWidget(line)
        layout.addSpacing(5)

        self.clk = QLabel("00:00:00")
        self.clk.setStyleSheet("color:#888; font-family: Consolas; font-weight: bold; background:transparent; font-size: 11pt;")
        layout.addWidget(self.clk)

        timer = QTimer(self)
        timer.timeout.connect(lambda: self.clk.setText(QTime.currentTime().toString("HH:mm:ss")))
        timer.start(1000)

        btn_min = QPushButton("─")
        btn_close = QPushButton("✕")
        for b in (btn_min, btn_close):
            b.setFixedSize(35, 35)
            b.setStyleSheet("QPushButton { background: transparent; color: #888; border: none; font-size: 14pt; } QPushButton:hover { background-color: #222; color: white; border-radius: 4px; }")
            layout.addWidget(b)
        btn_close.setStyleSheet("QPushButton { background: transparent; color: #888; border: none; font-size: 14pt; } QPushButton:hover { background-color: #d32f2f; color: white; border-radius: 4px; }")
        btn_min.clicked.connect(lambda: self.parent.showMinimized())
        btn_close.clicked.connect(lambda: self.parent.close())

        self.start = QPoint(0, 0)
        self.pressing = False

    def update_language_button(self):
        tm = get_translation_manager()
        current = tm.current_language.upper()
        flag_map = {
            "TR": "🇹🇷", "EN": "🇬🇧", "DE": "🇩🇪",
            "FR": "🇫🇷", "ES": "🇪🇸", "RU": "🇷🇺",
            "AR": "🇸🇦", "JA": "🇯🇵", "KO": "🇰🇷", "ZH-CN": "🇨🇳",
        }
        flag = flag_map.get(current, "🌐")
        self.btn_language.setText(f"{flag} {current}")

    def change_language(self):
        from PyQt5.QtWidgets import QMenu
        tm = get_translation_manager()
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #1e1e1e; color: #ffffff; border: 1px solid #00e676; padding: 5px; }
            QMenu::item { padding: 8px 25px; border-radius: 3px; }
            QMenu::item:selected { background-color: #00e676; color: #000000; }
        """)
        for code, name in tm.LANGUAGES.items():
            action = menu.addAction(name)
            action.triggered.connect(lambda checked, c=code: self.apply_language(c))
        menu.exec_(self.btn_language.mapToGlobal(self.btn_language.rect().bottomLeft()))

    def apply_language(self, lang_code):
        tm = get_translation_manager()
        if tm.set_language(lang_code):
            self.update_language_button()
            try:
                tm.translate_widget_texts(self)
            except Exception:
                pass
            if hasattr(self.parent, 'central'):
                tm.translate_widget_texts(self.parent.central)
            try:
                if hasattr(self.parent, 'sidebar_btns'):
                    for btn in self.parent.sidebar_btns:
                        tm.translate_widget_texts(btn)
            except Exception:
                pass
            if hasattr(self.parent, 'status_bar'):
                current_text = self.parent.status_bar.text().strip()
                if current_text and not current_text.startswith("🔔"):
                    self.parent.status_bar.setText(tm.translate(" Hazır."))

    def mousePressEvent(self, e):
        self.pressing = True
        self.start = self.mapToGlobal(e.pos())

    def mouseMoveEvent(self, e):
        if self.pressing:
            end = self.mapToGlobal(e.pos())
            move = end - self.start
            self.parent.setGeometry(self.parent.x() + move.x(),
                                    self.parent.y() + move.y(),
                                    self.parent.width(),
                                    self.parent.height())
            self.start = end

    def mouseReleaseEvent(self, e):
        self.pressing = False


# ────────────────────────────────────────────────────────────────────────────
# Main window
# ────────────────────────────────────────────────────────────────────────────
class SegeMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.MODULE_REGISTRY = MODULE_REGISTRY

        self.setWindowFlags(Qt.FramelessWindowHint)
        self.app_start_time = datetime.datetime.now()

        # Open-source: no license tier, no remaining-days. Show fixed labels.
        self.license_days = 9999
        self.license_level = "OPEN-SOURCE"
        self.username = self.load_username_from_settings()

        self.hud_window = None
        self.is_hud_running = False
        self.loaded_modules = {}
        self.setWindowIcon(QIcon(get_resource("sege.ico")))
        self.setWindowTitle("SEGE OPEN SOURCE")
        self.all_pk_button_groups = []

        # 1. SETTINGS
        self.config = {
            "hud_settings": {"visible_macros": ["hpmp"]},
            "global": {"target_process": "KnightOnLine.exe", "filter_enabled": False},
        }
        for m in self.MODULE_REGISTRY:
            self.config[m["key"]] = m["default"]
        self.load_settings()

        self.config.setdefault("global", {"target_process": "KnightOnLine.exe", "filter_enabled": False})
        self.config.setdefault("hud_settings", {"visible_macros": ["hpmp"]})

        # 2. GUI SETTINGS
        self.gui_config = {
            "width": 1280,
            "height": 850,
            "pages": [],
            "page_layouts": {},
        }
        self.load_gui_settings()

        if not self.gui_config.get("page_layouts"):
            log.info("Building fresh page_layouts from MODULE_REGISTRY")
            layouts = {
                "dashboard": [], "warrior": [], "asas": [], "okcu": [],
                "pot": [], "self": [], "priest": [], "mage": [],
                "kurian": [], "farm": [], "general": [],
            }
            legacy_map = {
                1: "warrior", 2: "asas", 3: "okcu", 4: "pot", 5: "self",
                6: "priest", 7: "mage", 8: "kurian", 9: "farm", 10: "general",
            }
            for m in self.MODULE_REGISTRY:
                raw_idxs = m.get("page_index", [5])
                target_indices = [raw_idxs] if isinstance(raw_idxs, int) else raw_idxs
                for idx in target_indices:
                    page_id = legacy_map.get(idx, "self")
                    if page_id in layouts:
                        if m["key"] not in layouts[page_id]:
                            layouts[page_id].append(m["key"])
            self.gui_config["page_layouts"] = layouts
            self.save_gui_settings()

        # Resize
        w = self.gui_config.get("width", 1280)
        h = self.gui_config.get("height", 850)
        self.resize(w, h)

        # 3. Scanners + UI
        self.buff_scanner = BuffScanner("BUFF_ALANI.json", self) if BuffScanner else None
        self.single_scanner = SingleScanner("1LI_ALANI.json", self) if SingleScanner else None
        self.init_ui()
        self.log_status(f"Sistem hazır. {self.license_level}.")

        # Open-source: no heartbeat worker. Just a UI refresh timer.
        QTimer(self, timeout=self.update_dashboard_and_colors).start(1000)
        self.setStyleSheet(STYLE_SHEET)

        QTimer.singleShot(500, lambda: get_translation_manager().translate_widget_texts(self.central))

    # ──────────────────────────────────────────────────────────────────────
    # Module loading — open-source signature: load_all_modules() takes NO args
    # ──────────────────────────────────────────────────────────────────────
    def load_and_init_modules(self):
        """EN/TR: Load every macro from disk and bind to the UI."""
        log.info("Modules loading")
        self.loaded_modules = load_all_modules()

        for m in self.MODULE_REGISTRY:
            if m["key"] not in self.config:
                self.config[m["key"]] = m["default"]

        self.init_macros()
        self.rebuild_dynamic_pages()
        log.info("UI rebuilt with loaded modules")

    def rebuild_dynamic_pages(self):
        self.all_pk_button_groups = []
        while self.pages.count() > 1:
            widget = self.pages.widget(1)
            self.pages.removeWidget(widget)
            try:
                widget.setParent(None)
            except Exception:
                pass
            widget.deleteLater()
        QApplication.processEvents()

        main_nav_data = [
            {"id": "pk_container"},
            {"id": "farm"},
            {"id": "pot"},
            {"id": "self"},
            {"id": "general"},
        ]
        for item in main_nav_data:
            if item['id'] == "pk_container":
                widget = self.create_pk_container()
            else:
                widget = self.create_dynamic_page(item['id'])
            self.pages.addWidget(widget)

    def init_macros(self):
        self.macros = {}
        self.MACRO_MAP = {}
        for mod_def in self.MODULE_REGISTRY:
            key = mod_def["key"]
            if key in self.loaded_modules:
                macro_instance, WidgetClass = self.loaded_modules[key]
                cfg = self.config.get(key, mod_def.get("default", {}))
                if hasattr(macro_instance, "update_config"):
                    macro_instance.update_config(cfg)
                setattr(self, f"{key}_macro", macro_instance)
                self.macros[key] = macro_instance
                self.MACRO_MAP[key] = mod_def.get("name", key)

    def closeEvent(self, event):
        """EN/TR: Open-source: nothing remote to clean up. Just close."""
        event.accept()

    @property
    def hud_settings_config(self):
        return self.config.get("hud_settings", {})

    # ──────────────────────────────────────────────────────────────────────
    # Settings I/O
    # ──────────────────────────────────────────────────────────────────────
    def load_settings(self):
        from core.paths import settings_path
        sp = settings_path()
        if os.path.exists(sp):
            try:
                with open(sp, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    if k in self.config and isinstance(v, dict):
                        self.config[k].update(v)
                    else:
                        self.config[k] = v
                log.info("Settings loaded")
            except Exception as e:
                log.error("Settings load error: %s", e)

    def load_username_from_settings(self):
        try:
            from core.paths import settings_path
            sp = settings_path()
            if os.path.exists(sp):
                with open(sp, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    auth_data = data.get("auth", {})
                    username = auth_data.get("user", "")
                    if username:
                        return username
        except Exception:
            pass
        return "USER"

    def load_gui_settings(self):
        from core.paths import gui_settings_path
        gp = gui_settings_path()
        if os.path.exists(gp):
            try:
                with open(gp, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.gui_config.update(data)
            except Exception as e:
                try:
                    import shutil
                    shutil.copy2(gp, gp + ".bak")
                except Exception:
                    pass
                log.error("GUI settings load error (file backed up): %s", e)

    def save_gui_settings(self):
        from core.paths import gui_settings_path
        try:
            with open(gui_settings_path(), "w", encoding="utf-8") as f:
                json.dump(self.gui_config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            QMessageBox.critical(self, "HATA", f"Arayüz ayarları kaydedilemedi: {e}")
            raise

    def save_settings_to_json(self):
        from core.paths import settings_path
        try:
            valid_mod_keys = {m["key"] for m in self.MODULE_REGISTRY}
            reserved = {"global", "hud_settings", "auth", "pages", "page_layouts"}
            filtered = {}
            for k, v in self.config.items():
                if k in valid_mod_keys or k in reserved:
                    filtered[k] = v
            self.config = filtered
        except Exception:
            pass

        try:
            with open(settings_path(), "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            self.log_status("Ayarlar kaydedildi.")
            QMessageBox.information(self, "KAYIT", "Ayarlar başarıyla kaydedildi.")
        except Exception as e:
            QMessageBox.critical(self, "HATA", str(e))
            raise

    # ──────────────────────────────────────────────────────────────────────
    # UI build
    # ──────────────────────────────────────────────────────────────────────
    def init_ui(self):
        self.central = QWidget(); self.setCentralWidget(self.central)
        main_layout = QVBoxLayout(self.central); main_layout.setContentsMargins(0, 0, 0, 0); main_layout.setSpacing(0)
        main_layout.addWidget(CustomTitleBar(self))

        body = QHBoxLayout(); body.setContentsMargins(0, 0, 0, 0); body.setSpacing(0)

        sidebar = QFrame(); sidebar.setObjectName("SidebarFrame"); sidebar.setFixedWidth(240)
        s_lay = QVBoxLayout(sidebar)
        s_lay.setContentsMargins(0, 0, 0, 10)
        s_lay.setSpacing(2)

        logo_label = QLabel()
        logo_label.setAlignment(Qt.AlignCenter)
        logo_path = get_resource("sege.ico")
        if os.path.exists(logo_path):
            pix = QPixmap(logo_path).scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            logo_label.setPixmap(pix)
        logo_label.setStyleSheet("background:transparent; padding: 10px 0 5px 0;")
        s_lay.addWidget(logo_label)

        pages_to_build = self.gui_config.get("pages", [])
        if not pages_to_build:
            pages_to_build = [
                {"id": "dashboard", "name": "⚡ DASHBOARD", "visible": True},
                {"id": "pk_container", "name": "⚔️ PK MODU", "visible": True},
                {"id": "farm", "name": "🚜 FARM MODU", "visible": True},
                {"id": "pot", "name": "💊 SMART HPMP", "visible": True},
                {"id": "self", "name": "🧠 SELF MACRO", "visible": True},
                {"id": "general", "name": "🔨 GENEL", "visible": True},
            ]

        self.pages = QStackedWidget()
        self.sidebar_btns = []

        current_idx = 0
        for item in pages_to_build:
            if not item.get("visible", True):
                continue
            btn = QPushButton(f" {item['name']}")
            btn.setObjectName("SidebarBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda c, i=current_idx, b=btn: self.switch_page(i, b))
            s_lay.addWidget(btn)
            self.sidebar_btns.append(btn)

            if item['id'] == "dashboard":
                widget = self.create_dashboard_page()
            elif item['id'] == "pk_container":
                widget = self.create_pk_container()
            else:
                widget = self.create_dynamic_page(item['id'])
            self.pages.addWidget(widget)
            current_idx += 1

        s_lay.addStretch(1)

        # License / version box (open-source: static labels)
        lic = QFrame(); lic.setStyleSheet("background:rgba(255,255,255,0.03); border-radius:4px; padding:5px; margin:5px;")
        lv = QVBoxLayout(lic); lv.setSpacing(5); lv.setContentsMargins(5, 5, 5, 5)

        self.lbl_license_level = QLabel(f"👤 {self.license_level}")
        self.lbl_license_level.setStyleSheet("color:#00e676; font-weight:bold; background:rgba(255,255,255,0.05); padding:8px; border-radius:3px;")
        lv.addWidget(self.lbl_license_level)

        self.lbl_expiry = QLabel("⏰ SÜRE: LIFETIME")
        self.lbl_expiry.setStyleSheet("color:#ffea00; font-weight:bold; background:rgba(255,255,255,0.05); padding:8px; border-radius:3px;")
        lv.addWidget(self.lbl_expiry)

        lbl_ver = QLabel(f"V: {CURRENT_VERSION}")
        lbl_ver.setStyleSheet("color: #ffd600; font-size: 11pt; font-family: Consolas; font-weight: bold; padding-top: 6px;")
        lv.addWidget(lbl_ver)

        s_lay.addWidget(lic)

        btn_settings = QPushButton("⚙️ ARAYÜZ AYARLARI")
        btn_settings.setObjectName("SidebarBtn")
        btn_settings.setStyleSheet("color: #888; font-size: 9pt; border: none; padding: 10px;")
        btn_settings.setCursor(Qt.PointingHandCursor)
        btn_settings.clicked.connect(self.open_ui_settings)
        s_lay.addWidget(btn_settings)

        body.addWidget(sidebar)

        content = QWidget(); c_lay = QVBoxLayout(content); c_lay.setContentsMargins(0, 0, 0, 0)
        c_lay.addWidget(self.pages); body.addWidget(content); main_layout.addLayout(body)

        self.status_bar = QLabel(" Hazır."); self.status_bar.setObjectName("StatusBar"); self.status_bar.setFixedHeight(30)
        main_layout.addWidget(self.status_bar)

        if self.sidebar_btns:
            self.switch_page(0, self.sidebar_btns[0])

    def create_scanner_box(self, page_id):
        container = QFrame()
        container.setStyleSheet("background-color: transparent;")
        main_layout = QHBoxLayout(container)
        main_layout.setContentsMargins(0, 10, 0, 10)
        main_layout.setSpacing(20)

        BTN_STYLE = "QPushButton { background:#1a1a1a; color:#ccc; border:1px solid #444; padding:8px; border-radius: 4px; font-weight: bold; } QPushButton:hover { background: #00e676; color: black; border: 1px solid #00ff00; }"

        if BuffScanner and self.buff_scanner:
            box_buff = QGroupBox("BUFF TARAMA")
            box_buff.setStyleSheet("QGroupBox { border: 1px solid #333; background-color: #0f0f0f; border-radius:6px; margin-top: 10px; } QGroupBox::title { color: #888; subcontrol-origin: margin; left: 10px; top: -5px; }")
            buff_layout = QVBoxLayout(box_buff)
            b1 = QPushButton("💾 BUFF KAYDET"); b1.clicked.connect(self.buff_scanner.toggle_guide_overlay); b1.setStyleSheet(BTN_STYLE)
            b2 = QPushButton("👁 BUFF GÖSTER"); b2.clicked.connect(self.buff_scanner.read_skills); b2.setStyleSheet(BTN_STYLE)
            buff_layout.addWidget(b1); buff_layout.addWidget(b2)
            box_buff.setFixedWidth(200); box_buff.setFixedHeight(130)
            main_layout.addWidget(box_buff)

        lbl_banner = QLabel()
        lbl_banner.setAlignment(Qt.AlignCenter)
        lbl_banner.setFixedHeight(150)
        banner_map = {
            "dashboard": "icons/mainbanner.png",
            "warrior": "icons/waribanner.png",
            "asas": "icons/asasbanner.png",
            "okcu": "icons/okcubanner.png",
            "pot": "icons/potbanner.png",
            "self": "icons/selfbanner.png",
            "priest": "icons/priestbanner.png",
            "mage": "icons/magebanner.png",
            "kurian": "icons/kurianbanner.png",
            "farm": "icons/farmbanner.png",
            "general": "icons/generalbanner.png",
        }
        try:
            img_path = banner_map.get(page_id, "icons/mainbanner.png")
            if os.path.exists(img_path):
                pix = QPixmap(img_path)
                lbl_banner.setPixmap(pix)
            else:
                lbl_banner.setText(f"BANNER: {page_id}")
                lbl_banner.setStyleSheet("color: #444; border: 2px dashed #333;")
        except Exception as e:
            lbl_banner.setText(f"BANNER ERROR: {e}")
            lbl_banner.setStyleSheet("color: red;")
        main_layout.addWidget(lbl_banner, 1)

        if SingleScanner and self.single_scanner:
            box_single = QGroupBox("1'Lİ TARAMA")
            box_single.setStyleSheet("QGroupBox { border: 1px solid #333; background-color: #0f0f0f; border-radius:6px; margin-top: 10px; } QGroupBox::title { color: #888; subcontrol-origin: margin; left: 10px; top: -5px; }")
            single_layout = QVBoxLayout(box_single)
            b3 = QPushButton("💾 1'Lİ KAYDET"); b3.clicked.connect(self.single_scanner.toggle_overlay); b3.setStyleSheet(BTN_STYLE)
            b4 = QPushButton("🎯 1'Lİ GÖSTER"); b4.clicked.connect(self.single_scanner.save_region); b4.setStyleSheet(BTN_STYLE)
            single_layout.addWidget(b3); single_layout.addWidget(b4)
            box_single.setFixedWidth(200); box_single.setFixedHeight(130)
            main_layout.addWidget(box_single)

        return container

    def create_pk_container(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.pk_stack = QStackedWidget()
        self.pk_stack.currentChanged.connect(self.sync_pk_navigation_buttons)

        chars = ["warrior", "asas", "okcu", "priest", "mage", "kurian"]
        for char_id in chars:
            char_page = self.create_dynamic_page(char_id)
            self.pk_stack.addWidget(char_page)

        layout.addWidget(self.pk_stack)
        return container

    def create_dynamic_page(self, page_id):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(self.create_scanner_box(page_id))

        pk_chars = ["warrior", "asas", "okcu", "priest", "mage", "kurian"]
        if page_id in pk_chars:
            nav_widget = QWidget()
            nav_widget.setFixedHeight(50)
            nav_layout = QHBoxLayout(nav_widget)
            nav_layout.setAlignment(Qt.AlignCenter)
            nav_layout.setSpacing(10)

            group = QButtonGroup(nav_widget)
            group.setExclusive(True)
            self.all_pk_button_groups.append(group)

            char_names = {
                "warrior": "WARRIOR", "asas": "ASSASSIN", "okcu": "ARCHER",
                "priest": "PRIEST", "mage": "MAGICIAN", "kurian": "KURIAN",
            }
            for i, (cid, name) in enumerate(char_names.items()):
                btn = QPushButton(name)
                btn.setCursor(Qt.PointingHandCursor)
                btn.setCheckable(True)
                if cid == page_id:
                    btn.setChecked(True)
                btn.setStyleSheet("""
                    QPushButton { background: #1a1a1a; color: #888; border: 1px solid #333; padding: 8px 15px; border-radius: 4px; font-weight: bold; }
                    QPushButton:hover { color: #fff; border-color: #00e676; }
                    QPushButton:checked { color: #00e676; border: 1px solid #00e676; background: rgba(0, 230, 118, 0.1); }
                """)
                btn.clicked.connect(lambda ch, idx=i: self.pk_stack.setCurrentIndex(idx))
                group.addButton(btn, i)
                nav_layout.addWidget(btn)
            layout.addWidget(nav_widget)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background:transparent;")

        content = QWidget()
        grid = QGridLayout(content)
        grid.setContentsMargins(5, 5, 5, 20)
        grid.setSpacing(20)

        layouts = self.gui_config.get("page_layouts", {})
        modules_to_show = layouts.get(page_id, [])

        r, c = 0, 0
        for mod_key in modules_to_show:
            if mod_key in self.loaded_modules:
                macro_inst, WidgetClass = self.loaded_modules[mod_key]
                cfg = self.config.get(mod_key, {})
                try:
                    w = WidgetClass(self, macro_inst, cfg)
                    grid.addWidget(w, r, c, Qt.AlignTop)
                    c += 1
                    if c >= 3:
                        c = 0; r += 1
                except Exception as _e:
                    log.warning("module widget build fail key=%s: %s", mod_key, _e)

        grid.setRowStretch(r + 1, 1)
        scroll.setWidget(content)
        layout.addWidget(scroll)

        bar = QFrame(); bar.setObjectName("StatusBar")
        bl = QHBoxLayout(bar); bl.setContentsMargins(20, 10, 20, 10)
        btn_save = QPushButton("AYARLARI KAYDET")
        btn_save.setObjectName("BottomSaveBtn")
        btn_save.setFixedSize(160, 35)
        btn_save.clicked.connect(self.save_settings_to_json)
        bl.addWidget(btn_save); bl.addStretch()
        layout.addWidget(bar)

        return page

    def sync_pk_navigation_buttons(self, index):
        for group in self.all_pk_button_groups:
            btn = group.button(index)
            if btn:
                btn.blockSignals(True)
                btn.setChecked(True)
                btn.blockSignals(False)

    # ──────────────────────────────────────────────────────────────────────
    # Dashboard
    # ──────────────────────────────────────────────────────────────────────
    def create_dashboard_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(30)

        header_layout = QHBoxLayout()
        lbl_title = QLabel(f"KONTROL MERKEZİ | {self.username.upper()}")
        lbl_title.setStyleSheet("font-size: 26pt; font-weight: bold; color: #00e676; letter-spacing: 2px;")
        header_layout.addWidget(lbl_title)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        gs = QGridLayout(); gs.setSpacing(20)
        self.bar_cpu, self.lbl_cpu = self.mk_stat(gs, 0, 0, "İŞLEMCİ (CPU)", "#00e676", True)
        self.bar_ram, self.lbl_ram = self.mk_stat(gs, 0, 1, "BELLEK (RAM)", "#2979ff", True)

        uptime_frame = QFrame(objectName="DashCardFrame")
        uptime_layout = QVBoxLayout(uptime_frame)
        uptime_layout.setContentsMargins(15, 15, 15, 15)
        uptime_layout.setSpacing(5)

        lbl_uptime_title = QLabel("⏱ ÇALIŞMA SÜRESİ")
        lbl_uptime_title.setStyleSheet("color:#888; font-weight:bold; font-size: 9pt;")
        uptime_layout.addWidget(lbl_uptime_title)

        self.lbl_up = QLabel("00:00:00")
        self.lbl_up.setStyleSheet("color:#ffea00; font-size:18pt; font-weight:bold; font-family:Consolas;")
        self.lbl_up.setAlignment(Qt.AlignCenter)
        uptime_layout.addWidget(self.lbl_up)

        gs.addWidget(uptime_frame, 0, 2)
        layout.addLayout(gs)

        mid_layout = QHBoxLayout(); mid_layout.setSpacing(20)
        hud_frame = QFrame(); hud_frame.setObjectName("HudBoxFrame")
        hl = QVBoxLayout(hud_frame); hl.setContentsMargins(20, 20, 20, 20); hl.setSpacing(15)

        hud_header = QLabel("👁️ HUD KONTROL PANELİ")
        hud_header.setStyleSheet("color: #00e676; font-size: 12pt; font-weight: bold; border-bottom: 1px solid #333; padding-bottom: 5px;")
        hl.addWidget(hud_header)

        self.lbl_hud_st = QLabel(f"DURUM: {'AKTİF' if self.is_hud_running else 'PASİF'}")
        self.lbl_hud_st.setStyleSheet("color: #ff1744; font-weight: bold; font-size: 11pt; margin-top: 5px;")
        hl.addWidget(self.lbl_hud_st); hl.addStretch()

        b_hud = QPushButton("HUD AÇ / KAPAT"); b_hud.setObjectName("HUDBtn"); b_hud.setMinimumHeight(40); b_hud.clicked.connect(self.toggle_hud)
        b_hud.setStyleSheet("background-color: #00e676; color: white; font-weight: bold; border-radius: 4px;")
        b_set = QPushButton("GÖRÜNÜM AYARLARI"); b_set.setMinimumHeight(35); b_set.clicked.connect(self.open_hud_settings)
        b_set.setStyleSheet("background-color: #222; color: #ccc; border: 1px solid #444; border-radius: 4px;")
        hl.addWidget(b_hud); hl.addWidget(b_set)

        global_frame = self.create_global_settings_widget()

        mid_layout.addWidget(hud_frame, 1)
        mid_layout.addWidget(global_frame, 1)
        layout.addLayout(mid_layout)

        layout.addStretch()
        return page

    def create_global_settings_widget(self):
        frame = QFrame()
        frame.setObjectName("GlobalSettingsFrame")

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        header = QLabel("🔧 SİSTEM & SÜRÜCÜ AYARLARI")
        header.setObjectName("GlobalHeader")
        layout.addWidget(header)

        input_layout = QVBoxLayout()
        input_layout.setSpacing(5)
        lbl_target = QLabel("HEDEF UYGULAMA (EXE):")
        lbl_target.setStyleSheet("color: #aaa; font-size: 9pt;")

        current_exe = self.config["global"].get("target_process", "KnightOnLine.exe")
        self.txt_exe = QLineEdit(current_exe)
        self.txt_exe.setObjectName("GlobalInput")
        self.txt_exe.setPlaceholderText("Örn: KnightOnLine.exe")

        input_layout.addWidget(lbl_target)
        input_layout.addWidget(self.txt_exe)
        layout.addLayout(input_layout)

        id_layout = QHBoxLayout()
        v_kb = QVBoxLayout()
        v_kb.addWidget(QLabel("KLAVYE ID:", styleSheet="color:#aaa; font-size:8pt;"))
        self.lbl_kb_id = QLabel(str(self.config["global"].get("keyboard_id", "—")))
        self.lbl_kb_id.setStyleSheet(
            "background:#000; color:#00e676; padding:8px; border:1px solid #333; "
            "font-family:Consolas; font-size:11pt; font-weight:bold;"
        )
        self.lbl_kb_id.setAlignment(Qt.AlignCenter)
        v_kb.addWidget(self.lbl_kb_id)

        v_ms = QVBoxLayout()
        v_ms.addWidget(QLabel("MOUSE ID:", styleSheet="color:#aaa; font-size:8pt;"))
        self.lbl_ms_id = QLabel(str(self.config["global"].get("mouse_id", "—")))
        self.lbl_ms_id.setStyleSheet(
            "background:#000; color:#00e676; padding:8px; border:1px solid #333; "
            "font-family:Consolas; font-size:11pt; font-weight:bold;"
        )
        self.lbl_ms_id.setAlignment(Qt.AlignCenter)
        v_ms.addWidget(self.lbl_ms_id)

        id_layout.addLayout(v_kb)
        id_layout.addLayout(v_ms)
        layout.addLayout(id_layout)

        btn_id_bul = QPushButton("🔍 KLAVYE / MOUSE ID BUL")
        btn_id_bul.setStyleSheet("""
            QPushButton {
                background-color: #ff9100; color: #000; font-weight: 900;
                padding: 10px; border: 1px solid #ef6c00; border-radius: 6px;
                font-size: 10pt;
            }
            QPushButton:hover { background-color: #ffa726; }
        """)
        btn_id_bul.setCursor(Qt.PointingHandCursor)
        btn_id_bul.clicked.connect(self.open_id_bul_dialog)
        layout.addWidget(btn_id_bul)

        self.chk_filt = QCheckBox("Sadece oyun öndeyken tuş gönder")
        self.chk_filt.setChecked(self.config["global"].get("filter_enabled", False))
        self.chk_filt.setStyleSheet("""
            QCheckBox { color: #ddd; spacing: 8px; }
            QCheckBox::indicator { width: 18px; height: 18px; border: 1px solid #555; background: #222; border-radius: 4px; }
            QCheckBox::indicator:checked { background: #2979ff; border: 1px solid #2979ff; }
        """)
        layout.addWidget(self.chk_filt)

        layout.addStretch()

        btn_glob = QPushButton("AYARLARI KAYDET")
        btn_glob.setObjectName("GlobalSaveBtn")
        btn_glob.setCursor(Qt.PointingHandCursor)
        btn_glob.clicked.connect(self.save_global)
        layout.addWidget(btn_glob)

        return frame

    def save_global(self):
        self.config["global"]["target_process"] = self.txt_exe.text()
        self.config["global"]["filter_enabled"] = self.chk_filt.isChecked()
        self.save_settings_to_json()
        self.log_status("Sistem ayarları kaydedildi.")

    def open_id_bul_dialog(self):
        """EN/TR: Optional device-ID picker. Module is not part of open-source
        package, so we degrade gracefully if it isn't present."""
        try:
            from app.id_bul_dialog import IdBulDialog  # type: ignore
        except Exception:
            QMessageBox.information(
                self, "Bilgi",
                "Cihaz ID bulma dialog'u bu sürümde dahil değildir.\n"
                "settings.json içindeki 'global.keyboard_id' ve 'global.mouse_id' "
                "alanlarını manuel olarak düzenleyin."
            )
            return
        initial_kb = self.config["global"].get("keyboard_id")
        initial_ms = self.config["global"].get("mouse_id")
        dlg = IdBulDialog(parent=self, initial_kb=initial_kb, initial_ms=initial_ms)
        if dlg.exec_():
            try:
                from core.paths import settings_path as _sp
                with open(_sp(), "r", encoding="utf-8") as _f:
                    fresh = json.load(_f)
                self.config["global"].update(fresh.get("global", {}))
            except Exception:
                pass
            try:
                self.lbl_kb_id.setText(str(self.config["global"].get("keyboard_id", "—")))
                self.lbl_ms_id.setText(str(self.config["global"].get("mouse_id", "—")))
            except Exception:
                pass
            self.log_status("Cihaz ID'leri güncellendi.")

    def mk_stat(self, grid, r, c, title, color, is_bar):
        fr = QFrame(objectName="DashCardFrame"); v = QVBoxLayout(fr); v.setContentsMargins(20, 20, 20, 20)
        v.addWidget(QLabel(title, styleSheet="color:#888; font-weight:bold;"))
        if is_bar:
            b = QProgressBar(); b.setRange(0, 100); b.setValue(0); b.setTextVisible(False); b.setFixedHeight(8)
            b.setStyleSheet(f"border:none; background:#222; border-radius:4px; QProgressBar::chunk{{background:{color};}}")
            l = QLabel("0%", styleSheet="color:#fff; font-size:16pt; font-weight:bold; font-family:Consolas;", alignment=Qt.AlignRight)
            v.addWidget(b); v.addWidget(l); grid.addWidget(fr, r, c); return b, l
        else:
            l = QLabel("...", styleSheet=f"color:{color}; font-size:24pt; font-weight:bold; font-family:Consolas;")
            v.addWidget(l); grid.addWidget(fr, r, c); return l

    def update_dashboard_and_colors(self):
        try:
            if self.pages.currentIndex() == 0:
                if HAS_PSUTIL:
                    c = psutil.cpu_percent()
                    r = psutil.virtual_memory().percent
                    if hasattr(self, 'bar_cpu'): self.bar_cpu.setValue(int(c))
                    if hasattr(self, 'lbl_cpu'): self.lbl_cpu.setText(f"%{c}")
                    if hasattr(self, 'bar_ram'): self.bar_ram.setValue(int(r))
                    if hasattr(self, 'lbl_ram'): self.lbl_ram.setText(f"%{r}")

                diff = datetime.datetime.now() - self.app_start_time
                if hasattr(self, 'lbl_up'):
                    self.lbl_up.setText(str(diff).split(".")[0])

            if self.is_hud_running and self.hud_window:
                self.hud_window.update_hud_data(self)
        except RuntimeError:
            pass
        except Exception as e:
            log.error("Dashboard update error: %s", e, exc_info=True)

    # ──────────────────────────────────────────────────────────────────────
    # HUD + misc
    # ──────────────────────────────────────────────────────────────────────
    def toggle_hud(self):
        if not self.hud_window:
            if HUDOverlay:
                self.hud_window = HUDOverlay(self)
            else:
                return
        if self.is_hud_running:
            self.hud_window.hide()
        else:
            self.hud_window.show()
            self.hud_window.update_hud_data(self)
        self.is_hud_running = not self.is_hud_running
        self.lbl_hud_st.setText(f"DURUM: {'AKTİF' if self.is_hud_running else 'PASİF'}")
        self.lbl_hud_st.setStyleSheet(f"color: {'#00ff00' if self.is_hud_running else '#ff1744'}; font-weight: bold; font-size: 11pt; margin-top: 5px;")

    def open_hud_settings(self):
        # FIX: HUD görünüm ayarları akışındaki 3 bug birden duzeltiliyor:
        #   1) Modul yuklenmemisse kullaniciya soyle (sessiz return yerine)
        #   2) Secimler diske yazilsin (save_settings_to_json) — yoksa program
        #      kapaninca kayboluyor
        #   3) HUD penceresi acikken anında refresh — yoksa kullanici tekrar
        #      ac/kapa yapmadan degisikligi gormez
        if not HUDSettingsDialog:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, "HUD Modulu Yok",
                "shared/hud.py yuklenememis — HUD ayarlari acilamiyor.\n"
                "PyQt5 kurulu mu? Import hatalari icin log dosyasini kontrol et."
            )
            return
        d = HUDSettingsDialog(self, self.config["hud_settings"], self.MODULE_REGISTRY)
        if d.exec_():
            self.config["hud_settings"] = d.result_config
            # 1) Diske yaz — kalıcı olsun
            try:
                self.save_settings_to_json()
            except Exception as e:
                log.error("HUD ayarlari kaydedilemedi: %s", e, exc_info=True)
            # 2) Acik HUD'a anında yansıt
            if self.is_hud_running and self.hud_window:
                try:
                    self.hud_window.update_hud_data(self)
                except Exception as e:
                    log.error("HUD live refresh fail: %s", e, exc_info=True)
            # 3) Status bar feedback
            visible_count = len(d.result_config.get("visible_macros", []))
            try:
                self.log_status(f"HUD gorunum ayarlari kaydedildi ({visible_count} makro secildi).")
            except Exception:
                pass

    def nudge_window(self):
        original_pos = self.pos()
        offset = 15
        x, y = original_pos.x(), original_pos.y()
        anim = QPropertyAnimation(self, b"pos")
        anim.setDuration(600)
        anim.setKeyValueAt(0.00, original_pos)
        anim.setKeyValueAt(0.10, QPoint(x + offset, y))
        anim.setKeyValueAt(0.20, QPoint(x - offset, y))
        anim.setKeyValueAt(0.30, QPoint(x, y - offset))
        anim.setKeyValueAt(0.40, QPoint(x, y + offset))
        anim.setKeyValueAt(0.55, QPoint(x + offset // 2, y))
        anim.setKeyValueAt(0.70, QPoint(x - offset // 2, y))
        anim.setKeyValueAt(1.00, original_pos)
        anim.start()
        self._main_nudge_anim = anim

    def switch_page(self, i, b):
        self.pages.setCurrentIndex(i)
        for x in self.sidebar_btns:
            x.setChecked(False)
        b.setChecked(True)
        self.log_status(f"Sayfa: {b.text().strip()}")

    def log_status(self, m):
        if hasattr(self, 'status_bar'):
            self.status_bar.setText(f" {datetime.datetime.now().strftime('%H:%M:%S')} - {m}")
        else:
            log.info("STATUS: %s", m)

    def open_ui_settings(self):
        dlg = InterfaceSettingsDialog(self.gui_config, self.MODULE_REGISTRY, self)
        QTimer.singleShot(100, lambda: get_translation_manager().translate_widget_texts(dlg))

        if dlg.exec_():
            self.gui_config = dlg.config
            self.save_gui_settings()
            new_w = self.gui_config.get("width", 1280)
            new_h = self.gui_config.get("height", 850)
            self.resize(new_w, new_h)

            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Ayarlar Kaydedildi")
            msg_box.setIcon(QMessageBox.Information)
            msg_box.setText(
                "Ayarlarınız başarıyla kaydedildi.\n\n"
                "Sayfa ve modül değişikliklerinin tam olarak uygulanması için "
                "programın yeniden başlatılması gerekmektedir."
            )
            btn_restart = msg_box.addButton("Şimdi Yeniden Başlat", QMessageBox.YesRole)
            msg_box.addButton("Daha Sonra", QMessageBox.NoRole)
            msg_box.exec_()
            if msg_box.clickedButton() == btn_restart:
                self.restart_application()

    def restart_application(self):
        log.info("Restarting application")
        try:
            subprocess.Popen(list(sys.argv))
        except Exception as e:
            log.error("Restart subprocess error: %s", e, exc_info=True)
        QCoreApplication.instance().quit()


# ────────────────────────────────────────────────────────────────────────────
# Entry point
# ────────────────────────────────────────────────────────────────────────────
def run() -> int:
    """EN: Bootstrap Qt and run the main window.
    TR: Qt'yi başlat, ana pencereyi çalıştır."""
    try:
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setApplicationName("SEGE Open Source")
    app.setApplicationVersion(str(CURRENT_VERSION))

    window = SegeMainWindow()
    # Open-source: load macros directly — no auth, no session.
    try:
        window.load_and_init_modules()
    except Exception as e:
        log.error("Module load failed: %s", e, exc_info=True)

    window.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(run())
