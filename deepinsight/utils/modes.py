"""
模式配置管理模块（代理到 skills）

统一使用 skills/scene-mode-manager-skill 的实现，避免重复逻辑。
"""

from typing import Dict, Any
from deepinsight.utils.skill_loader import load_skill_module

_skill = load_skill_module(
    "scene-mode-manager-skill",
    "modules/scene_mode_manager.py",
    "skills_scene_mode_manager",
)

MODE_CONFIGS = _skill.MODE_CONFIGS
get_mode_config = _skill.get_mode_config
get_all_modes = _skill.get_all_modes


def validate_mode(mode: str) -> bool:
    """验证模式名称是否有效"""
    return mode in MODE_CONFIGS


def get_mode_list() -> list:
    """获取所有有效的模式名称"""
    return list(MODE_CONFIGS.keys())
