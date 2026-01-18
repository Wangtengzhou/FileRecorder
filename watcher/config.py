"""
监控配置管理
处理监控功能的开关、目录列表、轮询间隔等配置
"""
import os
import time
from typing import Optional
from dataclasses import dataclass, field

from logger import get_logger

logger = get_logger("watcher")

@dataclass
class MonitoredFolder:
    """监控目录信息"""
    id: int = 0
    path: str = ""
    last_mtime: Optional[float] = None
    last_check_time: Optional[float] = None
    is_local: bool = True
    poll_interval_minutes: int = 15
    enabled: bool = True


class WatcherConfig:
    """监控配置管理器"""
    
    def __init__(self, db):
        self.db = db
        self._cache_enabled: Optional[bool] = None
    
    # ========== 总开关 ==========
    
    def is_enabled(self) -> bool:
        """检查监控功能是否启用"""
        if self._cache_enabled is not None:
            return self._cache_enabled
        
        value = self._get_config("feature_enabled")
        self._cache_enabled = value == "true"
        return self._cache_enabled
    
    def set_enabled(self, enabled: bool):
        """设置监控功能开关"""
        self._set_config("feature_enabled", "true" if enabled else "false")
        self._cache_enabled = enabled
        logger.info(f"功能开关: {'启用' if enabled else '禁用'}")
    
    def is_silent_update(self) -> bool:
        """检查是否开启静默更新"""
        value = self._get_config("silent_update")
        return value == "true"
    
    def set_silent_update(self, enabled: bool):
        """设置静默更新开关"""
        self._set_config("silent_update", "true" if enabled else "false")
        logger.info(f"静默更新: {'启用' if enabled else '禁用'}")
    
    def get_default_poll_interval(self) -> int:
        """获取默认轮询间隔（分钟）"""
        value = self._get_config("default_poll_interval")
        try:
            return int(value) if value else 15
        except:
            return 15
    
    def set_default_poll_interval(self, minutes: int):
        """设置默认轮询间隔（分钟）"""
        self._set_config("default_poll_interval", str(minutes))
    
    # ========== 监控目录 ==========
    
    def get_all_folders(self) -> list[MonitoredFolder]:
        """获取所有监控目录"""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, path, last_mtime, last_check_time, 
                       is_local, poll_interval_minutes, enabled
                FROM monitored_folders
                ORDER BY path
            """)
            return [
                MonitoredFolder(
                    id=row['id'],
                    path=row['path'],
                    last_mtime=row['last_mtime'],
                    last_check_time=row['last_check_time'],
                    is_local=bool(row['is_local']),
                    poll_interval_minutes=row['poll_interval_minutes'],
                    enabled=bool(row['enabled'])
                )
                for row in cursor.fetchall()
            ]
    
    def get_enabled_folders(self) -> list[MonitoredFolder]:
        """获取所有启用的监控目录"""
        return [f for f in self.get_all_folders() if f.enabled]
    
    def add_folder(self, path: str, poll_interval: int = 15) -> Optional[MonitoredFolder]:
        """添加监控目录"""
        path = path.replace('/', '\\').rstrip('\\')
        is_local = self._is_local_path(path)
        
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO monitored_folders 
                    (path, is_local, poll_interval_minutes, enabled)
                    VALUES (?, ?, ?, 1)
                """, (path, 1 if is_local else 0, poll_interval))
                
                folder_id = cursor.lastrowid
                logger.info(f"添加监控目录: {path} ({'本地' if is_local else '网络'})")
                
                return MonitoredFolder(
                    id=folder_id,
                    path=path,
                    is_local=is_local,
                    poll_interval_minutes=poll_interval,
                    enabled=True
                )
            except Exception as e:
                logger.warning(f"添加目录失败: {e}")
                return None
    
    def remove_folder(self, folder_id: int) -> bool:
        """移除监控目录"""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM monitored_folders WHERE id = ?", (folder_id,))
            success = cursor.rowcount > 0
            if success:
                logger.info(f"移除监控目录 ID: {folder_id}")
            return success
    
    def update_folder(self, folder_id: int, **kwargs) -> bool:
        """更新监控目录配置"""
        allowed_fields = {'enabled', 'poll_interval_minutes', 'last_mtime', 'last_check_time'}
        updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
        
        if not updates:
            return False
        
        set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
        values = list(updates.values()) + [folder_id]
        
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"UPDATE monitored_folders SET {set_clause} WHERE id = ?", values)
            return cursor.rowcount > 0
    
    def update_folder_mtime(self, folder_id: int, mtime: float):
        """更新目录的 mtime 和检查时间"""
        self.update_folder(folder_id, last_mtime=mtime, last_check_time=time.time())
    
    def folder_exists(self, path: str) -> bool:
        """检查目录是否已在监控列表"""
        path = path.replace('/', '\\').rstrip('\\')
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM monitored_folders WHERE path COLLATE NOCASE = ?",
                (path,)
            )
            return cursor.fetchone() is not None
    
    def is_path_monitored(self, path: str) -> Optional[MonitoredFolder]:
        """
        检查路径是否被监控（包括子路径匹配）
        返回匹配的监控目录，如果没有则返回 None
        """
        path = path.replace('/', '\\').rstrip('\\').lower()
        
        for folder in self.get_all_folders():
            folder_path = folder.path.lower()
            # 精确匹配或者是子路径
            if path == folder_path or path.startswith(folder_path + '\\'):
                return folder
        
        return None
    
    def remove_folder_by_path(self, path: str) -> bool:
        """通过路径移除监控目录"""
        path = path.replace('/', '\\').rstrip('\\')
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM monitored_folders WHERE path COLLATE NOCASE = ?",
                (path,)
            )
            success = cursor.rowcount > 0
            if success:
                logger.info(f"移除监控目录: {path}")
            return success
    
    def find_parent_child_conflicts(self, new_path: str) -> dict:
        """
        检测新路径与现有监控目录的父子关系冲突
        返回：{'parent': 父目录列表, 'children': 子目录列表}
        """
        new_path = new_path.replace('/', '\\').rstrip('\\').lower()
        conflicts = {'parent': [], 'children': []}
        
        for folder in self.get_all_folders():
            folder_path = folder.path.lower()
            
            # 新路径是某个已有目录的子目录
            if new_path.startswith(folder_path + '\\'):
                conflicts['parent'].append(folder)
            
            # 新路径是某个已有目录的父目录
            elif folder_path.startswith(new_path + '\\'):
                conflicts['children'].append(folder)
        
        return conflicts
    
    def merge_to_parent(self, parent_path: str, children: list[MonitoredFolder]):
        """合并子目录到父目录（移除子目录监控）"""
        for child in children:
            self.remove_folder(child.id)
            logger.info(f"合并: 移除子目录 {child.path} (父目录 {parent_path} 已覆盖)")
    
    # ========== 内部方法 ==========
    
    def _get_config(self, key: str) -> Optional[str]:
        """获取配置值"""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM watcher_config WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row['value'] if row else None
    
    def _set_config(self, key: str, value: str):
        """设置配置值"""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO watcher_config (key, value) VALUES (?, ?)
            """, (key, value))
    
    @staticmethod
    def _is_local_path(path: str) -> bool:
        """判断是否为本地路径"""
        # 网络路径以 \\ 或 // 开头
        if path.startswith('\\\\') or path.startswith('//'):
            return False
        # 本地路径通常是 C:\ 或类似格式
        if len(path) >= 2 and path[1] == ':':
            return True
        return False
