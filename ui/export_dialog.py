"""
导出进度对话框
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QProgressBar, QPushButton
)


class ExportProgressDialog(QDialog):
    """导出进度对话框"""
    
    cancelled = Signal()  # 取消信号
    
    def __init__(self, title: str = "导出中", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedSize(400, 150)
        self.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.CustomizeWindowHint)
        self.setModal(True)
        
        self._cancelled = False
        self._init_ui()
    
    def _init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        
        # 状态标签
        self.status_label = QLabel("准备中...")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        # 详情标签
        self.detail_label = QLabel("")
        self.detail_label.setStyleSheet("color: gray; font-size: 11px;")
        self.detail_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.detail_label)
        
        # 取消按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self.cancel_btn)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
    
    def update_progress(self, current: int, total: int, message: str = ""):
        """更新进度"""
        if total > 0:
            percent = int(current * 100 / total)
            self.progress_bar.setValue(percent)
            self.status_label.setText(f"正在导出... {percent}%")
        else:
            self.status_label.setText(message)
        
        if message:
            # 截断过长的消息
            if len(message) > 50:
                message = message[:25] + "..." + message[-22:]
            self.detail_label.setText(message)
    
    def set_finished(self):
        """设置完成状态"""
        self.progress_bar.setValue(100)
        self.status_label.setText("导出完成")
        self.cancel_btn.setText("关闭")
    
    def is_cancelled(self) -> bool:
        """检查是否被取消"""
        return self._cancelled
    
    def _on_cancel(self):
        """点击取消按钮"""
        if self.cancel_btn.text() == "关闭":
            self.accept()
        else:
            self._cancelled = True
            self.cancelled.emit()
            self.reject()
