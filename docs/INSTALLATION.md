# Installation — SEGE Open Source

> EN below · TR alttadır

---

## EN

### Prerequisites

| Component | Version | Notes |
|---|---|---|
| **OS** | Windows 10 / 11 (64-bit) | The Interception driver is Windows-only. |
| **Python** | 3.8 — 3.12 | Tested most on 3.10 and 3.12. |
| **Interception driver** | Latest | Kernel-mode input driver (free, BSD-licensed). |
| **Visual C++ Runtime** | 2015+ | Usually already installed via Windows Update. |
| **Tesseract OCR** *(optional)* | 5.x | Only for the `notification` module's text watcher. |

### Step 1 — Install Python

1. Download Python from <https://www.python.org/downloads/>.
2. **Important:** during install, tick **"Add Python to PATH"**.
3. Verify in a new terminal:
   ```powershell
   python --version
   pip --version
   ```

### Step 2 — Clone the repository

```powershell
git clone https://github.com/your-org/sege-opensource.git
cd sege-opensource
```

(Or download the ZIP from GitHub and extract.)

### Step 3 — Virtual environment (recommended)

```powershell
python -m venv .venv
.\.venv\Scripts\activate
```

You should see `(.venv)` in your prompt. To deactivate later: `deactivate`.

### Step 4 — Install Python dependencies

```powershell
pip install -r requirements.txt
```

This installs PyQt5, pyautogui, Pillow, numpy, opencv-python-headless,
psutil, pywin32, requests, mss.

For development extras (pytest, ruff, black, mypy):

```powershell
pip install -r requirements-dev.txt
```

### Step 5 — Install the Interception driver

The Interception driver is a kernel-mode driver that allows synthetic
input to pass through games that filter `SendInput`. It is a one-time
install and requires a reboot.

1. Download from <https://github.com/oblitum/Interception/releases>.
2. Extract the ZIP.
3. **Open an Administrator command prompt** in the extracted folder.
4. Run:
   ```powershell
   install-interception.exe /install
   ```
5. **Reboot** Windows.

After the reboot the driver is loaded automatically at startup.

### Step 6 — Place `interception.dll` next to the code

The Python `interception.py` binding needs the runtime DLL alongside it
(or on `PATH`). Easiest: copy `interception.dll` from the driver ZIP into
`segesource/`.

### Step 7 — (Optional) Install Tesseract OCR

Only needed if you plan to use the `notification` module's "number watch"
feature.

1. Download the Windows installer from
   <https://github.com/UB-Mannheim/tesseract/wiki>.
2. Install to the default path: `C:\Program Files\Tesseract-OCR`.
3. Add that folder to `PATH` (the installer can do this for you).
4. Verify:
   ```powershell
   tesseract --version
   ```

### Step 8 — Run

```powershell
python segesource/main.py
```

Or simply **double-click `segesource/main.py`** in Windows Explorer.

The first run creates `segesource/gui_settings.json` and
`segesource/segesource.log` next to the code.

### Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `ModuleNotFoundError: PyQt5` | Dependencies not installed | `pip install -r requirements.txt` |
| `OSError: ... interception.dll` | DLL missing or driver not installed | Re-do Step 5 + Step 6 |
| Window opens but input doesn't reach the game | Wrong device ID | Use the "ID Bul" dialog inside the app to detect your active keyboard/mouse |
| `cp1254 codec can't encode...` | Console encoding | Use Windows Terminal or run via `chcp 65001` first |
| App opens then closes immediately | Startup crash | See `segesource/segesource.log` — also a MessageBox should pop |

---

## TR

### Önkoşullar

| Bileşen | Versiyon | Not |
|---|---|---|
| **İşletim Sistemi** | Windows 10 / 11 (64-bit) | Interception sürücüsü sadece Windows. |
| **Python** | 3.8 — 3.12 | En çok 3.10 ve 3.12'de test edildi. |
| **Interception sürücüsü** | En son | Kernel-mode girdi sürücüsü (ücretsiz, BSD lisanslı). |
| **Visual C++ Runtime** | 2015+ | Genelde Windows Update ile zaten var. |
| **Tesseract OCR** *(opsiyonel)* | 5.x | Sadece `notification` modülünün metin gözcüsü için. |

### Adım 1 — Python kur

1. Python'u indir: <https://www.python.org/downloads/>.
2. **Önemli:** kurulum sırasında **"Add Python to PATH"** seçeneğini İŞARETLE.
3. Yeni bir terminalde doğrula:
   ```powershell
   python --version
   pip --version
   ```

### Adım 2 — Depoyu klonla

```powershell
git clone https://github.com/your-org/sege-opensource.git
cd sege-opensource
```

(Veya GitHub'dan ZIP indir + aç.)

### Adım 3 — Sanal ortam (önerilir)

```powershell
python -m venv .venv
.\.venv\Scripts\activate
```

Prompt'unda `(.venv)` görmen lazım. Sonradan kapatmak için: `deactivate`.

### Adım 4 — Python bağımlılıklarını kur

```powershell
pip install -r requirements.txt
```

Bu komut PyQt5, pyautogui, Pillow, numpy, opencv-python-headless, psutil,
pywin32, requests ve mss'i kurar.

Geliştirme ekstraları için (pytest, ruff, black, mypy):

```powershell
pip install -r requirements-dev.txt
```

### Adım 5 — Interception sürücüsünü kur

Interception, `SendInput` filtreleyen oyunlardan sentetik girdinin
geçmesini sağlayan bir kernel-mode sürücüdür. Tek sefer kurulur, yeniden
başlatma gerekir.

1. İndir: <https://github.com/oblitum/Interception/releases>.
2. ZIP'i aç.
3. Açtığın klasörde **Yönetici komut istemi aç**.
4. Çalıştır:
   ```powershell
   install-interception.exe /install
   ```
5. Windows'u **yeniden başlat**.

Yeniden başlatma sonrası sürücü açılışta otomatik yüklenir.

### Adım 6 — `interception.dll`'i kodun yanına koy

Python `interception.py` binding'i runtime DLL'ini yanında (veya `PATH`'te)
arar. En basit: `interception.dll`'i sürücü ZIP'inden `segesource/` içine kopyala.

### Adım 7 — (Opsiyonel) Tesseract OCR kur

Sadece `notification` modülünün "sayı izleme" özelliğini kullanacaksan
gerekli.

1. Windows yükleyiciyi indir: <https://github.com/UB-Mannheim/tesseract/wiki>.
2. Varsayılan yola kur: `C:\Program Files\Tesseract-OCR`.
3. O klasörü `PATH`'e ekle (kurulum bunu sana yapabilir).
4. Doğrula:
   ```powershell
   tesseract --version
   ```

### Adım 8 — Çalıştır

```powershell
python segesource/main.py
```

Veya Windows Explorer'da **`segesource/main.py`'a çift tıkla**.

İlk çalıştırma `segesource/gui_settings.json` ve `segesource/segesource.log`
dosyalarını kodun yanında oluşturur.

### Sorun giderme

| Belirti | Olası neden | Çözüm |
|---|---|---|
| `ModuleNotFoundError: PyQt5` | Bağımlılıklar kurulmamış | `pip install -r requirements.txt` |
| `OSError: ... interception.dll` | DLL eksik veya sürücü kurulu değil | Adım 5 + Adım 6'yı tekrarla |
| Pencere açılıyor ama girdi oyuna gitmiyor | Yanlış cihaz ID'si | Uygulama içindeki "ID Bul" diyaloğunu kullan |
| `cp1254 codec can't encode...` | Konsol kodlaması | Windows Terminal kullan veya önce `chcp 65001` çalıştır |
| Uygulama açılıp hemen kapanıyor | Başlatma çökmesi | `segesource/segesource.log`'a bak — ayrıca MessageBox çıkar |
