"""
搜索工具代理模块

统一转发到 skills/enhanced-search-tool-skill，避免重复实现。
"""

from deepinsight.utils.skill_loader import load_skill_module

_skill = load_skill_module(
    "enhanced-search-tool-skill",
    "modules/enhanced_search_tool.py",
    "skills_enhanced_search_tool",
)

SearchConfig = _skill.SearchConfig
EnhancedTavilyWrapper = _skill.EnhancedTavilyWrapper
search_provider = _skill.search_provider

__all__ = ["SearchConfig", "EnhancedTavilyWrapper", "search_provider"]