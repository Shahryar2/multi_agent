import uvicorn
import uuid
import json
import asyncio
import logging
import os
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from deepinsight.api.user_db import register_user, login_user, save_history, get_histories, toggle_favorite, delete_history, verify_token
from deepinsight.utils.modes import get_mode_config, get_all_modes, validate_mode
from deepinsight.utils.global_state import CANCELLED_TASKS

# 直接使用同步的 create_graph，因为它内部已经配置了 MemorySaver
from deepinsight.graph.workflow import create_graph

logger = logging.getLogger(__name__)

# 初始化全局图实例
graph = create_graph()

app = FastAPI(
    title="DeepInsight Agent API",
    description="Multi-Agent Research System API",
    version="1.0.0"
)

# CORS configuration
cors_origins_env = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://localhost:3000"
)
cors_origins = [o.strip() for o in cors_origins_env.split(",") if o.strip()]

allow_credentials = True
if "*" in cors_origins:
    cors_origins = ["*"]
    allow_credentials = False

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store for pending tasks
PENDING_TASKS: Dict[str, Dict[str, Any]] = {}

# Auth dependency
security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """Verify token and return user_id."""
    token = credentials.credentials
    user_id = verify_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user_id

# 跟踪取消任务
# CANCELLED_TASKS = set()

# --- Data Models ---
class ResearchRequest(BaseModel):
    query: str
    user_id: Optional[str] = None
    mode: Optional[str] = None  # 场景模式，默认由接口决定

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

class FavoriteRequest(BaseModel):
    user_id: str
    thread_id: str

# --- Auth Endpoints ---

@app.post("/auth/register")
async def register(req: AuthRequest):
    uid = register_user(req.username, req.password)
    if not uid:
        raise HTTPException(status_code=400, detail="Username already exists")
    from deepinsight.api.user_db import create_token
    token = create_token(uid)
    return {"id": uid, "username": req.username, "token": token}

@app.post("/auth/login")
async def login(req: AuthRequest):
    user = login_user(req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return user

@app.get("/user/history/{user_id}")
async def get_history(user_id: str, current_user: str = Depends(get_current_user)):
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return get_histories(user_id)

@app.post("/user/sync")
async def sync_history(req: SyncRequest, current_user: str = Depends(get_current_user)):
    if current_user != req.user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    save_history(req.user_id, req.thread_id, req.messages)
    return {"status": "ok"}

@app.post("/user/favorite")
async def toggle_fav(req: FavoriteRequest, current_user: str = Depends(get_current_user)):
    if current_user != req.user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    is_fav = toggle_favorite(req.user_id, req.thread_id)
    return {"is_favorite": is_fav}

@app.delete("/user/history/{user_id}/{thread_id}")
async def remove_history(user_id: str, thread_id: str, current_user: str = Depends(get_current_user)):
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    delete_history(user_id, thread_id)
    return {"status": "ok"}

# --- Endpoints ---

@app.post("/research/start")
async def start_research(request: ResearchRequest):
    """
    Start a new research session.
    
    Args:
        request: ResearchRequest with query and optional mode
        
    Returns:
        {"thread_id": str, "mode": str, "status": "created"}
    """
    # ✅ 验证 mode 有效性
    mode = request.mode or "research"
    if not validate_mode(mode):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode '{mode}'. Must be one of: research, chat, comparison, follow_up"
        )
    
    # ✅ 获取该模式的配置
    mode_config = get_mode_config(mode)
    
    thread_id = str(uuid.uuid4())
    
    initial_state = {
        "task": request.query,
        "mode": mode,
        "mode_config": mode_config,
        "plan": [],
        "current_step_index": 0,
        "documents": [],
        "bg_investigation": [],
        "max_revisions": 2,
        "revision_number": 0,
        "is_long_document": False,
        "writing_mode": "",
        "draft_sections": []
    }

    PENDING_TASKS[thread_id] = initial_state
    print(f"--- [API] Task Created: {thread_id} ---")
    print(f"    Mode: {mode}")
    print(f"    Config: {mode_config}")

    return {
        "thread_id": thread_id,
        "mode": mode,
        "status": "created"
    }

@app.get("/research/modes")
async def get_modes():
    """
    获取所有可用的研究模式
    
    Returns:
        {
            "research": {"name": "...", "description": "...", "emoji": "..."},
            "chat": {...},
            ...
        }
    """
    return get_all_modes()

@app.post("/research/{thread_id}/stop")
async def stop_research(thread_id: str):
    """
    Stop a running research session.
    """
    CANCELLED_TASKS.add(thread_id)
    print(f"--- [API] Task Cancel Requested: {thread_id} ---")
    return {"thread_id": thread_id, "status": "cancellation_requested"}

@app.post("/research/{thread_id}/continue")
async def continue_research(thread_id: str, request: ResearchRequest):
    """
    Continue an existing research session with a new query.
    Resets per-run state but preserves conversation context:
    - last_draft: previous report (injected as context in chat_node)
    - last_citations: previous citations
    - messages: full chat history (accumulated via operator.add)
    If the graph state is gone (e.g. server restarted / MemorySaver cleared),
    falls back to starting fresh instead of raising 404.
    """
    last_draft = ""
    last_citations = []
    existing_mode = None

    try:
        snapshot = graph.get_state({"configurable": {"thread_id": thread_id}})
        if snapshot and snapshot.values:
            current = snapshot.values
            last_draft = current.get("draft") or current.get("last_draft") or ""
            last_citations = current.get("citations") or current.get("last_citations") or []
            existing_mode = current.get("mode")
    except Exception as e:
        print(f"--- [API] Could not load state for {thread_id}: {e}. Starting fresh. ---")

    mode = request.mode or existing_mode or "research"
    if not validate_mode(mode):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode '{mode}'. Must be one of: research, chat, comparison, follow_up"
        )

    mode_config = get_mode_config(mode)

    continuation_state = {
        "task": request.query,
        "mode": mode,
        "mode_config": mode_config,
        "plan": [],
        "current_step_index": 0,
        "draft": "",
        "draft_sections": [],
        "revision_number": 0,
        "max_revisions": 2,
        "writing_mode": "",
        "is_long_document": False,
        "last_draft": last_draft,
        "last_citations": last_citations,
    }

    PENDING_TASKS[thread_id] = continuation_state
    print(f"--- [API] Task Continue: {thread_id} | query: {request.query[:40]}... ---")
    return {"thread_id": thread_id, "mode": mode, "status": "continuing"}


@app.get("/research/{thread_id}/stream")
async def stream_research(thread_id: str):
    """
    Stream updates using astream_events (v2) for granular tokens
    """
    async def event_generator():
        interrupt_sent = False
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
                if thread_id in CANCELLED_TASKS:
                    print(f"--- Task {thread_id} cancelled ---")
                    CANCELLED_TASKS.discard(thread_id)
                    yield f"data: {json.dumps({'node':'cancelled'})}\n\n"
                    return

                kind = event["event"]
                # 1. LLM Token Streaming
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
                    if event["name"] in ["router", "planner", "researcher", "writer", "verifier", "reviewer", "chat"]:
                        yield f"data: {json.dumps({'node': event['name']})}\n\n"
                
                # 3. Capture State Updates (Thought Process & Search Data)
                elif kind == "on_chain_end":
                     node_name = event.get("name")
                     output = event.get("data", {}).get("output")

                     if node_name == "router" and isinstance(output, dict):
                         classification = {
                             "category": output.get("category"),
                             "field": output.get("field"),
                             "depth": output.get("depth"),
                             "style": output.get("style"), 
                         }
                         yield f"data: {json.dumps({'classification': classification})}\n\n"
                     
                     # Extract thought_process from planner results
                     if node_name == "planner" and isinstance(output, dict):
                         if "thought_process" in output:
                             yield f"data: {json.dumps({'thought': output['thought_process']})}\n\n"

                         if not interrupt_sent and "plan" in output and len(output["plan"]) > 0:
                             plan = output["plan"]
                            #  interrupt for plan approval
                             try:
                                event_data = {'type': 'interrupt', 'plan': plan}
                                event_json = json.dumps(event_data, ensure_ascii=False)
                                yield f"data: {event_json}\n\n"
                                # 设置标志位
                                interrupt_sent = True
                                print(f"--- [Stream] ✅ Interrupt sent from on_chain_end ---")
                             except Exception as e:
                                print(f"--- [Stream] ❌ Failed to send interrupt: {e} ---")

                     # Extract search_data from researcher results
                     if node_name == "researcher" and isinstance(output, dict):
                         if "search_data" in output:
                             # Ensure it is serializable
                             try:
                                yield f"data: {json.dumps({'search_results': output['search_data']})}\n\n"
                             except Exception as e:
                                 logger.error(f"Failed to serialize search data: {e}")

                     if node_name == "chat" and isinstance(output, dict):
                         if "response" in output:
                             try:
                                yield f"data: {json.dumps({'response': output['response']})}\n\n"
                                logger.info(f"--- [Chat] Response sent to client ---")
                             except Exception as e:
                                 logger.error(f"Failed to serialize chat response: {e}")
                     
                     if node_name == "writer" and isinstance(output, dict):
                         if "draft_sections" in output and output["draft_sections"]:
                             try:
                                sections_summary = [
                                    {"id": sec["section_id"],"title": sec["title"],"status": sec["status"]}
                                    for sec in output["draft_sections"]
                                ]
                                yield f"data: {json.dumps({'draft_sections': sections_summary})}\n\n"
                             except Exception as e:
                                 logger.error(f"Failed to serialize draft sections: {e}")
                         if "writing_mode" in output:
                             yield f"data: {json.dumps({'writing_mode': output['writing_mode']})}\n\n"
                         if "token_stats" in output:
                             yield f"data: {json.dumps({'token_stats': output['token_stats']})}\n\n"

                         if "citations" in output:
                             try:
                                yield f"data: {json.dumps({'citations': output['citations']})}\n\n"
                             except Exception as e:
                                 logger.error(f"Failed to serialize citations data: {e}")

                         if "draft" in output:
                             try:
                                yield f"data: {json.dumps({'draft': output['draft']})}\n\n"
                             except Exception as e:
                                 logger.error(f"Failed to serialize draft data: {e}")
                
                # 4. Handle Interrupt (for Plan Approval)
                # When using astream, if it hits `interrupt_after`, it just stops.
                # We need to detect if we stopped at "planner".
                # We can check the state after the loop?
                
            # Check if interrupted
            snapshot = graph.get_state({"configurable":{"thread_id":thread_id}})
            # 调试
            print(f"--- [Stream] Workflow ended. Check interrupt status ---")
            print(f"--- [Stream] Nextnode: {snapshot.next if snapshot else 'None'} ---")
            print(f"--- [Stream] Snapshot exists: {snapshot is not None} ---")

            if snapshot and snapshot.next and not interrupt_sent:
                # If we have a 'next' step but loop finished, we probably interrupted.
                # Check plan
                value = snapshot.values or {}
                plan = value.get("plan", [])
                
                # 调试
                print(f"--- [Stream] Value keys: {list(value.keys())} ---")
                print(f"--- [Stream] Plan type: {type(plan)} ---")
                print(f"--- [Stream] Plan length: {len(plan)} ---")
                if len(plan) > 0:
                    print(f"--- [Stream] First plan step: {plan[0]} ---")
                    print(f"--- [Stream] Plan serializable test... ---")
                    try:
                        test_json = json.dumps(plan, ensure_ascii=False)
                        print(f"--- [Stream] Serialization OK, length: {len(test_json)} ---")
                    except Exception as e:
                        print(f"--- [Stream] Serialization FAILED: {e} ---")

                if plan and len(plan) > 0:
                    try:
                        event_data = {'type': 'interrupt', 'plan': plan}
                        event_json = json.dumps(event_data, ensure_ascii=False)
                        print(f"--- [Stream] Sending interrupt event ({len(event_json)} bytes) ---")
                        yield f"data: {event_json}\n\n"
                        print(f"--- [Stream] ✅ Interrupt event sent successfully ---")
                    except Exception as e:
                        print(f"--- [Stream] ❌ ERROR sending interrupt: {e} ---")
                        import traceback
                        traceback.print_exc()
                        yield f"data: {json.dumps({'error': f'Interrupt failed: {str(e)}'})}\n\n"

                # elif interrupt_sent:
                #     print(f"--- [Stream] ✅ Interrupt was already sent earlier ---")
                else:
                    print(f"--- [Stream] ❌ Plan is empty or None ---")
                    yield f"data: {json.dumps({'error': 'Plan is empty', 'values_keys': list(value.keys())})}\n\n"
            else:
                print(f"--- [Stream] Workflow completed normally (no interrupt) ---")
                yield f"data: {json.dumps({'node':'workflow_completed'})}\n\n"

            #         # If plan exists and status is pending, maybe asking for approval?
            #         yield f"data: {json.dumps({'type': 'interrupt', 'plan': plan})}\n\n"
            #     else:
            #         yield f"data: {json.dumps({'error': 'Planner generated error'})}\n\n"
            # else:
            #      yield f"data: {json.dumps({'node':'workflow_completed'})}\n\n"

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
