# -*- coding: utf-8 -*-
"""
WatcherMixin - 目录监控功能
"""
from logger import get_logger

logger = get_logger("ui")


class WatcherMixin:
    """目录监控功能 Mixin"""
    
    def _on_watcher_dialog(self):
        """打开目录监控管理窗口"""
        from ui.watcher_dialog import WatcherDialog
        dialog = WatcherDialog(self.db, self)
        dialog.config_changed.connect(self._on_watcher_config_changed)
        dialog.scan_requested.connect(self._on_watcher_scan_requested)
        dialog.exec()
    
    def _on_watcher_config_changed(self):
        """监控配置变更"""
        logger.info("配置已变更，重新加载监控设置")
        if self._watcher_manager:
            # 重启监控以应用新配置
            self._watcher_manager.restart()
    
    def _on_watcher_scan_requested(self, paths: list, silent: bool = None):
        """监控窗口请求扫描目录"""
        logger.info(f"收到扫描请求: {paths}")
        if paths:
            # 检查是否静默模式
            if silent is None:
                from watcher.config import WatcherConfig
                from config import config as app_config
                watcher_config = WatcherConfig(self.db)
                silent = watcher_config.is_silent_update()
            
            if silent:
                # 静默模式：后台扫描，不显示进度弹窗
                self._on_multi_scan_silent(paths)
            else:
                # 正常模式：显示进度弹窗
                self._on_multi_scan_requested(paths)
    
    def _start_runtime_watcher(self):
        """启动运行时文件监控"""
        from watcher.manager import FileWatcherManager
        
        if self._watcher_manager is None:
            self._watcher_manager = FileWatcherManager(self.db, self)
            # 连接信号
            self._watcher_manager.status_changed.connect(self._on_watcher_status_changed)
            self._watcher_manager.scan_requested.connect(self._on_watcher_scan_requested)
        
        self._watcher_manager.start()
    
    def _on_watcher_status_changed(self, status_type: str, message: str):
        """监控状态变更"""
        # 更新状态栏显示
        logger.debug(f"状态: {status_type} - {message}")
        
        # 根据状态类型设置样式
        if status_type == "normal":
            icon = "🟢"
            color = "#28a745"
        elif status_type == "warning":
            icon = "🟡"
            color = "#ffc107"
        elif status_type == "error":
            icon = "🔴"
            color = "#dc3545"
        else:  # disabled
            icon = "⚪"
            color = "#6c757d"
        
        self.watcher_status_label.setText(f"{icon} {message}")
        self.watcher_status_label.setStyleSheet(f"color: {color}; padding: 0 10px;")
        
        # 同步更新托盘图标状态
        self._update_tray_status(status_type, message)
    
    def _check_watcher_on_startup(self):
        """启动时检测监控目录变化"""
        from watcher.config import WatcherConfig
        from watcher.reconciler import Reconciler
        
        watcher_config = WatcherConfig(self.db)
        
        # 检查功能是否启用
        if not watcher_config.is_enabled():
            logger.info("功能未启用，跳过启动检测")
            return
        
        # 检查是否有监控目录
        folders = watcher_config.get_enabled_folders()
        if not folders:
            logger.info("没有监控目录，跳过启动检测")
            return
        
        # 执行对账
        reconciler = Reconciler(watcher_config, self.db)
        changed, errors = reconciler.check_all_folders()
        
        # 处理无法访问的目录（可选：提示用户）
        if errors:
            logger.warning(f"{len(errors)} 个目录无法访问")
        
        # 有变化时弹窗提示
        if changed:
            self._show_change_alert(changed, reconciler)
    
    def _show_change_alert(self, changes: list, reconciler):
        """显示变化检测弹窗"""
        from ui.change_dialogs import ChangeAlertDialog, ChangeSelectDialog
        
        # 第一层弹窗
        alert = ChangeAlertDialog(len(changes), self)
        result = alert.exec()
        
        if alert.result_action == "all":
            # 全部更新
            self._update_changed_folders(changes, reconciler)
        elif alert.result_action == "select":
            # 打开第二层弹窗选择
            select_dialog = ChangeSelectDialog(changes, self)
            if select_dialog.exec():
                selected = select_dialog.get_selected()
                if selected:
                    self._update_changed_folders(selected, reconciler)
        else:
            # 下次提醒 - 不做任何操作
            logger.info("用户选择下次提醒，跳过更新")
    
    def _update_changed_folders(self, changes: list, reconciler):
        """更新选中的目录索引"""
        logger.info(f"开始更新 {len(changes)} 个目录的索引")
        
        # 分离新目录和已索引目录
        new_folders = []
        existing_folders = []
        
        for change in changes:
            if change.is_new_folder:
                new_folders.append(change.folder.path)
            else:
                existing_folders.append(change)
        
        # 1. 新目录：触发完整扫描
        if new_folders:
            logger.info(f"触发新目录扫描: {new_folders}")
            self._on_multi_scan_requested(new_folders)
            # 扫描完成后会更新 mtime
        
        # 2. 已索引目录：触发增量扫描（暂时只更新 mtime，后续实现增量扫描）
        for change in existing_folders:
            folder = change.folder
            logger.debug(f"  增量更新: {folder.path}")
            # TODO: 执行实际的增量扫描，对比文件变化并更新索引
            # 目前先触发完整扫描
            self._on_multi_scan_requested([folder.path])
            reconciler.update_folder_mtime(folder, change.new_mtime)
        
        logger.info("索引更新任务已启动")
