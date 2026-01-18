"""
FileRecorder 文件表格模型
用于 QTableView 显示文件列表
"""
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel
from PySide6.QtGui import QColor, QFontMetrics
from PySide6.QtWidgets import QStyledItemDelegate, QStyle


class FileTableModel(QAbstractTableModel):
    """文件列表表格模型"""
    
    COLUMNS = [
        ('filename', '文件名'),
        ('extension', '类型'),
        ('size_bytes', '大小'),
        ('mtime', '修改时间'),
        ('parent_folder', '所在目录'),
        ('ai_category', 'AI分类'),
    ]
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: list[dict] = []
    
    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._data)
    
    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self.COLUMNS)
    
    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._data)):
            return None
        
        row_data = self._data[index.row()]
        column_key = self.COLUMNS[index.column()][0]
        value = row_data.get(column_key)
        
        if role == Qt.DisplayRole:
            # 格式化显示
            if column_key == 'size_bytes' and value is not None:
                return self._frc_format_size(value)
            elif column_key == 'mtime' and value is not None:
                return self._frc_format_time(value)
            elif column_key == 'extension':
                # 文件夹显示"文件夹"
                if row_data.get('is_dir'):
                    return '文件夹'
                return value or ''
            return value or ''
        
        elif role == Qt.ToolTipRole:
            if column_key == 'filename':
                return row_data.get('full_path', '')
            elif column_key == 'parent_folder':
                # 鼠标悬浮显示完整路径
                return value or ''
            return None
        
        elif role == Qt.TextAlignmentRole:
            # 所在目录列左对齐（确保显示左边内容）
            if column_key == 'parent_folder':
                return Qt.AlignLeft | Qt.AlignVCenter
            return None
        
        elif role == Qt.UserRole:
            # 返回原始值用于排序
            return value
        
        # 不设置特殊背景色，让系统主题处理以支持深色模式
        
        return None
    
    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            if 0 <= section < len(self.COLUMNS):
                return self.COLUMNS[section][1]
        return None
    
    def sort(self, column: int, order: Qt.SortOrder = Qt.AscendingOrder):
        """排序功能"""
        if not self._data:
            return
        
        column_key = self.COLUMNS[column][0]
        reverse = (order == Qt.DescendingOrder)
        
        # 数值类型列使用0作为默认值，字符串列使用空字符串
        numeric_columns = {'size_bytes', 'ctime', 'mtime'}
        if column_key in numeric_columns:
            default_value = 0
        else:
            default_value = ''
        
        self.beginResetModel()
        self._data.sort(
            key=lambda x: (x.get(column_key) is None, x.get(column_key) if x.get(column_key) is not None else default_value),
            reverse=reverse
        )
        self.endResetModel()
    
    def set_data(self, files: list[dict]) -> None:
        """设置表格数据"""
        self.beginResetModel()
        self._data = files
        self.endResetModel()
    
    def append_data(self, files: list[dict]) -> None:
        """追加数据"""
        if not files:
            return
        self.beginInsertRows(QModelIndex(), len(self._data), len(self._data) + len(files) - 1)
        self._data.extend(files)
        self.endInsertRows()
    
    def clear(self) -> None:
        """清空数据"""
        self.beginResetModel()
        self._data = []
        self.endResetModel()
    
    def get_file_at(self, row: int) -> dict:
        """获取指定行的文件信息"""
        if 0 <= row < len(self._data):
            return self._data[row]
        return {}
    
    def get_all_data(self) -> list[dict]:
        """获取所有数据"""
        return self._data.copy()
    
    @staticmethod
    def _frc_format_size(size_bytes: int) -> str:
        """格式化文件大小"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
    
    @staticmethod
    def _frc_format_time(timestamp: float) -> str:
        """格式化时间戳"""
        from datetime import datetime
        try:
            dt = datetime.fromtimestamp(timestamp)
            return dt.strftime('%Y-%m-%d %H:%M')
        except (ValueError, OSError):
            return ''


class ElideDelegate(QStyledItemDelegate):
    """自定义代理：自适应文本省略（ElideRight）"""
    
    def paint(self, painter, option, index):
        # 初始化样式选项
        opt = option
        self.initStyleOption(opt, index)
        
        # 获取文本
        text = opt.text
        if not text:
            return super().paint(painter, option, index)
        
        # 清空文本，让父类只绘制背景和焦点框
        opt.text = ""
        style = opt.widget.style() if opt.widget else None
        if style:
            style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)
        
        # 计算可用宽度（减去左右边距）
        text_rect = opt.rect.adjusted(4, 0, -4, 0)
        
        # 使用字体度量计算省略文本
        metrics = QFontMetrics(opt.font)
        elided_text = metrics.elidedText(text, Qt.ElideRight, text_rect.width())
        
        # 绘制省略后的文本
        painter.save()
        if opt.state & QStyle.State_Selected:
            painter.setPen(opt.palette.highlightedText().color())
        else:
            painter.setPen(opt.palette.text().color())
        painter.setFont(opt.font)
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, elided_text)
        painter.restore()


class HighlightDelegate(QStyledItemDelegate):
    """自定义代理：搜索词高亮显示"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._search_terms: list[str] = []  # 搜索关键词列表
        self._highlight_color = QColor(255, 255, 0, 180)  # 黄色高亮
        self._highlight_color_selected = QColor(255, 200, 0, 200)  # 选中时的高亮
    
    def set_search_terms(self, terms: list[str]):
        """设置搜索关键词列表"""
        self._search_terms = [t.lower() for t in terms if t]
    
    def clear_search_terms(self):
        """清除搜索关键词"""
        self._search_terms = []
    
    def paint(self, painter, option, index):
        # 初始化样式选项
        opt = option
        self.initStyleOption(opt, index)
        
        text = opt.text
        if not text or not self._search_terms:
            # 无搜索词时使用默认绘制
            return super().paint(painter, option, index)
        
        # 清空文本，让父类只绘制背景和焦点框
        opt.text = ""
        style = opt.widget.style() if opt.widget else None
        if style:
            style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)
        
        # 计算可用宽度
        text_rect = opt.rect.adjusted(4, 0, -4, 0)
        metrics = QFontMetrics(opt.font)
        
        # 省略文本
        elided_text = metrics.elidedText(text, Qt.ElideRight, text_rect.width())
        
        # 查找所有匹配位置
        text_lower = elided_text.lower()
        highlights = []  # [(start, end), ...]
        
        for term in self._search_terms:
            start = 0
            while True:
                pos = text_lower.find(term, start)
                if pos == -1:
                    break
                highlights.append((pos, pos + len(term)))
                start = pos + 1
        
        # 合并重叠区间
        if highlights:
            highlights.sort()
            merged = [highlights[0]]
            for start, end in highlights[1:]:
                if start <= merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(merged[-1][1], end))
                else:
                    merged.append((start, end))
            highlights = merged
        
        painter.save()
        painter.setFont(opt.font)
        
        # 选中状态使用不同颜色
        is_selected = opt.state & QStyle.State_Selected
        text_color = opt.palette.highlightedText().color() if is_selected else opt.palette.text().color()
        highlight_color = self._highlight_color_selected if is_selected else self._highlight_color
        
        # 绘制文本（逐段绘制，高亮部分加背景）
        x = text_rect.left()
        y = text_rect.top()
        h = text_rect.height()
        
        prev_end = 0
        for start, end in highlights:
            # 绘制高亮前的普通文本
            if start > prev_end:
                normal_text = elided_text[prev_end:start]
                painter.setPen(text_color)
                painter.drawText(x, y, metrics.horizontalAdvance(normal_text), h,
                               Qt.AlignLeft | Qt.AlignVCenter, normal_text)
                x += metrics.horizontalAdvance(normal_text)
            
            # 绘制高亮文本（带背景）
            highlight_text = elided_text[start:end]
            text_width = metrics.horizontalAdvance(highlight_text)
            
            # 绘制高亮背景
            painter.fillRect(x, y + 2, text_width, h - 4, highlight_color)
            
            # 绘制高亮文本
            painter.setPen(text_color)
            painter.drawText(x, y, text_width, h,
                           Qt.AlignLeft | Qt.AlignVCenter, highlight_text)
            x += text_width
            prev_end = end
        
        # 绘制剩余的普通文本
        if prev_end < len(elided_text):
            remaining_text = elided_text[prev_end:]
            painter.setPen(text_color)
            painter.drawText(x, y, metrics.horizontalAdvance(remaining_text), h,
                           Qt.AlignLeft | Qt.AlignVCenter, remaining_text)
        
        painter.restore()
