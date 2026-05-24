# -*- coding: utf-8 -*-
# ════════════════════════════════════════════════════════════════════════════
# SEGE OPEN SOURCE — Input driver subpackage
# ════════════════════════════════════════════════════════════════════════════
#
# EN: Wraps the Interception kernel-mode driver (and a pyautogui fallback)
#     behind a tiny, stable API used by every macro: KeyboardDriver and
#     MouseDriver. Macros never touch the driver directly — they receive
#     pre-configured instances.
#
# TR: Interception kernel-mode sürücüsünü (ve pyautogui yedeğini) küçük,
#     stabil bir API arkasına sarmalar: KeyboardDriver ve MouseDriver.
#     Makrolar sürücüye doğrudan dokunmaz — hazır örnekleri alır.
# ════════════════════════════════════════════════════════════════════════════
