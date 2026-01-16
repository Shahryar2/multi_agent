import uvicorn
import uuid
import json
import asyncio
import logging
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from deepinsight.api.user_db import register_user, login_user, save_history, get_histories

# 直接使用同步的 create_graph，因为它内部已经配置了 MemorySaver
from deepinsight.graph.workflow import create_graph

logger = logging.getLogger(__name__)

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
    user_id: Optional[str] = None # Optional user tracking

class ApproveRequest(BaseModel):
    thread_id: str
    plan: List[Dict[str, Any]]

class AuthRequest(BaseModel):
    username: str
    password: str

class SyncRequest(BaseModel):
    user_id: str
    thread_id: str
    messages: List[Dict[str, Any]]

# --- Auth Endpoints ---

@app.post("/auth/register")
async def register(req: AuthRequest):
    uid = register_user(req.username, req.password)
    if not uid:
        raise HTTPException(status_code=400, detail="Username already exists")
    return {"user_id": uid, "username": req.username}

@app.post("/auth/login")
async def login(req: AuthRequest):
    user = login_user(req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return user

@app.get("/user/history/{user_id}")
async def get_history(user_id: str):
    return get_histories(user_id)

@app.post("/user/sync")
async def sync_history(req: SyncRequest):
    save_history(req.user_id, req.thread_id, req.messages)
    return {"status": "ok"}

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
        try:
            # MemorySaver 虽然是基于内存的，但 LangGraph 的 astream 方法依然是异步的
            # 这里的调用方式是标准的异步流式调用
            async for event in graph.astream(
                {"task":""},
                config={"configurable":{"thread_id":thread_id}},
                version = "v1"
            ):
                event_name = event["event"]

                if event_name == "on_chain_end":
                    if event["name"] == "writer_node":
                        data_stream = event["data"]["output"]
                        for chunk in data_stream:
                            yield f"data:{json.dumps(chunk)}\n\n"
                            await asyncio.sleep(0.02)
                    else:
                        node_name = event["name"]
                        yield f"data:{json.dumps({'node':node_name})}\n\n"

                elif event_name == "on_chain_stream":
                    # 处理langgraph的流式块
                    chunk = event["data"]["chunk"]
                    if isinstance(chunk,dict) and "draft" in chunk:
                        yield f"data: {json.dumps(chunk)}\n\n"

            yield f"data: {json.dumps({'node':'workflow_completed'})}\n\n"

        except Exception as e:
            logger.error(f"Stram error:{e}")
            yield f"data: {json.dumps({'error':str(e)})}\n\n"

    return StreamingResponse(event_generator(),media_type="text/event-stream")

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
