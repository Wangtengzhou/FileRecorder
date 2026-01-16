"""
错误日志对话框
显示扫描错误和监控错误
"""
from datetime import datetime
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QTableWidget, QTableWidgetItem, QPushButton, QLabel,
    QHeaderView, QMessageBox, QFileDialog
)
from PySide6.QtCore import Qt


class ErrorLogDialog(QDialog):
    """错误日志对话框"""
    
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        
        self.setWindowTitle("错误日志")
        self.setMinimumSize(700, 500)
        
        self._init_ui()
        self._load_data()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        # 标签页
        self.tab_widget = QTabWidget()
        
        # 扫描错误标签页
        self.scan_error_tab = QWidget()
        self._init_scan_error_tab()
        self.tab_widget.addTab(self.scan_error_tab, "📁 扫描错误")
        
        # 监控错误标签页
        self.watcher_error_tab = QWidget()
        self._init_watcher_error_tab()
        self.tab_widget.addTab(self.watcher_error_tab, "📡 监控错误")
        
        layout.addWidget(self.tab_widget)
        
        # 底部按钮
        btn_layout = QHBoxLayout()
        
        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.clicked.connect(self._load_data)
        btn_layout.addWidget(refresh_btn)
        
        export_btn = QPushButton("📤 导出日志")
        export_btn.clicked.connect(self._on_export)
        btn_layout.addWidget(export_btn)
        
        btn_layout.addStretch()
        
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
    
    def _init_scan_error_tab(self):
        """初始化扫描错误标签页"""
        layout = QVBoxLayout(self.scan_error_tab)
        
        # 说明
        hint = QLabel("显示扫描过程中遇到的错误（文件访问失败、路径过长等）")
        hint.setStyleSheet("color: gray;")
        layout.addWidget(hint)
        
        # 表格
        self.scan_error_table = QTableWidget()
        self.scan_error_table.setColumnCount(4)
        self.scan_error_table.setHorizontalHeaderLabels(["时间", "路径", "来源", "错误信息"])
        
        header = self.scan_error_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        self.scan_error_table.setColumnWidth(0, 130)
        self.scan_error_table.setColumnWidth(2, 100)
        
        self.scan_error_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.scan_error_table.setEditTriggers(QTableWidget.NoEditTriggers)
        
        layout.addWidget(self.scan_error_table)
        
        # 操作按钮
        btn_layout = QHBoxLayout()
        
        clear_btn = QPushButton("清除已解决")
        clear_btn.clicked.connect(self._on_clear_scan_errors)
        btn_layout.addWidget(clear_btn)
        
        self.scan_error_count_label = QLabel("共 0 条记录")
        btn_layout.addWidget(self.scan_error_count_label)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
    
    def _init_watcher_error_tab(self):
        """初始化监控错误标签页"""
        layout = QVBoxLayout(self.watcher_error_tab)
        
        # 说明
        hint = QLabel("显示目录监控过程中遇到的错误（连接失败、权限问题等）")
        hint.setStyleSheet("color: gray;")
        layout.addWidget(hint)
        
        # 表格
        self.watcher_error_table = QTableWidget()
        self.watcher_error_table.setColumnCount(4)
        self.watcher_error_table.setHorizontalHeaderLabels(["时间", "目录", "状态", "错误信息"])
        
        header = self.watcher_error_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        self.watcher_error_table.setColumnWidth(0, 130)
        self.watcher_error_table.setColumnWidth(2, 80)
        
        self.watcher_error_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.watcher_error_table.setEditTriggers(QTableWidget.NoEditTriggers)
        
        layout.addWidget(self.watcher_error_table)
        
        # 操作按钮
        btn_layout = QHBoxLayout()
        
        retry_btn = QPushButton("立即重试")
        retry_btn.clicked.connect(self._on_retry_watcher)
        btn_layout.addWidget(retry_btn)
        
        self.watcher_error_count_label = QLabel("共 0 条记录")
        btn_layout.addWidget(self.watcher_error_count_label)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
    
    def _load_data(self):
        """加载数据"""
        self._load_scan_errors()
        self._load_watcher_errors()
    
    def _load_scan_errors(self):
        """加载扫描错误"""
        self.scan_error_table.setRowCount(0)
        
        # 从数据库加载
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT error_time, file_path, scan_source, error_message
                FROM scan_errors
                ORDER BY error_time DESC
                LIMIT 500
            """)
            
            for row in cursor.fetchall():
                row_idx = self.scan_error_table.rowCount()
                self.scan_error_table.insertRow(row_idx)
                
                # 时间
                try:
                    time_str = datetime.fromtimestamp(row['error_time']).strftime('%Y-%m-%d %H:%M')
                except:
                    time_str = ""
                self.scan_error_table.setItem(row_idx, 0, QTableWidgetItem(time_str))
                
                # 路径
                self.scan_error_table.setItem(row_idx, 1, QTableWidgetItem(row['file_path'] or ''))
                
                # 来源
                self.scan_error_table.setItem(row_idx, 2, QTableWidgetItem(row['scan_source'] or ''))
                
                # 错误信息
                self.scan_error_table.setItem(row_idx, 3, QTableWidgetItem(row['error_message'] or ''))
        
        count = self.scan_error_table.rowCount()
        self.scan_error_count_label.setText(f"共 {count} 条记录")
    
    def _load_watcher_errors(self):
        """加载监控错误"""
        self.watcher_error_table.setRowCount(0)
        
        # 从监控管理器获取当前错误状态
        parent = self.parent()
        if parent and hasattr(parent, '_watcher_manager') and parent._watcher_manager:
            status_info = parent._watcher_manager.get_status_info()
            error_paths = status_info.get('error_paths', [])
            
            for path in error_paths:
                row_idx = self.watcher_error_table.rowCount()
                self.watcher_error_table.insertRow(row_idx)
                
                # 时间
                time_str = datetime.now().strftime('%Y-%m-%d %H:%M')
                self.watcher_error_table.setItem(row_idx, 0, QTableWidgetItem(time_str))
                
                # 目录
                self.watcher_error_table.setItem(row_idx, 1, QTableWidgetItem(path))
                
                # 状态
                item = QTableWidgetItem("重试中")
                item.setForeground(Qt.darkYellow)
                self.watcher_error_table.setItem(row_idx, 2, item)
                
                # 错误信息
                self.watcher_error_table.setItem(row_idx, 3, QTableWidgetItem("连接失败，正在重试..."))
        
        count = self.watcher_error_table.rowCount()
        self.watcher_error_count_label.setText(f"共 {count} 条记录")
    
    def _on_clear_scan_errors(self):
        """清除扫描错误"""
        reply = QMessageBox.question(
            self, "确认",
            "确定要清除所有扫描错误记录吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM scan_errors")
            self._load_scan_errors()
            QMessageBox.information(self, "完成", "已清除所有扫描错误记录")
    
    def _on_retry_watcher(self):
        """立即重试监控"""
        parent = self.parent()
        if parent and hasattr(parent, '_watcher_manager') and parent._watcher_manager:
            parent._watcher_manager.restart()
            QMessageBox.information(self, "完成", "已重新启动监控")
            self._load_watcher_errors()
    
    def _on_export(self):
        """导出日志"""
        filename, _ = QFileDialog.getSaveFileName(
            self, "导出日志",
            f"error_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            "文本文件 (*.txt)"
        )
        
        if not filename:
            return
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("=" * 50 + "\n")
            f.write("扫描错误\n")
            f.write("=" * 50 + "\n\n")
            
            for i in range(self.scan_error_table.rowCount()):
                time_str = self.scan_error_table.item(i, 0).text()
                path = self.scan_error_table.item(i, 1).text()
                error_type = self.scan_error_table.item(i, 2).text()
                message = self.scan_error_table.item(i, 3).text()
                f.write(f"[{time_str}] {error_type}\n")
                f.write(f"  路径: {path}\n")
                f.write(f"  详情: {message}\n\n")
            
            f.write("\n" + "=" * 50 + "\n")
            f.write("监控错误\n")
            f.write("=" * 50 + "\n\n")
            
            for i in range(self.watcher_error_table.rowCount()):
                time_str = self.watcher_error_table.item(i, 0).text()
                path = self.watcher_error_table.item(i, 1).text()
                status = self.watcher_error_table.item(i, 2).text()
                message = self.watcher_error_table.item(i, 3).text()
                f.write(f"[{time_str}] {status}\n")
                f.write(f"  目录: {path}\n")
                f.write(f"  信息: {message}\n\n")
        
        QMessageBox.information(self, "导出完成", f"日志已导出到:\n{filename}")
