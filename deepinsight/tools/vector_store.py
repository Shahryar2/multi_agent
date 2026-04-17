"""
向量存储代理模块

统一转发到 skills/vector-storage-skill，避免重复实现。
"""

from deepinsight.utils.skill_loader import load_skill_module

_skill = load_skill_module(
    "vector-storage-skill",
    "modules/vector_storage.py",
    "skills_vector_storage",
)

VectorStore = _skill.VectorStore
vector_store = _skill.vector_store

__all__ = ["VectorStore", "vector_store"]