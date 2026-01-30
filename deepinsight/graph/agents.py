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
from langchain_tavily import TavilySearch
from langchain_community.tools.tavily_search import TavilySearchResults
# from langchain_tavily import TavilySearchResults
from deepinsight.core.llm import get_llm
import logging
from concurrent.futures import ThreadPoolExecutor,as_completed
from deepinsight.tools.vector_store import VectorStore, vector_store
from deepinsight.utils.summarizer import map_summarize_documents
from deepinsight.utils.token_utils import count_tokens, term_document
from deepinsight.tools.base import get_tools
from deepinsight.graph.state import DraftState, ResearchState
from deepinsight.tools.search_provider import search_provider
from deepinsight.utils.normalizers import normalize_data, smart_truncate
from deepinsight.utils.normalizers import select_citations_for_section
from deepinsight.prompts.prompt_tool import select_style_preset,get_style_config
from deepinsight.prompts.prompt_demo import CHAT_PROMPT, PLANNER_PROMPT, REACHER_PROMPT, ROUTER_PROMPT, STYLE_CONFIG,WRITER_PROMPT,REVIEVER_PROMPT, STYLE_ANALYZER_PROMPT

logger = logging.getLogger(__name__)
api_semaphore = threading.Semaphore(3)
vector_store = VectorStore()

def router_node(state: ResearchState):
    """
    路由节点
    """
    task = state["task"]
    logger.info(f"Router received task: {task}")
    if not task:
        logger.error("Task is empty!")
        # Fallback or error handling
        return {"next": "chat"}

    llm = get_llm(model_tag="smart")

    try:
        system_prompt = ROUTER_PROMPT
        # Combine system prompt into user message to compatibility with some proxies
        prompt = ChatPromptTemplate.from_messages([
            ("user", f"{system_prompt}\n\n用户输入: {{task}}")
        ])
        chain = prompt | llm | StrOutputParser()

        logger.info(f"--- [Router] 正在调用LLM进行场景分类... ---")
        response_text = rate_limited_call(chain.invoke, {"task": task})
        logger.info(f"Router category: {response_text}")
        # Parse JSON output
        try:
            router_output = json.loads(response_text)
        except:
            # 容错处理
            router_output = {
                "category": "report",
                "field": "other",
                "depth": "moderate",
                "audience_type": "general"
            }
        category = router_output.get("category", "report")
        field = router_output.get("field", "lifestyle")
        depth = router_output.get("depth", "moderate")
        audience = router_output.get("audience", "general")
        # 自主选择风格预设
        style = select_style_preset({
            "category": category,
            "field": field,
            "depth": depth,
            "audience": audience,
            "task": task
        })
        style_config = get_style_config(style)
        logger.info(f"Router detected style: {style_config}")

    except Exception as e:
        logger.error(f"Router LLM failed: {e}")
        # Default fallback
        category = "report"
        field = "other"
        depth = "moderate"
        audience = "general"
        style = "tech_deep"
    
    # saved history context
    base_return = {
        "category": category,
        "field": field,
        "depth": depth,
        "audience": audience,
        "style": style,
        "last_draft": state.get("last_draft",""),
        "last_citations": state.get("last_citations",[])
    }

    if category == "chat":
        return {**base_return, "next": "chat"}
    else:
        return {**base_return, "next": "planner"}

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
    llm = get_llm(model_tag="smart")

    if not review_feedback or review_feedback.get("status") == "pass":
        thought_msg = f"任务 '{task}'确定为[{category}/{field}]场景，深度[{depth}]，面向[{audience}]，开始拆解初步执行计划...."
        system_prompt = PLANNER_PROMPT.format(
            category=category,
            field=field,
            depth=depth, 
            task=task
        )
        user_input = f"任务：{task}"
    else:
        print(f"---[Planner]收到Review反馈，调整计划{review_feedback}---")
        thought_msg = f"收到审核反馈，正在根据意见[{review_feedback.get('reason')}]调整执行计划...."
        system_prompt = f"""
        你是一个具有深度反思能力的首席分析师。
        你之前的研究计划未能通过审核，现在需要基于反馈进行反思并调整计划。
        
        【审核反馈】
        状态：{review_feedback.get('status')}
        意见：{review_feedback.get('reason')}
        缺失内容：{review_feedback.get('missing')}
        
        【反思要求】
        1. 分析为什么之前的研究没能覆盖到这些缺失点。
        2. 针对缺失内容，增加 1-2 个极其精准的搜索或分析步骤。
        3. 保持原有已完成步骤的逻辑连贯性，不要删除已有的正确结论。
        
        请以 JSON 数组格式输出更新后的完整执行计划。
    """
        user_input = f"原任务：{task}\n 审核意见：{review_feedback.get('missing','内容缺失')}\n"

    # 使用 JsonOutputParser 获取格式说明
    parser = JsonOutputParser()
    format_instructions = parser.get_format_instructions()

    # 显式构建 Prompt 字符串
    full_prompt = f"{system_prompt}\n\n{format_instructions}\n\n用户输入: {user_input}"
    
    # 显式使用 HumanMessage
    messages = [HumanMessage(content=full_prompt)]
    
    try:
        response = llm.invoke(messages)
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

        for step in plan:
            if "status" not in step:
                step["status"] = "pending"

        return {
            "plan": plan,
            "current_step_index": 0,
            "thought_process": thought_msg
        }
    except Exception as e:
        print(f"---[Planner]解析失败，生成兜底分布计划{e}---")
        return {
            "plan": [{
                "type": "research", 
                "description":f"{task} - 第一部分：核心概念与背景调研",
                "status":"pending"
            },
            {
                "type": "research",
                "description":f"{task} - 第二部分：深度分析与核心内容",
                "status":"pending"
            },
            {
                "type": "research",
                "description":f"{task} - 第三部分：总结、建议",
                "status":"pending"
            }],
            "current_step_index": 0,
            "thought_process": thought_msg
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

def rate_limited_call(func, *args, **kwargs):
    """
    包装器：速率限制+重试逻辑
    """
    max_retries = 3
    for attempt in range(max_retries):
        with api_semaphore:
            try:
                # 随机抖动
                time.sleep(random.uniform(1.0, 2.5))
                return func(*args, **kwargs)
            except Exception as e:
                if ('429' in str(e) or '500' in str(e)) and attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 8
                    logger.warning(f"API调用失败，尝试重试 {attempt+1}/{max_retries} 次: {e}")
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
    def execute_single_task(task_info):
        sub_task_description = task_info.get("description","")
        safe_task = main_task[:20]
        query = f'{safe_task} - {sub_task_description}'[:200]
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
                    print(f"[Researcher]已添加 {len(new_docs)} 条文档到向量存储")
                except Exception as e:
                    logger.error(f"向量存储添加文档失败: {e}")
            
            if not new_docs:
                logger.warning(f"关键词 {query} 原始返回结果数: {len(cleaned_results)}，但无有效文档")

            step_summary = ""
            if new_docs:
                llm = get_llm(model_tag="smart")
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
        llm,
        all_sections_context: str="",
        max_tokens: int = 3000
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
    
    citations_text = select_citations_for_section(
        citations,
        section_topic=step_description,
        section_result=step_result,
        max_citations=3,
        max_snippet_length=150
    )
    step_result_short = smart_truncate(step_result, max_length=600)
    context_short = smart_truncate(all_sections_context, max_length=500)
    
    persona = style_config.get("persona","你是一个专业内容撰写者")
    persona_short = smart_truncate(persona, max_length=100, add_ellipsis=True)
    
    target_words = min(500,(max_tokens * 0.15))

    section_prompt = f"""{persona_short}

【任务目标】
任务：{task}
当前章节：第 {section_id} 部分 - {step_description}

【核心素材】
研究结论：{step_result_short}

【参考资料】
{citations_text}

{f"【前文脉络】{context_short}" if context_short else ""}

【写作要求】
1. 字数控制在 {target_words} 字以内。
2. 必须符合上述设定的写作风格（语气、受众）。
3. 使用 Markdown 格式，引用格式为 [index]。
4. 直接输出正文，不要包含 "好的" 或标题。

开始写作：
"""
    llm = get_llm(model_tag="smart")
    prompt_tokens = count_tokens(section_prompt, model_tag="smart")
    logger.info(f"章节 {section_id} 提示词Tokens: {prompt_tokens}, 目标输出Tokens: {max_tokens}")

    messages = [HumanMessage(content=section_prompt)]
    response = rate_limited_call(llm.invoke,messages)
    section_content = response.content
    
    # 检测并修复截断
    # section_content = smart_truncate(section_content, 3000)
    section_content = _fix_truncated_ending(section_content)
    
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

    citations_footer = "\n\n## 引用列表\n" + "\n".join(
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
    llm = get_llm(model_tag="smart")

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
        draft_sections: List[DraftState] = []
        total_output_tokens = 0
        accumulated_content = ""
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
            logger.info(f"---[Writer] 正在生成章节 {i+1}: {step.get('description','章节')} ---")
            section_content, section_tokens = generate_section(
                section_id=i + 1,
                plan_step={**step,"task": task},
                style_config=style_inst,
                citations=citations,
                llm=llm,
                all_sections_context=accumulated_content,
                max_tokens=per_section_buget
            )
            section: DraftState = {
                "section_id": i + 1,
                "title": step.get("description",f'第 {i+1} 章节'),
                "content": section_content,
                "source_step_id":step.get("id",i) ,
                "token_count": section_tokens,
                "status": "draft",
                "edit_history": []
            }

            draft_sections.append(section)
            # 累计内容用于后续章节的上下文
            accumulated_content += f"\n### {step.get('description',f'第 {i+1} 章节')}\n{section_content}\n"
            total_output_tokens += section_tokens
        
        # 合并章节为最终草稿
        final_draft = merge_sections_to_draft(
            task=task,
            sections=draft_sections,
            citations=citations
        )
        logger.info(f"---[Writer] 全文合并完成，累计输出Tokens: {total_output_tokens} ---")
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
        full_prompt = WRITER_PROMPT.format(
            persona = style_inst['persona'],
            structure = style_inst['structure'],
            standards = style_inst['standards'],
            format = style_inst['format'],
            task=task, 
            # style=style, 
            plan_context=plan_context, 
            docs_context=docs_context
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
            citations_footer = "\n\n## 引用列表\n" + "\n".join(
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
    
    llm = get_llm(model_tag="smart")

    draft_segment = draft[:10000] if draft else ""
    system_prompt = REVIEVER_PROMPT.format(task=task, draft_segment=draft_segment)
    
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

    llm = get_llm(model_tag="smart")

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
        