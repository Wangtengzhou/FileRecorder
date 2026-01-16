"""
本地目录监控
使用 watchdog 实现实时文件变化检测
"""
import time
from pathlib import Path
from typing import Callable, Optional
from dataclasses import dataclass, field
from threading import Timer

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent

from PySide6.QtCore import QObject, Signal


@dataclass
class FileEvent:
    """文件事件"""
    event_type: str  # 'created', 'deleted', 'modified', 'moved'
    src_path: str
    dest_path: str = ""  # 仅 moved 事件
    is_directory: bool = False


class DebouncedEventHandler(FileSystemEventHandler):
    """
    带防抖的事件处理器
    短时间内的多次事件会合并处理
    """
    
    def __init__(self, callback: Callable, debounce_seconds: float = 1.0):
        super().__init__()
        self.callback = callback
        self.debounce_seconds = debounce_seconds
        self._pending_events: dict[str, FileEvent] = {}
        self._timer: Optional[Timer] = None
        
        # 忽略的文件模式
        self._ignore_patterns = {
            '.tmp', '.partial', '.crdownload', '.part',
            '~$', '.swp', '.lock', 'desktop.ini', 'Thumbs.db'
        }
    
    def _should_ignore(self, path: str) -> bool:
        """检查是否应忽略该文件"""
        filename = Path(path).name.lower()
        for pattern in self._ignore_patterns:
            if pattern in filename:
                return True
        return False
    
    def _schedule_callback(self):
        """调度回调（防抖）"""
        if self._timer:
            self._timer.cancel()
        
        self._timer = Timer(self.debounce_seconds, self._flush_events)
        self._timer.start()
    
    def _flush_events(self):
        """刷新并处理所有待处理事件"""
        if self._pending_events:
            events = list(self._pending_events.values())
            self._pending_events.clear()
            self.callback(events)
    
    def _add_event(self, event: FileEvent):
        """添加事件到队列"""
        # 以路径为 key，后来的事件覆盖之前的
        self._pending_events[event.src_path] = event
        self._schedule_callback()
    
    def on_created(self, event: FileSystemEvent):
        if self._should_ignore(event.src_path):
            return
        print(f"[Watcher] 检测到创建: {event.src_path}")
        self._add_event(FileEvent(
            event_type='created',
            src_path=event.src_path,
            is_directory=event.is_directory
        ))
    
    def on_deleted(self, event: FileSystemEvent):
        if self._should_ignore(event.src_path):
            return
        print(f"[Watcher] 检测到删除: {event.src_path}")
        self._add_event(FileEvent(
            event_type='deleted',
            src_path=event.src_path,
            is_directory=event.is_directory
        ))
    
    def on_modified(self, event: FileSystemEvent):
        if event.is_directory:
            return  # 忽略目录修改事件
        if self._should_ignore(event.src_path):
            return
        print(f"[Watcher] 检测到修改: {event.src_path}")
        self._add_event(FileEvent(
            event_type='modified',
            src_path=event.src_path,
            is_directory=False
        ))
    
    def on_moved(self, event: FileSystemEvent):
        if self._should_ignore(event.src_path):
            return
        print(f"[Watcher] 检测到移动: {event.src_path} -> {event.dest_path}")
        self._add_event(FileEvent(
            event_type='moved',
            src_path=event.src_path,
            dest_path=event.dest_path,
            is_directory=event.is_directory
        ))


class LocalWatcher(QObject):
    """
    本地目录监控器
    封装 watchdog Observer
    """
    
    # 检测到变化信号
    changes_detected = Signal(str, list)  # (folder_path, events)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._observers: dict[str, Observer] = {}
        self._handlers: dict[str, DebouncedEventHandler] = {}
    
    def add_watch(self, path: str, debounce_seconds: float = 1.0) -> bool:
        """添加目录监控"""
        if path in self._observers:
            print(f"[Watcher] 目录已在监控中: {path}")
            return True
        
        try:
            # 创建事件处理器
            handler = DebouncedEventHandler(
                callback=lambda events, p=path: self._on_events(p, events),
                debounce_seconds=debounce_seconds
            )
            
            # 创建观察者
            observer = Observer()
            observer.schedule(handler, path, recursive=True)
            observer.start()
            
            self._observers[path] = observer
            self._handlers[path] = handler
            
            print(f"[Watcher] 开始监控本地目录: {path}")
            return True
            
        except Exception as e:
            print(f"[Watcher] 监控目录失败: {path} - {e}")
            return False
    
    def remove_watch(self, path: str):
        """移除目录监控"""
        if path in self._observers:
            self._observers[path].stop()
            self._observers[path].join(timeout=2)
            del self._observers[path]
            del self._handlers[path]
            print(f"[Watcher] 停止监控本地目录: {path}")
    
    def stop_all(self):
        """停止所有监控"""
        for path in list(self._observers.keys()):
            self.remove_watch(path)
    
    def _on_events(self, folder_path: str, events: list[FileEvent]):
        """事件回调"""
        print(f"[Watcher] 目录 {folder_path} 有 {len(events)} 个变化")
        self.changes_detected.emit(folder_path, events)
    
    @property
    def watched_paths(self) -> list[str]:
        """获取正在监控的路径列表"""
        return list(self._observers.keys())
