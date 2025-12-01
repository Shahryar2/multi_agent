import operator
from typing import Annotated, List, TypedDict, Union

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

from core.llm import get_llm
from tools.base import get_tools

# 1. 定义状态 (State)
# 状态是图在节点之间传递的数据包。这里我们主要传递消息历史。
class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]

# 2. 定义节点 (Nodes)
# 节点是执行具体逻辑的地方。

def call_model(state: AgentState):
    """
    核心思考节点：调用大模型，决定下一步是回复用户还是调用工具。
    """
    messages = state['messages']
    llm = get_llm()
    tools = get_tools()
    
    # 将工具绑定到模型上，让模型知道有哪些工具可用
    model_with_tools = llm.bind_tools(tools)
    
    response = model_with_tools.invoke(messages)
    return {"messages": [response]}

def should_continue(state: AgentState):
    """
    条件边逻辑：判断是否需要继续调用工具。
    """
    messages = state['messages']
    last_message = messages[-1]
    
    # 如果模型返回的消息包含 tool_calls，说明它想调用工具 -> 转到 'tools' 节点
    if last_message.tool_calls:
        return "tools"
    # 否则说明它已经生成了最终回复 -> 结束
    return END

# 3. 构建图 (Graph Construction)
def create_graph():
    # 初始化图
    workflow = StateGraph(AgentState)
    
    # 添加节点
    workflow.add_node("agent", call_model)
    
    # 添加工具执行节点 (LangGraph 预置了 ToolNode，非常方便)
    tool_node = ToolNode(get_tools())
    workflow.add_node("tools", tool_node)
    
    # 设置入口点
    workflow.set_entry_point("agent")
    
    # 添加边 (Edges)
    # 逻辑：agent -> 判断(should_continue) -> tools 或 END
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            END: END
        }
    )
    
    # 逻辑：工具执行完后，必须把结果扔回给 agent 让它继续思考
    workflow.add_edge("tools", "agent")
    
    # 编译图
    app = workflow.compile()
    return app

# 测试代码
if __name__ == "__main__":
    app = create_graph()
    
    # 模拟用户输入
    inputs = {"messages": [HumanMessage(content="北京今天天气怎么样？")]}
    
    print("--- 开始执行工作流 ---")
    for output in app.stream(inputs):
        # 打印每一步的输出，方便调试
        for key, value in output.items():
            print(f"Node '{key}':")
            print(value) # 如果想看详细日志可以取消注释
    print("--- 执行结束 ---")