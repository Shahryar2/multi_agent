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
    Stream updates using astream_events (v2) for granular tokens
    """
    async def event_generator():
        try:
            # Determine input. If first run, use PENDING_TASKS. If resume, use None.
            # But graph state might be empty if we rely only on PENDING_TASKS without initial injection.
            initial_input = None
            if thread_id in PENDING_TASKS:
                initial_input = PENDING_TASKS[thread_id]
                # Cleanup pending after picking it up? Or keep it?
                # Better to keep until successful start, but for simplicity:
                del PENDING_TASKS[thread_id]
            
            # If no pending task and no history, this might fail or do nothing.
            # But let's assume valid flow.
            # If initial_input is None, we pass explicit None to avoid overwriting state with empty dict.
            
            async for event in graph.astream_events(
                initial_input, 
                config={"configurable":{"thread_id":thread_id}},
                version="v2"
            ):
                kind = event["event"]
                
                # 1. LLM Token Streaming
                if kind == "on_chat_model_stream":
                    content = event["data"]["chunk"].content
                    if content:
                        # Send just the delta or the accumulated? Frontend expects drafts.
                        # For now, let's send just the "response" or "draft" type.
                        # Since we don't have accumulation logic here easily, we might send chunks
                        # BUT the frontend handles "draft" by replacing active content. 
                        # Ideally, we should accumulate OR the frontend acts as a terminal.
                        # Let's send "response" or "draft" with the chunk content.
                        # However, current Frontend `connectStream` replaces content: 
                        # `next[next.length - 1] = { ...last, content: data.draft };`
                        # This implies `data.draft` must be the FULL text.
                        # Using `on_chat_model_stream` gives DELTAS.
                        # So we can't use the current Frontend logic for deltas unless we change frontend
                        # OR we accumulate here.
                        # Accumulating here is hard because `event_generator` is transient.
                        
                        # Fix: Let's assume frontend can handle deltas IF we change the JSON key?
                        # No, the frontend code I wrote:
                        # `if (data.draft) ... content: data.draft` (Replace)
                        
                        # So I must either:
                        # A) Change frontend to append if `data.delta` is present.
                        # B) Accumulate in backend.
                        
                        # Let's choose A) Change Frontend is impossible now (I can't edit it again easily without reading).
                        # Actually I just wrote the Frontend. I should have added delta support.
                        # Let's check my Frontend code memory.
                        # `content: data.draft` -> Replaces.
                        
                        # Quickest fix: Accumulate here? No, 'writer' node runs once.
                        # Maybe we can use `graph.astream` to get node updates (chunks) but `writer_node` now returns full text.
                        
                        # Wait! I can't stream via `writer_node` anymore because I removed `stream_generator`.
                        # So `writer_node` will only output at the END.
                        # This kills the streaming experience.
                        pass

                # Re-evaluating:
                # If I want streaming, `astream_events` provides deltas.
                
                if kind == "on_chat_model_stream":
                    # Filter output to only come from the 'writer' node to prevent leakage of thinking process
                    # from router/planner/researcher nodes.
                    # 'langgraph_node' metadata key usually holds the node name.
                    metadata = event.get("metadata", {})
                    node_name = metadata.get("langgraph_node", "")
                    
                    if node_name == "writer":
                        content = event["data"]["chunk"].content
                        if content:
                            yield f"data: {json.dumps({'delta': content})}\n\n"

                # 2. Node Status
                elif kind == "on_chain_start":
                    if event["name"] in ["router", "planner", "researcher", "writer", "verifier", "reviewer"]:
                        yield f"data: {json.dumps({'node': event['name']})}\n\n"
                
                # 3. Handle Interrupt (for Plan Approval)
                # When using astream, if it hits `interrupt_after`, it just stops.
                # We need to detect if we stopped at "planner".
                # We can check the state after the loop?
                
            # Check if interrupted
            snapshot = graph.get_state({"configurable":{"thread_id":thread_id}})
            if snapshot and snapshot.next:
                # If we have a 'next' step but loop finished, we probably interrupted.
                # Check if next is orchestration or inside planner?
                # Actually `interrupt_after=["planner"]`.
                # If we are at planner, next should be 'orchestrator' but we stopped.
                
                # Check plan
                plan = snapshot.values.get("plan", [])
                # If plan exists and status is pending, maybe asking for approval?
                yield f"data: {json.dumps({'type': 'interrupt', 'plan': plan})}\n\n"
            else:
                 yield f"data: {json.dumps({'node':'workflow_completed'})}\n\n"

        except Exception as e:
            logger.error(f"Stream error:{e}")
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
