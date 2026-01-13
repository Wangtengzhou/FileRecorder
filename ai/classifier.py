"""
AI 分类服务模块
所有文件都交给 AI 识别，本地只做预处理
"""
import json
from typing import Optional
from dataclasses import dataclass

from ai.client import AIClient
from ai.parser import MediaInfo, format_size
from ai.prompts import build_prompt, SYSTEM_PROMPT


@dataclass
class ClassifyOptions:
    """分类选项"""
    # 用户自定义提示
    hint: str = ""
    # 每批处理数量
    batch_size: int = 30


class MediaClassifier:
    """媒体分类服务"""
    
    def __init__(self, ai_client: AIClient = None):
        self.ai = ai_client or AIClient()
    
    def classify_batch(self, media_list: list[MediaInfo], 
                       options: ClassifyOptions = None) -> dict:
        """
        批量分类媒体文件
        
        Args:
            media_list: 待分类的媒体列表
            options: 分类选项
            
        Returns:
            分类结果
        """
        options = options or ClassifyOptions()
        
        # 构建文件信息列表
        file_info = []
        for i, info in enumerate(media_list, 1):
            file_info.append(f"{i}. {info.filename} ({format_size(info.size_bytes)})")
        
        # 使用 prompts 模块构建消息
        messages = build_prompt(file_info, options.hint)
        
        # 调用 AI
        response = self.ai.chat(messages, temperature=0.3)
        
        if not response:
            return {}
        
        # 解析响应
        try:
            result = self._parse_response(response)
            return result
        except Exception as e:
            print(f"解析 AI 响应失败: {e}")
            print(f"原始响应: {response[:500]}...")
            return {}
    
    def _parse_response(self, response: str) -> dict:
        """解析 AI 响应"""
        response = response.strip()
        
        # 如果响应被 markdown 代码块包裹
        if "```" in response:
            lines = response.split('\n')
            json_lines = []
            in_json = False
            for line in lines:
                if line.strip().startswith("```json") or line.strip() == "```":
                    in_json = not in_json if line.strip() == "```" else True
                    continue
                if in_json:
                    json_lines.append(line)
            response = '\n'.join(json_lines)
        
        return json.loads(response)
    
    def apply_results(self, media_list: list[MediaInfo], 
                      ai_result: dict) -> list[MediaInfo]:
        """
        将 AI 结果应用到媒体列表
        
        Args:
            media_list: 原始媒体列表
            ai_result: AI 返回的结果
            
        Returns:
            更新后的媒体列表
        """
        if not ai_result:
            return media_list
        
        results = ai_result.get("results", [])
        
        for item in results:
            idx = item.get("index", 0)
            if 1 <= idx <= len(media_list):
                info = media_list[idx - 1]
                info.title = item.get("title_cn", "") or item.get("title_en", "")
                info.title_en = item.get("title_en", "")
                info.year = item.get("year")
                info.media_type = self._normalize_type(item.get("type", "其他"))
                info.resolution = item.get("resolution", "")
                info.source = item.get("source", "")
                info.season = item.get("season")
                info.episode = item.get("episode")
                info.parsed = True
                info.needs_ai = False
        
        return media_list
    
    def _normalize_type(self, type_str: str) -> str:
        """标准化类型字符串"""
        if not type_str:
            return "other"
        
        type_str = type_str.lower().strip()
        
        type_map = {
            # 电影
            "电影": "movie",
            "movie": "movie",
            "film": "movie",
            # 电视剧
            "电视剧": "tv",
            "tv": "tv",
            "剧集": "tv",
            "连续剧": "tv",
            "tv series": "tv",
            "tv show": "tv",
            # 动漫
            "动漫": "anime",
            "动画": "anime",
            "anime": "anime",
            "animation": "anime",
            # 纪录片
            "纪录片": "documentary",
            "documentary": "documentary",
            # 综艺
            "综艺": "variety",
            "variety": "variety",
            # NSFW
            "nsfw": "nsfw",
            "成人": "nsfw",
            "av": "nsfw",
            "adult": "nsfw",
            # 其他
            "其他": "other",
            "other": "other",
            "unknown": "other",
        }
        return type_map.get(type_str, "other")


class BatchClassifier:
    """批量分类处理器"""
    
    def __init__(self, classifier: MediaClassifier = None):
        self.classifier = classifier or MediaClassifier()
    
    def process(self, media_list: list[MediaInfo],
                options: ClassifyOptions = None,
                progress_callback=None) -> list[MediaInfo]:
        """
        处理整个媒体列表（全部交给 AI）
        
        Args:
            media_list: 媒体列表
            options: 分类选项
            progress_callback: 进度回调 (current, total, message)
            
        Returns:
            处理后的列表
        """
        options = options or ClassifyOptions()
        
        # 全部文件都需要 AI 处理
        total = len(media_list)
        if total == 0:
            return media_list
        
        processed = 0
        
        # 分批处理
        for i in range(0, total, options.batch_size):
            batch = media_list[i:i + options.batch_size]
            batch_end = min(i + options.batch_size, total)
            
            if progress_callback:
                progress_callback(
                    processed, total,
                    f"AI 识别中: {i+1}-{batch_end} / {total}"
                )
            
            # 调用 AI
            try:
                result = self.classifier.classify_batch(batch, options)
                # 应用结果
                self.classifier.apply_results(batch, result)
            except Exception as e:
                if progress_callback:
                    progress_callback(processed, total, f"  ⚠️ 批次 {i+1}-{batch_end} 出错: {e}")
            
            processed += len(batch)
        
        if progress_callback:
            progress_callback(total, total, "AI 识别完成")
        
        return media_list
