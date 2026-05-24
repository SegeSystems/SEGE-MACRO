# Architecture — SEGE Open Source

> EN below · TR alttadır

---

## EN

### Overview

SEGE Open Source is a PyQt5 desktop application that demonstrates several
Python patterns worth studying:

- A **plugin-style module registry** that discovers and loads many small
  feature modules at runtime.
- A **cooperative priority gate** for serialising access to a shared
  output device.
- A **Qt thread separation** model where UI work stays on the main thread
  and per-module workers run in their own threads.
- A **template-matching screen scanner** using OpenCV / Pillow.
- An **always-on-top HUD overlay** that doesn't steal focus.

### Layered structure

```text
┌──────────────────────────────────────────────────┐
│              segesource/main.py                  │  entry point
│  (sys.path setup, UTF-8 stdout, crash MessageBox)│
└────────────────────────┬─────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────┐
│              segesource/app/app.py               │  presentation
│  - SegeMainWindow (QMainWindow)                  │
│  - Sidebar + tab pages                           │
│  - Hotkey routing                                │
│  - HUD overlay manager                           │
└────────────────────────┬─────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────┐
│          segesource/app/modules.py               │  module registry
│  - MODULE_REGISTRY (55 entries)                  │
│  - load_all_modules() — importlib loader         │
│  - _apply_priority_patch() — cooperative gate    │
└──────────┬──────────────────────┬────────────────┘
           │                      │
           ▼                      ▼
┌──────────────────┐   ┌──────────────────────────┐
│ segesource/      │   │  segesource/macros/*.py  │
│   clicksend.py   │   │   - 54 macro modules     │
│ (driver wrapper) │   │   - each defines:        │
└────────┬─────────┘   │     class XxxMacro       │
         │             │     class XxxWidget      │
         ▼             └──────────────────────────┘
┌──────────────────┐
│ interception.dll │   kernel-mode input
└──────────────────┘
```

### Threading model

| Thread | Responsibility |
|---|---|
| **Qt main** | All UI work — building tabs, painting, signals/slots. Never blocks. |
| **Per-macro worker** | Each running macro owns a `threading.Thread`. The Macro class's `start()` spawns it; `stop()` joins it. |
| **Hotkey listener** | One global thread polls keyboard state via the Interception driver and dispatches matched bindings to the macros' start/stop hooks. |
| **HUD overlay** | A QTimer ticks on the main thread to refresh visible state. |

The contract: **macros never touch Qt directly**. They publish state by
mutating ordinary Python attributes (`self.hp_current_ratio`, etc.); the
widget's QTimer reads those attributes on the UI thread.

### Module registry contract

Each entry in `MODULE_REGISTRY` declares:

```python
{
    "key":         "wari_seriskill",        # unique id
    "name":        "WARRIOR SERİ SKILL",    # display name
    "page_index":  [1],                     # which tab(s) host the widget
    "module_file": "wari_seriskill",        # → macros/wari_seriskill.py
    "class_name":  "WarriorSkillMacro",     # the Macro class
    "widget_name": "WarriorSkillWidget",    # the Widget class
    "default":     { ... },                 # initial settings dict
    "priority":    1,                       # 0=VIP, 1=normal
}
```

`load_all_modules()` imports each `macros.<module_file>` via `importlib`,
pulls the two classes out, instantiates the Macro, wraps it in priority
attributes, and returns a `dict[key, (macro_instance, WidgetClass)]`.

The UI then walks `page_index` and places the widget on the matching
tab(s).

### Cooperative priority gate

Some macros are marked `priority=0` ("VIP"). When a VIP macro calls
`clicksend.KeyboardDriver.tusbas(...)` it claims a short exclusive
window (`priority_duration`, default 0.20 s). Lower-priority calls busy-
wait — with a 5 ms sleep — until the window expires.

Implementation lives in `app/modules.py:_apply_priority_patch()` and uses
monkey-patching on the driver classes. No kernel locks, no IPC.

### Settings persistence

`core/settings.py` reads/writes a single JSON file
`segesource/gui_settings.json`. Writes are **atomic**: temp file +
`os.replace`. The schema is loose — each module owns a top-level key,
plus global keys like `active_tab`.

### Self-contained data

Everything the app writes lives under `segesource/`:

- `gui_settings.json`
- `segesource.log` (5 MB rotating)
- `buff.json`, `single.json` (per-macro state)
- `farm_data/`, `narki_data/` (auto-created)

Nothing goes to `%APPDATA%`, the registry, or anywhere else. Move the
`segesource/` folder and your full state moves with it.

### What's NOT here (intentionally)

The closed-source build also had: a license server client, heartbeat
thread, encrypted module loading, HWID binding, anti-debug guard, and
telemetry beacons. All of that is removed in this open-source release.
What remains is the application skeleton plus the 55 feature modules.

---

## TR

### Genel bakış

SEGE Open Source, çalışılmaya değer birkaç Python desenini gösteren bir
PyQt5 masaüstü uygulamasıdır:

- Çalışma zamanında çok sayıda küçük özellik modülünü keşfedip yükleyen
  bir **plugin-tarzı modül kayıt defteri**.
- Paylaşılan bir çıkış cihazına erişimi sıraya koyan **kooperatif
  öncelik kapısı**.
- UI işinin ana thread'de, modül başına worker'ların kendi thread'inde
  çalıştığı **Qt thread ayrımı**.
- OpenCV / Pillow kullanan **template eşleşmeli ekran tarayıcı**.
- Odağı çalmayan **her zaman üstte HUD overlay**.

### Katmanlı yapı

```text
┌──────────────────────────────────────────────────┐
│              segesource/main.py                  │  giriş noktası
│  (sys.path ayarı, UTF-8 stdout, çökme MessageBox)│
└────────────────────────┬─────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────┐
│              segesource/app/app.py               │  sunum katmanı
│  - SegeMainWindow (QMainWindow)                  │
│  - Sidebar + sekme sayfaları                     │
│  - Hotkey yönlendirme                            │
│  - HUD overlay yöneticisi                        │
└────────────────────────┬─────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────┐
│          segesource/app/modules.py               │  modül kayıt defteri
│  - MODULE_REGISTRY (55 girdi)                    │
│  - load_all_modules() — importlib yükleyici      │
│  - _apply_priority_patch() — kooperatif kapı     │
└──────────┬──────────────────────┬────────────────┘
           │                      │
           ▼                      ▼
┌──────────────────┐   ┌──────────────────────────┐
│ segesource/      │   │  segesource/macros/*.py  │
│   clicksend.py   │   │   - 54 modül             │
│ (sürücü sarmal.) │   │   - her biri tanımlar:   │
└────────┬─────────┘   │     class XxxMacro       │
         │             │     class XxxWidget      │
         ▼             └──────────────────────────┘
┌──────────────────┐
│ interception.dll │   kernel-mode girdi
└──────────────────┘
```

### Thread modeli

| Thread | Sorumluluk |
|---|---|
| **Qt main** | Tüm UI işi — sekme kurma, çizim, signal/slot. Asla bloklamaz. |
| **Modül başına worker** | Çalışan her modül kendi `threading.Thread`'ine sahiptir. Macro sınıfının `start()`'ı thread'i başlatır, `stop()` join eder. |
| **Hotkey listener** | Interception sürücüsü üzerinden klavye durumunu poll'layan tek global thread, eşleşen kısayolları modül start/stop hook'larına yönlendirir. |
| **HUD overlay** | Görünür durumu yenilemek için main thread'de bir QTimer tıklar. |

Sözleşme: **modüller Qt'ye doğrudan dokunmaz**. Sıradan Python
attribute'larını değiştirerek durum yayınlarlar (`self.hp_current_ratio`
vb.); widget'ın QTimer'ı bu attribute'ları UI thread'inde okur.

### Modül kayıt defteri sözleşmesi

`MODULE_REGISTRY` içindeki her girdi şunları belirtir:

```python
{
    "key":         "wari_seriskill",        # benzersiz id
    "name":        "WARRIOR SERİ SKILL",    # görünen ad
    "page_index":  [1],                     # widget hangi sekmede
    "module_file": "wari_seriskill",        # → macros/wari_seriskill.py
    "class_name":  "WarriorSkillMacro",     # Macro sınıfı
    "widget_name": "WarriorSkillWidget",    # Widget sınıfı
    "default":     { ... },                 # başlangıç ayarları
    "priority":    1,                       # 0=VIP, 1=normal
}
```

`load_all_modules()` her `macros.<module_file>`'ı `importlib` ile import
eder, iki sınıfı çeker, Macro'yu örnekler, öncelik attribute'larıyla
sarar ve `dict[key, (macro_instance, WidgetClass)]` döner.

UI sonra `page_index`'i gezer ve widget'ı eşleşen sekme(ler)e yerleştirir.

### Kooperatif öncelik kapısı

Bazı modüller `priority=0` ("VIP") olarak işaretlidir. Bir VIP modülü
`clicksend.KeyboardDriver.tusbas(...)` çağırdığında kısa bir özel
pencere alır (`priority_duration`, varsayılan 0.20 sn). Düşük öncelikli
çağrılar pencere bitene kadar — 5 ms sleep ile — bekler.

Implementasyon `app/modules.py:_apply_priority_patch()` içinde, sürücü
sınıflarında monkey-patching kullanır. Kernel kilidi yok, IPC yok.

### Ayar kalıcılığı

`core/settings.py` tek bir JSON dosyasını okur/yazar:
`segesource/gui_settings.json`. Yazımlar **atomic**: temp dosya +
`os.replace`. Şema gevşek — her modül üst seviye bir anahtara sahip,
ayrıca `active_tab` gibi global anahtarlar var.

### Self-contained veri

Uygulamanın yazdığı her şey `segesource/` altında:

- `gui_settings.json`
- `segesource.log` (5 MB rotating)
- `buff.json`, `single.json` (modül başına durum)
- `farm_data/`, `narki_data/` (otomatik oluşur)

Hiçbir şey `%APPDATA%`'ya, kayıt defterine veya başka yere gitmez.
`segesource/` klasörünü taşırsın → tüm durumun gelir.

### Burada NE YOK (bilinçli)

Kapalı kaynak sürümde ayrıca şunlar vardı: lisans sunucu istemcisi,
heartbeat thread'i, şifreli modül yükleme, HWID bağlama, anti-debug
guard ve telemetri beacon'ları. Bunların hepsi açık kaynak sürümde
kaldırıldı. Geride kalan: uygulama iskeleti + 55 özellik modülü.
