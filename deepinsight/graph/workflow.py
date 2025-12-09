import operator
from typing import Annotated, List, TypedDict, Union

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from deepinsight.graph.agents import planner_node, research_node, writer_node
from graph.state import ResearchState

from core.llm import get_llm
from tools.base import get_tools

# # 2. 定义边 (Edges)
# def router_condition(state: AgentState):
#     """
#     条件边逻辑：根据意图进行下一步
#     """
#     return state["next"]

# def task_condition(state: AgentState):
#     """
#     条件边逻辑：任务智能体决定是否继续调用工具
#     """
#     last_message = state["messages"][-1] 
#     if last_message.tool_calls: 
#         return "tools"
#     return END

# 3. 构建图 (Graph Construction)
def create_graph():
    # 初始化图
    workflow = StateGraph(ResearchState)
    
    # 添加节点
    workflow.add_node("planner", planner_node)
    workflow.add_node("researcher", research_node)
    workflow.add_node("writer", writer_node)

    # # 添加工具执行节点 (LangGraph 预置了 ToolNode，非常方便)
    # workflow.add_node("tools", ToolNode(get_tools()))
    
    # 设置入口点
    workflow.set_entry_point("planner")
    
    workflow.add_edge("planner", "researcher")
    workflow.add_edge("researcher", "writer")
    workflow.add_edge("writer", END)
    
    # 编译图
    app = workflow.compile()
    return app

# 测试代码
if __name__ == "__main__":
    app = create_graph()
    
    task = "分析2024年中国新能源汽车出海现状"
    print(f"开始任务：{task}")

    inputs = {
        "task":task,
        "max_revisions":1,
        "revision_number":0,
    }
    for output in app.stream(inputs):
        for key, value in output.items():
            print(f"\n==={key}完成===")
            if key == "writer":
                print(f"\n最终报告内容：\n{value}\n")
                print(value["draft"])