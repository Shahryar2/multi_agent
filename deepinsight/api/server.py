import uvicorn
import uuid
import json
import asyncio
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# 直接使用同步的 create_graph，因为它内部已经配置了 MemorySaver
from deepinsight.graph.workflow import create_graph

# 初始化全局图实例
# 因为 MemorySaver 是线程安全的内存字典，全局单例即可
graph = create_graph()

app = FastAPI(
    title="DeepInsight Agent API",
    description="Multi-Agent Research System API",
    version="1.0.0"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store for pending tasks
PENDING_TASKS: Dict[str, Dict[str, Any]] = {}

# --- Data Models ---
class ResearchRequest(BaseModel):
    query: str

class ApproveRequest(BaseModel):
    thread_id: str
    plan: List[Dict[str, Any]]

# --- Endpoints ---

@app.post("/research/start")
async def start_research(request: ResearchRequest):
    """
    Start a new research session.
    """
    thread_id = str(uuid.uuid4())
    
    initial_state = {
        "task": request.query,
        "plan": [],
        "current_step_index": 0,
        "documents": [],
        "bg_investigation": []
    }
    
    PENDING_TASKS[thread_id] = initial_state
    print(f"--- [API] Task Created: {thread_id} ---")
    
    return {"thread_id": thread_id, "status": "created"}

@app.get("/research/{thread_id}/stream")
async def stream_research(thread_id: str):
    """
    Stream updates using MemorySaver (Robust & Simple)
    """
    async def event_generator():
        config = {"configurable": {"thread_id": thread_id}}
        
        inputs = None
        if thread_id in PENDING_TASKS:
            print(f"--- [API] Starting New Task for {thread_id} ---")
            inputs = PENDING_TASKS.pop(thread_id)
        else:
            print(f"--- [API] Resuming Task for {thread_id} ---")
            
        try:
            # MemorySaver 虽然是基于内存的，但 LangGraph 的 astream 方法依然是异步的
            # 这里的调用方式是标准的异步流式调用
            async for event in graph.astream(inputs, config, stream_mode="updates"):
                # 获取当前全局状态 (使用同步 get_state 即可，因为 MemorySaver 是内存操作)
                current_snapshot = graph.get_state(config)
                global_plan = current_snapshot.values.get("plan", [])
                
                for node_name, node_state in event.items():
                    print(f"--- [API] Node Executed: {node_name} ---")
                    
                    # Extract draft/citations if available
                    draft = current_snapshot.values.get("draft")
                    citations = current_snapshot.values.get("citations")
                    # Try to get chat response if it exists (chat node returns string usually, but state has no 'response' key, let's check agents.py)
                    # agents.py chat_node returns string direct to output, but StateGraph outputs are updates.
                    # If chat_node returns {"messages": ...} or similar.
                    # In agents.py currently: chat_node returns string? No, it returns last message?
                    # Let's check agents.py chat_node return value.
                    # It returns StrOutputParser output. 
                    # StateGraph expects a dict to update state. 
                    # If chat_node returns string, it might crash if state key not found?
                    # The state has 'task'. 
                    # We need to ensure chat_node returns a compatible dict like {"task": ...} or we handle it.
                    # Wait, agents.py chat_node invokes chain which returns string.
                    # We should probably fix chat_node to return a dict if it hasn't been fixed.
                    
                    # payload construction
                    payload = {
                        "node": node_name,
                        "plan": global_plan,
                        "step_index": current_snapshot.values.get("current_step_index", 0),
                        "draft": draft,
                        "citations": citations
                    }
                    
                    # Check for chat node special case (result might be in the event itself if it's not a state user key)
                    if node_name == "chat":
                        # If the node output is the message text
                        if isinstance(node_state, str):
                             payload["response"] = node_state
                        elif isinstance(node_state, dict) and "response" in node_state:
                             payload["response"] = node_state["response"]
                    
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    # 防止前端过载
                    await asyncio.sleep(0.05)
            
            # 检查最终状态
            snapshot = graph.get_state(config)
            print(f"--- [API] Stream Ended. Next: {snapshot.next} ---")
            
            if snapshot.next:
                print(f"--- [API] Interrupted at {snapshot.next} ---")
                payload = {
                    "type": "interrupt",
                    "next": snapshot.next,
                    "plan": snapshot.values.get("plan", [])
                }
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            else:
                print("--- [API] Workflow Completed ---")
                final_result = snapshot.values.get("draft", "") or \
                               snapshot.values.get("bg_investigation", "")
                
                if final_result:
                     yield f"data: {json.dumps({'type': 'result', 'content': str(final_result)}, ensure_ascii=False)}\n\n"
                
                yield "data: [DONE]\n\n"
                
        except Exception as e:
            print(f"--- [API Error] {e} ---")
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/research/{thread_id}/state")
async def get_state(thread_id: str):
    config = {"configurable": {"thread_id": thread_id}}
    # 同步调用 get_state
    snapshot = graph.get_state(config)
    
    if not snapshot:
        raise HTTPException(status_code=404, detail="Session not found")
        
    return {
        "values": snapshot.values,
        "next": snapshot.next,
        "metadata": snapshot.metadata
    }

@app.post("/research/approve")
async def approve_plan(request: ApproveRequest):
    config = {"configurable": {"thread_id": request.thread_id}}
    
    print(f"--- [API] Approving Plan for {request.thread_id} ---")
    # 同步调用 update_state
    graph.update_state(config, {"plan": request.plan})
    
    return {"status": "updated", "message": "Plan updated. Reconnect to stream to continue."}

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "DeepInsight API"}

if __name__ == "__main__":
    uvicorn.run("deepinsight.api.server:app", host="0.0.0.0", port=8000, reload=True)
