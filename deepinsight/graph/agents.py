import json
import re
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import JsonOutputParser,StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_tavily import TavilySearch
from core.llm import get_llm
import logging
from deepinsight.utils.summarizer import map_summarize_documents
from deepinsight.utils.token_utils import count_tokens, term_document
from tools.base import get_tools
from graph.state import ResearchState
from deepinsight.utils.normalizers import normalize_data
from deepinsight.prompts.prompt_demo import CHAT_PROMPT, PLANNER_PROMPT, REACHER_PROMPT, ROUTER_PROMPT,WRITER_PROMPT,REVIEVER_PROMPT

logger = logging.getLogger(__name__)

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
    llm = get_llm(model_tag="smart")
    
    # 定义计划的 Prompt
    system_prompt = PLANNER_PROMPT.format(category=catagory, task=task)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("user", "{task}")
    ])
    
    chain = prompt | llm | JsonOutputParser()
    try:
        plan = chain.invoke({"task": task})
        if isinstance(plan,list):
            return {"plan": plan,"current_step_index": 0}
        else:
            return {"plan": [task]}
    except Exception as e:
        print(f"---[Planner]解析失败，使用原始任务{e}---")
        plan = [task]
    
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
    单步研究节点,负责当前索引子任务
    '''
    idx = state.get("current_step_index", 0)
    plan = state.get("plan", [])
    
    if idx >= len(plan):
        return {"current_step_index": idx+1}
    
    current_task = plan[idx]
    query = current_task.get("description", "")
    print(f"---[Researcher]执行子任务 {idx+1}/{len(plan)}: {query}---")

    tavily_tool = TavilySearch(max_results=5)
    search_results = tavily_tool.invoke({"query": query})
    
    new_documents = []
    raw_results = search_results.get("results", []) 
    try:
        new_documents = normalize_data(raw_results, query)
    except Exception as e:
        logger.error(f"数据清洗失败: {e}")

    step_summary = ""
    if new_documents:
        llm = get_llm(model_tag="smart")
        # 构建小型上下文
        termmed_docs = term_document(
            new_documents,
            max_tokens=10000,
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
    current_task['result'] = step_summary
    current_task['status'] = 'completed'
    plan[idx] = current_task

    return {
        "documents": new_documents,
        "current_step_index": idx + 1,
        "plan": plan,
        "bg_investigation": raw_results
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
    
    # 计算占用token
    plan_tokens = count_tokens(plan_context,model_tag="basic")
    print(f"---[Writer] 骨架Tokens:{plan_tokens}---")

    # 这里的定值判断有必要吗
    MODEL_LIMIT = 32000
    RESERVED_OUTPUT = 4000
    SYSTEM_PROMPT_ESTIMATE = 2000

    availble_for_docs = MODEL_LIMIT - RESERVED_OUTPUT - SYSTEM_PROMPT_ESTIMATE - plan_tokens
    if availble_for_docs < 0:
        logger.warning(f"计划内容过长，超出模型限制")
        availble_for_docs = 1000

    processed_docs = term_document(
        documents,
        max_tokens=availble_for_docs, 
        model_tag="smart"
    )
    
    citations = []
    for idx,seg in enumerate(processed_docs,start=1):
        citations.append({
            "index":idx,
            "id":seg.get("id"),
            "title": seg.get("title"),
            "url": seg.get("url"),
            "snippet": seg.get("text")[:300]
        })
    
    docs_context = "\n\n".join([f"[{i+1}] Title: {seg.get('title')}\nContent: {seg.get('text')}\nSource: {seg.get('url')}" for i, seg in enumerate(processed_docs)])

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
    plan = state.get("plan", [])
    draft = state.get("draft", "")
    llm = get_llm(model_tag="basic")

    prompt = ChatPromptTemplate.from_messages([
        ("system", REVIEVER_PROMPT),
        ("user", "Plan:{plan}\n\nDraft:{draft}\n\n请输出 JSON.")
    ])
    chain = prompt | llm | StrOutputParser()
    raw_res = chain.invoke({"plan": plan, "draft": draft})

    try:
        json_match = re.search(r'\{.*\}', raw_res, re.DOTALL)
        if json_match:
            review_data = json.loads(json_match.group())
            return {"review": review_data}
        else:
            res = json.loads(raw_res)
            return {"review": res}
    except Exception as e:
        logger.error(f"Reviewer parsing failed: {e}")
        return {"review": {"status": "pass", "reason": "解析失败兜底"}}
