import json
import re
from langchain_core.documents import Document
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import JsonOutputParser,StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_tavily import TavilySearch
from core.llm import get_llm
import logging
from concurrent.futures import ThreadPoolExecutor,as_completed
from deepinsight.tools.vector_store import VectorStore, vector_store
from deepinsight.utils.summarizer import map_summarize_documents
from deepinsight.utils.token_utils import count_tokens, term_document
from tools.base import get_tools
from graph.state import ResearchState
from deepinsight.utils.normalizers import normalize_data
from deepinsight.prompts.prompt_demo import CHAT_PROMPT, PLANNER_PROMPT, REACHER_PROMPT, ROUTER_PROMPT,WRITER_PROMPT,REVIEVER_PROMPT

logger = logging.getLogger(__name__)
vector_store = VectorStore()

def router_node(state: ResearchState):
    """
    路由节点
    """
    task = state["task"]
    llm = get_llm(model_tag="smart")
    
    system_prompt = ROUTER_PROMPT

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("user", "{task}")
    ])
    chain = prompt | llm | StrOutputParser()
    category = chain.invoke({"task": task})
    if "report" in category:
        return {"next": "planner"}
    if "search" in category:
        return {"next": "simple_researcher"}
    if "chat" in category:
        return {"next": "chat"}

def planner_node(state: ResearchState):
    """
    拆解任务
    """
    task = state["task"]
    catagory = state.get("catagory","general")
    review_feedback = state.get("review",{})
    llm = get_llm(model_tag="smart")

    if not review_feedback or review_feedback.get("status") == "pass":
        system_prompt = PLANNER_PROMPT.format(category=catagory, task=task)
        user_input = f"任务：{task}"
    else:
        print(f"---[Planner]收到Review反馈，调整计划{review_feedback}---")
        system_prompt = """
        
    """
        user_input = f"原任务：{task}\n 审核意见：{review_feedback.get('missing','内容缺失')}\n"

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("user", "{user_input}")
    ])
    
    chain = prompt | llm | JsonOutputParser()
    try:
        plan = chain.invoke({"user_input": user_input})
        if not isinstance(plan,list):
            plan = [plan]

        for step in plan:
            if "status" not in step:
                step["status"] = "pending"

        return {"plan": plan,"current_step_index": 0}
    except Exception as e:
        print(f"---[Planner]解析失败，使用原始任务{e}---")
        return {
            "plan": [{
                "type": "research", 
                "description":f"针对{task}进行补充搜索",
                "status":"pending"
            }],
            "current_step_index": 0
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

def research_node(state: ResearchState):
    '''
    并行研究节点,负责当前索引子任务
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
    
    def execute_single_task(task_info):
        query = task_info.get("description", "")
        try:
            tavily_tool = TavilySearch(max_results=5)
            res = tavily_tool.invoke({"query": query})
            raw_results = res.get("results", [])

            new_docs = normalize_data(raw_results, query)
            if new_docs:
                try:
                    vector_store.add_documents(new_docs)
                    print(f"[Researcher]已添加 {len(new_docs)} 条文档到向量存储")
                except Exception as e:
                    logger.error(f"向量存储添加文档失败: {e}")

            step_summary = ""
            if new_docs:
                llm = get_llm(model_tag="smart")
                # 构建小型上下文
                termmed_docs = term_document(
                    new_docs,
                    max_tokens=6000,
                )
                context_text = "\n".join([f"- {doc.get('text')}" for doc in termmed_docs])
                prompt = REACHER_PROMPT.format(query=query, context_text=context_text)

                try:
                    response = llm.invoke(prompt)
                    step_summary = response.content
                    print(f"---[Researcher]子任务总结: {step_summary}---")
                except Exception as e:
                    logger.error(f"Researcher总结失败: {e}")
                    step_summary = "本步骤未能生成总结。"
            else:
                step_summary = "未能搜索到有效信息。"
                    
            return {
                "success": True,
                "results": step_summary,
                "docs": new_docs,
                "docs_ids": [doc.get("id") for doc in new_docs],
                "raw_results": raw_results
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
            print(f"---[Researcher]子任务完成: {plan[idx]['description'][:50]}---")
        else:
            plan[idx]["status"] = "failed"
            plan[idx]["result"] = f"任务失败: {res.get('error')}"
            print(f"---[Researcher]子任务失败: {plan[idx]['description'][:50]}---")

    return {
        "documents": all_new_docs,
        "current_step_index": len(plan),
        "plan": plan,
        "bg_investigation": all_raw_results
    }

def writer_node(state: ResearchState):
    """
    撰写
    """
    task = state["task"]
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

    doc_map = {doc.get("id"): doc for doc in documents if doc.get("id")}
    for step in plan:
        step_ids = step.get("doc_ids", [])
        for doc_id in step_ids:
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
        citations.append({
            "index":idx,
            "id":seg.get("id"),
            "title": seg.get("title"),
            "url": seg.get("url"),
            "snippet": seg.get("text")[:300]
        })
    
    docs_context = "\n\n".join([
        f"[{i+1}] Title: {seg.get('title')}\nContent: {seg.get('text')}\nSource: {seg.get('url')}" 
        for i, seg in enumerate(retrieved_docs)
    ])

    full_prompt = WRITER_PROMPT.format(task=task, plan_context=plan_context, docs_context=docs_context)
    
    messages = [
        SystemMessage(content="你是一个专业的研报撰写专家。"),
        HumanMessage(content=full_prompt)
    ]
    draft = llm.invoke(messages)
    content = draft.content

    citations_footer = "\n\n## 引用列表\n" + "\n".join(
        f"[{c['index']}] {c['title']} — {c['url']}" for c in citations
    )
    final_draft = content + citations_footer
    
    return {"draft": final_draft,"citations": citations}

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
    """
    task = state["task"]
    llm = get_llm()

    prompt = ChatPromptTemplate.from_messages([
        ("system", CHAT_PROMPT),
        ("user", "{task}")
    ])
    
    chain = prompt | llm | StrOutputParser()
    response = chain.invoke({"task": task})
    
    logger.info(f"聊天响应：{response}")
    print(f"聊天响应：{response}")

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
    prompt = ChatPromptTemplate.from_messages([
        ("system", "你是一个严格的审稿人,只输出JSON"),
        ("user", "{content}")
    ])
    chain = prompt | llm | JsonOutputParser()

    try:
        review_data = chain.invoke({"content":system_prompt})
        return {
            "review": review_data,
            "revision_number": revision_number + 1
        }
    except Exception as e:
        logger.error(f"Reviewer parsing failed: {e}")
        return {"review": {"status": "pass", "reason": "解析失败兜底"}, "revision_number": revision_number + 1}