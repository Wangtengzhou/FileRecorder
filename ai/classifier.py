"""
AI 分类服务模块
所有文件都交给 AI 识别，本地只做预处理
"""
import json
import re
import time
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from config import config
from ai.client import AIClient
from ai.parser import MediaInfo, format_size
from ai.prompts import build_prompt, build_context_prompt

# Debug 开关 - 开发时设为 True，发布时设为 False
DEBUG_CLASSIFIER = True

# 标准番号格式正则：
# 1. 字母开头 + 短横 + 数字（如 ADN-256）
# 2. 字母开头 + 数字（无短横，如 gachip318）
# 3. FC2-PPV 格式
RE_VALID_CODE = re.compile(
    r'^[A-Za-z]{2,6}-\d{3,7}$|'    # ABC-123 格式
    r'^[A-Za-z]{2,8}\d{3,5}$|'      # ABC123 格式（无短横）
    r'^FC2-?PPV-?\d{5,7}$',         # FC2-PPV 格式
    re.IGNORECASE
)


@dataclass
class ClassifyOptions:
    """分类选项"""
    # 用户自定义提示
    hint: str = ""
    # 每批处理数量
    batch_size: int = 30
    # Debug 模式
    debug: bool = False
    # 是否跳过预告片/样片
    skip_trailers: bool = True


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
        messages = build_prompt(file_info, options.hint, options.skip_trailers)
        
        # 从配置读取 temperature（使用低温度和固定 seed 提高结果一致性）
        temperature = config.get("ai", "temperature", default=0.1)
        response = self.ai.chat(messages, temperature=temperature, seed=42)
        
        if not response:
            # 返回错误信息供外部使用
            return {"error": self.ai.last_error or "API 请求失败"}
        
        # 解析响应
        try:
            result = self._parse_response(response)
            return result
        except Exception as e:
            print(f"解析 AI 响应失败: {e}")
            print(f"原始响应: {response[:500]}...")
            return {"error": f"解析响应失败: {e}"}
    
    def classify_with_context(self, media_list: list[MediaInfo], 
                              options: ClassifyOptions = None) -> dict:
        """
        二次检测：带路径上下文的分类
        
        Args:
            media_list: 需要二次检测的文件列表
            options: 分类选项（包含用户自定义 hint）
            
        Returns:
            分类结果
        """
        options = options or ClassifyOptions()
        
        # 构建带文件夹信息和首次识别类型的文件列表
        file_info = []
        for i, info in enumerate(media_list, 1):
            # 提取上级文件夹名
            parent_folder = Path(info.filepath).parent.name
            # 包含首次识别的类型，帮助 AI 保持一致性
            first_pass_type = info.media_type if info.media_type and info.media_type != "unknown" else "待定"
            file_info.append(
                f"{i}. {info.filename} ({format_size(info.size_bytes)}) [文件夹: {parent_folder}] [首次判断: {first_pass_type}]"
            )
        
        if DEBUG_CLASSIFIER:
            print(f"  📝 二次检测请求: {len(file_info)} 个文件")
        
        # 使用二次检测专用 Prompt
        messages = build_context_prompt(file_info, options.hint)
        
        # 调用 AI（使用较低温度提高一致性）
        response = self.ai.chat(messages, temperature=0.2)
        
        if not response:
            return {"error": self.ai.last_error or "API 请求失败"}
        
        if DEBUG_CLASSIFIER:
            # 显示响应的前200字符
            preview = response[:200].replace('\n', ' ')
            print(f"  📨 二次检测响应预览: {preview}...")
        
        # 解析响应
        try:
            result = self._parse_response(response)
            if DEBUG_CLASSIFIER:
                results_list = result.get("results", []) or result.get("files", [])
                print(f"  📊 解析结果: {len(results_list)} 个项目")
            return result
        except Exception as e:
            print(f"解析二次检测响应失败: {e}")
            if DEBUG_CLASSIFIER:
                print(f"  原始响应: {response[:500]}")
            return {"error": f"解析响应失败: {e}"}
    
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
        
        parsed = json.loads(response)
        
        # 如果 AI 直接返回了列表而不是字典，包装成标准格式
        if isinstance(parsed, list):
            return {"results": parsed}
        
        return parsed
    
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
        
        # 兼容 AI 返回 "results" 或 "files" 两种格式
        results = ai_result.get("results", []) or ai_result.get("files", [])
        
        # 记录已处理的索引
        processed_indices = set()
        
        for item in results:
            idx = item.get("index", 0)
            if 1 <= idx <= len(media_list):
                processed_indices.add(idx)
                info = media_list[idx - 1]
                # 新格式使用单一 title 字段
                info.title = item.get("title", "") or item.get("title_cn", "") or item.get("title_en", "")
                info.title_en = item.get("title_en", "")  # 兼容旧格式
                info.year = item.get("year")
                info.media_type = self._normalize_type(item.get("type", "其他"))
                info.resolution = item.get("resolution", "")
                info.source = item.get("source", "")
                info.season = item.get("season")
                info.episode = item.get("episode")
                # NSFW 番号 - 验证格式是否正确
                raw_code = item.get("code", "") or ""
                if raw_code and RE_VALID_CODE.match(raw_code):
                    info.code = raw_code.upper()
                else:
                    info.code = ""  # 无效格式不设置
                # 新增字段
                info.skip = item.get("skip", False)
                info.needs_context = item.get("needs_context", False)
                
                # 如果需要二次检测，则不应该跳过
                if info.needs_context:
                    info.skip = False
                
                info.parsed = True
                info.needs_ai = False
                
                # Debug 输出
                if DEBUG_CLASSIFIER:
                    if info.skip:
                        print(f"  🚫 SKIP: {info.filename}")
                    elif info.needs_context:
                        print(f"  🔍 需要二次检测: {info.filename}")
                    if info.code:
                        print(f"  📌 番号: {info.code} ← {info.filename}")
                    elif raw_code and not info.code:
                        print(f"  📝 未检测到有效番号: {info.filename}")
        
        # 检查是否有文件未被 AI 返回（可能被内容审查过滤）
        # 这些文件自动标记为需要二次检测
        for i, info in enumerate(media_list, 1):
            if i not in processed_indices and not info.parsed:
                info.needs_context = True
                info.parsed = True  # 标记为已处理，避免重复
                if DEBUG_CLASSIFIER:
                    print(f"  ⚠️ AI未返回结果，自动进入二次检测: {info.filename}")
        
        return media_list
    
    def _normalize_type(self, type_str: str) -> str:
        """
        标准化类型字符串
        
        现在直接返回 AI 给的类型（转为小写），不再硬编码映射。
        这样可以支持用户自定义的任意标签。
        """
        if not type_str:
            return "other"
        
        # 直接返回小写处理后的类型
        # 这样用户自定义的标签如 "nsfe av" 可以正确保留
        return type_str.lower().strip()


class BatchClassifier:
    """批量分类处理器"""
    
    def __init__(self, classifier: MediaClassifier = None):
        self.classifier = classifier or MediaClassifier()
    
    def process(self, media_list: list[MediaInfo],
                options: ClassifyOptions = None,
                progress_callback=None,
                cancel_check=None) -> list[MediaInfo]:
        """
        处理整个媒体列表（全部交给 AI）
        
        Args:
            media_list: 媒体列表
            options: 分类选项
            progress_callback: 进度回调 (current, total, message)
            cancel_check: 取消检查函数，返回 True 表示应取消
            
        Returns:
            处理后的列表
        """
        options = options or ClassifyOptions()
        
        # 全部文件都需要 AI 处理
        total = len(media_list)
        if total == 0:
            return media_list
        
        processed = 0
        failed_files = 0  # 追踪因 API 错误未能处理的文件数
        error_messages = []  # 收集错误信息
        
        # 分批处理
        for i in range(0, total, options.batch_size):
            # 检查是否取消
            if cancel_check and cancel_check():
                if progress_callback:
                    progress_callback(processed, total, "⏹️ 已取消")
                return media_list
            
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
                
                # 检查是否有 API 错误
                if "error" in result:
                    error_msg = result["error"]
                    if progress_callback:
                        progress_callback(processed, total, f"  ❌ 批次 {i+1}-{batch_end} 失败: {error_msg}")
                    print(f"批次 {i+1}-{batch_end} API 错误: {error_msg}")
                    failed_files += len(batch)
                    if error_msg not in error_messages:
                        error_messages.append(error_msg)
                else:
                    # 应用结果
                    self.classifier.apply_results(batch, result)
            except Exception as e:
                if progress_callback:
                    progress_callback(processed, total, f"  ⚠️ 批次 {i+1}-{batch_end} 出错: {e}")
                failed_files += len(batch)
                if str(e) not in error_messages:
                    error_messages.append(str(e))
            
            processed += len(batch)
            
            # TPM 限速：批次间延迟
            batch_delay = config.get("ai", "batch_delay_ms", default=500)
            if batch_delay > 0 and i + options.batch_size < total:
                time.sleep(batch_delay / 1000.0)

        
        # ====================
        # 二次检测流程
        # ====================
        needs_context = [m for m in media_list if getattr(m, 'needs_context', False)]
        
        if needs_context:
            if progress_callback:
                progress_callback(total, total, f"二次检测中: {len(needs_context)} 个文件需要上下文...")
            
            if DEBUG_CLASSIFIER:
                print(f"\n🔄 开始二次检测: {len(needs_context)} 个文件")
            
            # 分批进行二次检测
            for i in range(0, len(needs_context), options.batch_size):
                # 检查是否取消
                if cancel_check and cancel_check():
                    if progress_callback:
                        progress_callback(total, total, "⏹️ 已取消")
                    return media_list
                
                batch = needs_context[i:i + options.batch_size]
                batch_end = min(i + options.batch_size, len(needs_context))
                
                if DEBUG_CLASSIFIER:
                    print(f"  📦 二次检测批次: {i+1}-{batch_end} / {len(needs_context)}")
                
                if progress_callback:
                    progress_callback(
                        total, total,
                        f"二次检测: {i+1}-{batch_end} / {len(needs_context)}"
                    )

                
                try:
                    result = self.classifier.classify_with_context(batch, options)
                    
                    if "error" in result:
                        if progress_callback:
                            progress_callback(total, total, f"  ❌ 二次检测失败: {result['error']}")
                        if DEBUG_CLASSIFIER:
                            print(f"  ❌ 二次检测失败: {result['error']}")
                    else:
                        # 应用结果（会覆盖之前的 needs_context 状态）
                        results_count = len(result.get("results", []) or result.get("files", []))
                        if DEBUG_CLASSIFIER:
                            print(f"  ✅ 二次检测完成: 收到 {results_count} 个结果")
                        
                        self.classifier.apply_results(batch, result)
                        # 清除 needs_context 标记
                        for item in batch:
                            item.needs_context = False
                except Exception as e:
                    if progress_callback:
                        progress_callback(total, total, f"  ⚠️ 二次检测出错: {e}")
                    if DEBUG_CLASSIFIER:
                        print(f"  ⚠️ 二次检测出错: {e}")
                    failed_files += len(batch)
                    if str(e) not in error_messages:
                        error_messages.append(str(e))
        
        # 输出完成信息和错误汇总
        if progress_callback:
            progress_callback(total, total, "AI 识别完成")
            
            # 如果有错误，显示汇总
            if failed_files > 0:
                progress_callback(total, total, f"⚠️ 网络/API 问题导致 {failed_files} 个文件未能识别")
                for err in error_messages[:3]:  # 最多显示3条错误
                    progress_callback(total, total, f"   原因: {err}")
        
        return media_list
