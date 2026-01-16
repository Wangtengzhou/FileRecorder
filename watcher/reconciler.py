"""
启动对账模块
检测监控目录在软件关闭期间的变化，包括具体文件级别的变化
"""
import os
import time
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

from .config import WatcherConfig, MonitoredFolder


@dataclass
class FileChange:
    """单个文件的变化"""
    path: str
    filename: str
    change_type: str  # 'added', 'deleted', 'modified'
    size: int = 0


@dataclass
class FolderChange:
    """目录变化信息"""
    folder: MonitoredFolder
    old_mtime: Optional[float]
    new_mtime: float
    accessible: bool = True
    error_message: str = ""
    is_new_folder: bool = False  # 是否是未索引的新目录
    file_changes: list[FileChange] = field(default_factory=list)
    
    # 统计
    added_count: int = 0
    deleted_count: int = 0
    modified_count: int = 0
    
    @property
    def total_changes(self) -> int:
        return self.added_count + self.deleted_count + self.modified_count
    
    @property
    def summary(self) -> str:
        """变化摘要"""
        if self.is_new_folder:
            return "新目录（未索引）"
        parts = []
        if self.added_count:
            parts.append(f"+{self.added_count}")
        if self.deleted_count:
            parts.append(f"-{self.deleted_count}")
        if self.modified_count:
            parts.append(f"~{self.modified_count}")
        return ", ".join(parts) if parts else "有变化"


class Reconciler:
    """启动对账器"""
    
    def __init__(self, config: WatcherConfig, db=None):
        self.config = config
        self.db = db  # 用于查询已索引的文件
    
    def check_all_folders(self) -> tuple[list[FolderChange], list[FolderChange]]:
        """
        检查所有监控目录的变化（静默，不修改索引）
        
        Returns:
            (changed_folders, error_folders): 有变化的目录列表, 无法访问的目录列表
        """
        print("[Watcher] 开始启动对账...")
        
        changed = []
        errors = []
        
        for folder in self.config.get_enabled_folders():
            result = self._check_folder(folder)
            
            if not result.accessible:
                errors.append(result)
                print(f"[Watcher]   {folder.path}: ⚠️ 无法访问 - {result.error_message}")
            elif result.is_new_folder:
                changed.append(result)
                print(f"[Watcher]   {folder.path}: 新目录（未索引）")
            elif result.old_mtime is None:
                # 首次检查，但目录已存在于索引中
                print(f"[Watcher]   {folder.path}: 首次检查")
                self.config.update_folder_mtime(folder.id, result.new_mtime)
            elif result.new_mtime != result.old_mtime:
                # mtime 变化，检测具体文件变化
                if self.db:
                    self._detect_file_changes(result)
                changed.append(result)
                print(f"[Watcher]   {folder.path}: {result.summary}")
            else:
                print(f"[Watcher]   {folder.path}: 无变化")
        
        print(f"[Watcher] 对账完成: {len(changed)} 个目录有变化, {len(errors)} 个无法访问")
        return changed, errors
    
    def _check_folder(self, folder: MonitoredFolder) -> FolderChange:
        """检查单个目录"""
        try:
            current_mtime = os.stat(folder.path).st_mtime
            
            # 检查是否是新目录（未在索引中）
            is_new = False
            if self.db:
                is_new = not self._folder_in_index(folder.path)
            
            return FolderChange(
                folder=folder,
                old_mtime=folder.last_mtime,
                new_mtime=current_mtime,
                accessible=True,
                is_new_folder=is_new
            )
        except PermissionError as e:
            return FolderChange(
                folder=folder,
                old_mtime=folder.last_mtime,
                new_mtime=0,
                accessible=False,
                error_message=f"权限不足: {e}"
            )
        except FileNotFoundError:
            return FolderChange(
                folder=folder,
                old_mtime=folder.last_mtime,
                new_mtime=0,
                accessible=False,
                error_message="目录不存在"
            )
        except OSError as e:
            return FolderChange(
                folder=folder,
                old_mtime=folder.last_mtime,
                new_mtime=0,
                accessible=False,
                error_message=f"网络错误或超时: {e}"
            )
    
    def _folder_in_index(self, path: str) -> bool:
        """检查目录是否已在索引中"""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            # 检查 folders 表或 files 表中是否有该路径下的记录
            normalized = path.replace('/', '\\').rstrip('\\')
            cursor.execute("""
                SELECT 1 FROM folders 
                WHERE path COLLATE NOCASE = ? OR path LIKE ? ESCAPE '\\'
                LIMIT 1
            """, (normalized, normalized.replace('\\', '\\\\') + '%'))
            return cursor.fetchone() is not None
    
    def _detect_file_changes(self, change: FolderChange):
        """检测具体文件变化"""
        folder_path = change.folder.path
        
        # 获取当前目录中的文件
        current_files = {}
        try:
            for item in Path(folder_path).rglob('*'):
                if item.is_file():
                    rel_path = str(item)
                    try:
                        stat = item.stat()
                        current_files[rel_path.lower()] = {
                            'path': rel_path,
                            'name': item.name,
                            'mtime': stat.st_mtime,
                            'size': stat.st_size
                        }
                    except:
                        pass
        except Exception as e:
            print(f"[Watcher]     扫描目录失败: {e}")
            return
        
        # 获取索引中的文件
        indexed_files = {}
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            normalized = folder_path.replace('/', '\\').rstrip('\\')
            cursor.execute("""
                SELECT f.filename, fo.path, f.modified_time, f.size
                FROM files f
                JOIN folders fo ON f.folder_id = fo.id
                WHERE fo.path LIKE ? ESCAPE '\\'
            """, (normalized.replace('\\', '\\\\') + '%',))
            
            for row in cursor.fetchall():
                full_path = os.path.join(row['path'], row['filename'])
                indexed_files[full_path.lower()] = {
                    'path': full_path,
                    'name': row['filename'],
                    'mtime': row['modified_time'],
                    'size': row['size']
                }
        
        # 对比差异
        current_set = set(current_files.keys())
        indexed_set = set(indexed_files.keys())
        
        # 新增的文件
        added = current_set - indexed_set
        for path in list(added)[:5]:  # 最多显示5个
            info = current_files[path]
            change.file_changes.append(FileChange(
                path=info['path'],
                filename=info['name'],
                change_type='added',
                size=info['size']
            ))
        change.added_count = len(added)
        
        # 删除的文件
        deleted = indexed_set - current_set
        for path in list(deleted)[:5]:
            info = indexed_files[path]
            change.file_changes.append(FileChange(
                path=info['path'],
                filename=info['name'],
                change_type='deleted',
                size=info['size']
            ))
        change.deleted_count = len(deleted)
        
        # 修改的文件（mtime 变化）
        modified_count = 0
        for path in current_set & indexed_set:
            if current_files[path]['mtime'] != indexed_files[path]['mtime']:
                modified_count += 1
                if len(change.file_changes) < 10:
                    change.file_changes.append(FileChange(
                        path=current_files[path]['path'],
                        filename=current_files[path]['name'],
                        change_type='modified',
                        size=current_files[path]['size']
                    ))
        change.modified_count = modified_count
    
    def update_folder_mtime(self, folder: MonitoredFolder, mtime: float):
        """更新目录的 mtime（确认更新后调用）"""
        self.config.update_folder_mtime(folder.id, mtime)
