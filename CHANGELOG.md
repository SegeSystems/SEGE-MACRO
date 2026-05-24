# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-05-22

### Added
- Initial open-source release.
- 55 macro modules covering Warrior, Asas, Archer, Smart Pot, Self/Custom, Priest, Mage, Kurian, Farm, and General categories.
- PyQt5 tabbed main window with custom dark theme, sidebar navigation, HUD overlay.
- Interception driver wrapper (`clicksend.py`) with cooperative priority gate.
- Module registry (`app/modules.py`) — single source of truth for all 55 macros.
- Settings persistence under `segesource/gui_settings.json` (self-contained, never writes outside the project folder).
- Rolling log file (`segesource/segesource.log`, ~5 MB max).
- Bilingual documentation (English + Turkish READMEs, contributing guide).
- GitHub Actions: lint workflow (ruff + black + mypy) + import smoke test CI.
- Issue templates (bug report, feature request, question) and PR template.

### Notes
- Forked from the closed-source SEGE MAKRO commercial product.
- All DRM, license server, heartbeat, telemetry, anti-debug, and HWID-binding code has been removed.
- Educational / research use only — see LICENSE for the full disclaimer.
