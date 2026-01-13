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
        # 分组
        movie_groups = self._group_movies(media_list)
        tv_groups = self._group_tv_shows(media_list)
        anime_groups = self._group_anime(media_list)  # 动漫
        documentary_list = [m for m in media_list if m.media_type == "documentary"]  # 纪录片
        nsfw_standard = [m for m in media_list if m.media_type == "nsfw" and m.code]
        nsfw_custom = [m for m in media_list if m.media_type == "nsfw" and not m.code]
        others = [m for m in media_list if m.media_type in ("other", "unknown", None, "")]
        
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
        lines.append("| 类型 | 数量 | 文件数 | 大小 |")
        lines.append("|------|------|--------|------|")
        
        # 动态生成统计表，只显示非零分类
        stats_rows = []
        
        # 电影
        movie_count = len(movie_groups)
        movie_files = sum(g.file_count for g in movie_groups.values())
        movie_size = sum(g.total_size for g in movie_groups.values())
        if movie_count > 0:
            stats_rows.append(f"| 电影 | {movie_count} 部 | {movie_files} 个 | {format_size(movie_size)} |")
        
        # 电视剧
        tv_count = len(tv_groups)
        tv_episodes = sum(sum(len(eps) for eps in g.seasons.values()) for g in tv_groups.values())
        tv_size = sum(sum(e.size_bytes for eps in g.seasons.values() for e in eps if not e.is_hardlink) 
                      for g in tv_groups.values())
        if tv_count > 0:
            stats_rows.append(f"| 电视剧 | {tv_count} 部 | {tv_episodes} 集 | {format_size(tv_size)} |")
        
        # 动漫
        anime_count = len(anime_groups)
        anime_files = sum(g.file_count for g in anime_groups.values())
        anime_size = sum(g.total_size for g in anime_groups.values())
        if anime_count > 0:
            stats_rows.append(f"| 动漫 | {anime_count} 部 | {anime_files} 个 | {format_size(anime_size)} |")
        
        # 纪录片
        documentary_count = len(documentary_list)
        documentary_size = sum(m.size_bytes for m in documentary_list if not m.is_hardlink)
        if documentary_count > 0:
            stats_rows.append(f"| 纪录片 | {documentary_count} 部 | {documentary_count} 个 | {format_size(documentary_size)} |")
        
        # NSFW
        nsfw_count = len(nsfw_standard) + len(nsfw_custom)
        nsfw_size = sum(m.size_bytes for m in nsfw_standard + nsfw_custom if not m.is_hardlink)
        if nsfw_count > 0:
            stats_rows.append(f"| NSFW | {nsfw_count} 项 | {nsfw_count} 个 | {format_size(nsfw_size)} |")
        
        # 其他
        other_count = len(others)
        other_size = sum(m.size_bytes for m in others if not m.is_hardlink)
        if other_count > 0:
            stats_rows.append(f"| 其他 | {other_count} 项 | {other_count} 个 | {format_size(other_size)} |")
        
        lines.extend(stats_rows)
        
        lines.append("")
        if hardlink_count > 0:
            lines.append(f"*检测到 {hardlink_count} 个硬链接文件*\n")
        lines.append("")
        
        # 电影列表
        if movie_groups:
            lines.append("---\n")
            lines.append("## 电影\n")
            
            for title, group in sorted(movie_groups.items(), key=lambda x: x[0]):
                year_str = f" ({group.year})" if group.year else ""
                lines.append(f"### {group.title}{year_str}\n")
                
                lines.append("| # | 文件名 | 大小 | 格式 | 分辨率 | 位置 | 备注 |")
                lines.append("|---|--------|------|------|--------|------|------|")
                
                for i, info in enumerate(group.files, 1):
                    size = "-" if info.is_hardlink else format_size(info.size_bytes)
                    ext = info.extension.upper().lstrip('.') if info.extension else "-"
                    res = info.resolution or "-"
                    folder = str(Path(info.filepath).parent).replace('\\', '/')
                    
                    note = ""
                    if info.is_hardlink:
                        note = f"🔗 硬链接"
                    elif info.is_disc:
                        note = f"{info.disc_type}原盘"
                    elif info.hdr:
                        note = "HDR"
                    
                    lines.append(f"| {i} | {info.filename} | {size} | {ext} | {res} | {folder}/ | {note} |")
                
                lines.append("")
        
        # 电视剧列表
        if tv_groups:
            lines.append("---\n")
            lines.append("## 电视剧\n")
            
            for title, group in sorted(tv_groups.items(), key=lambda x: x[0]):
                lines.append(f"### {group.title}\n")
                
                for season in sorted(group.seasons.keys()):
                    episodes = group.seasons[season]
                    ep_count = len(episodes)
                    missing = group.get_missing_episodes(season)
                    
                    status = "✓" if not missing else f"⚠️ 缺 {', '.join(f'E{e:02d}' for e in missing)}"
                    lines.append(f"**Season {season}** - {ep_count} 集 {status}\n")
                    
                    lines.append("| 集数 | 文件名 | 大小 | 格式 | 位置 |")
                    lines.append("|------|--------|------|------|------|")
                    
                    for info in sorted(episodes, key=lambda x: x.episode or 0):
                        ep_str = f"E{info.episode:02d}" if info.episode else "-"
                        size = format_size(info.size_bytes)
                        ext = info.extension.upper().lstrip('.') if info.extension else "-"
                        folder = str(Path(info.filepath).parent).replace('\\', '/')
                        
                        lines.append(f"| {ep_str} | {info.filename} | {size} | {ext} | {folder}/ |")
                    
                    lines.append("")
        
        # 动漫列表
        if anime_groups:
            lines.append("---\n")
            lines.append("## 动漫\n")
            
            for title, group in sorted(anime_groups.items(), key=lambda x: x[0]):
                year_str = f" ({group.year})" if group.year else ""
                lines.append(f"### {group.title}{year_str}\n")
                
                lines.append("| # | 文件名 | 大小 | 格式 | 分辨率 | 位置 | 备注 |")
                lines.append("|---|--------|------|------|--------|------|------|")
                
                for i, info in enumerate(group.files, 1):
                    size = "-" if info.is_hardlink else format_size(info.size_bytes)
                    ext = info.extension.upper().lstrip('.') if info.extension else "-"
                    res = info.resolution or "-"
                    folder = str(Path(info.filepath).parent).replace('\\', '/')
                    
                    note = ""
                    if info.is_hardlink:
                        note = f"🔗 硬链接"
                    elif info.is_disc:
                        note = f"{info.disc_type}原盘"
                    elif info.hdr:
                        note = "HDR"
                    
                    lines.append(f"| {i} | {info.filename} | {size} | {ext} | {res} | {folder}/ | {note} |")
                
                lines.append("")
        
        # NSFW 列表
        if nsfw_standard or nsfw_custom:
            lines.append("---\n")
            lines.append("## NSFW\n")
            
            if nsfw_standard:
                lines.append("### 标准番号\n")
                lines.append("| 番号 | 文件名 | 大小 | 格式 | 位置 |")
                lines.append("|------|--------|------|------|------|")
                
                for info in sorted(nsfw_standard, key=lambda x: x.code):
                    size = format_size(info.size_bytes)
                    ext = info.extension.upper().lstrip('.') if info.extension else "-"
                    folder = str(Path(info.filepath).parent).replace('\\', '/')
                    
                    lines.append(f"| {info.code} | {info.filename} | {size} | {ext} | {folder}/ |")
                
                lines.append("")
            
            if nsfw_custom:
                lines.append("### 自定义命名\n")
                lines.append("| 文件名 | 大小 | 格式 | 位置 |")
                lines.append("|--------|------|------|------|")
                
                for info in sorted(nsfw_custom, key=lambda x: x.filename):
                    size = format_size(info.size_bytes)
                    ext = info.extension.upper().lstrip('.') if info.extension else "-"
                    folder = str(Path(info.filepath).parent).replace('\\', '/')
                    
                    lines.append(f"| {info.filename} | {size} | {ext} | {folder}/ |")
                
                lines.append("")
        
        # 其他
        if others:
            lines.append("---\n")
            lines.append("## 其他视频\n")
            lines.append("| 文件名 | 大小 | 格式 | 位置 |")
            lines.append("|--------|------|------|------|")
            
            for info in sorted(others, key=lambda x: x.filename):
                size = format_size(info.size_bytes)
                ext = info.extension.upper().lstrip('.') if info.extension else "-"
                folder = str(Path(info.filepath).parent).replace('\\', '/')
                
                lines.append(f"| {info.filename} | {size} | {ext} | {folder}/ |")
            
            lines.append("")
        
        return "\n".join(lines)
    
    def _group_movies(self, media_list: list[MediaInfo]) -> dict[str, MediaGroup]:
        """按电影分组"""
        groups = {}
        
        for info in media_list:
            if info.media_type != "movie":
                continue
            
            # 使用标题作为分组键
            key = info.title.lower() if info.title else info.filename.lower()
            
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
