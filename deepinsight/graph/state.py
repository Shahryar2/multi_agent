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
    task: str   # 任务描述
    catagory: str # 任务场景
    style: str # 写作风格
    plan: List[SubTask] # 任务步骤列表
    current_step_index: int # 当前步骤索引
    documents: Annotated[List[Dict[str, Any]], operator.add]    # 已收集文档
    draft: str  # 初稿
    citations: List[Dict[str, Any]]  # 引用文献
    revision_number: int    # 当前修订版本
    max_revisions: int  # 最大修订次数
    next: str   # 下一步行动
    bg_investigation: Annotated[List[Dict[str, Any]], operator.add]  # 背景调查
    review: Dict[str, Any]  # 评审
    response: str # 用于存储聊天回复

    thought_process: str # 前端展示系统思考
    search_data: list # 前端展示搜索数据