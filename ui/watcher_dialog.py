"""
目录监控管理窗口
提供监控功能开关、目录列表管理、轮询设置等
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QCheckBox,
    QListWidget, QListWidgetItem, QPushButton, QLabel, QSpinBox,
    QFileDialog, QMessageBox, QWidget
)
from PySide6.QtCore import Qt, Signal

from watcher.config import WatcherConfig, MonitoredFolder

from logger import get_logger

logger = get_logger("watcher")

class WatcherDialog(QDialog):
    """目录监控管理窗口"""
    
    # 信号
    config_changed = Signal()
    scan_requested = Signal(list)  # 待扫描的目录列表
    
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.config = WatcherConfig(db)
        
        self.setWindowTitle("目录监控管理")
        self.setMinimumSize(500, 450)
        
        self._init_ui()
        self._load_config()
    
    def _init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout(self)
        
        # 1. 功能开关
        switch_group = QGroupBox("功能开关")
        switch_layout = QVBoxLayout(switch_group)
        
        self.enable_cb = QCheckBox("启用目录监控功能")
        self.enable_cb.setToolTip("启动时自动检测监控目录的变化")
        switch_layout.addWidget(self.enable_cb)
        
        self.silent_cb = QCheckBox("静默更新（不显示扫描进度弹窗）")
        self.silent_cb.setToolTip("检测到变化时自动更新索引，不弹出扫描进度窗口")
        switch_layout.addWidget(self.silent_cb)
        
        layout.addWidget(switch_group)
        
        # 2. 监控目录列表
        folders_group = QGroupBox("监控目录列表")
        folders_layout = QVBoxLayout(folders_group)
        
        self.folder_list = QListWidget()
        self.folder_list.setSelectionMode(QListWidget.ExtendedSelection)
        folders_layout.addWidget(self.folder_list)
        
        # 按钮行
        btn_layout = QHBoxLayout()
        
        add_btn = QPushButton("+ 添加目录")
        add_btn.clicked.connect(self._on_add_folder)
        btn_layout.addWidget(add_btn)
        
        remove_btn = QPushButton("- 移除选中")
        remove_btn.clicked.connect(self._on_remove_folder)
        btn_layout.addWidget(remove_btn)
        
        check_btn = QPushButton("立即检查")
        check_btn.clicked.connect(self._on_check_now)
        btn_layout.addWidget(check_btn)
        
        btn_layout.addStretch()
        folders_layout.addLayout(btn_layout)
        
        layout.addWidget(folders_group)
        
        # 3. 轮询设置
        poll_group = QGroupBox("轮询设置")
        poll_layout = QHBoxLayout(poll_group)
        
        poll_layout.addWidget(QLabel("网络路径默认轮询间隔:"))
        self.poll_spin = QSpinBox()
        self.poll_spin.setRange(1, 60)
        self.poll_spin.setValue(15)
        self.poll_spin.setSuffix(" 分钟")
        poll_layout.addWidget(self.poll_spin)
        poll_layout.addStretch()
        
        layout.addWidget(poll_group)
        
        # 4. 底部按钮
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        
        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self._on_save)
        bottom_layout.addWidget(save_btn)
        
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        bottom_layout.addWidget(cancel_btn)
        
        layout.addLayout(bottom_layout)
    
    def _load_config(self):
        """加载配置"""
        # 开关状态
        self.enable_cb.setChecked(self.config.is_enabled())
        self.silent_cb.setChecked(self.config.is_silent_update())
        
        # 轮询间隔
        self.poll_spin.setValue(self.config.get_default_poll_interval())
        
        # 目录列表
        self.folder_list.clear()
        for folder in self.config.get_all_folders():
            item = QListWidgetItem()
            item.setData(Qt.UserRole, folder)
            
            # 显示文本
            path_type = "本地" if folder.is_local else "网络"
            mode = "实时监控" if folder.is_local else f"轮询 {folder.poll_interval_minutes}分钟"
            text = f"{folder.path}\n类型: {path_type}  监控方式: {mode}"
            item.setText(text)
            
            # 启用状态
            item.setCheckState(Qt.Checked if folder.enabled else Qt.Unchecked)
            
            self.folder_list.addItem(item)
    
    def _on_add_folder(self):
        """添加目录"""
        path = QFileDialog.getExistingDirectory(
            self, "选择要监控的目录", "",
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )
        
        if not path:
            return
        
        # 检查是否已存在于监控列表
        if self.config.folder_exists(path):
            QMessageBox.warning(self, "提示", "该目录已在监控列表中")
            return
        
        # 检测父子目录冲突
        conflicts = self.config.find_parent_child_conflicts(path)
        
        if conflicts['parent']:
            # 新目录是已有目录的子目录
            parent_paths = [f.path for f in conflicts['parent']]
            QMessageBox.information(
                self, "已被父目录覆盖",
                f"该目录已被以下父目录覆盖监控：\n\n" + 
                "\n".join(parent_paths) +
                "\n\n无需重复添加。"
            )
            return
        
        merge_performed = False
        if conflicts['children']:
            # 新目录是已有目录的父目录
            child_paths = [f.path for f in conflicts['children']]
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("检测到子目录")
            msg_box.setIcon(QMessageBox.Question)
            msg_box.setText(
                f"该目录包含已在监控的子目录：\n\n" +
                "\n".join(child_paths[:5]) +
                ("\n..." if len(child_paths) > 5 else "") +
                "\n\n是否合并（移除子目录，只保留父目录）？"
            )
            
            merge_btn = msg_box.addButton("合并（推荐）", QMessageBox.AcceptRole)
            keep_btn = msg_box.addButton("全部保留", QMessageBox.ActionRole)
            cancel_btn = msg_box.addButton("取消", QMessageBox.RejectRole)
            
            msg_box.exec()
            clicked = msg_box.clickedButton()
            
            if clicked == cancel_btn:
                return
            elif clicked == merge_btn:
                # 合并：移除子目录
                self.config.merge_to_parent(path, conflicts['children'])
                merge_performed = True
        
        # 添加到监控数据库
        folder = self.config.add_folder(path, self.poll_spin.value())
        if not folder:
            QMessageBox.warning(self, "添加失败", "无法添加监控目录")
            return
        
        self._load_config()  # 刷新列表
        
        # 统一强制扫描弹窗
        if merge_performed:
            scan_message = "已合并子目录监控到父目录，需要扫描以确保索引同步。"
        else:
            scan_message = "添加监控目录需要扫描以确保索引同步。"
        
        reply = QMessageBox.question(
            self, "扫描目录",
            f"{scan_message}\n\n{path}\n\n点击「取消」将移除刚添加的监控。",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # 开始扫描
            logger.info(f"立即触发扫描: {path}")
            self.scan_requested.emit([path])
        else:
            # 取消：移除刚添加的监控
            self.config.remove_folder(folder.id)
            self._load_config()
            logger.info(f"用户取消扫描，移除监控: {path}")
    
    def _check_if_indexed(self, path: str) -> bool:
        """检查目录是否已在索引中"""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            normalized = path.replace('/', '\\').rstrip('\\')
            cursor.execute("""
                SELECT 1 FROM folders 
                WHERE path COLLATE NOCASE = ? OR path LIKE ? ESCAPE '\\'
                LIMIT 1
            """, (normalized, normalized.replace('\\', '\\\\') + '%'))
            return cursor.fetchone() is not None
    
    def _on_remove_folder(self):
        """移除选中目录"""
        selected = self.folder_list.selectedItems()
        if not selected:
            return
        
        reply = QMessageBox.question(
            self, "确认",
            f"确定要移除选中的 {len(selected)} 个目录吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            for item in selected:
                folder = item.data(Qt.UserRole)
                self.config.remove_folder(folder.id)
            self._load_config()
    
    def _on_check_now(self):
        """立即检查所有启用的目录"""
        enabled_folders = self.config.get_enabled_folders()
        if not enabled_folders:
            QMessageBox.information(self, "提示", "没有启用的监控目录")
            return
        
        # 检测每个目录的索引状态
        unindexed = []
        for folder in enabled_folders:
            if not self._check_if_indexed(folder.path):
                unindexed.append(folder.path)
        
        if unindexed:
            reply = QMessageBox.question(
                self, "索引缺失",
                f"检测到 {len(unindexed)} 个目录尚未索引：\n\n" + 
                "\n".join(unindexed[:5]) + 
                ("\n..." if len(unindexed) > 5 else "") +
                "\n\n是否立即扫描？",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.scan_requested.emit(unindexed)
        else:
            QMessageBox.information(self, "检查完成", "所有监控目录均已索引")
    
    def _on_save(self):
        """保存配置"""
        # 保存开关状态
        self.config.set_enabled(self.enable_cb.isChecked())
        self.config.set_silent_update(self.silent_cb.isChecked())
        self.config.set_default_poll_interval(self.poll_spin.value())
        
        # 收集新启用的目录（之前禁用，现在启用）
        newly_enabled = []
        new_poll_interval = self.poll_spin.value()
        
        # 保存各目录的启用状态和轮询间隔
        for i in range(self.folder_list.count()):
            item = self.folder_list.item(i)
            folder = item.data(Qt.UserRole)
            enabled = item.checkState() == Qt.Checked
            
            updates = {}
            
            # 检查启用状态变化
            if folder.enabled != enabled:
                updates['enabled'] = enabled
                # 如果是从禁用变为启用
                if enabled and not folder.enabled:
                    newly_enabled.append(folder.path)
            
            # 更新网络目录的轮询间隔
            if not folder.is_local and folder.poll_interval_minutes != new_poll_interval:
                updates['poll_interval_minutes'] = new_poll_interval
                logger.info(f"更新轮询间隔: {folder.path} -> {new_poll_interval}分钟")
            
            if updates:
                self.config.update_folder(folder.id, **updates)
        
        logger.info("配置已保存")
        self.config_changed.emit()
        
        # 检测新启用目录的索引状态
        if newly_enabled:
            logger.info(f"检测新启用目录的索引状态: {newly_enabled}")
            unindexed = [p for p in newly_enabled if not self._check_if_indexed(p)]
            
            if unindexed:
                reply = QMessageBox.question(
                    self, "索引缺失",
                    f"检测到 {len(unindexed)} 个新启用的目录尚未索引：\n\n" + 
                    "\n".join(unindexed[:5]) + 
                    ("\n..." if len(unindexed) > 5 else "") +
                    "\n\n是否立即扫描？",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    self.scan_requested.emit(unindexed)
        
        self.accept()
