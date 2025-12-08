from langchain_core.messages import SystemMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_community.tools.tavily_search import TavilySearchResults
from core.llm import get_llm
from tools.base import get_tools
from graph.state import ResearchState

def planner_node(state: ResearchState):
    """
    接收任务，生成搜索计划。
    """
    task = state["task"]
    llm = get_llm()
    
    # 定义计划的 Prompt
    system_prompt = """你是一个资深的研究规划师。
    你的任务是接收一个研究主题，并将其拆解为 3 个具体的搜索引擎查询关键词。
    这些查询词应该涵盖主题的不同方面（如现状、趋势、风险等）。
    
    请只输出一个 JSON 列表，格式如下：
    ["查询词1", "查询词2", "查询词3"]"""
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("user", "{task}")
    ])
    
    chain = prompt | llm | JsonOutputParser(list)
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

    tavily_tool = TavilySearchResults(max_results=3)
    
    for query in plan:
        # 调用搜索工具
        print(f"调用搜索工具，查询：{query}")
        try:
            results = tavily_tool.invoke({"query": query})
            for result in results:
                # 提取content
                content = result.get('content')
                if content:
                    doc = f"[来源: {query}]\n{content}\n"
                    documents.append(doc)

        except Exception as e:
            print(f"调用搜索工具搜索{query}失败：{e}")
            continue
    
    return {"documents": documents}

# # --- 3. 任务执行智能体 (Task Agent) ---
# def task_agent_node(state):
#     """
#     专注于执行任务，可以调用工具。
#     """
#     messages = state["messages"]
#     llm = get_llm()
#     tools = get_tools()
    
#     # 绑定工具
#     model_with_tools = llm.bind_tools(tools)
#     response = model_with_tools.invoke(messages)
#     return {"messages": [response]}