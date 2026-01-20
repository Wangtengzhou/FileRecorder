"""
FileRecorder - 智能文件索引助手
https://github.com/Wangtengzhou/FileRecorder

数据库管理模块 - 使用 SQLite 存储文件索引信息
"""
import sqlite3
from pathlib import Path
from typing import Optional
from contextlib import contextmanager
from functools import lru_cache

from logger import get_logger

logger = get_logger("database")

class DatabaseManager:
    """SQLite 数据库管理器"""
    
    def __init__(self, db_path: str | Path):
        """
        初始化数据库管理器
        
        Args:
            db_path: 数据库文件路径
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_tables()
    
    @contextmanager
    def _get_connection(self):
        """获取数据库连接的上下文管理器"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row  # 支持按列名访问
        
        # 性能优化设置
        conn.execute("PRAGMA journal_mode=WAL")  # WAL模式提升并发性能
        conn.execute("PRAGMA synchronous=NORMAL")  # 平衡安全与性能
        conn.execute("PRAGMA cache_size=-64000")  # 64MB缓存
        conn.execute("PRAGMA temp_store=MEMORY")  # 临时表存内存
        
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def _init_tables(self) -> None:
        """初始化数据库表结构"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 启用自动回收空间（增量模式）
            # 注意：auto_vacuum需要在创建表之前设置才能生效
            cursor.execute("PRAGMA auto_vacuum = INCREMENTAL")
            
            # 文件夹表（路径去重，节省30-50%空间）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS folders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT UNIQUE NOT NULL,
                    parent_id INTEGER,
                    scan_source_id INTEGER,
                    ai_category TEXT,
                    ai_tags TEXT,
                    FOREIGN KEY (parent_id) REFERENCES folders(id)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_folder_path ON folders(path)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_folder_parent ON folders(parent_id)")
            
            # 为旧数据库添加新列（如果不存在）
            try:
                cursor.execute("ALTER TABLE folders ADD COLUMN ai_category TEXT")
            except sqlite3.OperationalError:
                pass  # 列已存在
            try:
                cursor.execute("ALTER TABLE folders ADD COLUMN ai_tags TEXT")
            except sqlite3.OperationalError:
                pass  # 列已存在
            try:
                cursor.execute("ALTER TABLE folders ADD COLUMN parent_id INTEGER")
            except sqlite3.OperationalError:
                pass  # 列已存在
            # 确保 parent_id 索引存在
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_folder_parent ON folders(parent_id)")

            
            # 文件索引表（优化版：用folder_id替代重复的路径文本）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL,
                    extension TEXT,
                    folder_id INTEGER,
                    size_bytes INTEGER,
                    ctime REAL,
                    mtime REAL,
                    scan_time REAL,
                    ai_category TEXT,
                    ai_tags TEXT,
                    is_dir INTEGER DEFAULT 0,
                    FOREIGN KEY (folder_id) REFERENCES folders(id)
                )
            """)
            
            # 创建索引以加速查询
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_filename ON files(filename)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_extension ON files(extension)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_folder_id ON files(folder_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_category ON files(ai_category)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_is_dir ON files(is_dir)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_folder_isdir ON files(folder_id, is_dir)")
            
            # 扫描源记录表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scan_sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT UNIQUE,
                    last_scan_time REAL,
                    file_count INTEGER,
                    total_size INTEGER
                )
            """)
            
            # 扫描错误记录表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scan_errors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT,
                    error_message TEXT,
                    error_time REAL,
                    scan_source TEXT,
                    resolved INTEGER DEFAULT 0
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_error_path ON scan_errors(file_path)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_error_source ON scan_errors(scan_source)")
            
            # 监控目录表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS monitored_folders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT UNIQUE NOT NULL,
                    last_mtime REAL,
                    last_check_time REAL,
                    is_local INTEGER DEFAULT 1,
                    poll_interval_minutes INTEGER DEFAULT 15,
                    enabled INTEGER DEFAULT 1
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_monitored_path ON monitored_folders(path)")
            
            # 监控配置表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS watcher_config (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
    
    def _frc_standardize_path(self, path: str) -> str:
        """标准化文件路径格式（统一斜杠方向，去除尾部斜杠）"""
        if not path:
            return ""
        return path.replace('/', '\\').rstrip('\\')
    
    def _get_or_create_folder_id(self, cursor, folder_path: str, scan_source_id: int = None) -> int:
        """获取或创建文件夹ID（路径去重核心方法，自动填充 parent_id）"""
        if not folder_path:
            return None
        
        folder_path = self._frc_standardize_path(folder_path)
        
        # 先尝试获取已有的
        cursor.execute("SELECT id FROM folders WHERE path = ?", (folder_path,))
        row = cursor.fetchone()
        if row:
            return row[0]
        
        # 计算父目录路径
        parent_path = '\\'.join(folder_path.split('\\')[:-1]) if '\\' in folder_path else None
        parent_id = None
        
        if parent_path:
            # 递归获取或创建父目录（确保层级完整）
            parent_id = self._get_or_create_folder_id(cursor, parent_path, scan_source_id)
        
        # 创建当前目录
        cursor.execute(
            "INSERT INTO folders (path, parent_id, scan_source_id) VALUES (?, ?, ?)",
            (folder_path, parent_id, scan_source_id)
        )
        return cursor.lastrowid

    
    def _get_folder_path(self, cursor, folder_id: int) -> str:
        """根据文件夹ID获取路径"""
        if not folder_id:
            return ""
        cursor.execute("SELECT path FROM folders WHERE id = ?", (folder_id,))
        row = cursor.fetchone()
        return row[0] if row else ""
    
    def insert_file(self, file_info: dict) -> int:
        """
        插入单个文件记录
        
        Args:
            file_info: 文件信息字典
        
        Returns:
            插入的记录ID
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 获取或创建文件夹ID
            parent_folder = file_info.get('parent_folder', '')
            folder_id = self._get_or_create_folder_id(cursor, parent_folder)
            
            cursor.execute("""
                INSERT OR REPLACE INTO files 
                (filename, extension, folder_id, size_bytes, ctime, mtime, scan_time, is_dir)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                file_info.get('filename'),
                file_info.get('extension'),
                folder_id,
                file_info.get('size_bytes'),
                file_info.get('ctime'),
                file_info.get('mtime'),
                file_info.get('scan_time'),
                file_info.get('is_dir', 0),
            ))
            return cursor.lastrowid
    
    def add_or_update_file(self, filepath: str, filename: str, size: int, 
                           extension: str, media_type: str = None, 
                           title: str = None, year: int = None) -> int:
        """
        添加或更新文件记录（用于 AI 整理功能）
        
        Args:
            filepath: 完整文件路径
            filename: 文件名
            size: 文件大小
            extension: 扩展名
            media_type: 媒体类型
            title: 标题
            year: 年份
            
        Returns:
            记录ID
        """
        from pathlib import Path
        from datetime import datetime
        
        parent_folder = str(Path(filepath).parent)
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 获取或创建文件夹ID
            folder_id = self._get_or_create_folder_id(cursor, parent_folder)
            
            # 检查是否已存在
            cursor.execute("""
                SELECT id FROM files WHERE folder_id = ? AND filename = ?
            """, (folder_id, filename))
            row = cursor.fetchone()
            
            now = datetime.now().isoformat()
            
            if row:
                # 更新
                cursor.execute("""
                    UPDATE files SET 
                        size_bytes = ?, 
                        ai_category = ?,
                        ai_tags = ?,
                        scan_time = ?
                    WHERE id = ?
                """, (size, media_type, title, now, row[0]))
                return row[0]
            else:
                # 插入
                cursor.execute("""
                    INSERT INTO files 
                    (filename, extension, folder_id, size_bytes, scan_time, is_dir, ai_category, ai_tags)
                    VALUES (?, ?, ?, ?, ?, 0, ?, ?)
                """, (filename, extension, folder_id, size, now, media_type, title))
                return cursor.lastrowid
    
    def batch_insert(self, files: list[dict]) -> int:
        """
        批量插入文件记录
        
        Args:
            files: 文件信息列表
        
        Returns:
            插入的记录数量
        """
        if not files:
            return 0
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 先批量创建/获取所有需要的文件夹ID
            folder_ids = {}  # path -> id 缓存
            for f in files:
                parent_folder = f.get('parent_folder', '')
                if parent_folder and parent_folder not in folder_ids:
                    folder_ids[parent_folder] = self._get_or_create_folder_id(cursor, parent_folder)
            
            # 批量插入文件
            records = []
            for f in files:
                filename = f.get('filename')
                if not filename:  # 跳过空文件名
                    continue
                parent_folder = f.get('parent_folder', '')
                folder_id = folder_ids.get(parent_folder)
                records.append((
                    filename,
                    f.get('extension'),
                    folder_id,
                    f.get('size_bytes'),
                    f.get('ctime'),
                    f.get('mtime'),
                    f.get('scan_time'),
                    1 if f.get('is_dir') else 0
                ))
            
            cursor.executemany("""
                INSERT OR REPLACE INTO files 
                (filename, extension, folder_id, size_bytes, ctime, mtime, scan_time, is_dir)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, records)
            return len(files)
    
    def search_files(self, keyword: str, extension: str = None, limit: int = 1000) -> list[dict]:
        """
        搜索文件
        
        Args:
            keyword: 搜索关键词（支持空格分隔多个关键词，AND关系）
            extension: 可选的扩展名过滤
            limit: 最大返回数量
        
        Returns:
            匹配的文件列表
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 分割关键词（支持多个空格分隔的关键词）
            keywords = [k.strip() for k in keyword.split() if k.strip()]
            
            if not keywords:
                return []
            
            # 构建多关键词 AND 查询（使用JOIN）
            conditions = []
            params = []
            
            for kw in keywords:
                conditions.append("f.filename LIKE ?")
                params.append(f"%{kw}%")
            
            query = """
                SELECT f.*, fo.path as parent_folder, 
                       fo.path || '\\' || f.filename as full_path
                FROM files f
                LEFT JOIN folders fo ON f.folder_id = fo.id
                WHERE """ + " AND ".join(conditions)
            
            if extension:
                query += " AND f.extension = ?"
                params.append(extension.lower().lstrip('.'))
            
            query += f" ORDER BY f.filename LIMIT {limit}"
            
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    
    def get_files_by_extension(self, extension: str, limit: int = 10000) -> list[dict]:
        """获取指定扩展名的所有文件"""
        ext = extension.lower().lstrip('.')
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT f.*, fo.path as parent_folder,
                       fo.path || '\\' || f.filename as full_path
                FROM files f
                LEFT JOIN folders fo ON f.folder_id = fo.id
                WHERE f.extension = ? LIMIT ?
            """, (ext, limit))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_files_by_folder(self, folder_path: str) -> list[dict]:
        """获取指定目录下的所有文件"""
        folder_path = folder_path.replace('/', '\\').rstrip('\\')
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT f.*, fo.path as parent_folder,
                       fo.path || '\\' || f.filename as full_path
                FROM files f
                LEFT JOIN folders fo ON f.folder_id = fo.id
                WHERE fo.path = ? OR fo.path LIKE ?
            """, (folder_path, f"{folder_path}\\%"))
            return [dict(row) for row in cursor.fetchall()]
    
    def update_ai_tags(self, file_id: int, category: str = None, tags: str = None) -> None:
        """更新文件的AI分类和标签"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE files SET ai_category = ?, ai_tags = ? WHERE id = ?",
                (category, tags, file_id)
            )
    
    def delete_file(self, file_id: int) -> bool:
        """删除单个文件记录
        
        Args:
            file_id: 文件ID
            
        Returns:
            是否删除成功
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM files WHERE id = ?", (file_id,))
            return cursor.rowcount > 0
    
    def delete_files(self, file_ids: list[int]) -> int:
        """批量删除文件记录
        
        Args:
            file_ids: 文件ID列表
            
        Returns:
            删除的记录数
        """
        if not file_ids:
            return 0
        with self._get_connection() as conn:
            cursor = conn.cursor()
            placeholders = ','.join('?' * len(file_ids))
            cursor.execute(f"DELETE FROM files WHERE id IN ({placeholders})", file_ids)
            return cursor.rowcount
    
    def delete_dir_record(self, dir_path: str) -> bool:
        """删除目录在 files 表中的记录（is_dir=1）
        
        Args:
            dir_path: 目录完整路径
            
        Returns:
            是否删除成功
        """
        dir_path = dir_path.replace('/', '\\').rstrip('\\')
        dir_name = dir_path.split('\\')[-1] if '\\' in dir_path else dir_path
        parent_path = '\\'.join(dir_path.split('\\')[:-1]) if '\\' in dir_path else ''
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # 获取父目录 folder_id
            cursor.execute("SELECT id FROM folders WHERE path = ? COLLATE NOCASE", (parent_path,))
            row = cursor.fetchone()
            if row:
                cursor.execute(
                    "DELETE FROM files WHERE folder_id = ? AND filename = ? AND is_dir = 1",
                    (row['id'], dir_name)
                )
                return cursor.rowcount > 0
            return False
    
    def batch_update_ai_tags(self, updates: list[dict]) -> None:
        """
        批量更新AI标签
        
        Args:
            updates: 更新列表，每项包含 id, ai_category, ai_tags
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(
                "UPDATE files SET ai_category = ?, ai_tags = ? WHERE id = ?",
                [(u.get('ai_category'), u.get('ai_tags'), u.get('id')) for u in updates]
            )
    
    def update_folder_ai_tags(self, folder_path: str, ai_category: str, ai_tags: str = "") -> bool:
        """
        通过路径更新文件夹的 AI 标签（如果文件夹不存在则创建）
        
        Args:
            folder_path: 文件夹路径
            ai_category: AI 分类
            ai_tags: AI 标签（可选）
            
        Returns:
            是否更新成功
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # 标准化路径（去除尾部斜杠，统一为反斜杠）
            normalized_path = folder_path.rstrip('/\\').replace('/', '\\')
            
            # 尝试用 LIKE 匹配（大小写不敏感）
            cursor.execute("""
                UPDATE folders SET ai_category = ?, ai_tags = ? 
                WHERE path COLLATE NOCASE = ? OR path COLLATE NOCASE = ?
            """, (ai_category, ai_tags, normalized_path, normalized_path.replace('\\', '/')))
            
            if cursor.rowcount > 0:
                return True
            
            # 尝试用文件夹名末尾模糊匹配
            folder_name = normalized_path.split('\\')[-1] if '\\' in normalized_path else normalized_path
            cursor.execute("""
                UPDATE folders SET ai_category = ?, ai_tags = ? 
                WHERE path COLLATE NOCASE LIKE ?
            """, (ai_category, ai_tags, f"%\\{folder_name}"))
            
            if cursor.rowcount > 0:
                return True
            
            # 文件夹不存在，创建它
            try:
                cursor.execute("""
                    INSERT INTO folders (path, ai_category, ai_tags) VALUES (?, ?, ?)
                """, (normalized_path, ai_category, ai_tags))
                return True
            except Exception as e:
                logger.warning(f"    创建文件夹记录失败: {e}")
                return False
    
    def get_all_extensions(self) -> list[tuple[str, int]]:
        """获取所有扩展名及其文件数量"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT extension, COUNT(*) as count 
                FROM files 
                WHERE extension IS NOT NULL AND extension != ''
                GROUP BY extension 
                ORDER BY count DESC
            """)
            return [(row['extension'], row['count']) for row in cursor.fetchall()]
    
    def get_folder_tree(self) -> list[str]:
        """获取所有扫描源目录列表（用于构建目录树）
        
        排序规则：本地路径在前，网络路径在后，各自按字母顺序
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # 从scan_sources表获取扫描源
            cursor.execute("SELECT path FROM scan_sources")
            sources = [row['path'] for row in cursor.fetchall() if row['path']]
            
            # 如果scan_sources为空，从folders表提取顶级目录
            if not sources:
                cursor.execute("SELECT DISTINCT path FROM folders")
                all_paths = [row['path'] for row in cursor.fetchall() if row['path']]
                # 提取扫描源（最上层路径）
                sources = self._extract_scan_sources(all_paths)
            
            # 分离本地路径和网络路径
            local_paths = sorted([s for s in sources if not s.startswith('\\\\')])
            network_paths = sorted([s for s in sources if s.startswith('\\\\')])
            
            return local_paths + network_paths
    
    def _extract_scan_sources(self, paths: list[str]) -> list[str]:
        """从路径列表中提取扫描源（顶级目录）"""
        sources = set()
        for path in paths:
            path = path.replace('/', '\\')
            if path.startswith('\\\\'):
                # 网络路径：取 \\server\share
                parts = path.lstrip('\\').split('\\')
                if len(parts) >= 2:
                    sources.add('\\\\' + parts[0] + '\\' + parts[1])
            else:
                # 本地路径：取盘符
                parts = path.split('\\')
                if parts:
                    sources.add(parts[0] + '\\')
        return list(sources)
    
    def get_all_directories(self) -> list[str]:
        """获取所有目录路径（用于构建完整目录树）"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT path FROM folders ORDER BY path")
            return [row['path'] for row in cursor.fetchall() if row['path']]
    
    def get_direct_subdirs(self, parent_path: str) -> list[dict]:
        """获取指定路径下的直接子目录（优先使用 parent_id 索引查询）
        
        Args:
            parent_path: 父目录路径
            
        Returns:
            子目录列表，每项包含 name, path, has_children
        """
        parent_path = parent_path.replace('/', '\\').rstrip('\\')
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 获取父目录的 ID
            cursor.execute("SELECT id FROM folders WHERE path = ? COLLATE NOCASE", (parent_path,))
            parent_row = cursor.fetchone()
            
            if parent_row:
                parent_id = parent_row['id']
                
                # 使用 parent_id 索引查询直接子目录（O(1) 复杂度）
                cursor.execute("""
                    SELECT id, path, ai_category, ai_tags
                    FROM folders 
                    WHERE parent_id = ?
                """, (parent_id,))
                
                subdirs = []
                for row in cursor.fetchall():
                    folder_id = row['id']
                    path = row['path']
                    name = path.split('\\')[-1] if '\\' in path else path
                    
                    # 检查是否有子目录（使用 parent_id 索引）
                    cursor.execute("SELECT 1 FROM folders WHERE parent_id = ? LIMIT 1", (folder_id,))
                    has_subdirs = cursor.fetchone() is not None
                    
                    # 检查是否有文件
                    cursor.execute("SELECT 1 FROM files WHERE folder_id = ? LIMIT 1", (folder_id,))
                    has_files = cursor.fetchone() is not None
                    
                    subdirs.append({
                        'name': name,
                        'path': path,
                        'has_children': has_subdirs  # 只检查是否有子目录，不检查文件
                    })
                
                return sorted(subdirs, key=lambda x: x['name'].lower())
            
            # 回退方案：parent_id 未填充时使用 LIKE 查询
            prefix = parent_path + '\\'
            prefix_len = len(prefix)
            
            cursor.execute("""
                SELECT DISTINCT 
                    SUBSTR(path, ?) as remaining,
                    path
                FROM folders 
                WHERE path LIKE ? ESCAPE '\\'
                  AND path COLLATE NOCASE != ?
                  AND INSTR(SUBSTR(path, ?), '\\') = 0
            """, (prefix_len + 1, prefix.replace('\\', '\\\\') + '%', parent_path, prefix_len + 1))
            
            subdirs_by_name = {}
            for row in cursor.fetchall():
                name = row['remaining']
                if name:
                    name_key = name.lower()
                    if name_key not in subdirs_by_name:
                        subdirs_by_name[name_key] = {
                            'name': name,
                            'path': parent_path + '\\' + name,
                        }
            
            result = []
            for subdir in subdirs_by_name.values():
                subdir_path = subdir['path']
                subdir_prefix = subdir_path + '\\'
                
                cursor.execute("""
                    SELECT 1 FROM folders 
                    WHERE path LIKE ? ESCAPE '\\' 
                    LIMIT 1
                """, (subdir_prefix.replace('\\', '\\\\') + '%',))
                has_subdirs = cursor.fetchone() is not None
                
                cursor.execute("""
                    SELECT 1 FROM files f
                    JOIN folders fo ON f.folder_id = fo.id
                    WHERE fo.path COLLATE NOCASE = ?
                    LIMIT 1
                """, (subdir_path,))
                has_files = cursor.fetchone() is not None
                
                subdir['has_children'] = has_subdirs  # 只检查是否有子目录
                result.append(subdir)
            
            return sorted(result, key=lambda x: x['name'].lower())


    
    def get_stats(self) -> dict:
        """获取统计信息"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 总文件数
            cursor.execute("SELECT COUNT(*) as count FROM files")
            total_files = cursor.fetchone()['count']
            
            # 总大小
            cursor.execute("SELECT SUM(size_bytes) as total FROM files")
            total_size = cursor.fetchone()['total'] or 0
            
            # 扩展名数量
            cursor.execute("SELECT COUNT(DISTINCT extension) as count FROM files")
            extension_count = cursor.fetchone()['count']
            
            # 已AI分类的文件数
            cursor.execute("SELECT COUNT(*) as count FROM files WHERE ai_category IS NOT NULL")
            ai_categorized = cursor.fetchone()['count']
            
            return {
                'total_files': total_files,
                'total_size': total_size,
                'extension_count': extension_count,
                'ai_categorized': ai_categorized
            }
    
    def clear_source(self, scan_source: str) -> int:
        """清除指定扫描源的所有记录"""
        scan_source_normalized = scan_source.replace('/', '\\').rstrip('\\').lower()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 直接用子查询删除文件（更高效）
            cursor.execute("""
                DELETE FROM files WHERE folder_id IN (
                    SELECT id FROM folders 
                    WHERE LOWER(path) = ? OR LOWER(path) LIKE ?
                )
            """, (scan_source_normalized, f"{scan_source_normalized}\\%"))
            deleted_count = cursor.rowcount
            
            # 删除文件夹记录
            cursor.execute("""
                DELETE FROM folders 
                WHERE LOWER(path) = ? OR LOWER(path) LIKE ?
            """, (scan_source_normalized, f"{scan_source_normalized}\\%"))
        
        # VACUUM回收空间
        if deleted_count > 0:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute("VACUUM")
            conn.close()
        
        return deleted_count
    
    def get_all_files(self, limit: int = 10000, offset: int = 0) -> list[dict]:
        """获取所有文件（分页）"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT f.*, fo.path as parent_folder,
                       fo.path || '\\' || f.filename as full_path
                FROM files f
                LEFT JOIN folders fo ON f.folder_id = fo.id
                ORDER BY f.filename LIMIT ? OFFSET ?
            """, (limit, offset))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_folder_contents(self, folder_path: str, limit: int = 500, offset: int = 0) -> dict:
        """获取指定目录的内容（直接子目录和文件）"""
        folder_path = folder_path.replace('/', '\\').rstrip('\\')
        # 注意：SQLite LOWER() 对非 ASCII 字符无效，使用精确匹配
        prefix = folder_path + '\\'
        prefix_len = len(prefix)
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 获取当前目录的folder_id（精确匹配，但允许大小写差异）
            # 使用 COLLATE NOCASE 确保 Windows 路径不区分大小写
            cursor.execute("SELECT id FROM folders WHERE path = ? COLLATE NOCASE", (folder_path,))
            row = cursor.fetchone()
            current_folder_id = row['id'] if row else None
            
            # 获取直接子目录（优化：只查询第一级子目录）
            # 使用 COLLATE NOCASE 进行大小写不敏感比较（对非ASCII字符也有效）
            cursor.execute("""
                SELECT DISTINCT 
                    SUBSTR(path, ?) as remaining,
                    path,
                    ai_category,
                    ai_tags
                FROM folders 
                WHERE path LIKE ? ESCAPE '\\'
                  AND path COLLATE NOCASE != ?
                  AND INSTR(SUBSTR(path, ?), '\\') = 0
            """, (prefix_len + 1, prefix.replace('\\', '\\\\') + '%', folder_path, prefix_len + 1))
            
            # 按文件名（忽略大小写）分组去重
            dirs_by_name = {}
            for row in cursor.fetchall():
                first_part = row['remaining'].split('\\')[0] if row['remaining'] else ''
                if first_part:
                    name_key = first_part.lower()
                    if name_key not in dirs_by_name:
                        dirs_by_name[name_key] = []
                    
                    dirs_by_name[name_key].append({
                        'filename': first_part,
                        'full_path': folder_path + '\\' + first_part,
                        'is_dir': 1,
                        'ai_category': row['ai_category'] or '',
                        'ai_tags': row['ai_tags'] or '',
                    })
            
            # 额外查询 files 表中的目录记录（is_dir=1）
            # 这些目录可能不在 folders 表中（如只有子目录没有文件的目录）
            if current_folder_id:
                cursor.execute("""
                    SELECT f.filename, f.id
                    FROM files f
                    WHERE f.folder_id = ? AND f.is_dir = 1 AND f.filename != ''
                """, (current_folder_id,))
                
                for row in cursor.fetchall():
                    dir_name = row['filename']
                    if not dir_name:  # 跳过空文件名
                        continue
                    name_key = dir_name.lower()
                    if name_key not in dirs_by_name:
                        dirs_by_name[name_key] = []
                        dirs_by_name[name_key].append({
                            'filename': dir_name,
                            'full_path': folder_path + '\\' + dir_name,
                            'is_dir': 1,
                            'ai_category': '',
                            'ai_tags': '',
                        })
            
            subdirs_direct = []
            all_variant_paths = []
            
            for variants in dirs_by_name.values():
                # 选取每一组的第一个作为代表
                rep = variants[0]
                # 记录该组所有变体的路径，以便后续汇总统计
                rep['_all_paths'] = [v['full_path'] for v in variants]
                all_variant_paths.extend(rep['_all_paths'])
                subdirs_direct.append(rep)
            
            # 为子目录批量获取计数（汇总所有变体）
            if all_variant_paths:
                # 批量查询所有变体的 folder_id
                placeholders = ','.join('?' * len(all_variant_paths))
                cursor.execute(f"""
                    SELECT id, path FROM folders 
                    WHERE path IN ({placeholders})
                """, all_variant_paths)
                path_to_id = {row['path']: row['id'] for row in cursor.fetchall()}
                
                # 批量查询文件数
                folder_ids = list(path_to_id.values())
                if folder_ids:
                    placeholders = ','.join('?' * len(folder_ids))
                    cursor.execute(f"""
                        SELECT folder_id, COUNT(*) as count FROM files 
                        WHERE folder_id IN ({placeholders})
                        GROUP BY folder_id
                    """, folder_ids)
                    id_to_count = {row['folder_id']: row['count'] for row in cursor.fetchall()}
                else:
                    id_to_count = {}
                
                # 汇总赋值
                for subdir in subdirs_direct:
                    total_count = 0
                    for path in subdir.get('_all_paths', []):
                        fid = path_to_id.get(path)
                        if fid:
                            total_count += id_to_count.get(fid, 0)
                    subdir['file_count'] = total_count
                    # 清理临时字段
                    if '_all_paths' in subdir:
                        del subdir['_all_paths']
            
            subdirs_direct.sort(key=lambda x: x['filename'].lower())
            
            # 获取直接文件
            if current_folder_id:
                cursor.execute("""
                    SELECT COUNT(*) as total FROM files 
                    WHERE folder_id = ? AND (is_dir = 0 OR is_dir IS NULL)
                """, (current_folder_id,))
                total_files = cursor.fetchone()['total']
                
                cursor.execute("""
                    SELECT f.*, fo.path as parent_folder,
                           fo.path || '\\' || f.filename as full_path
                    FROM files f
                    LEFT JOIN folders fo ON f.folder_id = fo.id
                    WHERE f.folder_id = ? AND (f.is_dir = 0 OR f.is_dir IS NULL)
                    ORDER BY f.filename
                    LIMIT ? OFFSET ?
                """, (current_folder_id, limit, offset))
                files = [dict(row) for row in cursor.fetchall()]
            else:
                total_files = 0
                files = []
            
            has_more = (offset + len(files)) < total_files
            
            return {
                'subdirs': subdirs_direct,
                'files': files,
                'has_more': has_more,
                'total': total_files
            }
    
    def get_file_count_in_folder(self, folder_path: str) -> int:
        """获取指定目录下的直接文件数量"""
        folder_path = folder_path.replace('/', '\\').rstrip('\\')
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM files f
                JOIN folders fo ON f.folder_id = fo.id
                WHERE fo.path = ? AND (f.is_dir IS NULL OR f.is_dir = 0)
            """, (folder_path,))
            return cursor.fetchone()[0]
    
    # ========== 扫描错误管理 ==========
    
    def insert_scan_error(self, file_path: str, error_message: str, scan_source: str):
        """记录扫描错误"""
        import time
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO scan_errors (file_path, error_message, error_time, scan_source)
                VALUES (?, ?, ?, ?)
            """, (file_path, error_message, time.time(), scan_source))
    
    def get_scan_errors(self, scan_source: str = None, include_resolved: bool = False) -> list[dict]:
        """获取扫描错误列表"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if scan_source:
                if include_resolved:
                    cursor.execute("SELECT * FROM scan_errors WHERE scan_source = ? ORDER BY error_time DESC", (scan_source,))
                else:
                    cursor.execute("SELECT * FROM scan_errors WHERE scan_source = ? AND resolved = 0 ORDER BY error_time DESC", (scan_source,))
            else:
                if include_resolved:
                    cursor.execute("SELECT * FROM scan_errors ORDER BY error_time DESC")
                else:
                    cursor.execute("SELECT * FROM scan_errors WHERE resolved = 0 ORDER BY error_time DESC")
            return [dict(row) for row in cursor.fetchall()]
    
    def get_error_count(self) -> int:
        """获取未解决错误数量"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM scan_errors WHERE resolved = 0")
            return cursor.fetchone()['count']
    
    def mark_error_resolved(self, error_id: int):
        """标记错误为已解决"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE scan_errors SET resolved = 1 WHERE id = ?", (error_id,))
    
    def delete_error(self, error_id: int):
        """删除错误记录"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM scan_errors WHERE id = ?", (error_id,))
    
    def clear_errors(self, scan_source: str = None):
        """清除错误记录"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if scan_source:
                cursor.execute("DELETE FROM scan_errors WHERE scan_source = ?", (scan_source,))
            else:
                cursor.execute("DELETE FROM scan_errors")
    
    def optimize_database(self) -> dict:
        """优化数据库（压缩和更新统计）
        
        Returns:
            优化结果信息
        """
        import os
        
        # 获取优化前大小
        size_before = os.path.getsize(self.db_path) if self.db_path.exists() else 0
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # VACUUM 压缩数据库，回收空间
            cursor.execute("VACUUM")
            # ANALYZE 更新查询优化器统计信息
            cursor.execute("ANALYZE")
        
        # 获取优化后大小
        size_after = os.path.getsize(self.db_path) if self.db_path.exists() else 0
        
        return {
            'size_before': size_before,
            'size_after': size_after,
            'saved': size_before - size_after
        }
    
    def analyze_database(self):
        """更新查询优化器统计信息（轻量级，扫描后自动调用）"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("ANALYZE")
