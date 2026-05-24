import json
import os
from PyQt5.QtWidgets import QWidget, QApplication, QMessageBox, QRubberBand
from PyQt5.QtCore import Qt, QRect, QObject, QPoint, QSize, QTimer
from PyQt5.QtGui import QPainter, QPen, QColor, QCursor, QPalette

# ============================================================
#  YARDIMCI: KAYITLI BÖLGEYİ GÖSTEREN YEŞİL KUTU
# ============================================================
class RegionVisualizerOverlay(QWidget):
    """
    Kaydedilmiş bölgeyi gösteren basit, yeşil çerçeveli overlay.
    İçi boştur ve tıklamaların altından geçmesine izin verir.
    """
    def __init__(self, region_data, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Kullanıcının içinden tıklayabilmesi için
        self.setWindowFlags(self.windowFlags() | Qt.WindowTransparentForInput)

        # JSON'dan gelen gerçek koordinatları kullan
        x = region_data['x']
        y = region_data['y']
        w = region_data['w']
        h = region_data['h']
        self.setGeometry(x, y, w, h)
        self.show() 

    def paintEvent(self, event):
        p = QPainter(self)
        p.setPen(QPen(Qt.green, 4))
        p.setBrush(Qt.NoBrush)
        p.drawRect(self.rect().adjusted(2, 2, -3, -3))

# ============================================================
#  SNIPPING TOOL TARZI ALAN SEÇİCİ (MODERN YÖNTEM)
# ============================================================
class SnippingOverlay(QWidget):
    def __init__(self, on_selected_callback):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        
        # Tüm ekranları kapla
        desktop = QApplication.desktop()
        self.setGeometry(desktop.geometry())
        
        self.setWindowOpacity(0.3)
        self.setStyleSheet("background-color: black;")
        self.on_selected_callback = on_selected_callback
        self.origin = QPoint()
        
        self.rubberBand = QRubberBand(QRubberBand.Rectangle, self)

        # --- YENİ KOD: Kırmızı Palette Tanımla ---
        red_palette = QPalette()
        red_palette.setColor(QPalette.Highlight, QColor(255, 0, 0))
        self.rubberBand.setPalette(red_palette)

        self.setCursor(Qt.CrossCursor)
        self._callback_fired = False  # FIX #50: double-fire guard
        self.show()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.origin = event.pos()
            self.rubberBand.setGeometry(QRect(self.origin, QSize()))
            self.rubberBand.show()
        elif event.button() == Qt.RightButton:
            self.close()

    def mouseMoveEvent(self, event):
        if not self.origin.isNull():
            self.rubberBand.setGeometry(QRect(self.origin, event.pos()).normalized())

    def mouseReleaseEvent(self, event):
        """FIX #50: Double-fire'ı _callback_fired flag ile engelle.
        Önce flag'i set et, sonra close ve callback sırala.
        """
        if event.button() == Qt.LeftButton:
            rect = self.rubberBand.geometry()
            global_pos = self.mapToGlobal(rect.topLeft())
            final_rect = QRect(global_pos, rect.size())
            self._callback_fired = True
            self.close()
            if final_rect.width() > 10 and final_rect.height() > 10:
                self.on_selected_callback(final_rect)
            else:
                self.on_selected_callback(QRect(0, 0, 0, 0))

    def closeEvent(self, event):
        """FIX #50: Sadece daha önce fire edilmediyse cancel callback at."""
        if not getattr(self, '_callback_fired', False):
            if hasattr(self, 'on_selected_callback') and self.on_selected_callback:
                self._callback_fired = True
                self.on_selected_callback(QRect(0, 0, 0, 0))
        event.accept()

# ============================================================
#  1. SINGLE SCANNER (1'Lİ TARAMA) - ÇİFT İŞLEVLİ
# ============================================================
class SingleScanner(QObject):
    def __init__(self, json_path=None, parent=None):
        super().__init__(parent)
        # FIX #49: relative path yerine core.paths.single_json_path
        if json_path is None:
            try:
                from core.paths import single_json_path
                json_path = single_json_path()
            except Exception:
                json_path = "1LI_ALANI.json"
        self.json_path = json_path
        self.selector = None
        self.visualizer = None

    def toggle_overlay(self):
        # SOL BUTON: ALAN SEÇ ve KAYDET
        if self.selector: return
        self.selector = SnippingOverlay(self.on_area_selected)

    def save_region(self):
        # SAĞ BUTON: GÖSTER / GİZLE (Yeşil Çerçeve)
        try:
            with open(self.json_path, "r") as f:
                data = json.load(f)
        except Exception:
            if self.parent():
                QMessageBox.warning(self.parent(), "UYARI", "Kayıtlı bir tarama alanı yok.")
            return

        if self.visualizer is None:
            self.visualizer = RegionVisualizerOverlay(data, parent=self.parent())
        elif self.visualizer.isVisible():
            self.visualizer.close()
            self.visualizer = None
        else:
            self.visualizer.show()

    def on_area_selected(self, rect):
        # Snipping Tool seçimi bitince otomatik çağrılır
        
        self.selector = None # Takılı kalmaması için ilk iş TEMİZLE
        
        # Seçim yapılmadıysa (Sağ tık veya sadece tık)
        if rect.width() < 10 or rect.height() < 10:
            if self.parent() and rect.width() > 0: # Eğer tıklandıysa (0x0 değilse)
                 QMessageBox.warning(self.parent(), "UYARI", 
                                    "Alan çok küçük. Tekrar deneyin.")
            # Sağ tık (0x0) ise sessizce çık.
            return 

        data = {
            "x": rect.x(), "y": rect.y(),
            "w": rect.width(), "h": rect.height()
        }
        self.save_to_json(data)
        
    def save_to_json(self, data):
        try:
            with open(self.json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            
            if self.parent():
                QMessageBox.information(self.parent(), "BAŞARILI", 
                                      f"1'li tarama alanı kaydedildi.\n"
                                      f"X:{data['x']} Y:{data['y']} W:{data['w']} H:{data['h']}")
            
            # YENİ KAYIT YAPILDI: Görselleştirici açıksa kapatıp yenisini göster
            if self.visualizer:
                self.visualizer.close()
                self.visualizer = None
                self.save_region() # Yeni koordinatlarla tekrar göster (Sağ butonun işlevi)

        except Exception as e:
            print(f"Kayıt hatası: {e}")


# ============================================================
#  2. BUFF SCANNER - ÇİFT İŞLEVLİ
# ============================================================
class BuffScanner(QObject):
    def __init__(self, json_path=None, parent=None):
        super().__init__(parent)
        # FIX #49: relative path yerine core.paths.buff_json_path
        if json_path is None:
            try:
                from core.paths import buff_json_path
                json_path = buff_json_path()
            except Exception:
                json_path = "BUFF_ALANI.json"
        self.json_path = json_path
        self.selector = None
        self.visualizer = None

    def toggle_guide_overlay(self):
        # SOL BUTON: ALAN SEÇ ve KAYDET
        if self.selector: return
        self.selector = SnippingOverlay(self.on_area_selected)

    def read_skills(self): 
        # SAĞ BUTON: GÖSTER / GİZLE (Yeşil Çerçeve)
        try:
            with open(self.json_path, "r") as f:
                data = json.load(f)
        except Exception:
            if self.parent():
                QMessageBox.warning(self.parent(), "UYARI", "Kayıtlı bir buff alanı yok.")
            return

        if self.visualizer is None:
            self.visualizer = RegionVisualizerOverlay(data, parent=self.parent())
        elif self.visualizer.isVisible():
            self.visualizer.close()
            self.visualizer = None
        else:
            self.visualizer.show()


    def on_area_selected(self, rect):
        # Snipping Tool seçimi bitince otomatik çağrılır
        
        self.selector = None # TAKILI KALMAMASI İÇİN İLK İŞ TEMİZLE
        
        if rect.width() < 10 or rect.height() < 10:
            if self.parent() and rect.width() > 0:
                QMessageBox.warning(self.parent(), "UYARI", 
                                    "Alan çok küçük. Tekrar deneyin.")
            return

        data = {
            "x": rect.x(), "y": rect.y(),
            "w": rect.width(), "h": rect.height()
        }
        self.save_to_json(data)

    def save_to_json(self, data):
        try:
            with open(self.json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            if self.parent():
                QMessageBox.information(self.parent(), "KAYIT", 
                                  f"Buff alanı kaydedildi.\nX:{data['x']} Y:{data['y']} W:{data['w']} H:{data['h']}")
            
            # YENİ KAYIT YAPILDI: Görselleştirici açıksa kapatıp yenisini göster
            if self.visualizer:
                self.visualizer.close()
                self.visualizer = None
                self.read_skills() # Yeni koordinatlarla tekrar göster (Sağ butonun işlevi)
        except Exception as e:
            print(f"Kayıt hatası: {e}")
