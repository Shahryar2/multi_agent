import hashlib
import json
import random
import re
import threading
import time
from typing import Any, Dict, List, Tuple
from langchain_core.documents import Document
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import JsonOutputParser,StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.prompts import PromptTemplate
from langchain_tavily import TavilySearch
from langchain_community.tools.tavily_search import TavilySearchResults
# from langchain_tavily import TavilySearchResults
from deepinsight.core.llm import get_llm
import logging
from concurrent.futures import ThreadPoolExecutor,as_completed
from deepinsight.tools.vector_store import VectorStore, vector_store
from deepinsight.utils.summarizer import find_matching_section
from deepinsight.utils.token_utils import count_tokens, term_document
from deepinsight.tools.base import get_tools
from deepinsight.graph.state import DraftState, ResearchState
from deepinsight.tools.search_provider import search_provider
from deepinsight.utils.normalizers import smart_truncate,remap_citations,smart_truncate_draft
from deepinsight.utils.normalizers import select_citations_for_section
from deepinsight.utils.global_state import CANCELLED_TASKS
from deepinsight.prompts.prompt_tool import select_style_preset,get_style_config
from deepinsight.prompts.prompt_demo import CHAT_PROMPT, PLANNER_PROMPT, REACHER_PROMPT, ROUTER_PROMPT, STYLE_CONFIG,WRITER_PROMPT,REVIEVER_PROMPT, STYLE_ANALYZER_PROMPT

logger = logging.getLogger(__name__)
api_semaphore = threading.Semaphore(3)

def router_node(state: ResearchState):
    """
    路由节点 - 改为配置驱动，而非启发式判断
    
    根据 state.mode 和 mode_config 决定下一步流程：
    - chat / follow_up: 直接进入 chat_node
    - comparison: 进入 planner_node（对比模式）
    - research: 进入 planner_node（研究模式）
    """
    task = state["task"]
    mode = state.get("mode", "research")  # ✅ 读取 mode
    mode_config = state.get("mode_config", {})  # ✅ 读取配置
    
    logger.info(f"🔀 Router: task='{task[:50]}...', mode='{mode}'")
    
    if not task:
        logger.error("Task is empty!")
        return {"next": "chat"}

    # ✅ 基于 mode 路由，而非自动判断
    if mode in ["chat", "follow_up"]:
        # Chat 和 Follow-up 模式：轻量模式，跳过 Planner，直接进入 Chat
        logger.info(f"    → Chat Mode: 跳过搜索和规划，直接进入对话")
        style = "general_chat"
        style_config = get_style_config(style)
        base_return = {
            "category": "chat",
            "field": "general",
            "depth": "brief",
            "audience": "general",
            "style": style,
            "style_config": style_config,
            "last_draft": state.get("last_draft", ""),
            "last_citations": state.get("last_citations", []),
            "mode": mode,
            "mode_config": mode_config,
        }
        return {**base_return, "next": "chat"}
    
    # Research 和 Comparison 模式都需要规划，但通过 comparison_mode 标记区分
    logger.info(f"    → Planning Mode: 进入任务规划流程")
    
    # ✅ 尝试用 LLM 分类（当需要时），或使用默认分类
    category = "report"  # 默认
    field = "general"
    depth = "moderate"
    audience = "general"
    style = "tech_deep"
    style_config = get_style_config(style)
    
    try:
        # 仅在 Research 模式下使用 LLM 分类，其他模式使用简化分类
        if mode == "comparison":
            # Comparison 模式：维度化思考
            category = "comparison"
            depth = "balanced"
            style = "analytical"
            logger.info(f"    → Comparison Mode: 维度化分类")
        else:
            # Research 模式：使用 LLM 进行详细分类
            llm = get_llm(
                model_tag="smart",
                thread_id=state.get("thread_id"),
                user_id=state.get("user_id"),
                mode=state.get("mode"),
            )
            system_prompt = ROUTER_PROMPT
            prompt = ChatPromptTemplate.from_messages([
                ("user", f"{system_prompt}\n\n用户输入: {{task}}")
            ])
            chain = prompt | llm | StrOutputParser()
            
            logger.info(f"    → Research Mode: 调用 LLM 进行场景分类...")
            response_text = rate_limited_call(chain.invoke, {"task": task})
            
            try:
                router_output = json.loads(response_text)
                category = router_output.get("category", "report")
                field = router_output.get("field", "other")
                depth = router_output.get("depth", "moderate")
                audience = router_output.get("audience", "general")
                style = select_style_preset({
                    "category": category,
                    "field": field,
                    "depth": depth,
                    "audience": audience,
                    "task": task
                })
                style_config = get_style_config(style)
                logger.info(f"    → Detected: category={category}, style={style}")
            except (json.JSONDecodeError, ValueError) as e:
                # 尝试从响应中提取 JSON 块
                json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
                json_matches = re.findall(json_pattern, response_text, re.DOTALL)
                
                extracted = False
                if json_matches:
                    for potential_json in json_matches:
                        try:
                            router_output = json.loads(potential_json)
                            # 验证必要的键
                            if all(k in router_output for k in ["category", "field", "depth", "audience"]):
                                category = router_output.get("category", "report")
                                field = router_output.get("field", "other")
                                depth = router_output.get("depth", "moderate")
                                audience = router_output.get("audience", "general")
                                style = select_style_preset({
                                    "category": category,
                                    "field": field,
                                    "depth": depth,
                                    "audience": audience,
                                    "task": task
                                })
                                style_config = get_style_config(style)
                                logger.info(f"    → ⚙️  提取JSON成功: category={category}, style={style}")
                                extracted = True
                                break
                        except json.JSONDecodeError:
                            continue
                
                if not extracted:
                    logger.error(f"    ⚠️  分类失败 (无法提取JSON): {e}，使用默认分类")
                    category = "report"
                    field = "other"
                    depth = "moderate"
                    audience = "general"
                    style = "tech_deep"
                    style_config = get_style_config(style)
            except Exception as e:
                logger.error(f"    ⚠️  分类失败: {e}，使用默认分类")
                category = "report"
                field = "other"
                depth = "moderate"
                audience = "general"
                style = "tech_deep"
                style_config = get_style_config(style)
                
    except Exception as e:
        logger.error(f"🔀 Router error: {e}")
    
    base_return = {
        "category": category,
        "field": field,
        "depth": depth,
        "audience": audience,
        "style": style,
        "style_config": style_config,
        "last_draft": state.get("last_draft", ""),
        "last_citations": state.get("last_citations", []),
        "mode": mode,  # ✅ 传递给下一个节点
        "mode_config": mode_config,  # ✅ 传递配置
    }
    
    return {**base_return, "next": "planner"}


def generate_step_id(topic: str, index: int) -> str:
    """
    基于 topic 和位置生成稳定 ID
    """
    content = f"{topic}_{index}"
    return hashlib.md5(content.encode('utf-8')).hexdigest()


def planner_node(state: ResearchState):
    """
    拆解任务
    output:
    {
     "plan": [
        {"description": str, "status": str},
        ...
     ],
     "current_step_index": int
    }
    """
    task = state["task"]
    # Fix typo in State definition variable name matches
    category = state.get("category","general")
    field = state.get("field", "other")
    depth = state.get("depth", "moderate")
    audience = state.get("audience", "general")
    
    review_feedback = state.get("review",{})
    current_plan = state.get("plan",[]) 
    llm = get_llm(
        model_tag="smart",
        thread_id=state.get("thread_id"),
        user_id=state.get("user_id"),
        mode=state.get("mode"),
    )

    simplified_old_plan = [
        {"id": step.get("id"), "topic": step.get("topic"), "description": step.get("description"), "status": step.get("status")}
        for step in current_plan
    ]
    current_plan_str = json.dumps(simplified_old_plan, ensure_ascii=False, indent=2)
    review_feedback_str = json.dumps(review_feedback, ensure_ascii=False, indent=2)

    if not review_feedback or review_feedback.get("status") == "pass":
        thought_msg = f"任务 '{task}'确定为[{category}/{field}]场景，深度[{depth}]，面向[{audience}]，开始拆解初步执行计划...."
        system_prompt = PLANNER_PROMPT.format(
            category=category,
            field=field,
            depth=depth, 
            task=task,
            current_plan="[]",
            review_feedback="{}"
        )
        user_input = f"任务：{task}"
    else:
        print(f"---[Planner]收到Review反馈，调整计划{review_feedback}---")
        thought_msg = f"收到审核反馈，正在根据意见[{review_feedback.get('reason')}]调整执行计划...."
        system_prompt = PLANNER_PROMPT.format(
            category=category,
            field=field,
            depth=depth,
            task=task,
            current_plan=current_plan_str,
            review_feedback=review_feedback_str
        )
        user_input = f"原任务：{task}\n 审核意见：{review_feedback.get('missing','内容缺失')}\n"

    # 使用 JsonOutputParser 获取格式说明
    parser = JsonOutputParser()
    format_instructions = parser.get_format_instructions()

    # 显式构建 Prompt 字符串
    full_prompt = f"{system_prompt}\n\n{format_instructions}\n\n用户输入: {user_input}"
    
    # 显式使用 HumanMessage
    messages = [HumanMessage(content=full_prompt)]
    
    try:
        response = rate_limited_call(llm.invoke, messages)
        content = response.content
        # 正则提取markdown中的Json块
        json_match = re.search(r"```json\s*(.*?)\s*```", content, re.DOTALL)
        if json_match:
            json_str = json_match.group(1).strip()
        else:
            # 兼容无代码块的情况
            start_idx = content.find("[")
            end_idx = content.rfind("]")
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                json_str = content[start_idx:end_idx+1].strip()
            else:
                start_idx = content.find("{")
                end_idx = content.rfind("}")
                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                    json_str = content[start_idx:end_idx+1].strip()
                else:
                    json_str = content
        
        try:
            plan = json.loads(json_str)
        except json.JSONDecodeError:
            plan = parser.parse(json_str)

        if not isinstance(plan,list):
            # 兼容 LLM 返回 {"steps": [...]} 或 {"plan": [...]} 的情况
            if isinstance(plan, dict):
                if "steps" in plan and isinstance(plan["steps"], list):
                    plan = plan["steps"]
                elif "plan" in plan and isinstance(plan["plan"], list):
                    plan = plan["plan"]
                else:
                    plan = [plan]
            else:
                plan = [plan]

        for i,step in enumerate(plan):
            if "status" not in step:
                step["status"] = "pending"
            if "id" not in step:
                step["id"] = generate_step_id(step.get("topic",step.get("description","")), i)
        
        def _norm_desc(text:str)->str:
            if not text:
                return ""
            return re.sub(r'\s+','',text).lower()

        old_plan_map = {}
        for p in state.get("plan",[]):
            if p.get("id"):
                old_plan_map[p["id"]] = p
            if p.get("description"):
                old_plan_map[_norm_desc(p["description"])] = p

        merged_plan = []
        for step in plan:
            step_id = step.get("id")
            norm_desc = _norm_desc(step.get("description",""))
            old_step = None
            if step_id and step_id in old_plan_map:
                old_step = old_plan_map.get(step_id)
            elif norm_desc and norm_desc in old_plan_map:
                old_step = old_plan_map.get(norm_desc)

            if old_step:
                llm_intended_status = step.get("status", "pending")
                if llm_intended_status == "completed" :
                    if old_step.get("result") and old_step.get("status") == "completed":
                        step["result"] = old_step.get("result", "")
                        step["doc_ids"] = old_step.get("doc_ids", [])
                        step["status"] = "completed"
                        logger.info(f"Step '{step_id or norm_desc}' retains completed status with existing result.")
                    else:
                        step["status"] = "pending"
                        step["result"] = ""
                        step["doc_ids"] = []
                        logger.warning(f"Step '{step_id or norm_desc}' cannot be marked as completed due to missing result, setting to pending.") 
                else:
                    step["status"] = "pending"
                    step["result"] = ""
                    step["doc_ids"] = []
                    logger.info(f"Step '{step_id or norm_desc}' status set to pending, clearing result and doc_ids.")
            else:
                if step.get("status") == "completed":
                    logger.warning(f"New step '{step_id or norm_desc}' is marked as completed but has no history, setting to pending.")
                    step["status"] = "pending"

            merged_plan.append(step)

        is_revision = bool(review_feedback and review_feedback.get("status") == "fail")
        if is_revision:
            pending_count = sum(1 for s in merged_plan if s.get("status") == "pending")
            if pending_count == 0:
                logger.warning("Review feedback indicates revision, but no pending steps found. Forcing last step to pending.")
                merged_plan[-1]["status"] = "pending"
                merged_plan[-1]["result"] = ""
                merged_plan[-1]["doc_ids"] = []

        return {
            "plan": merged_plan,
            "current_step_index": 0,
            "thought_process": thought_msg
        }
    except Exception as e:
        logger.error(f"Planner LLM failed: {e}")
        old_plan = state.get("plan",[]) or []
        
        is_revision = bool(review_feedback and review_feedback.get("status") == "fail")
        if is_revision and old_plan:
            # 修订失败时：用位置策略，将后半段的 completed 步骤重置为 pending
            # 不使用关键词匹配（不可靠），因为 reviewer 每次反馈的内容都不同
            fixed_plan = []
            has_pending = False
            total_steps = len(old_plan)
            # 后半段起始索引：至少从第2步开始，最多从中间开始
            rear_start_idx = max(1, total_steps // 2)

            for i, step in enumerate(old_plan):
                new_step = step.copy()
                # 后半段中，将 completed 步骤重置为 pending（跳过已经 failed 的）
                if i >= rear_start_idx and step.get("status") == "completed":
                    new_step["status"] = "pending"
                    new_step["result"] = ""
                    new_step["doc_ids"] = []
                    has_pending = True
                    logger.info(f"fallback: 步骤[{i}] '{step.get('topic','')}' 重置为pending")
                fixed_plan.append(new_step)

            # 安全兜底：后半段没有 completed 步骤时，强制找最后一个 completed 步骤重置
            if not has_pending:
                for step in reversed(fixed_plan):
                    if step.get("status") == "completed":
                        step["status"] = "pending"
                        step["result"] = ""
                        step["doc_ids"] = []
                        has_pending = True
                        break

            # 最终兜底：实在找不到，强制最后一步 pending
            if not has_pending and fixed_plan:
                fixed_plan[-1]["status"] = "pending"
                fixed_plan[-1]["result"] = ""
                fixed_plan[-1]["doc_ids"] = []

            return {
                "plan": fixed_plan,
                "current_step_index": 0,
                "thought_process": "解析失败，基于位置策略重置后半段步骤为pending。"
            }
        elif not old_plan:
            # 首次规划失败（old_plan为空）：生成结构完整的3步兜底计划
            # 不能用 old_plan + [单步骤]，否则 plan 只有1步，生成内容极简
            logger.warning("首次规划解析失败，使用结构化兜底计划")
            fallback_plan = [
                {
                    "type": "research",
                    "topic": "背景与需求",
                    "description": f"分析'{task}'的背景、用户需求和核心痛点",
                    "status": "pending",
                    "result": "",
                    "doc_ids": [],
                    "id": generate_step_id("背景与需求", 0)
                },
                {
                    "type": "research",
                    "topic": "核心内容",
                    "description": f"详细阐述'{task}'的核心内容、方法和策略",
                    "status": "pending",
                    "result": "",
                    "doc_ids": [],
                    "id": generate_step_id("核心内容", 1)
                },
                {
                    "type": "research",
                    "topic": "总结与建议",
                    "description": f"总结'{task}'的关键要点，提供具体可操作的建议",
                    "status": "pending",
                    "result": "",
                    "doc_ids": [],
                    "id": generate_step_id("总结与建议", 2)
                }
            ]
            return {
                "plan": fallback_plan,
                "current_step_index": 0,
                "thought_process": "首次规划解析失败，使用结构化兜底计划。"
            }
        else:
            # 修订失败且 old_plan 非空的极端情况：追加一个修订步骤
            fallback_key = {
                "type": "research",
                "topic": "补充修订",
                "description": f"根据审核反馈补充缺失内容：{review_feedback.get('missing', '完善内容')}",
                "status": "pending",
                "result": "",
                "doc_ids": [],
                "id": generate_step_id("fallback_fix", 999)
            }
            return {
                "plan": old_plan + [fallback_key],
                "current_step_index": 0,
                "thought_process": "解析失败，追加补充修订步骤。"
            }
    
def orchestrator_node(state: ResearchState):
    '''
    编排者节点,决定下一步
    '''
    plan = state.get("plan", [])
    idx = state.get("current_step_index", 0)

    if idx < len(plan):
        return {"next": "researcher"}
    else:
        return {"next": "writer"}

def _is_retryable_error(error: Exception) -> bool:
    """
    判断是否为可重试错误
    """
    message = str(error).lower()
    retryable_signals = [
        "429",
        "500",
        "incomplete chunked read",
        "peer closed connection",
        "connection reset",
        "readtimeout",
    ]
    return any(signal in message for signal in retryable_signals)


def rate_limited_call(func, *args, **kwargs):
    """
    包装器：速率限制+重试逻辑（仅在限速错误时 sleep）
    """
    max_retries = 3
    for attempt in range(max_retries):
        with api_semaphore:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if _is_retryable_error(e) and attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 8 + random.uniform(0, 2)
                    logger.warning(f"API调用失败，{wait_time:.1f}s后重试 {attempt + 1}/{max_retries}: {e}")
                    time.sleep(wait_time)
                    continue
                raise e
            
def validate_document_quality(doc: Document) -> bool:
    """
    检查文档质量
    """
    content = doc.page_content or ""
    if len(content) < 50:
        return False
    # if len([c for c in content if c.isalpha()]) < len(content) * 0.5:
    #     return False
    return True

def generate_optimized_query(
    main_task: str,
    sub_task_desc: str,
    thread_id: str | None = None,
    user_id: str | None = None,
    mode: str | None = None,
) -> str:
    """
    任务描述 -> 精准搜索引擎关键词
    """
    llm = get_llm(
        model_tag="smart",
        thread_id=thread_id,
        user_id=user_id,
        mode=mode,
    )
    prompt = PromptTemplate.from_template(
    """你是一个专业的搜索引擎优化专家。你的任务是根据用户的【总任务】和当前的【子步骤】，生成一个最适合在 Google/Bing 搜索的关键词。

    【总任务】：{main_task}
    【子步骤】：{sub_task_desc}

    要求：
    1. 仅输出一个最核心的搜索关键词（或短语）。
    2. 去除所有指令性词语（如"给我一份"、"去搜索"、"分析"、"整理"）。
    3. 关键词长度控制在 3-5 个词以内。
    4. 优先保留实体（地点、人名、事件）和核心意图。
    5. 不要输出 JSON，不要输出解释，直接输出关键词。

    搜索关键词："""
)
    chain = prompt | llm | StrOutputParser()
    try:
        query = chain.invoke({
            "main_task": main_task,
            "sub_task_desc": sub_task_desc
        })
        return query.strip().replace('"','').replace("'",'').replace('\n',' ')
    except Exception as e:
        return f"{main_task[:10]} {sub_task_desc[:10]}"


def research_node(state: ResearchState):
    '''
    并行研究节点,负责当前索引子任务
    output:
    {
     "documents": [{"id": str, "text": str, "title": str, "url": str}, ...],
     "plan":[
        {"description": str, "status": str, "result": str, "doc_ids": [str]},
        {"description": str, "status": str, "result": str},
     ],
     "current_step_index": int,
     "bg_investigation": [...]
    }
    '''
    thread_id = state.get("thread_id")
    # 任务取消检查 -- 节点开始前
    if thread_id and thread_id in CANCELLED_TASKS:
        logger.info(f"---[Researcher] 任务线程 {thread_id} 已取消，跳过研究节点 ---")
        return {"current_step_index": len(state.get("plan", []))}
    
    plan = state.get("plan", [])

    # 并行任务实现
    pending_tasks = []
    pending_indices = []
    for i,task in enumerate(plan):
        if task.get("status") == "pending":
            pending_tasks.append(task)
            pending_indices.append(i)

    if not pending_tasks:
        print(f"---[Researcher]无待处理子任务，跳过---")
        return {"current_step_index": len(plan)}
    
    main_task = state.get("task","")

    category = state.get("category","report").lower()
    field = state.get("field","other").lower()
    search_mode = "general"
    if category == "chat":
        search_mode = "social_media"
    elif category == "guide" and field == "lifestyle":
        search_mode = "lifestyle"
    elif category == "news":
        search_mode = "general"
    elif category == "report" and field in ["tech","academic"]:
        search_mode = "academic"
    logger.info(f"---[Researcher]研究类别: {category},搜索模式: {search_mode}---")

    # 任务取消检查 -- 并行子任务开始前
    if thread_id and thread_id in CANCELLED_TASKS:
        logger.info(f"---[Researcher] 任务线程 {thread_id} 已取消，跳过研究节点 ---")
        return {"current_step_index": len(state.get("plan", []))}

    def execute_single_task(task_info):
        # 任务取消检查 -- 子任务开始前
        if thread_id and thread_id in CANCELLED_TASKS:
            logger.info(f"---[Researcher] 任务线程 {thread_id} 已取消，跳过子任务 ---")
            return {
                "success": False,
                "error": "Task Cancelled"
            }

        sub_task_description = task_info.get("description","")
        # step_keyword = sub_task_description.split('：')[0].split(':')[0]
        # main_keyword = main_task[:15]

        # query = f'{main_keyword} {step_keyword}'
        # if len(query) < 5:
        #     query = sub_task_description[:50]
        logger.info(f"正在生成搜索词...(主：{main_task[:10]}... 子：{sub_task_description[:10]}...)")
        # 任务取消检查 -- 生成搜索词前
        if thread_id and thread_id in CANCELLED_TASKS:
            return {
                "success": False,
                "error": "Task Cancelled"
            }

        query = generate_optimized_query(
            main_task=main_task,
            sub_task_desc=sub_task_description,
            thread_id=thread_id,
            user_id=state.get("user_id"),
            mode=state.get("mode"),
        )
        logger.info(f"--- [Researcher] 优化后的搜索词 [{query}]---")
        
        # 任务取消检查 -- 搜索前
        if thread_id and thread_id in CANCELLED_TASKS:
            return {
                "success": False,
                "error": "Task Cancelled"
            }

        # 调用搜索工具
        try:
            cleaned_results = rate_limited_call(
                search_provider.search,
                query=query,
                config_name=search_mode
            )
            """
            返回格式:
            [
                {
                "title": str,
                "url": str,
                "content": str,
                "type": "text",
                "images": [...]
                },
                ...
            ]
            """
            # 任务取消检查 -- 写入向量库前
            if thread_id and thread_id in CANCELLED_TASKS:
                return {
                    "success": False,
                    "error": "Task Cancelled"
                }

            if not cleaned_results:
                logger.warning(f"优化关键词 [{query}] 失败，无搜索结果...")
                fallback_query = f"{main_task[:15]} {sub_task_description[:20]}"
                cleaned_results = rate_limited_call(
                    search_provider.search,
                    query=fallback_query,
                    config_name=search_mode
                )
                logger.info(f"兜底搜索 关键词 [{fallback_query}] 获得 {len(cleaned_results)} 条结果...")

            new_docs = []
            # 转换为 Langchain Document 对象
            for item in cleaned_results:
                content = item.get('content')
                if not content or not isinstance(content, str):
                    # logger.warning(f"跳过无效内容的搜索结果: {item.get('title')}")
                    continue
                doc = Document(
                    page_content=content,
                    metadata={
                        "source": item['url'],
                        "title": item.get('title'),
                        "type": item.get('type'),
                    }
                )
                if validate_document_quality(doc):
                    new_docs.append(doc)

            if new_docs:
                try:
                    vector_store.add_documents(new_docs)
                    # print(f"[Researcher]已添加 {len(new_docs)} 条文档到向量存储")
                except Exception as e:
                    logger.error(f"向量存储添加文档失败: {e}")
            
            if not new_docs:
                logger.warning(f"关键词 {query} 原始返回结果数: {len(cleaned_results)}，但无有效文档")

            step_summary = ""
            if new_docs:
                # 任务取消检查 -- 总结前
                if thread_id and thread_id in CANCELLED_TASKS:
                    return {
                        "success": False,
                        "error": "Task Cancelled"
                    }

                llm = get_llm(
                    model_tag="smart",
                    thread_id=thread_id,
                    user_id=state.get("user_id"),
                    mode=state.get("mode"),
                )
                text_only_docs = [d for d in new_docs if d.metadata.get("type") == "text"]
                docs_to_summarize = text_only_docs if text_only_docs else new_docs
                # 构建小型上下文
                termmed_docs = term_document(
                    docs_to_summarize,
                    max_tokens=6000,
                )
                
                formatted_contents = []
                for doc in termmed_docs:
                    if isinstance(doc,dict):
                        content = doc.get("text",doc.get("page_content",""))
                    else:
                        content = getattr(doc,"page_content","")
                    formatted_contents.append(f"- {content}")

                context_text = "\n".join(formatted_contents)
                
                prompt_content = REACHER_PROMPT.format(query=query, context_text=context_text)

                try:
                    # 使用 HumanMessage 列表调用，确保兼容性
                    messages = [HumanMessage(content=prompt_content)]
                    response = rate_limited_call(llm.invoke, messages)
                    step_summary = response.content
                    print(f"---[Researcher]子任务总结: {step_summary}---")
                except Exception as e:
                    logger.error(f"Researcher总结失败: {e}")
                    step_summary = "本步骤未能生成总结。"
            else:
                step_summary = f"搜索关键词 '{query}' 未获得有效结果，请尝试调整关键词或搜索策略。"
                logger.warning(f"子任务未获得有效文档：{query}")
                    
            return {
                "success": True,
                "results": step_summary,    # 子任务结果总结
                "docs": new_docs,   # Langchain Document 对象列表
                "docs_ids": [doc.metadata.get("source") for doc in new_docs],   # URL 列表
                "raw_results": cleaned_results  # 原始搜索结果
            }
        
        except Exception as e:
            logger.error(f"任务'{query}'执行失败: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    # 线程池并行执行
    results_map = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_index = {
            executor.submit(execute_single_task, task): idx 
            for idx, task in zip(pending_indices, pending_tasks)
        }
        for future in as_completed(future_to_index):
            # 任务取消检查 -- 子任务结果收集前
            if thread_id and thread_id in CANCELLED_TASKS:
                logger.info(f"---[Researcher] 任务主线程 {thread_id} 已取消，正在丢弃剩余任务 ---")
                executor.shutdown(wait=False,cancel_futures=True)

                return {"current_step_index": len(state.get("plan", []))}

            idx = future_to_index[future]
            try:
                res = future.result()
                results_map[idx] = res
            except Exception as e:
                logger.error(f"线程异常: {e}")
                results_map[idx] = {
                    "success": False,
                    "error": "Thread Exception"
                }

    all_new_docs = []
    all_raw_results = []

    for idx, res in results_map.items():
        if res.get("success"):
            plan[idx]["status"] = "completed"
            plan[idx]["result"] = res.get("results")
            plan[idx]["doc_ids"] = res.get("docs_ids")

            all_new_docs.extend(res.get("docs",[]))
            all_raw_results.extend(res.get("raw_results",[]))
            # Safely get description to prevent KeyError
            desc = plan[idx].get('description', 'Unknown Task')
            print(f"---[Researcher]子任务完成: {desc[:50]}---")
        else:
            plan[idx]["status"] = "failed"
            plan[idx]["result"] = f"任务失败: {res.get('error')}"
            desc = plan[idx].get('description', 'Unknown Task')
            print(f"---[Researcher]子任务失败: {desc[:50]}---")
    
    """ 文档截断 与 格式转换 """
    final_docs_for_state = []
    MAX_FULL_TEXT_DOCS = 5
    if len(all_new_docs) > MAX_FULL_TEXT_DOCS:
        print(f"---[Researcher]文档数量{len(all_new_docs)}，进行截断---")
        for d in all_new_docs:
            light_doc_dict = {
                "id": d.metadata.get("source"),
                "text": d.page_content[:500],  # 截断内容
                "title": d.metadata.get("title"),
                "url": d.metadata.get("source"),
                "type": d.metadata.get("type"),
            }
            final_docs_for_state.append(light_doc_dict)
    else:
        for d in all_new_docs:
            final_docs_for_state.append({
                "id":d.metadata.get("source"),
                "text":d.page_content,
                "title":d.metadata.get("title"),
                "url":d.metadata.get("source"),
                "type":d.metadata.get("type"),
            })

    return {
        "documents": final_docs_for_state,
        "current_step_index": len(plan),
        "plan": plan,
        "bg_investigation": all_raw_results,
        "search_data": all_raw_results
    }


def calculate_section_token_budget(total_available: int, num_sections: int) -> int:
    """
    计算每章节的Token预算

    Args:
        total_available (int): 总可用Token数
        num_sections (int): 章节数量
    """
    buffer = int(total_available * 0.2)
    per_section = (total_available - buffer) // max(num_sections, 1)
    return per_section

def generate_section(
        section_id: int,
        plan_step: Dict[str,Any],
        style_config: Dict,
        citations: List[dict],
        llm=None,
        all_sections_context: str="",
        topics_covered: List[str] = None,
        max_tokens: int = 3000,
        review_feedback: str = "",
        thread_id: str | None = None,
        user_id: str | None = None,
        mode: str | None = None,
    )-> Tuple[str,int]: 
    """
    生成单个章节

    Args:
        section_id: 章节号
        plan_step: 该步骤计划
        style_config: 写作风格配置
        citations: 引用文献列表
        llm: LLM实例
        all_sections_context: 已生成的章节内容
        max_tokens: 本章节最大Token数
    Returns:
        Tuple[str,int]: 生成的章节内容及使用的Token数
    """
    step_description = plan_step.get("description","")
    step_result = plan_step.get("result","")
    task = plan_step.get("task","")
    step_doc_ids = plan_step.get("doc_ids", [])  # 研究员专门为该步骤搜到的文档ID
    
    citations_text = select_citations_for_section(
        citations,
        section_topic=step_description,
        section_result=step_result,
        max_citations=5,  # 不同章节优先使用自己的研究成果，名额提升到 5 给LLM更多选择
        max_snippet_length=150,
        priority_ids=step_doc_ids,
    )
    step_result_short = smart_truncate(step_result, max_length=600)
    # 清洗研究结果中的伪引用标签，防止LLM将其学习为合法的引用格式
    _FAKE_LABEL_RE = re.compile(r'\[(核心素材|参考资料\d*|研究素材|参考文献|前文脉络)\]', re.UNICODE)
    step_result_short = _FAKE_LABEL_RE.sub('', step_result_short)
    context_short = smart_truncate(all_sections_context, max_length=2000)
    
    persona = style_config.get("persona","你是一个专业内容撰写者")
    persona_short = smart_truncate(persona, max_length=100, add_ellipsis=True)
    
    target_words = min(500,(max_tokens * 0.15))

    review_block = ""
    if review_feedback:
        review_block = f"""\n【审核修正要求】\n以下是审核反馈，请在本章节写作中务必针对性地修正这些问题：\n{review_feedback}\n"""

    topics_block = ""
    if topics_covered:
        topics_str = "、".join(topics_covered)
        topics_block = f"\n【已覆盖章节主题（请勿在本章节重复这些主题的核心要点）】\n前文已涵盖：{topics_str}。请确保本章节内容与前文互补，不要重复介绍已覆盖的内容。\n"

    section_prompt = f"""{persona_short}

【任务目标】
任务：{task}
当前章节：第 {section_id} 部分 - {step_description}

【研究素材（仅供参考，不得直接引用此标签）】
{step_result_short}

【可用文献（引用时只能使用以下编号，格式为[编号]）】
{citations_text}

{f"【前文脉络】{context_short}" if context_short else ""}
{topics_block}{review_block}
【写作要求】
1. 字数控制在 {target_words} 字以内。
2. 必须符合上述设定的写作风格（语气、受众）。
3. 使用 Markdown 格式。
4. 引用来源时，只能使用上方文献列表中出现的数字编号，格式严格为 [1]、[2]、[3] 等。
5. 严禁在正文中出现 [核心素材]、[参考资料]、[研究素材]、[前文脉络]、[参考文献] 等非数字标签。
6. 如果没有合适的文献编号可引用，则不引用，不要凭空捏造引用标记。
7. 直接输出正文，不要包含 "好的" 或标题。

开始写作：
"""
    if llm is None:
        llm = get_llm(
            model_tag="smart",
            thread_id=thread_id,
            user_id=user_id,
            mode=mode,
        )
    prompt_tokens = count_tokens(section_prompt, model_tag="smart")
    logger.info(f"章节 {section_id} 提示词Tokens: {prompt_tokens}, 目标输出Tokens: {max_tokens}")

    messages = [HumanMessage(content=section_prompt)]
    response = rate_limited_call(llm.invoke,messages)
    section_content = response.content
    
    # 检测并修复截断
    # section_content = smart_truncate(section_content, 3000)
    section_content = _fix_truncated_ending(section_content)
    # 清洗LLM输出中残留的伪引用标签（如[核心素材]、[参考资料]等）
    _FAKE_LABEL_RE = re.compile(r'\[(核心素材|参考资料\d*|研究素材|参考文献|前文脉络)\]', re.UNICODE)
    section_content = _FAKE_LABEL_RE.sub('', section_content)
    
    actual_tokens = count_tokens(section_content, model_tag="smart")
    logger.info(f"章节 {section_id} 生成完成，使用Tokens: {actual_tokens}")

    return section_content, actual_tokens


def _fix_truncated_ending(content: str) -> str:
    """
    修复截断结尾
    """
    if not content or len(content) < 30:
        return content
    incomplete_endings = ['，', '、', '：', '的', '和', '与', '在', '是', '有', '了', '等']
    last_char = content.rstrip()[-1] if content.rstrip() else ''
    if last_char in incomplete_endings:
        last_period = max(
            content.rfind('。'),
            content.rfind('！'),
            content.rfind('.'),
            content.rfind('？')
        )

        if last_period > len(content) * 0.6:
            return content[:last_period + 1]
        else:
            return content.rstrip() + "。"
    return content


def merge_sections_to_draft(
        task: str,
        sections: List[Dict[str,Any]],
        citations: List[Dict[str,Any]],
    ) -> str:
    """
    合并章节为完整草稿
    """
    draft_parts = [f"# {task}\n\n"]
    for section in sections:
        draft_parts.append(
            f"## {section['title']}\n\n{section['content']}\n\n"
        )

    citations_footer = "\n\n## 引用列表\n\n" + "\n\n".join(
        f"[{c['index']}] {c['title']} — {c['url']}" for c in citations
    )
    return "".join(draft_parts) + citations_footer

def writer_node(state: ResearchState):
    """
    撰写-优化混合(自主选择全文/分章)

    output:
    {
      "draft": str,
      "citations": [
        {
         "index": int,
         "id": str, 
         "title": str,
         "url": str, 
         "snippet": str
        },
        ...
      ]
    }
    """
    task = state["task"]
    style = state.get("style", "tech_deep")  # Get style
    plan = state.get("plan",[])
    documents = state.get("documents", [])
    llm = get_llm(
        model_tag="smart",
        thread_id=state.get("thread_id"),
        user_id=state.get("user_id"),
        mode=state.get("mode"),
    )

    style_inst = get_style_config(style)
    logger.info(f"---[Writer]使用风格配置: {style_inst}---")

    plan_context = ""
    for step in plan:
        plan_context += f"### 研究步骤:{step.get('description')}\n"
        plan_context += f"### 研究结论:{step.get('result','无结果')}\n\n"

    logger.info(f"---[Writer] 正在基于大纲检索向量库 ---")
    retrieved_docs = []
    seen_ids = set()
    # rag_success = False

    all_step_ids = []
    for step in plan:
        all_step_ids.extend(step.get("doc_ids", []))

    if all_step_ids:
        full_docs = vector_store.get_documents_by_ids(all_step_ids)
        for doc in full_docs:
            if doc.get("id") not in seen_ids:
                retrieved_docs.append(doc)
                seen_ids.add(doc.get("id"))

    if not retrieved_docs:
        doc_map = {doc.get("id"): doc for doc in documents if doc.get("id")}
        for doc_id in all_step_ids:
            if doc_id in doc_map and doc_id not in seen_ids:
                retrieved_docs.append(doc_map[doc_id])
                seen_ids.add(doc_id)
    print(f"---[Writer] 精准召回命中{len(retrieved_docs)}篇文档---")

    if len(retrieved_docs) < 5:
        logger.info(f"---[Writer] 精准召回不足，进行相似度检索补充 ---")
        try:
            for step in plan:
                query = step.get("description")
                results = vector_store.similarity_search(query, k=4)
                for res in results:
                    if isinstance(res, dict):
                        doc_data = res
                    else:
                        doc_data = {
                            "text": res.page_content,
                            "title": res.metadata.get("title", ""),
                            "url": res.metadata.get("url", ""),
                            "id": res.metadata.get("original_id") or str(hash(res.page_content))[:8]
                        }
                    doc_id = doc_data.get("id")
                    if doc_id and doc_id in seen_ids:
                        continue
                    # 简单去重
                    is_duplicate_content = any(
                        d.get("text", "")[:50] == doc_data.get("text", "")[:50] 
                        for d in retrieved_docs
                    )
                    if not is_duplicate_content:
                        retrieved_docs.append(doc_data)
                        if doc_id:
                            seen_ids.add(doc_id)
        except Exception as e:
            logger.error(f"RAG检索失败: {e}")

    if not retrieved_docs:
        logger.info(f"---[Writer] 向量库无结果，回退截断 ---")
    
        # 计算占用token
        plan_tokens = count_tokens(plan_context,model_tag="smart")
        print(f"---[Writer] 骨架Tokens:{plan_tokens}---")

        MODEL_LIMIT = 30000
        RESERVED_OUTPUT = 4000
        SYSTEM_PROMPT_ESTIMATE = 1000

        availble_for_docs = MODEL_LIMIT - RESERVED_OUTPUT - SYSTEM_PROMPT_ESTIMATE - plan_tokens
        if availble_for_docs < 0:
            logger.warning(f"计划内容过长，超出模型限制")
            availble_for_docs = 1000

        retrieved_docs = term_document(
            documents,
            max_tokens=availble_for_docs, 
            model_tag="smart"
        )
    
    citations = []
    for idx,seg in enumerate(retrieved_docs,start=1):
        is_dict = isinstance(seg, dict)
        text_content = seg.get("text") if is_dict else seg.page_content
        title_content = seg.get("title") if is_dict else seg.metadata.get("title", "Untitled")
        url_content = seg.get("url") if is_dict else seg.metadata.get("source", "")
        doc_id = seg.get("id") if is_dict else seg.metadata.get("source","unknown")

        citations.append({
            "index":idx,
            "id":doc_id,
            "title": title_content,
            "url": url_content,
            "snippet": text_content[:300],
            "full_text": text_content    # 可选(作为前端展示书写过程)
        })
    
    # 判断是否分章撰写
    plan_tokens = count_tokens(plan_context,model_tag="smart")
    docs_context = "\n\n".join([
        f"[{c['index']}] Title: {c['title']}\nContent: {c['full_text']}\nSource: {c['url']}" 
        for c in citations
    ])

    docs_tokens = count_tokens(docs_context,model_tag="smart")
    SYSTEM_PROMPT_TOKENS = 2000
    estimated_total_tokens = plan_tokens + docs_tokens + SYSTEM_PROMPT_TOKENS
    logger.info(f"-- [Writer] 预估总tokens消耗为 {estimated_total_tokens} --")

    MODEL_CONTEXT_LIMIT = 32000
    INTEGRATED_WRITING_LIMIT = 4000
    
    # TOKEN_THRESHOLD = 6000
    # 补全条件：预估Token超限，或大纲步骤过多，或历史标记为长文档
    use_sectional_writing = (
        estimated_total_tokens > INTEGRATED_WRITING_LIMIT or
        len(plan) >=3 or
        state.get("is_long_document", False)
    )
    
    if use_sectional_writing:
        logger.info(f"---[Writer] 切换到分章节写作方式 ---")
        # 提取审核反馈（修订轮次时传给 generate_section）
        review_data = state.get("review", {})
        review_feedback_str = ""
        if review_data.get("status") == "fail":
            missing = review_data.get("missing", "")
            reason = review_data.get("reason", "")
            review_feedback_str = f"问题: {missing}\n原因: {reason}".strip()
            logger.info(f"---[Writer] 修订模式，审核反馈: {review_feedback_str[:120]} ---")

        # 增量写作逻辑
        last_draft_sections = state.get("draft_sections", [])
        last_citations = state.get("citations", [])
        # 构建已有章节映射
        existing_sections_map = {s['title']: s for s in last_draft_sections}

        draft_sections: List[DraftState] = []
        total_output_tokens = 0
        accumulated_content = ""
        sections_written: List[str] = []   # 追踪已写章节标题，用于防止重复
        MAX_OUTPUT_TOKENS = 3000

        # 计算每个章节token预算
        availble_for_sections = MODEL_CONTEXT_LIMIT - SYSTEM_PROMPT_TOKENS
        per_section_buget = calculate_section_token_budget(
            total_available=availble_for_sections,
            num_sections=len(plan),
        )
        if per_section_buget > MAX_OUTPUT_TOKENS:
            per_section_buget = MAX_OUTPUT_TOKENS

        logger.warning(f"-- [Writer] 每个章节 Token 预算为 {per_section_buget} --")

        for i,step in enumerate(plan):
            step_desc = step.get("description","章节")
            step_topic = step.get("topic","")
            # 是否复用
            can_reuse = False
            reused_section = None
            if step.get("status") == "completed" :
                # 双重查找：优先用 topic 精准匹配，其次用 desc 精准匹配，最后模糊匹配
                # 注意：只保留一套查找逻辑，避免后面的覆盖前面更好的结果
                reused_section = (
                    existing_sections_map.get(step_topic) or
                    existing_sections_map.get(step_desc) or
                    find_matching_section(step_topic or step_desc, existing_sections_map)
                )

            if reused_section:
                logger.info(f"---[Writer] 复用章节 {step_desc} ---")

                # 防止混乱重新映射
                reused_content = remap_citations(
                    reused_section['content'],
                    old_citations=last_citations,
                    new_citations=citations
                )
                # 新状态对象
                new_section = reused_section.copy()
                new_section["section_id"] = i + 1
                new_section["title"] = step_topic or reused_section.get("title", step_desc[:50])
                new_section['content'] = reused_content
                new_section['source_step_id'] = step.get("id", i)
                
                draft_sections.append(new_section)
                sections_written.append(new_section["title"])

                accumulated_content += f"\n### {new_section['title']}\n{reused_content}\n"
                total_output_tokens += reused_section.get("token_count",0)
            else:
                logger.info(f"---[Writer] 正在生成章节 {i+1}: {step.get('description','章节')} ---")
                section_content, section_tokens = generate_section(
                    section_id=i + 1,
                    plan_step={**step,"task": task},
                    style_config=style_inst,
                    citations=citations,
                    llm=llm,
                    all_sections_context=accumulated_content,
                    topics_covered=sections_written if sections_written else None,
                    max_tokens=per_section_buget,
                    review_feedback=review_feedback_str,
                    thread_id=state.get("thread_id"),
                    user_id=state.get("user_id"),
                    mode=state.get("mode"),
                )
                section: DraftState = {
                    "section_id": i + 1,
                    "title": step_topic or step_desc[:50],
                    "content": section_content,
                    "source_step_id":step.get("id",i) ,
                    "token_count": section_tokens,
                    "status": "draft",
                    "edit_history": []
                }

                draft_sections.append(section)
                sections_written.append(section["title"])
                # 累计内容用于后续章节的上下文
                accumulated_content += f"\n### {section['title']}\n{section_content}\n"
                total_output_tokens += section_tokens
        
        # 合并章节为最终草稿
        final_draft = merge_sections_to_draft(
            task=task,
            sections=draft_sections,
            citations=citations
        )
        # 动态计算截断上限：每章节预留3000字符 + 引用列表2000字符
        # 避免写死10000导致多章节文档在章节中间被截断
        dynamic_max_length = max(len(plan) * 3000 + 2000, 15000)
        final_draft = smart_truncate_draft(final_draft, max_length=dynamic_max_length)

        # ── 引用裁剪与重新编号 ───
        # 从正文主体（引用列表之前）提取实际用到的编号
        body_text = final_draft.split("## 引用列表")[0]
        used_indices = {int(m) for m in re.findall(r'\[(\d+)\]', body_text)}
        if used_indices:
            # 只保留被引用的文献，按原顺序排列
            # 注意：必须用 copy() 防止修改 index 时污染原始 citations（影响 remap 里的旧编号查找）
            pruned_citations_raw = [c for c in citations if c['index'] in used_indices]
            old_to_new = {c['index']: new_i for new_i, c in enumerate(pruned_citations_raw, start=1)}
            pruned_citations = []
            for c in pruned_citations_raw:
                new_c = c.copy()
                new_c['index'] = old_to_new[c['index']]
                pruned_citations.append(new_c)
            # 替换正文中的旧编号（传入未修改的 citations 作为旧映射来源）
            final_draft = remap_citations(body_text, citations, pruned_citations)
            # 重建引用列表尾注
            citations_footer = "\n\n## 引用列表\n\n" + "\n\n".join(
                f"[{c['index']}] {c['title']} — {c['url']}" for c in pruned_citations
            )
            final_draft = final_draft + citations_footer
            citations = pruned_citations
            logger.info(f"---[Writer] 引用裁剪完成：{len(used_indices)} 个索引 → 保留 {len(citations)} 篇文献 ---")
        else:
            logger.warning("---[Writer] 正文中未检测到任何引用编号，跳过裁剪 ---")
        # ─────────────────────────────────────────────────────────────────

        logger.info(f"---[Writer] 全文合并完成，累计输出Tokens: {total_output_tokens}，字符数: {len(final_draft)} ---")
        return {
            "draft": final_draft, 
            "citations": citations,
            # 保存上下文
            "last_draft": final_draft,
            "last_citations": citations,
            "draft_sections": draft_sections,
            "writing_mode": "sectional",
            "writing_progress": len(draft_sections),
            "is_long_document": True,
            "token_stats": {
                "total_output_tokens": total_output_tokens,
                "estimated_total_tokens": estimated_total_tokens,
                "writing_mode": "sectional"
            }
        }
    else:
        # 整体生成
        def _escape_braces(text: str) -> str:
            return text.replace("{", "{{").replace("}", "}}") if text else ""

        full_prompt = WRITER_PROMPT.format(
            persona=_escape_braces(style_inst.get("persona", "")),
            structure=_escape_braces(style_inst.get("structure", "")),
            standards=_escape_braces(style_inst.get("standards", "")),
            format=_escape_braces(style_inst.get("format", "")),
            task=task,
            plan_context=plan_context,
            docs_context=docs_context,
        )
    
        # Combine messages for compatibility
        messages = [
            HumanMessage(content=full_prompt)
        ]
    
        # Use invoke instead of stream to return the final string for state update
        # The server will handle streaming via astream_events or separate callback if needed
        try:
            response = llm.invoke(messages)
            final_draft = response.content
            
            # Append citations
            citations_footer = "\n\n## 引用列表\n\n" + "\n\n".join(
                f"[{c['index']}] {c['title']} — {c['url']}" for c in citations
            )
            return {
                "draft": final_draft + citations_footer, 
                "citations": citations,
                # 保存上下文
                "last_draft": final_draft,
                "last_citations": citations,
                "draft_sections": None,
                "writing_mode": "integrated",
                "writing_progress": 1,
                "is_long_document": False,
                "token_stats": {
                    "total_output_tokens": count_tokens(final_draft),
                    "estimated_total_tokens": estimated_total_tokens,
                    "writing_mode": "integrated"
                }
            }
        except Exception as e:
            logger.error(f"Writer LLM failed: {e}")
            return {
                "draft": "生成报告失败。", 
                "citations": [],
                "last_draft": "",
                "last_citations": [],
                "draft_sections": None,
                "writing_mode": "integrated",
                "writing_progress": 0,
                "is_long_document": True,
                "token_stats": None,
            }
    
def verifier_node(state: ResearchState):
    """
    验证节点
    """
    draft = state.get("draft", "")
    citations = state.get("citations", [])
    revision_number = state.get("revision_number", 0)
    max_revisions = state.get("max_revisions", 3)

    main_indices = draft.split("## 引用列表")[0]
    used_indices = set(re.findall(r"\[(\d+)\]", main_indices))
    used_indices = {int(i) for i in used_indices}

    existing_indices = {c['index'] for c in citations}
    missing_indices = used_indices - existing_indices

    if missing_indices and revision_number < max_revisions:
        print(f"---[Verifier] 发现缺失引用索引: {missing_indices},正在标记修正---")
        return {
            "next": "writer",
            "revision_number": revision_number + 1
        }
    if missing_indices:
        print(f"---[Verifier] 达到最大修订次数或无缺少索引，强制通过---")
    
    return {"next": "reviewer"}

def reviewer_node(state: ResearchState):
    """
    审核节点
    """
    task = state["task"]
    # plan = state.get("plan", [])
    draft = state.get("draft", "")
    revision_number = state.get("revision_number", 0)
    max_revisions = state.get("max_revisions", 2)

    logger.info(f"[Reviewer] 正在审核第 {revision_number+1} 版稿件...")
    if revision_number >= max_revisions:
        logger.info(f"[Reviewer] 已达到最大修订次数，强制通过")
        return {"review": {"status": "pass", "reason": "达到最大修订次数"}}
    
    llm = get_llm(
        model_tag="smart",
        thread_id=state.get("thread_id"),
        user_id=state.get("user_id"),
        mode=state.get("mode"),
    )

    draft_segment = draft[:10000] if draft else ""
    system_prompt = REVIEVER_PROMPT.format(task=task, draft_segment=draft_segment, revision_number=revision_number)
    
    # 显式重构，增强对 Proxy API 的兼容性
    parser = JsonOutputParser()
    format_instructions = parser.get_format_instructions()
    
    full_prompt = f"你是一个严格的审稿人,只输出JSON\n\n{format_instructions}\n\n待审核内容:\n{system_prompt}"
    
    try:
        messages = [HumanMessage(content=full_prompt)]
        response = llm.invoke(messages)
        review_data = parser.parse(response.content)

        return {
            "review": review_data,
            "revision_number": revision_number + 1
        }
    except Exception as e:
        logger.error(f"Reviewer parsing failed: {e}")
        return {"review": {"status": "pass", "reason": "解析失败兜底"}, "revision_number": revision_number + 1}
    

def simple_researcher_node(state: ResearchState):
    """
    简单搜索节点
    """
    task = state["task"]

    tavily_tool = TavilySearch(max_results=1)

    logger.info(f"调用简单搜索工具，查询：{task}")
    print(f"搜索结果:{tavily_tool.invoke({'query': task})}")

    return {}

def chat_node(state: ResearchState):
    """
    聊天节点

    Input:
    {
        "task": str,
        "last_draft": str,
        "messages": [{...}, ...],
    }

    Output:
    {
        "response": str,
        "messages": [{"role": str,...}, ...],
    }
    """
    task = state["task"]
    last_draft = state.get("last_draft", "")
    last_citations = state.get("last_citations", [])
    messages = state.get("messages", [])

    llm = get_llm(
        model_tag="smart",
        thread_id=state.get("thread_id"),
        user_id=state.get("user_id"),
        mode=state.get("mode"),
    )

    logger.info(f"--- [Chat] 用户问题：{task[:50]}... ---")
    system_prompt = CHAT_PROMPT

    context_injection = ""
    if last_draft:
        draft_excerpt = last_draft[:2000]
        context_injection = f"""
    【生成的研究报告节选】
    {draft_excerpt}

    【引用】
    {chr(10).join([f"[{c['index']}] {c['title']}" for c in last_citations[:5]])}
    """
        logger.info(f"--- [Chat] 注入上下文信息 ---")

    if not messages:
        messages = []

    if not any(m.get("role") == "system" for m in messages):
        messages.insert(0, {
            "role": "system", 
            "content": system_prompt + context_injection
        })
    messages.append({
        "role": "user",
        "content": task
    })

    lc_messages = []
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")
        if role == "system":
            lc_messages.append(SystemMessage(content=content))
        elif role == "user":
            lc_messages.append(HumanMessage(content=content))
        # Adjust if AssistantMessage is available
        elif role == "assistant":
            from langchain_core.messages import AIMessage
            lc_messages.append(AIMessage(content=content))

    try:
        logger.info(f"--- [Chat] 正在调用LLM进行响应生成... ---")
        response = rate_limited_call(llm.invoke, lc_messages)
        assistant_response = response.content
        # Update messages history
        messages.append({
            "role": "assistant",
            "content": assistant_response
        })
        # 限制保留对话轮数
        system_messages = [m for m in messages if m.get("role") == "system"]
        orther_messages = [m for m in messages if m.get("role") != "system"]
        if len(orther_messages) > 20:
            orther_messages = orther_messages[-20:]
        messages = system_messages + orther_messages
        logger.info(f"--- [Chat] 响应生成完成 ---")

        return {
            "response": assistant_response,
            "messages": messages
        }

    except Exception as e:
        logger.error(f"Chat LLM failed: {e}")
        error_response = f"抱歉，聊天服务暂时不可用。错误信息: {str(e)[:100]}"
        messages.append({
            "role": "assistant",
            "content": error_response
        })
        return {
            "response": error_response,
            "messages": messages
        }
        