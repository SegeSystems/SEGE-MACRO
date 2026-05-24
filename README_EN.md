# SEGE Open Source

> Open-source macro framework for Knight Online — for educational use.

[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8+-yellow.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-lightgrey.svg)]()

[🇹🇷 Türkçe sürüm](README_TR.md) • [Architecture](docs/ARCHITECTURE.md) • [Modules](docs/MODULES.md) • [Installation](docs/INSTALLATION.md) • [Write a new macro](docs/NEW_MACRO_GUIDE.md)

---

> ⚠️ **Educational use only.** Automating input in online games may violate their Terms of Service and result in account bans. This project ships as a learning resource; you are fully responsible for how you run it.

---

## Why does this exist?

There are very few real-world open examples of building a non-trivial **Windows automation framework** with PyQt5. Most tutorials stop at "hello, button". SEGE Open Source goes further:

- A **tabbed GUI** that hosts 55 independent automation modules, each with its own settings persistence and live status feedback.
- **Threaded macro workers** that respect the Qt main thread and can be started/stopped via global hotkeys.
- **Kernel-mode input** via the open-source Interception driver — a much more reliable approach than `SendInput`/`keybd_event` for full-screen DirectX games and a great example of bridging Python with a Windows kernel driver.
- A **module registry pattern** that makes adding a new automation as small as one `Macro` class, one `Widget` class, and one registry entry.
- **Screen template matching** with OpenCV for vision-driven triggers (HP bar detection, item recognition, OCR).
- A transparent **HUD overlay** that always stays on top of full-screen applications.

If you are studying any of the above topics, this codebase is meant to be read.

---

## Features

The project ships with **55 example modules** organized over 10 tabs:

**Warrior (page 1):** `wari_seriskill`, `wari_des`, `wari_kafa`, `wari_kalkan`, `wari_silme`, `firfir`, `crazydes`

**Assassin (page 2):** `asas`, `styx`, `otobicak`

**Archer (page 3):** `threefive`, `icemlr`, `ok72`

**Shared (Assassin/Archer, page 4):** `minor`, `m20`, `otocure`, `otodef`, `oto_explore`, `birli`

**Smart Pot (page 5):** `hpmp`, `otodurat`, `itemchange`

**Self / Custom (page 6):** `self_macro` (1/2/3), `oto_kontrol`, `ototiklama`, `macro_tasarimci` (V5 self editor)

**Priest (page 7):** `priest_goat`, `priest_attack`, `priest_skiller`, `priest_kalkan`, `priest_hpmp_heal`, `priest_party_heal`

**Mage (page 8):** `mage_staff`, `restore`, `mage_remote_farm` (nova), `mage_oto_tp`, `mage_pt_cekme`, `mage_text_tp`

**Kurian (page 9):** `kurian_attack`

**Farm & Utility (page 10):** `autodrop` (loot), `oto_rpr`, `vip_storage`, `clan_storage`, `anti_afk`, `farm`, `pet_macro`

**General:** `multi` (multibox), `background_bot`, `upgrade_bot`, `narki`, `usko_otologin`, `notification`, `flood_plus`

See [docs/MODULES.md](docs/MODULES.md) for a per-module table with one-line descriptions.

---

## Architecture

```text
┌──────────────────────┐
│ segesource/main.py   │  entry point (double-click or `python ...`)
└──────────┬───────────┘
           │
┌──────────▼───────────┐
│ segesource/app/app.py│  PyQt5 main window, tab UI, hotkey manager
└──────────┬───────────┘
           │
┌──────────▼───────────┐       ┌─────────────────────────┐
│ segesource/app/      │──────▶│  segesource/macros/*.py │  55 modules
│   modules.py         │       └─────────────────────────┘
└──────────┬───────────┘
           │
┌──────────▼───────────┐       ┌────────────────────┐
│ segesource/          │──────▶│ interception.dll   │  kernel input
│   clicksend.py       │       └────────────────────┘
└──────────────────────┘
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full write-up: threading model, hotkey routing, settings persistence, screen capture pipeline, and the HUD overlay.

---

## Quick start

```bash
# 1. Clone
git clone https://github.com/your-org/sege-opensource.git
cd sege-opensource

# 2. Virtual environment (recommended)
python -m venv .venv
.\.venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install the Interception driver (admin, one-time, reboot required)
#    Download from: https://github.com/oblitum/Interception
install-interception.exe /install

# 5. Run — pick whichever you prefer:
#    a) Double-click segesource/main.py in Explorer
#    b) From the command line:
python segesource/main.py
```

Full step-by-step instructions including optional Tesseract OCR for the `notification` module are in [docs/INSTALLATION.md](docs/INSTALLATION.md).

---

## Configuration

The app is **fully self-contained** — it never writes outside its own folder. All runtime files live next to the code in `segesource/`:

```text
segesource/
├── gui_settings.json   # All UI settings + per-module config
├── segesource.log      # Rotating log file (~5 MB max)
├── buff.json           # Buff timer state (optional, written by some macros)
├── single.json         # Single-instance state (optional)
├── priest_goat_config.json
├── translations.json
├── farm_data/          # Per-macro persistent state (auto-created)
├── narki_data/
└── login_images/       # User-supplied template images for auto-login
```

This means you can zip the entire `segesource/` folder to back up your configuration, or move it to a new machine and your hotkeys / module settings come with it. Nothing lives in `%APPDATA%`, the registry, or anywhere else.

Settings are JSON-encoded and reloaded on startup. Each module owns a top-level key (e.g. `hpmp`, `wari_seriskill`). Hotkey bindings live under `hotkeys`.

---

## Add a new macro

The registry contract is intentionally minimal. To add a module you write:

1. A `Macro` class with `start()` / `stop()` methods.
2. A `Widget` class (subclass of `QWidget`) that exposes settings.
3. One entry in `app/modules.py`.

A full walkthrough with code is in [docs/NEW_MACRO_GUIDE.md](docs/NEW_MACRO_GUIDE.md).

---

## Project structure

```text
SEGESOURCE/                     # repo root — docs and metadata only
├── README.md, README_EN.md, README_TR.md
├── LICENSE, CONTRIBUTING.md, SECURITY.md
├── requirements.txt, requirements-dev.txt
├── docs/
│   ├── ARCHITECTURE.md
│   ├── MODULES.md
│   ├── INSTALLATION.md
│   └── NEW_MACRO_GUIDE.md
└── segesource/                 # the application — everything self-contained here
    ├── main.py                 # ⭐ entry point (double-click this)
    ├── clicksend.py            # Interception keyboard/mouse wrapper
    ├── interception.py         # raw driver bindings
    ├── consts.py               # input event constants
    ├── stroke.py               # virtual-key code helpers
    ├── translation_system.py   # i18n helper
    ├── translations.json       # translations dict
    ├── sege.ico                # window icon
    ├── social_*.png            # bottom-bar social icons
    ├── icons/                  # macro UI icons
    ├── login_images/           # user-supplied templates for auto-login macro
    ├── app/
    │   ├── app.py              # MainWindow, tab host
    │   └── modules.py          # MODULE_REGISTRY + .py module loader
    ├── core/                   # logging, paths, settings, translation
    ├── shared/
    │   ├── hud.py              # transparent always-on-top HUD
    │   └── taramaalani.py      # screen-region template matcher
    ├── macros/                 # 54 .py files (55 registry entries)
    │
    │ # ── runtime files (auto-created, gitignored) ──
    ├── gui_settings.json       # all UI + per-module settings
    ├── segesource.log          # rolling log
    ├── buff.json, single.json  # macro persistent state
    ├── farm_data/, narki_data/ # per-macro state dirs
└── README_TR.md
```

---

## Disclaimer

This project is published **strictly for educational and research purposes**. It demonstrates Python automation patterns, PyQt5 UI architecture, threading, and integration with the Interception driver. Running this software against a live online game may violate that game's Terms of Service and result in account suspension or permanent bans. **The authors and contributors are not responsible for any consequences of running, modifying, or redistributing this code.** No warranty of any kind is provided — see the [LICENSE](LICENSE) for the full disclaimer.

---

## License

Released under the [MIT License](LICENSE).

---

## Contributing

Pull requests are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) for the commit convention, code style, and module submission contract, and follow our [Code of Conduct](CODE_OF_CONDUCT.md).

---

## Acknowledgments

- **[Interception](https://github.com/oblitum/Interception)** by Francisco Lopes — the kernel-mode input driver that makes reliable game automation possible on modern Windows.
- **[PyQt5](https://riverbankcomputing.com/software/pyqt/)** — the GUI toolkit.
- **[OpenCV](https://opencv.org/)** — used for template matching in vision-driven modules.
- **[Pillow](https://python-pillow.org/)**, **[NumPy](https://numpy.org/)**, **[pyautogui](https://pyautogui.readthedocs.io/)**, **[psutil](https://github.com/giampaolo/psutil)**, **[pywin32](https://github.com/mhammond/pywin32)**, **[requests](https://requests.readthedocs.io/)** — the surrounding ecosystem.
- Everyone in the Knight Online private-server developer community who shared techniques over the years.
