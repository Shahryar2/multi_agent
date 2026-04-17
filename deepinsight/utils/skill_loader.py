"""
Skill module loader.

Loads skill code from the skills/ directory that uses hyphenated folder names,
which are not valid Python package names. This keeps skill code as the single
source of truth while exposing stable imports in deepinsight/.
"""

from __future__ import annotations

import sys
import importlib.util
from pathlib import Path
from typing import Dict


_MODULE_CACHE: Dict[str, object] = {}


def load_skill_module(skill_dir: str, module_rel_path: str, module_name: str):
    """
    Load a skill module from a file path and cache it in sys.modules.

    Args:
        skill_dir: Skill folder name under repo root (e.g., "llm-factory-skill").
        module_rel_path: Relative file path under the skill folder
                         (e.g., "modules/llm_factory.py").
        module_name: Stable module name to register in sys.modules.

    Returns:
        The loaded module object.
    """
    cache_key = f"{skill_dir}:{module_rel_path}:{module_name}"
    if cache_key in _MODULE_CACHE:
        return _MODULE_CACHE[cache_key]

    repo_root = Path(__file__).resolve().parents[2]
    module_path = repo_root / "skills" / skill_dir / module_rel_path

    if not module_path.exists():
        raise FileNotFoundError(f"Skill module not found: {module_path}")

    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if not spec or not spec.loader:
        raise ImportError(f"Failed to load skill module spec: {module_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    _MODULE_CACHE[cache_key] = module
    return module
