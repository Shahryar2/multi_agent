import json
import random
import re
import threading
import time
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
from deepinsight.graph.state import ResearchState
from deepinsight.tools.search_provider import search_provider
from deepinsight.utils.normalizers import normalize_data
from deepinsight.prompts.prompt_demo import CHAT_PROMPT, PLANNER_PROMPT, REACHER_PROMPT, ROUTER_PROMPT,WRITER_PROMPT,REVIEVER_PROMPT, STYLE_ANALYZER_PROMPT

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
        category = rate_limited_call(chain.invoke, {"task": task})

        logger.info(f"Router category: {category}")
        
        # Analyze style
        style_prompt = ChatPromptTemplate.from_messages([
            ("user", f"{STYLE_ANALYZER_PROMPT}\n\n用户输入: {{task}}")
        ])
        style_chain = style_prompt | llm | StrOutputParser()

        logger.info(f"--- [Router] 正在调用LLM进行风格分析... ---")
        style = rate_limited_call(style_chain.invoke, {"task": task})
        style = style.strip().strip('"').lower()
        if style not in ["casual", "story"]:
            style = "professional"
        logger.info(f"Router detected style: {style}")

    except Exception as e:
        logger.error(f"Router LLM failed: {e}")
        # Default fallback
        category = "report"
        style = "professional"

    # Normalize category
    category = category.strip().strip('"').lower()
    
    # saved history context
    base_return = {
        "category": category,
        "style": style,
        "last_draft": state.get("last_draft",""),
        "last_citations": state.get("last_citations",[])
    }

    if "report" in category:
        return {**base_return,"next": "planner"}
    if "search" in category:
        # Fallback search to planner for now as simple_researcher is not wired
        return {**base_return,"next": "planner"}
    if "chat" in category:
        return {**base_return,"next": "chat"}
    
    # Default to planner
    return {**base_return,"next": "planner"}

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
    review_feedback = state.get("review",{})
    llm = get_llm(model_tag="smart")

    if not review_feedback or review_feedback.get("status") == "pass":
        thought_msg = f"任务 '{task}'确定为新任务，开始拆解初步执行计划...."
        system_prompt = PLANNER_PROMPT.format(category=category, task=task)
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
        # 手动解析
        plan = parser.parse(response.content)

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
        print(f"---[Planner]解析失败，使用原始任务{e}---")
        return {
            "plan": [{
                "type": "research", 
                "description":f"针对{task}进行补充搜索",
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

    category = state.get("category","general").lower()
    config_map = {
        "chat": "social_media",
        "social": "social_media",
        "travel": "travel",
        "academia": "academic",
        "report": "general",
    }
    search_mode = config_map.get(category, "general")
    logger.info(f"---[Researcher]研究类别: {category},搜索模式: {search_mode}---")
    def execute_single_task(task_info):
        sub_task_description = task_info.get("description","")
        query = f'{main_task} - {sub_task_description}'
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
                doc = Document(
                    page_content=item.get('content'),
                    metadata={
                        "source": item['url'],
                        "title": item.get('title'),
                        "type": item.get('type'),
                    }
                )
                new_docs.append(doc)

            if new_docs:
                try:
                    vector_store.add_documents(new_docs)
                    print(f"[Researcher]已添加 {len(new_docs)} 条文档到向量存储")
                except Exception as e:
                    logger.error(f"向量存储添加文档失败: {e}")

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
                step_summary = "未能搜索到有效信息。"
                    
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

def writer_node(state: ResearchState):
    """
    撰写
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
    style = state.get("style", "professional")  # Get style
    plan = state.get("plan",[])
    documents = state.get("documents", [])
    llm = get_llm(model_tag="smart")

    plan_context = ""
    for step in plan:
        plan_context += f"### 研究步骤:{step.get('description')}\n"
        plan_context += f"### 研究结论:{step.get('result','无结果')}\n\n"

    logger.info(f"---[Writer] 正在基于大纲检索向量库 ---")
    retrieved_docs = []
    seen_ids = set()    # 去重ID
    rag_success = False

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
        plan_tokens = count_tokens(plan_context,model_tag="basic")
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
    
    docs_context = "\n\n".join([
        f"[{c['index']}] Title: {c['title']}\nContent: {c['full_text']}\nSource: {c['url']}" 
        for c in citations
    ])

    full_prompt = WRITER_PROMPT.format(
        task=task, 
        style=style, 
        plan_context=plan_context, 
        docs_context=docs_context
    )
    
    # Combine messages for compatibility
    messages = [
        HumanMessage(content=f"你是一个专业的研报撰写专家。\n\n{full_prompt}")
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
            "last_citations": citations
        }
    except Exception as e:
        logger.error(f"Writer LLM failed: {e}")
        return {
            "draft": "生成报告失败。", 
            "citations": [],
            "last_draft": "",
            "last_citations": []
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
    
    llm = get_llm(model_tag="basic")

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

    llm = get_llm(model_tag="basic")

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
        