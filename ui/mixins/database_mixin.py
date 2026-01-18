# -*- coding: utf-8 -*-
"""
DatabaseMixin - 数据库操作功能
"""
from PySide6.QtCore import Slot
from PySide6.QtWidgets import QMessageBox, QFileDialog

from config import config
from database.db_manager import DatabaseManager


class DatabaseMixin:
    """数据库操作功能 Mixin"""
    
    @Slot()
    def _on_optimize_db(self):
        """优化数据库（压缩和更新统计）"""
        reply = QMessageBox.question(
            self, "优化数据库",
            "优化将压缩数据库并更新统计信息，可能需要几秒钟。\n是否继续？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        
        if reply == QMessageBox.Yes:
            self.statusbar.showMessage("正在优化数据库...")
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)
            
            from PySide6.QtWidgets import QApplication
            QApplication.processEvents()
            
            try:
                result = self.db.optimize_database()
                
                self.progress_bar.setVisible(False)
                
                # 格式化大小
                def format_size(size):
                    for unit in ['B', 'KB', 'MB', 'GB']:
                        if size < 1024:
                            return f"{size:.1f} {unit}"
                        size /= 1024
                    return f"{size:.1f} TB"
                
                msg = f"优化完成！\n\n"
                msg += f"优化前: {format_size(result['size_before'])}\n"
                msg += f"优化后: {format_size(result['size_after'])}\n"
                msg += f"节省: {format_size(result['saved'])}"
                
                self.statusbar.showMessage("数据库优化完成", 5000)
                QMessageBox.information(self, "优化完成", msg)
            except Exception as e:
                self.progress_bar.setVisible(False)
                QMessageBox.critical(self, "优化失败", f"优化过程出错: {e}")
    
    @Slot()
    def _on_clear_index(self):
        """清除所有索引数据"""
        stats = self.db.get_stats()
        if stats['total_files'] == 0:
            QMessageBox.information(self, "提示", "数据库已经是空的")
            return
        
        reply = QMessageBox.warning(
            self, "确认清除",
            f"确定要清除所有索引数据吗？\n\n"
            f"当前共有 {stats['total_files']:,} 个文件记录。\n"
            f"此操作不可撤销！",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.statusbar.showMessage("正在清除索引...")
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)
            
            from PySide6.QtWidgets import QApplication
            QApplication.processEvents()
            
            try:
                # 获取所有扫描源并逐个清除
                sources = self.db.get_folder_tree()
                for source in sources:
                    self.db.clear_source(source)
                
                # 优化数据库回收空间
                self.db.optimize_database()
                
                self.progress_bar.setVisible(False)
                self.statusbar.showMessage("索引已清除", 5000)
                
                # 刷新界面
                self._refresh_data()
                self._update_stats()
                
                QMessageBox.information(self, "完成", "所有索引数据已清除")
            except Exception as e:
                self.progress_bar.setVisible(False)
                QMessageBox.critical(self, "错误", f"清除失败: {e}")
    
    @Slot()
    def _on_backup(self):
        """备份数据库"""
        import shutil
        from datetime import datetime
        
        # 检查是否有文件记录
        stats = self.db.get_stats()
        if stats['total_files'] == 0:
            QMessageBox.information(
                self, "无需备份",
                "当前文件记录为0，无需备份。"
            )
            return
        
        # 默认备份文件名包含时间戳
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"file_index_backup_{timestamp}.db"
        
        path, _ = QFileDialog.getSaveFileName(
            self, "保存备份文件",
            default_name,
            "SQLite数据库 (*.db);;所有文件 (*.*)"
        )
        
        if path:
            try:
                # 复制数据库文件
                shutil.copy2(str(config.database_path), path)
                QMessageBox.information(
                    self, "备份成功",
                    f"数据库已备份到:\n{path}\n\n共 {stats['total_files']} 条文件记录"
                )
            except Exception as e:
                QMessageBox.critical(self, "备份失败", f"无法备份数据库: {e}")
    
    @Slot()
    def _on_restore(self):
        """从备份恢复数据库"""
        import shutil
        
        reply = QMessageBox.warning(
            self, "确认恢复",
            "恢复操作将会覆盖当前的所有索引数据！\n\n确定要继续吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        path, _ = QFileDialog.getOpenFileName(
            self, "选择备份文件",
            "",
            "SQLite数据库 (*.db);;所有文件 (*.*)"
        )
        
        if path:
            try:
                # 关闭当前数据库连接（通过重新导入）
                # 复制备份文件到数据库位置
                shutil.copy2(path, str(config.database_path))
                
                # 重新初始化数据库连接
                self.db = DatabaseManager(config.database_path)
                
                # 刷新UI
                self._refresh_data()
                
                stats = self.db.get_stats()
                QMessageBox.information(
                    self, "恢复成功",
                    f"数据库已从备份恢复！\n\n共 {stats['total_files']} 条文件记录"
                )
            except Exception as e:
                QMessageBox.critical(self, "恢复失败", f"无法恢复数据库: {e}")
    
    @Slot()
    def _on_show_errors(self):
        """显示错误日志对话框"""
        from ui.error_log_dialog import ErrorLogDialog
        
        dialog = ErrorLogDialog(self.db, self)
        dialog.exec()
        
        # 刷新错误计数
        self._update_error_count()
    
    def _update_error_count(self):
        """更新错误计数显示"""
        count = self.db.get_error_count()
        if count > 0:
            self.error_action.setText(f"⚠️ 错误 ({count})")
        else:
            self.error_action.setText("⚠️ 错误 (0)")
    
    @Slot()
    def _on_settings(self):
        """打开设置对话框"""
        from ui.settings_dialog import SettingsDialog
        from ui.theme import theme_manager  # 延迟导入以避免循环依赖
        
        dialog = SettingsDialog(self)
        dialog.theme_changed.connect(theme_manager.set_mode)
        if dialog.exec_():
            config.save()
            self.statusbar.showMessage("设置已保存", 2000)
