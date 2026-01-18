# -*- coding: utf-8 -*-
"""
FolderTreeMixin - 目录树功能
"""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTreeWidgetItem, QMenu, QMessageBox, QApplication


class FolderTreeMixin:
    """目录树功能 Mixin"""
    
    def _build_folder_tree(self):
        """构建目录树（延迟加载模式）
        
        只加载扫描源目录作为顶级项目，子目录在展开时动态加载
        """
        self.folder_tree.clear()
        
        # 连接展开事件（使用标志位避免重复连接/断开警告）
        if hasattr(self, '_tree_expanded_connected') and self._tree_expanded_connected:
            self.folder_tree.itemExpanded.disconnect(self._on_tree_item_expanded)
        self.folder_tree.itemExpanded.connect(self._on_tree_item_expanded)
        self._tree_expanded_connected = True

        
        folders = self.db.get_folder_tree()  # 获取所有扫描源
        
        # 解析路径为顶级部分
        top_level_items = {}  # key -> item
        
        for folder in folders:
            if not folder:
                continue
            
            # 统一路径分隔符
            folder = folder.replace('/', '\\')
            
            # 获取顶级部分（盘符或网络服务器）
            if folder.startswith('\\\\'):
                # 网络路径：取服务器名
                parts = folder.lstrip('\\').split('\\')
                top_key = '\\\\' + parts[0] if parts else folder
            else:
                # 本地路径：取盘符
                top_key = str(Path(folder).parts[0]) if Path(folder).parts else folder
            
            # 创建顶级项目（如果不存在）
            if top_key not in top_level_items:
                item = QTreeWidgetItem([top_key])
                item.setData(0, Qt.UserRole, top_key)
                item.setData(0, Qt.UserRole + 1, False)  # 标记未加载子目录
                item.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)  # 显示展开箭头
                top_level_items[top_key] = item
            
            # 添加扫描源作为子项
            if folder != top_key:
                parent_item = top_level_items[top_key]
                # 提取相对路径部分
                if folder.startswith('\\\\'):
                    parts = folder.lstrip('\\').split('\\')
                    child_name = '\\'.join(parts[1:]) if len(parts) > 1 else ''
                else:
                    parts = list(Path(folder).parts)
                    child_name = '\\'.join(parts[1:]) if len(parts) > 1 else ''
                
                # 跳过空名称
                if not child_name:
                    continue
                
                child_item = QTreeWidgetItem([child_name])
                child_item.setData(0, Qt.UserRole, folder)
                child_item.setData(0, Qt.UserRole + 1, False)  # 未加载
                child_item.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)
                parent_item.addChild(child_item)
        
        # 排序：本地路径在前，网络路径在后
        sorted_items = sorted(top_level_items.items(), 
                            key=lambda x: (1 if x[0].startswith('\\\\') else 0, x[0]))
        
        for key, item in sorted_items:
            self.folder_tree.addTopLevelItem(item)
        
        # 自动展开顶级目录，预加载一级子目录
        for key, item in sorted_items:
            item.setExpanded(True)  # 展开顶级目录，触发子目录加载
    
    def _on_tree_item_expanded(self, item: QTreeWidgetItem):
        """目录树项目展开时动态加载子目录"""
        # 检查是否已加载
        is_loaded = item.data(0, Qt.UserRole + 1)
        if is_loaded:
            return
        
        folder_path = item.data(0, Qt.UserRole)
        if not folder_path:
            return
        
        # 标记为已加载
        item.setData(0, Qt.UserRole + 1, True)
        
        # 获取该目录下的子目录
        subdirs = self._get_subdirectories(folder_path)
        
        for subdir in subdirs:
            # 检查是否已存在
            exists = False
            for i in range(item.childCount()):
                if item.child(i).data(0, Qt.UserRole) == subdir['path']:
                    exists = True
                    break
            
            if not exists:
                child_item = QTreeWidgetItem([subdir['name']])
                child_item.setData(0, Qt.UserRole, subdir['path'])
                child_item.setData(0, Qt.UserRole + 1, False)
                if subdir['has_children']:
                    child_item.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)
                item.addChild(child_item)
    
    def _get_subdirectories(self, parent_path: str) -> list:
        """获取指定路径下的直接子目录（使用数据库优化查询）"""
        # 直接调用数据库层的高效查询方法
        return self.db.get_direct_subdirs(parent_path)

    
    def _on_folder_clicked(self, item: QTreeWidgetItem, column: int):
        """目录树项目点击处理"""
        folder_path = item.data(0, Qt.UserRole)
        if folder_path:
            self._navigate_to(folder_path)
    
    def _get_expanded_paths(self) -> set:
        """获取当前展开的目录路径集合"""
        expanded = set()
        
        def collect_expanded(item):
            if item.isExpanded():
                path = item.data(0, Qt.UserRole)
                if path:
                    expanded.add(path)
            for i in range(item.childCount()):
                collect_expanded(item.child(i))
        
        for i in range(self.folder_tree.topLevelItemCount()):
            collect_expanded(self.folder_tree.topLevelItem(i))
        
        return expanded
    
    def _restore_expanded_paths(self, expanded_paths: set):
        """恢复目录展开状态"""
        def restore_expanded(item):
            path = item.data(0, Qt.UserRole)
            if path and path in expanded_paths:
                item.setExpanded(True)
            for i in range(item.childCount()):
                restore_expanded(item.child(i))
        
        for i in range(self.folder_tree.topLevelItemCount()):
            restore_expanded(self.folder_tree.topLevelItem(i))
            
    def _select_tree_item(self, path: str, expand: bool = True):
        """选中目录树中的指定路径（递归查找）
        
        Args:
            path: 目标路径
            expand: 是否强制展开父节点以显示目标。False则仅在父节点已展开时继续查找。
        """
        path = path.replace('/', '\\').rstrip('\\').lower()
        
        def find_and_select(item):
            item_path = item.data(0, Qt.UserRole)
            if item_path:
                item_path = item_path.replace('/', '\\').rstrip('\\').lower()
                if item_path == path:
                    self.folder_tree.setCurrentItem(item)
                    # 确保可视
                    self.folder_tree.scrollToItem(item)
                    return True
            
            # 如果目标路径以当前项路径开头，则展开并继续查找
            if path.startswith(item_path + '\\'):
                # 如果不强制展开且当前未展开，则停止查找（尊重用户状态）
                if not expand and not item.isExpanded():
                    return False

                # 确保已加载子节点
                if not item.data(0, Qt.UserRole + 1):  # is_loaded
                    self._on_tree_item_expanded(item)
                
                item.setExpanded(True)
                # 处理异步加载或UI更新延迟，虽然 _on_tree_item_expanded 是同步的
                QApplication.processEvents()
                
                for i in range(item.childCount()):
                    child = item.child(i)
                    if child and find_and_select(child):
                        return True
            return False
        
        try:
            for i in range(self.folder_tree.topLevelItemCount()):
                top_item = self.folder_tree.topLevelItem(i)
                if top_item and find_and_select(top_item):
                    break
        except RuntimeError:
            # Qt 对象可能在刷新过程中被删除，忽略此错误
            pass
    
    def _show_folder_tree_menu(self, pos):
        """显示目录树右键菜单"""
        item = self.folder_tree.itemAt(pos)
        if not item:
            return
        
        folder_path = item.data(0, Qt.UserRole)
        if not folder_path:
            return
        
        menu = QMenu(self)
        
        # 在浏览器中导航
        nav_action = menu.addAction("📂 在右侧浏览")
        nav_action.triggered.connect(lambda: self._navigate_to(folder_path))
        
        # 在资源管理器中打开
        open_action = menu.addAction("📁 在资源管理器中打开")
        open_action.triggered.connect(lambda: self._open_folder_in_explorer(folder_path))
        
        menu.addSeparator()
        
        # 删除该目录的索引
        delete_action = menu.addAction("🗑️ 删除此目录索引")
        delete_action.triggered.connect(lambda: self._delete_folder_index(folder_path))
        
        menu.exec_(self.folder_tree.viewport().mapToGlobal(pos))
    
    def _delete_folder_index(self, folder_path: str):
        """删除指定目录的所有索引记录"""
        from watcher.config import WatcherConfig
        
        # 检查是否被监控
        watcher_config = WatcherConfig(self.db)
        monitored_folder = watcher_config.is_path_monitored(folder_path)
        
        if monitored_folder:
            # 被监控中，显示保护对话框
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("监控保护")
            msg_box.setIcon(QMessageBox.Warning)
            msg_box.setText(f"该目录正在被监控：\n\n{monitored_folder.path}")
            msg_box.setInformativeText("请选择操作：")
            
            # 添加按钮
            remove_monitor_btn = msg_box.addButton("去除监控", QMessageBox.ActionRole)
            remove_both_btn = msg_box.addButton("去除并删除记录", QMessageBox.ActionRole)
            cancel_btn = msg_box.addButton("取消", QMessageBox.RejectRole)
            
            msg_box.setDefaultButton(cancel_btn)
            msg_box.exec()
            
            clicked_btn = msg_box.clickedButton()
            
            if clicked_btn == cancel_btn:
                return
            elif clicked_btn == remove_monitor_btn:
                # 只移除监控，不删除索引
                watcher_config.remove_folder(monitored_folder.id)
                QMessageBox.information(
                    self, "监控已移除",
                    f"已移除对该目录的监控。\n如需删除索引记录，请再次执行删除操作。"
                )
                # 通知监控管理器更新
                if self._watcher_manager:
                    self._watcher_manager.restart()
                return
            elif clicked_btn == remove_both_btn:
                # 移除监控并继续删除索引
                watcher_config.remove_folder(monitored_folder.id)
                if self._watcher_manager:
                    self._watcher_manager.restart()
                # 继续执行删除索引
        else:
            # 未被监控，正常确认删除
            reply = QMessageBox.question(
                self, "确认删除",
                f"确定要删除以下目录的所有索引记录吗？\n\n{folder_path}\n\n此操作不会删除实际文件。",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply != QMessageBox.Yes:
                return
        
        # 执行删除
        self.statusbar.showMessage(f"正在删除 {folder_path} 的索引...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # 不确定模式
        
        # 强制更新UI
        QApplication.processEvents()
        
        # 删除该路径下的所有文件记录
        deleted_count = self.db.clear_source(folder_path)
        
        # 隐藏进度条
        self.progress_bar.setVisible(False)
        
        # 保存当前展开状态
        expanded_paths = self._get_expanded_paths()
        
        # 刷新数据
        self._refresh_data()
        
        # 恢复展开状态
        self._restore_expanded_paths(expanded_paths)
        
        self.statusbar.showMessage(f"已删除 {deleted_count} 条索引记录", 5000)
        QMessageBox.information(self, "删除完成", f"已删除 {deleted_count} 条索引记录")
