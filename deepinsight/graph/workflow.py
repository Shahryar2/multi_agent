import sqlite3
from typing import Annotated, List, TypedDict, Union
from langgraph.checkpoint.sqlite import SqliteSaver
# from langgraph.checkpoint. import SqliteSaver
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from deepinsight.graph.agents import (
    chat_node, 
    reviewer_node, 
    router_node,
    planner_node, 
    research_node,  
    writer_node,
)
from graph.state import ResearchState

# 构建图 (Graph Construction)
def create_graph():
    # 初始化图
    workflow = StateGraph(ResearchState)
    
    # 添加节点
    workflow.add_node("router", router_node)
    workflow.add_node("planner", planner_node)
    workflow.add_node("researcher", research_node)
    workflow.add_node("writer", writer_node)
    workflow.add_node("reviewer", reviewer_node)
    workflow.add_node("chat", chat_node)
   
    # 设置入口点
    workflow.set_entry_point("router")

    workflow.add_conditional_edges(
        "router",
        lambda state: state["next"],
        {
            "planner": "planner",
            # "simple_researcher": "simple_researcher",
            "chat": "chat",
        }
    )
    # 研究流程
    workflow.add_edge("planner", "researcher")
    workflow.add_edge("researcher", "writer")
    workflow.add_edge("writer", "reviewer")

    workflow.add_conditional_edges(
        "reviewer",
        lambda state: state.get("review",{}).get("status"),
        {
            "pass": END,
            "fail": "planner",
        }
    )

    # 聊天
    workflow.add_edge("chat", END)

    # --- 持久化配置 (SqliteSaver) ---
    conn = sqlite3.connect("checkpoints.sqlite", check_same_thread=False)
    memory = SqliteSaver(conn)

    # 编译图
    app = workflow.compile(checkpointer=memory, interrupt_before=["researcher"])
    return app

"""测试代码"""
if __name__ == "__main__":
    app = create_graph()
    
    task = "分析2025年中国新能源汽车出海现状"
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