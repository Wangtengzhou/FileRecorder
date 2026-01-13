"""
媒体文件名解析模块
提取年份、分辨率、来源、剧集编号、番号等信息
"""
import re
import os
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field


# 视频文件扩展名
VIDEO_EXTENSIONS = {
    '.mkv', '.mp4', '.avi', '.wmv', '.ts', '.m2ts', '.mov',
    '.flv', '.webm', '.rmvb', '.rm', '.mpg', '.mpeg', '.vob',
    '.iso'  # 光盘镜像
}

# 蓝光/DVD 原盘标识目录
DISC_FOLDERS = {'BDMV', 'VIDEO_TS', 'HVDVD_TS'}

# 跳过的文件名关键词（预告片、样片等）
SKIP_KEYWORDS = {'sample', 'trailer', 'preview', 'teaser', 'extra', 'bonus'}

# 最小文件大小（MB），小于此值跳过
MIN_FILE_SIZE_MB = 100


@dataclass
class MediaInfo:
    """媒体文件信息"""
    filename: str
    filepath: str
    size_bytes: int = 0
    extension: str = ""
    
    # 解析结果
    media_type: str = "unknown"  # movie, tv, nsfw, other
    title: str = ""
    title_en: str = ""
    year: Optional[int] = None
    resolution: str = ""        # 720p, 1080p, 4K, etc.
    source: str = ""            # BluRay, WEB-DL, HDTV, etc.
    codec: str = ""             # x264, x265, HEVC, etc.
    hdr: bool = False
    
    # 电视剧
    season: Optional[int] = None
    episode: Optional[int] = None
    
    # NSFW
    code: str = ""              # 番号
    
    # 原盘
    is_disc: bool = False
    disc_type: str = ""         # BluRay, DVD
    
    # 硬链接
    file_id: tuple = None       # (dev, inode)
    is_hardlink: bool = False
    hardlink_target: str = ""
    
    # 处理状态
    parsed: bool = False        # 预处理是否成功
    needs_ai: bool = False      # 是否需要 AI 处理


class MediaParser:
    """媒体文件名解析器"""
    
    # 正则表达式
    RE_YEAR = re.compile(r'[.\[\(]?(19|20)\d{2}[.\]\)]?')
    RE_RESOLUTION = re.compile(r'(720p|1080p|1080i|2160p|4K|UHD)', re.IGNORECASE)
    RE_SOURCE = re.compile(r'(BluRay|Blu-Ray|BDRip|BRRip|WEB-DL|WEBRip|HDTV|DVDRip|DVD|HDRip)', re.IGNORECASE)
    RE_CODEC = re.compile(r'(x264|x265|H\.?264|H\.?265|HEVC|AVC|MPEG-?2)', re.IGNORECASE)
    RE_HDR = re.compile(r'(HDR|HDR10|HDR10\+|Dolby.?Vision|DV)', re.IGNORECASE)
    
    # 剧集格式
    RE_EPISODE = re.compile(r'S(\d{1,2})E(\d{1,3})', re.IGNORECASE)
    RE_EPISODE_CN = re.compile(r'第(\d{1,3})[集话]')
    RE_EPISODE_EP = re.compile(r'EP?(\d{1,3})', re.IGNORECASE)
    
    # 番号格式（常见格式）
    RE_CODE = re.compile(r'\b([A-Z]{2,6})-?(\d{3,5})\b', re.IGNORECASE)
    
    def __init__(self, min_size_mb: int = 0):
        """min_size_mb: 最小文件大小（MB），0 表示不过滤"""
        self.min_size_bytes = min_size_mb * 1024 * 1024 if min_size_mb > 0 else 0
    
    def scan_directory(self, directory: str, recursive: bool = True) -> list[MediaInfo]:
        """扫描目录，收集视频文件（使用 os.walk）"""
        import os
        results = []
        
        # 统计
        file_count = 0
        video_count = 0
        skipped_small = 0
        skipped_sample = 0  # 样片/预告片
        
        # 先检测原盘目录
        disc_roots = set()
        
        try:
            # 使用 os.walk 递归遍历（参考 file_scanner.py）
            for dirpath, dirnames, filenames in os.walk(directory):
                # 检测原盘目录
                for dirname in dirnames:
                    if dirname.upper() in DISC_FOLDERS:
                        disc_roots.add(dirpath)
                        print(f"  检测到原盘: {dirpath} ({dirname})")
                
                # 检查当前目录是否在原盘内
                in_disc = False
                for disc_root in disc_roots:
                    if dirpath.lower().startswith(disc_root.lower()):
                        in_disc = True
                        break
                
                if in_disc:
                    continue  # 跳过原盘内部
                
                # 扫描文件
                for filename in filenames:
                    file_count += 1
                    filepath = os.path.join(dirpath, filename)
                    ext = os.path.splitext(filename)[1].lower()
                    
                    if ext in VIDEO_EXTENSIONS:
                        info, skip_reason = self._parse_file(Path(filepath))
                        if info:
                            video_count += 1
                            results.append(info)
                        elif skip_reason == 'small':
                            skipped_small += 1
                        elif skip_reason == 'sample':
                            skipped_sample += 1
                
                if not recursive:
                    break  # 不递归则只处理第一层
                    
        except Exception as e:
            print(f"扫描目录出错 {directory}: {e}")
        
        # 添加原盘记录
        for disc_path in disc_roots:
            info = self._parse_disc(Path(disc_path), "BluRay")
            if info:
                results.append(info)
        
        # 统计信息
        skip_info = []
        if skipped_sample > 0:
            skip_info.append(f"样片/预告片 {skipped_sample}")
        if skipped_small > 0:
            skip_info.append(f"小文件 {skipped_small}")
        skip_str = f", 跳过({', '.join(skip_info)})" if skip_info else ""
        print(f"扫描完成: 文件 {file_count}, 视频 {video_count}{skip_str}, 原盘 {len(disc_roots)}")
        
        return results
    
    def _find_disc_roots(self, directory: Path, recursive: bool) -> dict:
        """查找蓝光/DVD 原盘根目录"""
        disc_roots = {}
        
        if recursive:
            for item in directory.rglob('*'):
                if item.is_dir() and item.name.upper() in DISC_FOLDERS:
                    parent = item.parent
                    disc_type = 'BluRay' if item.name.upper() == 'BDMV' else 'DVD'
                    disc_roots[parent] = disc_type
                    print(f"  检测到原盘: {parent} ({disc_type})")
        
        return disc_roots
    
    def _is_subpath(self, path: Path, parent: Path) -> bool:
        """检查 path 是否在 parent 目录下（使用字符串比较避免 UNC 路径问题）"""
        try:
            # 使用字符串比较，避免 relative_to 在 UNC 路径上的问题
            path_str = str(path).lower().replace('/', '\\')
            parent_str = str(parent).lower().replace('/', '\\')
            # 确保 parent 以分隔符结尾
            if not parent_str.endswith('\\'):
                parent_str += '\\'
            return path_str.startswith(parent_str)
        except Exception:
            return False
    
    def _get_long_path(self, path: str) -> str:
        """获取 Windows 长路径格式（解决 260 字符限制）"""
        path = str(path)
        if path.startswith('\\\\?\\') or path.startswith('\\\\?\\UNC\\'):
            return path
        if path.startswith('\\\\'):
            # UNC 路径: \\server\share -> \\?\UNC\server\share
            return '\\\\?\\UNC\\' + path[2:]
        else:
            # 本地路径: C:\path -> \\?\C:\path
            return '\\\\?\\' + path
    
    def _parse_file(self, filepath: Path) -> tuple[Optional[MediaInfo], str]:
        """
        解析单个视频文件
        
        Returns:
            (MediaInfo, skip_reason) - info 为 None 时，skip_reason 表示跳过原因
        """
        try:
            # 使用长路径格式避免 Windows 260 字符限制
            long_path = self._get_long_path(str(filepath))
            stat = os.stat(long_path)
            size = stat.st_size
            
            filename = filepath.name
            filename_lower = filename.lower()
            
            # 跳过预告片、样片等
            if any(kw in filename_lower for kw in SKIP_KEYWORDS):
                return None, 'sample'
            
            # 跳过小文件
            if self.min_size_bytes > 0 and size < self.min_size_bytes:
                return None, 'small'
            
            info = MediaInfo(
                filename=filename,
                filepath=str(filepath),
                size_bytes=size,
                extension=filepath.suffix.lower(),
                file_id=(stat.st_dev, stat.st_ino)
            )
            
            # 解析文件名
            self._extract_info(info, filename)
            
            return info, ''
            
        except Exception as e:
            print(f"解析文件失败 {filepath}: {e}")
            return None, 'error'
    
    def _parse_disc(self, disc_path: Path, disc_type: str) -> MediaInfo:
        """解析原盘目录"""
        # 计算原盘总大小
        total_size = sum(f.stat().st_size for f in disc_path.rglob('*') if f.is_file())
        
        info = MediaInfo(
            filename=disc_path.name,
            filepath=str(disc_path),
            size_bytes=total_size,
            extension="",
            is_disc=True,
            disc_type=disc_type,
            media_type="movie"
        )
        
        # 从目录名提取信息
        self._extract_info(info, disc_path.name)
        info.source = disc_type
        
        return info
    
    def _extract_info(self, info: MediaInfo, text: str) -> None:
        """预处理：只提取不会出错的辅助信息，全部交给 AI 识别"""
        
        # 1. 提取分辨率（辅助信息）
        res_match = self.RE_RESOLUTION.search(text)
        if res_match:
            res = res_match.group(1).upper()
            if res in ('4K', 'UHD', '2160P'):
                info.resolution = '4K'
            else:
                info.resolution = res
        
        # 2. 提取来源（辅助信息）
        src_match = self.RE_SOURCE.search(text)
        if src_match:
            info.source = src_match.group(1)
        
        # 3. 提取编码（辅助信息）
        codec_match = self.RE_CODEC.search(text)
        if codec_match:
            info.codec = codec_match.group(1).upper()
        
        # 4. 检测 HDR（辅助信息）
        if self.RE_HDR.search(text):
            info.hdr = True
        
        # 全部文件都需要 AI 处理
        info.needs_ai = True
        info.title = self._clean_title(text)
    
    def _clean_title(self, text: str) -> str:
        """清理标题"""
        # 移除扩展名
        for ext in VIDEO_EXTENSIONS:
            if text.lower().endswith(ext):
                text = text[:-len(ext)]
        
        # 替换分隔符为空格
        text = re.sub(r'[._\-\[\]()]', ' ', text)
        
        # 移除多余空格
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text


def format_size(size_bytes: int) -> str:
    """格式化文件大小"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
