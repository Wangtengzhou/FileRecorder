"""
媒体识别 Prompt 模板
独立文件，便于调试和自定义
"""

# ====================
# 系统 Prompt（强制）
# ====================

SYSTEM_PROMPT = """你是一个媒体文件识别专家。根据文件名和信息，识别视频内容并返回结构化数据。

规则：
1. 识别影片/剧集的真实名称（中英文）
2. 判断内容类型（电影/电视剧/动漫/纪录片/NSFW/其他）
3. 提取年份、分辨率、来源等信息
4. 同一影片的不同版本归为同一标题
5. 需要剔除文件中的样片和预告片等信息，只返回正片的数据。

特别注意：
- 不同命名格式可能是同一影片，如"复仇者联盟4"和"Avengers.Endgame"
- 番号格式如 ABC-123 归类为 NSFW
- 电视剧识别 S01E01 格式

返回严格 JSON 格式。"""


# ====================
# 用户 Prompt 模板
# ====================

USER_PROMPT_TEMPLATE = """分析以下视频文件，返回 JSON：

文件列表：
{file_list}

{user_hint}

返回格式（严格 JSON，不要其他内容）：
{{
  "results": [
    {{
      "index": 1,
      "title_cn": "中文名",
      "title_en": "English Name", 
      "year": 2024,
      "type": "电影",
      "resolution": "4K",
      "source": "BluRay"
    }}
  ]
}}

type 可选值：电影、电视剧、动漫、纪录片、综艺、NSFW、其他
如果是电视剧或纪录片，额外返回 season 和 episode 字段"""


# ====================
# 默认用户提示
# ====================

DEFAULT_HINT = ""

# 预设提示选项
HINT_PRESETS = {
    "动漫": "这些文件是动漫/动画作品",
    "日剧": "这些文件是日本电视剧",
    "纪录片": "这些文件是纪录片",
    "NSFW": "这些文件是成人内容",
}


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
    
    # 组合用户提示
    hint_section = ""
    if user_hint:
        hint_section = f"额外提示：{user_hint}"
    
    # 填充模板
    user_content = USER_PROMPT_TEMPLATE.format(
        file_list=file_list_str,
        user_hint=hint_section
    )
    
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content}
    ]
