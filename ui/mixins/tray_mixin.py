# -*- coding: utf-8 -*-
"""
TrayMixin - 系统托盘功能
"""
from PySide6.QtWidgets import QSystemTrayIcon, QApplication

from config import config


def resource_path(relative_path):
    """获取资源绝对路径（支持 PyInstaller 打包）"""
    import sys
    import os
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


class TrayMixin:
    """系统托盘功能 Mixin"""
    
    def _init_tray_icon(self):
        """初始化系统托盘图标"""
        from ui.tray_icon import StatusTrayIcon
        
        icon_path = resource_path("logo.png")
        self._tray_icon = StatusTrayIcon(icon_path, self)
        
        # 连接信号
        self._tray_icon.show_window_requested.connect(self._show_from_tray)
        self._tray_icon.exit_requested.connect(self._exit_from_tray)
        
        # 设置初始状态
        self._tray_icon.set_status('disabled')
        self._tray_icon.update_tooltip("目录监控: 未启用")
        
        # 显示托盘图标
        self._tray_icon.show()
    
    def _show_from_tray(self):
        """从托盘恢复窗口"""
        self.showNormal()
        self.activateWindow()
        self.raise_()
    
    def _exit_from_tray(self):
        """从托盘退出程序"""
        self._force_quit = True
        self.close()
    
    def _update_tray_status(self, status_type: str, message: str):
        """更新托盘图标状态"""
        if self._tray_icon:
            self._tray_icon.set_status(status_type)
            self._tray_icon.update_tooltip(message)
    
    def _minimize_to_tray(self):
        """最小化到托盘"""
        self.hide()
        if self._tray_icon:
            self._tray_icon.showMessage(
                "FileRecorder",
                "程序已最小化到系统托盘，双击图标可恢复窗口",
                QSystemTrayIcon.Information,
                2000
            )
    
    def _do_quit(self):
        """执行退出"""
        # 停止扫描线程
        if self.scanner_thread and self.scanner_thread.isRunning():
            self.scanner_thread.cancel()
            self.scanner_thread.wait(2000)
        
        # 停止监控
        if self._watcher_manager:
            self._watcher_manager.stop()
        
        # 隐藏托盘图标
        if self._tray_icon:
            self._tray_icon.hide()
        
        QApplication.quit()
    
    def _handle_close_event(self, event):
        """处理关闭事件（由 MainWindow.closeEvent 调用）"""
        # 保存窗口尺寸
        if config.get("ui", "remember_window_size"):
            config.set("ui", "window_width", value=self.width())
            config.set("ui", "window_height", value=self.height())
            config.save()
        
        # 如果是强制退出，直接关闭
        if self._force_quit:
            self._do_quit()
            event.accept()
            return True
        
        # 检查关闭行为设置
        close_to_tray = config.get("ui", "close_to_tray")
        remembered = config.get("ui", "close_behavior_remembered", default=False)
        
        if remembered and close_to_tray is not None:
            # 已记住选择
            if close_to_tray:
                self._minimize_to_tray()
                event.ignore()
            else:
                self._do_quit()
                event.accept()
        else:
            # 未记住，显示询问对话框
            from ui.close_dialog import CloseConfirmDialog
            dialog = CloseConfirmDialog(self)
            if dialog.exec():
                # 保存选择
                if dialog.remember:
                    config.set("ui", "close_to_tray", value=dialog.close_to_tray)
                    config.set("ui", "close_behavior_remembered", value=True)
                    config.save()
                
                if dialog.close_to_tray:
                    self._minimize_to_tray()
                    event.ignore()
                else:
                    self._do_quit()
                    event.accept()
            else:
                # 取消关闭
                event.ignore()
        
        return False  # 表示事件已处理
