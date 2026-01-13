"""
FileRecorder 文件扫描模块
支持本地及网络路径的递归扫描
"""
import os
import time
from pathlib import Path
from typing import Callable, Optional
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

from PySide6.QtCore import QObject, Signal, QThread


class FileScanner(QObject):
    """文件扫描器"""
    
    # 信号定义
    progress = Signal(int, int, str)      # current, total, current_file
    finished = Signal(dict)                # 扫描结果统计
    error = Signal(str)                    # 错误信息
    file_found = Signal(dict)              # 单个文件信息（用于实时更新）
    
    def __init__(self, db=None, batch_size: int = 1000, ignore_patterns: list[str] = None, timeout: int = 5):
        """
        初始化扫描器
        
        Args:
            db: 数据库管理器（用于分批写入）
            batch_size: 每批写入的记录数量
            ignore_patterns: 要忽略的文件/目录模式
            timeout: 网络路径超时时间（秒）
        """
        super().__init__()
        self.db = db
        self.batch_size = batch_size
        self._batch = []  # 当前批次缓存
        self._batch_count = 0  # 已写入批次数
        self.ignore_patterns = ignore_patterns or [
            ".*",
            "$RECYCLE.BIN",
            "System Volume Information",
            "Thumbs.db"
        ]
        self.timeout = timeout
        self._cancelled = False
    
    def _flush_batch(self, force: bool = False) -> int:
        """
        写入当前批次到数据库
        
        Args:
            force: 强制写入（即使未达到batch_size）
        
        Returns:
            写入的记录数
        """
        if not self._batch:
            return 0
        
        if not force and len(self._batch) < self.batch_size:
            return 0
        
        if self.db:
            try:
                self.db.batch_insert(self._batch)
                count = len(self._batch)
                self._batch_count += 1
                self._batch = []  # 清空内存
                return count
            except Exception as e:
                self.error.emit(f"批量写入失败: {e}")
                return 0
        else:
            # 没有db时保留在内存（兼容旧逻辑）
            return 0
    
    def cancel(self) -> None:
        """取消扫描"""
        self._cancelled = True
    
    def is_cancelled(self) -> bool:
        """检查是否已取消"""
        return self._cancelled
    
    def _should_ignore(self, name: str) -> bool:
        """检查是否应该忽略该文件/目录"""
        for pattern in self.ignore_patterns:
            if pattern.startswith('.') and name.startswith('.'):
                return True
            if name == pattern:
                return True
        return False
    
    def _is_network_path(self, path: str) -> bool:
        """检查是否为网络路径"""
        return path.startswith('\\\\') or '://' in path
    
    def _get_long_path(self, path: str) -> str:
        """获取 Windows 长路径格式（解决 260 字符限制）"""
        path = str(path)
        if path.startswith('\\\\?\\') or path.startswith('\\\\?\\UNC\\'):
            return path
        if path.startswith('\\\\'):
            # UNC 路径: \\server\share -> \\?\UNC\server\share
            return '\\\\?\\UNC\\' + path[2:]
        else:
            # 本地路径: C:\path -> \\?\C:\path
            return '\\\\?\\' + path
    
    def _restore_original_path(self, path: str) -> str:
        """将长路径格式还原为原始格式（用于存储到数据库）"""
        path = str(path)
        if path.startswith('\\\\?\\UNC\\'):
            # \\?\UNC\server\share -> \\server\share
            return '\\\\' + path[8:]
        elif path.startswith('\\\\?\\'):
            # \\?\C:\path -> C:\path
            return path[4:]
        return path
    
    def _get_file_info(self, file_path: Path, scan_source: str) -> Optional[dict]:
        """
        获取文件信息
        
        Args:
            file_path: 文件路径
            scan_source: 扫描源路径
        
        Returns:
            文件信息字典，失败返回None
        """
        try:
            # 使用长路径格式避免 Windows 260 字符限制
            long_path = self._get_long_path(str(file_path))
            stat = os.stat(long_path)
            
            # 存储时使用原始路径格式（不含 \\?\ 前缀）
            original_path = self._restore_original_path(str(file_path))
            original_parent = self._restore_original_path(str(file_path.parent))
            
            return {
                'filename': file_path.name,
                'extension': file_path.suffix.lower().lstrip('.') if file_path.suffix else '',
                'full_path': original_path,
                'parent_folder': original_parent,
                'size_bytes': stat.st_size,
                'ctime': stat.st_ctime,
                'mtime': stat.st_mtime,
                'scan_source': scan_source,
                'scan_time': time.time()
            }
        except (OSError, PermissionError) as e:
            self.error.emit(f"无法读取文件信息: {file_path} - {e}")
            return None
    
    def _get_file_info_with_timeout(self, file_path: Path, scan_source: str) -> Optional[dict]:
        """带超时的获取文件信息（用于网络路径）"""
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self._get_file_info, file_path, scan_source)
            try:
                return future.result(timeout=self.timeout)
            except FuturesTimeoutError:
                self.error.emit(f"读取超时: {file_path}")
                return None
            except Exception as e:
                self.error.emit(f"读取错误: {file_path} - {e}")
                return None
    
    def _get_dir_info(self, dir_path: Path, scan_source: str) -> Optional[dict]:
        """
        获取目录信息
        
        Args:
            dir_path: 目录路径
            scan_source: 扫描源路径
        
        Returns:
            目录信息字典，失败返回None
        """
        try:
            # 使用长路径格式避免 Windows 260 字符限制
            long_path = self._get_long_path(str(dir_path))
            stat = os.stat(long_path)
            
            # 存储时使用原始路径格式（不含 \\?\ 前缀）
            original_path = self._restore_original_path(str(dir_path))
            original_parent = self._restore_original_path(str(dir_path.parent))
            
            return {
                'filename': dir_path.name,
                'extension': '',
                'full_path': original_path,
                'parent_folder': original_parent,
                'size_bytes': 0,
                'ctime': stat.st_ctime,
                'mtime': stat.st_mtime,
                'scan_source': scan_source,
                'scan_time': time.time(),
                'is_dir': True
            }
        except (OSError, PermissionError) as e:
            self.error.emit(f"无法读取目录信息: {dir_path} - {e}")
            return None
    
    def scan_path(self, path: str, progress_callback: Callable = None) -> dict:
        """
        扫描指定路径
        
        Args:
            path: 要扫描的路径
            progress_callback: 进度回调函数
        
        Returns:
            扫描结果统计
        """
        self._cancelled = False
        self._batch = []  # 重置批次缓存
        self._batch_count = 0
        scan_source = path
        is_network = self._is_network_path(path)
        
        # 风险防护：扫描前先清除该路径的旧记录（避免重复数据）
        if self.db:
            try:
                self.db.clear_source(scan_source)
            except Exception as e:
                self.error.emit(f"清理旧记录失败: {e}")
        
        files_found = []  # 仅用于兼容旧逻辑（无db时）
        errors = []
        scanned_count = 0
        total_size = 0
        total_inserted = 0
        
        try:
            root_path = Path(path)
            if not root_path.exists():
                raise FileNotFoundError(f"路径不存在: {path}")
            
            # 首先记录扫描源目录本身
            root_dir_info = self._get_dir_info(root_path, scan_source)
            if root_dir_info:
                self._add_to_batch(root_dir_info, files_found)
                scanned_count += 1
                self.progress.emit(scanned_count, 0, str(root_path))
            
            # 使用 os.walk 递归遍历（使用长路径格式避免 260 字符限制）
            ignored_dirs = 0  # 统计忽略的目录数
            ignored_files = 0  # 统计忽略的文件数
            successful_files = 0  # 成功读取的文件数
            failed_files = 0  # 读取失败的文件数
            
            # 对于长路径，使用长路径格式
            walk_path = self._get_long_path(path)
            for dirpath, dirnames, filenames in os.walk(walk_path):
                if self._cancelled:
                    break
                
                # 过滤忽略的目录
                original_count = len(dirnames)
                dirnames[:] = [d for d in dirnames if not self._should_ignore(d)]
                ignored_dirs += original_count - len(dirnames)
                
                # 记录当前目录下的子目录
                for dirname in dirnames:
                    if self._cancelled:
                        break
                    
                    dir_full_path = Path(dirpath) / dirname
                    scanned_count += 1
                    
                    # 发送进度信号
                    self.progress.emit(scanned_count, 0, str(dir_full_path))
                    
                    # 获取目录信息
                    dir_info = self._get_dir_info(dir_full_path, scan_source)
                    if dir_info:
                        self._add_to_batch(dir_info, files_found)
                        self.file_found.emit(dir_info)
                    
                    # 检查是否需要写入批次
                    total_inserted += self._flush_batch()
                
                # 记录文件
                for filename in filenames:
                    if self._cancelled:
                        break
                    
                    if self._should_ignore(filename):
                        continue
                    
                    file_path = Path(dirpath) / filename
                    scanned_count += 1
                    
                    # 发送进度信号
                    self.progress.emit(scanned_count, 0, str(file_path))
                    if progress_callback:
                        progress_callback(scanned_count, 0, str(file_path))
                    
                    # 获取文件信息
                    if is_network:
                        file_info = self._get_file_info_with_timeout(file_path, scan_source)
                    else:
                        file_info = self._get_file_info(file_path, scan_source)
                    
                    if file_info:
                        self._add_to_batch(file_info, files_found)
                        total_size += file_info.get('size_bytes', 0)
                        self.file_found.emit(file_info)
                        successful_files += 1
                    else:
                        errors.append({'path': str(file_path), 'error': '无法读取文件信息'})
                        failed_files += 1
                    
                    # 检查是否需要写入批次
                    total_inserted += self._flush_batch()
        
        except Exception as e:
            self.error.emit(f"扫描错误: {e}")
            errors.append({'path': path, 'error': str(e)})
        
        # 写入剩余批次
        total_inserted += self._flush_batch(force=True)
        
        # 输出扫描统计日志
        print(f"扫描统计: 成功 {successful_files}, 失败 {failed_files}, 忽略目录 {ignored_dirs}")
        
        # 风险防护：如果用户取消，可选择清理已写入数据
        # 注意：这里保留已扫描数据，用户可在界面中删除
        
        # 计算最终数量
        final_count = total_inserted if self.db else len(files_found)
        
        result = {
            'scan_source': scan_source,
            'files': files_found if not self.db else [],  # 有db时不返回files节省内存
            'file_count': final_count,
            'total_size': total_size,
            'error_count': len(errors),
            'errors': errors[:100],  # 最多保留100条错误
            'cancelled': self._cancelled,
            'batch_count': self._batch_count
        }
        
        self.finished.emit(result)
        return result
    
    def _add_to_batch(self, file_info: dict, files_found: list):
        """添加到批次缓存"""
        if self.db:
            self._batch.append(file_info)
        else:
            files_found.append(file_info)


class ScannerThread(QThread):
    """扫描线程包装器"""
    
    progress = Signal(int, int, str)
    finished = Signal(dict)
    error = Signal(str)
    
    def __init__(self, scanner: FileScanner, path: str, parent=None):
        super().__init__(parent)
        self.scanner = scanner
        self.path = path
        
        # 转发信号
        self.scanner.progress.connect(self.progress)
        self.scanner.finished.connect(self.finished)
        self.scanner.error.connect(self.error)
    
    def run(self):
        """执行扫描"""
        self.scanner.scan_path(self.path)
    
    def cancel(self):
        """取消扫描"""
        self.scanner.cancel()
