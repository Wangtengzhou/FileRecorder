"""
FileRecorder - 智能文件索引助手
https://github.com/Wangtengzhou/FileRecorder

文件监控管理器 - 统一管理本地监控（watchdog）和网络轮询
"""
import os
import time
from typing import Optional, Callable

from PySide6.QtCore import QObject, Signal

from .config import WatcherConfig, MonitoredFolder
from .local_watcher import LocalWatcher, FileEvent
from .network_poller import NetworkPoller

from logger import get_logger

logger = get_logger("watcher")
class FileWatcherManager(QObject):
    """
    文件监控管理器
    统一管理本地目录实时监控和网络目录轮询
    """
    
    # 信号
    changes_detected = Signal(str, list)  # (folder_path, events/changes)
    status_changed = Signal(str, str)  # (状态类型, 消息) - normal/warning/error/disabled
    scan_requested = Signal(list)  # 需要扫描的目录列表
    
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.config = WatcherConfig(db)
        
        # 子监控器
        self._local_watcher = LocalWatcher(self)
        self._network_poller = NetworkPoller(self)
        
        # 连接信号
        self._local_watcher.changes_detected.connect(self._on_local_changes)
        self._network_poller.changes_detected.connect(self._on_network_changes)
        self._network_poller.connection_error.connect(self._on_connection_error)
        self._network_poller.connection_restored.connect(self._on_connection_restored)
        
        # 状态
        self._running = False
        self._error_paths: set[str] = set()
    
    # ========== 公共方法 ==========
    
    def is_running(self) -> bool:
        """是否正在运行"""
        return self._running
    
    def start(self):
        """启动监控"""
        if not self.config.is_enabled():
            logger.info("功能未启用，跳过启动")
            self._update_status()
            return
        
        if self._running:
            logger.debug("已在运行中")
            return
        
        logger.info("启动目录监控")
        self._running = True
        
        folders = self.config.get_enabled_folders()
        logger.info(f"加载 {len(folders)} 个监控目录")
        
        for folder in folders:
            self._start_folder_watch(folder)
        
        self._update_status()
    
    def stop(self):
        """停止监控"""
        logger.info("停止目录监控")
        self._running = False
        
        self._local_watcher.stop_all()
        self._network_poller.stop_all()
        self._error_paths.clear()
        
        self._update_status()
    
    def restart(self):
        """重启监控"""
        self.stop()
        # 重新加载配置（清除缓存）
        self.config = WatcherConfig(self.db)
        self.start()
    
    # ========== 动态配置变更 ==========
    
    def apply_config_changes(self, old_folders: list[MonitoredFolder], new_folders: list[MonitoredFolder]):
        """应用配置变更"""
        old_paths = {f.path: f for f in old_folders}
        new_paths = {f.path: f for f in new_folders}
        
        old_set = set(old_paths.keys())
        new_set = set(new_paths.keys())
        
        # 新增的目录
        added = new_set - old_set
        for path in added:
            logger.info(f"新增监控: {path}")
            self._start_folder_watch(new_paths[path])
        
        # 移除的目录
        removed = old_set - new_set
        for path in removed:
            logger.info(f"移除监控: {path}")
            self._stop_folder_watch(path)
        
        # 修改的目录（检查间隔变化等）
        for path in old_set & new_set:
            old_f = old_paths[path]
            new_f = new_paths[path]
            
            # 启用状态变化
            if old_f.enabled != new_f.enabled:
                if new_f.enabled:
                    self._start_folder_watch(new_f)
                else:
                    self._stop_folder_watch(path)
            
            # 轮询间隔变化
            elif not new_f.is_local and old_f.poll_interval_minutes != new_f.poll_interval_minutes:
                self._network_poller.update_interval(path, new_f.poll_interval_minutes)
        
        self._update_status()
    
    def on_global_toggle(self, enabled: bool):
        """全局开关变更"""
        if enabled:
            self.start()
        else:
            self.stop()
    
    # ========== 内部方法 ==========
    
    def _start_folder_watch(self, folder: MonitoredFolder):
        """启动单个目录的监控"""
        if not folder.enabled:
            return
        
        if folder.is_local:
            # 本地目录使用 watchdog
            self._local_watcher.add_watch(folder.path)
        else:
            # 网络目录使用轮询
            self._network_poller.add_poll(folder)
    
    def _stop_folder_watch(self, path: str):
        """停止单个目录的监控"""
        self._local_watcher.remove_watch(path)
        self._network_poller.remove_poll(path)
        self._error_paths.discard(path)
    
    def _on_local_changes(self, folder_path: str, events: list[FileEvent]):
        """本地目录变化回调"""
        logger.info(f"本地目录变化: {folder_path}, {len(events)} 个事件")
        
        # 更新 mtime
        try:
            mtime = os.stat(folder_path).st_mtime
            folders = self.config.get_all_folders()
            for f in folders:
                if f.path.lower() == folder_path.lower():
                    self.config.update_folder_mtime(f.id, mtime)
                    break
        except:
            pass
        
        # 发射信号（主窗口可以选择是否立即更新索引）
        self.changes_detected.emit(folder_path, events)
        
        # 触发扫描请求
        self.scan_requested.emit([folder_path])
    
    def _on_network_changes(self, folder_path: str, new_mtime: float):
        """网络目录变化回调"""
        logger.info(f"网络目录变化: {folder_path}")
        
        # 更新 mtime
        folders = self.config.get_all_folders()
        for f in folders:
            if f.path.lower() == folder_path.lower():
                self.config.update_folder_mtime(f.id, new_mtime)
                break
        
        # 发射信号
        self.changes_detected.emit(folder_path, [])
        
        # 触发扫描请求
        self.scan_requested.emit([folder_path])
    
    def _on_connection_error(self, folder_path: str, error_message: str):
        """连接错误回调"""
        self._error_paths.add(folder_path)
        self._update_status()
    
    def _on_connection_restored(self, folder_path: str):
        """连接恢复回调"""
        self._error_paths.discard(folder_path)
        self._update_status()
    
    def _update_status(self):
        """更新状态栏"""
        if not self.config.is_enabled():
            self.status_changed.emit("disabled", "目录监控: 未启用")
            return
        
        if not self._running:
            self.status_changed.emit("disabled", "目录监控: 已停止")
            return
        
        local_count = len(self._local_watcher.watched_paths)
        network_count = len(self._network_poller.polled_paths)
        total = local_count + network_count
        error_count = len(self._error_paths)
        
        if error_count > 0:
            working = total - error_count
            self.status_changed.emit("warning", f"监控中: {working}/{total} 目录 ({error_count}个重试中)")
        elif total > 0:
            self.status_changed.emit("normal", f"监控中: {total} 个目录")
        else:
            self.status_changed.emit("normal", "监控中: 无目录")
    
    def get_status_info(self) -> dict:
        """获取状态详情"""
        return {
            'running': self._running,
            'enabled': self.config.is_enabled(),
            'local_paths': self._local_watcher.watched_paths,
            'network_paths': self._network_poller.polled_paths,
            'error_paths': list(self._error_paths)
        }
