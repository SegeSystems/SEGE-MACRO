# Contributing

Thank you for considering a contribution to **SEGE Open Source**. This document is bilingual: **English first, Turkish after.**

---

## English

### How to contribute

1. **Fork** the repository on GitHub.
2. **Create a feature branch** from `main`:
   ```bash
   git checkout -b feat/my-new-macro
   ```
3. **Make your changes** with focused commits.
4. **Run the test suite** and the linters locally (see _Code style_ below).
5. **Open a pull request** against `main`. Fill in the PR template, link any related issues, and describe what you changed and why.
6. A maintainer will review your PR. Expect feedback — most PRs go through at least one revision round before merging.

### Commit message format (Conventional Commits)

We use [Conventional Commits](https://www.conventionalcommits.org/):

```text
<type>(<optional scope>): <short summary>

<optional body>

<optional footer>
```

Allowed types:

| Type | Use for |
|------|---------|
| `feat` | a new feature or new macro module |
| `fix` | a bug fix |
| `refactor` | code change that neither fixes a bug nor adds a feature |
| `docs` | documentation only |
| `test` | adding or fixing tests |
| `chore` | tooling, CI, dependency updates |
| `perf` | performance improvement |
| `ci` | CI configuration |

Examples:

```text
feat(macros): add mage_remote_farm nova module
fix(drivers): clicksend ignores remapped keys on Win11
docs(architecture): describe hotkey routing
```

### Code style

- **PEP 8** is the baseline.
- Format with **[black](https://black.readthedocs.io/)** (line length 100).
- Lint with **[ruff](https://docs.astral.sh/ruff/)** using the configuration in `pyproject.toml`.
- Type hints are encouraged for new code; we are gradually adopting `mypy` in strict mode.
- Prefer many small files over a few large ones. Target ≤ 400 lines per module, hard limit 800.
- No `print()` for logging — use the project logger from `segesource.core.logging`.
- No mutation of shared state outside the owning macro's worker thread.

Run all checks locally:

```bash
black segesource tests
ruff check segesource tests
pytest -q
```

### Writing tests

- Tests live in `tests/` and are written with **pytest**.
- For PyQt code, use `pytest-qt`'s `qtbot` fixture.
- For driver code, mock `drivers.clicksend` — do **not** call the real Interception driver in CI.
- Aim for ≥ 80% coverage on new modules.

### Adding a new macro module

The full contract is documented in [docs/NEW_MACRO_GUIDE.md](docs/NEW_MACRO_GUIDE.md). In short, every new macro must:

1. Provide a `Macro` class with **`start()`** and **`stop()`** methods.
2. Provide a `Widget` class (subclass of `QWidget`) that surfaces user settings.
3. Persist its settings under its own key in `gui_settings.json`.
4. Register itself in `segesource/app/modules.py` with a unique `key`, `name`, and `page` number.
5. Ship with at least one unit test exercising the macro lifecycle.

PRs that add modules without tests will be sent back.

### Reporting bugs

Open an issue using the **Bug report** template. Include:

- Your Windows version (build number).
- Python version.
- Interception driver version.
- Full traceback if any.
- Steps to reproduce.

### Reporting security issues

Please do **not** open public issues for security vulnerabilities. Email the maintainers privately — see `SECURITY.md` if present, otherwise use the contact address in the repository description.

---

## Türkçe

### Nasıl katkıda bulunulur?

1. Repoyu GitHub üzerinde **fork** edin.
2. `main` üzerinden bir **özellik dalı** açın:
   ```bash
   git checkout -b feat/yeni-makrom
   ```
3. **Değişikliklerinizi** odaklı commit'ler hâlinde yapın.
4. Yerelde **test paketini** ve linter'ları çalıştırın (aşağıdaki _Kod stili_).
5. `main`'e karşı bir **pull request** açın. PR şablonunu doldurun, ilgili issue'ları bağlayın ve neyi neden değiştirdiğinizi anlatın.
6. Bir bakımcı PR'ınızı inceleyecektir. Geri bildirim bekleyin — çoğu PR birleştirilmeden önce en az bir revizyon turu geçirir.

### Commit mesaj formatı (Conventional Commits)

[Conventional Commits](https://www.conventionalcommits.org/) kullanıyoruz:

```text
<tip>(<isteğe bağlı kapsam>): <kısa özet>

<isteğe bağlı gövde>

<isteğe bağlı altbilgi>
```

İzin verilen tipler:

| Tip | Kullanım |
|------|---------|
| `feat` | yeni özellik veya yeni makro modülü |
| `fix` | hata düzeltmesi |
| `refactor` | hata düzeltmeyen ve özellik eklemeyen değişiklik |
| `docs` | yalnızca dokümantasyon |
| `test` | test ekleme veya düzeltme |
| `chore` | araç, CI, bağımlılık güncellemesi |
| `perf` | performans iyileştirmesi |
| `ci` | CI yapılandırması |

Örnekler:

```text
feat(macros): mage_remote_farm nova modülü eklendi
fix(drivers): clicksend Win11'de remap edilmiş tuşları yok sayıyor
docs(architecture): hotkey yönlendirmesi açıklandı
```

### Kod stili

- **PEP 8** temel alınır.
- **[black](https://black.readthedocs.io/)** ile formatlayın (satır uzunluğu 100).
- `pyproject.toml` içindeki yapılandırma ile **[ruff](https://docs.astral.sh/ruff/)** üzerinden lintleyin.
- Yeni kod için tip ipuçları teşvik edilir; strict mod `mypy`'yi kademeli olarak benimsiyoruz.
- Birkaç büyük dosya yerine çok sayıda küçük dosyayı tercih edin. Modül başına ≤ 400 satır hedef, üst sınır 800.
- Loglama için `print()` kullanmayın — `segesource.core.logging` içindeki proje logger'ını kullanın.
- Sahibi olan makronun worker thread'i dışında paylaşılan duruma mutasyon yok.

Tüm kontrolleri yerelde çalıştırın:

```bash
black segesource tests
ruff check segesource tests
pytest -q
```

### Test yazma

- Testler `tests/` altında yaşar ve **pytest** ile yazılır.
- PyQt kodu için `pytest-qt`'nin `qtbot` fikstürünü kullanın.
- Sürücü kodu için `drivers.clicksend`'i mocklayın — CI'da gerçek Interception sürücüsünü çağırmayın.
- Yeni modüllerde ≥ %80 kapsamı hedefleyin.

### Yeni makro modülü ekleme

Tam sözleşme [docs/NEW_MACRO_GUIDE.md](docs/NEW_MACRO_GUIDE.md) içindedir. Kısaca her yeni makronun:

1. **`start()`** ve **`stop()`** metotlarına sahip bir `Macro` sınıfı sağlaması.
2. Kullanıcı ayarlarını sunan bir `Widget` sınıfı (`QWidget` alt sınıfı) sağlaması.
3. Ayarlarını `gui_settings.json` içinde kendi anahtarı altında saklaması.
4. `segesource/app/modules.py` içinde benzersiz bir `key`, `name` ve `page` numarasıyla kendisini kaydetmesi.
5. Makro yaşam döngüsünü test eden en az bir birim test ile gelmesi gerekir.

Testsiz modül ekleyen PR'lar geri gönderilecektir.

### Hata bildirimi

**Bug report** şablonunu kullanarak issue açın. Şunları ekleyin:

- Windows sürümünüz (build numarası).
- Python sürümü.
- Interception sürücü sürümü.
- Varsa tam traceback.
- Yeniden üretme adımları.

### Güvenlik sorunu bildirimi

Güvenlik açıkları için lütfen **açık issue açmayın**. Bakımcılara özel e-posta gönderin — varsa `SECURITY.md`, yoksa repo açıklamasındaki iletişim adresini kullanın.
