"""
系统托盘图标模块
支持状态指示器显示监控状态
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QBrush, QPen
from PySide6.QtWidgets import QSystemTrayIcon, QMenu


class StatusTrayIcon(QSystemTrayIcon):
    """带状态指示器的系统托盘图标"""
    
    # 信号
    show_window_requested = Signal()
    exit_requested = Signal()
    
    # 状态颜色映射
    STATUS_COLORS = {
        'normal': QColor(76, 175, 80),    # 绿色
        'warning': QColor(255, 193, 7),   # 黄色
        'error': QColor(244, 67, 54),     # 红色
        'disabled': None,                  # 无颜色（不显示指示器）
    }
    
    def __init__(self, base_icon_path: str, parent=None):
        super().__init__(parent)
        
        self._base_icon_path = base_icon_path
        self._current_status = 'disabled'
        
        # 加载基础图标
        self._base_pixmap = QPixmap(base_icon_path)
        if self._base_pixmap.isNull():
            # 创建默认图标
            self._base_pixmap = QPixmap(64, 64)
            self._base_pixmap.fill(Qt.transparent)
        
        # 初始化菜单
        self._init_menu()
        
        # 设置初始图标
        self._update_icon()
        
        # 连接双击事件
        self.activated.connect(self._on_activated)
    
    def _init_menu(self):
        """初始化右键菜单"""
        menu = QMenu()
        
        show_action = menu.addAction("显示主窗口")
        show_action.triggered.connect(self.show_window_requested.emit)
        
        menu.addSeparator()
        
        exit_action = menu.addAction("退出程序")
        exit_action.triggered.connect(self.exit_requested.emit)
        
        self.setContextMenu(menu)
    
    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason):
        """托盘图标激活事件"""
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_window_requested.emit()
    
    def set_status(self, status: str):
        """设置监控状态
        
        Args:
            status: 'normal', 'warning', 'error', 'disabled'
        """
        if status not in self.STATUS_COLORS:
            status = 'disabled'
        
        if self._current_status != status:
            self._current_status = status
            self._update_icon()
    
    def _update_icon(self):
        """更新托盘图标（叠加状态指示器）"""
        # 复制基础图标
        icon_pixmap = self._base_pixmap.copy()
        
        # 获取状态颜色
        status_color = self.STATUS_COLORS.get(self._current_status)
        
        if status_color is not None:
            # 在右下角绘制状态圆点
            painter = QPainter(icon_pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            
            # 计算圆点位置和大小
            icon_size = icon_pixmap.width()
            dot_size = max(16, int(icon_size // 2.5))  # 增大角标：大小约为图标的 40%

            margin = 2
            
            x = icon_size - dot_size - margin
            y = icon_size - dot_size - margin
            
            # 绘制白色边框
            painter.setPen(QPen(QColor(255, 255, 255), 2))
            painter.setBrush(QBrush(status_color))
            painter.drawEllipse(x, y, dot_size, dot_size)
            
            painter.end()
        
        self.setIcon(QIcon(icon_pixmap))
    
    def update_tooltip(self, message: str):
        """更新托盘提示文本"""
        self.setToolTip(f"FileRecorder\n{message}")
