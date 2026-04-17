import operator
from typing import Annotated,Any, Dict, List, Optional, TypedDict

class SubTask(TypedDict):
    '''
    任务步骤
    '''
    id: str
    type: str    # research, analysis, writing,summarized
    description: str
    status: str  # pending, completed
    result: str

class DraftState(TypedDict):
    """
    章节草稿状态
    """
    section_id: int  # 章节编号
    title: str  # 章节标题
    content: str  # 章节内容
    source_step_id: int  # 生成该章节的任务步骤ID
    token_count: int  # 章节内容的Token数量
    status: str  
    edit_history: List[Dict[str, Any]]  # 编辑历史记录(可选)

class ResearchState(TypedDict):
    """
    系统的核心状态
    """
    # 基础输入
    task: str   # 任务描述
    category: str # 任务场景
    field: str # 任务领域
    depth: str # 任务深度
    audience: str # 目标受众
    style: str # 写作风格
    style_config: Dict[str, Any]  # 写作风格配置
    thread_id: str  # 任务线程ID

    # 场景模式
    mode: str  # 场景模式：research | chat | comparison | follow_up
    mode_config: Dict[str, Any]  # 该模式的完整配置

    # 研究流程相关
    plan: List[SubTask] # 任务步骤列表
    documents: Annotated[List[Dict[str, Any]], operator.add]    # 已收集文档
    draft: str  # 合并草稿
    citations: List[Dict[str, Any]]  # 引用文献

    # 分章节相关
    draft_sections: List[DraftState]  # 章节草稿状态
    writing_mode: str  # 写作模式
    writing_progress: int  # 章节数
    is_long_document: bool  # 是否为长文档

    # 修订相关
    revision_number: int    # 当前修订版本
    max_revisions: int  # 最大修订次数
    review: Dict[str, Any]  # 评审

    # 对话上下文管理
    response: str # 当前聊天回复
    messages: Annotated[List[Dict[str, Any]], operator.add]  # 历史聊天消息记录
    last_draft: Optional[str]  # 最后一次草稿内容
    last_citations: Optional[List[Dict[str, Any]]]  # 最后一次引用文献

    # 其他
    next: str   # 下一步行动
    bg_investigation: Annotated[List[Dict[str, Any]], operator.add]  # 背景调查
    current_step_index: int # 当前步骤索引
    thought_process: str # 前端展示系统思考
    search_data: list # 前端展示搜索数据