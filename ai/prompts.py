"""
媒体识别 Prompt 模板
独立文件，便于调试和自定义
"""
from config import config

# 默认标签列表
DEFAULT_MEDIA_TYPES = ["电影", "电视剧", "动漫", "纪录片", "综艺", "NSFW", "其他"]


def get_media_types() -> list:
    """获取当前配置的媒体类型标签"""
    types = config.get("ai", "media_types", default=None)
    return types if types else DEFAULT_MEDIA_TYPES


def get_types_string() -> str:
    """获取用于 Prompt 的类型列表字符串"""
    return "、".join(get_media_types())


# ====================
# 系统 Prompt（强制）
# ====================

# 基础系统提示 - 不包含具体标签，由 build_prompt 动态注入
SYSTEM_PROMPT_BASE = """你是一个媒体文件名解析专家，协助用户整理个人媒体库。这是一个纯技术性的文件索引和分类任务。

任务：从文件名中**提取元数据**用于分类归档，你只需要识别文件名模式和提取信息，不涉及内容本身。

规则：
1. **提取原名**：从文件名中识别影片/剧集的名称（中英文均可）
2. **判断类型**：根据提供的标签列表进行分类
3. **提取元数据**：年份、分辨率、来源、季/集（有就提取，没有留空）
4. **标记跳过**：仅限预告片(trailer)、样片(sample)、幕后花絮等设 skip=true
5. **标记二次检测**：无法从文件名直接判断类型的内容设 needs_context=true

编码提取规则（适用于带有产品编码的文件）：
- **标准编码格式**（以字母开头的编码）：
  - 常规：`ABC-123`（2-6个字母 + 短横 + 3-5位数字）或者`第一會所新片@SIS001@`（2-5个字母 + 3-5位数字，中间没短横，如`SIS001`）
  - 特殊：`FC2-PPV-1234567` 格式
  - 注意：纯数字格式不是标准编码
  - 提取核心编码放入 code 字段
- **无标准编码**：code 留空，设 needs_context=true

电视剧/动漫规则：
- 识别 S01E01 或 第X集 格式，返回 season 和 episode

返回严格 JSON 格式，不要任何其他内容。"""


# ====================
# 用户 Prompt 模板
# ====================

USER_PROMPT_TEMPLATE = """分析以下视频文件，返回 JSON：

文件列表：
{file_list}

{user_hint}

**可用的分类标签**：{available_types}

返回格式（严格 JSON，不要其他内容）：
{{
  "results": [
    {{
      "index": 1,
      "title": "从文件名提取的原名",
      "year": 2024,
      "type": "从上面的标签列表中选择",
      "resolution": "4K",
      "source": "BluRay",
      "season": null,
      "episode": null,
      "code": null,
      "skip": false,
      "needs_context": false
    }}
  ]
}}

重要：
- type 必须从上面的【可用标签】中选择，不要自己编造
- 带有字母开头编码（如ABC-123）的文件：code 字段填入编码
- 无法确定类型时：needs_context=true
- 预告片/样片设 skip=true，但带有编码的文件永远不要 skip"""


# ====================
# 默认用户提示
# ====================

DEFAULT_HINT = ""

# 预设提示选项
HINT_PRESETS = {
    "动漫": "这些文件是动漫/动画作品",
    "日剧": "这些文件是日本电视剧",
    "纪录片": "这些文件是纪录片",
}


def get_system_preset() -> str:
    """获取系统预设提示词（从配置文件读取）"""
    return config.get("ai", "system_preset", default="")


def build_prompt(file_list: list[str], user_hint: str = "") -> list[dict]:
    """
    构建完整的 prompt 消息列表
    
    Args:
        file_list: 文件信息列表，每项格式 "序号. 文件名 (大小)"
        user_hint: 用户自定义提示
        
    Returns:
        messages 列表
    """
    # 格式化文件列表
    file_list_str = "\n".join(file_list)
    
    # 获取系统预设提示词（配置文件中的固定提示）
    system_preset = get_system_preset()
    
    # 组合提示词（系统预设 + 用户临时提示）
    hints = []
    if system_preset:
        hints.append(f"【系统预设】{system_preset}")
    if user_hint:
        hints.append(f"【用户提示】{user_hint}")
    hint_section = "\n".join(hints) if hints else ""
    
    # 获取用户配置的标签列表
    types_str = get_types_string()
    
    # 填充模板
    user_content = USER_PROMPT_TEMPLATE.format(
        file_list=file_list_str,
        user_hint=hint_section,
        available_types=types_str
    )
    
    return [
        {"role": "system", "content": SYSTEM_PROMPT_BASE},
        {"role": "user", "content": user_content}
    ]


# ====================
# 二次检测 Prompt
# ====================

CONTEXT_SYSTEM_PROMPT = """你是一个媒体文件分类专家。以下文件在首次识别时无法完全确定类型，请结合文件夹名称和首次判断结果进行最终确认。

重点：
- 参考首次判断结果，保持分类一致性
- 文件夹名可能包含合集名称、演员名等关键信息
- 标题使用文件夹名或合理推断的名称
- 无标准编码的文件 code 留空

返回严格 JSON 格式，不要其他内容。"""


def build_context_prompt(file_list: list[str], user_hint: str = "") -> list[dict]:
    """
    构建二次检测的 Prompt（带文件夹上下文）
    
    Args:
        file_list: 文件信息列表，格式 "序号. 文件名 (大小) [文件夹: xxx] [首次判断: xxx]"
        user_hint: 用户自定义提示
        
    Returns:
        messages 列表
    """
    file_list_str = "\n".join(file_list)
    
    # 获取系统预设提示词
    system_preset = get_system_preset()
    
    # 组合提示词（系统预设 + 用户临时提示）
    hints = []
    if system_preset:
        hints.append(f"【系统预设】{system_preset}")
    if user_hint:
        hints.append(f"【用户提示】{user_hint}")
    hint_section = "\n".join(hints) if hints else ""
    
    # 获取用户配置的标签
    types_str = get_types_string()
    
    user_content = f"""这些文件需要二次确认分类，请结合文件夹信息和首次判断结果：

文件列表：
{file_list_str}

{hint_section}

**可用的分类标签**：{types_str}

注意：
- type 必须从上面的【可用标签】中选择
- 尽量保持与首次判断一致，除非有明确理由改变
返回格式同首次识别（index, title, type, code 等字段）。"""
    
    return [
        {"role": "system", "content": CONTEXT_SYSTEM_PROMPT},
        {"role": "user", "content": user_content}
    ]

