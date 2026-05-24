# SEGE Open Source

> Knight Online için açık kaynak makro çatısı — yalnızca eğitim amaçlıdır.

[![Lisans: MIT](https://img.shields.io/badge/lisans-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8+-yellow.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-lightgrey.svg)]()

[🇬🇧 English version](README_EN.md) • [Mimari](docs/ARCHITECTURE.md) • [Modüller](docs/MODULES.md) • [Kurulum](docs/INSTALLATION.md) • [Yeni makro yazma](docs/NEW_MACRO_GUIDE.md)

---

> ⚠️ **Yalnızca eğitim amaçlı.** Çevrimiçi oyunlarda giriş otomasyonu kullanmak Kullanım Koşullarını ihlal edebilir ve hesap banına yol açabilir. Bu proje bir öğrenme kaynağı olarak yayımlanmıştır; nasıl çalıştıracağınızdan tamamen siz sorumlusunuz.

---

## Bu proje neden var?

PyQt5 ile **gerçek dünyada işe yarayan bir Windows otomasyon çatısı** kurmanın açık örneği çok azdır. Çoğu öğretici "merhaba düğme" seviyesinde kalır. SEGE Open Source bunun ötesine geçer:

- **Sekmeli bir GUI** — her biri kendi ayar saklamasına ve canlı durum geri bildirimine sahip 55 bağımsız otomasyon modülünü barındırır.
- **Thread tabanlı makro çalışanları** — Qt ana iş parçacığına saygı duyar ve global kısayol tuşlarıyla başlatılıp durdurulabilir.
- **Kernel modu giriş** — açık kaynak Interception sürücüsü üzerinden; tam ekran DirectX oyunlarda `SendInput`/`keybd_event`'a göre çok daha güvenilirdir ve Python'u Windows kernel sürücüsüne köprülemenin güzel bir örneğidir.
- **Modül kayıt deseni** — yeni bir otomasyon eklemek bir `Macro` sınıfı, bir `Widget` sınıfı ve bir registry girdisi kadar küçüktür.
- **OpenCV ile ekran şablonu eşleştirme** — görüntü güdümlü tetikleyiciler için (HP barı algılama, eşya tanıma, OCR).
- **Şeffaf HUD katmanı** — tam ekran uygulamaların her zaman üstünde kalır.

Yukarıdakilerden herhangi birini öğreniyorsanız, bu kod tabanı okunmak için yazıldı.

---

## Özellikler

Proje 10 sekmeye dağılmış **55 örnek modül** ile gelir:

**Savaşçı (sayfa 1):** `wari_seriskill`, `wari_des`, `wari_kafa`, `wari_kalkan`, `wari_silme`, `firfir`, `crazydes`

**Asas (sayfa 2):** `asas`, `styx`, `otobicak`

**Okçu (sayfa 3):** `threefive`, `icemlr`, `ok72`

**Ortak (Asas/Okçu, sayfa 4):** `minor`, `m20`, `otocure`, `otodef`, `oto_explore`, `birli`

**Akıllı Pot (sayfa 5):** `hpmp`, `otodurat`, `itemchange`

**Self / Özel (sayfa 6):** `self_macro` (1/2/3), `oto_kontrol`, `ototiklama`, `macro_tasarimci` (V5 self editor)

**Priest (sayfa 7):** `priest_goat`, `priest_attack`, `priest_skiller`, `priest_kalkan`, `priest_hpmp_heal`, `priest_party_heal`

**Mage (sayfa 8):** `mage_staff`, `restore`, `mage_remote_farm` (nova), `mage_oto_tp`, `mage_pt_cekme`, `mage_text_tp`

**Kurian (sayfa 9):** `kurian_attack`

**Farm & Yardımcı (sayfa 10):** `autodrop` (loot), `oto_rpr`, `vip_storage`, `clan_storage`, `anti_afk`, `farm`, `pet_macro`

**Genel:** `multi` (multibox), `background_bot`, `upgrade_bot`, `narki`, `usko_otologin`, `notification`, `flood_plus`

Modül başına tek satırlık açıklamalı tablo için [docs/MODULES.md](docs/MODULES.md) dosyasına bakın.

---

## Mimari

```text
┌──────────────────────┐
│ segesource/main.py   │  giriş noktası (çift tık veya `python ...`)
└──────────┬───────────┘
           │
┌──────────▼───────────┐
│ segesource/app/app.py│  PyQt5 ana pencere, sekme UI, hotkey yöneticisi
└──────────┬───────────┘
           │
┌──────────▼───────────┐       ┌─────────────────────────┐
│ segesource/app/      │──────▶│  segesource/macros/*.py │  55 modül
│   modules.py         │       └─────────────────────────┘
└──────────┬───────────┘
           │
┌──────────▼───────────┐       ┌────────────────────┐
│ segesource/          │──────▶│ interception.dll   │  kernel giriş
│   clicksend.py       │       └────────────────────┘
└──────────────────────┘
```

Tam yazı için [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): threading modeli, hotkey yönlendirmesi, ayar saklama, ekran yakalama hattı ve HUD katmanı.

---

## Hızlı başlangıç

```bash
# 1. Klonla
git clone https://github.com/your-org/sege-opensource.git
cd sege-opensource

# 2. Sanal ortam (önerilir)
python -m venv .venv
.\.venv\Scripts\activate

# 3. Bağımlılıklar
pip install -r requirements.txt

# 4. Interception sürücüsünü kur (yönetici, tek sefer, yeniden başlatma gerekir)
#    İndirme: https://github.com/oblitum/Interception
install-interception.exe /install

# 5. Çalıştır:
#    a) Explorer'da segesource/main.py'a çift tıkla
#    b) Komut satırından:
python segesource/main.py
```

`notification` modülü için opsiyonel Tesseract OCR dahil tüm adımlar [docs/INSTALLATION.md](docs/INSTALLATION.md) dosyasındadır.

---

## Yapılandırma

Uygulama **tamamen kendi içinde** — kendi klasörünün DIŞINA hiçbir şey yazmaz. Tüm çalışma zamanı dosyaları kodun yanında, `segesource/` içinde tutulur:

```text
segesource/
├── gui_settings.json   # Tüm UI ayarları + modül başına config
├── segesource.log      # Rolling log dosyası (~5 MB max)
├── buff.json           # Buff zamanlayıcı durumu (bazı makrolar yazar)
├── single.json         # Tek-örnek durumu (opsiyonel)
├── priest_goat_config.json
├── translations.json
├── farm_data/          # Makro başına kalıcı durum (otomatik oluşur)
├── narki_data/
└── login_images/       # Oto-login için kullanıcı şablonları
```

Bu sayede tüm `segesource/` klasörünü zip'leyerek konfigürasyonunu yedekleyebilir, başka makineye taşıyabilirsin — kısayolların ve modül ayarların onunla gelir. `%APPDATA%`, kayıt defteri veya başka bir yerde hiçbir dosya yok.

Ayarlar JSON olarak kodlanır ve başlangıçta yeniden yüklenir. Her modülün kendi üst düzey anahtarı vardır (örn. `hpmp`, `wari_seriskill`). Hotkey bağlamaları `hotkeys` altında bulunur.

---

## Yeni makro ekleme

Registry sözleşmesi bilinçli olarak küçük tutulmuştur. Bir modül eklemek için şunları yazarsınız:

1. `start()` / `stop()` metotlarına sahip bir `Macro` sınıfı.
2. Ayarları açan bir `Widget` sınıfı (`QWidget` alt sınıfı).
3. `app/modules.py` içinde tek bir girdi.

Kod örnekli tam rehber için [docs/NEW_MACRO_GUIDE.md](docs/NEW_MACRO_GUIDE.md).

---

## Proje yapısı

```text
SEGESOURCE/                     # depo kökü — sadece doküman ve metadata
├── README.md, README_EN.md, README_TR.md
├── LICENSE, CONTRIBUTING.md, SECURITY.md
├── requirements.txt, requirements-dev.txt
├── docs/
│   ├── ARCHITECTURE.md
│   ├── MODULES.md
│   ├── INSTALLATION.md
│   └── NEW_MACRO_GUIDE.md
└── segesource/                 # uygulama — her şey burada self-contained
    ├── main.py                 # ⭐ giriş noktası (buna çift tıkla)
    ├── clicksend.py            # Interception klavye/fare sarmalayıcı
    ├── interception.py         # ham sürücü bağlamaları
    ├── consts.py               # girdi event sabitleri
    ├── stroke.py               # sanal tuş kodu yardımcıları
    ├── translation_system.py   # i18n yardımcısı
    ├── translations.json       # çeviri sözlüğü
    ├── sege.ico                # pencere ikonu
    ├── social_*.png            # alt bar sosyal medya ikonları
    ├── icons/                  # makro UI ikonları
    ├── login_images/           # oto-login makrosu için kullanıcı şablonları
    ├── app/
    │   ├── app.py              # MainWindow, sekme barındırma
    │   └── modules.py          # MODULE_REGISTRY + .py modül yükleyici
    ├── core/                   # loglama, yollar, ayarlar, çeviri
    ├── shared/
    │   ├── hud.py              # şeffaf her zaman üstte HUD
    │   └── taramaalani.py      # ekran bölgesi template eşleyici
    ├── macros/                 # 54 .py dosya (55 registry girişi)
    │
    │ # ── runtime dosyalar (otomatik oluşur, .gitignore'da) ──
    ├── gui_settings.json       # tüm UI + modül başına ayarlar
    ├── segesource.log          # rolling log
    ├── buff.json, single.json  # makro kalıcı durumu
    ├── farm_data/, narki_data/ # makro başına durum klasörleri
```

---

## Yasal uyarı

Bu proje **kesinlikle eğitim ve araştırma amaçlı** yayımlanmıştır. Python otomasyon desenlerini, PyQt5 UI mimarisini, threading ve Interception sürücüsü entegrasyonunu örneklendirir. Yazılımı canlı bir çevrimiçi oyuna karşı çalıştırmak, o oyunun Kullanım Koşullarını ihlal edebilir ve hesabın askıya alınmasına veya kalıcı banlanmasına neden olabilir. **Yazarlar ve katkıda bulunanlar; kodun çalıştırılması, değiştirilmesi veya yeniden dağıtılması sonucu doğan hiçbir şeyden sorumlu değildir.** Hiçbir tür garanti verilmez — tam reddiye için [LICENSE](LICENSE) dosyasına bakın.

---

## Lisans

[MIT Lisansı](LICENSE) altında yayımlanmıştır.

---

## Katkıda bulunma

Pull request'ler memnuniyetle karşılanır. Commit kuralları, kod stili ve modül gönderme sözleşmesi için [CONTRIBUTING.md](CONTRIBUTING.md) dosyasını okuyun ve [Davranış Kuralları](CODE_OF_CONDUCT.md) belgemize uyun.

---

## Teşekkürler

- **[Interception](https://github.com/oblitum/Interception)** — Francisco Lopes; modern Windows üzerinde güvenilir oyun otomasyonunu mümkün kılan kernel modu giriş sürücüsü.
- **[PyQt5](https://riverbankcomputing.com/software/pyqt/)** — GUI araç seti.
- **[OpenCV](https://opencv.org/)** — görüntü güdümlü modüllerde şablon eşleştirme.
- **[Pillow](https://python-pillow.org/)**, **[NumPy](https://numpy.org/)**, **[pyautogui](https://pyautogui.readthedocs.io/)**, **[psutil](https://github.com/giampaolo/psutil)**, **[pywin32](https://github.com/mhammond/pywin32)**, **[requests](https://requests.readthedocs.io/)** — etrafındaki ekosistem.
- Yıllar içinde tekniklerini paylaşan tüm Knight Online private server geliştirici topluluğu.
