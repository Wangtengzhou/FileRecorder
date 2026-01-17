"""
索引目录选择对话框
用于从已建立索引的数据库中选择目录，采用类似资源管理器的树形+列表视图
"""
from pathlib import Path
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QSplitter, 
    QTreeWidget, QTreeWidgetItem, QTableView, 
    QPushButton, QHeaderView, QWidget, QLabel
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon

from ui.file_browser import FileBrowserModel

class IndexBrowserDialog(QDialog):
    """索引浏览对话框"""
    
    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self.selected_path = None
        
        self.setWindowTitle("选择已索引目录")
        self.resize(1000, 600)
        
        self._init_ui()
        self._load_tree_roots()
        
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # 中间分割视图
        splitter = QSplitter(Qt.Horizontal)
        
        # 左侧目录树
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemExpanded.connect(self._on_item_expanded)
        self.tree.itemClicked.connect(self._on_tree_clicked)
        splitter.addWidget(self.tree)
        
        # 右侧文件列表
        self.file_table = QTableView()
        self.browser_model = FileBrowserModel(db=self.db)
        self.file_table.setModel(self.browser_model)
        
        # 连接列表点击事件
        self.file_table.doubleClicked.connect(self._on_table_double_clicked)
        self.file_table.clicked.connect(self._on_table_clicked)
        
        # 性能优化设置
        self.file_table.setWordWrap(False)
        self.file_table.verticalHeader().setVisible(False)
        self.file_table.setHorizontalScrollMode(QTableView.ScrollPerPixel)
        self.file_table.setVerticalScrollMode(QTableView.ScrollPerPixel)
        self.file_table.setSelectionBehavior(QTableView.SelectRows)
        self.file_table.setSortingEnabled(True)
        self.file_table.setShowGrid(False)
        
        # 列表头设置
        header = self.file_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Fixed)
        header.setStretchLastSection(True)
        self.file_table.setColumnWidth(0, 350)
        self.file_table.setColumnWidth(1, 80)
        self.file_table.setColumnWidth(2, 90)
        
        splitter.addWidget(self.file_table)
        splitter.setSizes([260, 740])  # 稍微加宽左侧
        layout.addWidget(splitter)
        
        # 底部按钮
        btn_layout = QHBoxLayout()
        # 显示当前选中路径
        self.path_label = QLabel("未选择")
        # 使用粗体和默认颜色（即黑色/白色），不再使用灰色
        font = self.path_label.font()
        font.setBold(True)
        self.path_label.setFont(font)
        # self.path_label.setStyleSheet("color: #666;") # 移除灰色
        
        btn_layout.addWidget(self.path_label)
        btn_layout.addStretch()

        
        self.ok_btn = QPushButton("确定选择")
        self.ok_btn.clicked.connect(self.accept)
        self.ok_btn.setEnabled(False)  # 初始禁用
        
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        
        btn_layout.addWidget(self.ok_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

    def _load_tree_roots(self):
        """加载已索引的根目录"""
        folders = self.db.get_folder_tree()
        top_items = {}
        
        for folder in folders:
            if not folder: continue
            folder = folder.replace('/', '\\')
            
            # 解析顶级节点（盘符或网络服务器）
            if folder.startswith('\\\\'):
                parts = folder.lstrip('\\').split('\\')
                top_key = '\\\\' + parts[0] if parts else folder
            else:
                top_key = str(Path(folder).parts[0]) if Path(folder).parts else folder
                
            if top_key not in top_items:
                item = QTreeWidgetItem([top_key])
                item.setData(0, Qt.UserRole, top_key)
                item.setData(0, Qt.UserRole + 1, False) # loaded flag
                item.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)
                top_items[top_key] = item
                
            # 添加具体扫描源
            if folder != top_key:
                parent_item = top_items[top_key]
                
                # 计算相对路径显示名
                if folder.startswith('\\\\'):
                    parts = folder.lstrip('\\').split('\\')
                    child_name = '\\'.join(parts[1:]) if len(parts) > 1 else ''
                else:
                    try:
                        child_name = str(Path(folder).relative_to(top_key))
                    except ValueError:
                        child_name = folder
                        
                if not child_name: continue
                
                child = QTreeWidgetItem([child_name])
                child.setData(0, Qt.UserRole, folder)
                child.setData(0, Qt.UserRole + 1, False)
                child.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)
                parent_item.addChild(child)
        
        # 排序并添加
        sorted_items = sorted(top_items.items(), 
                            key=lambda x: (1 if x[0].startswith('\\\\') else 0, x[0]))
        for _, item in sorted_items:
            self.tree.addTopLevelItem(item)
            item.setExpanded(True) # 默认展开第一层

    def _on_item_expanded(self, item):
        """展开节点加载子目录"""
        if item.data(0, Qt.UserRole + 1): return # 已加载
        
        path = item.data(0, Qt.UserRole)
        if not path: return
        
        item.setData(0, Qt.UserRole + 1, True)
        subdirs = self.db.get_direct_subdirs(path)
        
        # 避免添加重复项
        existing = {item.child(i).data(0, Qt.UserRole) for i in range(item.childCount())}
        
        for sub in subdirs:
            if sub['path'] in existing: continue
            
            child = QTreeWidgetItem([sub['name']])
            child.setData(0, Qt.UserRole, sub['path'])
            child.setData(0, Qt.UserRole + 1, False)
            if sub['has_children']:
                child.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)
            item.addChild(child)

    def _on_tree_clicked(self, item, column):
        """点击树节点加载文件列表"""
        path = item.data(0, Qt.UserRole)
        # 点击左侧树时，视为选中该目录
        self._update_selection(path)
        
        # 刷新右侧视图
        if path:
            self.browser_model.navigate_to(path)
            
    def _on_table_double_clicked(self, index):
        """双击列表项"""
        if not index.isValid():
            return
            
        item = self.browser_model.get_item(index.row())
        if not item:
            return
            
        if item.get('is_dir'):
            # 双击文件夹：进入该目录
            path = item.get('full_path')
            # 同步更新左侧树的展开状态（可选，比较复杂，暂时只更新视图）
            self.browser_model.navigate_to(path)
            # 进入新目录后，默认选中这一级目录
            self._update_selection(path)
        else:
            # 双击文件：不做操作（或者可以选择该文件所在的目录？）
            pass
            
    def _on_table_clicked(self, index):
        """单击列表项"""
        if not index.isValid():
            return
            
        item = self.browser_model.get_item(index.row())
        if not item:
            return
            
        if item.get('is_dir'):
            # 单击文件夹：将该文件夹作为选中目标
            self._update_selection(item.get('full_path'))
        else:
            # 单击文件：保留当前目录作为选中目标（或者禁用确定按钮？）
            # 这里逻辑是：如果选了文件，用户意图可能是选文件所在目录，或者误操作
            # 既然是“选择目录”，选文件时我们暂不改变 selection，或者保持为当前父目录
            pass
            
    def _update_selection(self, path):
        """更新选中状态"""
        self.selected_path = path
        
        if path:
            self.path_label.setText(path)
            self.ok_btn.setEnabled(True)
        else:
            self.path_label.setText("未选择")
            self.ok_btn.setEnabled(False)

