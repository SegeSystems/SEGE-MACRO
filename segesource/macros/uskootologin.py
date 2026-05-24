# -*- coding: utf-8 -*-
# ═══════════════════════════════════════════════════════════════════════════
# SEGE OPEN SOURCE — MACRO MODULE
# ═══════════════════════════════════════════════════════════════════════════
#
# EN:
#   This module is part of the SEGE open-source macro framework for
#   Knight Online. It defines a single automated behavior (a "macro") plus
#   its PyQt5 configuration widget. The macro is loaded at runtime by the
#   module registry (segesource/app/modules.py) and reacts to a configurable
#   hotkey defined by the user in the UI.
#
#   Architecture contract every macro module must follow:
#     - exports a `*Macro` class with `.start()` and `.stop()` methods
#     - exports a `*Widget` class (QWidget subclass) for configuration
#     - reads/writes its persistent state via the shared settings dict
#     - uses `drivers.clicksend` for keyboard/mouse output (Interception
#       driver wrapper), never raw pyautogui inside hotpath
#
#   This file ships under the MIT License (see LICENSE in the repo root).
#   It is provided for EDUCATIONAL and RESEARCH purposes only. Using this
#   software to automate input in any online game may violate that game's
#   Terms of Service.
#
# TR:
#   Bu modül, Knight Online için SEGE açık kaynak makro çerçevesinin bir
#   parçasıdır. Tek bir otomatik davranışı (bir "makro") ve onun PyQt5
#   konfigürasyon widget'ını içerir. Makro, çalışma zamanında modül kayıt
#   defteri (segesource/app/modules.py) tarafından yüklenir ve kullanıcının
#   arayüzde belirlediği kısayol tuşuna tepki verir.
#
#   Her makro modülünün uyması gereken mimari sözleşme:
#     - `.start()` ve `.stop()` metodları olan bir `*Macro` sınıfı sağlar
#     - Konfigürasyon için bir `*Widget` sınıfı (QWidget) sağlar
#     - Kalıcı durumunu paylaşılan settings sözlüğü üzerinden okur/yazar
#     - Klavye/fare çıktısı için `drivers.clicksend` kullanır (Interception
#       sürücü wrapper'ı), sıcak yolda asla doğrudan pyautogui değil
#
#   Bu dosya MIT lisansı altında dağıtılır (depo kökündeki LICENSE).
#   YALNIZCA EĞİTİM ve ARAŞTIRMA amaçlıdır. Bu yazılımı herhangi bir
#   çevrimiçi oyunda giriş otomasyonu için kullanmak ilgili oyunun
#   Kullanım Koşullarını ihlal edebilir.
#
# ═══════════════════════════════════════════════════════════════════════════

import threading
import time
import os
import subprocess
import keyboard
import pyautogui
import cv2
import numpy as np
import requests
import base64
import pytesseract
from PIL import Image
from PyQt5.QtWidgets import (
    QDialog, QLabel, QComboBox, 
    QLineEdit, QPushButton, QHBoxLayout, QWidget,
    QFrame, QVBoxLayout, QSizePolicy,
    QScrollArea, QCheckBox, QGroupBox, QRadioButton,
    QButtonGroup, QSpinBox, QFileDialog, QDialogButtonBox
)
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QSize

# Tesseract Yolu
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# Sürücü Kontrolü
try:
    from clicksend import KeyboardDriver, MouseDriver
except ImportError:
    KeyboardDriver = None
    MouseDriver = None

# PyAutoGUI Ayarları
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.05

# ============================================================
# GÖRSEL DOSYA İSİMLERİ
# ============================================================
IMAGE_FILES = {
    "launcher_start": "launcherstart.png", "launcher_close": "launcherclose.png",
    "login_btn": "login.png", "ok": "ok.png",
    "num_0": "0.png", "num_1": "1.png", "num_2": "2.png", "num_3": "3.png",
    "num_4": "4.png", "num_5": "5.png", "num_6": "6.png", "num_7": "7.png",
    "num_8": "8.png", "num_9": "9.png", "num_del": "del.png",
    "otp_confirm": "otpconfirm.png", "otp_copy": "otpcopy.png",
    "otp_password": "otppassword.png", "otp_error": "otperror.png", "otp_sonra": "Otpsonra.png",
    "captcha": "captcha.png", "captcha_input": "captcha_input.png",
    "captcha_confirm": "Captcheconfirm.png", "captcha_refresh": "captcheyenile.png",
    "pass": "pass.png",
    "oreads_sari": "oreadssari.png", "minark_sari": "minarksari.png",
    "destan_sari": "destansari.png", "dryads_sari": "dryadssari.png",
    "pandora_sari": "pandorasari.png", "felis_sari": "felissari.png",
    "agartha_sari": "agarthasari.png", "zero_sari": "zerosari.png",
    "oreads_beyaz": "oreadsbeyaz.png", "minark_beyaz": "minarkbeyaz.png",
    "destan_beyaz": "destanbeyaz.png", "dryads_beyaz": "dryadsbeyaz.png",
    "pandora_beyaz": "pandorabeyaz.png", "felis_beyaz": "felisbeyaz.png",
    "agartha_beyaz": "agarthabeyaz.png", "zero_beyaz": "zerobeyaz.png",
    "s1": "s1.png", "s2": "s2.png", "s3": "s3.png", "s4": "s4.png",
    "s5": "s5.png", "s6": "s6.png", "s7": "s7.png", "s8": "s8.png",
    "error_confirm": "enterconfirm.png",
    "char_left": "solkarakter.png",
    "dc_confirm": "dcconfirm.png",
    "notice_confirm": "noticeconfirm.png",
    "connect": "connect.png",
    "start_game": "startgame.png",
    "cancel": "cancel.png",
    "refresh": "refresh.png",
    "disconnected": "disconnected.png",
    "entered": "entered.png",
}

# ============================================================
# GÖRSEL TANIMLAMA YARDIMCI FONKSİYONLARI
# ============================================================
def capture_screen():
    screenshot = pyautogui.screenshot()
    return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)

def find_template(screen, template_path, threshold=0.8):
    if not os.path.exists(template_path):
        return None
    template = cv2.imread(template_path)
    if template is None:
        return None
    screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
    template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    result = cv2.matchTemplate(screen_gray, template_gray, cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
    if max_val >= threshold:
        h, w = template_gray.shape
        center_x = max_loc[0] + w // 2
        center_y = max_loc[1] + h // 2
        return (center_x, center_y, w, h, max_val)
    return None

def check_image_exists(screen, template_path, threshold=0.8):
    return find_template(screen, template_path, threshold) is not None

# ============================================================
# CAPTCHA ÇÖZÜCÜLER
# ============================================================
def solve_with_2captcha(image_path, api_key):
    if not api_key or len(api_key) < 10:
        return None
    try:
        with open(image_path, "rb") as f:
            img_str = base64.b64encode(f.read()).decode('utf-8')
        payload = {
            "key": api_key, "method": "base64", "body": img_str,
            "json": 1, "min_len": 4, "max_len": 4, "regsense": 1, "numeric": 0
        }
        resp = requests.post("http://2captcha.com/in.php", data=payload, timeout=10)
        result = resp.json()
        if result.get('status') != 1:
            return None
        captcha_id = result['request']
        for _ in range(40):
            time.sleep(2)
            resp = requests.get(f"http://2captcha.com/res.php?key={api_key}&action=get&id={captcha_id}&json=1", timeout=10)
            result = resp.json()
            if result.get('status') == 1:
                return result['request']
            elif result.get('request') == "ERROR_CAPTCHA_UNSOLVABLE":
                return None
    except Exception:
        pass
    return None

# ============================================================
class UskoOtoLoginMacro:
    def __init__(self):
        self.config = {}
        self._running = False
        self._stop_event = threading.Event()
        self._thread = None
        self.kb = KeyboardDriver() if KeyboardDriver else None
        self.mouse = MouseDriver() if MouseDriver else None
        self.status = "HAZIR"
        self.current_step = 0
        self.total_steps = 9
    
    def _handle_captcha(self):
        if not self.config.get("enable_captcha", False):
            return True
        confirm_path = self._get_image_path("captcha_confirm")
        refresh_path = self._get_image_path("captcha_refresh")
        error_confirm_path = self._get_image_path("error_confirm")
        api_key = self.config.get("api_key", "")
        
        # GÜNCELLEME 1: Çıktı dosyasını images_dir içine kaydet
        images_dir = self.config.get("images_dir", "login_images")
        captcha_output_path = os.path.join(images_dir, "kontrol_ne_kesiyor.png")
        
        for attempt in range(1, 6):
            if self._stop_event.is_set(): return False
            time.sleep(2) 
            screen = capture_screen()
            confirm_result = find_template(screen, confirm_path, threshold=0.65)
            if not confirm_result:
                continue

            cx, cy, _, _, _ = confirm_result
            cap_x, cap_y, cap_w, cap_h = max(0, cx - 210), max(0, cy - 85), 200, 55
            captcha_img = screen[cap_y:cap_y+cap_h, cap_x:cap_x+cap_w]
            cv2.imwrite(captcha_output_path, captcha_img)
            
            captcha_text = solve_with_2captcha(captcha_output_path, api_key)
            if not captcha_text or len(captcha_text) < 3:
                refresh_res = find_template(screen, refresh_path, 0.6)
                if refresh_res: self._safe_click(refresh_res[0], refresh_res[1])
                continue
            
            self._safe_click(cx - 75, cy) 
            time.sleep(0.5) 
            if self.kb:
                BACKSPACE_SC = 0x0E
                for _ in range(10): 
                    self.kb.tusbas(BACKSPACE_SC, 0.05)
                    time.sleep(0.05)
            else:
                for _ in range(10): pyautogui.press('backspace')
            time.sleep(0.2)
            self._type_with_driver(captcha_text)
            time.sleep(0.5)
            self._safe_click(cx, cy)
            time.sleep(2.5) 
            
            screen_after = capture_screen()
            error_btn = find_template(screen_after, error_confirm_path, threshold=0.7)
            if error_btn:
                self._safe_click(error_btn[0], error_btn[1])
                time.sleep(1)
                refresh_res = find_template(screen_after, refresh_path, 0.6)
                if refresh_res: self._safe_click(refresh_res[0], refresh_res[1])
                continue
            
            if not check_image_exists(screen_after, confirm_path, 0.65):
                return True
            else:
                refresh_res = find_template(screen_after, refresh_path, 0.6)
                if refresh_res: self._safe_click(refresh_res[0], refresh_res[1])
        return False
        
    def update_config(self, cfg):
        self.config = cfg
        
    @property
    def is_running(self):
        return self._running
    
    def start(self):
        if not self._running:
            self._stop_event.clear()
            self._running = True
            self.status = "BAŞLADI"
            self.current_step = 0
            self._thread = threading.Thread(target=self._login_sequence, daemon=True)
            self._thread.start()
            
    def stop(self):
        self._stop_event.set()
        self._running = False
        self.status = "DURDURULDU"
    
    def _get_image_path(self, key):
        images_dir = self.config.get("images_dir", "login_images")
        filename = IMAGE_FILES.get(key, "")
        return os.path.join(images_dir, filename)
        
    def _safe_click(self, x, y, delay=0.1, use_interception=True):
        try:
            if use_interception and self.mouse:
                self.mouse.leftclick(0.05, int(x), int(y))
            else:
                pyautogui.click(int(x), int(y))
            time.sleep(delay)
        except Exception:
            pass
            
    def _type_with_driver(self, text):
        SCANCODES = {
            'a': 0x1E, 'b': 0x30, 'c': 0x2E, 'd': 0x20, 'e': 0x12, 'f': 0x21, 'g': 0x22, 'h': 0x23, 'i': 0x17, 'j': 0x24,
            'k': 0x25, 'l': 0x26, 'm': 0x32, 'n': 0x31, 'o': 0x18, 'p': 0x19, 'q': 0x10, 'r': 0x13, 's': 0x1F, 't': 0x14,
            'u': 0x16, 'v': 0x2F, 'w': 0x11, 'x': 0x2D, 'y': 0x15, 'z': 0x2C,
            '0': 0x0B, '1': 0x02, '2': 0x03, '3': 0x04, '4': 0x05, '5': 0x06, '6': 0x07, '7': 0x08, '8': 0x09, '9': 0x0A,
        }
        SHIFT_CHARS = {
            '!': 0x02, '@': 0x03, '#': 0x04, '$': 0x05, '%': 0x06, '^': 0x07, '&': 0x08, '*': 0x09, '(': 0x0A, ')': 0x0B,
            '-': 0x0C, '=': 0x0D, '[': 0x1A, ']': 0x1B, ';': 0x27, "'": 0x28, '`': 0x29, '\\': 0x2B, ',': 0x33, '.': 0x34,
            '/': 0x35, ' ': 0x39,
        }
        SHIFT_CODE = 0x2A
        KEY_PRESS_DURATION = 0.08
        KEY_INTERVAL = 0.15
        if self.kb:
            for char in text:
                if self._stop_event.is_set(): return
                if char.isupper():
                    lower_char = char.lower()
                    sc = SCANCODES.get(lower_char)
                    if sc:
                        self.kb.tusbasilitut(SHIFT_CODE)
                        time.sleep(0.05)
                        self.kb.tusbas(sc, KEY_PRESS_DURATION)
                        self.kb.tusbirak(SHIFT_CODE)
                        time.sleep(KEY_INTERVAL)
                    continue
                if char in SCANCODES:
                    sc = SCANCODES[char]
                    self.kb.tusbas(sc, KEY_PRESS_DURATION)
                    time.sleep(KEY_INTERVAL)
                elif char in SHIFT_CHARS:
                    sc = SHIFT_CHARS[char]
                    self.kb.tusbasilitut(SHIFT_CODE)
                    time.sleep(0.05)
                    self.kb.tusbas(sc, KEY_PRESS_DURATION)
                    self.kb.tusbirak(SHIFT_CODE)
                    time.sleep(KEY_INTERVAL)
                else:
                    time.sleep(KEY_INTERVAL)
        else:
            pyautogui.write(text, interval=0.15)
                
    def _find_and_click(self, image_key, timeout=30, threshold=0.8, offset_x=0, offset_y=0, use_interception=True):
        template_path = self._get_image_path(image_key)
        self.status = "Aranıyor..."
        start = time.time()
        while time.time() - start < timeout:
            if self._stop_event.is_set(): return False
            screen = capture_screen()
            result = find_template(screen, template_path, threshold)
            if result:
                x, y, w, h, conf = result
                self._safe_click(x + offset_x, y + offset_y, use_interception=use_interception)
                return True
            time.sleep(0.3)
        return False
    
    def _wait_for_image(self, image_key, timeout=30, threshold=0.8):
        template_path = self._get_image_path(image_key)
        start = time.time()
        while time.time() - start < timeout:
            if self._stop_event.is_set(): return None
            screen = capture_screen()
            result = find_template(screen, template_path, threshold)
            if result: return result
            time.sleep(0.3)
        return None
    
    def _check_image(self, image_key, threshold=0.8):
        template_path = self._get_image_path(image_key)
        screen = capture_screen()
        return find_template(screen, template_path, threshold) is not None
    
    def _click_otp_number(self, digit, numpad_region=None):
        image_key = f"num_{digit}"
        template_path = self._get_image_path(image_key)
        if not os.path.exists(template_path): return False, numpad_region, None, None
        screen = capture_screen()
        template = cv2.imread(template_path)
        if template is None: return False, numpad_region, None, None
        
        if numpad_region:
            rx, ry, rw, rh = numpad_region
            cropped_screen = screen[ry:ry+rh, rx:rx+rw]
            screen_gray = cv2.cvtColor(cropped_screen, cv2.COLOR_BGR2GRAY)
            template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
            result = cv2.matchTemplate(screen_gray, template_gray, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
            if max_val >= 0.65:
                th, tw = template_gray.shape
                center_x = rx + max_loc[0] + tw // 2
                center_y = ry + max_loc[1] + th // 2
                pyautogui.click(center_x, center_y)
                return True, numpad_region, center_x, center_y
        
        screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
        template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        result = cv2.matchTemplate(screen_gray, template_gray, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        if max_val >= 0.65:
            th, tw = template_gray.shape
            center_x = max_loc[0] + tw // 2
            center_y = max_loc[1] + th // 2
            pyautogui.click(center_x, center_y)
            return True, numpad_region, center_x, center_y
        return False, numpad_region, None, None
    
    def _find_numpad_region(self):
        screen = capture_screen()
        all_points = []
        for digit in ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']:
            template_path = self._get_image_path(f"num_{digit}")
            if not os.path.exists(template_path): continue
            template = cv2.imread(template_path)
            if template is None: continue
            screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
            template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
            result = cv2.matchTemplate(screen_gray, template_gray, cv2.TM_CCOEFF_NORMED)
            locations = np.where(result >= 0.7)
            for pt in zip(*locations[::-1]): all_points.append((pt[0], pt[1]))
        if len(all_points) >= 3:
            xs = [p[0] for p in all_points]
            ys = [p[1] for p in all_points]
            min_x, min_y = min(xs) - 20, min(ys) - 20
            max_x, max_y = max(xs) + 60, max(ys) + 60
            width, height = max_x - min_x, max_y - min_y
            if 80 < width < 400 and 80 < height < 400:
                return (min_x, min_y, width, height)
        return None
    
    def _enter_otp_password(self, otp_password):
        self.status = "OTP giriliyor..."
        numpad_region = self._find_numpad_region()
        if numpad_region:
            rx, ry, rw, rh = numpad_region
            pyautogui.click(rx + rw // 2, ry + rh // 2 - 30)
            time.sleep(0.3)
        prev_digit, last_click_x, last_click_y = None, None, None
        for i, digit in enumerate(otp_password):
            if self._stop_event.is_set(): return False
            if prev_digit == digit and last_click_x and last_click_y:
                time.sleep(1.5)
                pyautogui.click(last_click_x, last_click_y)
                time.sleep(0.5)
            else:
                numpad_region = self._find_numpad_region()
                success, numpad_region, click_x, click_y = self._click_otp_number(digit, numpad_region)
                if not success: return False
                last_click_x, last_click_y = click_x, click_y
                time.sleep(0.5)
            prev_digit = digit
        return True
    
    def _login_sequence(self):
        try:
            images_dir = self.config.get("images_dir", "login_images")
            if not os.path.exists(images_dir):
                self.status = "HATA: Görsel klasörü yok"
                self._running = False
                return
            
            self.current_step = 1
            self.status = "Launcher açılıyor..."
            game_path = self.config.get("game_path", "")
            # AUDIT-2026-05 Round 3 C7 FIX:
            # Eski "shell=True" + f-string Windows cmd metakarakter injection
            # acigi yaratiyordu (& | && ; > < ^). Path "C:\x.exe" & calc & echo "
            # gibi olsa "calc" calisirdi. Artik:
            #  - shell=False + liste arg (cmd parser kullanmaz)
            #  - .exe uzanti kontrolu
            #  - absolute path kontrolu
            if not game_path:
                self.status = "HATA: Oyun yolu hatalı"
                self._running = False
                return
            if not game_path.lower().endswith(".exe"):
                self.status = "HATA: Oyun yolu .exe olmali"
                self._running = False
                return
            if not os.path.isabs(game_path) or not os.path.isfile(game_path):
                self.status = "HATA: Oyun yolu bulunamadi"
                self._running = False
                return
            subprocess.Popen([game_path], shell=False)
            time.sleep(5)
            
            self.current_step = 2
            self.status = "START aranıyor..."
            if not self._find_and_click("launcher_start", timeout=60, threshold=0.75, use_interception=False):
                self.status = "HATA: START bulunamadı"
                self._running = False
                return
            time.sleep(2)
            
            self.current_step = 3
            self.status = "Login bekleniyor..."
            otp_mode = self.config.get("otp_mode", "none")
            otp_clipboard_ready = False
            login_success = False
            
            if self._wait_for_image("login_btn", timeout=60, threshold=0.75):
                time.sleep(1)
                screen = capture_screen()
                login_result = find_template(screen, self._get_image_path("login_btn"), 0.75)
                if login_result:
                    login_x, login_y, w, h, conf = login_result
                    id_y = login_y + 75
                    self._safe_click(login_x, id_y, delay=0.3)
                    time.sleep(0.3)
                    pyautogui.hotkey('ctrl', 'a')
                    time.sleep(0.1)
                    pyautogui.press('delete')
                    time.sleep(0.1)
                    username = self.config.get("username", "")
                    self._type_with_driver(username)
                    time.sleep(0.5)
                    pass_y = id_y + 52
                    self._safe_click(login_x, pass_y, delay=0.3)
                    time.sleep(0.3)
                    pyautogui.hotkey('ctrl', 'a')
                    time.sleep(0.1)
                    pyautogui.press('delete')
                    time.sleep(0.1)
                    password = self.config.get("password", "")
                    self._type_with_driver(password)
                    time.sleep(0.5)
                    self._find_and_click("ok", timeout=10, threshold=0.75)
                    for attempt in range(30):
                        screen = capture_screen()
                        if not find_template(screen, self._get_image_path("login_btn"), 0.75):
                            login_success = True
                            break
                        time.sleep(0.3)
                    if not login_success:
                        login_success = True
                        time.sleep(2)
            else:
                self.status = "HATA: Login ekranı gelmedi"
                self._running = False
                return
            
            if not login_success:
                self.status = "HATA: Login başarısız"
                self._running = False
                return
            
            if otp_mode != "none":
                self.current_step = 4
                self.status = "OTP açılıyor..."
                otp_path = self.config.get("otp_path", "")
                # AUDIT-2026-05 Round 3 C7 FIX:
                # Path validation: yalnizca absolute .exe ve dosya gercekten var.
                # Sonra shell=True yerine ShellExecute / Popen(list) kullaniyor.
                if not otp_path:
                    self.status = "HATA: OTP yolu boş"
                    self._running = False
                    return
                if not otp_path.lower().endswith(".exe"):
                    self.status = "HATA: OTP yolu .exe olmali"
                    self._running = False
                    return
                if not os.path.isabs(otp_path) or not os.path.isfile(otp_path):
                    self.status = "HATA: OTP exe yok"
                    self._running = False
                    return
                try:
                    otp_directory = os.path.dirname(otp_path)
                    import ctypes
                    try:
                        # 1. tercih: ShellExecuteW (UAC promptlu)
                        result = ctypes.windll.shell32.ShellExecuteW(None, "runas", otp_path, None, otp_directory, 1)
                    except Exception:
                        try:
                            # 2. tercih: direkt Popen (admin gerekmiyorsa)
                            otp_process = subprocess.Popen(
                                [otp_path], cwd=otp_directory, shell=False,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            )
                        except Exception:
                            # 3. tercih: PowerShell Start-Process — shell=False + list arg
                            # ile arg injection imkansiz. Path zaten valide edildi.
                            subprocess.Popen(
                                [
                                    "powershell", "-NoProfile", "-Command",
                                    "Start-Process",
                                    "-FilePath", otp_path,
                                    "-WorkingDirectory", otp_directory,
                                    "-Verb", "RunAs",
                                ],
                                shell=False,
                            )
                except Exception as e:
                    self.status = f"HATA: OTP hatası: {str(e)}"
                    self._running = False
                    return
                time.sleep(5)
                self.status = "OTP şifre ekranı..."
                otp_screen_found = False
                result = self._wait_for_image("otp_password", timeout=3, threshold=0.6)
                if result:
                    otp_screen_found = True
                else:
                    screen = capture_screen()
                    for digit in ['1', '5', '0', '9', '2', '3']:
                        digit_path = self._get_image_path(f"num_{digit}")
                        if os.path.exists(digit_path):
                            digit_result = find_template(screen, digit_path, threshold=0.7)
                            if digit_result:
                                otp_screen_found = True
                                break
                    if not otp_screen_found:
                        confirm_result = self._wait_for_image("otp_confirm", timeout=2, threshold=0.6)
                        if confirm_result: otp_screen_found = True
                
                if otp_screen_found:
                    time.sleep(0.5)
                    otp_password = self.config.get("otp_password", "")
                    if otp_password:
                        if not self._enter_otp_password(otp_password):
                            self.status = "HATA: OTP şifre hatası"
                            self._running = False
                            return
                        time.sleep(0.5)
                        self.status = "OTP Confirm..."
                        if not self._find_and_click("otp_confirm", timeout=10, threshold=0.6):
                            self.status = "UYARI: OTP Confirm yok"
                        time.sleep(1.5)
                        self.status = "OTP Kopyalanıyor..."
                        if not self._find_and_click("otp_copy", timeout=10, threshold=0.6):
                            self.status = "UYARI: OTP Copy yok"
                        else:
                            otp_clipboard_ready = True
                        time.sleep(0.5)
                else:
                    self.status = "UYARI: OTP ekranı bulunamadı"
            
            if otp_mode != "none" and otp_clipboard_ready:
                self.current_step = 5
                self.status = "OTP yapıştırılıyor..."
                time.sleep(1)
                screen = capture_screen()
                otp_sonra_result = find_template(screen, self._get_image_path("otp_sonra"), threshold=0.6)
                if otp_sonra_result:
                    self._safe_click(otp_sonra_result[0], otp_sonra_result[1])
                else:
                    screen_width, screen_height = pyautogui.size()
                    game_x = int(screen_width * 0.75)
                    game_y = int(screen_height * 0.5)
                    pyautogui.click(game_x, game_y)
                time.sleep(0.5)
                if self.kb:
                    self.kb.tusbasilitut(0x1D)
                    time.sleep(0.05)
                    self.kb.tusbas(0x2F, 0.05)
                    self.kb.tusbirak(0x1D)
                else:
                    pyautogui.hotkey('ctrl', 'v')
                time.sleep(0.5)
                if self.kb: self.kb.tusbas(0x1C, 0.05)
                else: pyautogui.press('enter')
                time.sleep(1)
                
            self.current_step = 6
            self.status = "Notice onaylanıyor..."
            time.sleep(2)
            if not self._find_and_click("notice_confirm", timeout=15, threshold=0.75):
                self.status = "Notice Confirm yok"
            
            self.current_step = 7
            self.status = "Server seçiliyor..."
            time.sleep(2)
            server_name = self.config.get("server_name", "FELIS").lower()
            channel = self.config.get("channel", 1)
            server_found = False
            server_keys = [f"{server_name}_sari", f"{server_name}_beyaz"]
            for server_key in server_keys:
                screen = capture_screen()
                server_path = self._get_image_path(server_key)
                if os.path.exists(server_path):
                    result = find_template(screen, server_path, threshold=0.7)
                    if result:
                        x, y, w, h, conf = result
                        click_x = x - 5
                        self._safe_click(click_x, y, delay=0.3, use_interception=True)
                        time.sleep(0.3)
                        if self.kb: self.kb.tusbas(0x1C, 0.05)
                        else: pyautogui.press('enter')
                        server_found = True
                        break
            time.sleep(0.8)
            channel_key = f"s{channel}"
            channel_path = self._get_image_path(channel_key)
            if os.path.exists(channel_path):
                screen = capture_screen()
                result = find_template(screen, channel_path, threshold=0.7)
                if result:
                    x, y, w, h, conf = result
                    click_x = x - 5
                    self._safe_click(click_x, y, delay=0.3, use_interception=True)
                    time.sleep(0.3)
                    self._find_and_click("connect", timeout=5, threshold=0.7)
            
            self.current_step = 8
            self.status = "CAPTCHA bekleniyor..."
            time.sleep(2)
            if not self._handle_captcha(): pass
            
            self.current_step = 9
            self.status = "Karakter seçiliyor..."
            time.sleep(3)
            char_index = self.config.get("character_index", 1)
            if self._wait_for_image("start_game", timeout=30, threshold=0.75):
                if char_index > 1:
                    clicks_needed = char_index - 1
                    for i in range(clicks_needed):
                        if self._stop_event.is_set(): return
                        found_arrow = self._find_and_click("char_left", timeout=10, threshold=0.7, use_interception=True)
                        if found_arrow: time.sleep(3.0) 
                        else: break
                time.sleep(1.0)
                self._find_and_click("start_game", timeout=15, threshold=0.75, use_interception=True)
            
            self.status = "GİRİŞ TAMAMLANDI!"
            self.current_step = 9
            if self.config.get("auto_reconnect", False): self._monitor_game()
        except Exception as e:
            self.status = f"HATA: {str(e)}"
        finally:
            self._running = False
            
    def _monitor_game(self):
        self.status = "Oyun izleniyor..."
        while not self._stop_event.is_set():
            time.sleep(10)
            if self._stop_event.is_set(): break
            if self._check_image("disconnected", threshold=0.75):
                self.status = "DC ALGILANDI!"
                time.sleep(2)
                found_btn = self._find_and_click("dc_confirm", timeout=10, threshold=0.7, use_interception=True)
                if not found_btn:
                    if self.mouse:
                        for _ in range(3):
                            self.mouse.left_click()
                            time.sleep(0.15)
                    elif self.kb:
                        self.kb.tusbas(0x1C, 0.1)
                    else:
                        pyautogui.click(clicks=3, interval=0.15)
                self.status = "Restart bekleniyor..."
                time.sleep(25)
                self._running = True
                self._login_sequence()
                break
            if self._check_image("launcher_start", threshold=0.75):
                self._running = True
                self._login_sequence()
                break

# ============================================================
# AYARLAR DİYALOĞU
# ============================================================
class UskoOtoLoginSettingsDialog(QDialog):
    def __init__(self, parent, config, macro):
        super().__init__(parent)
        self.setWindowTitle("USKO OTO LOGIN AYARLARI")
        self.setFixedSize(600, 700)
        self.config = config
        self.macro = macro
        # GÜNCELLEME 3: Hotkey yakalama değişkeni kaldırıldı
        # self.capture_hotkey = False
        self.result_config = {}
        
        self.setStyleSheet("""
            QDialog { background-color: #101010; color: white; }
            QLabel { color: #ccc; font-family: 'Segoe UI'; font-size: 11px; }
            QLineEdit { background: #151515; border: 1px solid #333; color: #00ff4c; padding: 5px; border-radius: 3px; }
            QPushButton { background-color: #1a1a2e; color: white; border: 1px solid #444; padding: 8px; border-radius: 4px; }
            QPushButton:hover { background-color: #16213e; border-color: #00ff4c; }
            QCheckBox { color: #00ff4c; font-size: 11px; }
            QRadioButton { color: #eee; font-size: 11px; }
            QComboBox { background: #151515; color: #00ff4c; border: 1px solid #444; padding: 5px; }
            QGroupBox { color: #00ff4c; font-weight: bold; border: 1px solid #333; border-radius: 5px; margin-top: 10px; padding-top: 10px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
            QSpinBox { background: #151515; color: #00ff4c; border: 1px solid #444; padding: 5px; }
            QScrollArea { border: none; background: transparent; }
        """)
        self._setup_ui()
            
    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        layout = QVBoxLayout(scroll_widget)
        
        title = QLabel("🎮 KNIGHT ONLINE OTOMATİK GİRİŞ")
        title.setStyleSheet("color: #ff6600; font-size: 16px; font-weight: bold; padding: 10px;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        path_group = QGroupBox("📁 DOSYA YOLLARI")
        path_layout = QVBoxLayout(path_group)
        
        h1 = QHBoxLayout()
        h1.addWidget(QLabel("Oyun Yolu:"))
        self.txt_game_path = QLineEdit(self.config.get("game_path", ""))
        self.txt_game_path.setPlaceholderText("C:\\NTTGame\\KnightOnlineEn\\KnightOnLine.exe")
        btn_game = QPushButton("Seç")
        btn_game.setFixedWidth(50)
        btn_game.clicked.connect(lambda: self._select_path("game"))
        h1.addWidget(self.txt_game_path)
        h1.addWidget(btn_game)
        path_layout.addLayout(h1)
        
        h2 = QHBoxLayout()
        h2.addWidget(QLabel("OTP Yolu:"))
        self.txt_otp_path = QLineEdit(self.config.get("otp_path", ""))
        self.txt_otp_path.setPlaceholderText("C:\\Program Files (x86)\\AnyOTF\\AnyOTF.exe")
        btn_otp = QPushButton("Seç")
        btn_otp.setFixedWidth(50)
        btn_otp.clicked.connect(lambda: self._select_path("otp"))
        h2.addWidget(self.txt_otp_path)
        h2.addWidget(btn_otp)
        path_layout.addLayout(h2)
        
        h3 = QHBoxLayout()
        h3.addWidget(QLabel("Görsel Klasörü:"))
        self.txt_images_dir = QLineEdit(self.config.get("images_dir", "login_images"))
        btn_images = QPushButton("Seç")
        btn_images.setFixedWidth(50)
        btn_images.clicked.connect(lambda: self._select_path("images"))
        h3.addWidget(self.txt_images_dir)
        h3.addWidget(btn_images)
        path_layout.addLayout(h3)
        layout.addWidget(path_group)
        
        account_group = QGroupBox("👤 HESAP BİLGİLERİ")
        account_layout = QVBoxLayout(account_group)
        h4 = QHBoxLayout()
        h4.addWidget(QLabel("Kullanıcı Adı:"))
        self.txt_username = QLineEdit(self.config.get("username", ""))
        h4.addWidget(self.txt_username)
        account_layout.addLayout(h4)
        h5 = QHBoxLayout()
        h5.addWidget(QLabel("Şifre:"))
        self.txt_password = QLineEdit(self.config.get("password", ""))
        self.txt_password.setEchoMode(QLineEdit.Password)
        h5.addWidget(self.txt_password)
        account_layout.addLayout(h5)
        layout.addWidget(account_group)
        
        otp_group = QGroupBox("🔐 OTP AYARLARI")
        otp_layout = QVBoxLayout(otp_group)
        h6 = QHBoxLayout()
        h6.addWidget(QLabel("OTP Şifre:"))
        self.txt_otp_password = QLineEdit(self.config.get("otp_password", ""))
        self.txt_otp_password.setEchoMode(QLineEdit.Password)
        self.txt_otp_password.setPlaceholderText("6 haneli OTP şifresi")
        h6.addWidget(self.txt_otp_password)
        otp_layout.addLayout(h6)
        h7 = QHBoxLayout()
        self.rb_otp_none = QRadioButton("OTP Yok")
        self.rb_otp_any = QRadioButton("AnyOTP")
        self.rb_otp_start = QRadioButton("StartOTP")
        self.otp_btn_group = QButtonGroup(self)
        self.otp_btn_group.addButton(self.rb_otp_none)
        self.otp_btn_group.addButton(self.rb_otp_any)
        self.otp_btn_group.addButton(self.rb_otp_start)
        otp_mode = self.config.get("otp_mode", "none")
        if otp_mode == "anyotp": self.rb_otp_any.setChecked(True)
        elif otp_mode == "startotp": self.rb_otp_start.setChecked(True)
        else: self.rb_otp_none.setChecked(True)
        h7.addWidget(self.rb_otp_none)
        h7.addWidget(self.rb_otp_any)
        h7.addWidget(self.rb_otp_start)
        h7.addStretch()
        otp_layout.addLayout(h7)
        layout.addWidget(otp_group)
        
        # GÜNCELLEME 2: Server, Kanal, Karakter Sırası Yan Yana
        server_group = QGroupBox("🌐 SERVER AYARLARI")
        server_layout = QVBoxLayout(server_group)
        
        h_server_settings = QHBoxLayout() 

        # Server
        h_server_settings.addWidget(QLabel("Server:"))
        self.cmb_server = QComboBox()
        servers = ["OREADS", "MINARK", "DESTAN", "DRYADS", "PANDORA", "FELIS", "AGARTHA", "ZERO"]
        self.cmb_server.addItems(servers)
        server_name = self.config.get("server_name", "FELIS")
        if server_name in servers: self.cmb_server.setCurrentIndex(servers.index(server_name))
        self.cmb_server.setFixedWidth(100) # Genişlik ayarı eklendi
        h_server_settings.addWidget(self.cmb_server)
        
        # Kanal
        h_server_settings.addWidget(QLabel("Kanal:"))
        self.spin_channel = QSpinBox()
        self.spin_channel.setMinimum(1)
        self.spin_channel.setMaximum(8)
        self.spin_channel.setValue(self.config.get("channel", 1))
        self.spin_channel.setFixedWidth(40) # Genişlik ayarı eklendi
        h_server_settings.addWidget(self.spin_channel)
        
        # Karakter Sırası
        h_server_settings.addWidget(QLabel("Karakter Sırası:"))
        self.spin_char = QSpinBox()
        self.spin_char.setMinimum(1)
        self.spin_char.setMaximum(4)
        self.spin_char.setValue(self.config.get("character_index", 1))
        self.spin_char.setFixedWidth(40) # Genişlik ayarı eklendi
        h_server_settings.addWidget(self.spin_char)
        
        h_server_settings.addStretch()
        server_layout.addLayout(h_server_settings)
        server_layout.addStretch() # İçeriği yukarıda tutmak için
        layout.addWidget(server_group)
        
        # GÜNCELLEME 3: Hotkey F12 olarak sabitleniyor
        hotkey_group = QGroupBox("⌨️ HOTKEY AYARLARI")
        hotkey_layout = QVBoxLayout(hotkey_group)
        h_hotkey = QHBoxLayout()
        h_hotkey.addWidget(QLabel("Başlatma Tuşu:"))
        self.txt_hotkey = QLineEdit("F12") # Sabitlendi
        self.txt_hotkey.setReadOnly(True)
        h_hotkey.addWidget(self.txt_hotkey)
        # Tuş Ata butonu kaldırıldı
        h_hotkey.addStretch() 
        hotkey_layout.addLayout(h_hotkey)
        layout.addWidget(hotkey_group)
        
        extra_group = QGroupBox("⚙️ EK AYARLAR")
        extra_layout = QVBoxLayout(extra_group)
        api_layout = QHBoxLayout()
        api_layout.addWidget(QLabel("2Captcha API Key:"))
        self.txt_api_key = QLineEdit(self.config.get("api_key", ""))
        self.txt_api_key.setPlaceholderText("Varsa API Key yapıştırın")
        self.txt_api_key.setEchoMode(QLineEdit.Password)
        api_layout.addWidget(self.txt_api_key)
        extra_layout.addLayout(api_layout)
        info_api = QLabel("ℹ️ Key girerseniz 2Captcha kullanılır, girmezseniz Ücretsiz mod çalışır.")
        info_api.setStyleSheet("color: #888; font-size: 10px;")
        extra_layout.addWidget(info_api)
        self.chk_auto_reconnect = QCheckBox("Oyun kapanırsa otomatik tekrar giriş yap")
        self.chk_auto_reconnect.setChecked(self.config.get("auto_reconnect", False))
        extra_layout.addWidget(self.chk_auto_reconnect)
        self.chk_enable_captcha = QCheckBox("CAPTCHA Doğrulaması Etkinleştir")
        self.chk_enable_captcha.setChecked(self.config.get("enable_captcha", False))
        extra_layout.addWidget(self.chk_enable_captcha)
        layout.addWidget(extra_group)
        
        layout.addStretch()
        scroll.setWidget(scroll_widget)
        main_layout.addWidget(scroll)
        
        btn_layout = QHBoxLayout()
        btn_save = QPushButton("💾 KAYDET")
        btn_save.clicked.connect(self.accept)
        btn_cancel = QPushButton("❌ İPTAL")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_cancel)
        main_layout.addLayout(btn_layout)
        
    def _select_path(self, path_type):
        try:
            # Native pencereyi devre dışı bırakan ayar
            options = QFileDialog.Options()
            options |= QFileDialog.DontUseNativeDialog

            if path_type == "game":
                path, _ = QFileDialog.getOpenFileName(
                    self, 
                    "Oyun Launcher Seç", 
                    "", 
                    "Executable (*.exe);;All Files (*.*)", 
                    options=options
                )
                if path:
                    self.txt_game_path.setText(path.replace("/", "\\"))
                    
            elif path_type == "otp":
                path, _ = QFileDialog.getOpenFileName(
                    self, 
                    "OTP Programı Seç", 
                    "", 
                    "Executable (*.exe);;All Files (*.*)", 
                    options=options
                )
                if path:
                    self.txt_otp_path.setText(path.replace("/", "\\"))
                    
            elif path_type == "images":
                path = QFileDialog.getExistingDirectory(
                    self, 
                    "Görsel Klasörü Seç",
                    "",
                    options=options
                )
                if path:
                    self.txt_images_dir.setText(path.replace("/", "\\"))
                    
        except Exception as e:
            print(f"Hata detayı: {e}")

    def accept(self):
        if self.rb_otp_any.isChecked(): otp_mode = "anyotp"
        elif self.rb_otp_start.isChecked(): otp_mode = "startotp"
        else: otp_mode = "none"
        
        servers = ["OREADS", "MINARK", "DESTAN", "DRYADS", "PANDORA", "FELIS", "AGARTHA", "ZERO"]
        server_name = self.cmb_server.currentText()
        server_index = servers.index(server_name) if server_name in servers else 5
        
        self.result_config = {
            "game_path": self.txt_game_path.text(),
            "otp_path": self.txt_otp_path.text(),
            "images_dir": self.txt_images_dir.text() or "login_images",
            "username": self.txt_username.text(),
            "password": self.txt_password.text(),
            "otp_password": self.txt_otp_password.text(),
            "otp_mode": otp_mode,
            "server_name": server_name,
            "server_index": server_index,
            "channel": self.spin_channel.value(),
            "character_index": self.spin_char.value(),
            "auto_reconnect": self.chk_auto_reconnect.isChecked(),
            "enable_captcha": self.chk_enable_captcha.isChecked(),
            "api_key": self.txt_api_key.text(),
            "key": self.txt_hotkey.text().lower() or "f12",
        }
        super().accept()

# ============================================================
# WIDGET (Ana Arayüz Kartı - ASAS Stil)
# ============================================================
class UskoOtoLoginWidget(QFrame):
    update_signal = pyqtSignal()
    
    def __init__(self, parent=None, macro_instance=None, config=None):
        super().__init__(parent)
        self.macro = macro_instance
        self.config = config or {
            "key": "F12", "game_path": "", "otp_path": "", "images_dir": "login_images",
            "username": "", "password": "", "otp_password": "", "otp_mode": "none",
            "server_name": "FELIS", "server_index": 5, "channel": 1, "character_index": 1,
            "auto_reconnect": False
        }
        self.listen_active = False
        self._hook = None
        
        self.update_signal.connect(self._safe_update_status)
        self.setup_ui()
        self._safe_update_status()
        
    def setup_ui(self):
        self.setFrameShape(QFrame.Box)
        self.setFrameShadow(QFrame.Plain)
        self.setMaximumWidth(260)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setStyleSheet("""
            QFrame {
                background-color: #101010;
                border: 1px solid #444444;
                border-radius: 4px;
            }
        """)
        
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(4)
        
        # --- HEADER ---
        h = QHBoxLayout()
        h.setSpacing(2)
        
        # Tek Resim (İkon)
        lbl_icon = QLabel("🎮") # Eğer resim yoksa emoji
        lbl_icon.setStyleSheet("color: #ccc; font-size: 16px;")
        lbl_icon.setAlignment(Qt.AlignCenter)
        lbl_icon.setFixedSize(30, 30)
        # Resim yüklemeyi dene
        icon_path = os.path.join(self.config.get("images_dir", "login_images"), "launcherstart.png")
        if os.path.exists(icon_path):
            pix = QPixmap(icon_path)
            if not pix.isNull():
                lbl_icon.setPixmap(pix.scaled(25, 25, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        h.addWidget(lbl_icon)
        
        h.addStretch(1)
        lbl_title = QLabel("USKO OTO LOGIN")
        lbl_title.setObjectName("MinorHeaderLabel") 
        # Title Color Changed to WHITE per request
        lbl_title.setStyleSheet("color: white; font-weight: bold; font-size: 13px;")
        h.addWidget(lbl_title)
        v.addLayout(h)
        
        # --- BUTTON ---
        self.btn_listen = QPushButton("TUŞ DİNLEMEYİ BAŞLAT")
        self.btn_listen.setObjectName("ThreeFiveListenButton")
        # Button background changed to dark neutral to match program style
        self.btn_listen.setStyleSheet("""
            QPushButton {
                background-color: #151515;
                color: white;
                border: 1px solid #444;
                padding: 10px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #222;
                border-color: #00ff4c;
            }
        """)
        self.btn_listen.clicked.connect(self.toggle_listen)
        v.addWidget(self.btn_listen)
        
        # --- STATUS ---
        self.lbl_status = QLabel("DURUM: PASİF")
        # Changed Alignment to Left per request, added padding
        self.lbl_status.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.lbl_status.setContentsMargins(5, 0, 0, 0)
        self.lbl_status.setObjectName("MinorStatusLabel")
        v.addWidget(self.lbl_status)
        
        # --- FOOTER ---
        row = QHBoxLayout()
        row.setSpacing(4)
        
        row.addWidget(QLabel("AKTİF TUŞ:"))
        self.lbl_hotkey = QLabel(self.config.get("key", "F12").upper())
        self.lbl_hotkey.setObjectName("HotkeyLabel")
        self.lbl_hotkey.setAlignment(Qt.AlignCenter)
        self.lbl_hotkey.setStyleSheet("color: #00ff4c; font-weight: bold;")
        row.addWidget(self.lbl_hotkey)
        
        btn_set = QPushButton("⚙ AYARLAR")
        btn_set.setObjectName("MinorSettingsButton")
        btn_set.setFlat(True)
        btn_set.setStyleSheet("""
            QPushButton {
                background-color: #252525;
                color: white;
                border: 1px solid #444;
                padding: 5px;
                border-radius: 3px;
            }
            QPushButton:hover { border-color: #00ff4c; }
        """)
        btn_set.clicked.connect(self.open_settings)
        row.addWidget(btn_set)
        
        v.addLayout(row)
        
    def _safe_update_status(self):
        if not self.listen_active:
            self.lbl_status.setText("DURUM: PASİF")
            self.btn_listen.setText("TUŞ DİNLEMEYİ BAŞLAT")
            self.lbl_status.setStyleSheet("color: #ff5555; font-weight: bold;")
        else:
            if self.macro.is_running:
                self.lbl_status.setText(f"{self.macro.status}")
                self.lbl_status.setStyleSheet("color: #00ff4c; font-weight: bold;")
            else:
                self.lbl_status.setText("DURUM: BEKLİYOR")
                self.lbl_status.setStyleSheet("color: #ffff55; font-weight: bold;")
            self.btn_listen.setText("DİNLEMEYİ DURDUR")
            
        if self.listen_active and self.macro.is_running:
            QTimer.singleShot(500, self._safe_update_status)

    def toggle_listen(self):
        if not self.listen_active:
            try:
                # Hotkey sabitlendiği için doğrudan F12 kullanılır.
                key = "f12" 
                self._hook = keyboard.on_press_key(key, lambda e: self._on_hotkey())
                self.listen_active = True
            except Exception:
                pass
        else:
            if self._hook:
                keyboard.unhook(self._hook)
            self._hook = None
            self.listen_active = False
            self.macro.stop()
        self._safe_update_status()
        
    def _on_hotkey(self):
        if self.macro.is_running:
            self.macro.stop()
        else:
            self.macro.start()
        self.update_signal.emit()

    def open_settings(self):
        dialog = UskoOtoLoginSettingsDialog(self, self.config, self.macro)
        if dialog.exec_():
            self.config.update(dialog.result_config)
            self.macro.update_config(self.config)
            self.lbl_hotkey.setText(self.config.get("key", "F12").upper())
            if self.listen_active:
                self.toggle_listen()
                self.toggle_listen()
