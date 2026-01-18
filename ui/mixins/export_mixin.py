# -*- coding: utf-8 -*-
"""
ExportMixin - 导出功能
"""
from PySide6.QtCore import Slot
from PySide6.QtWidgets import QMessageBox, QFileDialog


class ExportMixin:
    """导出功能 Mixin"""
    
    @Slot()
    def _on_ai_organize(self):
        """AI 媒体库整理"""
        from ui.media_wizard import MediaWizardDialog
        
        dialog = MediaWizardDialog(self, self.db)
        # 连接信号，扫描完成后刷新主窗口数据
        dialog.scan_finished.connect(self._refresh_data)
        dialog.exec_()
    
    @Slot()
    def _on_export_csv(self):
        """导出CSV"""
        import csv
        from datetime import datetime
        from PySide6.QtWidgets import QApplication
        from ui.export_dialog import ExportProgressDialog
        
        # 检查数据库是否有数据
        stats = self.db.get_stats()
        if stats['total_files'] == 0:
            QMessageBox.warning(self, "提示", "数据库为空，没有可导出的数据")
            return
        
        path, _ = QFileDialog.getSaveFileName(
            self, "导出CSV文件",
            "fileindex_export.csv",
            "CSV文件 (*.csv)"
        )
        
        if not path:
            return
        
        # 创建导出进度对话框
        progress = ExportProgressDialog("导出 CSV", self)
        progress.show()
        QApplication.processEvents()
        
        try:
            # 使用数据库管理器的上下文管理器
            with self.db._get_connection() as conn:
                # 先获取总数用于进度显示
                total_count = conn.execute("SELECT COUNT(*) FROM files WHERE is_dir = 0").fetchone()[0]
                
                cursor = conn.execute("""
                    SELECT f.filename as name, f.extension, fo.path, f.size_bytes, f.ctime, f.mtime, 
                           f.ai_category, f.ai_tags
                    FROM files f
                    JOIN folders fo ON f.folder_id = fo.id
                    WHERE f.is_dir = 0
                    ORDER BY fo.path, f.filename
                """)
                
                with open(path, 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f)
                    writer.writerow(['文件名', '类型', '完整路径', '所在目录', '大小', '创建时间', '修改时间', 'AI分类', 'AI标签'])
                    
                    count = 0
                    for row in cursor:
                        if progress.is_cancelled():
                            break
                        
                        name, ext, folder, size, ctime, mtime, ai_cat, ai_tags = row
                        
                        # 格式化大小
                        size = size or 0
                        if size < 1024:
                            size_str = f"{size} B"
                        elif size < 1024 * 1024:
                            size_str = f"{size / 1024:.1f} KB"
                        elif size < 1024 * 1024 * 1024:
                            size_str = f"{size / (1024 * 1024):.1f} MB"
                        else:
                            size_str = f"{size / (1024 * 1024 * 1024):.2f} GB"
                        
                        # 格式化时间
                        ctime_str = datetime.fromtimestamp(ctime).strftime('%Y-%m-%d %H:%M') if ctime else ''
                        mtime_str = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M') if mtime else ''
                        
                        # 完整路径
                        full_path = f"{folder}\\{name}" if folder else name
                        
                        writer.writerow([
                            name, ext or '', full_path, folder or '',
                            size_str, ctime_str, mtime_str,
                            ai_cat or '', ai_tags or ''
                        ])
                        count += 1
                        
                        # 每1000条更新一次进度
                        if count % 1000 == 0:
                            progress.update_progress(count, total_count, f"已导出 {count} 个文件")
                            QApplication.processEvents()
            
            progress.close()
            
            if not progress.is_cancelled():
                QMessageBox.information(self, "成功", f"已导出 {count} 条文件记录到:\n{path}\n\n注：仅导出文件，不含文件夹")
                
        except Exception as e:
            progress.close()
            QMessageBox.critical(self, "错误", f"导出失败: {e}")
    
    @Slot()
    def _on_export_html(self):
        """导出为 HTML 文件"""
        from PySide6.QtWidgets import QApplication
        from export.html_exporter import HtmlExporter
        from ui.export_dialog import ExportProgressDialog
        
        # 检查是否有数据
        stats = self.db.get_stats()
        if stats['total_files'] == 0:
            QMessageBox.warning(self, "提示", "数据库为空，没有可导出的数据")
            return
        
        # 选择保存路径
        path, _ = QFileDialog.getSaveFileName(
            self, "导出HTML文件",
            "fileindex_export.html",
            "HTML文件 (*.html)"
        )
        
        if not path:
            return
        
        # 创建导出进度对话框
        progress = ExportProgressDialog("导出 HTML", self)
        progress.show()
        QApplication.processEvents()
        
        try:
            def update_progress(current, total, msg):
                if progress.is_cancelled():
                    return
                progress.update_progress(current, total, msg)
                QApplication.processEvents()
            
            # 执行导出
            exporter = HtmlExporter(self.db)
            success = exporter.export(path, update_progress)
            
            # 关闭进度对话框
            progress.close()
            
            if success:
                # 询问是否打开
                reply = QMessageBox.question(
                    self, "导出成功",
                    f"已导出 {stats['total_files']} 个文件到:\n{path}\n\n是否立即打开？",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes
                )
                if reply == QMessageBox.Yes:
                    import os
                    os.startfile(path)
            else:
                QMessageBox.critical(self, "错误", "导出失败，请检查控制台输出")
                
        except Exception as e:
            progress.close()
            QMessageBox.critical(self, "错误", f"导出失败: {e}")
