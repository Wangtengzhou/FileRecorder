"""
网络目录轮询器
使用 mtime 比较检测网络目录变化
"""
import os
import time
from typing import Optional

from PySide6.QtCore import QObject, Signal, QTimer

from .config import MonitoredFolder


class NetworkPoller(QObject):
    """
    网络目录轮询器
    定时检查目录 mtime 变化
    """
    
    # 检测到变化信号
    changes_detected = Signal(str, float)  # (folder_path, new_mtime)
    
    # 连接错误信号
    connection_error = Signal(str, str)  # (folder_path, error_message)
    
    # 连接恢复信号
    connection_restored = Signal(str)  # folder_path
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._timers: dict[str, QTimer] = {}
        self._last_mtime: dict[str, float] = {}
        self._retry_info: dict[str, dict] = {}  # 重试信息
    
    def add_poll(self, folder: MonitoredFolder) -> bool:
        """添加轮询目录"""
        path = folder.path
        
        if path in self._timers:
            print(f"[Watcher] 目录已在轮询中: {path}")
            return True
        
        # 记录初始 mtime
        if folder.last_mtime:
            self._last_mtime[path] = folder.last_mtime
        
        # 创建定时器
        interval_ms = folder.poll_interval_minutes * 60 * 1000
        timer = QTimer(self)
        timer.timeout.connect(lambda p=path: self._poll(p))
        timer.start(interval_ms)
        
        self._timers[path] = timer
        print(f"[Watcher] 开始轮询网络目录: {path} (间隔 {folder.poll_interval_minutes} 分钟)")
        
        # 立即执行一次检查
        QTimer.singleShot(1000, lambda p=path: self._poll(p))
        
        return True
    
    def remove_poll(self, path: str):
        """移除轮询目录"""
        if path in self._timers:
            self._timers[path].stop()
            del self._timers[path]
            if path in self._last_mtime:
                del self._last_mtime[path]
            if path in self._retry_info:
                del self._retry_info[path]
            print(f"[Watcher] 停止轮询网络目录: {path}")
    
    def update_interval(self, path: str, interval_minutes: int):
        """更新轮询间隔"""
        if path in self._timers:
            interval_ms = interval_minutes * 60 * 1000
            self._timers[path].setInterval(interval_ms)
            print(f"[Watcher] 更新轮询间隔: {path} -> {interval_minutes} 分钟")
    
    def stop_all(self):
        """停止所有轮询"""
        for path in list(self._timers.keys()):
            self.remove_poll(path)
    
    def _poll(self, path: str):
        """执行轮询检查"""
        try:
            current_mtime = os.stat(path).st_mtime
            
            # 连接成功，清除重试状态
            was_retrying = path in self._retry_info
            if was_retrying:
                del self._retry_info[path]
                # 恢复正常轮询间隔
                self._restore_normal_interval(path)
                self.connection_restored.emit(path)
                print(f"[Watcher] 连接恢复: {path}")
            
            # 检查变化
            last_mtime = self._last_mtime.get(path)
            if last_mtime and current_mtime != last_mtime:
                print(f"[Watcher] 轮询检测到变化: {path}")
                self.changes_detected.emit(path, current_mtime)
            else:
                print(f"[Watcher] 轮询检查: {path} 无变化")
            
            self._last_mtime[path] = current_mtime
            
        except Exception as e:
            self._handle_error(path, str(e))
    
    def _handle_error(self, path: str, error_message: str):
        """处理连接错误（退避重试）"""
        print(f"[Watcher] ⚠️ 轮询失败: {path} - {error_message}")
        
        if path not in self._retry_info:
            self._retry_info[path] = {
                'fail_count': 0,
                'first_fail_time': time.time()
            }
        
        info = self._retry_info[path]
        info['fail_count'] += 1
        
        # 计算下次重试间隔（退避策略）
        elapsed = time.time() - info['first_fail_time']
        if elapsed < 120:  # 前2分钟
            next_interval = 5
        elif elapsed < 600:  # 2-10分钟
            next_interval = 30
        else:  # 10分钟后
            next_interval = 300
        
        print(f"[Watcher]   下次重试: {next_interval}秒后")
        
        # 调整定时器间隔
        if path in self._timers:
            self._timers[path].setInterval(next_interval * 1000)
        
        self.connection_error.emit(path, error_message)
    
    def _restore_normal_interval(self, path: str):
        """恢复正常轮询间隔"""
        # TODO: 从配置获取原始间隔
        # 暂时使用默认 15 分钟
        if path in self._timers:
            self._timers[path].setInterval(15 * 60 * 1000)
    
    @property
    def polled_paths(self) -> list[str]:
        """获取正在轮询的路径列表"""
        return list(self._timers.keys())
    
    @property
    def error_paths(self) -> list[str]:
        """获取有错误的路径列表"""
        return list(self._retry_info.keys())
