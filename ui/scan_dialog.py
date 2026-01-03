"""
FileRecorder 多文件夹扫描对话框
支持选中多个文件夹后依次扫描
"""
from pathlib import Path
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QFileDialog, QLineEdit, QProgressBar,
    QGroupBox, QMessageBox
)


class MultiFolderScanDialog(QDialog):
    """多文件夹扫描对话框"""
    
    # 信号：开始扫描（传递路径列表）
    scan_requested = Signal(list)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("多文件夹扫描")
        self.setMinimumSize(500, 400)
        
        self._init_ui()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        # 说明文字
        info_label = QLabel(
            "添加多个文件夹路径，点击开始后将依次扫描。\n"
            "支持本地路径和网络路径（如 \\\\服务器\\共享文件夹）"
        )
        info_label.setStyleSheet("color: gray;")
        layout.addWidget(info_label)
        
        # 路径列表
        list_group = QGroupBox("待扫描路径列表")
        list_layout = QVBoxLayout(list_group)
        
        self.path_list = QListWidget()
        self.path_list.setSelectionMode(QListWidget.ExtendedSelection)
        list_layout.addWidget(self.path_list)
        
        # 路径操作按钮
        btn_layout = QHBoxLayout()
        
        add_local_btn = QPushButton("📁 添加本地文件夹")
        add_local_btn.clicked.connect(self._on_add_local)
        btn_layout.addWidget(add_local_btn)
        
        add_network_btn = QPushButton("🌐 添加网络路径")
        add_network_btn.clicked.connect(self._on_add_network)
        btn_layout.addWidget(add_network_btn)
        
        remove_btn = QPushButton("🗑️ 移除选中")
        remove_btn.clicked.connect(self._on_remove_selected)
        btn_layout.addWidget(remove_btn)
        
        clear_btn = QPushButton("清空列表")
        clear_btn.clicked.connect(self._on_clear)
        btn_layout.addWidget(clear_btn)
        
        list_layout.addLayout(btn_layout)
        layout.addWidget(list_group)
        
        # 网络路径输入
        network_group = QGroupBox("快速添加网络路径")
        network_layout = QHBoxLayout(network_group)
        
        self.network_input = QLineEdit()
        self.network_input.setPlaceholderText("输入网络路径，如 \\\\Synology\\File\\Backup")
        self.network_input.returnPressed.connect(self._on_add_network_input)
        network_layout.addWidget(self.network_input)
        
        add_input_btn = QPushButton("添加")
        add_input_btn.clicked.connect(self._on_add_network_input)
        network_layout.addWidget(add_input_btn)
        
        layout.addWidget(network_group)
        
        # 操作按钮
        action_layout = QHBoxLayout()
        action_layout.addStretch()
        
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        action_layout.addWidget(cancel_btn)
        
        self.scan_btn = QPushButton("🔍 开始扫描")
        self.scan_btn.setDefault(True)
        self.scan_btn.clicked.connect(self._on_start_scan)
        action_layout.addWidget(self.scan_btn)
        
        layout.addLayout(action_layout)
    
    def _on_add_local(self):
        """添加本地文件夹"""
        paths = QFileDialog.getExistingDirectory(
            self, "选择要扫描的目录",
            "",
            QFileDialog.ShowDirsOnly
        )
        if paths:
            self._add_path(paths)
    
    def _on_add_network(self):
        """添加网络路径对话框"""
        from PySide6.QtWidgets import QInputDialog
        path, ok = QInputDialog.getText(
            self, "输入网络路径",
            "请输入网络共享路径：",
            text="\\\\Synology\\File\\Backup"
        )
        if ok and path.strip():
            self._add_path(path.strip())
    
    def _on_add_network_input(self):
        """从输入框添加网络路径"""
        path = self.network_input.text().strip()
        if path:
            self._add_path(path)
            self.network_input.clear()
    
    def _add_path(self, path: str):
        """添加路径到列表"""
        # 检查是否已存在
        for i in range(self.path_list.count()):
            if self.path_list.item(i).text() == path:
                QMessageBox.warning(self, "提示", f"路径已在列表中:\n{path}")
                return
        
        item = QListWidgetItem(path)
        self.path_list.addItem(item)
    
    def _on_remove_selected(self):
        """移除选中项"""
        for item in self.path_list.selectedItems():
            self.path_list.takeItem(self.path_list.row(item))
    
    def _on_clear(self):
        """清空列表"""
        self.path_list.clear()
    
    def _on_start_scan(self):
        """开始扫描"""
        paths = []
        for i in range(self.path_list.count()):
            paths.append(self.path_list.item(i).text())
        
        if not paths:
            QMessageBox.warning(self, "提示", "请先添加要扫描的路径")
            return
        
        self.scan_requested.emit(paths)
        self.accept()
    
    def get_paths(self) -> list:
        """获取所有路径"""
        paths = []
        for i in range(self.path_list.count()):
            paths.append(self.path_list.item(i).text())
        return paths
