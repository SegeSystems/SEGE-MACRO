# -*- coding: utf-8 -*-
# ════════════════════════════════════════════════════════════════════════════
# SEGE OPEN SOURCE — Path helpers
# ════════════════════════════════════════════════════════════════════════════
#
# EN: Cross-platform helpers for "where do we write our files?". The app
#     writes settings, logs, and per-module persistent data into a folder
#     in the user's AppData/Local directory (Windows) or ~/.local/share
#     (POSIX). Everything is opt-in — no global state, no env vars consumed.
#
# TR: "Dosyalarımızı nereye yazıyoruz?" sorusunun platform bağımsız cevabı.
#     Uygulama ayarları, log dosyaları ve modül başına kalıcı verileri,
#     Windows'ta AppData/Local, POSIX'te ~/.local/share altındaki bir
#     klasöre yazar. Tüm fonksiyonlar opt-in — global state veya çevre
#     değişkeni kullanılmaz.
# ════════════════════════════════════════════════════════════════════════════

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

APP_NAME = "SegeSource"


@lru_cache(maxsize=1)
def user_data_dir() -> Path:
    """EN: Where runtime data (logs, settings, per-module state) is stored.
        Lives INSIDE the segesource/ package directory so the app is fully
        self-contained: nothing is ever written outside the project folder.
        Move/zip the segesource/ folder and your config moves with it.
    TR: Çalışma zamanı verilerinin (log, ayar, modül başına durum)
        saklandığı yer. segesource/ paket dizininin İÇİNDE — uygulama
        tamamen kendi içinde, proje klasörünün DIŞINA hiçbir şey yazmaz.
        segesource/ klasörünü taşı/zip'le; ayarların onunla gelir."""
    path = project_root() / "segesource"
    path.mkdir(parents=True, exist_ok=True)
    return path


@lru_cache(maxsize=1)
def project_root() -> Path:
    """EN: Return the directory that contains the running source tree.
    TR: Çalışan kaynak ağacın bulunduğu kök dizini döner.

    EN: Useful for locating bundled assets (icons, login_images, etc.).
        Walks up from this file until it finds a `segesource` directory.
    TR: Bundle'lı asset'leri (ikonlar, login_images vb.) bulmak için
        kullanılır. Bu dosyadan yukarı çıkarak `segesource` klasörünü arar.
    """
    here = Path(__file__).resolve()
    for parent in (here, *here.parents):
        if (parent.parent / "segesource").is_dir():
            return parent.parent
    return here.parents[2]  # fallback: <root>/segesource/core/paths.py → <root>


def settings_file() -> Path:
    """EN: Where GUI / per-module persistent settings are stored.
    TR: GUI ve modül başına kalıcı ayarların kaydedildiği dosya."""
    return user_data_dir() / "gui_settings.json"


def log_file() -> Path:
    """EN: Rolling log file path used by `core.logger`.
    TR: `core.logger` tarafından kullanılan rolling log dosya yolu."""
    return user_data_dir() / "segesource.log"


def assets_dir() -> Path:
    """EN: Directory where bundled non-code resources (icons, images) live.
    TR: Bundle'lı kod-dışı kaynakların (ikon, görsel) bulunduğu klasör."""
    return project_root() / "assets"


# ────────────────────────────────────────────────────────────────────────────
# Legacy compatibility shims
# EN: The original (closed-source) client used these function names. We
#     keep them as aliases so ported UI code keeps importing what it
#     already knows. New code should use the names above.
# TR: Orijinal (kapalı kaynak) client bu fonksiyon adlarını kullanıyordu.
#     Port edilmiş UI kodu bildiği adları import etmeye devam etsin diye
#     alias tutuyoruz. Yeni kod yukarıdaki adları kullanmalı.
# ────────────────────────────────────────────────────────────────────────────

def app_dir() -> str:
    """EN: Legacy alias for `user_data_dir()` returning a str.
    TR: `user_data_dir()` için geriye dönük uyumluluk (str döner)."""
    return str(user_data_dir())


def settings_path() -> str:
    """EN: Legacy alias for `settings_file()` returning a str.
    TR: `settings_file()` için geriye dönük uyumluluk (str döner)."""
    return str(settings_file())


def gui_settings_path() -> str:
    """EN: Legacy alias — same target as `settings_path()`.
    TR: Geriye dönük alias — `settings_path()` ile aynı hedef."""
    return str(settings_file())


def buff_json_path() -> str:
    """EN: Path used by some macros to persist buff timer state.
    TR: Bazı makroların buff zamanlayıcı durumunu kaydettiği yol."""
    return str(user_data_dir() / "buff.json")


def single_json_path() -> str:
    """EN: Path used by some macros for single-instance state.
    TR: Bazı makroların tek-örnek durumu için kullandığı yol."""
    return str(user_data_dir() / "single.json")


def macros_enc_dir() -> str:
    """EN: Compatibility stub — the open-source build doesn't ship .enc
        modules; this points to the (.py) macros directory instead.
    TR: Uyumluluk stub'ı — açık kaynak sürüm .enc modülleri içermez;
        bunun yerine (.py) makro klasörünü gösterir."""
    return str(project_root() / "segesource" / "macros")


def resource_path(filename: str) -> str:
    """EN: Resolve a packaged resource (icon, image). Searches, in order:
          1. `<repo>/assets/<filename>`
          2. `<repo>/segesource/<filename>`        (package dir)
          3. `<repo>/segesource/icons/<filename>`  (icons sub-folder)
          4. `<repo>/<filename>`                   (repo root)
        Returns the path of the first match; if none match, returns the
        package-dir candidate so the caller still gets a sensible default.
    TR: Paketli kaynağı (ikon, görsel) çözer. Sırasıyla şuralara bakar:
          1. `<repo>/assets/<filename>`
          2. `<repo>/segesource/<filename>`        (paket klasörü)
          3. `<repo>/segesource/icons/<filename>`  (icons alt klasörü)
          4. `<repo>/<filename>`                   (repo kökü)
        İlk bulunanın yolunu döner; hiçbiri bulunmazsa, çağıran kod için
        makul varsayılan olarak paket-klasörü adayını döner."""
    pkg_dir = project_root() / "segesource"
    candidates = [
        assets_dir() / filename,
        pkg_dir / filename,
        pkg_dir / "icons" / filename,
        project_root() / filename,
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return str(pkg_dir / filename)


def dll_path(dll_name: str) -> str:
    """EN: Compatibility stub for DLL lookup. The open-source build does
        NOT ship core_security.dll; only interception.dll matters and
        the user installs it via the Interception driver setup.
    TR: DLL araması için uyumluluk stub'ı. Açık kaynak sürümde
        core_security.dll YOK; sadece interception.dll önemli ve onu
        kullanıcı Interception sürücü kurulumuyla yükler."""
    return str(project_root() / dll_name)


def normalize_long_path(path: str) -> str:
    """EN: Windows 8.3-short-path → long-path normaliser.
    TR: Windows 8.3 kısa yol → uzun yol normalleyici."""
    if sys.platform != "win32":
        return path
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(1024)
        ctypes.windll.kernel32.GetLongPathNameW(path, buf, 1024)
        return buf.value or path
    except Exception:
        return path


def internal_dir() -> str:
    """EN: Where the running EXE's internal data lives. In source mode
        this is the package directory.
    TR: Çalışan EXE'nin iç verisinin bulunduğu yer. Kaynak modunda
        paket dizinidir."""
    return str(project_root() / "segesource")
