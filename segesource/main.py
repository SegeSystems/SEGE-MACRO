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


def main() -> None:
    """EN: Application entry point.
    TR: Uygulama giriş noktası."""
    _configure_stdout_encoding()

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
