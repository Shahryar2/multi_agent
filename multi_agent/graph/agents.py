from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from core.llm import get_llm
from tools.base import get_tools

# --- 1. 路由智能体 (Router) ---
def router_node(state):
    """
    分析用户意图，分类为 'chat' (闲聊) 或 'task' (任务)。
    """
    messages = state["messages"]
    llm = get_llm(temperature=0) # 路由需要精确，温度设为0
    
    # 定义分类系统的 Prompt
    system_prompt = """你是一个意图分类器。请分析用户的输入，并只输出以下两个单词之一：
    - "chat": 如果用户只是打招呼、寻求情感安慰、闲聊，不需要查询外部信息。
    - "task": 如果用户询问天气、时间、搜索信息或需要执行具体操作。
    
    只输出单词，不要包含标点符号或其他内容。"""
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("placeholder", "{messages}")
    ])
    
    chain = prompt | llm
    response = chain.invoke({"messages": messages})
    
    # 清洗结果，防止模型输出多余空格
    category = response.content.strip().lower()
    
    # 默认回退机制：如果不确定，就当作 chat
    if "task" in category:
        return {"next": "task_agent"}
    else:
        return {"next": "chat_agent"}

# --- 2. 情感陪聊智能体 (Chat Agent) ---
def chat_agent_node(state):
    """
    专注于情感陪伴和闲聊，不使用工具。
    """
    messages = state["messages"]
    llm = get_llm(temperature=0.7) # 闲聊需要一点创造力
    
    system_message = SystemMessage(content="""
    你是一个温柔、体贴的私人管家。
    你的名字叫 小屈。
    你的任务是陪伴用户，安抚他们的情绪，或者进行轻松的对话。
    请不要尝试调用任何工具，直接用温暖的语气回复用户。
    """)
    
    # 将 SystemMessage 插入到历史消息的最前面
    response = llm.invoke([system_message] + messages)
    return {"messages": [response]}

# --- 3. 任务执行智能体 (Task Agent) ---
def task_agent_node(state):
    """
    专注于执行任务，可以调用工具。
    """
    messages = state["messages"]
    llm = get_llm()
    tools = get_tools()
    
    # 绑定工具
    model_with_tools = llm.bind_tools(tools)
    response = model_with_tools.invoke(messages)
    return {"messages": [response]}