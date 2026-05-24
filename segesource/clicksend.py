# -*- coding: utf-8 -*-
# ════════════════════════════════════════════════════════════════════════════
# SEGE OPEN SOURCE — clicksend: keyboard/mouse driver wrapper
# ════════════════════════════════════════════════════════════════════════════
#
# EN:
#   This module exposes `KeyboardDriver` and `MouseDriver` — the two
#   classes every macro instantiates to send synthetic keyboard and mouse
#   input. The implementation backs onto the Interception kernel-mode
#   driver via `interception.py`, which is what lets the synthetic input
#   pass through games that filter SendInput-style input.
#
#   Public API (do not break — 54 macros depend on it):
#     class KeyboardDriver:
#         def tusbas(self, key, delay): ...        # press + release
#         def tusbasilitut(self, key): ...         # press (hold) only
#         def tusbirak(self, key): ...             # release only
#     class MouseDriver:
#         def leftclick(self, sleep, x, y): ...
#         def rightclick(self, sleep, x, y): ...
#         def mouse_left_down(self, x, y): ...
#         def mouse_left_up(self, x, y): ...
#         def mouse_right_down(self, x, y): ...
#         def mouse_right_up(self, x, y): ...
#         def mouse_move(self, x, y): ...
#         def move(self, x, y): ...                # alias of mouse_move
#
#   Differences from the closed-source build:
#     - No DRM permission check
#     - No heartbeat lease gate
#     - No telemetry / distress beacon
#     - Foreground-window filter is OPT-IN via settings.json "filter_enabled"
#       and is fail-OPEN (if it crashes the macro still works)
#
# TR:
#   Bu modül `KeyboardDriver` ve `MouseDriver` sınıflarını sunar — her
#   makro bu iki sınıfı oluşturup sentetik klavye/fare girdisi gönderir.
#   Implementasyon `interception.py` üzerinden Interception kernel-mode
#   sürücüsüne bağlanır; bu da sentetik girdinin SendInput'u filtreleyen
#   oyunlardan geçmesini sağlar.
#
#   Public API (bozma — 54 makro buna bağımlı):
#     yukarıdaki EN bölümünde listelenen aynı sınıf/metodlar.
#
#   Kapalı kaynak sürümden farklar:
#     - DRM izin kontrolü yok
#     - Heartbeat lease kapısı yok
#     - Telemetri / distress beacon yok
#     - Ön plan pencere filtresi settings.json "filter_enabled" ile
#       OPT-IN ve fail-OPEN (crash olursa makro yine çalışır)
# ════════════════════════════════════════════════════════════════════════════

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Dict, Optional

try:
    import pyautogui
    _SCREEN_W, _SCREEN_H = pyautogui.size()
except Exception:
    # EN: Headless test environments don't have a real display; fall back.
    # TR: Headless test ortamında gerçek ekran yok; varsayılan.
    _SCREEN_W, _SCREEN_H = 1920, 1080

from interception import (  # type: ignore  # noqa: F401 — re-exports needed
    interception,
    key_stroke,
    mouse_stroke,
)
from consts import (  # type: ignore  # noqa: F401
    interception_key_state,
    interception_mouse_flag,
    interception_mouse_state,
)

try:
    from core.logger import get_logger
    log = get_logger(__name__)
except Exception:  # pragma: no cover
    import logging
    log = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────────
# Settings cache (used for optional foreground-window filter)
# Settings cache (opsiyonel ön plan pencere filtresi için)
# ────────────────────────────────────────────────────────────────────────────

_cfg_cache: Optional[Dict[str, Any]] = None
_cfg_cache_ts: float = 0.0
_CFG_TTL: float = 5.0  # seconds


def _read_settings_cached() -> Dict[str, Any]:
    """EN: 5-second cache around settings.json reads.
    TR: settings.json okumaları için 5 saniyelik cache."""
    global _cfg_cache, _cfg_cache_ts
    now = time.time()
    if _cfg_cache is not None and (now - _cfg_cache_ts) < _CFG_TTL:
        return _cfg_cache

    data: Dict[str, Any] = {}
    try:
        from core.paths import settings_file
        path = settings_file()
        if path.is_file():
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                data = loaded
    except Exception as e:
        log.warning("settings.json parse fail (clicksend): %s", e)

    _cfg_cache = data
    _cfg_cache_ts = now
    return data


def _is_target_active() -> bool:
    """EN: Optional foreground-window filter. Returns True (allow) unless
        `global.filter_enabled` is set AND the foreground process name
        doesn't match `global.target_process`. Fail-OPEN — any error
        sending = allow, so a broken filter never silently kills macros.
    TR: Opsiyonel ön plan pencere filtresi. `global.filter_enabled`
        ayarı açık DEĞİLSE veya ön plan process'i eşleşiyorsa True
        döner. Fail-OPEN — hata olursa True (izin) döner ki bozuk bir
        filtre makroları sessizce kapatmasın."""
    cfg = _read_settings_cached().get("global", {})
    if not cfg.get("filter_enabled"):
        return True
    target = cfg.get("target_process")
    if not target:
        return True

    if sys.platform != "win32":
        return True  # filter is Windows-only

    try:
        import ctypes
        import psutil  # optional dep
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return True
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return psutil.Process(pid.value).name().lower() == str(target).lower()
    except Exception as e:
        log.debug("_is_target_active fail (open): %s", e)
        return True  # fail-OPEN


# ────────────────────────────────────────────────────────────────────────────
# Device-ID resolution
# ────────────────────────────────────────────────────────────────────────────

_active_kb_id: Optional[int] = None
_active_ms_id: Optional[int] = None


def _resolve_active_id(is_keyboard: bool) -> int:
    """EN: Look up the user-configured device ID for the given input class.
        Falls back to a sensible default (kb=1, mouse=11) so the framework
        boots even if the user hasn't run the device-detection dialog yet.
    TR: Verilen girdi sınıfı için kullanıcı tarafından yapılandırılmış
        cihaz ID'sini döner. Kullanıcı cihaz-tespit diyaloğunu henüz
        çalıştırmadıysa makul varsayılan döner (kb=1, mouse=11)."""
    cfg = _read_settings_cached().get("global", {})
    key = "keyboard_id" if is_keyboard else "mouse_id"
    try:
        v = int(cfg.get(key))  # type: ignore[arg-type]
        if 0 <= v <= 20:
            return v
    except (TypeError, ValueError):
        pass
    return 1 if is_keyboard else 11


def get_active_kb_id() -> int:
    """EN: Resolve (and cache) the active keyboard device ID.
    TR: Aktif klavye cihaz ID'sini çözer (ve cache'ler)."""
    global _active_kb_id
    if _active_kb_id is None:
        _active_kb_id = _resolve_active_id(True)
    return _active_kb_id


def get_active_ms_id() -> int:
    """EN: Resolve (and cache) the active mouse device ID.
    TR: Aktif fare cihaz ID'sini çözer (ve cache'ler)."""
    global _active_ms_id
    if _active_ms_id is None:
        _active_ms_id = _resolve_active_id(False)
    return _active_ms_id


def reload_device_ids() -> None:
    """EN: Drop the cached IDs (call after user changes them in settings).
    TR: Cache'lenen ID'leri sıfırlar (kullanıcı ayarlarda değiştirince çağır)."""
    global _active_kb_id, _active_ms_id, _cfg_cache, _cfg_cache_ts
    _active_kb_id = None
    _active_ms_id = None
    _cfg_cache = None
    _cfg_cache_ts = 0.0


# ────────────────────────────────────────────────────────────────────────────
# Interception context + filtered send
# ────────────────────────────────────────────────────────────────────────────

context = interception()
_original_send = context.send


def secure_send(device: int, stroke: Any) -> None:
    """EN: Filtered wrapper around `context.send`. The only gate left in
        the open-source build is the optional foreground-window filter.
    TR: `context.send` etrafında filtreli sarmalayıcı. Açık kaynak
        sürümde tek kapı: opsiyonel ön plan pencere filtresi."""
    if not _is_target_active():
        return
    _original_send(device, stroke)


# EN: Macros call `context.send(...)` indirectly via the driver classes
#     below, but legacy macros may also hit `context.send` directly.
#     Override here so the foreground filter applies uniformly.
# TR: Makrolar `context.send(...)`'i aşağıdaki sürücü sınıfları üzerinden
#     dolaylı çağırır, ama bazı eski makrolar doğrudan da çağırabilir.
#     Burada override ediyoruz — filtre tek noktadan geçsin.
context.send = secure_send  # type: ignore[assignment]


# ────────────────────────────────────────────────────────────────────────────
# Keyboard driver
# ────────────────────────────────────────────────────────────────────────────

class KeyboardDriver:
    """EN: Synthetic keyboard via Interception.
    TR: Interception üzerinden sentetik klavye."""

    def __init__(self) -> None:
        pass

    @property
    def keyboard(self) -> int:
        """EN: Backward-compat property — live keyboard ID.
        TR: Geriye dönük uyumluluk — canlı klavye ID'si."""
        return get_active_kb_id()

    def tusbas(self, key: int, delay: float) -> None:
        """EN: Press + release a key, with `delay` seconds between events.
        TR: Bir tuşa bas + bırak, aralarında `delay` saniye bekle."""
        kb = get_active_kb_id()
        stroke = key_stroke(key, interception_key_state.INTERCEPTION_KEY_DOWN.value, 0)
        context.send(kb, stroke)
        time.sleep(delay)
        stroke.state = interception_key_state.INTERCEPTION_KEY_UP.value
        context.send(kb, stroke)

    def tusbasilitut(self, key: int) -> None:
        """EN: Press a key and HOLD it (no release).
        TR: Bir tuşa bas ve TUT (bırakma yok)."""
        stroke = key_stroke(key, interception_key_state.INTERCEPTION_KEY_DOWN.value, 0)
        context.send(get_active_kb_id(), stroke)

    def tusbirak(self, key: int) -> None:
        """EN: Release a previously-held key.
        TR: Daha önce basılı tutulan tuşu bırak."""
        stroke = key_stroke(key, interception_key_state.INTERCEPTION_KEY_UP.value, 0)
        context.send(get_active_kb_id(), stroke)


# ────────────────────────────────────────────────────────────────────────────
# Mouse driver
# ────────────────────────────────────────────────────────────────────────────

class MouseDriver:
    """EN: Synthetic mouse via Interception. All coordinates are absolute
        screen-space pixels; we convert to Interception's 0..65535 space.
    TR: Interception üzerinden sentetik fare. Tüm koordinatlar mutlak
        ekran piksel; Interception'ın 0..65535 uzayına dönüştürülür."""

    def __init__(self) -> None:
        pass

    @property
    def mouse(self) -> int:
        """EN: Backward-compat property — live mouse ID.
        TR: Geriye dönük uyumluluk — canlı fare ID'si."""
        return get_active_ms_id()

    @staticmethod
    def _to_abs(x: int, y: int) -> tuple:
        """EN: Convert screen pixel → Interception absolute (0..65535).
        TR: Ekran piksel → Interception mutlak (0..65535) dönüşümü."""
        ax = int((0xFFFF * x) / _SCREEN_W)
        ay = int((0xFFFF * y) / _SCREEN_H)
        return ax, ay

    def _send_button(self, state_down: int, state_up: int,
                     sleep_s: float, x: int, y: int) -> None:
        ax, ay = self._to_abs(x, y)
        flag = interception_mouse_flag.INTERCEPTION_MOUSE_MOVE_ABSOLUTE.value
        s = mouse_stroke(state_down, flag, 0, ax, ay, 0)
        context.send(self.mouse, s)
        time.sleep(sleep_s)
        s.state = state_up
        context.send(self.mouse, s)

    def leftclick(self, sleep: float, x: int, y: int) -> None:
        """EN: Left-click at (x, y) with `sleep` seconds between down/up.
        TR: (x, y)'de sol tık; down/up arası `sleep` saniye."""
        self._send_button(
            interception_mouse_state.INTERCEPTION_MOUSE_LEFT_BUTTON_DOWN.value,
            interception_mouse_state.INTERCEPTION_MOUSE_LEFT_BUTTON_UP.value,
            sleep, x, y,
        )

    def rightclick(self, sleep: float, x: int, y: int) -> None:
        """EN: Right-click at (x, y).
        TR: (x, y)'de sağ tık."""
        self._send_button(
            interception_mouse_state.INTERCEPTION_MOUSE_RIGHT_BUTTON_DOWN.value,
            interception_mouse_state.INTERCEPTION_MOUSE_RIGHT_BUTTON_UP.value,
            sleep, x, y,
        )

    def mouse_left_down(self, x: int, y: int) -> None:
        """EN: Press the left mouse button at (x, y) without releasing.
        TR: (x, y)'de sol tuşa bas (bırakma yok)."""
        ax, ay = self._to_abs(x, y)
        s = mouse_stroke(
            interception_mouse_state.INTERCEPTION_MOUSE_LEFT_BUTTON_DOWN.value,
            interception_mouse_flag.INTERCEPTION_MOUSE_MOVE_ABSOLUTE.value,
            0, ax, ay, 0,
        )
        context.send(self.mouse, s)

    def mouse_left_up(self, x: int, y: int) -> None:
        """EN: Release the left mouse button at (x, y).
        TR: (x, y)'de sol tuşu bırak."""
        ax, ay = self._to_abs(x, y)
        s = mouse_stroke(
            interception_mouse_state.INTERCEPTION_MOUSE_LEFT_BUTTON_UP.value,
            interception_mouse_flag.INTERCEPTION_MOUSE_MOVE_ABSOLUTE.value,
            0, ax, ay, 0,
        )
        context.send(self.mouse, s)

    def mouse_right_down(self, x: int, y: int) -> None:
        """EN: Press the right mouse button at (x, y) without releasing.
        TR: (x, y)'de sağ tuşa bas (bırakma yok)."""
        ax, ay = self._to_abs(x, y)
        s = mouse_stroke(
            interception_mouse_state.INTERCEPTION_MOUSE_RIGHT_BUTTON_DOWN.value,
            interception_mouse_flag.INTERCEPTION_MOUSE_MOVE_ABSOLUTE.value,
            0, ax, ay, 0,
        )
        context.send(self.mouse, s)

    def mouse_right_up(self, x: int, y: int) -> None:
        """EN: Release the right mouse button at (x, y).
        TR: (x, y)'de sağ tuşu bırak."""
        ax, ay = self._to_abs(x, y)
        s = mouse_stroke(
            interception_mouse_state.INTERCEPTION_MOUSE_RIGHT_BUTTON_UP.value,
            interception_mouse_flag.INTERCEPTION_MOUSE_MOVE_ABSOLUTE.value,
            0, ax, ay, 0,
        )
        context.send(self.mouse, s)

    def mouse_move(self, x: int, y: int) -> None:
        """EN: Move the cursor to (x, y) without clicking (drag helper).
        TR: İmleci (x, y)'ye taşı, tıklama yok (sürükleme yardımcısı)."""
        ax, ay = self._to_abs(x, y)
        s = mouse_stroke(
            0,  # state=0 → move only
            interception_mouse_flag.INTERCEPTION_MOUSE_MOVE_ABSOLUTE.value,
            0, ax, ay, 0,
        )
        context.send(self.mouse, s)

    # EN: Some older macros call `.move(x, y)` instead of `.mouse_move(x, y)`.
    # TR: Bazı eski makrolar `.mouse_move` yerine `.move` çağırıyor.
    move = mouse_move
