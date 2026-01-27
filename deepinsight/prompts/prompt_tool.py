import json
import random
import re
import threading
import logging
from deepinsight.prompts.prompt_demo import STYLE_CONFIG

logger = logging.getLogger(__name__)

def select_style_preset(params: dict) -> str:
    """
    动态选择写作风格预设

    Args:
        params (dict): 包含任务参数的字典，可能包含以下键：
            - category (str): 任务类别，如 "report", "guide", "news", "chat"
            - field (str): 任务领域，如 "tech", "lifestyle", "finance", "other"
            - depth (str): 任务深度，如 "shallow", "moderate", "deep"
            - audience (str): 目标受众，如 "general", "professional", "expert"
    Returns:
        str: 选择的写作风格预设标签
    """
    task = params.get("task", "")   # 原始查询
    category = params.get("category", "report")
    field = params.get("field", "other")
    depth = params.get("depth", "moderate")
    audience = params.get("audience", "general")

    if category == "chat":
        return "general_chat"
    
    if category == "news":
        return "news_bulletin"
    
    if category == "guide":
        if field == "lifestyle":
            return "lifestyle_guide"
        elif field == "tech":
            return "tech_tutorial"
        elif field == "finance":
            return "finance_professional"
    else:
        return "lifestyle_guide"
    
    if category == "report":
        if field == "tech" :
            if depth == "deep" or audience == "professional":
                return "tech_deep"
            else:
                return "tech_tutorial"
        elif field == "finance":
            return "finance_professional"
        elif field == "lifestyle":
            if audience == "enthusiast":
                return "lifestyle_guide"
            else:
                return "lifestyle_social"
        else:
            return "tech_deep"
        
    # 兜底
    field_fallback_map = {
        "tech": "tech_tutorial",
        "lifestyle": "lifestyle_guide",
        "finance": "finance_professional",
        "culture": "lifestyle_social",
        "news": "news_bulletin",
    }

    return field_fallback_map.get(field, "tech_deep")


def get_style_config(style_key: str) -> dict:
    """
    根据风格预设标签获取对应的写作风格配置

    Args:
        style_key (str): 风格预设标签

    Returns:
        dict: 包含 persona, structure, standards, format 等配置 
        对应的写作风格配置字典
    """
    if style_key in STYLE_CONFIG:
        return STYLE_CONFIG[style_key]
    
    logger.warning(f"未知的风格预设标签: {style_key}，使用默认配置")
    return STYLE_CONFIG.get("professional", {
        STYLE_CONFIG.get("tech_deep", {
        "persona": "你是一位专业的分析师，语言简洁准确。",
        "structure": "使用标准的报告格式：摘要 → 分析 → 结论",
        "standards": "引用权威数据，保持客观中立",
        "format": "Markdown 格式，使用合适的标题层级"
        })
    })