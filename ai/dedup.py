"""
硬链接检测模块
检测同一文件的硬链接，用于识别重复文件
"""
import os
from pathlib import Path
from collections import defaultdict
from typing import Optional

from ai.parser import MediaInfo


class HardlinkDetector:
    """硬链接检测器"""
    
    def __init__(self):
        self.file_id_map: dict[tuple, list[MediaInfo]] = defaultdict(list)
    
    def detect_hardlinks(self, media_list: list[MediaInfo]) -> list[MediaInfo]:
        """
        检测硬链接，标记重复文件
        
        Args:
            media_list: 媒体文件列表
            
        Returns:
            处理后的列表（已标记硬链接）
        """
        self.file_id_map.clear()
        
        # 按 file_id 分组
        for info in media_list:
            if info.file_id:
                self.file_id_map[info.file_id].append(info)
        
        # 标记硬链接
        for file_id, files in self.file_id_map.items():
            if len(files) > 1:
                # 第一个作为主文件，其他标记为硬链接
                primary = files[0]
                for i, other in enumerate(files[1:], 1):
                    other.is_hardlink = True
                    other.hardlink_target = primary.filepath
        
        return media_list
    
    def get_hardlink_groups(self) -> list[list[MediaInfo]]:
        """获取所有硬链接分组"""
        return [files for files in self.file_id_map.values() if len(files) > 1]
    
    def get_hardlink_count(self) -> int:
        """获取硬链接组数"""
        return sum(1 for files in self.file_id_map.values() if len(files) > 1)


def get_file_id(filepath: str) -> Optional[tuple]:
    """
    获取文件唯一标识（设备号, inode）
    硬链接的文件具有相同的 file_id
    
    Args:
        filepath: 文件路径
        
    Returns:
        (st_dev, st_ino) 元组，失败返回 None
    """
    try:
        stat = os.stat(filepath)
        return (stat.st_dev, stat.st_ino)
    except Exception:
        return None


def find_duplicate_files(directory: str, recursive: bool = True) -> dict[tuple, list[str]]:
    """
    查找目录中的硬链接文件
    
    Args:
        directory: 目录路径
        recursive: 是否递归
        
    Returns:
        {file_id: [filepath1, filepath2, ...]}
    """
    file_id_map = defaultdict(list)
    
    path = Path(directory)
    items = path.rglob('*') if recursive else path.iterdir()
    
    for item in items:
        if item.is_file():
            file_id = get_file_id(str(item))
            if file_id:
                file_id_map[file_id].append(str(item))
    
    # 只返回有重复的
    return {fid: paths for fid, paths in file_id_map.items() if len(paths) > 1}
