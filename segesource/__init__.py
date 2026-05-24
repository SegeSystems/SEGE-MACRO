# -*- coding: utf-8 -*-
# ════════════════════════════════════════════════════════════════════════════
# SEGE OPEN SOURCE — Package root
# ════════════════════════════════════════════════════════════════════════════
#
# EN: Top-level package for the SEGE open-source macro framework.
#     Exposes the package version and a `main()` function that callers
#     can use to launch the app: `from segesource import main; main()`.
# TR: SEGE açık kaynak makro çerçevesinin üst seviye paketi.
#     Paket sürümünü ve uygulamayı başlatmak için kullanılabilecek bir
#     `main()` fonksiyonunu dışa açar: `from segesource import main; main()`.
# ════════════════════════════════════════════════════════════════════════════

from __future__ import annotations

__version__ = "0.1.0"
__author__ = "SEGE Open Source Contributors"
__license__ = "MIT"


def main() -> None:
    """EN: Application entry point. Identical behaviour whether you call
        this from `main.py`, from `python -m segesource`, or from any
        external script that imports `segesource`.
    TR: Uygulama giriş noktası. `main.py`'dan, `python -m segesource`'dan
        ya da `segesource`'u import eden harici bir scriptten çağrı —
        davranış aynı."""
    import sys

    # EN: UTF-8 stdout/stderr so Turkish characters survive cp1254 consoles.
    # TR: cp1254 konsolda Türkçe karakterler hayatta kalsın diye UTF-8.
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

    # EN: Logger installed BEFORE any other import so import-time crashes
    #     are captured in the log file too.
    # TR: Logger diğer import'lardan ÖNCE kurulur ki import anında
    #     yaşanan çökmeler de log dosyasına düşsün.
    from .core.logger import install_crash_handler, setup_logging
    setup_logging()
    install_crash_handler()

    from .app.app import run as run_app
    sys.exit(run_app())


__all__ = ["main", "__version__", "__author__", "__license__"]
