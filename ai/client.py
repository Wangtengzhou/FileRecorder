"""
AI 客户端模块 - 使用 OpenAI 兼容 API
"""
import json
import urllib.request
import urllib.error
from typing import Optional, Tuple

from config import config
from logger import get_logger

logger = get_logger("ai")

# 调试开关 - 开发时设为 True，发布时设为 False
DEBUG = True


class AIClient:
    """OpenAI 兼容 API 客户端"""
    
    def __init__(self, api_key: str = None, base_url: str = None, model: str = None):
        """
        初始化 AI 客户端
        
        Args:
            api_key: API 密钥，默认从配置读取
            base_url: API 地址，默认从配置读取
            model: 模型名称，默认从配置读取
        """
        self.api_key = api_key or config.get("ai", "api_key", default="")
        self.base_url = base_url or config.get("ai", "base_url", default="")
        self.model = model or config.get("ai", "model", default="gpt-4o-mini")
        self.last_error = None  # 存储最后一次错误信息
        
        # 默认使用 OpenAI 地址
        if not self.base_url:
            self.base_url = "https://api.openai.com/v1"
        
        # 确保 base_url 不以 / 结尾
        self.base_url = self.base_url.rstrip("/")
    
    def test_connection(self) -> Tuple[bool, str]:
        """
        测试 API 连接是否可用
        
        Returns:
            (成功, 消息)
        """
        if not self.api_key:
            return False, "API 密钥未配置"
        
        try:
            # 构建请求 URL
            url = f"{self.base_url}/chat/completions"
            
            data = {
                "model": self.model,
                "messages": [{"role": "user", "content": "Hi"}],
                "max_tokens": 5
            }
            
            # 调试输出
            if DEBUG:
                logger.debug("=" * 50)
                logger.debug("🔍 API 连接测试")
                logger.debug("=" * 50)
                logger.debug(f"📌 请求地址: {url}")
                logger.debug(f"📌 模型名称: {self.model}")
                logger.debug(f"📌 API 密钥: {self.api_key[:8]}...{self.api_key[-4:]}")
                logger.debug(f"📌 请求数据: {data}")
                logger.debug("-" * 50)
                logger.debug("⏳ 正在发送请求...")
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            
            req = urllib.request.Request(
                url,
                data=json.dumps(data).encode("utf-8"),
                headers=headers,
                method="POST"
            )
            
            with urllib.request.urlopen(req, timeout=10) as response:
                result = json.loads(response.read().decode("utf-8"))
                if DEBUG:
                    logger.debug(f"✅ 响应状态: {response.status}")
                    logger.debug(f"✅ 响应内容: {result}")
                    logger.debug("=" * 50)
                if "choices" in result:
                    return True, "API 连接成功"
                else:
                    return False, "响应格式异常"
                    
        except urllib.error.HTTPError as e:
            error_body = ""
            try:
                error_body = e.read().decode("utf-8")
                error_json = json.loads(error_body)
                msg = error_json.get("error", {}).get("message", str(e))
            except:
                msg = str(e)
            
            if DEBUG:
                logger.warning(f"❌ HTTP 错误: {e.code}")
                logger.warning(f"❌ 错误内容: {error_body or msg}")
                logger.debug("=" * 50)
            
            if e.code == 401:
                return False, "API 密钥无效"
            elif e.code == 404:
                return False, f"接口地址错误 (404): {url}"
            elif e.code == 429:
                return False, "请求过于频繁"
            else:
                return False, f"HTTP {e.code}: {msg}"
                
        except urllib.error.URLError as e:
            if DEBUG:
                logger.warning(f"❌ 网络错误: {e.reason}")
                logger.debug("=" * 50)
            return False, f"网络错误: {str(e.reason)}"
        except Exception as e:
            if DEBUG:
                logger.warning(f"❌ 未知错误: {e}")
                logger.debug("=" * 50)
            return False, f"未知错误: {str(e)}"
    
    def chat(self, messages: list, **kwargs) -> Optional[str]:
        """
        发送聊天请求
        
        Args:
            messages: 消息列表，格式 [{"role": "user", "content": "..."}]
            **kwargs: 其他参数如 temperature, max_tokens 等
            
        Returns:
            AI 回复内容，失败返回 None
        """
        if not self.api_key:
            return None
        
        try:
            url = f"{self.base_url}/chat/completions"
            
            data = {
                "model": self.model,
                "messages": messages,
                **kwargs
            }
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            
            req = urllib.request.Request(
                url,
                data=json.dumps(data).encode("utf-8"),
                headers=headers,
                method="POST"
            )
            
            # 从配置文件读取超时时间
            timeout = config.get("ai", "timeout", default=60)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
                return result["choices"][0]["message"]["content"]
        
        except urllib.error.HTTPError as e:
            error_msg = f"API 错误 HTTP {e.code}"
            try:
                error_body = e.read().decode("utf-8")
                error_json = json.loads(error_body)
                detail = error_json.get("error", {}).get("message", "")
                if detail:
                    error_msg = f"API 错误 HTTP {e.code}: {detail}"
            except:
                pass
            logger.warning(f"❌ {error_msg}")
            # 存储最后一次错误供外部读取
            self.last_error = error_msg
            return None
            
        except urllib.error.URLError as e:
            error_msg = f"网络错误: {e.reason}"
            logger.warning(f"❌ {error_msg}")
            self.last_error = error_msg
            return None
            
        except Exception as e:
            error_msg = f"AI 请求失败: {e}"
            logger.warning(f"❌ {error_msg}")
            self.last_error = error_msg
            return None


# 便捷函数
def test_api_connection(api_key: str = None, base_url: str = None, model: str = None) -> Tuple[bool, str]:
    """测试 API 连接"""
    client = AIClient(api_key, base_url, model)
    return client.test_connection()
