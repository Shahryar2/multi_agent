import json
import re
from langchain_core.messages import SystemMessage
from langchain_core.output_parsers import JsonOutputParser,StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_tavily import TavilySearch
from core.llm import get_llm
import logging
from deepinsight.utils.summarizer import map_summarize_documents
from deepinsight.utils.token_utils import term_document
from tools.base import get_tools
from graph.state import ResearchState
from deepinsight.utils.normalizers import normalize_data
from deepinsight.prompts.prompt_demo import CHAT_PROMPT, PLANNER_PROMPT, ROUTER_PROMPT,WRITER_PROMPT,REVIEVER_PROMPT

logger = logging.getLogger(__name__)

def router_node(state: ResearchState):
    """
    路由节点
    """
    task = state["task"]
    llm = get_llm()
    
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
    接收任务，生成搜索计划。
    """
    task = state["task"]
    llm = get_llm()
    
    # 定义计划的 Prompt
    system_prompt = PLANNER_PROMPT
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("user", "{task}")
    ])
    
    chain = prompt | llm | JsonOutputParser()
    try:
        plan = chain.invoke({"task": task})
        if isinstance(plan,list):
            return {"plan": plan}
        else:
            return {"plan": [task]}
    except Exception as e:
        print(f"---[Planner]解析失败，使用原始任务{e}---")
        plan = [task]
    
    
def research_node(state: ResearchState):
    """
    根据搜索计划，调用搜索工具获取信息。
    """
    plan = state.get("plan", [])
    documents = state.get("documents", []) or []
    # background_investigation
    raw_results = state.get("bg_investigation", []) or []

    tavily_tool = TavilySearch(max_results=3)
    
    for query in plan:
        # 调用搜索工具
        print(f"调用搜索工具，查询：{query}")
        try:
            results = tavily_tool.invoke({"query": query})
            # 记录原始返回
            raw_results.append({"query": query, "raw": results})
            segments = normalize_data(results,query,source="tavily")
            documents.extend(segments)
        except Exception as e:
            print(f"调用搜索工具搜索{query}失败：{e}")
            continue
    
    return {"documents": documents, "bg_investigation": raw_results}

def writer_node(state: ResearchState):
    """
    根据收集到的文档，生成最终的研究报告。
    """
    task = state["task"]
    documents = state.get("documents", []) or []
    llm = get_llm()

    # Map_reduce 文档摘要
    summarized_docs = map_summarize_documents(documents, max_workers=5)

    processed_docs = term_document(
        summarized_docs,
        max_tokens=25000, 
        max_tokens_per_doc=1500,
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
    
    # for c in citations:
    #     if not c.get("url"):
    #         c['url'] = "来源缺失"

    # 定义写作的 Prompt
    system_prompt = WRITER_PROMPT.format(task=task)
    docs_context = "\n\n".join([f"[{i+1}] {seg.get('text')}" for i, seg in enumerate(processed_docs)])

    user_instructions = (
        f"任务：请基于以下资料撰写关于“{task}”的深度报告。\n\n"
        "要求：\n"
        "1. **必须**在文中每个事实陈述后加上引用编号，例如：“市场增长率达到15% [1]。”\n"
        "2. **绝对不要**在文末自己生成“引用列表”或“参考文献”章节，系统会自动处理。\n"
        "3. 保持客观、专业，使用 Markdown 格式。\n\n"
        f"参考资料：\n{docs_context}"
    )
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("user", "{instructions}")
    ])
    
    chain = prompt | llm | StrOutputParser()
    draft = chain.invoke({
        "instructions": user_instructions,
        "task": task
    })
    citations_footer = "\n\n## 引用列表\n" + "\n".join(
        f"[{c['index']}] {c['title']} — {c['url']}" for c in citations
    )
    final_draft = draft + citations_footer
    
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
    llm = get_llm()

    prompt = ChatPromptTemplate.from_messages([
        ("system", REVIEVER_PROMPT),
        ("user", "Plan:{plan}\n\nDraft:{draft}\n\n请输出 JSON.")
    ])
    chain = prompt | llm | StrOutputParser()
    try:
        raw_res = chain.invoke({"plan": plan, "draft": draft})
        json_match = re.search(r'\{.*\}', raw_res, re.DOTALL)
        if json_match:
            res = json.loads(json_match.group())
        else:
            res = {"status": "fail", "missing": ['无法解析模型输出']}
        if res.get("status") == "pass":
            return {"review": {"status": "pass"}}
        else:
            return {"review": {"status": "fail", "missing": res.get("missing", [])}}
    except Exception as e:
        logger.error(f"Reviewer parsing failed: {e}")
        return {"review": {"status": "fail", "missing": plan}}
