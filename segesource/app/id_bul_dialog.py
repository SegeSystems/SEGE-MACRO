# -*- coding: utf-8 -*-
"""
SEGE - Cihaz ID Bul Dialog
==========================
Ana programın içine entegre edilmiş id_bul.py varyantı. Standalone EXE'den
farklı olarak:
  - clicksend.context'ini paylaşır (yeni interception açmaz, çakışma yok)
  - "Kaydet & Uygula" → settings.json + clicksend.reload_device_ids()
  - Program restart gerekmiyor; sonraki stroke yeni ID ile gider

Kullanım: app.py'den show_id_bul_dialog(parent) ile çağırılır.
"""
import re
import json
import os
import logging

log = logging.getLogger(__name__)

from PyQt5.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication, QDialog, QWidget, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QGroupBox, QListWidget, QListWidgetItem,
    QFrame, QSizePolicy, QMessageBox
)

from interception import interception, interception_filter_key_state, \
    interception_filter_mouse_state, interception_mouse_state
# AUDIT-2026-05 Round 8 FIX: consts.py'da MAX_DEVICES yok (Nuitka obf da
# soyleyebilir). interception.py module-level MAX_DEVICES = 20 tanimliyor —
# oradan al. Fallback: 20 default.
try:
    from interception import MAX_DEVICES
except Exception:
    try:
        from consts import MAX_DEVICES
    except Exception:
        # AUDIT-2026-05 Round 9: fallback log
        log.warning("MAX_DEVICES import fail, fallback to 20")
        MAX_DEVICES = 20

# clicksend.context paylaş — yeni interception() açma!
try:
    from clicksend import context as _shared_context, reload_device_ids
except Exception:
    _shared_context = None
    reload_device_ids = None

try:
    from core.paths import settings_path as _settings_path
    _SETTINGS_FILE = _settings_path()
except Exception:
    _SETTINGS_FILE = "settings.json"


# ---------------- Helpers ----------------
def _clean_hwid(raw):
    try:
        return raw.replace("\x00", "").strip() if raw else ""
    except Exception:
        return ""


def _get_hwid(ctx, dev_id: int) -> str:
    try:
        return _clean_hwid(ctx.get_HWID(dev_id))
    except Exception:
        return ""


def _extract_vid_pid(hwid: str) -> str:
    if not hwid:
        return "VID/PID ?"
    m_vid = re.search(r"VID_([0-9A-Fa-f]{4})", hwid)
    m_pid = re.search(r"PID_([0-9A-Fa-f]{4})", hwid)
    if m_vid and m_pid:
        return f"VID_{m_vid.group(1).upper()} PID_{m_pid.group(1).upper()}"
    return "VID/PID ?"


def _try_registry_desc(hwid: str) -> str:
    try:
        import winreg
        if not hwid:
            return "?"
        parts = hwid.split("\\")
        if len(parts) < 3:
            return "?"
        bus, dev, inst = parts[0], parts[1], parts[2]
        key_path = rf"SYSTEM\CurrentControlSet\Enum\{bus}\{dev}\{inst}"

        def q(name):
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as k:
                    v, _ = winreg.QueryValueEx(k, name)
                    return v
            except Exception:
                return None

        for field in ("FriendlyName", "DeviceDesc", "Mfg"):
            v = q(field)
            if isinstance(v, str) and v.strip():
                return v.strip()
        return "?"
    except Exception:
        return "?"


def _enumerate_devices(ctx):
    kbs, ms = [], []
    hwid_map = {}
    for i in range(MAX_DEVICES):
        h = _get_hwid(ctx, i)
        if h:
            hwid_map.setdefault(h, []).append(i)

    for i in range(MAX_DEVICES):
        if interception.is_keyboard(i):
            hwid = _get_hwid(ctx, i)
            dup = " (dup)" if hwid and len(hwid_map.get(hwid, [])) > 1 else ""
            vidpid = _extract_vid_pid(hwid)
            desc = _try_registry_desc(hwid)
            short = hwid if len(hwid) <= 62 else hwid[:62] + "..."
            text = f"Device {i} — {vidpid}{dup}\n{desc}\n{short}"
            kbs.append((i, hwid, text))
        elif interception.is_mouse(i):
            hwid = _get_hwid(ctx, i)
            dup = " (dup)" if hwid and len(hwid_map.get(hwid, [])) > 1 else ""
            vidpid = _extract_vid_pid(hwid)
            desc = _try_registry_desc(hwid)
            short = hwid if len(hwid) <= 62 else hwid[:62] + "..."
            text = f"Device {i} — {vidpid}{dup}\n{desc}\n{short}"
            ms.append((i, hwid, text))
    return kbs, ms


_STYLE = """
QDialog { background-color: #121212; color: #e0e0e0; font-family: "Segoe UI"; font-size: 10pt; }
QGroupBox { border: 1px solid #2b2b2b; border-radius: 10px; margin-top: 12px;
            background-color: #151515; font-weight: 700; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; top: -6px; padding: 0 6px;
                   color: #00e676; background-color: #151515; }
QListWidget { background-color: #0f0f0f; border: 1px solid #2b2b2b; border-radius: 8px;
              padding: 8px; font-family: "Consolas"; font-size: 9.5pt; }
QListWidget::item { padding: 10px; margin-bottom: 6px; border-radius: 8px;
                    border: 1px solid transparent; }
QListWidget::item:selected { background-color: rgba(0,230,118,0.12); border: 1px solid #00e676; }
#HeaderBar { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #070707, stop:1 #1b1b1b);
             border-bottom: 2px solid #00e676; }
#HeaderTitle { color: #00e676; font-size: 13pt; font-weight: 900; }
#HeaderSub { color: #8a8a8a; font-size: 9.5pt; }
QPushButton { background-color: #1f1f1f; border: 1px solid #2b2b2b; border-radius: 8px;
              padding: 10px; font-weight: 800; color: #e0e0e0; }
QPushButton:hover { border-color: #00e676; }
QPushButton:disabled { color:#666; border-color:#222; }
QPushButton#GreenBtn { background-color: #00e676; color: #000; border: 1px solid #00c853; }
QPushButton#BlueBtn  { background-color: #2979ff; color: #fff; border: 1px solid #1565c0; }
QPushButton#OrangeBtn{ background-color: #ff9100; color: #000; border: 1px solid #ef6c00; }
#PickFrame { background-color: #0b0b0b; border: 1px solid #1f1f1f; border-radius: 10px; }
#PickTitle { color: #00e676; font-size: 11pt; font-weight: 900; }
#PickLine  { color: #d7d7d7; font-family: "Consolas"; font-size: 10pt; }
#StatusLine{ background-color: #0b0b0b; border: 1px solid #1f1f1f; border-radius: 8px;
             padding: 8px 10px; color: #9a9a9a; font-family: "Consolas"; }
"""


# ---------------- Detect Thread ----------------
class _DetectThread(QThread):
    info = pyqtSignal(str)
    detected = pyqtSignal(str, int)

    def __init__(self, ctx, mode: str):
        super().__init__()
        self._ctx = ctx
        self.mode = mode
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        ctx = self._ctx
        if ctx is None:
            self.info.emit("HATA: interception context yok.")
            return
        try:
            try:
                ctx.set_filter(interception.is_keyboard, 0)
                ctx.set_filter(interception.is_mouse, 0)
            except Exception as _e:
                # AUDIT-2026-05 Round 9: filter reset hatasi sessiz kalmasin
                self.info.emit(f"HATA: filter reset basarisiz: {_e}")
                return

            if self.mode == "keyboard":
                ctx.set_filter(
                    interception.is_keyboard,
                    interception_filter_key_state.INTERCEPTION_FILTER_KEY_DOWN.value
                )
                self.info.emit("⌨️ Dinleniyor... GERÇEK klavyeden 1 tuşa bas.")
            else:
                ctx.set_filter(
                    interception.is_mouse,
                    interception_filter_mouse_state.INTERCEPTION_FILTER_MOUSE_LEFT_BUTTON_DOWN.value
                )
                self.info.emit("🖱️ Dinleniyor... GERÇEK mouse ile 1 kez SOL TIK yap.")

            while not self._stop:
                dev = ctx.wait(milliseconds=200)
                if not dev:
                    continue
                try:
                    stroke = ctx.receive(dev)
                except Exception:
                    continue

                # Input'u yutmasın diye geri gönder (raw send — secure_send override etmiş olabilir)
                try:
                    if hasattr(ctx, "_orig_send"):
                        ctx._orig_send(dev, stroke)
                    else:
                        ctx.send(dev, stroke)
                except Exception:
                    pass

                if self.mode == "keyboard":
                    if interception.is_keyboard(dev):
                        self.detected.emit("keyboard", dev)
                        return
                else:
                    if interception.is_mouse(dev):
                        try:
                            if hasattr(stroke, "state"):
                                if int(stroke.state) != int(interception_mouse_state.INTERCEPTION_MOUSE_LEFT_BUTTON_DOWN.value):
                                    continue
                        except Exception:
                            pass
                        self.detected.emit("mouse", dev)
                        return
        finally:
            try:
                ctx.set_filter(interception.is_keyboard, 0)
                ctx.set_filter(interception.is_mouse, 0)
            except Exception:
                pass


# ---------------- Dialog ----------------
class IdBulDialog(QDialog):
    """Cihaz ID Bul Dialog — ana programa entegre."""

    def __init__(self, parent=None, initial_kb=None, initial_ms=None):
        super().__init__(parent)
        self.setWindowTitle("SEGE — Cihaz ID Bul")
        self.setMinimumSize(900, 600)
        self.setStyleSheet(_STYLE)

        # paylaşılan context
        self._ctx = _shared_context
        if self._ctx is None:
            QMessageBox.critical(self, "Hata",
                                 "Interception context açılamadı.\n"
                                 "Sürücü kurulu mu, lghub_agent.exe yönetici olarak mı çalışıyor?")

        self.selected_keyboard_id = initial_kb
        self.selected_mouse_id = initial_ms
        self.det_thread = None

        self._build_ui()
        self.refresh_lists()
        self._update_pick_box()

    # ----- UI -----
    def _build_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(12, 12, 12, 12)
        main.setSpacing(10)

        # Header
        header = QFrame()
        header.setObjectName("HeaderBar")
        header.setFixedHeight(58)
        h = QHBoxLayout(header)
        h.setContentsMargins(16, 8, 16, 8)
        h.setSpacing(12)
        tb = QVBoxLayout()
        lt = QLabel("Cihaz ID Bul")
        lt.setObjectName("HeaderTitle")
        ls = QLabel("Test ile dinleyip gerçek klavye/mouse ID'sini yakala. Restart yok.")
        ls.setObjectName("HeaderSub")
        tb.addWidget(lt)
        tb.addWidget(ls)
        h.addLayout(tb)
        h.addStretch(1)
        self.btn_refresh = QPushButton("🔄 Yenile")
        self.btn_refresh.setObjectName("BlueBtn")
        self.btn_refresh.setCursor(Qt.PointingHandCursor)
        self.btn_refresh.clicked.connect(self.refresh_lists)
        h.addWidget(self.btn_refresh)
        main.addWidget(header)

        # Panels
        row = QHBoxLayout()
        row.setSpacing(10)

        gb_kb = QGroupBox("⌨️ Klavyeler")
        kbl = QVBoxLayout(gb_kb)
        self.kb_list = QListWidget()
        self.kb_list.setWordWrap(True)
        # R13: signal bir kez bagla — refresh_lists her cagrildiginda
        # yeniden bind edilirse handler N kez patlardi.
        self.kb_list.itemClicked.connect(self._on_kb_clicked)
        kbl.addWidget(self.kb_list, 1)
        self.btn_kb = QPushButton("⌨️ Klavye Test (1 tuşa bas)")
        self.btn_kb.setObjectName("BlueBtn")
        self.btn_kb.setCursor(Qt.PointingHandCursor)
        self.btn_kb.clicked.connect(lambda: self.start_detect("keyboard"))
        kbl.addWidget(self.btn_kb)

        gb_ms = QGroupBox("🖱️ Mouse'lar")
        msl = QVBoxLayout(gb_ms)
        self.ms_list = QListWidget()
        self.ms_list.setWordWrap(True)
        # R13: signal bir kez bagla (yukaridaki kb_list ile ayni gerekce).
        self.ms_list.itemClicked.connect(self._on_ms_clicked)
        msl.addWidget(self.ms_list, 1)
        self.btn_ms = QPushButton("🖱️ Sol Tık Test (1 kez tıkla)")
        self.btn_ms.setObjectName("GreenBtn")
        self.btn_ms.setCursor(Qt.PointingHandCursor)
        self.btn_ms.clicked.connect(lambda: self.start_detect("mouse"))
        msl.addWidget(self.btn_ms)

        row.addWidget(gb_kb, 1)
        row.addWidget(gb_ms, 1)
        main.addLayout(row, 1)

        # Pick + Action
        bot = QHBoxLayout()

        pick = QFrame()
        pick.setObjectName("PickFrame")
        pl = QVBoxLayout(pick)
        pl.setContentsMargins(14, 12, 14, 12)
        pt = QLabel("✅ Seçili Cihazlar")
        pt.setObjectName("PickTitle")
        pl.addWidget(pt)
        self.lbl_pick_kb = QLabel("Klavye: —")
        self.lbl_pick_kb.setObjectName("PickLine")
        self.lbl_pick_ms = QLabel("Mouse : —")
        self.lbl_pick_ms.setObjectName("PickLine")
        pl.addWidget(self.lbl_pick_kb)
        pl.addWidget(self.lbl_pick_ms)
        pl.addStretch(1)
        bot.addWidget(pick, 1)

        # Action col
        ac = QVBoxLayout()
        ac.setSpacing(8)
        self.btn_apply = QPushButton("💾 KAYDET & UYGULA")
        self.btn_apply.setObjectName("OrangeBtn")
        self.btn_apply.setMinimumHeight(48)
        self.btn_apply.setCursor(Qt.PointingHandCursor)
        self.btn_apply.clicked.connect(self.save_and_apply)
        ac.addWidget(self.btn_apply)

        # AUDIT-2026-05 Round 8 DIAGNOSTIC: "Test Tus" butonu — kaydettikten
        # sonra gercek driver'i (secure_send dahil) test eder, drop sebebini
        # raporlar. User "tus gitmiyor" derken hangi gate'in blokladigi
        # belli olur.
        self.btn_test_key = QPushButton("⌨️ Test: 'A' tusu gonder")
        self.btn_test_key.setCursor(Qt.PointingHandCursor)
        self.btn_test_key.setStyleSheet(
            "QPushButton{background:#2979ff;color:#fff;padding:8px;"
            "border:1px solid #1565c0;border-radius:6px;}"
            "QPushButton:hover{background:#448aff;}"
        )
        self.btn_test_key.clicked.connect(self.test_send_key)
        ac.addWidget(self.btn_test_key)

        btn_close = QPushButton("Kapat")
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.clicked.connect(self.reject)
        ac.addWidget(btn_close)
        ac.addStretch(1)
        bot.addLayout(ac, 1)

        main.addLayout(bot)

        self.status = QLabel("Hazır.")
        self.status.setObjectName("StatusLine")
        self.status.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        main.addWidget(self.status)

    # ----- Logic -----
    def _update_pick_box(self):
        self.lbl_pick_kb.setText(
            "Klavye: —" if self.selected_keyboard_id is None
            else f"Klavye: Device {self.selected_keyboard_id}"
        )
        self.lbl_pick_ms.setText(
            "Mouse : —" if self.selected_mouse_id is None
            else f"Mouse : Device {self.selected_mouse_id}"
        )

    def set_busy(self, busy):
        for w in (self.btn_refresh, self.btn_kb, self.btn_ms,
                  self.btn_apply, self.kb_list, self.ms_list):
            w.setEnabled(not busy)

    def refresh_lists(self):
        if self._ctx is None:
            # AUDIT-2026-05 Round 9: sessizce return yerine status hint
            self.status.setText(
                "⚠ Interception context yok — driver yuklu ve admin olarak "
                "calistigindan emin ol."
            )
            return
        keep_kb = self.selected_keyboard_id
        keep_ms = self.selected_mouse_id
        self.kb_list.clear()
        self.ms_list.clear()
        kbs, ms = _enumerate_devices(self._ctx)
        for dev_id, hwid, text in kbs:
            it = QListWidgetItem(text)
            it.setData(Qt.UserRole, dev_id)
            self.kb_list.addItem(it)
        for dev_id, hwid, text in ms:
            it = QListWidgetItem(text)
            it.setData(Qt.UserRole, dev_id)
            self.ms_list.addItem(it)
        if keep_kb is not None:
            self._highlight(self.kb_list, keep_kb)
        if keep_ms is not None:
            self._highlight(self.ms_list, keep_ms)
        # R13: itemClicked connect _build_ui'a tasindi — refresh_lists her
        # cagrildiginda bind edilmiyor, handler 1 kez tetiklenir.
        self.status.setText(f"Hazır. Taranan: {len(kbs)} klavye, {len(ms)} mouse")
        self._update_pick_box()

    def _on_kb_clicked(self, item):
        self.selected_keyboard_id = item.data(Qt.UserRole)
        self._update_pick_box()
        self.status.setText(f"Klavye manuel secildi: Device {self.selected_keyboard_id}")

    def _on_ms_clicked(self, item):
        self.selected_mouse_id = item.data(Qt.UserRole)
        self._update_pick_box()
        self.status.setText(f"Mouse manuel secildi: Device {self.selected_mouse_id}")

    def start_detect(self, mode):
        if self._ctx is None:
            QMessageBox.warning(self, "Hata", "Interception context yok.")
            return
        if self.det_thread and self.det_thread.isRunning():
            return
        self.set_busy(True)
        self.status.setText("Dinleme başladı...")
        self.det_thread = _DetectThread(self._ctx, mode)
        self.det_thread.info.connect(self.status.setText)
        self.det_thread.detected.connect(self.on_detected)
        self.det_thread.finished.connect(lambda: self.set_busy(False))
        self.det_thread.start()

    def on_detected(self, mode, dev_id):
        if mode == "keyboard":
            self.selected_keyboard_id = dev_id
            self._highlight(self.kb_list, dev_id)
            self.status.setText(f"✅ Klavye bulundu: Device {dev_id}")
        else:
            self.selected_mouse_id = dev_id
            self._highlight(self.ms_list, dev_id)
            self.status.setText(f"✅ Mouse bulundu: Device {dev_id}")
        self._update_pick_box()

    def _highlight(self, lst, dev_id):
        for i in range(lst.count()):
            it = lst.item(i)
            if it.data(Qt.UserRole) == dev_id:
                lst.setCurrentRow(i)
                lst.scrollToItem(it)
                return

    def save_and_apply(self):
        if self.selected_keyboard_id is None and self.selected_mouse_id is None:
            QMessageBox.information(
                self, "Eksik",
                "Önce klavye veya mouse seçmen lazım.\n"
                "Listeden tıklayabilir veya 'Test' butonu ile algılayabilirsin."
            )
            return
        try:
            cfg = {}
            if os.path.exists(_SETTINGS_FILE):
                try:
                    with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
                        cfg = json.load(f) or {}
                except Exception:
                    cfg = {}
            cfg.setdefault("global", {})
            if self.selected_keyboard_id is not None:
                cfg["global"]["keyboard_id"] = int(self.selected_keyboard_id)
            if self.selected_mouse_id is not None:
                cfg["global"]["mouse_id"] = int(self.selected_mouse_id)
            with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=4, ensure_ascii=False)

            # clicksend.reload_device_ids → mevcut Driver instance'lari yeni ID ile
            # SEGESOURCE varyanti None dondurur (sadece cache temizler);
            # SEGECLAUDE varyanti (new_kb, new_ms) tuple dondurur. Ikisini de
            # destekle ki dialog her iki build'de de calissin.
            new_kb = self.selected_keyboard_id
            new_ms = self.selected_mouse_id
            if reload_device_ids is not None:
                try:
                    result = reload_device_ids()
                    if isinstance(result, tuple) and len(result) == 2:
                        new_kb, new_ms = result
                except Exception as e:
                    QMessageBox.warning(self, "Uyari",
                                        f"Ayar yazildi ama runtime reload basarisiz: {e}\n"
                                        "Programi yeniden baslat.")
                    self.accept()
                    return
            QMessageBox.information(
                self, "Uygulandi",
                f"Cihaz ID'leri guncellendi.\n\n"
                f"Klavye: {new_kb}\nMouse : {new_ms}\n\n"
                "Restart gerekmiyor — sonraki tuş gönderimleri yeni ID ile gidecek."
            )
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Kaydetme hatasi: {e}")

    def test_send_key(self):
        """5 sn icinde aktif pencereye 'A' tusu gonder + sonucu raporla.

        SEGESOURCE (open-source build) icinde secure_send'in TEK gate'i var:
        `_is_target_active()` (opsiyonel foreground-window filter). Eski
        closed-source build'in DLL permission ve heartbeat lease gate'leri
        bu build'de YOK — kaldirildilar, kontrol etmek yanlis teshis verir.

        AUDIT-2026-05 Round 9: UI freeze fix — time.sleep(5) yerine
        QTimer.singleShot(5000) ile event loop bloklanmiyor.
        """
        try:
            import clicksend as _cs
            # SEGESOURCE'da `_is_target_active` modulun ic fonksiyonu;
            # AttributeError olursa fail-OPEN (her zaman izin var say).
            try:
                _is_target_active = _cs._is_target_active
            except AttributeError:
                _is_target_active = lambda: True
            try:
                KeyboardDriver = _cs.KeyboardDriver
            except AttributeError:
                KeyboardDriver = None
            if KeyboardDriver is None:
                QMessageBox.critical(self, "Test Hatasi",
                                     "clicksend.KeyboardDriver bulunamadi (build problemi).")
                return

            # Gate diagnostics — SADECE SEGESOURCE'da gercekten var olan gate
            reasons = []
            if not _is_target_active():
                reasons.append(
                    "Foreground filter aktif (Sistem Ayarlari'nda "
                    "'Sadece oyun ondeyken tus gonder' acik) ve hedef "
                    "pencere onde degil."
                )

            # Closure state — _do_test_send_actual icin sakla
            self._test_reasons = reasons
            self._test_KeyboardDriver = KeyboardDriver

            self.status.setText("5 sn icinde Notepad/oyun penceresini onal — A tusu gidecek...")
            self.btn_test_key.setEnabled(False)
            # UI bloklanmasin — 5 sn sonra _do_test_send_actual cagrilsin
            QTimer.singleShot(5000, self._do_test_send_actual)
        except Exception as e:
            QMessageBox.critical(self, "Test Hatasi", f"{e}")

    def _do_test_send_actual(self):
        """QTimer callback — 5sn sonra stroke gonderir, 300ms sonra rapor.

        R13: time.sleep(0.3) UI thread'i bloklamiyordu (dialog kucuk)
        ama deterministik degil — QTimer.singleShot(300, ...) ile event-
        loop-safe iki adim: stroke + (300ms sonra) followup rapor.
        """
        try:
            KeyboardDriver = getattr(self, "_test_KeyboardDriver", None)
            if KeyboardDriver is None:
                QMessageBox.critical(self, "Test Hatasi", "KeyboardDriver yok (state kayip).")
                self.btn_test_key.setEnabled(True)
                return

            try:
                drv = KeyboardDriver()
                drv.tusbas(0x1E, 0.05)  # scan code for 'A'
            except Exception as e:
                QMessageBox.critical(self, "Test Hatasi", f"tusbas exception: {e}")
                self.btn_test_key.setEnabled(True)
                return

            # 300ms sonra rapor — UI event loop calismaya devam.
            QTimer.singleShot(300, self._do_test_send_followup)
        except Exception as e:
            QMessageBox.critical(self, "Test Hatasi", f"{e}")
            try:
                self.btn_test_key.setEnabled(True)
            except Exception:
                pass

    def _do_test_send_followup(self):
        """R13: 300ms sonra calisan rapor uretici (eski blocking sleep).

        SEGESOURCE'da drop counter telemetri yok; sonucu kullanici gozuyle
        dogrular ("A yazildi mi?"). Yazilmadiysa olasi sebepler:
        1) Yanlis keyboard_id (default=1, gercek klavyen baska device)
        2) Interception driver yuklu degil / servisi durmus
        3) Oyun admin calisiyor, SEGESOURCE degil (UAC mismatch)
        """
        try:
            reasons = getattr(self, "_test_reasons", [])
            msg = "TEST SONUCU\n\n"
            if not reasons:
                msg += "✅ Stroke gonderildi (gate yok / acik).\n\n"
                msg += "Pencerene 'A' yazildi mi?\n"
                msg += "  • Yazildiysa → cihaz ID dogru, sistem calisiyor.\n"
                msg += "  • Yazilmadiysa muhtemel sebep:\n"
                msg += "      1) Yanlis keyboard_id → bu dialog'da klavye sec + KAYDET\n"
                msg += "      2) Interception driver yuklu degil / servisi kapali\n"
                msg += "      3) Oyun admin calisiyor, SEGESOURCE admin degil"
            else:
                msg += "❌ Stroke gonderilmedi:\n"
                for r in reasons:
                    msg += f"  • {r}\n"
            QMessageBox.information(self, "Tus Test Sonucu", msg)
            self.status.setText("Test tamamlandi.")
        except Exception as e:
            QMessageBox.critical(self, "Test Hatasi", f"{e}")
        finally:
            try:
                self.btn_test_key.setEnabled(True)
            except Exception:
                pass

    def reject(self):
        try:
            if self.det_thread and self.det_thread.isRunning():
                self.det_thread.stop()
                self.det_thread.wait(500)
        except Exception:
            pass
        super().reject()

    def closeEvent(self, e):
        self.reject()
        e.accept()


def show_id_bul_dialog(parent=None, initial_kb=None, initial_ms=None):
    """Convenience wrapper — app.py'den çağırılır."""
    dlg = IdBulDialog(parent=parent, initial_kb=initial_kb, initial_ms=initial_ms)
    return dlg.exec_()
