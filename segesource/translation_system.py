# translation_system.py - BASİT JSON TABANLI SİSTEM
"""
Basit ve Hızlı Çeviri Sistemi
------------------------------
- Sadece JSON'dan yükler
- Google Translate YOK
- Cache var (hızlı)
- Hafif
"""

import json
import os
import sys


def _get_embedded_path(filename):
    """EXE içine gömülü dosya (translations.json gibi)"""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)

def _get_external_path(filename):
    """EXE'nin yanındaki dosya (translation_settings.json gibi)"""
    return os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), filename)


class TranslationManager:
    """Basit çeviri yöneticisi"""
    
    LANGUAGES = {
        "tr": "🇹🇷 Türkçe",
        "en": "🇬🇧 English", 
        "de": "🇩🇪 Deutsch",
        "fr": "🇫🇷 Français",
        "es": "🇪🇸 Español",
        "ru": "🇷🇺 Русский",
        "ar": "🇸🇦 العربية",
        "ja": "🇯🇵 日本語",
        "ko": "🇰🇷 한국어",
        "zh-cn": "🇨🇳 简体中文"
    }
    
    def __init__(self):
        self.current_language = "tr"
        self.translations = {}
        self.cache = {}
        self.settings_file = "translation_settings.json"
        
        self._load_translations()
        self._load_settings()
        
        # ============================================
        # MONKEY PATCH: TÜM DIALOGLARI OTOMATİK ÇEVİR!
        # ============================================
        self._install_dialog_hook()
        
        print(f"[ÇEVİRİ] {len(self.translations)} kelime yüklendi (Dil: {self.current_language})")
        print(f"[ÇEVİRİ] Dialog yakalama aktif - Tüm pencereler otomatik çevrilecek!")
    
    def _load_settings(self):
        """Dil ayarını yükle"""
        try:
            settings_path = _get_external_path(self.settings_file)
            if os.path.exists(settings_path):
                with open(settings_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.current_language = data.get("language", "tr")
        except:
            pass

    
    def save_settings(self):
        """Dil ayarını EXE'nin yanına kaydet"""
        try:
            save_path = _get_external_path(self.settings_file)
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump({"language": self.current_language}, f, ensure_ascii=False)
        except:
            pass
    
    def _load_translations(self):
        """translations.json'u yükle"""
        json_file = _get_embedded_path("translations.json")
        
        if not os.path.exists(json_file):
            print(f"[CEVIRI] translations.json bulunamadi: {json_file}")
            return
        
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                self.translations = json.load(f)
            print(f"[CEVIRI] translations.json yuklendi: {json_file}")
        except Exception as e:
            print(f"[CEVIRI] JSON yuklenemedi: {e}")
            self.translations = {}
        
    def set_language(self, lang_code):
        """Dili değiştir"""
        if lang_code in self.LANGUAGES:
            old_lang = self.current_language
            self.current_language = lang_code
            self.cache.clear()
            self.save_settings()
            return old_lang != lang_code
        return False
    
    def translate(self, text, target_lang=None):
        """Metni çevir"""
        if not text or not text.strip():
            return text
        
        if target_lang is None:
            target_lang = self.current_language
        
        # Türkçe ise çevirme
        if target_lang == "tr":
            return text
        
        # Sayıları çevirme
        clean_text = text.replace("%", "").replace(",", "").replace(".", "").replace("-", "").replace(":", "")
        if clean_text.isdigit():
            return text
        
        # Cache'de var mı?
        cache_key = f"{text}_{target_lang}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        # JSON'da var mı?
        result = text
        if text in self.translations:
            lang_dict = self.translations[text]
            if isinstance(lang_dict, dict):
                result = lang_dict.get(target_lang, text)
        
        # Cache'e kaydet
        self.cache[cache_key] = result
        return result
    
    def translate_widget_texts(self, widget):
        """Widget metinlerini çevir - GÜÇLÜ REKÜRSİF + AYARLAR DESTEĞİ
        FIX #16: TR ise en başta çık, alttaki recursive branch'i de tetikleme.
        """
        if self.current_language == "tr":
            return

        from PyQt5.QtWidgets import (
            QPushButton, QLabel, QGroupBox, QCheckBox,
            QRadioButton, QAction, QTabWidget, QMenu, QDialog, QTreeWidget
        )
        
        try:
            # ============================================
            # 1. KENDİNİ ÇEVİR
            # ============================================
            if isinstance(widget, QPushButton):
                original = widget.text()
                if original and original.strip() and len(original) > 0:
                    # Özel butonları atla
                    if original in ["?", "X", "─", "✕", "OK", "Cancel"]:
                        return
                    translated = self.translate(original)
                    if translated != original:
                        widget.setText(translated)
            
            elif isinstance(widget, QLabel):
                original = widget.text()
                if original and original.strip():
                    # FIX #43: 'V:' eşitlik değil startswith — 'V: 3.1.6' de atlansın
                    skip_prefixes = ("V:", "%", "http", "⏰", "👤", "📅", "🔔")
                    if (original.startswith(skip_prefixes) or
                        original.endswith("ms") or
                        "SEGE" in original.upper()):
                        return
                    
                    # "Cihaz Kimliği: XXX" formatı
                    if ":" in original and len(original.split(":")[-1]) > 10:
                        parts = original.split(":", 1)
                        parts[0] = self.translate(parts[0])
                        widget.setText(":".join(parts))
                    else:
                        translated = self.translate(original)
                        if translated != original:
                            widget.setText(translated)
            
            elif isinstance(widget, QGroupBox):
                original = widget.title()
                if original and original.strip():
                    translated = self.translate(original)
                    if translated != original:
                        widget.setTitle(translated)
            
            elif isinstance(widget, (QCheckBox, QRadioButton)):
                original = widget.text()
                if original and original.strip():
                    translated = self.translate(original)
                    if translated != original:
                        widget.setText(translated)
            
            elif isinstance(widget, QAction):
                original = widget.text()
                if original and original.strip():
                    translated = self.translate(original)
                    if translated != original:
                        widget.setText(translated)
            
            elif isinstance(widget, QTabWidget):
                for i in range(widget.count()):
                    original = widget.tabText(i)
                    if original and original.strip():
                        translated = self.translate(original)
                        if translated != original:
                            widget.setTabText(i, translated)
            
            elif isinstance(widget, QMenu):
                original = widget.title()
                if original and original.strip():
                    translated = self.translate(original)
                    if translated != original:
                        widget.setTitle(translated)
            
            # ============================================
            # 2. QTreeWidget ÖZEL İŞLEM (AYARLAR PENCERESİ)
            # ============================================
            elif isinstance(widget, QTreeWidget):
                # Tree item'ları çevir
                def translate_tree_item(item):
                    for col in range(item.columnCount()):
                        original = item.text(col)
                        if original and original.strip():
                            translated = self.translate(original)
                            if translated != original:
                                item.setText(col, translated)
                    # Alt item'ları da çevir
                    for i in range(item.childCount()):
                        translate_tree_item(item.child(i))
                
                # Root item'ları çevir
                root = widget.invisibleRootItem()
                for i in range(root.childCount()):
                    translate_tree_item(root.child(i))
            
            # ============================================
            # 3. REKÜRSİF - TÜM ÇOCUKLARI ÇEVİR
            # FIX #17: Dialog branch zaten findChildren ile derin tarıyor.
            # Recursive ve findChildren ikisi birden çalışınca aynı label
            # birden fazla kez çevriliyordu — dialog ise burada recursion'ı atla.
            # ============================================
            if not isinstance(widget, QDialog) and hasattr(widget, 'children'):
                for child in widget.children():
                    self.translate_widget_texts(child)

            # ============================================
            # 4. QDialog ÖZEL - findChildren ile DERİN TARAMA
            # ============================================
            if isinstance(widget, QDialog):
                # Tüm butonları bul ve çevir
                for btn in widget.findChildren(QPushButton):
                    original = btn.text()
                    if original and original.strip() and original not in ["?", "X", "─", "✕", "OK", "Cancel"]:
                        translated = self.translate(original)
                        if translated != original:
                            btn.setText(translated)
                
                # Tüm label'ları bul ve çevir
                for lbl in widget.findChildren(QLabel):
                    original = lbl.text()
                    if original and original.strip():
                        if not (original.startswith("%") or 
                               original.startswith("http") or
                               "SEGE" in original.upper()):
                            if ":" in original and len(original.split(":")[-1]) > 10:
                                parts = original.split(":", 1)
                                parts[0] = self.translate(parts[0])
                                lbl.setText(":".join(parts))
                            else:
                                translated = self.translate(original)
                                if translated != original:
                                    lbl.setText(translated)
                
                # Tüm checkbox'ları bul ve çevir
                for chk in widget.findChildren(QCheckBox):
                    original = chk.text()
                    if original and original.strip():
                        translated = self.translate(original)
                        if translated != original:
                            chk.setText(translated)
                
                # Tüm groupbox'ları bul ve çevir
                for gb in widget.findChildren(QGroupBox):
                    original = gb.title()
                    if original and original.strip():
                        translated = self.translate(original)
                        if translated != original:
                            gb.setTitle(translated)
                
                # Tüm tree widget'ları bul ve çevir
                for tree in widget.findChildren(QTreeWidget):
                    self.translate_widget_texts(tree)
        
        except Exception as e:
            print(f"[ÇEVİRİ HATASI] {e}")
            pass
    
    def get_available_languages(self):
        """Mevcut diller"""
        return self.LANGUAGES
    
    # ============================================
    # MONKEY PATCH: QDIALOG YAKALAMA SİSTEMİ
    # ============================================
    def _install_dialog_hook(self):
        """
        Tüm QDialog'ların exec_() metodunu yakalar ve açıldığında otomatik çevirir.
        FIX #18: Tek-sefer hook flag'i + TR'de no-op.
        """
        try:
            from PyQt5.QtWidgets import QDialog
            from PyQt5.QtCore import QTimer

            # Zaten yüklü mü? (nested wrap sonsuz döngüsünü engelle)
            if getattr(QDialog, "_sege_patched", False):
                return

            original_exec = QDialog.exec_

            def patched_exec(dialog_self):
                # TR'de hiçbir şey yapma (fast-path)
                if self.current_language != "tr":
                    QTimer.singleShot(50, lambda: self.translate_widget_texts(dialog_self))
                return original_exec(dialog_self)

            QDialog.exec_ = patched_exec
            QDialog._sege_patched = True

            print("[ÇEVİRİ] Dialog hook kuruldu (tek-sefer).")
        except Exception as e:
            print(f"[CEVIRI] Dialog hook kurulamadi: {e}")


# Global instance
_translation_manager = None

def get_translation_manager():
    global _translation_manager
    if _translation_manager is None:
        _translation_manager = TranslationManager()
    return _translation_manager

def translate(text, lang=None):
    return get_translation_manager().translate(text, lang)
