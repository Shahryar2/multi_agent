import uvicorn
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from graph.workflow import create_graph
import json
import asyncio

app = FastAPI(
    title="multi-agent",
    description="支持情感陪伴与任务执行的双轨多智能体系统",
    version="1.0.0"
)

# 初始化图（单例模式，避免每次请求都重新编译）
graph = create_graph()

async def generate_stream(query: str):
    """
    生成流式响应的核心生成器。
    它会将 LangGraph 的事件流转换为前端易读的 SSE (Server-Sent Events) 格式。
    """
    inputs = {"messages": [HumanMessage(content=query)]}
    
    # 使用 astream (异步流)
    async for event in graph.astream(inputs):
        # event 是一个字典，key 是节点名 (e.g., 'router', 'chat_agent')
        for node_name, state in event.items():
            # 获取最新的一条消息
            if "messages" in state and state["messages"]:
                last_msg = state["messages"][-1]
                
                # 构造返回给前端的数据包
                data = {
                    "node": node_name,
                    "content": last_msg.content,
                    "type": last_msg.type
                }
                
                # 如果是工具调用，把调用细节也发回去（增加透明度）
                if hasattr(last_msg, 'tool_calls') and last_msg.tool_calls:
                    data["tool_calls"] = last_msg.tool_calls
                
                # 发送 SSE 格式数据
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                
                # 稍微停顿一下，防止发送太快前端渲染不过来（可选）
                await asyncio.sleep(0.05)

    yield "data: [DONE]\n\n"

@app.post("/chat/stream")
async def chat_stream(query: str):
    """
    流式对话接口。
    客户端可以通过 EventSource 连接此接口，实时获取 Agent 的思考和回复。
    """
    return StreamingResponse(
        generate_stream(query),
        media_type="text/event-stream"
    )

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "Multi-Agent Platform"}

if __name__ == "__main__":
    # 启动服务
    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=True)