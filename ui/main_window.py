"""
FileRecorder 主窗口
"""
import subprocess
import sys
import os
from pathlib import Path

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QToolBar, QStatusBar, QLineEdit, QPushButton,
    QTableView, QHeaderView, QFileDialog, QMessageBox,
    QProgressBar, QLabel, QSplitter, QTreeWidget, QTreeWidgetItem,
    QMenu, QComboBox, QApplication
)

from database.db_manager import DatabaseManager
from scanner.file_scanner import FileScanner, ScannerThread
from ui.file_table import FileTableModel, ElideDelegate
from ui.file_browser import FileBrowserModel
from ui.scan_dialog import MultiFolderScanDialog
from ui.progress_dialog import ScanProgressDialog
from config import config


def resource_path(relative_path):
    """获取资源绝对路径（支持 PyInstaller 打包）"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


class SelectAllLineEdit(QLineEdit):
    """首次获得焦点时自动全选的搜索框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._first_click = True
    
    def focusInEvent(self, event):
        """获得焦点时全选"""
        super().focusInEvent(event)
        self._first_click = True
        # 使用单次定时器延迟全选，确保焦点事件先处理完
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self.selectAll)
    
    def mousePressEvent(self, event):
        """鼠标点击时的处理"""
        if self._first_click and self.text():
            # 第一次点击，让focusInEvent处理全选
            self._first_click = False
            super().mousePressEvent(event)
        else:
            # 后续点击，正常处理（允许拖拽选择）
            super().mousePressEvent(event)


class MainWindow(QMainWindow):
    """主窗口"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FileRecorder - 智能文件索引助手")
        # 设置窗口图标
        icon_path = resource_path("logo.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
            
        self.resize(
            config.get("ui", "window_width", default=1200),
            config.get("ui", "window_height", default=800)
        )
        
        # 初始化数据库
        self.db = DatabaseManager(config.database_path)
        
        # 扫描线程和队列
        self.scanner_thread = None
        self.scan_queue = []  # 待扫描路径队列
        self.current_scan_path = None
        self.progress_dialog = None  # 进度对话框
        # 扫描累计统计（用于多目录扫描汇总）
        self._scan_total_files = 0
        self._scan_total_errors = 0
        self._scan_paths_count = 0
        
        # 浏览模式: 'browser'(逐级) 或 'flat'(平铺)
        self.view_mode = 'browser'
        
        # 导航历史（用于前进后退）
        self._history_back = []   # 后退栈
        self._history_forward = []  # 前进栈
        self._history_navigating = False  # 是否正在通过历史导航
        
        # 初始化界面
        self._init_ui()
        self._init_toolbar()
        self._init_statusbar()
        
        # 加载数据
        self._refresh_data()
        
        # 更新错误计数
        self._update_error_count()
        
        # 安装事件过滤器以捕获鼠标侧键
        from PySide6.QtWidgets import QApplication
        QApplication.instance().installEventFilter(self)
    
    def _init_ui(self):
        """初始化界面"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(8, 8, 8, 8)
        
        # 搜索栏
        search_layout = QHBoxLayout()
        
        self.search_input = SelectAllLineEdit()
        self.search_input.setPlaceholderText("输入关键词搜索文件...")
        self.search_input.returnPressed.connect(self._on_search)
        search_layout.addWidget(self.search_input)
        
        self.ext_filter = QComboBox()
        self.ext_filter.setMinimumWidth(100)
        self.ext_filter.addItem("所有类型", "")
        self.ext_filter.currentIndexChanged.connect(self._on_search)
        search_layout.addWidget(self.ext_filter)
        
        search_btn = QPushButton("搜索")
        search_btn.clicked.connect(self._on_search)
        search_layout.addWidget(search_btn)
        
        clear_btn = QPushButton("清除")
        clear_btn.clicked.connect(self._on_clear_search)
        search_layout.addWidget(clear_btn)
        
        layout.addLayout(search_layout)
        
        # 面包屑导航栏
        nav_layout = QHBoxLayout()
        
        # 后退按钮
        self.back_btn = QPushButton("⬅ 后退")
        self.back_btn.clicked.connect(self._on_go_back)
        self.back_btn.setEnabled(False)
        self.back_btn.setToolTip("后退 (鼠标侧键/Alt+Left)")
        nav_layout.addWidget(self.back_btn)
        
        # 前进按钮
        self.forward_btn = QPushButton("➡ 前进")
        self.forward_btn.clicked.connect(self._on_go_forward)
        self.forward_btn.setEnabled(False)
        self.forward_btn.setToolTip("前进 (鼠标侧键/Alt+Right)")
        nav_layout.addWidget(self.forward_btn)
        
        self.home_btn = QPushButton("🏠 根目录")
        self.home_btn.clicked.connect(self._on_go_home)
        nav_layout.addWidget(self.home_btn)
        
        self.path_label = QLabel("当前位置: /")
        self.path_label.setStyleSheet("color: #666; padding: 4px;")
        self.path_label.setTextFormat(Qt.RichText)  # 支持富文本
        self.path_label.setOpenExternalLinks(False)  # 不自动打开外部链接
        self.path_label.linkActivated.connect(self._on_breadcrumb_click)
        nav_layout.addWidget(self.path_label, 1)
        
        # 刷新按钮
        self.refresh_btn = QPushButton("🔄 刷新")
        self.refresh_btn.clicked.connect(self._refresh_data)
        self.refresh_btn.setToolTip("刷新当前视图 (F5)")
        nav_layout.addWidget(self.refresh_btn)
        
        # 视图切换
        self.view_toggle_btn = QPushButton("📋 平铺视图")
        self.view_toggle_btn.clicked.connect(self._on_toggle_view)
        nav_layout.addWidget(self.view_toggle_btn)
        
        layout.addLayout(nav_layout)
        
        # 主体区域 - 分割器
        splitter = QSplitter(Qt.Horizontal)
        
        # 左侧目录树
        self.folder_tree = QTreeWidget()
        self.folder_tree.setHeaderLabel("目录结构")
        self.folder_tree.setMinimumWidth(200)
        self.folder_tree.itemClicked.connect(self._on_folder_clicked)
        self.folder_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.folder_tree.customContextMenuRequested.connect(self._show_folder_tree_menu)
        # 增加行间距，提高可读性
        self.folder_tree.setStyleSheet("""
            QTreeWidget::item {
                padding: 2px 0;
                min-height: 20px;
            }
        """)
        splitter.addWidget(self.folder_tree)
        
        # 右侧文件浏览器
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        self.file_table = QTableView()
        
        # 两个模型: 浏览器模式和平铺模式
        self.browser_model = FileBrowserModel(db=self.db)
        self.file_model = FileTableModel()
        self.file_table.setModel(self.browser_model)  # 默认浏览器模式
        self.file_table.setSelectionBehavior(QTableView.SelectRows)
        self.file_table.setSelectionMode(QTableView.ExtendedSelection)
        self.file_table.setSortingEnabled(True)
        self.file_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_table.customContextMenuRequested.connect(self._show_context_menu)
        self.file_table.doubleClicked.connect(self._on_double_click)
        self.file_table.setTextElideMode(Qt.ElideRight)  # 长文本从右侧截断显示...
        
        # 滚动事件监听（用于分页预加载）
        self.file_table.verticalScrollBar().valueChanged.connect(self._on_table_scroll)
        
        # 设置列宽 - 允许用户调整
        header = self.file_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)  # 允许调整
        header.setStretchLastSection(True)  # 最后一列拉伸
        # 设置默认宽度
        self.file_table.setColumnWidth(0, 300)  # 名称
        self.file_table.setColumnWidth(1, 70)   # 类型
        self.file_table.setColumnWidth(2, 80)   # 大小
        self.file_table.setColumnWidth(3, 120)  # 时间
        self.file_table.setColumnWidth(4, 80)   # AI分类
        
        right_layout.addWidget(self.file_table)
        splitter.addWidget(right_widget)
        splitter.setSizes([250, 950])
        
        layout.addWidget(splitter)
    
    def _init_toolbar(self):
        """初始化工具栏"""
        toolbar = QToolBar("主工具栏")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        
        # 扫描目录 (整合后的入口)
        self.scan_action = QAction("📁 扫描目录", self)
        self.scan_action.triggered.connect(self._on_start_scan)
        toolbar.addAction(self.scan_action)
        
        toolbar.addSeparator()
        
        # AI 整理 (Phase 3)
        ai_action = QAction("🤖 AI整理", self)
        ai_action.triggered.connect(self._on_ai_organize)
        toolbar.addAction(ai_action)
        
        toolbar.addSeparator()
        
        # 导出
        export_action = QAction("导出CSV", self)
        export_action.triggered.connect(self._on_export_csv)
        toolbar.addAction(export_action)
        
        export_html_action = QAction("导出HTML", self)
        export_html_action.triggered.connect(self._on_export_html)
        toolbar.addAction(export_html_action)
        
        # 备份数据库
        backup_action = QAction("💾 备份", self)
        backup_action.triggered.connect(self._on_backup)
        toolbar.addAction(backup_action)
        
        # 恢复数据库
        restore_action = QAction("📥 恢复", self)
        restore_action.triggered.connect(self._on_restore)
        toolbar.addAction(restore_action)
        
        # 优化数据库
        optimize_action = QAction("🔧 优化", self)
        optimize_action.setToolTip("压缩数据库，回收空间")
        optimize_action.triggered.connect(self._on_optimize_db)
        toolbar.addAction(optimize_action)
        
        # 清除索引
        clear_action = QAction("🗑️ 清除", self)
        clear_action.setToolTip("清除所有索引数据")
        clear_action.triggered.connect(self._on_clear_index)
        toolbar.addAction(clear_action)
        
        toolbar.addSeparator()
        
        # 错误文件
        self.error_action = QAction("⚠️ 错误 (0)", self)
        self.error_action.triggered.connect(self._on_show_errors)
        toolbar.addAction(self.error_action)
        
        # 设置
        settings_action = QAction("⚙️ 设置", self)
        settings_action.triggered.connect(self._on_settings)
        toolbar.addAction(settings_action)
    
    def _init_statusbar(self):
        """初始化状态栏"""
        self.statusbar = QStatusBar()
        self.setStatusBar(self.statusbar)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(200)
        self.progress_bar.setVisible(False)
        self.statusbar.addPermanentWidget(self.progress_bar)
        
        # 统计信息
        self.stats_label = QLabel()
        self.statusbar.addPermanentWidget(self.stats_label)
        
        # 确保初始状态栏消息为空
        self.statusbar.clearMessage()
        self._update_stats()
    
    def _update_stats(self):
        """更新统计信息"""
        stats = self.db.get_stats()
        total_size = stats['total_size']
        
        # 格式化大小
        if total_size < 1024 * 1024 * 1024:
            size_str = f"{total_size / (1024 * 1024):.1f} MB"
        else:
            size_str = f"{total_size / (1024 * 1024 * 1024):.2f} GB"
        
        self.stats_label.setText(
            f"共 {stats['total_files']:,} 个文件 | {size_str} | "
            f"{stats['extension_count']} 种类型 | AI已分类: {stats['ai_categorized']}"
        )
    
    def _refresh_data(self, navigate_to: str = None):
        """刷新数据显示
        
        Args:
            navigate_to: 可选，刷新后要导航到的路径。如果不指定，保持当前位置。
        """
        # 确定要导航到的目录
        # 注意：如果从 clicked 信号调用，navigate_to 可能是 bool 类型
        if navigate_to and isinstance(navigate_to, str):
            target_path = navigate_to
        else:
            # 保持当前位置，如果没有当前位置则导航到第一个扫描源
            target_path = self.browser_model.get_current_path()
            if not target_path:
                folders = self.db.get_folder_tree()
                target_path = folders[0] if folders else ""
        
        # 保存目录树展开状态
        expanded_paths = self._get_expanded_paths()
        
        # 更新目录树
        self._build_folder_tree()
        
        # 恢复目录树展开状态
        self._restore_expanded_paths(expanded_paths)
        
        # 恢复选中状态（仅当路径可见时才选中，不强制展开）
        if target_path:
            self._select_tree_item(target_path, expand=False)
        
        # 清除缓存
        self.browser_model.clear_cache()
        
         # 最后导航到目标目录，确保右侧视图与左侧同步
        if target_path:
            self.browser_model.navigate_to(target_path)
        else:
            self.browser_model.navigate_to("")
            
        # 强制更新右侧视图模型绑定，防止视图卡死
        self.file_table.setModel(self.browser_model)
        
        # 平铺模式的file_model按需加载
        # self.file_model.set_data([])
        
        self._update_nav_ui()
        
        # 平铺模式的file_model按需加载
        # self.file_model.set_data([])
        
        self._update_nav_ui()
        
        # 更新扩展名过滤器 - 暂时阻塞信号以防止触发搜索逻辑重置视图
        self.ext_filter.blockSignals(True)
        self.ext_filter.clear()
        self.ext_filter.addItem("所有类型", "")
        for ext, count in self.db.get_all_extensions()[:30]:  # 最多30个扩展名
            self.ext_filter.addItem(f".{ext} ({count})", ext)
        self.ext_filter.blockSignals(False)
        
        # 更新统计
        self._update_stats()
    
    def _build_folder_tree(self):
        """构建目录树（延迟加载模式）
        
        只加载扫描源目录作为顶级项目，子目录在展开时动态加载
        """
        self.folder_tree.clear()
        
        # 连接展开事件（只连接一次）
        try:
            self.folder_tree.itemExpanded.disconnect(self._on_tree_item_expanded)
        except:
            pass
        self.folder_tree.itemExpanded.connect(self._on_tree_item_expanded)
        
        folders = self.db.get_folder_tree()  # 获取所有扫描源
        
        # 解析路径为顶级部分
        top_level_items = {}  # key -> item
        
        for folder in folders:
            if not folder:
                continue
            
            # 统一路径分隔符
            folder = folder.replace('/', '\\')
            
            # 获取顶级部分（盘符或网络服务器）
            if folder.startswith('\\\\'):
                # 网络路径：取服务器名
                parts = folder.lstrip('\\').split('\\')
                top_key = '\\\\' + parts[0] if parts else folder
            else:
                # 本地路径：取盘符
                top_key = str(Path(folder).parts[0]) if Path(folder).parts else folder
            
            # 创建顶级项目（如果不存在）
            if top_key not in top_level_items:
                item = QTreeWidgetItem([top_key])
                item.setData(0, Qt.UserRole, top_key)
                item.setData(0, Qt.UserRole + 1, False)  # 标记未加载子目录
                item.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)  # 显示展开箭头
                top_level_items[top_key] = item
            
            # 添加扫描源作为子项
            if folder != top_key:
                parent_item = top_level_items[top_key]
                # 提取相对路径部分
                if folder.startswith('\\\\'):
                    parts = folder.lstrip('\\').split('\\')
                    child_name = '\\'.join(parts[1:]) if len(parts) > 1 else ''
                else:
                    parts = list(Path(folder).parts)
                    child_name = '\\'.join(parts[1:]) if len(parts) > 1 else ''
                
                # 跳过空名称
                if not child_name:
                    continue
                
                child_item = QTreeWidgetItem([child_name])
                child_item.setData(0, Qt.UserRole, folder)
                child_item.setData(0, Qt.UserRole + 1, False)  # 未加载
                child_item.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)
                parent_item.addChild(child_item)
        
        # 排序：本地路径在前，网络路径在后
        sorted_items = sorted(top_level_items.items(), 
                            key=lambda x: (1 if x[0].startswith('\\\\') else 0, x[0]))
        
        for key, item in sorted_items:
            self.folder_tree.addTopLevelItem(item)
        
        # 自动展开顶级目录，预加载一级子目录
        for key, item in sorted_items:
            item.setExpanded(True)  # 展开顶级目录，触发子目录加载
    
    def _on_tree_item_expanded(self, item: QTreeWidgetItem):
        """目录树项目展开时动态加载子目录"""
        # 检查是否已加载
        is_loaded = item.data(0, Qt.UserRole + 1)
        if is_loaded:
            return
        
        folder_path = item.data(0, Qt.UserRole)
        if not folder_path:
            return
        
        # 标记为已加载
        item.setData(0, Qt.UserRole + 1, True)
        
        # 获取该目录下的子目录
        subdirs = self._get_subdirectories(folder_path)
        
        for subdir in subdirs:
            # 检查是否已存在
            exists = False
            for i in range(item.childCount()):
                if item.child(i).data(0, Qt.UserRole) == subdir['path']:
                    exists = True
                    break
            
            if not exists:
                child_item = QTreeWidgetItem([subdir['name']])
                child_item.setData(0, Qt.UserRole, subdir['path'])
                child_item.setData(0, Qt.UserRole + 1, False)
                if subdir['has_children']:
                    child_item.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)
                item.addChild(child_item)
    
    def _get_subdirectories(self, parent_path: str) -> list:
        """获取指定路径下的直接子目录"""
        parent_path = parent_path.replace('/', '\\').rstrip('\\')
        
        # 从数据库获取所有目录
        all_dirs = self.db.get_all_directories()
        
        subdirs = []
        seen = set()
        
        for dir_path in all_dirs:
            if not dir_path:
                continue
            
            dir_path = dir_path.replace('/', '\\')
            
            # 检查是否是直接子目录
            if dir_path.lower().startswith(parent_path.lower() + '\\'):
                remaining = dir_path[len(parent_path) + 1:]
                # 取第一级子目录
                first_part = remaining.split('\\')[0]
                
                # 跳过空名称
                if not first_part:
                    continue
                
                full_subdir = parent_path + '\\' + first_part
                
                if full_subdir.lower() not in seen:
                    seen.add(full_subdir.lower())
                    # 检查是否有更深的子目录
                    has_subdirs = any(
                        d.replace('/', '\\').lower().startswith(full_subdir.lower() + '\\')
                        for d in all_dirs if d
                    )
                    # 检查是否有子文件（通过数据库查询）
                    file_count = self.db.get_file_count_in_folder(full_subdir)
                    has_children = has_subdirs or file_count > 0
                    subdirs.append({
                        'name': first_part,
                        'path': full_subdir,
                        'has_children': has_children
                    })
        
        return sorted(subdirs, key=lambda x: x['name'].lower())
    
    def _on_folder_clicked(self, item: QTreeWidgetItem, column: int):
        """目录树项目点击处理"""
        folder_path = item.data(0, Qt.UserRole)
        if folder_path:
            self._navigate_to(folder_path)
    
    def _get_expanded_paths(self) -> set:
        """获取当前展开的目录路径集合"""
        expanded = set()
        
        def collect_expanded(item):
            if item.isExpanded():
                path = item.data(0, Qt.UserRole)
                if path:
                    expanded.add(path)
            for i in range(item.childCount()):
                collect_expanded(item.child(i))
        
        for i in range(self.folder_tree.topLevelItemCount()):
            collect_expanded(self.folder_tree.topLevelItem(i))
        
        return expanded
    
    def _restore_expanded_paths(self, expanded_paths: set):
        """恢复目录展开状态"""
        def restore_expanded(item):
            path = item.data(0, Qt.UserRole)
            if path and path in expanded_paths:
                item.setExpanded(True)
            for i in range(item.childCount()):
                restore_expanded(item.child(i))
        
        for i in range(self.folder_tree.topLevelItemCount()):
            restore_expanded(self.folder_tree.topLevelItem(i))
            
    def _select_tree_item(self, path: str, expand: bool = True):
        """选中目录树中的指定路径（递归查找）
        
        Args:
            path: 目标路径
            expand: 是否强制展开父节点以显示目标。False则仅在父节点已展开时继续查找。
        """
        path = path.replace('/', '\\').rstrip('\\').lower()
        
        def find_and_select(item):
            item_path = item.data(0, Qt.UserRole)
            if item_path:
                item_path = item_path.replace('/', '\\').rstrip('\\').lower()
                if item_path == path:
                    self.folder_tree.setCurrentItem(item)
                    # 确保可视
                    self.folder_tree.scrollToItem(item)
                    return True
            
            # 如果目标路径以当前项路径开头，则展开并继续查找
            if path.startswith(item_path + '\\'):
                # 如果不强制展开且当前未展开，则停止查找（尊重用户状态）
                if not expand and not item.isExpanded():
                    return False

                # 确保已加载子节点
                if not item.data(0, Qt.UserRole + 1):  # is_loaded
                    self._on_tree_item_expanded(item)
                
                item.setExpanded(True)
                # 处理异步加载或UI更新延迟，虽然 _on_tree_item_expanded 是同步的
                QApplication.processEvents()
                
                for i in range(item.childCount()):
                    if find_and_select(item.child(i)):
                        return True
            return False
        
        for i in range(self.folder_tree.topLevelItemCount()):
            if find_and_select(self.folder_tree.topLevelItem(i)):
                break
    
    # ========== 事件处理 ==========
    
    @Slot()
    def _on_start_scan(self):
        """开始扫描 - 打开多文件夹扫描对话框"""
        dialog = MultiFolderScanDialog(self)
        dialog.scan_requested.connect(self._on_multi_scan_requested)
        dialog.exec_()
    
    @Slot(list)
    def _on_multi_scan_requested(self, paths: list):
        """处理多文件夹扫描请求"""
        if not paths:
            return
        
        # 重置累计统计
        self._scan_total_files = 0
        self._scan_total_errors = 0
        self._scan_paths_count = len(paths)
        
        # 第一个路径用 _start_scan 创建对话框
        first_path = paths[0]
        # 剩余的加入队列
        self.scan_queue = paths[1:] if len(paths) > 1 else []
        # 启动第一个扫描（会创建进度对话框）
        self._start_scan(first_path)
    
    def _scan_next_in_queue(self):
        """扫描队列中的下一个路径"""
        if not self.scan_queue:
            # 队列完成
            self.statusbar.showMessage("所有路径扫描完成")
            return
        
        path = self.scan_queue.pop(0)
        self.current_scan_path = path
        
        # 复用现有对话框，只更新标题
        if self.progress_dialog:
            remaining = len(self.scan_queue)
            self.progress_dialog.set_title(f"正在扫描: {path}", "🔍")
        
        # 创建新的扫描器和线程
        scanner = FileScanner(
            db=self.db,
            batch_size=config.get("scanner", "batch_size", default=1000),
            ignore_patterns=config.get("scanner", "ignore_patterns"),
            timeout=config.get("scanner", "timeout_seconds", default=5)
        )
        
        self.scanner_thread = ScannerThread(scanner, path)
        self.scanner_thread.progress.connect(self._on_scan_progress)
        if self.progress_dialog:
            self.scanner_thread.progress.connect(self.progress_dialog.update_progress)
        self.scanner_thread.finished.connect(self._on_scan_finished)
        self.scanner_thread.error.connect(self._on_scan_error)
        
        self.statusbar.showMessage("扫描中...")
        self.scanner_thread.start()
    
    def _start_scan(self, path: str):
        """开始扫描指定路径"""
        if self.scanner_thread and self.scanner_thread.isRunning():
            QMessageBox.warning(self, "提示", "扫描正在进行中...")
            return
        
        # 保存当前扫描路径
        self.current_scan_path = path
        
        # 初始化累计统计（仅在非队列模式下，即直接调用 _start_scan 时）
        if self._scan_paths_count == 0:
            self._scan_total_files = 0
            self._scan_total_errors = 0
            self._scan_paths_count = 1
        
        # 创建进度对话框
        self.progress_dialog = ScanProgressDialog("正在扫描", self)
        self.progress_dialog.set_title(f"正在扫描: {path}", "🔍")
        self.progress_dialog.stop_requested.connect(self._on_stop_scan)
        
        # 创建扫描器（传入db实现分批写入，清理旧数据由扫描器负责）
        scanner = FileScanner(
            db=self.db,
            batch_size=config.get("scanner", "batch_size", default=1000),
            ignore_patterns=config.get("scanner", "ignore_patterns"),
            timeout=config.get("scanner", "timeout_seconds", default=5)
        )
        
        self.scanner_thread = ScannerThread(scanner, path)
        self.scanner_thread.progress.connect(self._on_scan_progress)
        self.scanner_thread.progress.connect(self.progress_dialog.update_progress)
        self.scanner_thread.finished.connect(self._on_scan_finished)
        self.scanner_thread.error.connect(self._on_scan_error)
        
        # 更新工具栏状态（用户看不到，但保持逻辑一致）
        self.scan_action.setText("⏹️ 停止扫描")
        self.scan_action.triggered.disconnect()
        self.scan_action.triggered.connect(self._on_stop_scan)
        
        # 隐藏底部进度条（进度对话框已有进度条）
        self.progress_bar.setVisible(False)
        self.statusbar.showMessage("扫描中...")
        
        # 启动扫描并显示对话框
        self.scanner_thread.start()
        self.progress_dialog.show()
    
    @Slot()
    def _on_stop_scan(self):
        """停止扫描"""
        if self.scanner_thread:
            self.scanner_thread.cancel()
    
    @Slot(int, int, str)
    def _on_scan_progress(self, current: int, total: int, filename: str):
        """扫描进度更新"""
        # 有进度对话框时不更新状态栏（避免重复信息）
        if not self.progress_dialog:
            self.statusbar.showMessage(f"已扫描 {current} 个文件: {filename}")
    
    @Slot(dict)
    def _on_scan_finished(self, result: dict):
        """扫描完成"""
        # 注意：分批写入模式下，数据已在扫描过程中写入数据库，result['files']为空
        # 只有无db模式下才需要批量插入（兼容旧逻辑）
        if result['files']:
            batch_size = config.get("scanner", "batch_size", default=1000)
            files = result['files']
            for i in range(0, len(files), batch_size):
                self.db.batch_insert(files[i:i+batch_size])
        
        # 记录扫描错误
        scan_source = result.get('scan_source', '')
        for error in result.get('errors', []):
            if isinstance(error, dict):
                self.db.insert_scan_error(
                    error.get('path', ''),
                    error.get('error', '未知错误'),
                    scan_source
                )
        
        # 累计统计
        self._scan_total_files += result.get('file_count', 0)
        self._scan_total_errors += result.get('error_count', 0)
        
        # 检查是否还有队列
        remaining = len(self.scan_queue)
        
        if remaining > 0:
            # 还有待扫描项目，更新对话框并继续扫描
            completed = self._scan_paths_count - remaining
            if self.progress_dialog:
                self.progress_dialog.set_title(f"扫描进度 ({completed}/{self._scan_paths_count})", "📋")
            self.statusbar.showMessage(
                f"完成: {result['scan_source']} ({result['file_count']}个文件) | 剩余 {remaining} 个路径"
            )
            self._scan_next_in_queue()
            return
        
        # 队列全部完成
        # 更新进度对话框 - 显示累计汇总
        if self.progress_dialog:
            if result['cancelled']:
                self.progress_dialog.set_cancelled()
            else:
                self.progress_dialog.set_finished(self._scan_total_files, self._scan_total_errors)
        
        # 恢复工具栏UI状态
        self.scan_action.setText("🔍 开始扫描")
        self.scan_action.triggered.disconnect()
        self.scan_action.triggered.connect(self._on_start_scan)
        
        self.progress_bar.setVisible(False)
        self.current_scan_path = None
        
        # 刷新显示并导航到扫描的目录
        self._refresh_data(navigate_to=result['scan_source'])
        
        # 获取最新统计
        stats = self.db.get_stats()
        
        # 更新状态栏 - 显示累计汇总
        if self._scan_paths_count > 1:
            msg = f"扫描完成！共扫描 {self._scan_paths_count} 个目录，{self._scan_total_files} 个文件，数据库共 {stats['total_files']} 条记录"
        else:
            msg = f"扫描完成！本次扫描到 {self._scan_total_files} 个文件，数据库共 {stats['total_files']} 条记录"
        if self._scan_total_errors > 0:
            msg += f"，{self._scan_total_errors} 个文件读取失败"
        if result['cancelled']:
            msg = "扫描已取消 | " + msg
        
        self.statusbar.showMessage(msg)
        
        # 更新错误计数
        self._update_error_count()
        
        # 重置统计变量
        self._scan_paths_count = 0
    
    @Slot(str)
    def _on_scan_error(self, error: str):
        """扫描错误"""
        print(f"扫描错误: {error}")  # 记录日志
    
    def _search_input_click(self, event):
        """搜索框点击事件 - 首次获得焦点时全选"""
        from PySide6.QtWidgets import QLineEdit
        from PySide6.QtCore import QTimer
        
        # 检查是否有选中文本（有选中说明已经操作过了）
        has_selection = self.search_input.hasSelectedText()
        
        # 调用默认处理
        QLineEdit.mousePressEvent(self.search_input, event)
        
        # 如果之前没有选中文本，则全选
        if not has_selection and self.search_input.text():
            QTimer.singleShot(0, self.search_input.selectAll)
    
    @Slot()
    def _on_search(self):
        """执行搜索 - 自动切换到平铺视图"""
        keyword = self.search_input.text().strip()
        extension = self.ext_filter.currentData()
        
        if keyword or extension:
            files = self.db.search_files(keyword, extension)
            # 搜索时切换到平铺视图
            self.view_mode = 'flat'
            self.file_model.set_data(files)
            self.file_table.setModel(self.file_model)
            
            # 设置搜索结果列宽（6列）
            self.file_table.setColumnWidth(0, 260)  # 文件名
            self.file_table.setColumnWidth(1, 60)   # 类型
            self.file_table.setColumnWidth(2, 70)   # 大小
            self.file_table.setColumnWidth(3, 110)  # 时间
            self.file_table.setColumnWidth(4, 280)  # 所在目录（加宽）
            self.file_table.setColumnWidth(5, 80)   # AI分类
            
            # 为所在目录列设置自适应省略代理
            self.file_table.setItemDelegateForColumn(4, ElideDelegate(self.file_table))
            
            self.view_toggle_btn.setText("📂 浏览视图")
            self.back_btn.setEnabled(False)
            self.path_label.setText(f"搜索结果: '{keyword}' ({len(files)} 个文件)")
            
            # 只在搜索时显示状态栏消息
            self.statusbar.showMessage(f"找到 {len(files)} 个匹配文件")
        else:
            # 空搜索切换回浏览视图
            self._on_go_home()
    
    @Slot()
    def _on_clear_search(self):
        """清除搜索"""
        self.search_input.clear()
        self.ext_filter.setCurrentIndex(0)
        self._refresh_data()
    
    @Slot()
    def _on_folder_clicked(self, item, column):
        """目录树点击 - 导航到指定目录"""
        folder_path = item.data(0, Qt.UserRole)
        if folder_path:
            self._navigate_to(folder_path)
    
    def _show_folder_tree_menu(self, pos):
        """显示目录树右键菜单"""
        item = self.folder_tree.itemAt(pos)
        if not item:
            return
        
        folder_path = item.data(0, Qt.UserRole)
        if not folder_path:
            return
        
        menu = QMenu(self)
        
        # 在浏览器中导航
        nav_action = menu.addAction("📂 在右侧浏览")
        nav_action.triggered.connect(lambda: self._navigate_to(folder_path))
        
        # 在资源管理器中打开
        open_action = menu.addAction("📁 在资源管理器中打开")
        open_action.triggered.connect(lambda: self._open_folder_in_explorer(folder_path))
        
        menu.addSeparator()
        
        # 删除该目录的索引
        delete_action = menu.addAction("🗑️ 删除此目录索引")
        delete_action.triggered.connect(lambda: self._delete_folder_index(folder_path))
        
        menu.exec_(self.folder_tree.viewport().mapToGlobal(pos))
    
    def _delete_folder_index(self, folder_path: str):
        """删除指定目录的所有索引记录"""
        from PySide6.QtWidgets import QMessageBox
        
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除以下目录的所有索引记录吗？\n\n{folder_path}\n\n此操作不会删除实际文件。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # 显示进度提示
            self.statusbar.showMessage(f"正在删除 {folder_path} 的索引...")
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)  # 不确定模式
            
            # 强制更新UI
            from PySide6.QtWidgets import QApplication
            QApplication.processEvents()
            
            # 删除该路径下的所有文件记录
            deleted_count = self.db.clear_source(folder_path)
            
            # 隐藏进度条
            self.progress_bar.setVisible(False)
            
            # 保存当前展开状态
            expanded_paths = self._get_expanded_paths()
            
            # 刷新数据
            self._refresh_data()
            
            # 恢复展开状态
            self._restore_expanded_paths(expanded_paths)
            
            self.statusbar.showMessage(f"已删除 {deleted_count} 条索引记录", 5000)
            QMessageBox.information(self, "删除完成", f"已删除 {deleted_count} 条索引记录")

    
    @Slot()
    def _on_double_click(self, index):
        """双击事件 - 目录进入，文件打开位置"""
        if self.view_mode == 'browser':
            item = self.browser_model.get_item_at(index.row())
            if item.get('is_dir'):
                # 进入目录
                self._navigate_to(item.get('full_path', ''))
            else:
                # 打开文件位置
                self._open_file_location(item.get('full_path'))
        else:
            file_info = self.file_model.get_file_at(index.row())
            if file_info:
                self._open_file_location(file_info.get('full_path'))
    
    def _navigate_to(self, path: str):
        """导航到指定路径"""
        current_path = self.browser_model.get_current_path()
        
        # 如果不是通过历史导航，则记录历史
        if not self._history_navigating:
            if current_path:  # 只记录非空路径
                self._history_back.append(current_path)
            # 清空前进栈（新的导航会清除前进历史）
            self._history_forward.clear()
        
        self.view_mode = 'browser'
        self.file_table.setModel(self.browser_model)
        self.browser_model.navigate_to(path)
        self._update_nav_ui()
        self.view_toggle_btn.setText("📋 平铺视图")
        
        # 清除状态栏搜索结果提示
        self.statusbar.clearMessage()
    
    def _navigate_and_select(self, folder_path: str, filename: str):
        """导航到目录并选中指定文件"""
        # 先导航到目录
        self._navigate_to(folder_path)
        
        # 延迟选中文件（等待视图刷新）
        from PySide6.QtCore import QTimer
        def select_file():
            # 在当前视图中查找文件
            for row in range(self.browser_model.rowCount()):
                item = self.browser_model.get_item_at(row)
                if item and item.get('name', '') == filename:
                    # 选中该行
                    index = self.browser_model.index(row, 0)
                    self.file_table.setCurrentIndex(index)
                    self.file_table.scrollTo(index)
                    break
        
        QTimer.singleShot(100, select_file)
    
    def _update_nav_ui(self):
        """更新导航UI"""
        current_path = self.browser_model.get_current_path()
        
        # 更新后退按钮状态
        self.back_btn.setEnabled(len(self._history_back) > 0)
        
        # 更新前进按钮状态
        self.forward_btn.setEnabled(len(self._history_forward) > 0)
        
        if current_path:
            # 生成可点击的面包屑路径
            breadcrumb_html = self._build_breadcrumb_html(current_path)
            self.path_label.setText(breadcrumb_html)
        else:
            self.path_label.setText("当前位置: / (根目录)")
    
    def _build_breadcrumb_html(self, path: str) -> str:
        """构建面包屑HTML"""
        # 统一路径分隔符
        path = path.replace('/', '\\')
        
        # 处理网络路径和本地路径
        if path.startswith('\\\\'):
            # 网络路径：\\server\share\folder
            clean = path.lstrip('\\')
            parts = clean.split('\\')
            if len(parts) >= 1:
                parts = ['\\\\' + parts[0]] + parts[1:]
        else:
            # 本地路径
            parts = list(Path(path).parts)
        
        # 构建HTML链接
        html_parts = ["当前位置: "]
        current_path = ""
        
        for i, part in enumerate(parts):
            if i == 0:
                current_path = part
            else:
                current_path = current_path.rstrip('\\') + '\\' + part
            
            # 最后一个部分不是链接
            if i == len(parts) - 1:
                html_parts.append(f"<b>{part}</b>")
            else:
                # 转义路径用于URL
                escaped_path = current_path.replace('\\', '/')
                html_parts.append(f'<a href="{escaped_path}" style="color: #4a9eff; text-decoration: none;">{part}</a>')
                html_parts.append(" › ")
        
        return "".join(html_parts)
    
    @Slot(str)
    def _on_breadcrumb_click(self, link: str):
        """面包屑链接点击"""
        # 还原路径格式
        path = link.replace('/', '\\')
        self._navigate_to(path)
    
    @Slot(int)
    def _on_table_scroll(self, value: int):
        """表格滚动事件 - 预加载更多数据"""
        if self.view_mode != 'browser':
            return
        
        # 获取最后可见的行号
        scrollbar = self.file_table.verticalScrollBar()
        max_val = scrollbar.maximum()
        
        # 只在滚动到底部80%时才检查加载更多
        if max_val > 0 and value > max_val * 0.8:
            # 计算可见区域的最后一行
            visible_rect = self.file_table.viewport().rect()
            last_visible_index = self.file_table.indexAt(visible_rect.bottomLeft())
            if last_visible_index.isValid():
                self.browser_model.check_load_more(last_visible_index.row())
    
    @Slot()
    def _on_go_back(self):
        """后退 - 返回上一个浏览的位置"""
        if not self._history_back:
            return
        
        current_path = self.browser_model.get_current_path()
        
        # 当前路径加入前进栈
        if current_path:
            self._history_forward.append(current_path)
        
        # 从后退栈取出上一个位置
        previous_path = self._history_back.pop()
        
        # 标记为历史导航（避免重复记录）
        self._history_navigating = True
        self._navigate_to(previous_path)
        self._history_navigating = False
    
    @Slot()
    def _on_go_forward(self):
        """前进 - 返回下一个浏览的位置"""
        if not self._history_forward:
            return
        
        current_path = self.browser_model.get_current_path()
        
        # 当前路径加入后退栈
        if current_path:
            self._history_back.append(current_path)
        
        # 从前进栈取出下一个位置
        next_path = self._history_forward.pop()
        
        # 标记为历史导航
        self._history_navigating = True
        self._navigate_to(next_path)
        self._history_navigating = False
    
    @Slot()
    def _on_go_home(self):
        """回到当前路径对应的顶级索引目录"""
        current_path = self.browser_model.get_current_path()
        
        if current_path:
            # 找到当前路径对应的扫描源（顶级目录）
            folders = self.db.get_folder_tree()
            current_lower = current_path.lower().replace('/', '\\')
            
            for folder in folders:
                folder_lower = folder.lower().replace('/', '\\')
                if current_lower.startswith(folder_lower):
                    self._navigate_to(folder)
                    return
        
        # 如果没有找到对应的顶级目录，导航到第一个索引目录
        folders = self.db.get_folder_tree()
        if folders:
            self._navigate_to(folders[0])
    
    @Slot()
    def _on_toggle_view(self):
        """切换视图模式"""
        if self.view_mode == 'browser':
            # 切换到平铺视图
            self.view_mode = 'flat'
            self.file_table.setModel(self.file_model)
            self.view_toggle_btn.setText("📂 浏览视图")
            self.back_btn.setEnabled(False)
            self.path_label.setText("平铺视图 (显示所有文件)")
        else:
            # 切换到浏览视图 - 导航到第一个索引目录
            folders = self.db.get_folder_tree()
            first_folder = folders[0] if folders else ""
            self._navigate_to(first_folder)
    
    def _show_context_menu(self, pos):
        """显示右键菜单"""
        index = self.file_table.indexAt(pos)
        if not index.isValid():
            return
        
        # 根据视图模式获取项目信息
        if self.view_mode == 'browser':
            item = self.browser_model.get_item_at(index.row())
            if not item:
                return
            full_path = item.get('full_path', '')
            is_dir = item.get('is_dir', False)
            file_id = item.get('id')
        else:
            file_info = self.file_model.get_file_at(index.row())
            if not file_info:
                return
            full_path = file_info.get('full_path', '')
            is_dir = False
            file_id = file_info.get('id')
        
        menu = QMenu(self)
        
        if is_dir:
            enter_action = menu.addAction("📂 进入目录")
            enter_action.triggered.connect(lambda: self._navigate_to(full_path))
            
            open_action = menu.addAction("📁 在资源管理器中打开")
            open_action.triggered.connect(lambda: self._open_folder_in_explorer(full_path))
        else:
            # 在索引中打开（导航到文件所在目录并高亮选中）
            parent_folder = str(Path(full_path).parent) if full_path else ''
            filename = Path(full_path).name if full_path else ''
            if parent_folder:
                index_action = menu.addAction("在索引中打开")
                index_action.triggered.connect(
                    lambda checked=False, pf=parent_folder, fn=filename: 
                    self._navigate_and_select(pf, fn)
                )
            
            open_action = menu.addAction("打开所在位置")
            open_action.triggered.connect(lambda: self._open_file_location(full_path))
        
        copy_action = menu.addAction("复制路径")
        copy_action.triggered.connect(lambda: self._copy_to_clipboard(full_path))
        
        if not is_dir and file_id:
            menu.addSeparator()
            delete_action = menu.addAction("从索引中删除")
            delete_action.triggered.connect(lambda: self._delete_from_index(file_id))
        
        menu.exec_(self.file_table.viewport().mapToGlobal(pos))
    
    def _open_file_location(self, path: str):
        """打开文件所在位置"""
        if path:
            try:
                subprocess.run(['explorer', '/select,', path], check=False)
            except Exception as e:
                QMessageBox.warning(self, "错误", f"无法打开位置: {e}")
    
    def _open_folder_in_explorer(self, folder_path: str):
        """在资源管理器中打开文件夹"""
        if folder_path:
            try:
                subprocess.run(['explorer', folder_path], check=False)
            except Exception as e:
                QMessageBox.warning(self, "错误", f"无法打开文件夹: {e}")
    
    def _copy_to_clipboard(self, text: str):
        """复制到剪贴板"""
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(text)
        self.statusbar.showMessage("已复制到剪贴板", 2000)
    
    def _delete_from_index(self, file_id: int):
        """从索引中删除"""
        # TODO: 实现删除功能
        pass
    
    @Slot()
    def _on_ai_organize(self):
        """AI 媒体库整理"""
        from ui.media_wizard import MediaWizardDialog
        
        dialog = MediaWizardDialog(self, self.db)
        # 连接信号，扫描完成后刷新主窗口数据
        dialog.scan_finished.connect(self._refresh_data)
        dialog.exec_()
    
    @Slot()
    def _on_export_csv(self):
        """导出CSV"""
        import csv
        from datetime import datetime
        from PySide6.QtWidgets import QApplication
        from ui.export_dialog import ExportProgressDialog
        
        # 检查数据库是否有数据
        stats = self.db.get_stats()
        if stats['total_files'] == 0:
            QMessageBox.warning(self, "提示", "数据库为空，没有可导出的数据")
            return
        
        path, _ = QFileDialog.getSaveFileName(
            self, "导出CSV文件",
            "fileindex_export.csv",
            "CSV文件 (*.csv)"
        )
        
        if not path:
            return
        
        # 创建导出进度对话框
        progress = ExportProgressDialog("导出 CSV", self)
        progress.show()
        QApplication.processEvents()
        
        try:
            # 使用数据库管理器的上下文管理器
            with self.db._get_connection() as conn:
                # 先获取总数用于进度显示
                total_count = conn.execute("SELECT COUNT(*) FROM files WHERE is_dir = 0").fetchone()[0]
                
                cursor = conn.execute("""
                    SELECT f.filename as name, f.extension, fo.path, f.size_bytes, f.ctime, f.mtime, 
                           f.ai_category, f.ai_tags
                    FROM files f
                    JOIN folders fo ON f.folder_id = fo.id
                    WHERE f.is_dir = 0
                    ORDER BY fo.path, f.filename
                """)
                
                with open(path, 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f)
                    writer.writerow(['文件名', '类型', '完整路径', '所在目录', '大小', '创建时间', '修改时间', 'AI分类', 'AI标签'])
                    
                    count = 0
                    for row in cursor:
                        if progress.is_cancelled():
                            break
                        
                        name, ext, folder, size, ctime, mtime, ai_cat, ai_tags = row
                        
                        # 格式化大小
                        size = size or 0
                        if size < 1024:
                            size_str = f"{size} B"
                        elif size < 1024 * 1024:
                            size_str = f"{size / 1024:.1f} KB"
                        elif size < 1024 * 1024 * 1024:
                            size_str = f"{size / (1024 * 1024):.1f} MB"
                        else:
                            size_str = f"{size / (1024 * 1024 * 1024):.2f} GB"
                        
                        # 格式化时间
                        ctime_str = datetime.fromtimestamp(ctime).strftime('%Y-%m-%d %H:%M') if ctime else ''
                        mtime_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M') if mtime else ''
                        
                        # 完整路径
                        full_path = f"{folder}\\{name}" if folder else name
                        
                        writer.writerow([
                            name, ext or '', full_path, folder or '',
                            size_str, ctime_str, mtime_str,
                            ai_cat or '', ai_tags or ''
                        ])
                        count += 1
                        
                        # 每1000条更新一次进度
                        if count % 1000 == 0:
                            progress.update_progress(count, total_count, f"已导出 {count} 个文件")
                            QApplication.processEvents()
            
            progress.close()
            
            if not progress.is_cancelled():
                QMessageBox.information(self, "成功", f"已导出 {count} 条文件记录到:\n{path}\n\n注：仅导出文件，不含文件夹")
                
        except Exception as e:
            progress.close()
            QMessageBox.critical(self, "错误", f"导出失败: {e}")
    
    @Slot()
    def _on_export_html(self):
        """导出为 HTML 文件"""
        from PySide6.QtWidgets import QApplication
        from export.html_exporter import HtmlExporter
        from ui.export_dialog import ExportProgressDialog
        
        # 检查是否有数据
        stats = self.db.get_stats()
        if stats['total_files'] == 0:
            QMessageBox.warning(self, "提示", "数据库为空，没有可导出的数据")
            return
        
        # 选择保存路径
        path, _ = QFileDialog.getSaveFileName(
            self, "导出HTML文件",
            "fileindex_export.html",
            "HTML文件 (*.html)"
        )
        
        if not path:
            return
        
        # 创建导出进度对话框
        progress = ExportProgressDialog("导出 HTML", self)
        progress.show()
        QApplication.processEvents()
        
        try:
            def update_progress(current, total, msg):
                if progress.is_cancelled():
                    return
                progress.update_progress(current, total, msg)
                QApplication.processEvents()
            
            # 执行导出
            exporter = HtmlExporter(self.db)
            success = exporter.export(path, update_progress)
            
            # 关闭进度对话框
            progress.close()
            
            if success:
                # 询问是否打开
                reply = QMessageBox.question(
                    self, "导出成功",
                    f"已导出 {stats['total_files']} 个文件到:\n{path}\n\n是否立即打开？",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes
                )
                if reply == QMessageBox.Yes:
                    import os
                    os.startfile(path)
            else:
                QMessageBox.critical(self, "错误", "导出失败，请检查控制台输出")
                
        except Exception as e:
            progress.close()
            QMessageBox.critical(self, "错误", f"导出失败: {e}")
    
    @Slot()
    def _on_optimize_db(self):
        """优化数据库（压缩和更新统计）"""
        reply = QMessageBox.question(
            self, "优化数据库",
            "优化将压缩数据库并更新统计信息，可能需要几秒钟。\n是否继续？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        
        if reply == QMessageBox.Yes:
            self.statusbar.showMessage("正在优化数据库...")
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)
            
            from PySide6.QtWidgets import QApplication
            QApplication.processEvents()
            
            try:
                result = self.db.optimize_database()
                
                self.progress_bar.setVisible(False)
                
                # 格式化大小
                def format_size(size):
                    for unit in ['B', 'KB', 'MB', 'GB']:
                        if size < 1024:
                            return f"{size:.1f} {unit}"
                        size /= 1024
                    return f"{size:.1f} TB"
                
                msg = f"优化完成！\n\n"
                msg += f"优化前: {format_size(result['size_before'])}\n"
                msg += f"优化后: {format_size(result['size_after'])}\n"
                msg += f"节省: {format_size(result['saved'])}"
                
                self.statusbar.showMessage("数据库优化完成", 5000)
                QMessageBox.information(self, "优化完成", msg)
            except Exception as e:
                self.progress_bar.setVisible(False)
                QMessageBox.critical(self, "优化失败", f"优化过程出错: {e}")
    
    @Slot()
    def _on_clear_index(self):
        """清除所有索引数据"""
        stats = self.db.get_stats()
        if stats['total_files'] == 0:
            QMessageBox.information(self, "提示", "数据库已经是空的")
            return
        
        reply = QMessageBox.warning(
            self, "确认清除",
            f"确定要清除所有索引数据吗？\n\n"
            f"当前共有 {stats['total_files']:,} 个文件记录。\n"
            f"此操作不可撤销！",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.statusbar.showMessage("正在清除索引...")
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)
            
            from PySide6.QtWidgets import QApplication
            QApplication.processEvents()
            
            try:
                # 获取所有扫描源并逐个清除
                sources = self.db.get_folder_tree()
                for source in sources:
                    self.db.clear_source(source)
                
                # 优化数据库回收空间
                self.db.optimize_database()
                
                self.progress_bar.setVisible(False)
                self.statusbar.showMessage("索引已清除", 5000)
                
                # 刷新界面
                self._refresh_data()
                self._update_stats()
                
                QMessageBox.information(self, "完成", "所有索引数据已清除")
            except Exception as e:
                self.progress_bar.setVisible(False)
                QMessageBox.critical(self, "错误", f"清除失败: {e}")
    
    @Slot()
    def _on_backup(self):
        """备份数据库"""
        import shutil
        from datetime import datetime
        
        # 检查是否有文件记录
        stats = self.db.get_stats()
        if stats['total_files'] == 0:
            QMessageBox.information(
                self, "无需备份",
                "当前文件记录为0，无需备份。"
            )
            return
        
        # 默认备份文件名包含时间戳
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"file_index_backup_{timestamp}.db"
        
        path, _ = QFileDialog.getSaveFileName(
            self, "保存备份文件",
            default_name,
            "SQLite数据库 (*.db);;所有文件 (*.*)"
        )
        
        if path:
            try:
                # 复制数据库文件
                shutil.copy2(str(config.database_path), path)
                QMessageBox.information(
                    self, "备份成功",
                    f"数据库已备份到:\n{path}\n\n共 {stats['total_files']} 条文件记录"
                )
            except Exception as e:
                QMessageBox.critical(self, "备份失败", f"无法备份数据库: {e}")
    
    @Slot()
    def _on_restore(self):
        """从备份恢复数据库"""
        import shutil
        
        reply = QMessageBox.warning(
            self, "确认恢复",
            "恢复操作将会覆盖当前的所有索引数据！\n\n确定要继续吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        path, _ = QFileDialog.getOpenFileName(
            self, "选择备份文件",
            "",
            "SQLite数据库 (*.db);;所有文件 (*.*)"
        )
        
        if path:
            try:
                # 关闭当前数据库连接（通过重新导入）
                # 复制备份文件到数据库位置
                shutil.copy2(path, str(config.database_path))
                
                # 重新初始化数据库连接
                self.db = DatabaseManager(config.database_path)
                
                # 刷新UI
                self._refresh_data()
                
                stats = self.db.get_stats()
                QMessageBox.information(
                    self, "恢复成功",
                    f"数据库已从备份恢复！\n\n共 {stats['total_files']} 条文件记录"
                )
            except Exception as e:
                QMessageBox.critical(self, "恢复失败", f"无法恢复数据库: {e}")
    
    @Slot()
    def _on_show_errors(self):
        """显示扫描错误列表"""
        errors = self.db.get_scan_errors()
        
        if not errors:
            QMessageBox.information(self, "无错误", "没有扫描错误记录")
            return
        
        # 创建错误对话框
        from PySide6.QtWidgets import QDialog, QTextEdit, QVBoxLayout, QPushButton, QHBoxLayout
        
        dialog = QDialog(self)
        dialog.setWindowTitle(f"扫描错误 ({len(errors)} 条)")
        dialog.resize(700, 400)
        
        layout = QVBoxLayout(dialog)
        
        # 错误列表
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        
        error_text = ""
        for err in errors:
            from datetime import datetime
            error_time = datetime.fromtimestamp(err['error_time']).strftime('%Y-%m-%d %H:%M:%S') if err.get('error_time') else ''
            resolved = "✓" if err.get('resolved') else "✗"
            error_text += f"[{resolved}] {error_time}\n"
            error_text += f"    路径: {err.get('file_path', '')}\n"
            error_text += f"    错误: {err.get('error_message', '')}\n"
            error_text += f"    来源: {err.get('scan_source', '')}\n\n"
        
        text_edit.setPlainText(error_text)
        layout.addWidget(text_edit)
        
        # 按钮区
        btn_layout = QHBoxLayout()
        
        clear_btn = QPushButton("清除所有错误")
        def on_clear():
            reply = QMessageBox.question(dialog, "确认", "确定要清除所有错误记录吗？")
            if reply == QMessageBox.Yes:
                self.db.clear_errors()
                self._update_error_count()
                dialog.accept()
        clear_btn.clicked.connect(on_clear)
        btn_layout.addWidget(clear_btn)
        
        btn_layout.addStretch()
        
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(close_btn)
        
        layout.addLayout(btn_layout)
        dialog.exec_()
    
    def _update_error_count(self):
        """更新错误计数显示"""
        count = self.db.get_error_count()
        if count > 0:
            self.error_action.setText(f"⚠️ 错误 ({count})")
        else:
            self.error_action.setText("⚠️ 错误 (0)")
    
    @Slot()
    def _on_settings(self):
        """打开设置对话框"""
        from ui.settings_dialog import SettingsDialog
        dialog = SettingsDialog(self)
        if dialog.exec_():
            config.save()
            self.statusbar.showMessage("设置已保存", 2000)
    
    def eventFilter(self, obj, event):
        """事件过滤器 - 捕获鼠标侧键导航"""
        from PySide6.QtCore import QEvent, Qt
        
        if event.type() == QEvent.MouseButtonPress:
            if event.button() == Qt.BackButton:
                # 鼠标后退侧键
                self._on_go_back()
                return True
            elif event.button() == Qt.ForwardButton:
                # 鼠标前进侧键
                self._on_go_forward()
                return True
        
        return super().eventFilter(obj, event)
    
    def closeEvent(self, event):
        """关闭事件"""
        # 保存窗口尺寸
        if config.get("ui", "remember_window_size"):
            config.set("ui", "window_width", value=self.width())
            config.set("ui", "window_height", value=self.height())
            config.save()
        
        # 停止扫描线程
        if self.scanner_thread and self.scanner_thread.isRunning():
            self.scanner_thread.cancel()
            self.scanner_thread.wait(2000)
        
        event.accept()
