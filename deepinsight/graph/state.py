import operator
from typing import Annotated,Any, Dict, List, Optional, TypedDict

class ResearchState(TypedDict):
    """
    系统的核心状态
    """
    task: str
    plan: List[str]
    documents: Annotated[List[str, Any], operator.add]
    draft: str
    revision_number: int
    max_revisions: int