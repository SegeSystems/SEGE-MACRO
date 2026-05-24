# -*- coding: utf-8 -*-
# ════════════════════════════════════════════════════════════════════════════
# SEGE OPEN SOURCE — Settings persistence
# ════════════════════════════════════════════════════════════════════════════
#
# EN: Tiny JSON-on-disk settings store. Per-macro state lives under a
#     namespaced key (`settings["wari_seriskill"] = {...}`); top-level
#     keys are reserved for global app state (`active_page`, `language`).
#
#     Concurrency model: single-process, single-writer. We re-read on load
#     and write atomically (write-to-temp + os.replace) so a crash mid-save
#     can't corrupt the file.
#
# TR: Diskte JSON tutan küçük ayar deposu. Her makronun durumu kendi
#     isim alanı altında (`settings["wari_seriskill"] = {...}`); en üst
#     anahtarlar global uygulama durumu için ayrılmıştır (`active_page`,
#     `language`).
#
#     Eşzamanlılık modeli: tek process, tek yazar. Yüklemede dosyayı
#     yeniden okur, yazarken atomic (geçici dosyaya yaz + os.replace)
#     işlem yapar — kayıt sırasında çökme dosyayı bozamaz.
# ════════════════════════════════════════════════════════════════════════════

from __future__ import annotations

import json
import os
import tempfile
from typing import Any, Dict

from .logger import get_logger
from .paths import settings_file

log = get_logger(__name__)


def load_settings() -> Dict[str, Any]:
    """EN: Read settings.json and return it as a dict (empty if missing).
    TR: settings.json'u okur ve dict döner (yoksa boş)."""
    path = settings_file()
    if not path.is_file():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            log.warning("settings.json kök bir dict değil; sıfırlanıyor")
            return {}
        return data
    except json.JSONDecodeError as e:
        log.error("settings.json bozuk: %s — sıfırdan başlanıyor", e)
        return {}
    except OSError as e:
        log.error("settings.json okunamadı: %s", e)
        return {}


def save_settings(data: Dict[str, Any]) -> bool:
    """EN: Persist `data` to settings.json atomically. Returns True on success.
    TR: `data`'yı settings.json'a atomic olarak yazar. Başarıda True döner."""
    target = settings_file()
    target.parent.mkdir(parents=True, exist_ok=True)

    # EN: Write into a sibling temp file, then atomically rename.
    # TR: Aynı klasörde geçici dosyaya yaz, sonra atomic rename.
    fd, tmp_path = tempfile.mkstemp(
        prefix=".gui_settings.", suffix=".tmp", dir=str(target.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                # EN: fsync can fail on network drives; not fatal.
                # TR: Ağ sürücülerinde fsync düşebilir; ölümcül değil.
                pass
        os.replace(tmp_path, target)
        return True
    except Exception as e:
        log.error("settings.json yazılamadı: %s", e)
        # EN: Clean up the leftover temp file on failure.
        # TR: Başarısızlıkta artık temp dosyayı temizle.
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        return False


def get_module_state(settings: Dict[str, Any], module_key: str) -> Dict[str, Any]:
    """EN: Return the per-module sub-dict, creating it if needed.
    TR: Modüle özel alt-dict'i döner, yoksa oluşturur."""
    bucket = settings.setdefault(module_key, {})
    if not isinstance(bucket, dict):
        bucket = {}
        settings[module_key] = bucket
    return bucket
