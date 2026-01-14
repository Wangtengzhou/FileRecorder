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
            Markdown 格式的报告
        """
        # 过滤掉 skip=True 的文件（预告片、样片等）
        media_list = [m for m in media_list if not getattr(m, 'skip', False)]
        
        # 动态按类型分组（支持任意用户自定义标签）
        type_groups = defaultdict(list)
        for m in media_list:
            type_key = m.media_type or "other"
            type_groups[type_key].append(m)
        
        # 统计
        hardlink_count = sum(1 for m in media_list if m.is_hardlink)
        
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
            total_size = sum(m.size_bytes for m in files if not m.is_hardlink)
            # 类型名首字母大写
            display_name = type_name.upper() if type_name.lower() in ('nsfw', 'av', 'nsfe') else type_name.title()
            lines.append(f"| {display_name} | {file_count} 个 | {format_size(total_size)} |")
        
        lines.append("")
        if hardlink_count > 0:
            lines.append(f"*检测到 {hardlink_count} 个硬链接文件*\n")
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
                    size = "-" if info.is_hardlink else format_size(info.size_bytes)
                    ext = info.extension.upper().lstrip('.') if info.extension else "-"
                    res = info.resolution or "-"
                    folder = str(Path(info.filepath).parent).replace('\\', '/')
                    
                    note = ""
                    if info.is_hardlink:
                        note = "🔗 硬链接"
                    elif info.is_disc:
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
