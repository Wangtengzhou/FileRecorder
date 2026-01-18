# -*- coding: utf-8 -*-
"""
UI Mixins Package
将 MainWindow 的功能拆分为多个 Mixin 类
"""

from ui.mixins.tray_mixin import TrayMixin
from ui.mixins.database_mixin import DatabaseMixin
from ui.mixins.export_mixin import ExportMixin
from ui.mixins.navigation_mixin import NavigationMixin
from ui.mixins.folder_tree_mixin import FolderTreeMixin
from ui.mixins.scanner_mixin import ScannerMixin
from ui.mixins.watcher_mixin import WatcherMixin

__all__ = [
    'TrayMixin',
    'DatabaseMixin', 
    'ExportMixin',
    'NavigationMixin',
    'FolderTreeMixin',
    'ScannerMixin',
    'WatcherMixin',
]
