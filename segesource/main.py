# -*- coding: utf-8 -*-
# ════════════════════════════════════════════════════════════════════════════
# SEGE OPEN SOURCE — main.py (TEK giriş noktası / single entry point)
# ════════════════════════════════════════════════════════════════════════════
#
# EN: Double-click this file in Windows Explorer to launch the app.
#     Also runnable from the command line: `python main.py`.
# TR: Windows Explorer'da bu dosyaya çift tıklayarak uygulamayı başlat.
#     Komut satırından da çalışır: `python main.py`.
# ════════════════════════════════════════════════════════════════════════════

from __future__ import annotations

import os
import sys

# EN: This file lives INSIDE the `segesource/` package directory. When
#     double-clicked, sys.path[0] is already this directory, so absolute
#     imports of sibling modules (`core`, `app`, `clicksend`, ...) resolve.
#     We just make sure it's there explicitly so command-line invocations
#     from other directories also work.
# TR: Bu dosya `segesource/` paket dizininin İÇİNDE. Çift tıklayınca
#     sys.path[0] zaten bu dizin oluyor, bu yüzden kardeş modüllerin
#     mutlak import'ları (`core`, `app`, `clicksend`, ...) çözülür.
#     Başka dizinden komut satırı çağrıları da çalışsın diye yine de
#     açıkça ekliyoruz.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)


def _show_fatal_error(message: str) -> None:
    """EN: Show a Windows MessageBox when startup crashes so a double-click
        launch doesn't die silently.
    TR: Çift tıkla başlatınca sessiz ölüm olmasın diye Windows MessageBox
        ile başlatma hatasını göster."""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            None, message, "SEGE - Baslatma Hatasi / Startup Error", 0x10,
        )
    except Exception:
        pass


def _configure_stdout_encoding() -> None:
    """EN: Force UTF-8 on stdout/stderr to survive Windows cp1254 consoles
        (Turkish characters / emoji in print()s).
    TR: Windows cp1254 konsolunda hayatta kalmak için UTF-8 zorla
        (Türkçe karakter / emoji içeren print()'ler için)."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def _is_admin() -> bool:
    """EN: True iff the current process holds Windows admin (elevated) rights.
        Non-Windows platforms return True (no elevation concept used here).
    TR: Mevcut process Windows admin (yükseltilmiş) yetkisine sahip mi?
        Windows dışında True döner (burada yükseltme kavramı yok)."""
    if sys.platform != "win32":
        return True
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _relaunch_as_admin() -> bool:
    """EN: Re-launch THIS script under UAC elevation via ShellExecuteW
        with the "runas" verb. Returns True on successful elevation (caller
        should sys.exit immediately so the elevated child takes over).
        Returns False if the user denied UAC or the call failed — caller
        should continue un-elevated so the app at least starts (the user
        will see that key sending into admin games is blocked).
    TR: Bu scripti UAC yükseltmesi altında ShellExecuteW "runas" verb'ü
        ile yeniden başlatır. Başarılı yükseltmede True döner (çağıran
        hemen sys.exit etmeli; yükseltilmiş çocuk devralır). UAC reddi
        veya hata durumunda False — çağıran yükseltilmemiş devam etmeli
        (uygulama açılsın, kullanıcı admin oyuna tuş gitmediğini görsün)."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        # EN: Quote each argv element so paths with spaces survive intact.
        # TR: Boşluklu yolların bozulmaması için her argv elemanını alıntıla.
        params = " ".join(f'"{a}"' for a in sys.argv)
        rc = ctypes.windll.shell32.ShellExecuteW(
            None,            # parent hwnd / üst pencere yok
            "runas",         # verb → UAC tetikler
            sys.executable,  # python.exe
            params,          # original argv as one string
            None,            # working dir = inherit
            1,               # SW_SHOWNORMAL
        )
        # EN: ShellExecuteW returns > 32 on success; <= 32 means error.
        # TR: ShellExecuteW başarıda > 32 döner; <= 32 hata demektir.
        return int(rc) > 32
    except Exception:
        return False


def _ensure_admin_or_exit() -> None:
    """EN: If not already elevated, spawn an elevated copy and exit the
        current (un-elevated) process. If elevation fails (user clicks
        "No" on UAC) we fall through and continue — the app still starts
        but key sending into admin-protected games will be silently
        blocked by Windows UIPI. The user can opt out of this behaviour
        by setting `SEGE_SKIP_ELEVATION=1` in the environment.
    TR: Henüz yükseltilmemişsek, yükseltilmiş bir kopya açıp şu anki
        (yükseltilmemiş) process'i kapat. Yükseltme başarısız olursa
        (UAC'da "Hayır" tıklanırsa) düşüp devam ediyoruz — uygulama
        açılır ama admin korumalı oyunlara tuş gönderimi Windows UIPI
        tarafından sessizce engellenir. `SEGE_SKIP_ELEVATION=1` ortam
        değişkeniyle bu davranış devre dışı bırakılabilir."""
    if os.environ.get("SEGE_SKIP_ELEVATION"):
        return
    if _is_admin():
        return
    if _relaunch_as_admin():
        # EN: Elevated child took over — quit the un-elevated parent silently.
        # TR: Yükseltilmiş çocuk devraldı — yükseltilmemiş ebeveyni sessizce kapat.
        sys.exit(0)
    # EN: UAC denied / failed — log and let main() continue un-elevated.
    # TR: UAC reddedildi / hata — logla ve main() yükseltilmemiş devam etsin.
    try:
        sys.stderr.write(
            "[SEGE] UAC elevation failed/denied; running un-elevated. "
            "Key sending into admin games will be blocked.\n"
        )
    except Exception:
        pass


def main() -> None:
    """EN: Application entry point.
    TR: Uygulama giriş noktası."""
    _configure_stdout_encoding()
    # EN: Try to acquire admin rights FIRST — Interception kernel-mode
    #     driver itself works either way, but Windows UIPI blocks
    #     synthetic input from a low-IL process targeting a high-IL
    #     process (admin game). Without elevation, tuş gönderimi fails
    #     silently and looks like a config bug.
    # TR: ÖNCE admin yetkisini almayı dene — Interception kernel-mode
    #     sürücüsü zaten çalışır, ama Windows UIPI düşük-bütünlük bir
    #     process'ten yüksek-bütünlük process'e (admin oyun) sentetik
    #     girdiyi engeller. Yükseltme olmadan tuş gönderimi sessizce
    #     başarısız olur ve config hatası gibi görünür.
    _ensure_admin_or_exit()

    # EN: Logger first so any later import-time crash is captured.
    # TR: Önce logger — sonraki import çökmeleri de yakalansın.
    from core.logger import install_crash_handler, setup_logging
    setup_logging()
    install_crash_handler()

    # EN: app.app imports use leading dot relative imports only where they
    #     reference sibling files in the same `app/` subpackage. The
    #     SegeMainWindow class itself is reachable as `app.app.SegeMainWindow`.
    # TR: app.app içindeki import'larda nokta-ile-başlayan göreceli
    #     import'lar sadece aynı `app/` alt paketindeki kardeş dosyalar
    #     için kullanılıyor. SegeMainWindow'a `app.app.SegeMainWindow`
    #     ile ulaşılır.
    from app.app import run as run_app
    sys.exit(run_app())


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:
        import traceback
        tb = traceback.format_exc()
        try:
            sys.stderr.write(tb)
        except Exception:
            pass
        _show_fatal_error(
            f"SEGE basla­tilamadi / failed to start:\n\n"
            f"{type(exc).__name__}: {exc}\n\n{tb}"
        )
        sys.exit(1)
