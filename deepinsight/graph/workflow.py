import sqlite3
from typing import Annotated, List, TypedDict, Union
from langgraph.checkpoint.sqlite import SqliteSaver
# from langgraph.checkpoint. import SqliteSaver
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from deepinsight.graph.agents import (
    chat_node,
    orchestrator_node, 
    reviewer_node, 
    router_node,
    planner_node, 
    research_node,  
    writer_node,
    verifier_node
)
from deepinsight.graph.state import ResearchState

# 构建图 (Graph Construction)
def create_graph():
    # 初始化图
    workflow = StateGraph(ResearchState)
    
    # 添加节点
    workflow.add_node("router", router_node)
    workflow.add_node("planner", planner_node)
    workflow.add_node("orchestrator", orchestrator_node)
    workflow.add_node("researcher", research_node)
    workflow.add_node("writer", writer_node)
    workflow.add_node("verifier", verifier_node)
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
    workflow.add_edge("planner", "orchestrator")
    
    workflow.add_conditional_edges(
        "orchestrator",
        lambda state: state["next"],
        {
            "researcher": "researcher",
            "writer": "writer",
        }
    )
    
    workflow.add_edge("researcher", "orchestrator")
    workflow.add_edge("writer", "verifier")

    workflow.add_conditional_edges(
        "verifier",
        lambda state: state.get("next"),
        {
            "writer": "writer",
            "reviewer": "reviewer",
        }
    )

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
    app = workflow.compile(checkpointer=memory, interrupt_after=["planner"])
    return app
