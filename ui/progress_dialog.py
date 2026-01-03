"""
FileRecorder 进度对话框
用于扫描/删除操作的模态进度显示
"""
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar,
    QPushButton, QMessageBox
)


class ScanProgressDialog(QDialog):
    """扫描/删除进度对话框（模态）"""
    
    # 信号：用户确认终止
    stop_requested = Signal()
    
    def __init__(self, title: str = "正在扫描", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)  # 模态窗口
        self.setMinimumWidth(450)
        self.setWindowFlags(
            Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint
        )  # 禁用关闭按钮
        
        self._is_stopping = False
        self._init_ui()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # 标题图标
        self.title_label = QLabel("🔍 正在扫描...")
        self.title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(self.title_label)
        
        # 当前文件（固定高度，避免下方元素跳动）
        self.current_label = QLabel("准备中...")
        self.current_label.setStyleSheet("color: #666;")
        self.current_label.setWordWrap(False)  # 单行显示
        self.current_label.setFixedHeight(25)  # 固定高度
        self.current_label.setMinimumWidth(400)
        layout.addWidget(self.current_label)
        
        # 已扫描数量
        self.count_label = QLabel("已扫描: 0 个项目")
        self.count_label.setStyleSheet("font-size: 14px;")
        layout.addWidget(self.count_label)
        
        # 成果展示区域（初始隐藏，完成时显示）
        self.success_label = QLabel()
        self.success_label.setStyleSheet("font-size: 15px; color: #2e7d32; margin: 5px 0;")
        self.success_label.hide()
        layout.addWidget(self.success_label)
        
        self.error_label = QLabel()
        self.error_label.setStyleSheet("font-size: 14px; color: #c62828; margin: 5px 0;")
        self.error_label.hide()
        layout.addWidget(self.error_label)
        
        self.hint_label = QLabel("💡 点击菜单「工具 → 查看扫描错误」可查看详情")
        self.hint_label.setStyleSheet("font-size: 12px; color: #666; margin: 5px 0;")
        self.hint_label.hide()
        layout.addWidget(self.hint_label)
        
        # 进度条（固定蓝色，不随焦点变化）
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # 不确定模式
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setMinimumHeight(20)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #ccc;
                border-radius: 5px;
                background-color: #e0e0e0;
            }
            QProgressBar::chunk {
                background-color: #2196F3;
                border-radius: 4px;
            }
        """)
        layout.addWidget(self.progress_bar)
        
        # 终止按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.stop_btn = QPushButton("⏹️ 终止任务")
        self.stop_btn.setMinimumWidth(120)
        self.stop_btn.clicked.connect(self._on_stop_clicked)
        btn_layout.addWidget(self.stop_btn)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
    
    def set_title(self, title: str, icon: str = "🔍"):
        """设置标题"""
        self.title_label.setText(f"{icon} {title}")
        self.setWindowTitle(title)
    
    @Slot(int, int, str)
    def update_progress(self, current: int, total: int, filename: str):
        """更新进度"""
        # 更新计数
        self.count_label.setText(f"已扫描: {current:,} 个项目")
        
        # 更新当前文件（截断过长路径）
        display_path = filename
        if len(display_path) > 60:
            display_path = "..." + display_path[-57:]
        self.current_label.setText(f"当前: {display_path}")
    
    def _on_stop_clicked(self):
        """终止按钮点击"""
        if self._is_stopping:
            return
        
        # 弹出确认对话框
        reply = QMessageBox.warning(
            self,
            "确认终止",
            "确定要终止当前任务吗？\n\n"
            "⚠️ 已扫描的数据将保留在索引中。\n"
            "如需清理，请手动右键删除该路径索引。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self._is_stopping = True
            self.stop_btn.setEnabled(False)
            self.stop_btn.setText("正在终止...")
            self.title_label.setText("⏳ 正在终止...")
            self.stop_requested.emit()
    
    def set_finished(self, success_count: int, error_count: int = 0):
        """设置为完成状态 - 成果展示"""
        # 隐藏扫描中的内容
        self.current_label.hide()
        self.count_label.hide()
        
        # 修改标题
        self.title_label.setText("✅ 扫描完成")
        
        # 修改进度条为完成状态
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        
        # 显示成果展示（使用预创建的控件）
        self.success_label.setText(f"📁 成功扫描: {success_count:,} 个项目")
        self.success_label.show()
        
        # 失败数量（仅在有错误时显示）
        if error_count > 0:
            self.error_label.setText(f"⚠️ 读取失败: {error_count:,} 个项目")
            self.error_label.show()
            self.hint_label.show()
        
        # 修改按钮
        self.stop_btn.setText("完成")
        self.stop_btn.clicked.disconnect()
        self.stop_btn.clicked.connect(self.accept)
    
    def set_cancelled(self):
        """设置为已取消状态"""
        self.title_label.setText("⚠️ 任务已终止")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.stop_btn.setText("关闭")
        self.stop_btn.setEnabled(True)
        self.stop_btn.clicked.disconnect()
        self.stop_btn.clicked.connect(self.accept)
    
    def closeEvent(self, event):
        """禁止直接关闭（必须通过按钮）"""
        if self._is_stopping or self.stop_btn.text() == "关闭":
            event.accept()
        else:
            event.ignore()
