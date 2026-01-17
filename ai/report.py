"""
媒体库报告生成模块
生成 Markdown/HTML 格式的整理报告
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from ai.parser import MediaInfo, format_size


@dataclass
class ReportOptions:
    """报告选项"""
    # 是否启用去重
    dedup_enabled: bool = False
    # 去重规则
    dedup_by_name: bool = True
    dedup_by_resolution: bool = False
    dedup_by_format: bool = False
    # 输出格式
    format: str = "markdown"  # markdown, html


class MediaGroup:
    """媒体分组"""
    def __init__(self, title: str, year: int = None, media_type: str = "movie"):
        self.title = title
        self.year = year
        self.media_type = media_type
        self.files: list[MediaInfo] = []
    
    def add_file(self, info: MediaInfo):
        self.files.append(info)
    
    @property
    def total_size(self) -> int:
        return sum(f.size_bytes for f in self.files if not f.is_hardlink)
    
    @property
    def file_count(self) -> int:
        return len(self.files)


class TVShowGroup:
    """电视剧分组"""
    def __init__(self, title: str):
        self.title = title
        self.seasons: dict[int, list[MediaInfo]] = defaultdict(list)
    
    def add_episode(self, info: MediaInfo):
        season = info.season or 1
        self.seasons[season].append(info)
    
    def get_episode_count(self, season: int) -> int:
        return len(self.seasons.get(season, []))
    
    def get_missing_episodes(self, season: int, expected: int = None) -> list[int]:
        """获取缺失的集数"""
        episodes = self.seasons.get(season, [])
        ep_nums = sorted(set(e.episode for e in episodes if e.episode))
        if not ep_nums:
            return []
        
        max_ep = expected if expected else max(ep_nums)
        expected_set = set(range(1, max_ep + 1))
        actual_set = set(ep_nums)
        return sorted(expected_set - actual_set)


class ReportGenerator:
    """报告生成器"""
    
    def __init__(self, options: ReportOptions = None):
        self.options = options or ReportOptions()
    
    def generate(self, media_list: list[MediaInfo], 
                 directories: list[str] = None) -> str:
        """
        生成报告
        
        Args:
            media_list: 媒体文件列表
            directories: 扫描的目录列表
            
        Returns:
            Markdown 或 HTML 格式的报告
        """
        # 过滤掉 skip=True 的文件（预告片、样片等）
        media_list = [m for m in media_list if not getattr(m, 'skip', False)]
        
        # 根据格式选择生成方法
        if self.options.format == "html":
            return self._generate_html(media_list, directories)
        
        # 动态按类型分组（支持任意用户自定义标签）
        type_groups = defaultdict(list)
        for m in media_list:
            type_key = m.media_type or "other"
            type_groups[type_key].append(m)
        
        # 生成报告
        lines = []
        
        # 标题
        lines.append("# 媒体库整理报告\n")
        lines.append(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        if directories:
            lines.append(f"扫描目录：{', '.join(directories)}\n")
        lines.append("")
        
        # 统计概览
        lines.append("## 统计概览\n")
        lines.append("| 类型 | 数量 | 大小 |")
        lines.append("|------|------|------|")
        
        # 按类型动态生成统计，按文件数量降序排列
        for type_name, files in sorted(type_groups.items(), key=lambda x: -len(x[1])):
            file_count = len(files)
            total_size = sum(m.size_bytes for m in files)
            # 类型名首字母大写
            display_name = type_name.upper() if type_name.lower() in ('nsfw', 'av', 'nsfe') else type_name.title()
            lines.append(f"| {display_name} | {file_count} 个 | {format_size(total_size)} |")
        
        lines.append("")
        lines.append("")
        
        # 按类型分别输出详情
        for type_name, files in sorted(type_groups.items(), key=lambda x: -len(x[1])):
            if not files:
                continue
            
            # 类型标题
            display_name = type_name.upper() if type_name.lower() in ('nsfw', 'av', 'nsfe') else type_name.title()
            lines.append("---\n")
            lines.append(f"## {display_name}\n")
            
            # 检查是否有编码（用于番号类型）
            with_code = [m for m in files if m.code]
            without_code = [m for m in files if not m.code]
            
            # 如果有编码的文件，分两组显示
            if with_code:
                lines.append("### 标准编码\n")
                lines.append("| # | 编码 | 文件名 | 大小 | 格式 | 位置 |")
                lines.append("|---|------|--------|------|------|------|")
                
                for i, info in enumerate(sorted(with_code, key=lambda x: x.code), 1):
                    size = format_size(info.size_bytes)
                    ext = info.extension.upper().lstrip('.') if info.extension else "-"
                    folder = str(Path(info.filepath).parent).replace('\\', '/')
                    
                    lines.append(f"| {i} | {info.code} | {info.filename} | {size} | {ext} | {folder}/ |")
                
                lines.append("")
            
            if without_code:
                if with_code:
                    lines.append("### 无编码\n")
                lines.append("| # | 文件名 | 大小 | 格式 | 分辨率 | 位置 | 备注 |")
                lines.append("|---|--------|------|------|--------|------|------|")
                
                for i, info in enumerate(sorted(without_code, key=lambda x: x.filename), 1):
                    size = format_size(info.size_bytes)
                    ext = info.extension.upper().lstrip('.') if info.extension else "-"
                    res = info.resolution or "-"
                    folder = str(Path(info.filepath).parent).replace('\\', '/')
                    
                    note = ""
                    if info.is_disc:
                        note = f"{info.disc_type}原盘"
                    elif info.hdr:
                        note = "HDR"
                    
                    # 使用 title 或 filename
                    display_title = info.title or info.filename
                    lines.append(f"| {i} | {info.filename} | {size} | {ext} | {res} | {folder}/ | {note} |")
                
                lines.append("")
        
        return "\n".join(lines)
    
    def _group_movies(self, media_list: list[MediaInfo]) -> dict[str, MediaGroup]:
        """按电影分组（标题+年份）"""
        groups = {}
        
        for info in media_list:
            if info.media_type != "movie":
                continue
            
            # 使用标题+年份作为分组键，避免同名不同年份的电影被合并
            title_key = info.title.lower() if info.title else info.filename.lower()
            year_key = str(info.year) if info.year else ""
            key = f"{title_key}|{year_key}"
            
            if key not in groups:
                groups[key] = MediaGroup(info.title or info.filename, info.year, "movie")
            
            groups[key].add_file(info)
        
        return groups
    
    def _group_tv_shows(self, media_list: list[MediaInfo]) -> dict[str, TVShowGroup]:
        """按电视剧分组"""
        groups = {}
        
        for info in media_list:
            if info.media_type != "tv":
                continue
            
            key = info.title.lower() if info.title else "未知剧集"
            
            if key not in groups:
                groups[key] = TVShowGroup(info.title or "未知剧集")
            
            groups[key].add_episode(info)
        
        return groups
    
    def _group_anime(self, media_list: list[MediaInfo]) -> dict[str, MediaGroup]:
        """按动漫分组"""
        groups = {}
        
        for info in media_list:
            if info.media_type != "anime":
                continue
            
            key = info.title.lower() if info.title else info.filename.lower()
            
            if key not in groups:
                groups[key] = MediaGroup(info.title or info.filename, info.year, "anime")
            
            groups[key].add_file(info)
        
        return groups
    
    def save(self, content: str, filepath: str) -> str:
        """保存报告到文件"""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
        return str(path)
    
    def _generate_html(self, media_list: list[MediaInfo], directories: list[str] = None) -> str:
        """生成 HTML 格式报告"""
        import json
        
        # 按类型分组
        type_groups = defaultdict(list)
        for m in media_list:
            type_key = m.media_type or "other"
            type_groups[type_key].append(m)
        
        # 构建分类数据
        categories = []
        all_files = []
        
        for type_name, files in sorted(type_groups.items(), key=lambda x: -len(x[1])):
            display_name = type_name.upper() if type_name.lower() in ('nsfw', 'av') else type_name.title()
            
            category_files = []
            for m in files:
                file_data = {
                    "filename": m.filename,
                    "title": m.title or m.filename,
                    "code": m.code or "",
                    "resolution": m.resolution or "",
                    "size": m.size_bytes,
                    "mtime": getattr(m, 'mtime', 0) or 0,
                    "extension": (m.extension or "").upper().lstrip('.'),
                    "path": str(Path(m.filepath).parent).replace('\\', '/'),
                    "category": display_name,
                    "is_disc": m.is_disc,
                    "disc_type": m.disc_type or ""
                }
                category_files.append(file_data)
                all_files.append(file_data)
            
            categories.append({
                "name": display_name,
                "count": len(files),
                "files": category_files
            })
        
        # 构建数据对象
        data = {
            "metadata": {
                "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "totalFiles": len(media_list),
                "directories": directories or [],
                "source": "FileRecorder AI整理"
            },
            "categories": categories,
            "allFiles": all_files
        }
        
        # 生成 HTML
        template = self._get_html_template()
        json_data = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
        html_content = template.replace("/*{{DATA_PLACEHOLDER}}*/", f"const DATA = {json_data};")
        
        return html_content
    
    def _get_html_template(self) -> str:
        """获取 HTML 报告模板"""
        return '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI 整理报告</title>
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
        
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
            font-size: 13px;
            background: var(--bg-primary);
            color: var(--text-primary);
            height: 100vh;
            display: flex;
            flex-direction: column;
        }
        
        .header {
            background: var(--bg-secondary);
            border-bottom: 1px solid var(--border-color);
            padding: 8px 16px;
            display: flex;
            align-items: center;
            gap: 16px;
            flex-shrink: 0;
        }
        
        .header h1 { font-size: 14px; font-weight: 500; flex-shrink: 0; }
        
        .search-group {
            display: flex;
            align-items: center;
            gap: 8px;
            flex: 1;
        }
        
        .search-box {
            flex: 1;
            max-width: 300px;
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
        
        .search-box input:focus { border-color: var(--accent-color); }
        
        .search-box svg {
            position: absolute;
            left: 10px;
            top: 50%;
            transform: translateY(-50%);
            width: 14px;
            height: 14px;
            fill: var(--text-secondary);
        }
        
        .filter-group {
            display: flex;
            gap: 8px;
            align-items: center;
        }
        
        .filter-group select {
            padding: 6px 8px;
            border: 1px solid var(--border-color);
            border-radius: 4px;
            background: var(--bg-secondary);
            color: var(--text-primary);
            font-size: 12px;
            cursor: pointer;
        }
        
        .search-btns {
            display: flex;
            gap: 4px;
        }
        
        .search-btns button, .theme-btn {
            padding: 6px 10px;
            border: 1px solid var(--border-color);
            border-radius: 4px;
            background: var(--bg-secondary);
            color: var(--text-primary);
            font-size: 12px;
            cursor: pointer;
        }
        
        .search-btns button:hover, .theme-btn:hover { background: var(--bg-hover); }
        
        .theme-wrapper { position: relative; }
        
        .theme-btn { display: flex; align-items: center; }
        .theme-btn svg { width: 16px; height: 16px; fill: currentColor; }
        
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
            min-width: 100px;
            z-index: 100;
        }
        
        .theme-dropdown.show { display: block; }
        
        .theme-option {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 8px 12px;
            cursor: pointer;
            font-size: 12px;
        }
        
        .theme-option:hover { background: var(--bg-hover); }
        .theme-option.active { background: var(--accent-color); color: white; }
        .theme-option svg { width: 14px; height: 14px; fill: currentColor; }
        
        .main {
            display: flex;
            flex: 1;
            overflow: hidden;
        }
        
        .sidebar {
            width: 200px;
            background: var(--bg-secondary);
            border-right: 1px solid var(--border-color);
            overflow: auto;
            flex-shrink: 0;
        }
        
        .category-item {
            padding: 10px 16px;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border-color);
        }
        
        .category-item:hover { background: var(--bg-hover); }
        .category-item.selected { background: var(--accent-color); color: white; }
        
        .category-name { font-weight: 500; }
        .category-count { font-size: 11px; color: var(--text-secondary); }
        .category-item.selected .category-count { color: rgba(255,255,255,0.7); }
        
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
        
        .file-list-header > div, .file-item > div {
            padding: 6px 12px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        
        .file-list-header > div { cursor: pointer; user-select: none; }
        .file-list-header > div:hover { background: var(--bg-hover); }
        
        .file-list-header > div.sorted::after { content: ' ▲'; font-size: 10px; }
        .file-list-header > div.sorted.desc::after { content: ' ▼'; }
        
        .col-name { flex: 1; min-width: 200px; }
        .col-code { width: 140px; }
        .col-res { width: 80px; }
        .col-size { width: 80px; }
        .col-time { width: 130px; }
        .col-ext { width: 60px; }
        .col-cat { width: 80px; }
        
        .file-list { flex: 1; overflow: auto; }
        
        .file-item {
            display: flex;
            border-bottom: 1px solid var(--border-color);
        }
        
        .file-item:hover { background: var(--bg-hover); }
        
        .file-item .col-name {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .file-icon { width: 16px; height: 16px; flex-shrink: 0; }
        .file-icon svg { width: 16px; height: 16px; fill: var(--icon-file); }
        
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
        
        .highlight { background: #ffff00; color: #000; }
        [data-theme="dark"] .highlight { background: #665c00; color: #fff; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🤖 AI 整理报告</h1>
        <div class="search-group">
            <div class="search-box">
                <svg viewBox="0 0 16 16"><path d="M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398h-.001c.03.04.062.078.098.115l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.85-3.85a1.007 1.007 0 0 0-.115-.1zM12 6.5a5.5 5.5 0 1 1-11 0 5.5 5.5 0 0 1 11 0z"/></svg>
                <input type="text" id="searchInput" placeholder="搜索文件名/编码...">
            </div>
            <div class="filter-group">
                <select id="categoryFilter">
                    <option value="">全部分类</option>
                </select>
                <select id="extFilter">
                    <option value="">全部格式</option>
                </select>
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
                    <svg viewBox="0 0 16 16"><path d="M8 11a3 3 0 1 1 0-6 3 3 0 0 1 0 6zm0 1a4 4 0 1 0 0-8 4 4 0 0 0 0 8z"/></svg>
                    <span>浅色</span>
                </div>
                <div class="theme-option" data-theme="dark">
                    <svg viewBox="0 0 16 16"><path d="M6 .278a.768.768 0 0 1 .08.858 7.208 7.208 0 0 0-.878 3.46c0 4.021 3.278 7.277 7.318 7.277.527 0 1.04-.055 1.533-.16a.787.787 0 0 1 .81.316.733.733 0 0 1-.031.893A8.349 8.349 0 0 1 8.344 16C3.734 16 0 12.286 0 7.71 0 4.266 2.114 1.312 5.124.06A.752.752 0 0 1 6 .278z"/></svg>
                    <span>深色</span>
                </div>
                <div class="theme-option" data-theme="auto">
                    <svg viewBox="0 0 16 16"><path d="M0 4s0-2 2-2h12s2 0 2 2v6s0 2-2 2h-4c0 .667.083 1.167.25 1.5H11a.5.5 0 0 1 0 1H5a.5.5 0 0 1 0-1h.75c.167-.333.25-.833.25-1.5H2s-2 0-2-2V4z"/></svg>
                    <span>系统</span>
                </div>
            </div>
        </div>
    </div>
    
    <div class="main">
        <div class="sidebar" id="categoryList"></div>
        <div class="content">
            <div class="file-list-header">
                <div class="col-name" data-sort="name">名称</div>
                <div class="col-code" data-sort="code">编码</div>
                <div class="col-res" data-sort="resolution">分辨率</div>
                <div class="col-size" data-sort="size">大小</div>
                <div class="col-time" data-sort="mtime">时间</div>
                <div class="col-ext" data-sort="ext">格式</div>
                <div class="col-cat" data-sort="category">分类</div>
            </div>
            <div class="file-list" id="fileList"></div>
        </div>
    </div>
    
    <div class="footer">
        <span id="footerLeft">正在加载...</span>
        <span id="footerRight"></span>
    </div>

    <script>
        /*{{DATA_PLACEHOLDER}}*/
        
        const ICONS = {
            file: '<svg viewBox="0 0 16 16"><path d="M4 0a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V4.5L9.5 0H4zm5.5 0v4a.5.5 0 0 0 .5.5h4L9.5 0z"/></svg>',
            disc: '<svg viewBox="0 0 16 16"><path d="M8 15A7 7 0 1 1 8 1a7 7 0 0 1 0 14zm0 1A8 8 0 1 0 8 0a8 8 0 0 0 0 16z"/><path d="M10 8a2 2 0 1 1-4 0 2 2 0 0 1 4 0z"/></svg>'
        };
        
        const THEME_ICONS = {
            light: '<path d="M8 11a3 3 0 1 1 0-6 3 3 0 0 1 0 6zm0 1a4 4 0 1 0 0-8 4 4 0 0 0 0 8z"/>',
            dark: '<path d="M6 .278a.768.768 0 0 1 .08.858 7.208 7.208 0 0 0-.878 3.46c0 4.021 3.278 7.277 7.318 7.277.527 0 1.04-.055 1.533-.16a.787.787 0 0 1 .81.316.733.733 0 0 1-.031.893A8.349 8.349 0 0 1 8.344 16C3.734 16 0 12.286 0 7.71 0 4.266 2.114 1.312 5.124.06A.752.752 0 0 1 6 .278z"/>',
            auto: '<path d="M0 4s0-2 2-2h12s2 0 2 2v6s0 2-2 2h-4c0 .667.083 1.167.25 1.5H11a.5.5 0 0 1 0 1H5a.5.5 0 0 1 0-1h.75c.167-.333.25-.833.25-1.5H2s-2 0-2-2V4z"/>'
        };
        
        let currentTheme = 'auto';
        let currentCategory = null;
        let currentSort = {field: 'name', asc: true};
        let currentFiles = [];
        let isShowingSearchResults = false;
        let categoryBeforeSearch = null;
        
        // Theme
        function initTheme() {
            currentTheme = localStorage.getItem('aiReportTheme') || 'auto';
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
            localStorage.setItem('aiReportTheme', theme);
            applyTheme();
            updateThemeUI();
            document.getElementById('themeDropdown').classList.remove('show');
        }
        
        // Format helpers
        function formatSize(bytes) {
            if (!bytes) return '-';
            const units = ['B', 'KB', 'MB', 'GB', 'TB'];
            let i = 0;
            while (bytes >= 1024 && i < units.length - 1) { bytes /= 1024; i++; }
            return bytes.toFixed(i > 0 ? 1 : 0) + ' ' + units[i];
        }
        
        function formatDate(timestamp) {
            if (!timestamp) return '-';
            const d = new Date(timestamp * 1000);
            const date = d.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' });
            const time = d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false });
            return date + ' ' + time;
        }
        
        // Build category list
        function buildCategoryList() {
            const container = document.getElementById('categoryList');
            container.innerHTML = '';
            
            // 总览
            const overviewItem = document.createElement('div');
            overviewItem.className = 'category-item selected';
            overviewItem.innerHTML = `
                <span class="category-name">📊 总览</span>
                <span class="category-count">${DATA.allFiles.length}</span>
            `;
            overviewItem.onclick = () => selectCategory(null, overviewItem);
            container.appendChild(overviewItem);
            
            // 各分类
            DATA.categories.forEach(cat => {
                const item = document.createElement('div');
                item.className = 'category-item';
                item.innerHTML = `
                    <span class="category-name">📁 ${cat.name}</span>
                    <span class="category-count">${cat.count}</span>
                `;
                item.onclick = () => selectCategory(cat.name, item);
                container.appendChild(item);
            });
            
            // 初始化筛选下拉框
            initFilters();
        }
        
        function initFilters() {
            const catFilter = document.getElementById('categoryFilter');
            DATA.categories.forEach(cat => {
                const opt = document.createElement('option');
                opt.value = cat.name;
                opt.textContent = cat.name;
                catFilter.appendChild(opt);
            });
            
            const extFilter = document.getElementById('extFilter');
            const exts = [...new Set(DATA.allFiles.map(f => f.extension).filter(e => e))].sort();
            exts.forEach(ext => {
                const opt = document.createElement('option');
                opt.value = ext;
                opt.textContent = ext;
                extFilter.appendChild(opt);
            });
        }
        
        function selectCategory(catName, element) {
            document.querySelectorAll('.category-item').forEach(el => el.classList.remove('selected'));
            element.classList.add('selected');
            currentCategory = catName;
            isShowingSearchResults = false;
            
            if (catName === null) {
                currentFiles = DATA.allFiles;
            } else {
                const cat = DATA.categories.find(c => c.name === catName);
                currentFiles = cat ? cat.files : [];
            }
            
            renderFiles();
            updateFooter();
        }
        
        function renderFiles(highlight = '') {
            const list = document.getElementById('fileList');
            list.innerHTML = '';
            
            // 高亮函数：支持多关键词
            const keywords = highlight ? highlight.split(/\s+/).filter(k => k.length > 0) : [];
            function highlightText(text) {
                if (keywords.length === 0) return text;
                let result = text;
                keywords.forEach(kw => {
                    if (kw) result = result.replace(new RegExp(kw, 'gi'), '<span class="highlight">$&</span>');
                });
                return result;
            }
            
            const sorted = sortFiles(currentFiles, currentSort.field, currentSort.asc);
            
            sorted.forEach(file => {
                const row = document.createElement('div');
                row.className = 'file-item';
                row.title = file.path;  // 鼠标悬停显示路径
                
                const name = document.createElement('div');
                name.className = 'col-name';
                const icon = document.createElement('span');
                icon.className = 'file-icon';
                icon.innerHTML = file.is_disc ? ICONS.disc : ICONS.file;
                name.appendChild(icon);
                const label = document.createElement('span');
                if (keywords.length > 0) {
                    label.innerHTML = highlightText(file.filename);
                } else {
                    label.textContent = file.filename;
                }
                name.appendChild(label);
                
                const code = document.createElement('div');
                code.className = 'col-code';
                code.textContent = file.code || '-';
                
                const res = document.createElement('div');
                res.className = 'col-res';
                res.textContent = file.resolution || '-';
                
                const size = document.createElement('div');
                size.className = 'col-size';
                size.textContent = formatSize(file.size);
                
                const time = document.createElement('div');
                time.className = 'col-time';
                time.textContent = formatDate(file.mtime);
                
                const ext = document.createElement('div');
                ext.className = 'col-ext';
                ext.textContent = file.extension || '-';
                
                const cat = document.createElement('div');
                cat.className = 'col-cat';
                cat.textContent = file.category;
                
                row.appendChild(name);
                row.appendChild(code);
                row.appendChild(res);
                row.appendChild(size);
                row.appendChild(time);
                row.appendChild(ext);
                row.appendChild(cat);
                list.appendChild(row);
            });
        }
        
        function sortFiles(files, field, asc) {
            return [...files].sort((a, b) => {
                let va, vb;
                switch(field) {
                    case 'name': va = a.filename.toLowerCase(); vb = b.filename.toLowerCase(); break;
                    case 'code': va = a.code || ''; vb = b.code || ''; break;
                    case 'resolution': va = a.resolution || ''; vb = b.resolution || ''; break;
                    case 'size': va = a.size || 0; vb = b.size || 0; break;
                    case 'mtime': va = a.mtime || 0; vb = b.mtime || 0; break;
                    case 'ext': va = a.extension || ''; vb = b.extension || ''; break;
                    case 'category': va = a.category; vb = b.category; break;
                    default: va = a.filename; vb = b.filename;
                }
                if (va < vb) return asc ? -1 : 1;
                if (va > vb) return asc ? 1 : -1;
                return 0;
            });
        }
        
        function handleSort(field) {
            if (currentSort.field === field) {
                currentSort.asc = !currentSort.asc;
            } else {
                currentSort.field = field;
                currentSort.asc = true;
            }
            updateSortUI();
            renderFiles();
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
        
        function doSearch() {
            const rawKeyword = document.getElementById('searchInput').value.trim();
            const catFilter = document.getElementById('categoryFilter').value;
            const extFilter = document.getElementById('extFilter').value;
            
            if (!rawKeyword && !catFilter && !extFilter) return;
            
            if (!isShowingSearchResults) {
                categoryBeforeSearch = currentCategory;
            }
            isShowingSearchResults = true;
            
            let results = DATA.allFiles;
            
            // 支持空格分隔的多关键词搜索（AND 逻辑）
            if (rawKeyword) {
                const keywords = rawKeyword.toLowerCase().split(/\s+/).filter(k => k.length > 0);
                results = results.filter(f => {
                    const searchText = (f.filename + ' ' + (f.code || '') + ' ' + (f.title || '')).toLowerCase();
                    return keywords.every(kw => searchText.includes(kw));
                });
            }
            
            if (catFilter) {
                results = results.filter(f => f.category === catFilter);
            }
            
            if (extFilter) {
                results = results.filter(f => f.extension === extFilter);
            }
            
            currentFiles = results.slice(0, 1000);
            renderFiles(rawKeyword);
            
            let footerText = `搜索结果: ${results.length} 个文件`;
            if (results.length > 1000) footerText += ' (显示前 1000 条)';
            document.getElementById('footerLeft').textContent = footerText;
            document.getElementById('footerRight').textContent = '';
        }
        
        function clearSearch() {
            document.getElementById('searchInput').value = '';
            document.getElementById('categoryFilter').value = '';
            document.getElementById('extFilter').value = '';
            
            if (isShowingSearchResults) {
                isShowingSearchResults = false;
                // 返回之前的分类
                const items = document.querySelectorAll('.category-item');
                if (categoryBeforeSearch === null) {
                    selectCategory(null, items[0]);
                } else {
                    const catIndex = DATA.categories.findIndex(c => c.name === categoryBeforeSearch) + 1;
                    if (items[catIndex]) selectCategory(categoryBeforeSearch, items[catIndex]);
                }
                categoryBeforeSearch = null;
            }
        }
        
        function updateFooter() {
            const catName = currentCategory === null ? '总览' : currentCategory;
            document.getElementById('footerLeft').textContent = `${catName}: ${currentFiles.length} 个文件`;
            document.getElementById('footerRight').textContent = DATA.metadata.directories.join(', ');
        }
        
        // Init
        function init() {
            initTheme();
            buildCategoryList();
            currentFiles = DATA.allFiles;
            renderFiles();
            updateFooter();
            updateSortUI();
            
            // Event listeners
            document.getElementById('searchBtn').onclick = doSearch;
            document.getElementById('clearBtn').onclick = clearSearch;
            document.getElementById('searchInput').onkeydown = e => { if (e.key === 'Enter') doSearch(); };
            document.getElementById('themeBtn').onclick = e => {
                e.stopPropagation();
                document.getElementById('themeDropdown').classList.toggle('show');
            };
            document.querySelectorAll('.theme-option').forEach(opt => {
                opt.onclick = () => setTheme(opt.dataset.theme);
            });
            document.querySelectorAll('.file-list-header > div[data-sort]').forEach(el => {
                el.onclick = () => handleSort(el.dataset.sort);
            });
            document.onclick = () => document.getElementById('themeDropdown').classList.remove('show');
        }
        
        init();
    </script>
</body>
</html>'''
