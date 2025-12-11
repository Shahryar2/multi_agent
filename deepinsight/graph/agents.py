from langchain_core.messages import SystemMessage
from langchain_core.output_parsers import JsonOutputParser,StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_tavily import TavilySearch
from core.llm import get_llm
import logging
from tools.base import get_tools
from graph.state import ResearchState
from deepinsight.prompts.prompt_demo import CHAT_PROMPT, PLANNER_PROMPT, ROUTER_PROMPT,WRITER_PROMPT

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
    plan = state["plan"]
    documents = []

    tavily_tool = TavilySearch(max_results=3)
    
    for query in plan:
        # 调用搜索工具
        print(f"调用搜索工具，查询：{query}")
        try:
            results = tavily_tool.invoke({"query": query})
            if results:
                doc = f"[来源: {query}]\n{results}\n"
                documents.append(doc)

        except Exception as e:
            print(f"调用搜索工具搜索{query}失败：{e}")
            continue
    
    return {"documents": documents}

def writer_node(state: ResearchState):
    """
    根据收集到的文档，生成最终的研究报告。
    """
    task = state["task"]
    documents = state["documents"]
    llm = get_llm()
    
    # 文档拼接
    context = "\n\n".join(documents)

    # 定义写作的 Prompt
    system_prompt = WRITER_PROMPT.format(task=task)
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("user", "请根据以下文档撰写报告：\n{context}")
    ])
    
    chain = prompt | llm | StrOutputParser()
    draft = chain.invoke({
        "task": task,
        "context": context
    })
    
    return {"draft": draft}

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