# -*- coding: utf-8 -*-
"""
ScannerMixin - 扫描功能
"""
from PySide6.QtCore import Slot
from PySide6.QtWidgets import QMessageBox

from config import config
from scanner.file_scanner import FileScanner, ScannerThread
from logger import get_logger

logger = get_logger("ui")


class ScannerMixin:
    """扫描功能 Mixin"""
    
    @Slot()
    def _on_start_scan(self):
        """开始扫描 - 打开多文件夹扫描对话框"""
        from ui.scan_dialog import MultiFolderScanDialog
        dialog = MultiFolderScanDialog(self)
        dialog.scan_requested.connect(self._on_multi_scan_requested)
        dialog.exec_()
    
    @Slot(list)
    def _on_multi_scan_requested(self, paths: list):
        """处理多文件夹扫描请求"""
        if not paths:
            return
        
        # 重置累计统计
        self._scan_total_files = 0
        self._scan_total_folders = 0
        self._scan_total_errors = 0
        self._scan_paths_count = len(paths)
        
        # 第一个路径用 _start_scan 创建对话框
        first_path = paths[0]
        # 剩余的加入队列
        self.scan_queue = paths[1:] if len(paths) > 1 else []
        # 启动第一个扫描（会创建进度对话框）
        self._start_scan(first_path)
    
    def _scan_next_in_queue(self):
        """扫描队列中的下一个路径"""
        if not self.scan_queue:
            # 队列完成
            self.statusbar.showMessage("所有路径扫描完成")
            return
        
        path = self.scan_queue.pop(0)
        self.current_scan_path = path
        
        # 复用现有对话框，只更新标题
        if self.progress_dialog:
            remaining = len(self.scan_queue)
            self.progress_dialog.set_title(f"正在扫描: {path}", "🔍")
        
        # 创建新的扫描器和线程
        scanner = FileScanner(
            db=self.db,
            batch_size=config.get("scanner", "batch_size", default=1000),
            ignore_patterns=config.get("scanner", "ignore_patterns"),
            timeout=config.get("scanner", "timeout_seconds", default=5)
        )
        
        self.scanner_thread = ScannerThread(scanner, path)
        self.scanner_thread.progress.connect(self._on_scan_progress)
        if self.progress_dialog:
            self.scanner_thread.progress.connect(self.progress_dialog.update_progress)
        self.scanner_thread.finished.connect(self._on_scan_finished)
        self.scanner_thread.error.connect(self._on_scan_error)
        
        self.statusbar.showMessage("扫描中...")
        self.scanner_thread.start()
    
    def _start_scan(self, path: str):
        """开始扫描指定路径"""
        from ui.progress_dialog import ScanProgressDialog
        
        if self.scanner_thread and self.scanner_thread.isRunning():
            QMessageBox.warning(self, "提示", "扫描正在进行中...")
            return
        
        # 保存当前扫描路径
        self.current_scan_path = path
        
        # 初始化累计统计（仅在非队列模式下，即直接调用 _start_scan 时）
        if self._scan_paths_count == 0:
            self._scan_total_files = 0
            self._scan_total_folders = 0
            self._scan_total_errors = 0
            self._scan_paths_count = 1
        
        # 创建进度对话框
        self.progress_dialog = ScanProgressDialog("正在扫描", self)
        self.progress_dialog.set_title(f"正在扫描: {path}", "🔍")
        self.progress_dialog.stop_requested.connect(self._on_stop_scan)
        
        # 创建扫描器（传入db实现分批写入，清理旧数据由扫描器负责）
        scanner = FileScanner(
            db=self.db,
            batch_size=config.get("scanner", "batch_size", default=1000),
            ignore_patterns=config.get("scanner", "ignore_patterns"),
            timeout=config.get("scanner", "timeout_seconds", default=5)
        )
        
        self.scanner_thread = ScannerThread(scanner, path)
        self.scanner_thread.progress.connect(self._on_scan_progress)
        self.scanner_thread.progress.connect(self.progress_dialog.update_progress)
        self.scanner_thread.finished.connect(self._on_scan_finished)
        self.scanner_thread.error.connect(self._on_scan_error)
        
        # 更新工具栏状态（用户看不到，但保持逻辑一致）
        self.scan_action.setText("⏹️ 停止扫描")
        self.scan_action.triggered.disconnect()
        self.scan_action.triggered.connect(self._on_stop_scan)
        
        # 隐藏底部进度条（进度对话框已有进度条）
        self.progress_bar.setVisible(False)
        self.statusbar.showMessage("扫描中...")
        
        # 启动扫描并显示对话框
        self.scanner_thread.start()
        self.progress_dialog.show()
    
    @Slot()
    def _on_stop_scan(self):
        """停止扫描"""
        if self.scanner_thread:
            self.scanner_thread.cancel()
    
    @Slot(int, int, str)
    def _on_scan_progress(self, files: int, folders: int, filename: str):
        """扫描进度更新"""
        # 有进度对话框时不更新状态栏（避免重复信息）
        if not self.progress_dialog:
            self.statusbar.showMessage(f"已扫描 {files} 个文件, {folders} 个文件夹: {filename}")
    
    @Slot(dict)
    def _on_scan_finished(self, result: dict):
        """扫描完成"""
        # 注意：分批写入模式下，数据已在扫描过程中写入数据库，result['files']为空
        # 只有无db模式下才需要批量插入（兼容旧逻辑）
        if result['files']:
            batch_size = config.get("scanner", "batch_size", default=1000)
            files = result['files']
            for i in range(0, len(files), batch_size):
                self.db.batch_insert(files[i:i+batch_size])
        
        # 记录扫描错误
        scan_source = result.get('scan_source', '')
        for error in result.get('errors', []):
            if isinstance(error, dict):
                self.db.insert_scan_error(
                    error.get('path', ''),
                    error.get('error', '未知错误'),
                    scan_source
                )
        
        # 累计统计
        self._scan_total_files += result.get('file_count', 0)
        self._scan_total_folders += result.get('folder_count', 0)
        self._scan_total_errors += result.get('error_count', 0)
        
        # 检查是否还有队列
        remaining = len(self.scan_queue)
        
        if remaining > 0:
            # 还有待扫描项目，更新对话框并继续扫描
            completed = self._scan_paths_count - remaining
            if self.progress_dialog:
                self.progress_dialog.set_title(f"扫描进度 ({completed}/{self._scan_paths_count})", "📋")
            self.statusbar.showMessage(
                f"完成: {result['scan_source']} ({result['file_count']}个文件, {result['folder_count']}个文件夹) | 剩余 {remaining} 个路径"
            )
            self._scan_next_in_queue()
            return
        
        # 队列全部完成
        # 更新进度对话框 - 显示累计汇总
        if self.progress_dialog:
            if result['cancelled']:
                self.progress_dialog.set_cancelled()
            else:
                self.progress_dialog.set_finished(self._scan_total_files, self._scan_total_folders, self._scan_total_errors)
        
        # 恢复工具栏UI状态
        self.scan_action.setText("🔍 开始扫描")
        self.scan_action.triggered.disconnect()
        self.scan_action.triggered.connect(self._on_start_scan)
        
        self.progress_bar.setVisible(False)
        self.current_scan_path = None
        
        # 刷新显示并导航到扫描的目录
        self._refresh_data(navigate_to=result['scan_source'])
        
        # 获取最新统计
        stats = self.db.get_stats()
        
        # 更新状态栏 - 显示累计汇总
        if self._scan_paths_count > 1:
            msg = f"扫描完成！共扫描 {self._scan_paths_count} 个目录，{self._scan_total_files} 个文件，{self._scan_total_folders} 个文件夹，数据库共 {stats['total_files']} 条记录"
        else:
            msg = f"扫描完成！本次扫描到 {self._scan_total_files} 个文件，{self._scan_total_folders} 个文件夹，数据库共 {stats['total_files']} 条记录"
        if self._scan_total_errors > 0:
            msg += f"，{self._scan_total_errors} 个文件读取失败"
        if result['cancelled']:
            msg = "扫描已取消 | " + msg
        
        self.statusbar.showMessage(msg)
        
        # 更新错误计数
        self._update_error_count()
        
        # 扫描完成后自动更新查询优化器统计信息
        self.db.analyze_database()
        
        # 重置统计变量
        self._scan_paths_count = 0
    
    @Slot(str)
    def _on_scan_error(self, error: str):
        """扫描错误"""
        logger.warning(f"扫描错误: {error}")
    
    def _on_multi_scan_silent(self, paths: list):
        """静默模式多目录扫描（后台执行，不显示进度弹窗）"""
        logger.info(f"静默扫描: {paths}")
        
        # 使用与普通扫描相同的线程，但不显示进度对话框
        if self.scanner_thread and self.scanner_thread.isRunning():
            # 已有扫描在进行，将路径加入队列
            for path in paths:
                if path not in self.scan_queue:
                    self.scan_queue.append(path)
            logger.info(f"静默扫描已排队: {len(self.scan_queue)} 个待处理")
            return
        
        # 加入队列并开始扫描
        self.scan_queue = list(paths)
        self._scan_total_files = 0
        self._scan_total_folders = 0
        self._scan_total_errors = 0
        self._scan_paths_count = len(paths)
        
        # 标记为静默模式
        self._silent_scan_mode = True
        
        # 开始扫描第一个
        self._start_next_scan_silent()
    
    def _start_next_scan_silent(self):
        """静默模式开始下一个扫描"""
        if not self.scan_queue:
            # 扫描完成
            logger.info(f"静默扫描完成: {self._scan_total_files} 个文件, {self._scan_total_folders} 个文件夹")
            self._silent_scan_mode = False
            self.statusbar.showMessage(f"后台更新完成: {self._scan_total_files} 个文件, {self._scan_total_folders} 个文件夹", 5000)
            self._refresh_data()
            return
        
        path = self.scan_queue.pop(0)
        self.current_scan_path = path
        
        logger.info(f"静默扫描: {path}")
        self.statusbar.showMessage(f"后台更新: {path}...")
        
        # 创建扫描器
        scanner = FileScanner(
            db=self.db,
            timeout=5
        )
        
        self.scanner_thread = ScannerThread(scanner, path)
        self.scanner_thread.progress.connect(self._on_scan_progress)
        self.scanner_thread.finished.connect(self._on_silent_scan_finished)
        self.scanner_thread.error.connect(self._on_scan_error)
        self.scanner_thread.start()
    
    def _on_silent_scan_finished(self, result: dict):
        """静默扫描完成"""
        self._scan_total_files += result.get('file_count', 0)
        self._scan_total_folders += result.get('folder_count', 0)
        self._scan_total_errors += result.get('error_count', 0)
        
        logger.info(f"静默扫描路径完成: {result.get('scan_source')}")
        
        # 继续下一个
        self._start_next_scan_silent()
