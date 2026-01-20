"""
FileRecorder - 智能文件索引助手
https://github.com/Wangtengzhou/FileRecorder

主窗口 - 采用 Mixin 模式拆分功能模块
"""
import sys
import os
from pathlib import Path

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QAction, QIcon, QMouseEvent
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QToolBar, QStatusBar, QLineEdit, QPushButton,
    QTableView, QHeaderView, QMessageBox,
    QProgressBar, QLabel, QSplitter, QTreeWidget,
    QComboBox, QApplication
)

from database.db_manager import DatabaseManager
from ui.file_table import FileTableModel, ElideDelegate, HighlightDelegate
from ui.file_browser import FileBrowserModel
from config import config

from logger import get_logger

# 导入所有 Mixin
from ui.mixins import (
    TrayMixin,
    DatabaseMixin,
    ExportMixin,
    NavigationMixin,
    FolderTreeMixin,
    ScannerMixin,
    WatcherMixin,
)

logger = get_logger("ui")


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


class MainWindow(
    QMainWindow,
    TrayMixin,
    DatabaseMixin,
    ExportMixin,
    NavigationMixin,
    FolderTreeMixin,
    ScannerMixin,
    WatcherMixin,
):
    """主窗口 - 通过 Mixin 组合各功能模块"""
    
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
        self._silent_scan_mode = False
        
        # 浏览模式: 'browser'(逐级) 或 'flat'(平铺)
        self.view_mode = 'browser'
        
        # 导航历史（用于前进后退）
        self._history_back = []   # 后退栈
        self._history_forward = []  # 前进栈
        self._history_navigating = False  # 是否正在通过历史导航
        
        # 文件监控管理器
        self._watcher_manager = None
        
        # 系统托盘图标
        self._tray_icon = None
        self._force_quit = False  # 是否强制退出（不询问）
        self._init_tray_icon()
        
        # 初始化界面
        self._init_ui()
        self._init_toolbar()
        self._init_statusbar()
        
        # 加载数据
        self._refresh_data()
        
        # 更新错误计数
        self._update_error_count()
        
        # 启动时检测监控目录变化（延迟执行，等待窗口显示）
        # 对账完成后会自动启动运行时监控
        from PySide6.QtCore import QTimer
        QTimer.singleShot(500, self._check_watcher_and_start_monitoring)
        
        # 安装事件过滤器以捕获鼠标侧键
        QApplication.instance().installEventFilter(self)
        
        # 初始化快捷键
        self._init_shortcuts()
        
    def showEvent(self, event):
        """窗口显示事件"""
        super().showEvent(event)
        # 延迟设置标题栏颜色，确保窗口已完全初始化 (关键修复)
        from PySide6.QtCore import QTimer
        from ui.theme import theme_manager
        QTimer.singleShot(100, lambda: theme_manager.apply_theme(theme_manager._mode))

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
        
        # === 性能优化设置 ===
        self.file_table.setWordWrap(False)  # 禁用自动换行
        self.file_table.verticalHeader().setVisible(False)  # 隐藏行号，减少渲染
        self.file_table.setHorizontalScrollMode(QTableView.ScrollPerPixel)  # 平滑横向滚动
        self.file_table.setVerticalScrollMode(QTableView.ScrollPerPixel)  # 平滑纵向滚动

        
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
        
        # 设置列宽 - 固定模式，避免自动计算
        header = self.file_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Fixed)  # 固定列宽，提升性能
        header.setStretchLastSection(True)  # 最后一列拉伸
        # 设置默认宽度
        self.file_table.setColumnWidth(0, 300)  # 名称
        self.file_table.setColumnWidth(1, 70)   # 类型
        self.file_table.setColumnWidth(2, 80)   # 大小
        self.file_table.setColumnWidth(3, 120)  # 时间
        self.file_table.setColumnWidth(4, 80)   # AI分类

        
        right_layout.addWidget(self.file_table)
        
        # 空结果提示标签（初始隐藏）
        self.empty_hint_label = QLabel()
        self.empty_hint_label.setAlignment(Qt.AlignCenter)
        self.empty_hint_label.setStyleSheet("""
            QLabel {
                color: #888888;
                font-size: 14px;
                padding: 40px;
            }
        """)
        self.empty_hint_label.hide()
        right_layout.addWidget(self.empty_hint_label)
        
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
        
        # 目录监控
        watcher_action = QAction("📡 目录监控", self)
        watcher_action.triggered.connect(self._on_watcher_dialog)
        toolbar.addAction(watcher_action)
        
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
        
        # 监控状态标签（左下角）
        self.watcher_status_label = QLabel("⚪ 监控: 未启用")
        self.watcher_status_label.setStyleSheet("color: #6c757d; padding: 0 10px;")
        self.watcher_status_label.setToolTip("点击打开监控设置")
        self.watcher_status_label.setCursor(Qt.PointingHandCursor)
        self.watcher_status_label.mousePressEvent = lambda e: self._on_watcher_dialog()
        self.statusbar.addWidget(self.watcher_status_label)
        
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
            
            # 为文件名列设置搜索高亮代理
            search_terms = keyword.split() if keyword else []
            highlight_delegate = HighlightDelegate(self.file_table)
            highlight_delegate.set_search_terms(search_terms)
            self.file_table.setItemDelegateForColumn(0, highlight_delegate)
            
            # 为所在目录列设置自适应省略代理
            self.file_table.setItemDelegateForColumn(4, ElideDelegate(self.file_table))
            
            self.view_toggle_btn.setText("📂 浏览视图")
            self.back_btn.setEnabled(False)
            
            if files:
                self.path_label.setText(f"搜索结果: '{keyword}' ({len(files)} 个文件)")
                self.statusbar.showMessage(f"找到 {len(files)} 个匹配文件")
                self._hide_empty_hint()
            else:
                # 搜索无结果时显示提示
                self.path_label.setText(f"搜索结果: '{keyword}' (无匹配)")
                self.statusbar.showMessage(f"未找到与 \"{keyword}\" 相关的文件")
                self._show_empty_hint(f"未找到与 \"{keyword}\" 相关的搜索结果")
        else:
            # 空搜索切换回浏览视图
            self._hide_empty_hint()
            
            # 切换回浏览模式
            self.view_mode = 'browser'
            self.file_table.setModel(self.browser_model)
            self.view_toggle_btn.setText("📋 平铺视图")
            
            # 重置浏览模式列宽（5列）
            self.file_table.setColumnWidth(0, 300)  # 名称
            self.file_table.setColumnWidth(1, 70)   # 类型
            self.file_table.setColumnWidth(2, 80)   # 大小
            self.file_table.setColumnWidth(3, 120)  # 时间
            self.file_table.setColumnWidth(4, 80)   # AI分类
            
            # 清除搜索高亮代理
            self.file_table.setItemDelegateForColumn(0, None)
            self.file_table.setItemDelegateForColumn(4, None)
            
            self._on_go_home()
    
    @Slot()
    def _on_clear_search(self):
        """清除搜索"""
        self.search_input.clear()
        self.ext_filter.setCurrentIndex(0)
        self._hide_empty_hint()
        
        # 切换回浏览模式
        self.view_mode = 'browser'
        self.file_table.setModel(self.browser_model)
        self.view_toggle_btn.setText("📋 平铺视图")
        
        # 重置浏览模式列宽（5列）
        self.file_table.setColumnWidth(0, 300)  # 名称
        self.file_table.setColumnWidth(1, 70)   # 类型
        self.file_table.setColumnWidth(2, 80)   # 大小
        self.file_table.setColumnWidth(3, 120)  # 时间
        self.file_table.setColumnWidth(4, 80)   # AI分类
        
        # 清除搜索高亮代理
        self.file_table.setItemDelegateForColumn(0, None)
        self.file_table.setItemDelegateForColumn(4, None)
        
        self._refresh_data()
    
    def eventFilter(self, obj, event):
        """事件过滤器 - 捕获鼠标侧键导航"""
        from PySide6.QtCore import QEvent
        
        if event.type() == QEvent.MouseButtonPress:
            # 检查是否是鼠标侧键
            if hasattr(event, 'button'):
                from PySide6.QtCore import Qt
                if event.button() == Qt.BackButton:
                    self._on_go_back()
                    return True
                elif event.button() == Qt.ForwardButton:
                    self._on_go_forward()
                    return True
        
        return super().eventFilter(obj, event)
    
    def closeEvent(self, event):
        """关闭事件 - 委托给 TrayMixin"""
        self._handle_close_event(event)
    
    # ========== 快捷键相关 ==========
    
    def _init_shortcuts(self):
        """初始化快捷键"""
        from PySide6.QtGui import QShortcut, QKeySequence
        
        # Ctrl+F 聚焦搜索框
        QShortcut(QKeySequence("Ctrl+F"), self, self._focus_search)
        
        # F5 刷新
        QShortcut(QKeySequence("F5"), self, self._refresh_data)
        
        # Backspace 返回上级目录
        QShortcut(QKeySequence("Backspace"), self, self._on_backspace)
        
        # Alt+Left/Right 后退/前进
        QShortcut(QKeySequence("Alt+Left"), self, self._on_go_back)
        QShortcut(QKeySequence("Alt+Right"), self, self._on_go_forward)
        
        # Esc 清除搜索
        QShortcut(QKeySequence("Escape"), self, self._on_escape)
        
        # Ctrl+C 复制选中文件路径
        QShortcut(QKeySequence("Ctrl+C"), self, self._copy_selected_paths)
        
        # Delete 删除索引
        QShortcut(QKeySequence("Delete"), self, self._on_delete_key_pressed)
    
    def _on_delete_key_pressed(self):
        """Delete 键处理 - 根据焦点决定删除左侧目录树还是右侧表格"""
        # 检查左侧目录树是否有焦点
        if self.folder_tree.hasFocus():
            item = self.folder_tree.currentItem()
            if item:
                folder_path = item.data(0, Qt.UserRole)
                if folder_path:
                    self._delete_folder_index(folder_path)
        else:
            # 右侧表格删除
            self._on_delete_selected()
    
    def _focus_search(self):
        """聚焦搜索框并全选"""
        self.search_input.setFocus()
        self.search_input.selectAll()
    
    def _on_backspace(self):
        """Backspace 键处理 - 如果搜索框没有焦点则返回上级"""
        if not self.search_input.hasFocus():
            self._on_go_back()
    
    def _on_escape(self):
        """Esc 键处理 - 清除搜索或取消焦点"""
        if self.search_input.text():
            self._on_clear_search()
        else:
            # 如果搜索框有焦点，移除焦点
            if self.search_input.hasFocus():
                self.file_table.setFocus()
    
    def _on_enter_selected(self):
        """Enter 键进入选中的文件夹"""
        # 获取当前选中行
        indexes = self.file_table.selectionModel().selectedRows()
        if not indexes:
            return
        
        # 获取第一个选中项
        index = indexes[0]
        model = self.file_table.model()
        
        if hasattr(model, 'get_item'):
            item = model.get_item(index.row())
        else:
            item = model.get_file_at(index.row())
        
        if item and item.get('is_dir'):
            # 进入文件夹
            folder_path = item.get('full_path', '')
            if folder_path:
                self._navigate_to(folder_path)
    
    def _copy_selected_paths(self):
        """复制选中文件的路径到剪贴板"""
        indexes = self.file_table.selectionModel().selectedRows()
        if not indexes:
            return
        
        model = self.file_table.model()
        paths = []
        
        for index in indexes:
            if hasattr(model, 'get_item'):
                item = model.get_item(index.row())
            else:
                item = model.get_file_at(index.row())
            
            if item:
                path = item.get('full_path', '')
                if path:
                    paths.append(path)
        
        if paths:
            clipboard = QApplication.clipboard()
            clipboard.setText('\n'.join(paths))
            self.statusbar.showMessage(f"已复制 {len(paths)} 个路径到剪贴板", 3000)
    
    def _on_delete_selected(self):
        """删除选中的项目（从索引中删除）"""
        from watcher.config import WatcherConfig
        
        indexes = self.file_table.selectionModel().selectedRows()
        if not indexes:
            return
        
        model = self.file_table.model()
        watcher_config = WatcherConfig(self.db)
        
        # 收集选中项目信息并分类
        monitored_items = []  # [(id, path, monitored_folder), ...]
        non_monitored_items = []  # [(id, path), ...]
        monitored_dirs = []  # [(path, monitored_folder), ...]
        non_monitored_dirs = []  # [path, ...]
        monitored_folders_set = {}  # {folder_id: MonitoredFolder}
        
        for index in indexes:
            if hasattr(model, 'get_item'):
                item = model.get_item(index.row())
            elif hasattr(model, 'get_item_at'):
                item = model.get_item_at(index.row())
            else:
                item = model.get_file_at(index.row())
            
            if not item:
                continue
            
            full_path = item.get('full_path', '')
            monitored = watcher_config.is_path_monitored(full_path)
            
            if item.get('is_dir'):
                if monitored:
                    monitored_dirs.append((full_path, monitored))
                    monitored_folders_set[monitored.id] = monitored
                else:
                    non_monitored_dirs.append(full_path)
            else:
                file_id = item.get('id')
                if file_id:
                    if monitored:
                        monitored_items.append((file_id, full_path, monitored))
                        monitored_folders_set[monitored.id] = monitored
                    else:
                        non_monitored_items.append((file_id, full_path))
        
        total_monitored = len(monitored_items) + len(monitored_dirs)
        total_non_monitored = len(non_monitored_items) + len(non_monitored_dirs)
        total_count = total_monitored + total_non_monitored
        
        if total_count == 0:
            return
        
        # 情况3：全部不在监控目录下 - 普通确认
        if total_monitored == 0:
            self._do_normal_delete(non_monitored_items, non_monitored_dirs)
            return
        
        # 构建监控目录信息
        monitored_paths = [f.path for f in monitored_folders_set.values()]
        monitored_info = "\n".join(monitored_paths[:5]) + ("\n..." if len(monitored_paths) > 5 else "")
        
        # 情况1：全部在监控目录下 - 三选项
        if total_non_monitored == 0:
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("监控保护")
            msg_box.setIcon(QMessageBox.Warning)
            msg_box.setText(f"选中的内容所在目录正在被监控：\n\n{monitored_info}")
            msg_box.setInformativeText("请选择操作：")
            
            remove_monitor_btn = msg_box.addButton("去除监控", QMessageBox.ActionRole)
            remove_both_btn = msg_box.addButton("去除并删除全部记录", QMessageBox.ActionRole)
            cancel_btn = msg_box.addButton("取消", QMessageBox.RejectRole)
            
            msg_box.setDefaultButton(cancel_btn)
            msg_box.exec()
            
            clicked_btn = msg_box.clickedButton()
            
            if clicked_btn == cancel_btn:
                return
            elif clicked_btn == remove_monitor_btn:
                # 只去除监控
                for folder in monitored_folders_set.values():
                    watcher_config.remove_folder(folder.id)
                self._refresh_data()
                logger.info(f"用户去除监控: {monitored_paths}")
                QMessageBox.information(self, "完成", "已去除监控，索引保留")
                return
            else:
                # 去除监控并删除全部
                for folder in monitored_folders_set.values():
                    watcher_config.remove_folder(folder.id)
                self._do_delete_all(monitored_items, monitored_dirs, [], [])
                return
        
        # 情况2：混合场景 - 四选项
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("监控保护")
        msg_box.setIcon(QMessageBox.Warning)
        msg_box.setText(f"部分选中内容所在目录正在被监控：\n\n{monitored_info}")
        msg_box.setInformativeText(f"监控内: {total_monitored} 项  |  监控外: {total_non_monitored} 项\n\n请选择操作：")
        
        only_non_monitored_btn = msg_box.addButton("仅删除非监控文件", QMessageBox.ActionRole)
        remove_monitor_btn = msg_box.addButton("去除监控", QMessageBox.ActionRole)
        remove_both_btn = msg_box.addButton("去除并删除全部记录", QMessageBox.ActionRole)
        cancel_btn = msg_box.addButton("取消", QMessageBox.RejectRole)
        
        msg_box.setDefaultButton(cancel_btn)
        msg_box.exec()
        
        clicked_btn = msg_box.clickedButton()
        
        if clicked_btn == cancel_btn:
            return
        elif clicked_btn == only_non_monitored_btn:
            # 仅删除非监控文件
            self._do_normal_delete(non_monitored_items, non_monitored_dirs)
            return
        elif clicked_btn == remove_monitor_btn:
            # 只去除监控
            for folder in monitored_folders_set.values():
                watcher_config.remove_folder(folder.id)
            self._refresh_data()
            logger.info(f"用户去除监控: {monitored_paths}")
            QMessageBox.information(self, "完成", "已去除监控，索引保留")
            return
        else:
            # 去除监控并删除全部
            for folder in monitored_folders_set.values():
                watcher_config.remove_folder(folder.id)
            self._do_delete_all(monitored_items, monitored_dirs, non_monitored_items, non_monitored_dirs)
    
    def _do_normal_delete(self, items: list, dirs: list):
        """执行普通删除（非监控）"""
        total_count = len(items) + len(dirs)
        if total_count == 0:
            return
        
        msg_parts = []
        if items:
            msg_parts.append(f"{len(items)} 个文件")
        if dirs:
            msg_parts.append(f"{len(dirs)} 个目录")
        
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要从索引中删除以下内容吗？\n\n{' 和 '.join(msg_parts)}\n\n此操作不会删除实际文件。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        deleted_count = 0
        
        if items:
            file_ids = [item[0] for item in items]
            file_paths = [item[1] for item in items]
            deleted_count += self.db.delete_files(file_ids)
            for path in file_paths:
                logger.info(f"用户删除索引: {path}")
        
        for dir_path in dirs:
            count = self.db.clear_source(dir_path)
            deleted_count += count
            self.db.delete_dir_record(dir_path)
            logger.info(f"用户删除目录索引: {dir_path}, 删除 {count} 条记录")
        
        self._refresh_data()
        QMessageBox.information(self, "删除完成", f"已从索引中删除 {deleted_count} 条记录")
    
    def _do_delete_all(self, monitored_items: list, monitored_dirs: list, non_monitored_items: list, non_monitored_dirs: list):
        """执行删除全部（监控已去除）"""
        deleted_count = 0
        
        # 删除监控项
        if monitored_items:
            file_ids = [item[0] for item in monitored_items]
            file_paths = [item[1] for item in monitored_items]
            deleted_count += self.db.delete_files(file_ids)
            for path in file_paths:
                logger.info(f"用户删除索引: {path}")
        
        for dir_path, _ in monitored_dirs:
            count = self.db.clear_source(dir_path)
            deleted_count += count
            self.db.delete_dir_record(dir_path)
            logger.info(f"用户删除目录索引: {dir_path}, 删除 {count} 条记录")
        
        # 删除非监控项
        if non_monitored_items:
            file_ids = [item[0] for item in non_monitored_items]
            file_paths = [item[1] for item in non_monitored_items]
            deleted_count += self.db.delete_files(file_ids)
            for path in file_paths:
                logger.info(f"用户删除索引: {path}")
        
        for dir_path in non_monitored_dirs:
            count = self.db.clear_source(dir_path)
            deleted_count += count
            self.db.delete_dir_record(dir_path)
            logger.info(f"用户删除目录索引: {dir_path}, 删除 {count} 条记录")
        
        self._refresh_data()
        QMessageBox.information(self, "删除完成", f"已去除监控并删除 {deleted_count} 条记录")
    
    def _show_empty_hint(self, message: str):
        """显示空结果提示"""
        self.empty_hint_label.setText(message)
        self.empty_hint_label.show()
        self.file_table.hide()
    
    def _hide_empty_hint(self):
        """隐藏空结果提示"""
        self.empty_hint_label.hide()
        self.file_table.show()

