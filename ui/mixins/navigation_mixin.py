# -*- coding: utf-8 -*-
"""
NavigationMixin - 导航功能
"""
import subprocess
from pathlib import Path

from PySide6.QtCore import Slot
from PySide6.QtWidgets import QMessageBox, QMenu


class NavigationMixin:
    """导航功能 Mixin"""
    
    @Slot()
    def _on_double_click(self, index):
        """双击事件 - 目录进入，文件打开位置"""
        if self.view_mode == 'browser':
            item = self.browser_model.get_item_at(index.row())
            if item.get('is_dir'):
                # 进入目录
                self._navigate_to(item.get('full_path', ''))
            else:
                # 打开文件位置
                self._open_file_location(item.get('full_path'))
        else:
            file_info = self.file_model.get_file_at(index.row())
            if file_info:
                self._open_file_location(file_info.get('full_path'))
    
    def _navigate_to(self, path: str):
        """导航到指定路径"""
        current_path = self.browser_model.get_current_path()
        
        # 如果不是通过历史导航，则记录历史
        if not self._history_navigating:
            if current_path:  # 只记录非空路径
                self._history_back.append(current_path)
            # 清空前进栈（新的导航会清除前进历史）
            self._history_forward.clear()
        
        self.view_mode = 'browser'
        self.file_table.setModel(self.browser_model)
        self.browser_model.navigate_to(path)
        self._update_nav_ui()
        self.view_toggle_btn.setText("📋 平铺视图")
        
        # 清除状态栏搜索结果提示
        self.statusbar.clearMessage()
    
    def _navigate_and_select(self, folder_path: str, filename: str):
        """导航到目录并选中指定文件"""
        # 先导航到目录
        self._navigate_to(folder_path)
        
        # 延迟选中文件（等待视图刷新）
        from PySide6.QtCore import QTimer
        def select_file():
            # 在当前视图中查找文件
            for row in range(self.browser_model.rowCount()):
                item = self.browser_model.get_item_at(row)
                if item and item.get('name', '') == filename:
                    # 选中该行
                    index = self.browser_model.index(row, 0)
                    self.file_table.setCurrentIndex(index)
                    self.file_table.scrollTo(index)
                    break
        
        QTimer.singleShot(100, select_file)
    
    def _update_nav_ui(self):
        """更新导航UI"""
        current_path = self.browser_model.get_current_path()
        
        # 更新后退按钮状态
        self.back_btn.setEnabled(len(self._history_back) > 0)
        
        # 更新前进按钮状态
        self.forward_btn.setEnabled(len(self._history_forward) > 0)
        
        if current_path:
            # 生成可点击的面包屑路径
            breadcrumb_html = self._build_breadcrumb_html(current_path)
            self.path_label.setText(breadcrumb_html)
        else:
            self.path_label.setText("当前位置: / (根目录)")
    
    def _build_breadcrumb_html(self, path: str) -> str:
        """构建面包屑HTML"""
        # 统一路径分隔符
        path = path.replace('/', '\\')
        
        # 处理网络路径和本地路径
        if path.startswith('\\\\'):
            # 网络路径：\\server\share\folder
            clean = path.lstrip('\\')
            parts = clean.split('\\')
            if len(parts) >= 1:
                parts = ['\\\\' + parts[0]] + parts[1:]
        else:
            # 本地路径
            parts = list(Path(path).parts)
        
        # 构建HTML链接
        html_parts = ["当前位置: "]
        current_path = ""
        
        for i, part in enumerate(parts):
            if i == 0:
                current_path = part
            else:
                current_path = current_path.rstrip('\\') + '\\' + part
            
            # 最后一个部分不是链接
            if i == len(parts) - 1:
                html_parts.append(f"<b>{part}</b>")
            else:
                # 转义路径用于URL
                escaped_path = current_path.replace('\\', '/')
                html_parts.append(f'<a href="{escaped_path}" style="color: #4a9eff; text-decoration: none;">{part}</a>')
                html_parts.append(" › ")
        
        return "".join(html_parts)
    
    @Slot(str)
    def _on_breadcrumb_click(self, link: str):
        """面包屑链接点击"""
        # 还原路径格式
        path = link.replace('/', '\\')
        self._navigate_to(path)
    
    @Slot(int)
    def _on_table_scroll(self, value: int):
        """表格滚动事件 - 预加载更多数据"""
        if self.view_mode != 'browser':
            return
        
        # 获取最后可见的行号
        scrollbar = self.file_table.verticalScrollBar()
        max_val = scrollbar.maximum()
        
        # 只在滚动到底部80%时才检查加载更多
        if max_val > 0 and value > max_val * 0.8:
            # 计算可见区域的最后一行
            visible_rect = self.file_table.viewport().rect()
            last_visible_index = self.file_table.indexAt(visible_rect.bottomLeft())
            if last_visible_index.isValid():
                self.browser_model.check_load_more(last_visible_index.row())
    
    @Slot()
    def _on_go_back(self):
        """后退 - 返回上一个浏览的位置"""
        if not self._history_back:
            return
        
        current_path = self.browser_model.get_current_path()
        
        # 当前路径加入前进栈
        if current_path:
            self._history_forward.append(current_path)
        
        # 从后退栈取出上一个位置
        previous_path = self._history_back.pop()
        
        # 标记为历史导航（避免重复记录）
        self._history_navigating = True
        self._navigate_to(previous_path)
        self._history_navigating = False
    
    @Slot()
    def _on_go_forward(self):
        """前进 - 返回下一个浏览的位置"""
        if not self._history_forward:
            return
        
        current_path = self.browser_model.get_current_path()
        
        # 当前路径加入后退栈
        if current_path:
            self._history_back.append(current_path)
        
        # 从前进栈取出下一个位置
        next_path = self._history_forward.pop()
        
        # 标记为历史导航
        self._history_navigating = True
        self._navigate_to(next_path)
        self._history_navigating = False
    
    @Slot()
    def _on_go_home(self):
        """回到当前路径对应的顶级索引目录"""
        current_path = self.browser_model.get_current_path()
        
        if current_path:
            # 找到当前路径对应的扫描源（顶级目录）
            folders = self.db.get_folder_tree()
            current_lower = current_path.lower().replace('/', '\\')
            
            for folder in folders:
                folder_lower = folder.lower().replace('/', '\\')
                if current_lower.startswith(folder_lower):
                    self._navigate_to(folder)
                    return
        
        # 如果没有找到对应的顶级目录，导航到第一个索引目录
        folders = self.db.get_folder_tree()
        if folders:
            self._navigate_to(folders[0])
    
    @Slot()
    def _on_toggle_view(self):
        """切换视图模式"""
        if self.view_mode == 'browser':
            # 切换到平铺视图
            self.view_mode = 'flat'
            self.file_table.setModel(self.file_model)
            self.view_toggle_btn.setText("📂 浏览视图")
            self.back_btn.setEnabled(False)
            self.path_label.setText("平铺视图 (显示所有文件)")
        else:
            # 切换到浏览视图 - 导航到第一个索引目录
            folders = self.db.get_folder_tree()
            first_folder = folders[0] if folders else ""
            self._navigate_to(first_folder)
    
    def _show_context_menu(self, pos):
        """显示右键菜单"""
        index = self.file_table.indexAt(pos)
        if not index.isValid():
            return
        
        # 根据视图模式获取项目信息
        if self.view_mode == 'browser':
            item = self.browser_model.get_item_at(index.row())
            if not item:
                return
            full_path = item.get('full_path', '')
            is_dir = item.get('is_dir', False)
            file_id = item.get('id')
        else:
            file_info = self.file_model.get_file_at(index.row())
            if not file_info:
                return
            full_path = file_info.get('full_path', '')
            is_dir = False
            file_id = file_info.get('id')
        
        menu = QMenu(self)
        
        if is_dir:
            enter_action = menu.addAction("📂 进入目录")
            enter_action.triggered.connect(lambda: self._navigate_to(full_path))
            
            open_action = menu.addAction("📁 在资源管理器中打开")
            open_action.triggered.connect(lambda: self._open_folder_in_explorer(full_path))
        else:
            # 在索引中打开（导航到文件所在目录并高亮选中）
            parent_folder = str(Path(full_path).parent) if full_path else ''
            filename = Path(full_path).name if full_path else ''
            if parent_folder:
                index_action = menu.addAction("在索引中打开")
                index_action.triggered.connect(
                    lambda checked=False, pf=parent_folder, fn=filename: 
                    self._navigate_and_select(pf, fn)
                )
            
            open_action = menu.addAction("打开所在位置")
            open_action.triggered.connect(lambda: self._open_file_location(full_path))
        
        copy_action = menu.addAction("复制路径")
        copy_action.triggered.connect(lambda: self._copy_to_clipboard(full_path))
        
        if not is_dir and file_id:
            menu.addSeparator()
            delete_action = menu.addAction("从索引中删除")
            delete_action.triggered.connect(lambda: self._delete_from_index(file_id))
        
        menu.exec_(self.file_table.viewport().mapToGlobal(pos))
    
    def _open_file_location(self, path: str):
        """打开文件所在位置"""
        if path:
            try:
                subprocess.run(['explorer', '/select,', path], check=False)
            except Exception as e:
                QMessageBox.warning(self, "错误", f"无法打开位置: {e}")
    
    def _open_folder_in_explorer(self, folder_path: str):
        """在资源管理器中打开文件夹"""
        if folder_path:
            try:
                subprocess.run(['explorer', folder_path], check=False)
            except Exception as e:
                QMessageBox.warning(self, "错误", f"无法打开文件夹: {e}")
    
    def _copy_to_clipboard(self, text: str):
        """复制到剪贴板"""
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(text)
        self.statusbar.showMessage("已复制到剪贴板", 2000)
    
    def _delete_from_index(self, file_id: int):
        """从索引中删除"""
        # TODO: 实现删除功能
        pass
