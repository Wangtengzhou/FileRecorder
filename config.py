"""
FileRecorder 配置管理模块
"""
import json
import sys
from pathlib import Path


class Config:
    """应用程序配置管理"""
    
    # 默认配置
    DEFAULTS = {
        # 数据库配置
        "database": {
            "path": "data/fileindex.db"
        },
        # AI 接口配置 (默认为空，需用户在界面设置)
        "ai": {
            "api_key": "",
            "base_url": "",      # 自定义接口地址，如 https://api.deepseek.com
            "model": "gpt-4o-mini",
            "tpm_limit": 60000,   # 每分钟最大令牌数
            "rpm_limit": 60,      # 每分钟最大请求数
            "timeout": 60         # API 请求超时(秒)
        },
        # 扫描配置
        "scanner": {
            "timeout_seconds": 5,  # 网络路径超时
            "batch_size": 1000,    # 批量插入大小
            "ignore_patterns": [   # 忽略的文件/目录模式
                ".*",              # 隐藏文件
                "$RECYCLE.BIN",
                "System Volume Information",
                "Thumbs.db"
            ]
        },
        # 界面配置
        "ui": {
            "window_width": 1200,
            "window_height": 800,
            "remember_window_size": True,
            "close_to_tray": None,              # None=未设置(每次询问), True=最小化到托盘, False=退出
            "close_behavior_remembered": False, # 是否记住关闭行为
            "theme": "auto"                     # auto=跟随系统, light=浅色, dark=深色
        }
    }
    
    def __init__(self, config_path: str = None):
        """
        初始化配置管理器
        
        Args:
            config_path: 配置文件路径，默认为程序目录下的 config.json
        """
        # 获取程序根目录
        if getattr(sys, 'frozen', False):
            # 打包后，使用 exe 所在目录
            self.base_dir = Path(sys.executable).parent
        else:
            # 开发环境，使用当前文件所在目录
            self.base_dir = Path(__file__).parent
            
        if config_path:
            self.config_path = Path(config_path)
        else:
            self.config_path = self.base_dir / "config.json"
        
        self._config = self.DEFAULTS.copy()
        self.load()
    
    def load(self) -> None:
        """从文件加载配置"""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    saved_config = json.load(f)
                    self._deep_update(self._config, saved_config)
            except (json.JSONDecodeError, IOError) as e:
                # 使用 print 而非 logger，因为 config.py 在 logger 之前加载
                print(f"加载配置失败: {e}，使用默认配置")
    
    def save(self) -> None:
        """保存配置到文件"""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self._config, f, indent=4, ensure_ascii=False)
    
    def get(self, *keys, default=None):
        """
        获取配置值
        
        Args:
            keys: 配置键路径，如 get("ai", "api_key")
            default: 默认值
        
        Returns:
            配置值或默认值
        """
        value = self._config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value
    
    def set(self, *keys, value) -> None:
        """
        设置配置值
        
        Args:
            keys: 配置键路径
            value: 要设置的值
        """
        if len(keys) < 1:
            return
        
        config = self._config
        for key in keys[:-1]:
            if key not in config:
                config[key] = {}
            config = config[key]
        config[keys[-1]] = value
    
    def _deep_update(self, base: dict, update: dict) -> None:
        """深度更新字典"""
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_update(base[key], value)
            else:
                base[key] = value
    
    @property
    def database_path(self) -> Path:
        """获取数据库完整路径"""
        db_path = self.get("database", "path")
        path = Path(db_path)
        if not path.is_absolute():
            path = self.base_dir / path
        return path
    
    @property
    def ai_configured(self) -> bool:
        """检查AI是否已配置"""
        return bool(self.get("ai", "api_key"))


# 全局配置实例
config = Config()
