"""
FileRecorder - 智能文件索引助手
https://github.com/Wangtengzhou/FileRecorder

统一日志模块
"""
import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler


def setup_logging(log_dir: Path = None, console_level=logging.INFO, file_level=logging.DEBUG):
    """
    初始化日志系统
    
    Args:
        log_dir: 日志目录，默认为程序目录下的 data/
        console_level: 控制台日志级别，默认 INFO
        file_level: 文件日志级别，默认 DEBUG
    
    Returns:
        根 logger 实例
    """
    if log_dir is None:
        # 获取程序根目录
        if getattr(sys, 'frozen', False):
            base_dir = Path(sys.executable).parent
        else:
            base_dir = Path(__file__).parent
        log_dir = base_dir / "data"
    
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "filerecorder.log"
    
    # 根 logger
    root = logging.getLogger("FileRecorder")
    root.setLevel(logging.DEBUG)
    
    # 避免重复添加 handler
    if root.handlers:
        return root
    
    # 日志格式
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # 控制台 Handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(console_level)
    console.setFormatter(fmt)
    root.addHandler(console)
    
    # 文件 Handler (5MB 滚动, 保留 3 份)
    file_handler = RotatingFileHandler(
        log_file, maxBytes=5*1024*1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setLevel(file_level)
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)
    
    return root


def get_logger(name: str):
    """
    获取子 logger
    
    Args:
        name: 模块名称，如 "watcher", "scanner", "ai"
    
    Returns:
        logger 实例
    """
    return logging.getLogger(f"FileRecorder.{name}")
