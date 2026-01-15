"""
FileRecorder 文件浏览器组件
支持逐级目录浏览，类似文件管理器
"""
from pathlib import Path
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, Signal
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import QStyle, QApplication


class FileBrowserModel(QAbstractTableModel):
    """文件浏览器模型 - 支持目录和文件混合显示（分页加载）"""
    
    # 加载更多信号
    load_more_requested = Signal()
    
    COLUMNS = [
        ('name', '名称'),
        ('type', '类型'),
        ('size', '大小'),
        ('mtime', '修改时间'),
        ('ai_category', 'AI分类'),
    ]
    
    PAGE_SIZE = 200  # 每页加载数量
    PRELOAD_THRESHOLD = 50  # 距离底部多少行时预加载
    
    def __init__(self, db=None, parent=None):
        super().__init__(parent)
        self._db = db  # 数据库引用
        self._items: list[dict] = []  # 当前显示的项目（目录+文件）
        self._current_path: str = ""  # 当前浏览路径
        self._file_offset: int = 0  # 文件分页偏移
        self._has_more: bool = False  # 是否有更多文件
        self._total_files: int = 0  # 当前目录总文件数
        self._subdirs_count: int = 0  # 子目录数量
        self._loading: bool = False  # 是否正在加载
        self._folder_cache: dict = {}  # 目录内容缓存（最多缓存50个）
        self._cache_max_size = 50
    
    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._items)
    
    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self.COLUMNS)
    
    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._items)):
            return None
        
        item = self._items[index.row()]
        column_key = self.COLUMNS[index.column()][0]
        
        if role == Qt.DisplayRole:
            if column_key == 'name':
                return item.get('name', '')
            elif column_key == 'type':
                if item.get('is_dir'):
                    return '文件夹'
                return item.get('extension', '') or '文件'
            elif column_key == 'size':
                if item.get('is_dir'):
                    count = item.get('file_count', 0)
                    return f"{count} 项"
                return self._format_size(item.get('size_bytes', 0))
            elif column_key == 'mtime':
                mtime = item.get('mtime')
                return self._format_time(mtime) if mtime else ''
            elif column_key == 'ai_category':
                return item.get('ai_category', '')
            return ''
        
        elif role == Qt.DecorationRole:
            if index.column() == 0:  # 名称列显示图标
                style = QApplication.style()
                if item.get('is_dir'):
                    return style.standardIcon(QStyle.SP_DirIcon)
                else:
                    return style.standardIcon(QStyle.SP_FileIcon)
        
        elif role == Qt.ToolTipRole:
            if index.column() == 0:
                return item.get('full_path', '')
        
        elif role == Qt.UserRole:
            return item  # 返回完整数据
        
        elif role == Qt.BackgroundRole:
            # 不设置固定背景色，让系统主题处理以支持深色模式
            pass
        
        return None
    
    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            if 0 <= section < len(self.COLUMNS):
                return self.COLUMNS[section][1]
        return None
    
    def sort(self, column: int, order: Qt.SortOrder = Qt.AscendingOrder):
        """排序 - 目录始终在前"""
        if not self._items:
            return
        
        column_key = self.COLUMNS[column][0]
        reverse = (order == Qt.DescendingOrder)
        
        # 分离目录和文件
        dirs = [i for i in self._items if i.get('is_dir')]
        files = [i for i in self._items if not i.get('is_dir')]
        
        # 数值类型列
        numeric_keys = {'size_bytes', 'mtime', 'file_count'}
        
        def get_sort_key(item):
            if column_key == 'name':
                return item.get('name', '').lower()
            elif column_key == 'size':
                if item.get('is_dir'):
                    return item.get('file_count', 0)
                return item.get('size_bytes', 0)
            elif column_key == 'mtime':
                return item.get('mtime', 0)
            elif column_key == 'type':
                if item.get('is_dir'):
                    return ''
                return item.get('extension', '')
            else:
                val = item.get(column_key)
                return val if val is not None else ''
        
        dirs.sort(key=get_sort_key, reverse=reverse)
        files.sort(key=get_sort_key, reverse=reverse)
        
        self.beginResetModel()
        self._items = dirs + files
        self.endResetModel()
    
    def set_db(self, db):
        """设置数据库引用"""
        self._db = db
    
    def navigate_to(self, path: str = ""):
        """导航到指定路径"""
        self._current_path = path
        self._file_offset = 0  # 重置分页
        self._rebuild_view()
    
    def clear_cache(self):
        """清除目录内容缓存（数据变化后调用）"""
        self._folder_cache.clear()
    
    def get_current_path(self) -> str:
        """获取当前路径"""
        return self._current_path
    
    def _rebuild_view(self):
        """重建当前视图（从数据库按需加载，支持缓存）"""
        if not self._db:
            return
        
        self.beginResetModel()
        self._items = []
        
        path_to_show = self._current_path
        
        # 如果路径为空，获取第一个扫描源
        if not path_to_show:
            folders = self._db.get_folder_tree()
            if folders:
                path_to_show = folders[0]
                self._current_path = path_to_show
        
        if path_to_show:
            cache_key = path_to_show.lower()
            
            # 尝试从缓存获取
            if cache_key in self._folder_cache:
                contents = self._folder_cache[cache_key]
            else:
                # 从数据库获取并缓存
                contents = self._db.get_folder_contents(
                    path_to_show, 
                    limit=self.PAGE_SIZE, 
                    offset=0
                )
                # 缓存结果（限制缓存大小）
                if len(self._folder_cache) >= self._cache_max_size:
                    # 移除最早的缓存
                    oldest_key = next(iter(self._folder_cache))
                    del self._folder_cache[oldest_key]
                self._folder_cache[cache_key] = contents
            
            self._subdirs_count = len(contents['subdirs'])
            self._total_files = contents['total']
            self._has_more = contents['has_more']
            self._file_offset = len(contents['files'])
            
            # 添加子目录
            for subdir in contents['subdirs']:
                self._items.append({
                    'name': subdir.get('filename', ''),
                    'full_path': subdir.get('full_path', ''),
                    'is_dir': True,
                    'file_count': subdir.get('file_count', 0),
                    'ai_category': subdir.get('ai_category', ''),
                    'ai_tags': subdir.get('ai_tags', ''),
                })
            
            # 添加文件
            for f in contents['files']:
                self._items.append({
                    'name': f.get('filename', ''),
                    'full_path': f.get('full_path', ''),
                    'extension': f.get('extension', ''),
                    'size_bytes': f.get('size_bytes', 0),
                    'mtime': f.get('mtime'),
                    'ai_category': f.get('ai_category'),
                    'ai_tags': f.get('ai_tags'),
                    'is_dir': False,
                })
        
        self.endResetModel()
    
    def load_more(self):
        """加载更多文件（分页）"""
        if not self._db or not self._has_more or self._loading:
            return
        
        self._loading = True
        
        contents = self._db.get_folder_contents(
            self._current_path,
            limit=self.PAGE_SIZE,
            offset=self._file_offset
        )
        
        if contents['files']:
            # 插入新数据
            start_row = len(self._items)
            self.beginInsertRows(QModelIndex(), start_row, start_row + len(contents['files']) - 1)
            
            for f in contents['files']:
                self._items.append({
                    'name': f.get('filename', ''),
                    'full_path': f.get('full_path', ''),
                    'extension': f.get('extension', ''),
                    'size_bytes': f.get('size_bytes', 0),
                    'mtime': f.get('mtime'),
                    'ai_category': f.get('ai_category'),
                    'ai_tags': f.get('ai_tags'),
                    'is_dir': False,
                })
            
            self.endInsertRows()
            self._file_offset += len(contents['files'])
        
        self._has_more = contents['has_more']
        self._loading = False
    
    def has_more(self) -> bool:
        """是否有更多数据可加载"""
        return self._has_more
    
    def check_load_more(self, visible_row: int):
        """检查是否需要预加载更多"""
        if self._has_more and not self._loading:
            remaining = len(self._items) - visible_row
            if remaining < self.PRELOAD_THRESHOLD:
                self.load_more()
    
    def _build_root_view(self):
        """构建根视图 - 显示所有顶级目录"""
        # 收集所有唯一的顶级路径
        root_paths = {}  # key: 小写路径, value: 原始路径
        
        for f in self._all_files:
            full_path = f.get('full_path', '').replace('/', '\\')
            if not full_path:
                continue
            
            path = Path(full_path)
            parts = path.parts
            
            if len(parts) >= 1:
                if full_path.startswith('\\\\'):
                    # 网络路径，取前两部分
                    if len(parts) >= 2:
                        root = '\\\\' + parts[0].strip('\\') + '\\' + parts[1]
                    else:
                        root = full_path
                else:
                    # 本地路径，取盘符
                    root = parts[0] + '\\'
                
                root_lower = root.lower()
                if root_lower not in root_paths:
                    root_paths[root_lower] = root
        
        # 为每个根路径创建目录项
        for root_lower, root in sorted(root_paths.items()):
            file_count = sum(1 for f in self._all_files 
                           if f.get('full_path', '').lower().startswith(root_lower))
            self._items.append({
                'name': root,
                'full_path': root,
                'is_dir': True,
                'file_count': file_count,
            })
    
    def _build_folder_view(self, folder_path: str):
        """构建文件夹视图"""
        # 统一路径分隔符
        folder_path = folder_path.replace('/', '\\').rstrip('\\')
        folder_path_lower = folder_path.lower()
        prefix_len = len(folder_path)
        
        # 收集直接子目录和文件
        subdirs = {}
        files_in_folder = []
        
        for f in self._all_files:
            full_path = f.get('full_path', '').replace('/', '\\')
            full_path_lower = full_path.lower()
            
            # 检查是否在当前目录下（大小写不敏感）
            # 必须是 folder_path + '\' + 其他内容
            if not full_path_lower.startswith(folder_path_lower + '\\'):
                continue
            
            # 获取相对路径（跳过前缀和分隔符）
            relative = full_path[prefix_len + 1:]
            if not relative:
                continue
            
            # 分割相对路径
            parts = relative.split('\\')
            is_dir = f.get('is_dir', False)
            
            if len(parts) == 1:
                # 直接在当前目录下的项目
                if is_dir:
                    # 是目录记录
                    subdir_key = full_path_lower
                    if subdir_key not in subdirs:
                        subdirs[subdir_key] = {
                            'name': f.get('filename', parts[0]),
                            'full_path': full_path,
                            'is_dir': True,
                            'file_count': 0,
                        }
                else:
                    # 是文件记录
                    files_in_folder.append(f)
            elif len(parts) > 1:
                # 子目录中的项目 - 添加到子目录计数
                subdir_name = parts[0]
                subdir_path = folder_path + '\\' + subdir_name
                subdir_key = subdir_path.lower()
                
                if subdir_key not in subdirs:
                    subdirs[subdir_key] = {
                        'name': subdir_name,
                        'full_path': subdir_path,
                        'is_dir': True,
                        'file_count': 0,
                    }
                subdirs[subdir_key]['file_count'] += 1
        
        # 添加子目录
        for subdir in sorted(subdirs.values(), key=lambda x: x['name'].lower()):
            self._items.append(subdir)
        
        # 添加文件
        for f in sorted(files_in_folder, key=lambda x: x.get('filename', '').lower()):
            self._items.append({
                'name': f.get('filename', ''),
                'full_path': f.get('full_path', ''),
                'extension': f.get('extension', ''),
                'size_bytes': f.get('size_bytes', 0),
                'mtime': f.get('mtime'),
                'ai_category': f.get('ai_category'),
                'ai_tags': f.get('ai_tags'),
                'is_dir': False,
                'id': f.get('id'),
            })
    
    def get_item_at(self, row: int) -> dict:
        """获取指定行的项目"""
        if 0 <= row < len(self._items):
            return self._items[row]
        return {}
    
    def get_all_files_in_view(self) -> list[dict]:
        """获取当前视图中的所有文件（不含目录）"""
        return [item for item in self._items if not item.get('is_dir')]
    
    @staticmethod
    def _format_size(size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
    
    @staticmethod
    def _format_time(timestamp: float) -> str:
        from datetime import datetime
        try:
            dt = datetime.fromtimestamp(timestamp)
            return dt.strftime('%Y-%m-%d %H:%M')
        except (ValueError, OSError):
            return ''
