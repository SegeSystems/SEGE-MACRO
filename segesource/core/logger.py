# -*- coding: utf-8 -*-
# ════════════════════════════════════════════════════════════════════════════
# SEGE OPEN SOURCE — Logging subsystem
# ════════════════════════════════════════════════════════════════════════════
#
# EN: Thin wrapper around the stdlib `logging` module with three small
#     conveniences:
#       * `setup_logging()` — single idempotent bootstrap; rotating file
#         handler + console handler, UTF-8 everywhere.
#       * `install_crash_handler()` — replaces `sys.excepthook` so that an
#         otherwise-silent crash in a windowed build still lands in the
#         log file.
#       * `get_logger(name)` — drop-in replacement for `logging.getLogger`
#         so users of this module don't have to import the stdlib one.
#       * `log_event()` — structured single-line event helper (key=value).
#
# TR: Standart kütüphane `logging` modülünün ince bir sarmalı; üç küçük
#     kolaylık sağlar:
#       * `setup_logging()` — idempotent kurulum: rolling file handler +
#         konsol handler, her yerde UTF-8.
#       * `install_crash_handler()` — `sys.excepthook`'u değiştirir;
#         pencereli (konsolsuz) sürümde sessizce kaybolacak çökmeler bile
#         log dosyasına düşer.
#       * `get_logger(name)` — `logging.getLogger`'ın drop-in karşılığı;
#         bu modülü kullananlar stdlib'i import etmek zorunda kalmasın.
#       * `log_event()` — yapılandırılmış tek satırlık event yardımcısı.
# ════════════════════════════════════════════════════════════════════════════

from __future__ import annotations

import logging
import sys
import traceback
from logging.handlers import RotatingFileHandler
from typing import Any

from .paths import log_file

_LOG_FORMAT = "[%(asctime)s] [%(levelname)-8s] [%(name)s] %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
_BACKUP_COUNT = 3

_initialised = False


def setup_logging(level: int = logging.INFO) -> None:
    """EN: Configure the root logger. Idempotent — safe to call repeatedly.
    TR: Kök logger'ı yapılandırır. Idempotent — tekrar tekrar çağrılabilir."""
    global _initialised
    if _initialised:
        return

    root = logging.getLogger()
    root.setLevel(level)

    fmt = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # EN: Rolling file handler keeps the last ~20 MB of history on disk.
    #     `delay=True` defers opening the file until the first write — this
    #     prevents Windows file-lock conflicts when multiple processes run
    #     simultaneously (and lets the rotate succeed without races).
    # TR: Rolling file handler diskte son ~20 MB geçmişi tutar.
    #     `delay=True` dosyayı ilk yazmaya kadar açmaz — birden çok process
    #     aynı anda çalıştığında Windows dosya kilidi çakışmalarını önler
    #     (ve rotate'in race olmadan başarmasını sağlar).
    try:
        fh = RotatingFileHandler(
            log_file(),
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
            delay=True,
        )
        fh.setFormatter(fmt)
        fh.setLevel(level)
        root.addHandler(fh)
    except Exception:
        # EN: If the user's AppData is unwritable we still want the console.
        # TR: Kullanıcı AppData'sı yazılamıyorsa bile konsol çalışsın.
        pass

    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    sh.setLevel(level)
    root.addHandler(sh)

    _initialised = True


def install_crash_handler() -> None:
    """EN: Route uncaught exceptions to the log instead of stderr-only.
    TR: Yakalanmamış istisnaları sadece stderr yerine log'a yönlendirir."""
    log = logging.getLogger("crash")

    def _excepthook(exc_type: type, exc_value: BaseException, exc_tb: Any) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            # EN: Don't drown Ctrl+C in error noise.
            # TR: Ctrl+C hata gürültüsünde boğulmasın.
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        log.critical("Uncaught exception:\n%s", tb_text)

    sys.excepthook = _excepthook


def get_logger(name: str) -> logging.Logger:
    """EN: Convenience wrapper around `logging.getLogger`.
    TR: `logging.getLogger` için kısa sarmalayıcı."""
    return logging.getLogger(name)


def log_event(category: str, action: str, level: int = logging.INFO, **fields: Any) -> None:
    """EN: Emit a single-line structured event (`category.action key=value...`).
    TR: Tek satırlık yapılandırılmış event yayar (`kategori.aksiyon key=value...`).

    EN: This is intentionally not JSON — readability in a tail/grep workflow
        beats structured parsing for an end-user macro tool.
    TR: Bilinçli olarak JSON değil — son kullanıcı makro aracında tail/grep
        akışında okunabilirlik, yapılandırılmış parse'tan daha değerli.
    """
    parts = [f"{category}.{action}"]
    for k, v in fields.items():
        parts.append(f"{k}={v}")
    logging.getLogger("event").log(level, " ".join(parts))
