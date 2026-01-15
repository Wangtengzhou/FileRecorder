"""
媒体库整理向导 UI
目录选择、选项配置、进度显示
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QGroupBox, QCheckBox,
    QLineEdit, QProgressBar, QTextEdit, QFileDialog,
    QSplitter, QWidget, QComboBox, QSpinBox, QMessageBox,
    QFrame, QLayout, QSizePolicy, QScrollArea
)
from PySide6.QtCore import Qt, Signal, QThread, QRect, QSize, QPoint
from PySide6.QtGui import QFont
from pathlib import Path
from typing import Optional

from ai.parser import MediaParser, MediaInfo, VIDEO_EXTENSIONS
from ai.dedup import HardlinkDetector
from ai.classifier import MediaClassifier, BatchClassifier, ClassifyOptions
from ai.report import ReportGenerator, ReportOptions
from scanner.file_scanner import FileScanner
from config import config

# 默认标签列表
DEFAULT_TAGS = ["电影", "电视剧", "动漫", "纪录片", "综艺", "NSFW", "其他"]


class FlowLayout(QLayout):
    """流式布局 - 自动换行"""
    
    def __init__(self, parent=None, margin=0, spacing=6):
        super().__init__(parent)
        self.setContentsMargins(margin, margin, margin, margin)
        self._spacing = spacing
        self._items = []
    
    def addItem(self, item):
        self._items.append(item)
    
    def spacing(self):
        return self._spacing
    
    def count(self):
        return len(self._items)
    
    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None
    
    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None
    
    def hasHeightForWidth(self):
        return True
    
    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)
    
    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)
    
    def sizeHint(self):
        return self.minimumSize()
    
    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size
    
    def _do_layout(self, rect, test_only):
        margins = self.contentsMargins()
        effective_rect = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x = effective_rect.x()
        y = effective_rect.y()
        line_height = 0
        
        for item in self._items:
            widget = item.widget()
            space_x = self._spacing
            space_y = self._spacing
            
            next_x = x + item.sizeHint().width() + space_x
            if next_x - space_x > effective_rect.right() and line_height > 0:
                x = effective_rect.x()
                y = y + line_height + space_y
                next_x = x + item.sizeHint().width() + space_x
                line_height = 0
            
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
            
            x = next_x
            line_height = max(line_height, item.sizeHint().height())
        
        return y + line_height - rect.y() + margins.bottom()


class ScanWorker(QThread):
    """扫描和处理工作线程"""
    progress = Signal(int, int, str)  # current, total, message
    finished = Signal(list, str)       # results, report_path
    error = Signal(str)
    
    def __init__(self, directories: list[str], options: dict, db_manager=None):
        super().__init__()
        self.directories = directories
        self.options = options
        self.db = db_manager
        self._cancelled = False
    
    def run(self):
        try:
            all_media = []
            
            # 1. 使用 FileScanner 扫描目录（自动保存到数据库）
            self.progress.emit(0, 100, "正在扫描目录并保存到索引...")
            
            scanner = FileScanner(
                db=self.db,
                batch_size=config.get("scanner", "batch_size", default=1000),
                ignore_patterns=config.get("scanner", "ignore_patterns"),
                timeout=config.get("scanner", "timeout_seconds", default=5)
            )
            
            total_dirs = len(self.directories)
            scanned_files = []
            
            for i, directory in enumerate(self.directories):
                if self._cancelled:
                    return
                self.progress.emit(i * 20 // total_dirs, 100, f"[{i+1}/{total_dirs}] 扫描: {directory}")
                
                try:
                    result = scanner.scan_path(directory)
                    file_count = result.get('file_count', 0)
                    error_count = result.get('error_count', 0)
                    self.progress.emit((i+1) * 20 // total_dirs, 100, 
                        f"  → 扫描完成: {file_count} 个文件, {error_count} 个错误")
                except Exception as e:
                    self.progress.emit((i+1) * 20 // total_dirs, 100, f"  ⚠️ 扫描出错: {e}")
            
            # 扫描完成后立即发出刷新信号，让主窗口显示新数据
            self.progress.emit(20, 100, "扫描完成，刷新主界面...")
            # 注意：实际刷新由 scan_finished 信号触发，这里只是进度提示
            
            # 2. 从数据库读取视频文件，构建 MediaInfo 列表
            self.progress.emit(25, 100, "从索引中筛选视频文件...")
            
            min_size = self.options.get('min_size_mb', 0) * 1024 * 1024
            
            # 原盘目录标识
            DISC_FOLDERS = {'BDMV', 'VIDEO_TS', 'HVDVD_TS'}
            disc_roots = set()  # 记录原盘根目录
            
            for directory in self.directories:
                try:
                    # 获取该目录下的所有文件
                    files = self.db.get_files_by_folder(directory) if self.db else []
                    print(f"数据库查询: {directory} → {len(files)} 个文件")
                    
                    # 第一遍：识别原盘目录和 ISO 文件
                    iso_files = []  # ISO 原盘文件
                    for f in files:
                        filename = f.get('filename', '')
                        ext = f.get('extension', '').lower()
                        parent = f.get('parent_folder', '')
                        
                        # 检测 ISO 文件
                        if ext == 'iso':
                            iso_files.append(f)
                            continue
                        
                        # 检测 BDMV/VIDEO_TS 目录结构
                        parts = parent.replace('\\', '/').split('/')
                        for i, part in enumerate(parts):
                            if part.upper() in DISC_FOLDERS:
                                # 找到原盘标识目录，记录其父目录（电影名称目录）
                                disc_root = '/'.join(parts[:i])
                                disc_roots.add(disc_root.lower())
                    
                    # 输出识别到的原盘
                    if disc_roots or iso_files:
                        print(f"  发现原盘: BDMV/DVD {len(disc_roots)} 个, ISO {len(iso_files)} 个")
                        for dr in disc_roots:
                            print(f"    - {dr}")
                    
                    # 第二遍：筛选文件，统计跳过原因
                    skipped_non_video = 0
                    skipped_in_disc = 0
                    skipped_small = 0
                    
                    for f in files:
                        ext = '.' + f.get('extension', '') if f.get('extension') else ''
                        
                        # 跳过 ISO 文件（已在原盘列表中单独处理）
                        if ext.lower() == '.iso':
                            continue
                        
                        if ext.lower() not in VIDEO_EXTENSIONS:
                            skipped_non_video += 1
                            continue
                        
                        filepath = f.get('full_path', '')
                        parent = f.get('parent_folder', '').replace('\\', '/').lower()
                        
                        # 检查是否在原盘目录内
                        in_disc = any(parent.startswith(dr) for dr in disc_roots)
                        if in_disc:
                            skipped_in_disc += 1
                            continue  # 跳过原盘内的文件
                        
                        size = f.get('size_bytes', 0)
                        if min_size > 0 and size < min_size:
                            skipped_small += 1
                            continue
                        
                        # 构建 MediaInfo
                        info = MediaInfo(
                            filename=f.get('filename', ''),
                            filepath=filepath,
                            size_bytes=size,
                            extension=ext,
                            file_id=(0, f.get('id', 0))
                        )
                        all_media.append(info)
                    
                    # 输出跳过统计
                    print(f"目录 {directory}: 总文件 {len(files)}, 非视频 {skipped_non_video}, 原盘内 {skipped_in_disc}, 小文件 {skipped_small}")
                    
                    # 原盘作为单独项目添加，计算体积
                    for disc_root in disc_roots:
                        # 从 disc_root 提取名称
                        disc_name = disc_root.split('/')[-1] if '/' in disc_root else disc_root
                        
                        # 计算原盘内所有文件的总体积
                        disc_size = 0
                        for f in files:
                            parent = f.get('parent_folder', '').replace('\\', '/').lower()
                            if parent.startswith(disc_root):
                                disc_size += f.get('size_bytes', 0)
                        
                        info = MediaInfo(
                            filename=disc_name,
                            filepath=disc_root,
                            size_bytes=disc_size,
                            extension='.disc',
                            is_disc=True,
                            disc_type='BluRay',
                            needs_ai=True  # 确保参与 AI 识别
                        )
                        all_media.append(info)
                    
                    # ISO 文件作为原盘添加
                    for iso_f in iso_files:
                        info = MediaInfo(
                            filename=iso_f.get('filename', ''),
                            filepath=iso_f.get('full_path', ''),
                            size_bytes=iso_f.get('size_bytes', 0),
                            extension='.iso',
                            is_disc=True,
                            disc_type='ISO',
                            file_id=(0, iso_f.get('id', 0)),  # 添加 file_id 以支持打标签
                            needs_ai=True  # 确保参与 AI 识别
                        )
                        all_media.append(info)
                        
                except Exception as e:
                    self.progress.emit(25, 100, f"  ⚠️ 读取文件列表出错: {e}")
            
            # 统计日志
            disc_count = len(disc_roots) + len([m for m in all_media if m.extension == '.iso'])
            print(f"预处理统计: 视频文件 {len(all_media)} 个, 原盘(含ISO) {disc_count} 个")
            
            total_files = len(all_media)
            self.progress.emit(30, 100, f"共筛选出 {total_files} 个视频文件")
            
            if not all_media:
                self.finished.emit([], "")
                return
            
            # 2. AI 分类（强制所有文件）
            self.progress.emit(40, 100, f"AI 识别 {len(all_media)} 个文件...")
            
            try:
                classifier = BatchClassifier()
                options = ClassifyOptions(
                    hint=self.options.get('ai_hint', ''),
                    batch_size=self.options.get('batch_size', 20),
                    skip_trailers=self.options.get('skip_trailers', True)
                )
                
                def on_progress(current, total, msg):
                    pct = 40 + int(current / max(total, 1) * 40)
                    self.progress.emit(pct, 100, msg)
                
                classifier.process(all_media, options, on_progress)
            except Exception as e:
                self.progress.emit(80, 100, f"  ⚠️ AI 识别出错: {e}")
            
            # 4. 生成报告
            self.progress.emit(85, 100, "生成报告...")
            try:
                generator = ReportGenerator()
                report_content = generator.generate(all_media, self.directories)
                
                # 保存报告
                report_path = self.options.get('report_path', '')
                if report_path:
                    generator.save(report_content, report_path)
                    self.progress.emit(90, 100, f"报告已保存: {report_path}")
            except Exception as e:
                self.progress.emit(90, 100, f"  ⚠️ 报告生成出错: {e}")
                report_path = ""
            
            # 5. 更新 AI 分类结果到数据库
            if self.db and self.options.get('save_tags', True):
                self.progress.emit(95, 100, f"更新 AI 分类结果... (共 {len(all_media)} 个文件)")
                try:
                    updates = []
                    skipped_no_id = 0
                    skipped_no_type = 0
                    skipped_skip = 0
                    for info in all_media:
                        # 跳过被标记为 skip 的文件（样片/预告片）
                        if getattr(info, 'skip', False):
                            skipped_skip += 1
                            continue
                        
                        # 获取文件 ID
                        if isinstance(info.file_id, tuple) and len(info.file_id) > 1:
                            file_db_id = info.file_id[1]
                        elif isinstance(info.file_id, int):
                            file_db_id = info.file_id
                        else:
                            file_db_id = 0
                        
                        # 跳过无效 ID（BDMV 原盘没有数据库 ID）
                        if file_db_id <= 0:
                            skipped_no_id += 1
                            continue
                        
                        # 跳过没有分类结果的文件
                        if not info.media_type and not info.title:
                            skipped_no_type += 1
                            continue
                        
                        updates.append({
                            'id': file_db_id,
                            'ai_category': info.media_type or '',
                            'ai_tags': info.title or ''
                        })
                    
                    # 更新普通文件的标签
                    if updates:
                        self.db.batch_update_ai_tags(updates)
                        msg = f"  → 已更新 {len(updates)} 个文件的 AI 分类"
                        if skipped_no_id > 0:
                            msg += f"（跳过 {skipped_no_id} 个 BDMV 原盘）"
                        self.progress.emit(98, 100, msg)
                    
                    # 为 BDMV 原盘更新文件夹标签
                    folder_updates = 0
                    folder_attempts = 0
                    for info in all_media:
                        # 只处理 BDMV 原盘（is_disc=True 且 extension='.disc'）
                        if getattr(info, 'is_disc', False) and info.extension == '.disc':
                            folder_attempts += 1
                            if info.media_type:
                                print(f"  📂 尝试更新 BDMV 文件夹: {info.filepath} → {info.media_type}")
                                success = self.db.update_folder_ai_tags(
                                    info.filepath,
                                    info.media_type,
                                    info.title or ''
                                )
                                if success:
                                    folder_updates += 1
                                    print(f"    ✅ 更新成功")
                                else:
                                    print(f"    ❌ 未找到匹配的文件夹")
                    
                    if folder_updates > 0:
                        self.progress.emit(100, 100, f"  → 已更新 {folder_updates} 个 BDMV 原盘文件夹的分类")
                    elif folder_attempts > 0:
                        self.progress.emit(100, 100, f"  ⚠️ 尝试更新 {folder_attempts} 个 BDMV，但未找到匹配的文件夹记录")
                    elif skipped_no_id == 0 and len(updates) == 0:
                        self.progress.emit(100, 100, f"  ⚠️ 没有可更新的文件（无分类: {skipped_no_type}）")
                except Exception as e:
                    import traceback
                    self.progress.emit(100, 100, f"  ⚠️ 更新分类出错: {e}")
            
            self.finished.emit(all_media, report_path)
            
        except Exception as e:
            import traceback
            error_msg = f"{e}\n{traceback.format_exc()}"
            self.error.emit(error_msg)
    
    def cancel(self):
        self._cancelled = True


class MediaWizardDialog(QDialog):
    """媒体库整理向导对话框"""
    
    # 扫描完成信号，用于通知主窗口刷新
    scan_finished = Signal()
    
    def __init__(self, parent=None, db_manager=None):
        super().__init__(parent)
        self.db = db_manager
        self.worker = None
        self.results = []
        self._current_tags = []  # 当前标签列表
        
        self.setWindowTitle("媒体库整理向导")
        self.setMinimumSize(800, 600)
        self.setup_ui()
        
        # 初始化标签显示
        self._load_tags()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # 使用 Splitter 分割上下区域
        splitter = QSplitter(Qt.Vertical)
        
        # 上半部分：配置区
        config_widget = QWidget()
        config_layout = QVBoxLayout(config_widget)
        config_layout.setContentsMargins(0, 0, 0, 0)
        
        # 1. 目录选择
        dir_group = QGroupBox("1. 选择目录")
        dir_layout = QVBoxLayout(dir_group)
        
        self.dir_list = QListWidget()
        self.dir_list.setMaximumHeight(120)
        dir_layout.addWidget(self.dir_list)
        
        dir_btn_layout = QHBoxLayout()
        self.add_dir_btn = QPushButton("浏览添加...")
        self.add_dir_btn.setAutoDefault(False)
        self.add_dir_btn.setDefault(False)
        self.remove_dir_btn = QPushButton("移除")
        self.remove_dir_btn.setAutoDefault(False)
        self.remove_dir_btn.setDefault(False)
        self.add_indexed_btn = QPushButton("从索引选择...")
        self.add_indexed_btn.setAutoDefault(False)
        self.add_indexed_btn.setDefault(False)
        dir_btn_layout.addWidget(self.add_dir_btn)
        dir_btn_layout.addWidget(self.remove_dir_btn)
        dir_btn_layout.addWidget(self.add_indexed_btn)
        dir_btn_layout.addStretch()
        dir_layout.addLayout(dir_btn_layout)
        
        config_layout.addWidget(dir_group)
        
        # 2. 扫描选项
        scan_group = QGroupBox("2. 扫描选项")
        scan_layout = QVBoxLayout(scan_group)
        
        row1 = QHBoxLayout()
        self.skip_small_cb = QCheckBox("跳过小于")
        self.min_size_spin = QSpinBox()
        self.min_size_spin.setRange(0, 1000)
        self.min_size_spin.setValue(100)
        row1.addWidget(self.skip_small_cb)
        row1.addWidget(self.min_size_spin)
        row1.addWidget(QLabel("MB 的文件"))
        row1.addStretch()
        scan_layout.addLayout(row1)
        
        row2 = QHBoxLayout()
        self.detect_disc_cb = QCheckBox("识别蓝光/DVD原盘")
        self.detect_disc_cb.setChecked(True)
        row2.addWidget(self.detect_disc_cb)
        row2.addStretch()
        scan_layout.addLayout(row2)
        
        config_layout.addWidget(scan_group)
        
        # 3. AI 识别选项
        ai_group = QGroupBox("3. AI 识别")
        ai_layout = QVBoxLayout(ai_group)
        
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("每批处理文件数："))
        self.batch_size_spin = QSpinBox()
        self.batch_size_spin.setRange(5, 100)
        self.batch_size_spin.setValue(20)
        self.batch_size_spin.setToolTip("每次发送给 AI 的文件数量，建议 10-30")
        row1.addWidget(self.batch_size_spin)
        row1.addSpacing(20)
        self.skip_trailer_cb = QCheckBox("跳过预告片/样片")
        self.skip_trailer_cb.setChecked(True)
        self.skip_trailer_cb.setToolTip(
            "启用后，AI 会自动识别并跳过预告片(trailer)、样片(sample)、花絮等非正片内容\n"
            "这些文件不会出现在最终报告中"
        )
        row1.addWidget(self.skip_trailer_cb)
        row1.addStretch()
        ai_layout.addLayout(row1)
        
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("提示词："))
        self.ai_hint_edit = QLineEdit()
        self.ai_hint_edit.setPlaceholderText('可选，如"这是动漫"、"这是日剧"...')
        row2.addWidget(self.ai_hint_edit)
        ai_layout.addLayout(row2)
        
        # 标签管理区域
        tags_label = QLabel("分类标签：")
        ai_layout.addWidget(tags_label)
        
        # 标签容器（流式布局）
        self.tags_widget = QWidget()
        self.tags_flow = FlowLayout(self.tags_widget, margin=2, spacing=4)
        self.tags_widget.setLayout(self.tags_flow)
        self.tags_widget.setMinimumHeight(30)
        ai_layout.addWidget(self.tags_widget)
        
        # 标签操作按钮
        tags_btn_row = QHBoxLayout()
        self.new_tag_input = QLineEdit()
        self.new_tag_input.setPlaceholderText("添加标签...")
        self.new_tag_input.setMaximumWidth(120)
        self.new_tag_input.returnPressed.connect(self._add_tag)
        tags_btn_row.addWidget(self.new_tag_input)
        
        add_tag_btn = QPushButton("增加")
        add_tag_btn.setFixedWidth(50)
        add_tag_btn.setAutoDefault(False)  # 防止回车键触发其他按钮
        add_tag_btn.setDefault(False)
        add_tag_btn.setToolTip("添加标签")
        add_tag_btn.clicked.connect(self._add_tag)
        tags_btn_row.addWidget(add_tag_btn)
        
        restore_tags_btn = QPushButton("恢复默认")
        restore_tags_btn.setFixedWidth(70)
        restore_tags_btn.setAutoDefault(False)
        restore_tags_btn.setDefault(False)
        restore_tags_btn.clicked.connect(self._restore_default_tags)
        tags_btn_row.addWidget(restore_tags_btn)
        tags_btn_row.addStretch()
        ai_layout.addLayout(tags_btn_row)
        
        config_layout.addWidget(ai_group)
        
        # 4. 输出选项
        output_group = QGroupBox("4. 输出选项")
        output_layout = QVBoxLayout(output_group)
        
        row1 = QHBoxLayout()
        self.save_tags_cb = QCheckBox("保存标签到数据库")
        self.save_tags_cb.setChecked(True)
        self.gen_report_cb = QCheckBox("生成整理报告")
        self.gen_report_cb.setChecked(True)
        row1.addWidget(self.save_tags_cb)
        row1.addWidget(self.gen_report_cb)
        row1.addStretch()
        output_layout.addLayout(row1)
        
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("报告格式："))
        self.report_format_combo = QComboBox()
        self.report_format_combo.addItems(["Markdown (.md)", "HTML (.html)"])
        row2.addWidget(self.report_format_combo)
        row2.addStretch()
        output_layout.addLayout(row2)
        
        config_layout.addWidget(output_group)
        
        splitter.addWidget(config_widget)
        
        # 下半部分：进度区
        progress_widget = QWidget()
        progress_layout = QVBoxLayout(progress_widget)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        
        progress_group = QGroupBox("进度")
        pg_layout = QVBoxLayout(progress_group)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        pg_layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("就绪")
        pg_layout.addWidget(self.status_label)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        self.log_text.setFont(QFont("Consolas", 9))
        pg_layout.addWidget(self.log_text)
        
        progress_layout.addWidget(progress_group)
        splitter.addWidget(progress_widget)
        
        layout.addWidget(splitter)
        
        # 底部按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.start_btn = QPushButton("开始整理")
        self.start_btn.setMinimumWidth(120)
        self.start_btn.setAutoDefault(False)
        self.start_btn.setDefault(False)
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setAutoDefault(False)
        self.cancel_btn.setDefault(False)
        self.close_btn = QPushButton("关闭")
        self.close_btn.setAutoDefault(False)
        self.close_btn.setDefault(False)
        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.close_btn)
        layout.addLayout(btn_layout)
        
        # 连接信号
        self.add_dir_btn.clicked.connect(self._on_add_dir)
        self.remove_dir_btn.clicked.connect(self._on_remove_dir)
        self.add_indexed_btn.clicked.connect(self._on_add_indexed)
        self.start_btn.clicked.connect(self._on_start)
        self.cancel_btn.clicked.connect(self._on_cancel)
        self.close_btn.clicked.connect(self.close)
    
    def _on_add_dir(self):
        """添加目录"""
        path = QFileDialog.getExistingDirectory(self, "选择目录")
        if path:
            # 检查是否已添加
            for i in range(self.dir_list.count()):
                if self.dir_list.item(i).text() == path:
                    return
            self.dir_list.addItem(path)
    
    def _on_remove_dir(self):
        """移除选中目录"""
        current = self.dir_list.currentRow()
        if current >= 0:
            self.dir_list.takeItem(current)
    
    def _on_add_indexed(self):
        """从已索引目录中选择"""
        if not self.db:
            QMessageBox.warning(self, "警告", "数据库未初始化")
            return
        
        # 获取所有目录
        all_dirs = self.db.get_all_directories()
        if not all_dirs:
            QMessageBox.information(self, "提示", "没有已索引的目录")
            return
        
        # 弹出选择对话框
        from PySide6.QtWidgets import QInputDialog
        item, ok = QInputDialog.getItem(
            self, "选择目录", 
            "从已索引目录中选择\uff1a",
            all_dirs, 0, False
        )
        
        if ok and item:
            # 检查是否已添加
            for i in range(self.dir_list.count()):
                if self.dir_list.item(i).text() == item:
                    QMessageBox.information(self, "提示", "该目录已添加")
                    return
            self.dir_list.addItem(item)
    
    def _on_start(self):
        """开始整理"""
        # 收集目录
        directories = []
        for i in range(self.dir_list.count()):
            directories.append(self.dir_list.item(i).text())
        
        if not directories:
            QMessageBox.warning(self, "警告", "请至少添加一个目录")
            return
        
        # 收集选项
        options = {
            'min_size_mb': self.min_size_spin.value() if self.skip_small_cb.isChecked() else 0,
            'detect_disc': self.detect_disc_cb.isChecked(),
            'batch_size': self.batch_size_spin.value(),
            'ai_hint': self.ai_hint_edit.text().strip(),
            'skip_trailers': self.skip_trailer_cb.isChecked(),
            'save_tags': self.save_tags_cb.isChecked(),
            'gen_report': self.gen_report_cb.isChecked(),
        }
        
        # 选择报告保存路径
        if options['gen_report']:
            ext = ".md" if self.report_format_combo.currentIndex() == 0 else ".html"
            path, _ = QFileDialog.getSaveFileName(
                self, "保存报告", f"media_report{ext}",
                f"{'Markdown' if ext == '.md' else 'HTML'} (*{ext})"
            )
            if not path:
                return
            options['report_path'] = path
        
        # 禁用控件
        self.start_btn.setEnabled(False)
        self.log_text.clear()
        
        # 启动工作线程
        self.worker = ScanWorker(directories, options, self.db)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.error.connect(self._on_error)
        self.worker.start()
    
    def _on_cancel(self):
        """取消操作"""
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.log_text.append("正在取消...")
    
    def _on_progress(self, current: int, total: int, message: str):
        """更新进度"""
        if total > 0:
            self.progress_bar.setValue(int(current / total * 100))
        self.status_label.setText(message)
        self.log_text.append(message)
    
    def _on_finished(self, results: list, report_path: str):
        """处理完成"""
        self.results = results
        self.start_btn.setEnabled(True)
        self.progress_bar.setValue(100)
        
        # 动态统计各类型数量（支持任意自定义标签）
        type_counts = {}
        skipped_count = 0
        for r in results:
            # 跳过的文件单独统计
            if getattr(r, 'skip', False):
                skipped_count += 1
                continue
            t = r.media_type or "unknown"
            type_counts[t] = type_counts.get(t, 0) + 1
        
        msg = f"整理完成！共 {len(results)} 个文件\n"
        stats_parts = []
        for t, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            # 直接使用类型名，首字母大写处理
            display_name = t.upper() if t.lower() in ('nsfw', 'av', 'nsfe') else t.title()
            stats_parts.append(f"{display_name}: {count}")
        if skipped_count > 0:
            stats_parts.append(f"跳过: {skipped_count}")
        msg += ", ".join(stats_parts)
        
        if report_path:
            msg += f"\n\n报告已保存到:\n{report_path}"
        
        self.status_label.setText("完成")
        self.log_text.append(msg)
        
        QMessageBox.information(self, "完成", msg)
        
        # 通知主窗口刷新数据
        self.scan_finished.emit()
    
    def _on_error(self, error: str):
        """处理错误"""
        self.start_btn.setEnabled(True)
        self.status_label.setText("错误")
        self.log_text.append(f"错误: {error}")
        QMessageBox.critical(self, "错误", error)
    
    # ====================
    # 标签管理方法
    # ====================
    
    def _create_tag_chip(self, tag_name: str) -> QFrame:
        """创建一个小胶囊样式的标签"""
        chip = QFrame()
        chip.setStyleSheet("""
            QFrame {
                background-color: #f0f0f0;
                border: 1px solid #ddd;
                border-radius: 10px;
                padding: 0px;
            }
            QFrame:hover {
                background-color: #e0e0e0;
            }
        """)
        
        layout = QHBoxLayout(chip)
        layout.setContentsMargins(8, 2, 4, 2)
        layout.setSpacing(2)
        
        # 标签文字
        label = QLabel(tag_name)
        label.setStyleSheet("font-size: 11px; color: #333; border: none; background: transparent;")
        layout.addWidget(label)
        
        # 删除按钮
        del_btn = QPushButton("×")
        del_btn.setFixedSize(14, 14)
        del_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #888;
                border: none;
                font-size: 12px;
                padding: 0px;
            }
            QPushButton:hover {
                color: #d32f2f;
            }
        """)
        del_btn.clicked.connect(lambda: self._remove_tag(tag_name))
        layout.addWidget(del_btn)
        
        return chip
    
    def _load_tags(self):
        """从配置加载标签"""
        tags = config.get("ai", "media_types", default=None)
        if tags is None:
            self._current_tags = DEFAULT_TAGS.copy()
        else:
            self._current_tags = list(tags)
        self._refresh_tags_display()
    
    def _save_tags(self):
        """保存标签到配置"""
        config.set("ai", "media_types", value=self._current_tags)
        config.save()
    
    def _refresh_tags_display(self):
        """刷新标签显示"""
        # 清空现有标签 - 使用同步删除避免竞态条件
        while self.tags_flow.count():
            item = self.tags_flow.takeAt(0)
            if item and item.widget():
                widget = item.widget()
                widget.setParent(None)  # 同步移除
                widget.deleteLater()    # 延迟销毁
        
        # 确保布局更新
        self.tags_flow.invalidate()
        
        # 添加标签胶囊
        for tag in self._current_tags:
            chip = self._create_tag_chip(tag)
            self.tags_flow.addWidget(chip)
        
        self.tags_widget.updateGeometry()
        self.tags_widget.update()
    
    def _add_tag(self):
        """添加新标签"""
        tag_name = self.new_tag_input.text().strip()
        if not tag_name:
            return
        
        if tag_name in self._current_tags:
            self.new_tag_input.clear()
            return
        
        self._current_tags.append(tag_name)
        self._save_tags()
        self._refresh_tags_display()
        self.new_tag_input.clear()
    
    def _remove_tag(self, tag_name: str):
        """删除标签"""
        if tag_name in self._current_tags:
            self._current_tags.remove(tag_name)
            self._save_tags()
            self._refresh_tags_display()
    
    def _restore_default_tags(self):
        """恢复默认标签"""
        self._current_tags = DEFAULT_TAGS.copy()
        self._save_tags()
        self._refresh_tags_display()
