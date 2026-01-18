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
        from PySide6.QtCore import QTimer
        QTimer.singleShot(500, self._check_watcher_on_startup)
        
        # 延迟启动运行时监控（在启动检测完成后）
        QTimer.singleShot(2000, self._start_runtime_watcher)
        
        # 安装事件过滤器以捕获鼠标侧键
        QApplication.instance().installEventFilter(self)
        
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
