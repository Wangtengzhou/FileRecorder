"""
变化检测弹窗
第一层：简洁提示有多少目录发生变化
第二层：详细选择要更新的目录，显示具体文件变化
"""
from datetime import datetime
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTreeWidget, QTreeWidgetItem, QCheckBox, QMessageBox, QHeaderView,
    QProgressBar
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QColor

from watcher.reconciler import FolderChange


class ReconcileProgressDialog(QDialog):
    """
    对账进度弹窗：显示启动时检测进度
    """
    
    def __init__(self, folder_count: int, parent=None):
        super().__init__(parent)
        self.folder_count = folder_count
        self.current_index = 0
        
        self.setWindowTitle("正在检测变化...")
        self.setMinimumWidth(400)
        self.setModal(True)
        # 无关闭按钮
        self.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint)
        
        self._init_ui()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        
        # 图标和消息
        self.msg_label = QLabel(f"正在检测 {self.folder_count} 个监控目录...")
        self.msg_label.setStyleSheet("font-size: 14px;")
        layout.addWidget(self.msg_label)
        
        # 当前目录
        self.current_label = QLabel("准备中...")
        self.current_label.setStyleSheet("color: #666;")
        self.current_label.setWordWrap(True)
        layout.addWidget(self.current_label)
        
        # 进度条
        self.progress = QProgressBar()
        self.progress.setRange(0, self.folder_count)
        self.progress.setValue(0)
        layout.addWidget(self.progress)
    
    def update_progress(self, index: int, folder_path: str):
        """更新进度"""
        self.current_index = index
        self.progress.setValue(index)
        self.current_label.setText(f"检测: {folder_path}")
        # 强制刷新 UI
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
    
    def finish(self):
        """完成检测"""
        self.progress.setValue(self.folder_count)
        self.current_label.setText("检测完成")
        QTimer.singleShot(300, self.accept)


class ChangeAlertDialog(QDialog):
    """
    第一层弹窗：简洁提示
    显示"检测到 N 个监控目录发生了变化"
    """
    
    # 用户选择信号
    update_all = Signal()
    update_selected = Signal()
    remind_later = Signal()
    
    def __init__(self, change_count: int, parent=None):
        super().__init__(parent)
        self.change_count = change_count
        self.result_action = None
        
        self.setWindowTitle("目录监控 - 变动检测")
        self.setMinimumWidth(400)
        self.setModal(True)
        # 完全移除关闭按钮
        self.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint)
        
        self._init_ui()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        
        # 图标和消息
        icon_label = QLabel("⚠️")
        icon_label.setStyleSheet("font-size: 48px;")
        icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_label)
        
        msg_label = QLabel(f"您开启了目录监控功能\n检测到 {self.change_count} 个监控目录有文件变动\n是否同步到索引？\n不同步的相关目录将被移除监控")
        msg_label.setStyleSheet("font-size: 14px;")
        msg_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(msg_label)
        
        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        all_btn = QPushButton("全部更新")
        all_btn.clicked.connect(self._on_update_all)
        all_btn.setDefault(True)
        btn_layout.addWidget(all_btn)
        
        select_btn = QPushButton("查看详情")
        select_btn.clicked.connect(self._on_select)
        btn_layout.addWidget(select_btn)
        
        later_btn = QPushButton("跳过并移除监控")
        later_btn.setToolTip("不更新索引，同时移除这些目录的监控")
        later_btn.clicked.connect(self._on_later)
        btn_layout.addWidget(later_btn)
        
        layout.addLayout(btn_layout)
    
    def _on_update_all(self):
        self.result_action = "all"
        self.update_all.emit()
        self.accept()
    
    def _on_select(self):
        self.result_action = "select"
        self.update_selected.emit()
        self.accept()
    
    def _on_later(self):
        self.result_action = "later"
        self.remind_later.emit()
        self.accept()
    
    def closeEvent(self, event):
        """阻止通过右上角X关闭，强制用户通过按钮选择"""
        event.ignore()


class ChangeSelectDialog(QDialog):
    """
    第二层弹窗：详细选择
    显示有变化的目录列表和具体文件变化
    """
    
    def __init__(self, changes: list[FolderChange], parent=None):
        super().__init__(parent)
        self.changes = changes
        self.selected_changes: list[FolderChange] = []
        
        self.setWindowTitle("选择要更新的目录")
        self.setMinimumSize(650, 500)
        self.setModal(True)
        # 完全移除关闭按钮
        self.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint)
        
        self._init_ui()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        # 说明
        hint = QLabel("以下监控目录有文件变动，勾选需要同步到索引的目录：")
        layout.addWidget(hint)
        
        # 使用 TreeWidget 显示目录和文件变化
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["目录/文件", "变化类型", "大小"])
        self.tree.setColumnCount(3)
        
        # 设置列宽
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        self.tree.setColumnWidth(1, 100)
        self.tree.setColumnWidth(2, 80)
        
        for change in self.changes:
            # 目录项（可勾选）
            folder_item = QTreeWidgetItem()
            folder_item.setData(0, Qt.UserRole, change)
            folder_item.setFlags(folder_item.flags() | Qt.ItemIsUserCheckable)
            folder_item.setCheckState(0, Qt.Checked)
            
            # 目录名称和变化摘要
            folder_item.setText(0, change.folder.path)
            folder_item.setText(1, change.summary)
            
            # 格式化上次检查时间
            if change.folder.last_check_time:
                last_check = datetime.fromtimestamp(change.folder.last_check_time).strftime('%m-%d %H:%M')
                folder_item.setToolTip(0, f"上次检查: {last_check}")
            
            # 添加文件变化子项
            if change.file_changes:
                for fc in change.file_changes[:10]:  # 最多显示10个
                    file_item = QTreeWidgetItem(folder_item)
                    file_item.setText(0, fc.filename)
                    
                    # 变化类型和颜色
                    if fc.change_type == 'added':
                        file_item.setText(1, "➕ 新增")
                        file_item.setForeground(1, QColor("#28a745"))
                    elif fc.change_type == 'deleted':
                        file_item.setText(1, "➖ 删除")
                        file_item.setForeground(1, QColor("#dc3545"))
                    elif fc.change_type == 'modified':
                        file_item.setText(1, "✏️ 修改")
                        file_item.setForeground(1, QColor("#fd7e14"))
                    
                    # 文件大小
                    file_item.setText(2, self._frc_format_size(fc.size))
                    file_item.setToolTip(0, fc.path)
                
                # 如果有更多文件
                total = change.total_changes
                shown = len(change.file_changes)
                if total > shown:
                    more_item = QTreeWidgetItem(folder_item)
                    more_item.setText(0, f"... 还有 {total - shown} 个文件变化")
                    more_item.setForeground(0, QColor("#6c757d"))
            
            self.tree.addTopLevelItem(folder_item)
            folder_item.setExpanded(True)
        
        layout.addWidget(self.tree)
        
        # 全选/取消全选
        check_layout = QHBoxLayout()
        
        select_all_btn = QPushButton("全选")
        select_all_btn.clicked.connect(self._select_all)
        check_layout.addWidget(select_all_btn)
        
        deselect_all_btn = QPushButton("取消全选")
        deselect_all_btn.clicked.connect(self._deselect_all)
        check_layout.addWidget(deselect_all_btn)
        
        check_layout.addStretch()
        layout.addLayout(check_layout)
        
        # 底部按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        confirm_btn = QPushButton("同步勾选目录")
        confirm_btn.clicked.connect(self._on_confirm)
        btn_layout.addWidget(confirm_btn)
        
        cancel_btn = QPushButton("跳过未勾选并移除其监控")
        cancel_btn.setToolTip("未勾选的目录不同步，并移除其监控")
        cancel_btn.clicked.connect(self._on_skip_unselected)
        btn_layout.addWidget(cancel_btn)
        
        layout.addLayout(btn_layout)
    
    def _frc_format_size(self, size: int) -> str:
        """格式化文件大小"""
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        else:
            return f"{size / (1024 * 1024 * 1024):.2f} GB"
    
    def _select_all(self):
        for i in range(self.tree.topLevelItemCount()):
            self.tree.topLevelItem(i).setCheckState(0, Qt.Checked)
    
    def _deselect_all(self):
        for i in range(self.tree.topLevelItemCount()):
            self.tree.topLevelItem(i).setCheckState(0, Qt.Unchecked)
    
    def _on_confirm(self):
        self.selected_changes = []
        self.skipped_changes = []
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            change = item.data(0, Qt.UserRole)
            if item.checkState(0) == Qt.Checked:
                self.selected_changes.append(change)
            else:
                self.skipped_changes.append(change)
        
        if not self.selected_changes:
            QMessageBox.warning(self, "提示", "请至少选择一个目录")
            return
        
        self.accept()
    
    def _on_skip_unselected(self):
        """跳过未选目录（移除其监控）"""
        self.selected_changes = []
        self.skipped_changes = []
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            change = item.data(0, Qt.UserRole)
            if item.checkState(0) == Qt.Checked:
                self.selected_changes.append(change)
            else:
                self.skipped_changes.append(change)
        self.accept()
    
    def get_selected(self) -> list[FolderChange]:
        """获取用户选择的变化列表"""
        return self.selected_changes
    
    def get_skipped(self) -> list[FolderChange]:
        """获取被跳过的变化列表"""
        return getattr(self, 'skipped_changes', [])
    
    def closeEvent(self, event):
        """阻止通过右上角X关闭，强制用户通过按钮选择"""
        event.ignore()

