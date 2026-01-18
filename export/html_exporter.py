"""
FileRecorder - 智能文件索引助手
https://github.com/Wangtengzhou/FileRecorder

HTML 导出模块 - 生成可离线浏览的单 HTML 文件
"""
import json
import os
from pathlib import Path
from typing import Callable, Optional
from datetime import datetime

from logger import get_logger

logger = get_logger("export")

class HtmlExporter:
    """HTML 导出器"""
    
    def __init__(self, db_manager):
        """
        初始化导出器
        
        Args:
            db_manager: 数据库管理器实例
        """
        self.db = db_manager
        self.template_path = Path(__file__).parent / "template.html"
    
    def export(self, output_path: str, progress_callback: Optional[Callable] = None) -> bool:
        """
        导出为 HTML 文件
        
        Args:
            output_path: 输出文件路径
            progress_callback: 进度回调函数 (current, total, message)
            
        Returns:
            是否成功
        """
        try:
            # 1. 获取所有文件数据
            if progress_callback:
                progress_callback(0, 100, "正在读取数据库...")
            
            files = self._get_all_files()
            total_items = len(files)
            # 统计文件和文件夹数量
            total_files = sum(1 for f in files if not f[4])  # is_dir = 0
            total_folders = sum(1 for f in files if f[4])    # is_dir = 1
            
            if progress_callback:
                progress_callback(20, 100, f"读取到 {total_files} 个文件和 {total_folders} 个文件夹，正在构建树形结构...")
            
            # 2. 构建树形结构
            tree = self._build_tree(files)
            
            if progress_callback:
                progress_callback(60, 100, "正在生成 HTML...")
            
            # 3. 生成 JSON 数据
            data = {
                "metadata": {
                    "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "totalFiles": total_files,
                    "totalFolders": total_folders,
                    "source": "FileRecorder"
                },
                "tree": tree
            }
            
            # 4. 读取模板并替换
            template = self._read_template()
            json_data = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
            html_content = template.replace("/*{{DATA_PLACEHOLDER}}*/", f"const DATA = {json_data};")
            
            if progress_callback:
                progress_callback(80, 100, "正在写入文件...")
            
            # 5. 写入文件
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            if progress_callback:
                progress_callback(100, 100, "导出完成")
            
            return True
            
        except Exception as e:
            logger.warning(f"HTML 导出失败: {e}")
            return False
    
    def _get_all_files(self) -> list:
        """获取所有文件记录"""
        with self.db._get_connection() as conn:
            cursor = conn.execute("""
                SELECT f.filename, f.extension, f.size_bytes, f.mtime, f.is_dir, fo.path
                FROM files f
                JOIN folders fo ON f.folder_id = fo.id
                ORDER BY fo.path, f.is_dir DESC, f.filename
            """)
            return cursor.fetchall()
    
    def _build_tree(self, files: list) -> list:
        """
        将平铺文件列表构建为树形结构
        
        Returns:
            树形结构列表（顶级目录列表）
        """
        # 使用字典存储目录节点
        nodes = {}
        roots = []
        
        for row in files:
            name, ext, size, mtime, is_dir, full_path = row
            
            # 解析路径
            path_parts = full_path.replace('/', '\\').split('\\')
            
            # 逐级创建目录节点
            current_path = ""
            parent_node = None
            
            for i, part in enumerate(path_parts):
                if not part:
                    continue
                    
                current_path = current_path + "\\" + part if current_path else part
                
                if current_path not in nodes:
                    node = {
                        "n": part,
                        "c": [],  # children (dirs)
                        "f": []   # files
                    }
                    nodes[current_path] = node
                    
                    if parent_node is None:
                        # 这是顶级目录
                        roots.append(node)
                    else:
                        parent_node["c"].append(node)
                
                parent_node = nodes[current_path]
            
            # 添加文件到当前目录
            if parent_node and not is_dir:
                file_entry = {"n": name}
                if size:
                    file_entry["s"] = size
                if mtime:
                    file_entry["t"] = int(mtime) if mtime else 0
                parent_node["f"].append(file_entry)
        
        return roots
    
    def _read_template(self) -> str:
        """读取 HTML 模板"""
        if self.template_path.exists():
            with open(self.template_path, 'r', encoding='utf-8') as f:
                return f.read()
        else:
            # 返回内置模板
            return self._get_builtin_template()
    
    def _get_builtin_template(self) -> str:
        """获取内置 HTML 模板"""
        return '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FileRecorder Export</title>
    <style>
        :root {
            --bg-primary: #1e1e1e;
            --bg-secondary: #252526;
            --bg-hover: #2a2d2e;
            --text-primary: #cccccc;
            --text-secondary: #858585;
            --border-color: #3c3c3c;
            --accent-color: #0078d4;
            --icon-folder: #dcb67a;
            --icon-file: #c5c5c5;
        }
        
        [data-theme="light"] {
            --bg-primary: #ffffff;
            --bg-secondary: #f3f3f3;
            --bg-hover: #e8e8e8;
            --text-primary: #333333;
            --text-secondary: #6e6e6e;
            --border-color: #e0e0e0;
            --accent-color: #0078d4;
            --icon-folder: #dcb67a;
            --icon-file: #6e6e6e;
        }
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            font-size: 13px;
            background: var(--bg-primary);
            color: var(--text-primary);
            height: 100vh;
            display: flex;
            flex-direction: column;
        }
        
        /* Header */
        .header {
            background: var(--bg-secondary);
            border-bottom: 1px solid var(--border-color);
            padding: 8px 16px;
            display: flex;
            align-items: center;
            gap: 16px;
            flex-shrink: 0;
        }
        
        .header h1 {
            font-size: 14px;
            font-weight: 500;
            flex-shrink: 0;
        }
        
        .search-group {
            display: flex;
            align-items: center;
            gap: 8px;
            flex: 1;
        }
        
        .search-box {
            flex: 1;
            max-width: 400px;
            position: relative;
        }
        
        .search-box input {
            width: 100%;
            padding: 6px 12px 6px 32px;
            border: 1px solid var(--border-color);
            border-radius: 4px;
            background: var(--bg-primary);
            color: var(--text-primary);
            font-size: 13px;
            outline: none;
        }
        
        .search-box input:focus {
            border-color: var(--accent-color);
        }
        
        .search-box svg {
            position: absolute;
            left: 10px;
            top: 50%;
            transform: translateY(-50%);
            width: 14px;
            height: 14px;
            fill: var(--text-secondary);
        }
        
        .search-btns {
            display: flex;
            gap: 4px;
        }
        
        .search-btns button {
            padding: 6px 10px;
            border: 1px solid var(--border-color);
            border-radius: 4px;
            background: var(--bg-secondary);
            color: var(--text-primary);
            font-size: 12px;
            cursor: pointer;
        }
        
        .search-btns button:hover {
            background: var(--bg-hover);
        }
        
        /* Theme dropdown */
        .theme-wrapper {
            position: relative;
        }
        
        .theme-btn {
            padding: 6px 8px;
            border: 1px solid var(--border-color);
            border-radius: 4px;
            background: var(--bg-secondary);
            color: var(--text-primary);
            cursor: pointer;
            display: flex;
            align-items: center;
        }
        
        .theme-btn:hover {
            background: var(--bg-hover);
        }
        
        .theme-btn svg {
            width: 16px;
            height: 16px;
            fill: currentColor;
        }
        
        .theme-dropdown {
            display: none;
            position: absolute;
            top: 100%;
            right: 0;
            margin-top: 4px;
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 6px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            min-width: 120px;
            z-index: 100;
            overflow: hidden;
        }
        
        .theme-dropdown.show {
            display: block;
        }
        
        .theme-option {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 8px 12px;
            cursor: pointer;
            font-size: 12px;
        }
        
        .theme-option:hover {
            background: var(--bg-hover);
        }
        
        .theme-option.active {
            background: var(--accent-color);
            color: white;
        }
        
        .theme-option svg {
            width: 14px;
            height: 14px;
            fill: currentColor;
        }
        
        /* Main Content */
        .main {
            display: flex;
            flex: 1;
            overflow: hidden;
        }
        
        /* Sidebar - Tree */
        .sidebar {
            width: 280px;
            background: var(--bg-secondary);
            border-right: 1px solid var(--border-color);
            overflow: auto;
            flex-shrink: 0;
        }
        
        .tree-item {
            cursor: pointer;
            user-select: none;
        }
        
        .tree-item-content {
            display: flex;
            align-items: center;
            padding: 4px 8px;
            gap: 4px;
        }
        
        .tree-item-content:hover {
            background: var(--bg-hover);
        }
        
        .tree-item-content.selected {
            background: var(--accent-color);
            color: white;
        }
        
        .tree-toggle {
            width: 16px;
            height: 16px;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
        }
        
        .tree-toggle svg {
            width: 10px;
            height: 10px;
            fill: var(--text-secondary);
            transition: transform 0.15s;
        }
        
        .tree-item.expanded > .tree-item-content .tree-toggle svg {
            transform: rotate(90deg);
        }
        
        .tree-icon {
            width: 16px;
            height: 16px;
            flex-shrink: 0;
        }
        
        .tree-icon svg {
            width: 16px;
            height: 16px;
            fill: var(--icon-folder);
        }
        
        .tree-label {
            flex: 1;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        
        .tree-children {
            display: none;
            padding-left: 16px;
        }
        
        .tree-item.expanded > .tree-children {
            display: block;
        }
        
        /* File List */
        .content {
            flex: 1;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }
        
        .file-list-header {
            display: flex;
            background: var(--bg-secondary);
            border-bottom: 1px solid var(--border-color);
            font-weight: 500;
            flex-shrink: 0;
        }
        
        .file-list-header > div,
        .file-item > div {
            padding: 6px 12px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        
        .file-list-header > div {
            cursor: pointer;
            user-select: none;
        }
        
        .file-list-header > div:hover {
            background: var(--bg-hover);
        }
        
        .file-list-header > div.sorted::after {
            content: ' ▲';
            font-size: 10px;
        }
        
        .file-list-header > div.sorted.desc::after {
            content: ' ▼';
        }
        
        .col-name { flex: 1; min-width: 200px; }
        .col-size { width: 100px; }
        .col-date { width: 140px; }
        
        .file-list {
            flex: 1;
            overflow: auto;
        }
        
        .file-item {
            display: flex;
            border-bottom: 1px solid var(--border-color);
        }
        
        .file-item:hover {
            background: var(--bg-hover);
        }
        
        .file-item .col-name {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .file-item .file-icon {
            width: 16px;
            height: 16px;
            flex-shrink: 0;
        }
        
        .file-item .file-icon svg {
            width: 16px;
            height: 16px;
            fill: var(--icon-file);
        }
        
        /* Footer */
        .footer {
            background: var(--bg-secondary);
            border-top: 1px solid var(--border-color);
            padding: 6px 16px;
            font-size: 12px;
            color: var(--text-secondary);
            flex-shrink: 0;
            display: flex;
            justify-content: space-between;
        }
        
        .footer-left, .footer-right {
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        
        .footer-right {
            text-align: right;
            flex-shrink: 0;
            max-width: 50%;
        }
        
        /* Clickable folder */
        .file-item.folder-item {
            cursor: pointer;
        }
        
        .file-item.folder-item:hover {
            background: var(--accent-color);
            color: white;
        }
        
        /* Search highlight */
        .highlight {
            background: #ffff00;
            color: #000;
        }
        
        [data-theme="dark"] .highlight {
            background: #665c00;
            color: #fff;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>FileRecorder</h1>
        <div class="search-group">
            <div class="search-box">
                <svg viewBox="0 0 16 16"><path d="M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398h-.001c.03.04.062.078.098.115l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.85-3.85a1.007 1.007 0 0 0-.115-.1zM12 6.5a5.5 5.5 0 1 1-11 0 5.5 5.5 0 0 1 11 0z"/></svg>
                <input type="text" id="searchInput" placeholder="搜索文件名...">
            </div>
            <div class="search-btns">
                <button id="searchBtn">搜索</button>
                <button id="clearBtn">清除</button>
            </div>
        </div>
        <div class="theme-wrapper">
            <button class="theme-btn" id="themeBtn" title="切换主题">
                <svg id="themeIcon" viewBox="0 0 16 16"></svg>
            </button>
            <div class="theme-dropdown" id="themeDropdown">
                <div class="theme-option" data-theme="light">
                    <svg viewBox="0 0 16 16"><path d="M8 11a3 3 0 1 1 0-6 3 3 0 0 1 0 6zm0 1a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM8 0a.5.5 0 0 1 .5.5v2a.5.5 0 0 1-1 0v-2A.5.5 0 0 1 8 0zm0 13a.5.5 0 0 1 .5.5v2a.5.5 0 0 1-1 0v-2A.5.5 0 0 1 8 13zm8-5a.5.5 0 0 1-.5.5h-2a.5.5 0 0 1 0-1h2a.5.5 0 0 1 .5.5zM3 8a.5.5 0 0 1-.5.5h-2a.5.5 0 0 1 0-1h2A.5.5 0 0 1 3 8z"/></svg>
                    <span>浅色</span>
                </div>
                <div class="theme-option" data-theme="dark">
                    <svg viewBox="0 0 16 16"><path d="M6 .278a.768.768 0 0 1 .08.858 7.208 7.208 0 0 0-.878 3.46c0 4.021 3.278 7.277 7.318 7.277.527 0 1.04-.055 1.533-.16a.787.787 0 0 1 .81.316.733.733 0 0 1-.031.893A8.349 8.349 0 0 1 8.344 16C3.734 16 0 12.286 0 7.71 0 4.266 2.114 1.312 5.124.06A.752.752 0 0 1 6 .278z"/></svg>
                    <span>深色</span>
                </div>
                <div class="theme-option" data-theme="auto">
                    <svg viewBox="0 0 16 16"><path d="M0 4s0-2 2-2h12s2 0 2 2v6s0 2-2 2h-4c0 .667.083 1.167.25 1.5H11a.5.5 0 0 1 0 1H5a.5.5 0 0 1 0-1h.75c.167-.333.25-.833.25-1.5H2s-2 0-2-2V4zm1.398-.855a.758.758 0 0 0-.254.302A1.46 1.46 0 0 0 1 4.01V10c0 .325.078.502.145.602.07.105.17.188.302.254a1.464 1.464 0 0 0 .538.143L2.01 11H14c.325 0 .502-.078.602-.145a.758.758 0 0 0 .254-.302 1.464 1.464 0 0 0 .143-.538L15 9.99V4c0-.325-.078-.502-.145-.602a.757.757 0 0 0-.302-.254A1.46 1.46 0 0 0 13.99 3H2c-.325 0-.502.078-.602.145z"/></svg>
                    <span>系统</span>
                </div>
            </div>
        </div>
    </div>
    
    <div class="main">
        <div class="sidebar" id="treeContainer"></div>
        <div class="content">
            <div class="file-list-header">
                <div class="col-name" id="sortName" data-sort="name">名称</div>
                <div class="col-size" id="sortSize" data-sort="size">大小</div>
                <div class="col-date" id="sortDate" data-sort="date">修改时间</div>
            </div>
            <div class="file-list" id="fileList"></div>
        </div>
    </div>
    
    <div class="footer">
        <span class="footer-left" id="footerLeft">正在加载...</span>
        <span class="footer-right" id="footerRight"></span>
    </div>

    <script>
        /*{{DATA_PLACEHOLDER}}*/
        
        // Icons
        const ICONS = {
            folder: '<svg viewBox="0 0 16 16"><path d="M.54 3.87L.5 3a2 2 0 0 1 2-2h3.672a2 2 0 0 1 1.414.586l.828.828A2 2 0 0 0 9.828 3H14a2 2 0 0 1 2 2v1H0a1 1 0 0 1 0-.13zM0 13V6a.5.5 0 0 1 .5-.5h15a.5.5 0 0 1 .5.5v7a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2z"/></svg>',
            file: '<svg viewBox="0 0 16 16"><path d="M4 0a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V4.5L9.5 0H4zm5.5 0v4a.5.5 0 0 0 .5.5h4L9.5 0z"/></svg>',
            chevron: '<svg viewBox="0 0 16 16"><path d="M4.646 1.646a.5.5 0 0 1 .708 0l6 6a.5.5 0 0 1 0 .708l-6 6a.5.5 0 0 1-.708-.708L10.293 8 4.646 2.354a.5.5 0 0 1 0-.708z"/></svg>'
        };
        
        let selectedNode = null;
        let currentTheme = 'auto';
        
        // Theme Icons
        const THEME_ICONS = {
            light: '<path d="M8 11a3 3 0 1 1 0-6 3 3 0 0 1 0 6zm0 1a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM8 0a.5.5 0 0 1 .5.5v2a.5.5 0 0 1-1 0v-2A.5.5 0 0 1 8 0zm0 13a.5.5 0 0 1 .5.5v2a.5.5 0 0 1-1 0v-2A.5.5 0 0 1 8 13zm8-5a.5.5 0 0 1-.5.5h-2a.5.5 0 0 1 0-1h2a.5.5 0 0 1 .5.5zM3 8a.5.5 0 0 1-.5.5h-2a.5.5 0 0 1 0-1h2A.5.5 0 0 1 3 8z"/>',
            dark: '<path d="M6 .278a.768.768 0 0 1 .08.858 7.208 7.208 0 0 0-.878 3.46c0 4.021 3.278 7.277 7.318 7.277.527 0 1.04-.055 1.533-.16a.787.787 0 0 1 .81.316.733.733 0 0 1-.031.893A8.349 8.349 0 0 1 8.344 16C3.734 16 0 12.286 0 7.71 0 4.266 2.114 1.312 5.124.06A.752.752 0 0 1 6 .278z"/>',
            auto: '<path d="M0 4s0-2 2-2h12s2 0 2 2v6s0 2-2 2h-4c0 .667.083 1.167.25 1.5H11a.5.5 0 0 1 0 1H5a.5.5 0 0 1 0-1h.75c.167-.333.25-.833.25-1.5H2s-2 0-2-2V4zm1.398-.855a.758.758 0 0 0-.254.302A1.46 1.46 0 0 0 1 4.01V10c0 .325.078.502.145.602.07.105.17.188.302.254a1.464 1.464 0 0 0 .538.143L2.01 11H14c.325 0 .502-.078.602-.145a.758.758 0 0 0 .254-.302 1.464 1.464 0 0 0 .143-.538L15 9.99V4c0-.325-.078-.502-.145-.602a.757.757 0 0 0-.302-.254A1.46 1.46 0 0 0 13.99 3H2c-.325 0-.502.078-.602.145z"/>'
        };
        
        // Theme
        function initTheme() {
            currentTheme = localStorage.getItem('themeMode') || 'auto';
            applyTheme();
            updateThemeUI();
        }
        
        function applyTheme() {
            if (currentTheme === 'auto') {
                document.body.dataset.theme = window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
            } else {
                document.body.dataset.theme = currentTheme;
            }
        }
        
        function updateThemeUI() {
            document.getElementById('themeIcon').innerHTML = THEME_ICONS[currentTheme];
            document.querySelectorAll('.theme-option').forEach(opt => {
                opt.classList.toggle('active', opt.dataset.theme === currentTheme);
            });
        }
        
        function setTheme(theme) {
            currentTheme = theme;
            localStorage.setItem('themeMode', theme);
            applyTheme();
            updateThemeUI();
            document.getElementById('themeDropdown').classList.remove('show');
        }
        
        function toggleThemeDropdown(e) {
            e.stopPropagation();
            document.getElementById('themeDropdown').classList.toggle('show');
        }
        
        // Format helpers
        function formatSize(bytes) {
            if (!bytes) return '-';
            const units = ['B', 'KB', 'MB', 'GB', 'TB'];
            let i = 0;
            while (bytes >= 1024 && i < units.length - 1) {
                bytes /= 1024;
                i++;
            }
            return bytes.toFixed(i > 0 ? 1 : 0) + ' ' + units[i];
        }
        
        function formatDate(timestamp) {
            if (!timestamp) return '-';
            const d = new Date(timestamp * 1000);
            const date = d.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' });
            const time = d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false });
            return date + ' ' + time;
        }
        
        // Build tree
        function buildTree(nodes, container) {
            nodes.forEach(node => {
                const item = document.createElement('div');
                item.className = 'tree-item';
                
                const content = document.createElement('div');
                content.className = 'tree-item-content';
                
                const hasChildren = node.c && node.c.length > 0;
                
                const toggle = document.createElement('span');
                toggle.className = 'tree-toggle';
                toggle.innerHTML = hasChildren ? ICONS.chevron : '';
                content.appendChild(toggle);
                
                const icon = document.createElement('span');
                icon.className = 'tree-icon';
                icon.innerHTML = ICONS.folder;
                content.appendChild(icon);
                
                const label = document.createElement('span');
                label.className = 'tree-label';
                label.textContent = node.n;
                content.appendChild(label);
                
                item.appendChild(content);
                
                if (hasChildren) {
                    const children = document.createElement('div');
                    children.className = 'tree-children';
                    buildTree(node.c, children);
                    item.appendChild(children);
                }
                
                // 点击箭头只展开/收起
                toggle.addEventListener('click', (e) => {
                    e.stopPropagation();
                    e.preventDefault();
                    if (hasChildren) {
                        item.classList.toggle('expanded');
                    }
                });
                
                // 点击文件夹名称（非箭头区域）选择该文件夹
                content.addEventListener('click', (e) => {
                    // 如果点击的是箭头区域，不处理
                    if (e.target === toggle || toggle.contains(e.target)) {
                        return;
                    }
                    e.stopPropagation();
                    selectNode(node, content, item);
                });
                
                container.appendChild(item);
            });
        }
        
        function selectNode(node, element, treeItem, pushHistory = true) {
            if (selectedNode) {
                selectedNode.classList.remove('selected');
            }
            selectedNode = element;
            element.classList.add('selected');
            // 展开选中的文件夹
            if (treeItem) {
                treeItem.classList.add('expanded');
            }
            currentNode = node;
            currentPath = getNodePath(node);
            isShowingSearchResults = false;
            showFolderContents(node);
            
            // 添加到历史记录
            if (pushHistory) {
                pushHistoryState({type: 'folder', node: node, path: currentPath});
            }
        }
        
        // 获取节点路径
        function getNodePath(targetNode) {
            function findPath(nodes, target, path) {
                for (const node of nodes) {
                    const newPath = path ? path + '\\\\' + node.n : node.n;
                    if (node === target) return newPath;
                    if (node.c) {
                        const found = findPath(node.c, target, newPath);
                        if (found) return found;
                    }
                }
                return null;
            }
            return findPath(DATA.tree, targetNode, '') || '';
        }
        
        // 更新底部信息显示
        function updateFooterInfo() {
            if (!currentNode) return;
            
            // 递归计算文件夹总体积
            function calcSize(node) {
                let size = 0;
                if (node.f) {
                    node.f.forEach(f => size += (f.s || 0));
                }
                if (node.c) {
                    node.c.forEach(child => size += calcSize(child));
                }
                return size;
            }
            
            // 计算当前文件夹的统计信息
            const folderCount = currentNode.c ? currentNode.c.length : 0;
            const fileCount = currentNode.f ? currentNode.f.length : 0;
            const totalSize = calcSize(currentNode);
            
            document.getElementById('footerLeft').textContent = 
                `${folderCount} 个文件夹、${fileCount} 个文件，共 ${formatSize(totalSize)}`;
            document.getElementById('footerRight').textContent = currentPath || '';
        }
        
        function updateFooterDefault() {
            const f = DATA.metadata.totalFiles.toLocaleString();
            const d = DATA.metadata.totalFolders ? DATA.metadata.totalFolders.toLocaleString() : '0';
            document.getElementById('footerLeft').textContent = 
                `共 ${f} 个文件、${d} 个文件夹 · 生成于 ${DATA.metadata.generated}`;
            document.getElementById('footerRight').textContent = '';
        }
        
        // 排序相关
        let currentSort = {field: 'name', asc: true};
        let currentNode = null;
        let currentPath = '';
        let currentItems = [];
        
        function sortItems(items, field, asc) {
            return [...items].sort((a, b) => {
                // 文件夹永远在前
                if (a.isDir !== b.isDir) return a.isDir ? -1 : 1;
                
                let va, vb;
                if (field === 'name') {
                    va = a.n.toLowerCase();
                    vb = b.n.toLowerCase();
                } else if (field === 'size') {
                    va = a.s || 0;
                    vb = b.s || 0;
                } else if (field === 'date') {
                    va = a.t || 0;
                    vb = b.t || 0;
                }
                
                if (va < vb) return asc ? -1 : 1;
                if (va > vb) return asc ? 1 : -1;
                return 0;
            });
        }
        
        function updateSortUI() {
            document.querySelectorAll('.file-list-header > div').forEach(el => {
                el.classList.remove('sorted', 'desc');
            });
            const sortEl = document.querySelector(`[data-sort="${currentSort.field}"]`);
            if (sortEl) {
                sortEl.classList.add('sorted');
                if (!currentSort.asc) sortEl.classList.add('desc');
            }
        }
        
        function handleSort(field) {
            if (currentSort.field === field) {
                currentSort.asc = !currentSort.asc;
            } else {
                currentSort.field = field;
                currentSort.asc = true;
            }
            updateSortUI();
            renderCurrentItems();
        }
        
        function renderCurrentItems() {
            const list = document.getElementById('fileList');
            list.innerHTML = '';
            
            const sorted = sortItems(currentItems, currentSort.field, currentSort.asc);
            
            sorted.forEach(item => {
                const row = document.createElement('div');
                row.className = item.isDir ? 'file-item folder-item' : 'file-item';
                
                const name = document.createElement('div');
                name.className = 'col-name';
                
                const icon = document.createElement('span');
                icon.className = 'file-icon';
                icon.innerHTML = item.isDir ? ICONS.folder : ICONS.file;
                if (item.isDir) {
                    icon.querySelector('svg').style.fill = 'var(--icon-folder)';
                }
                name.appendChild(icon);
                
                const label = document.createElement('span');
                label.textContent = item.n;
                name.appendChild(label);
                
                const size = document.createElement('div');
                size.className = 'col-size';
                size.textContent = item.isDir ? '-' : formatSize(item.s);
                
                const date = document.createElement('div');
                date.className = 'col-date';
                date.textContent = item.isDir ? '-' : formatDate(item.t);
                
                row.appendChild(name);
                row.appendChild(size);
                row.appendChild(date);
                
                // 文件夹可点击跳转
                if (item.isDir && item.nodeRef) {
                    row.addEventListener('click', () => {
                        navigateToNode(item.nodeRef);
                    });
                }
                
                list.appendChild(row);
            });
        }
        
        function navigateToNode(node) {
            // 在树中找到对应节点并选中
            const treeItems = document.querySelectorAll('.tree-item');
            for (const treeItem of treeItems) {
                const content = treeItem.querySelector('.tree-item-content');
                const label = content.querySelector('.tree-label');
                if (label && label.textContent === node.n) {
                    // 检查是否是同一个节点（通过父节点路径）
                    selectNode(node, content, treeItem);
                    // 确保树节点可见
                    content.scrollIntoView({behavior: 'smooth', block: 'nearest'});
                    break;
                }
            }
        }
        
        function showFolderContents(node) {
            currentItems = [];
            
            // 添加子文件夹
            if (node.c && node.c.length > 0) {
                node.c.forEach(child => {
                    currentItems.push({
                        n: child.n,
                        s: 0,
                        t: 0,
                        isDir: true,
                        nodeRef: child
                    });
                });
            }
            
            // 添加文件
            if (node.f && node.f.length > 0) {
                node.f.forEach(file => {
                    currentItems.push({
                        n: file.n,
                        s: file.s,
                        t: file.t,
                        isDir: false
                    });
                });
            }
            
            renderCurrentItems();
            updateFooterInfo();
        }
        
        function showFiles(files, highlight = '') {
            const list = document.getElementById('fileList');
            list.innerHTML = '';
            
            files.forEach(file => {
                const item = document.createElement('div');
                item.className = 'file-item';
                
                const name = document.createElement('div');
                name.className = 'col-name';
                
                const icon = document.createElement('span');
                icon.className = 'file-icon';
                icon.innerHTML = ICONS.file;
                name.appendChild(icon);
                
                const label = document.createElement('span');
                if (highlight) {
                    label.innerHTML = file.n.replace(new RegExp(highlight, 'gi'), '<span class="highlight">$&</span>');
                } else {
                    label.textContent = file.n;
                }
                name.appendChild(label);
                
                const size = document.createElement('div');
                size.className = 'col-size';
                size.textContent = formatSize(file.s);
                
                const date = document.createElement('div');
                date.className = 'col-date';
                date.textContent = formatDate(file.t);
                
                item.appendChild(name);
                item.appendChild(size);
                item.appendChild(date);
                list.appendChild(item);
            });
        }
        
        function showSearchResults(results, keywords = []) {
            const list = document.getElementById('fileList');
            list.innerHTML = '';
            
            // 高亮函数：高亮所有关键词
            function highlightText(text) {
                if (!keywords || keywords.length === 0) return text;
                let result = text;
                keywords.forEach(kw => {
                    if (kw) result = result.replace(new RegExp(kw, 'gi'), '<span class="highlight">$&</span>');
                });
                return result;
            }
            
            results.forEach(item => {
                const row = document.createElement('div');
                row.className = 'file-item';
                
                const name = document.createElement('div');
                name.className = 'col-name';
                
                const icon = document.createElement('span');
                icon.className = 'file-icon';
                icon.innerHTML = item.isDir ? ICONS.folder : ICONS.file;
                // 文件夹图标使用黄色
                if (item.isDir) {
                    icon.querySelector('svg').style.fill = 'var(--icon-folder)';
                }
                name.appendChild(icon);
                
                const label = document.createElement('span');
                const displayName = item.isDir ? item.n + ' (文件夹)' : item.n;
                if (keywords && keywords.length > 0) {
                    label.innerHTML = highlightText(displayName);
                } else {
                    label.textContent = displayName;
                }
                name.appendChild(label);
                
                // 显示路径
                if (item.path) {
                    const pathSpan = document.createElement('span');
                    pathSpan.style.cssText = 'color: var(--text-secondary); font-size: 11px; margin-left: 8px;';
                    pathSpan.textContent = item.path;
                    name.appendChild(pathSpan);
                }
                
                const size = document.createElement('div');
                size.className = 'col-size';
                size.textContent = item.isDir ? '-' : formatSize(item.s);
                
                const date = document.createElement('div');
                date.className = 'col-date';
                date.textContent = item.isDir ? '-' : formatDate(item.t);
                
                row.appendChild(name);
                row.appendChild(size);
                row.appendChild(date);
                list.appendChild(row);
            });
        }
        
        // Search state
        let isShowingSearchResults = false;
        let nodeBeforeSearch = null;
        
        function search(keyword) {
            if (!keyword) {
                return;
            }
            
            // 记住搜索前的节点
            if (!isShowingSearchResults && currentNode) {
                nodeBeforeSearch = currentNode;
            }
            
            isShowingSearchResults = true;
            
            const results = [];
            // 支持空格分隔的多关键词搜索（AND 逻辑）
            const keywords = keyword.toLowerCase().split(/\s+/).filter(k => k.length > 0);
            
            function matchesAllKeywords(text) {
                const lowerText = text.toLowerCase();
                return keywords.every(kw => lowerText.includes(kw));
            }
            
            function searchNode(node, path) {
                // 搜索文件夹名称
                if (matchesAllKeywords(node.n)) {
                    results.push({n: node.n, isDir: true, path: path});
                }
                // 搜索文件
                if (node.f) {
                    node.f.forEach(file => {
                        if (matchesAllKeywords(file.n)) {
                            results.push({...file, path: path});
                        }
                    });
                }
                // 递归搜索子目录
                if (node.c) {
                    const newPath = path ? path + '\\\\' + node.n : node.n;
                    node.c.forEach(child => searchNode(child, newPath));
                }
            }
            
            DATA.tree.forEach(node => searchNode(node, ''));
            const displayResults = results.slice(0, 1000);
            showSearchResults(displayResults, keywords);
            
            let footerText = `搜索 "${keyword}" - ${results.length} 个结果`;
            if (results.length > 1000) {
                footerText += ` (显示前 1000 条)`;
            }
            document.getElementById('footerLeft').textContent = footerText;
            document.getElementById('footerRight').textContent = '搜索结果';
        }
        
        function doSearch() {
            const keyword = document.getElementById('searchInput').value.trim();
            if (keyword) {
                search(keyword);
            }
        }
        
        function clearSearch() {
            document.getElementById('searchInput').value = '';
            
            // 如果当前正在显示搜索结果，返回搜索前的文件夹
            if (isShowingSearchResults && nodeBeforeSearch) {
                // 找到树中对应节点并选中
                navigateToNode(nodeBeforeSearch);
                nodeBeforeSearch = null;
            } else if (currentNode) {
                // 用户已选择新文件夹，更新 footer 显示当前文件夹信息
                updateFooterInfo();
            } else {
                // 没有选择任何文件夹，显示默认信息
                updateFooterDefault();
            }
        }
        
        // History navigation
        let historyStack = [];
        let historyIndex = -1;
        let isNavigating = false;
        
        function pushHistoryState(state) {
            if (isNavigating) return;
            
            // 如果当前不是栈顶，截断后面的历史
            if (historyIndex < historyStack.length - 1) {
                historyStack = historyStack.slice(0, historyIndex + 1);
            }
            historyStack.push(state);
            historyIndex = historyStack.length - 1;
        }
        
        function goBack() {
            if (historyIndex > 0) {
                historyIndex--;
                navigateToState(historyStack[historyIndex]);
            }
        }
        
        function goForward() {
            if (historyIndex < historyStack.length - 1) {
                historyIndex++;
                navigateToState(historyStack[historyIndex]);
            }
        }
        
        function navigateToState(state) {
            isNavigating = true;
            if (state.type === 'folder' && state.node) {
                navigateToNode(state.node);
            }
            isNavigating = false;
        }
        
        // Init
        document.addEventListener('DOMContentLoaded', () => {
            initTheme();
            
            if (typeof DATA !== 'undefined') {
                buildTree(DATA.tree, document.getElementById('treeContainer'));
                
                // 默认展开根目录一级
                document.querySelectorAll('#treeContainer > .tree-item').forEach(item => {
                    item.classList.add('expanded');
                });
                
                const f = DATA.metadata.totalFiles.toLocaleString();
                const d = DATA.metadata.totalFolders ? DATA.metadata.totalFolders.toLocaleString() : '0';
                document.getElementById('footerLeft').textContent = 
                    `共 ${f} 个文件、${d} 个文件夹 · 生成于 ${DATA.metadata.generated}`;
            }
            

            
            document.getElementById('searchInput').addEventListener('keypress', (e) => {
                if (e.key === 'Enter') doSearch();
            });
            
            document.getElementById('searchBtn').addEventListener('click', doSearch);
            document.getElementById('clearBtn').addEventListener('click', clearSearch);
            document.getElementById('themeBtn').addEventListener('click', toggleThemeDropdown);
            
            // 鼠标侧键前进后退
            window.addEventListener('mouseup', (e) => {
                if (e.button === 3) { // 后退键
                    e.preventDefault();
                    goBack();
                } else if (e.button === 4) { // 前进键
                    e.preventDefault();
                    goForward();
                }
            });
            
            // 键盘前进后退 (Alt+Left/Right)
            window.addEventListener('keydown', (e) => {
                if (e.altKey && e.key === 'ArrowLeft') {
                    e.preventDefault();
                    goBack();
                } else if (e.altKey && e.key === 'ArrowRight') {
                    e.preventDefault();
                    goForward();
                }
            });
            
            // 排序事件
            document.querySelectorAll('.file-list-header > div[data-sort]').forEach(el => {
                el.addEventListener('click', () => handleSort(el.dataset.sort));
            });
            
            document.querySelectorAll('.theme-option').forEach(opt => {
                opt.addEventListener('click', () => setTheme(opt.dataset.theme));
            });
            
            // 点击其他地方关闭下拉菜单
            document.addEventListener('click', () => {
                document.getElementById('themeDropdown').classList.remove('show');
            });
            
            // 监听系统主题变化
            window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
                if (currentTheme === 'auto') applyTheme();
            });
        });
    </script>
</body>
</html>'''
