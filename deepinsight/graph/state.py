import operator
from typing import Annotated,Any, Dict, List, Optional, TypedDict

class SubTask(TypedDict):
    '''
    任务步骤
    '''
    id:int
    type:str    # research, analysis, writing,summarized
    description:str
    status:str  # pending, completed
    result:str

class ResearchState(TypedDict):
    """
    系统的核心状态
    """
    task: str
    catagory: str # 任务场景
    plan: List[SubTask]
    current_step_index: int
    documents: Annotated[List[Dict[str, Any]], operator.add]
    sections: Annotated[List[Dict[str, Any]], operator.add] # 分段撰写的内容
    draft: str
    revision_number: int
    max_revisions: int
    next: str
    bg_investigation: Annotated[List[Dict[str, Any]], operator.add]