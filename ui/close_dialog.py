"""
关闭确认对话框
首次关闭时询问用户是最小化到托盘还是退出
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QCheckBox
)


class CloseConfirmDialog(QDialog):
    """关闭确认对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("关闭确认")
        self.setModal(True)
        self.setFixedWidth(350)
        
        # 返回值
        self.close_to_tray = True  # True=最小化, False=退出
        self.remember = False      # 是否记住选择
        
        self._init_ui()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # 提示文字
        label = QLabel("请选择关闭窗口时的行为：")
        label.setStyleSheet("font-size: 14px;")
        layout.addWidget(label)
        
        # 按钮区域
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        tray_btn = QPushButton("最小化到托盘")
        tray_btn.setMinimumHeight(40)
        tray_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 10px 20px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        tray_btn.clicked.connect(self._on_tray)
        btn_layout.addWidget(tray_btn)
        
        exit_btn = QPushButton("退出程序")
        exit_btn.setMinimumHeight(40)
        exit_btn.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 10px 20px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
        """)
        exit_btn.clicked.connect(self._on_exit)
        btn_layout.addWidget(exit_btn)
        
        layout.addLayout(btn_layout)
        
        # 记住选择复选框
        self.remember_cb = QCheckBox("记住我的选择（可在设置中修改）")
        layout.addWidget(self.remember_cb)
    
    def _on_tray(self):
        """最小化到托盘"""
        self.close_to_tray = True
        self.remember = self.remember_cb.isChecked()
        self.accept()
    
    def _on_exit(self):
        """退出程序"""
        self.close_to_tray = False
        self.remember = self.remember_cb.isChecked()
        self.accept()
