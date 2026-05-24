# Writing a New Module — SEGE Open Source

> EN below · TR alttadır

---

## EN

Adding a new module is three small steps:

1. Write a `.py` file in `segesource/macros/` with a `Macro` class
   and a `Widget` class.
2. Add one entry to `MODULE_REGISTRY` in `segesource/app/modules.py`.
3. Run the app — your widget appears on the tab you specified.

### Step 1 — The `.py` file

Create `segesource/macros/my_module.py`:

```python
# -*- coding: utf-8 -*-
"""
Example module — demonstrates the contract every macro must follow.
"""

import threading
import time
from typing import Any, Dict

from PyQt5.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
)

import clicksend  # top-level import works because segesource/ is on sys.path


# ── 1. The Macro class ─────────────────────────────────────────────────────

class MyExampleMacro:
    """The headless side: state + start/stop hooks.

    Convention:
        - `__init__` takes NO required arguments.
        - `start()` spawns a worker thread (idempotent).
        - `stop()` signals the thread to exit (idempotent).
        - Public state lives as plain attributes — the Widget's QTimer
          reads them on the UI thread without any locks.
    """

    def __init__(self) -> None:
        self.kb = clicksend.KeyboardDriver()
        self._running = False
        self._thread: threading.Thread | None = None

        # Public state — the widget reads these
        self.is_running: bool = False
        self.tick_count: int = 0

        # User-configurable settings (filled in by Widget)
        self.key_code: int = 0x46  # 'F' by default
        self.delay: float = 0.20

    def update_config(self, config: Dict[str, Any]) -> None:
        """Called by the Widget whenever settings change."""
        self.key_code = config.get("key_code", self.key_code)
        self.delay = config.get("delay", self.delay)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self.is_running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        self.is_running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

    def _loop(self) -> None:
        """Worker thread body — runs on its OWN thread, NEVER touches Qt."""
        while self._running:
            self.kb.tusbas(self.key_code, 0.05)
            self.tick_count += 1
            time.sleep(self.delay)


# ── 2. The Widget class ────────────────────────────────────────────────────

class MyExampleWidget(QFrame):
    """The visible card on the tab. Hosts the on/off button + settings."""

    def __init__(self, parent=None, macro_instance=None, config=None) -> None:
        super().__init__(parent)
        self.macro = macro_instance
        self.config = config or {}

        # Push initial config into the macro
        if self.macro is not None:
            self.macro.update_config(self.config)

        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet("""
            QFrame  { background:#1a1a1a; border:1px solid #333; border-radius:6px; }
            QLabel  { color:#eee; }
            QPushButton {
                background:#00c853; color:black; padding:6px 14px;
                font-weight:bold; border:none; border-radius:4px;
            }
            QPushButton:hover { background:#00e676; }
        """)

        title = QLabel("MY EXAMPLE MACRO")
        title.setStyleSheet("color:#00e676; font-weight:bold;")

        self.btn_toggle = QPushButton("Başlat")
        self.btn_toggle.clicked.connect(self._toggle)

        self.lbl_status = QLabel("PASİF")
        self.lbl_status.setStyleSheet("color:#d32f2f; font-weight:bold;")

        h_top = QHBoxLayout()
        h_top.addWidget(title)
        h_top.addStretch(1)
        h_top.addWidget(self.btn_toggle)

        layout = QVBoxLayout(self)
        layout.addLayout(h_top)
        layout.addWidget(self.lbl_status)

    def _toggle(self) -> None:
        if self.macro is None:
            return
        if self.macro.is_running:
            self.macro.stop()
            self.btn_toggle.setText("Başlat")
            self.lbl_status.setText("PASİF")
            self.lbl_status.setStyleSheet("color:#d32f2f; font-weight:bold;")
        else:
            self.macro.start()
            self.btn_toggle.setText("Durdur")
            self.lbl_status.setText("AKTİF")
            self.lbl_status.setStyleSheet("color:#00e676; font-weight:bold;")
```

### Step 2 — Register it

Open `segesource/app/modules.py` and add to `MODULE_REGISTRY`:

```python
{
    "key":         "my_example",
    "name":        "MY EXAMPLE MACRO",
    "page_index":  [5],                # appears on the "Self / Custom" tab
    "module_file": "my_module",        # → macros/my_module.py
    "class_name":  "MyExampleMacro",
    "widget_name": "MyExampleWidget",
    "default":     {"key_code": 0x46, "delay": 0.20},
    "priority":    1,                  # 1 = normal, 0 = VIP
},
```

### Step 3 — Run

```powershell
python segesource/main.py
```

Your widget appears on tab 5 ("Self / Custom"). Click "Başlat" and the
macro starts. Look in `segesource/segesource.log` for any errors.

### Cooperative priority

Set `"priority": 0` in the registry entry to make your macro a **VIP**.
When a VIP macro sends input, lower-priority macros wait until its
`priority_duration` (default 0.20 s) expires. This prevents critical
actions (e.g. an emergency defence cast) from being interleaved with
non-critical input.

### Hooking into settings persistence

To persist user settings between runs, write into the shared dict that
the main window passes around. The simplest pattern: store everything
inside `self.config`, expose a "save" button in your Widget that writes
to `core.settings.save_settings(...)`. See `core/settings.py` for the
exact API.

### Common pitfalls

- **Never call Qt from the worker thread.** Mutate plain attributes
  and let the Widget's QTimer read them on the main thread.
- **Always provide `stop()` and make it idempotent.** The main window
  calls it during shutdown for every loaded macro.
- **Don't hard-code device IDs.** Use `clicksend.KeyboardDriver()` /
  `MouseDriver()` and let the user pick their device in settings.
- **Don't block in `__init__`.** Heavy work goes in `start()` or
  later — UI build time should stay snappy.

---

## TR

Yeni modül eklemek üç küçük adım:

1. `segesource/macros/` içine `Macro` ve `Widget` sınıfı içeren bir `.py`
   dosyası yaz.
2. `segesource/app/modules.py` içindeki `MODULE_REGISTRY`'e bir girdi ekle.
3. Uygulamayı çalıştır — widget'ın belirttiğin sekmede çıkar.

### Adım 1 — `.py` dosyası

`segesource/macros/my_module.py` oluştur:

```python
# -*- coding: utf-8 -*-
"""Örnek modül — her makronun uyması gereken sözleşmeyi gösterir."""

import threading, time
from typing import Any, Dict

from PyQt5.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
)

import clicksend  # segesource/ sys.path'te olduğu için düz import çalışır


# ── 1. Macro sınıfı ────────────────────────────────────────────────────────

class MyExampleMacro:
    """Başsız taraf: durum + start/stop hook'ları.

    Kurallar:
        - `__init__` zorunlu argüman ALMAZ.
        - `start()` bir worker thread başlatır (idempotent).
        - `stop()` thread'in çıkmasını ister (idempotent).
        - Public durum sıradan attribute olarak yaşar — Widget'ın QTimer'ı
          UI thread'inde okur, kilit gerekmez.
    """

    def __init__(self) -> None:
        self.kb = clicksend.KeyboardDriver()
        self._running = False
        self._thread = None

        # Public durum — widget okur
        self.is_running = False
        self.tick_count = 0

        # Kullanıcı ayarları (Widget doldurur)
        self.key_code = 0x46  # 'F' varsayılan
        self.delay = 0.20

    def update_config(self, config: Dict[str, Any]) -> None:
        """Widget her ayar değişiminde çağırır."""
        self.key_code = config.get("key_code", self.key_code)
        self.delay = config.get("delay", self.delay)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self.is_running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        self.is_running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

    def _loop(self) -> None:
        """Worker thread gövdesi — KENDİ thread'inde, Qt'ye DOKUNMAZ."""
        while self._running:
            self.kb.tusbas(self.key_code, 0.05)
            self.tick_count += 1
            time.sleep(self.delay)


# ── 2. Widget sınıfı ───────────────────────────────────────────────────────

class MyExampleWidget(QFrame):
    """Sekmedeki görünür kart. Aç/kapa butonu + ayarlar."""

    def __init__(self, parent=None, macro_instance=None, config=None) -> None:
        super().__init__(parent)
        self.macro = macro_instance
        self.config = config or {}

        # Başlangıç ayarlarını makroya gönder
        if self.macro is not None:
            self.macro.update_config(self.config)

        self._build_ui()

    def _build_ui(self) -> None:
        self.setStyleSheet("""
            QFrame  { background:#1a1a1a; border:1px solid #333; border-radius:6px; }
            QLabel  { color:#eee; }
            QPushButton {
                background:#00c853; color:black; padding:6px 14px;
                font-weight:bold; border:none; border-radius:4px;
            }
            QPushButton:hover { background:#00e676; }
        """)

        title = QLabel("ÖRNEK MAKRO")
        title.setStyleSheet("color:#00e676; font-weight:bold;")

        self.btn_toggle = QPushButton("Başlat")
        self.btn_toggle.clicked.connect(self._toggle)

        self.lbl_status = QLabel("PASİF")
        self.lbl_status.setStyleSheet("color:#d32f2f; font-weight:bold;")

        h_top = QHBoxLayout()
        h_top.addWidget(title)
        h_top.addStretch(1)
        h_top.addWidget(self.btn_toggle)

        layout = QVBoxLayout(self)
        layout.addLayout(h_top)
        layout.addWidget(self.lbl_status)

    def _toggle(self) -> None:
        if self.macro is None:
            return
        if self.macro.is_running:
            self.macro.stop()
            self.btn_toggle.setText("Başlat")
            self.lbl_status.setText("PASİF")
            self.lbl_status.setStyleSheet("color:#d32f2f; font-weight:bold;")
        else:
            self.macro.start()
            self.btn_toggle.setText("Durdur")
            self.lbl_status.setText("AKTİF")
            self.lbl_status.setStyleSheet("color:#00e676; font-weight:bold;")
```

### Adım 2 — Kaydet

`segesource/app/modules.py` dosyasını aç ve `MODULE_REGISTRY`'e ekle:

```python
{
    "key":         "my_example",
    "name":        "ÖRNEK MAKRO",
    "page_index":  [5],                # "Self / Custom" sekmesinde
    "module_file": "my_module",        # → macros/my_module.py
    "class_name":  "MyExampleMacro",
    "widget_name": "MyExampleWidget",
    "default":     {"key_code": 0x46, "delay": 0.20},
    "priority":    1,                  # 1 = normal, 0 = VIP
},
```

### Adım 3 — Çalıştır

```powershell
python segesource/main.py
```

Widget'ın 5. sekmede ("Self / Custom") görünür. "Başlat"a tıkla, makro
başlar. Hata varsa `segesource/segesource.log`'a bak.

### Kooperatif öncelik

Registry'de `"priority": 0` ile makronu **VIP** yaparsın. VIP makro girdi
gönderdiğinde, düşük öncelikli makrolar `priority_duration` (varsayılan
0.20 sn) bitene kadar bekler. Kritik aksiyonların (örn. acil savunma
büyüsü) önemsiz girdiyle karışmasını engeller.

### Ayar kalıcılığına bağlanma

Kullanıcı ayarlarını çalıştırmalar arasında saklamak için, ana pencerenin
dolaştırdığı paylaşılan dict'e yaz. En basit desen: her şeyi `self.config`
içinde tut, Widget'ında "kaydet" butonu ile `core.settings.save_settings(...)`
çağır. Tam API için `core/settings.py`'a bak.

### Yaygın hatalar

- **Worker thread'inden Qt'ye dokunma.** Düz attribute değiştir; Widget'ın
  QTimer'ı main thread'de okur.
- **Her zaman `stop()` sağla, idempotent olsun.** Ana pencere kapanırken
  yüklü her makro için çağırır.
- **Cihaz ID'lerini sabit kodlama.** `clicksend.KeyboardDriver()` /
  `MouseDriver()` kullan; kullanıcı kendi cihazını seçsin.
- **`__init__`'te bloklama yapma.** Ağır iş `start()`'a veya sonraya —
  UI build hızlı kalsın.
