import logging
from typing import List, Dict, Any, Optional
from difflib import SequenceMatcher
from deepinsight.graph.state import DraftState
from deepinsight.utils.skill_loader import load_skill_module

logger = logging.getLogger(__name__)

_skill = load_skill_module(
    "document-summarizer-skill",
    "modules/document_summarizer.py",
    "skills_document_summarizer",
)

summarize_single_doc = _skill.summarize_single_doc
map_summarize_documents = _skill.map_summarize_documents


def find_matching_section(
        step_desc: str,
        existing_sections: Dict[str,DraftState],
        threshold:float = 0.5
    )-> Optional[DraftState]:
    """
    基于语义相似度查找可复用章节
    """
    best_match = None
    best_ratio = 0.0

    for title, section in existing_sections.items():
        ratio = SequenceMatcher(None,step_desc,title).ratio()
        if ratio >= best_ratio and ratio >= threshold:
            best_ratio = ratio
            best_match = section

    return best_match
