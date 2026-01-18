"""
FileRecorder - 智能文件索引助手
https://github.com/Wangtengzhou/FileRecorder

主题管理模块 - 支持深色/浅色/自动主题
"""
import sys
from PySide6.QtWidgets import QApplication, QStyleFactory
from PySide6.QtGui import QPalette, QColor, Qt
from PySide6.QtCore import QObject, QTimer, Signal

class ThemeManager(QObject):
    theme_changed = Signal(bool)  # is_dark

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_is_dark = None
        self._auto_check_timer = QTimer(self)
        self._auto_check_timer.timeout.connect(self._check_system_theme)
        self._mode = "auto"
        
        # 安装全局事件过滤器以捕获新窗口显示
        QTimer.singleShot(0, self._install_event_filter)

    def _install_event_filter(self):
        app = QApplication.instance()
        if app:
            app.installEventFilter(self)

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QWidget, QApplication
        
        # 1. 监听应用程序级别的调色板变化 (系统主题变更信号)
        if obj is QApplication.instance() and event.type() == QEvent.ApplicationPaletteChange:
            if self._current_is_dark is not None:
                # 系统主题变了，Windows可能会重置标题栏，强制重设
                self._enforce_title_bars_delayed()
            return False

        # 2. 监听窗口显示事件 (新窗口/弹窗)
        # 只处理 QWidget 及其子类
        if isinstance(obj, QWidget):
            if event.type() == QEvent.Show:
                if obj.isWindow() and self._current_is_dark is not None:
                    # 新窗口显示，设置标题栏
                    QTimer.singleShot(10, lambda: set_window_dark_title_bar(obj, self._current_is_dark))
            # 某些情况下 ThemeChange 也可以作为补充
            elif event.type() == QEvent.ThemeChange:
                if obj.isWindow() and self._current_is_dark is not None:
                     QTimer.singleShot(10, lambda: set_window_dark_title_bar(obj, self._current_is_dark))
                     
        return False

    def _enforce_title_bars_delayed(self):
        """延迟强制刷新所有窗口标题栏"""
        QTimer.singleShot(100, self._enforce_title_bars)
        QTimer.singleShot(500, self._enforce_title_bars) # 双重保险

    def _enforce_title_bars(self):
        """强制刷新所有顶层窗口标题栏"""
        app = QApplication.instance()
        if not app: return
        is_dark = self._current_is_dark
        if is_dark is None: return
        
        for widget in app.topLevelWidgets():
            if widget.isWindow():
                set_window_dark_title_bar(widget, is_dark)

    def start_auto_check(self):
        """开始自动检测系统主题变化"""
        self._check_system_theme() # 立即检测一次
        self._auto_check_timer.start(2000) # 每2秒检测一次

    def stop_auto_check(self):
        self._auto_check_timer.stop()

    def set_mode(self, mode: str):
        self._mode = mode
        if mode == "auto":
            self.start_auto_check()
        else:
            self.stop_auto_check()
            self.apply_theme(mode)

    def _check_system_theme(self):
        if self._mode != "auto":
            return
            
        is_dark = is_windows_dark_mode()
        # 如果这是第一次检测，或者状态发生了改变
        if self._current_is_dark is None or self._current_is_dark != is_dark:
            self.apply_theme("auto")

    def apply_theme(self, theme: str = "auto") -> bool:
        """应用主题，返回是否为深色"""
        app = QApplication.instance()
        
        if theme == "auto":
            is_dark = is_windows_dark_mode()
        else:
            is_dark = (theme == "dark")
            
        self._current_is_dark = is_dark
        
        if is_dark:
            self._apply_dark_theme(app)
        else:
            self._apply_light_theme(app)
            
        # 设置所有顶层窗口的标题栏
        for widget in app.topLevelWidgets():
            if widget.isWindow():
                set_window_dark_title_bar(widget, is_dark)
                
        # 移除强制全量 widget update，改为只让 app 处理 style 变化
        # style 变化会自动触发大部分重绘
        return is_dark

    def _apply_dark_theme(self, app):
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(53, 53, 53))
        palette.setColor(QPalette.WindowText, Qt.white)
        palette.setColor(QPalette.Base, QColor(42, 42, 42))
        palette.setColor(QPalette.AlternateBase, QColor(66, 66, 66))
        palette.setColor(QPalette.ToolTipBase, QColor(53, 53, 53))
        palette.setColor(QPalette.ToolTipText, Qt.white)
        palette.setColor(QPalette.Text, Qt.white)
        palette.setColor(QPalette.Button, QColor(53, 53, 53))
        palette.setColor(QPalette.ButtonText, Qt.white)
        palette.setColor(QPalette.BrightText, Qt.red)
        palette.setColor(QPalette.Link, QColor(42, 130, 218))
        palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
        palette.setColor(QPalette.HighlightedText, Qt.black)
        palette.setColor(QPalette.Disabled, QPalette.WindowText, QColor(127, 127, 127))
        palette.setColor(QPalette.Disabled, QPalette.Text, QColor(127, 127, 127))
        palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(127, 127, 127))
        app.setPalette(palette)
        
        app.setStyleSheet("""
            QTableView, QTreeWidget, QListView, QHeaderView {
                background-color: #2a2a2a;
                color: white;
                alternate-background-color: #323232;
            }
            QHeaderView::section {
                background-color: #353535;
                color: white;
                border: 1px solid #555;
            }
            QTableView::item, QTreeWidget::item, QListView::item {
                background-color: #2a2a2a;
                color: white;
            }
            QTableView::item:selected, QTreeWidget::item:selected, QListView::item:selected {
                background-color: #2a82da;
                color: white;
            }
            QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QComboBox {
                background-color: #2a2a2a;
                color: white;
                border: 1px solid #555;
            }
            QCheckBox::indicator:unchecked {
                background-color: transparent;
                border: 1px solid #888888;
            }
        """)

    def _apply_light_theme(self, app):
        # 显式构造浅色 Palette，防止受系统深色模式影响
        palette = QStyleFactory.create('Fusion').standardPalette()
        # 确保关键颜色是浅色的
        palette.setColor(QPalette.Window, QColor(240, 240, 240))
        palette.setColor(QPalette.WindowText, Qt.black)
        palette.setColor(QPalette.Base, Qt.white)
        palette.setColor(QPalette.AlternateBase, QColor(245, 245, 245))
        palette.setColor(QPalette.Text, Qt.black)
        palette.setColor(QPalette.Button, QColor(240, 240, 240))
        palette.setColor(QPalette.ButtonText, Qt.black)
        palette.setColor(QPalette.Highlight, QColor(48, 140, 198))
        palette.setColor(QPalette.HighlightedText, Qt.white)
        app.setPalette(palette)
        
        # 清除深色样式表，保留必要的修复
        app.setStyleSheet("""
            QCheckBox::indicator:unchecked {
                background-color: transparent;
                border: 1px solid #888888;
            }
        """)

def is_windows_dark_mode():
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        )
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        winreg.CloseKey(key)
        # AppsUseLightTheme: 1=Light, 0=Dark
        return value == 0 
    except:
        return False

def set_window_dark_title_bar(window, dark: bool):
    try:
        import ctypes
        # 尝试获取 HWND
        if hasattr(window, "windowHandle") and window.windowHandle():
            hwnd = int(window.windowHandle().winId())
        else:
            hwnd = int(window.winId())
            
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        value = ctypes.c_int(1 if dark else 0)
        
        # 尝试使用新的 Attribute ID (20)
        try:
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
                ctypes.byref(value), ctypes.sizeof(value)
            )
        except OSError:
            # 如果失败，尝试旧的 (19)
            try:
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE_BEFORE_20H1,
                    ctypes.byref(value), ctypes.sizeof(value)
                )
            except:
                pass
        
        # 强制刷新标题栏 (SWP_FRAMECHANGED)
        # 强制刷新标题栏 (SWP_FRAMECHANGED)
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_NOZORDER = 0x0004
        SWP_FRAMECHANGED = 0x0020
        ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED)
    except Exception:
        # print(f"Title bar error: {e}")
        pass

# 全局单例
theme_manager = ThemeManager()
