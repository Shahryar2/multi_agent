import operator
from typing import Annotated, List, TypedDict, Union

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from multi_agent.graph.agents import router_node, chat_agent_node, task_agent_node

from core.llm import get_llm
from tools.base import get_tools

# 1. 定义状态 (State)
# 状态是图在节点之间传递的数据包。这里我们主要传递消息历史。
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    next:str

# 2. 定义边 (Edges)
def router_condition(state: AgentState):
    """
    条件边逻辑：根据意图进行下一步
    """
    return state["next"]

def task_condition(state: AgentState):
    """
    条件边逻辑：任务智能体决定是否继续调用工具
    """
    last_message = state["messages"][-1] 
    if last_message.tool_calls: 
        return "tools"
    return END

# 3. 构建图 (Graph Construction)
def create_graph():
    # 初始化图
    workflow = StateGraph(AgentState)
    
    # 添加节点
    workflow.add_node("router", router_node)
    workflow.add_node("chat_agent", chat_agent_node)
    workflow.add_node("task_agent", task_agent_node)
    # 添加工具执行节点 (LangGraph 预置了 ToolNode，非常方便)
    workflow.add_node("tools", ToolNode(get_tools()))
    
    # 设置入口点
    workflow.set_entry_point("router")
    
    # 添加边 (Edges)
    # 逻辑：agent -> 判断(should_continue) -> tools 或 END
    workflow.add_conditional_edges(
        "router",
        router_condition,
        {
            "chat_agent": "chat_agent",
            "task_agent": "task_agent"
        }
    )
    # 逻辑：闲聊结束后回到路由节点还是应该结束(END)?
    workflow.add_edge("chat_agent", END)

    workflow.add_conditional_edges(
        "task_agent",
        task_condition,
        {
            "tools": "tools",
            END: END
        }
    ) 

    workflow.add_edge("tools", "task_agent")
    
    # 编译图
    app = workflow.compile()
    return app

# 测试代码
if __name__ == "__main__":
    app = create_graph()
    
    print("--- 开始执行工作流1 ---")
    # 模拟用户输入
    inputs1 = {"messages": [HumanMessage(content="最近北京天气？")]}
    for output in app.stream(inputs1):
        # 打印每一步的输出，方便调试
        for key, value in output.items():
            print(f"Node '{key}':")
            if "messages" in value:
                print(f'回复：{value["messages"]}') # 如果想看详细日志可以取消注释
    print("--- 执行结束 ---")

    print("--- 开始执行工作流2 ---")
    # 模拟用户输入
    inputs2 = {"messages": [HumanMessage(content="下午好小屈，如果我想写一篇论文，应该怎么做呢？")]}
    for output in app.stream(inputs2):
        # 打印每一步的输出，方便调试
        for key, value in output.items():
            print(f"Node '{key}':")
            if "messages" in value:
                print(f'回复：{value["messages"]}') # 如果想看详细日志可以取消注释
    print("--- 执行结束 ---")