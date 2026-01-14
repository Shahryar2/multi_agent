import uvicorn
import uuid
import json
import asyncio
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import os

from langchain_core.messages import HumanMessage
from deepinsight.graph.workflow import create_graph

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

# Initialize Graph
# Ensure we are in the right directory or path is setup
graph = create_graph()

# --- Data Models ---

class ResearchRequest(BaseModel):
    query: str

class PlanItem(BaseModel):
    id: int
    type: str
    description: str
    status: str = "pending"
    result: Optional[str] = None

class ApproveRequest(BaseModel):
    thread_id: str
    plan: List[Dict[str, Any]]

# --- Endpoints ---

@app.post("/research/start")
async def start_research(request: ResearchRequest):
    """
    Start a new research session.
    Initialize state with task query but don't run yet.
    """
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    
    # Initialize state with the user query
    # We use update_state to populate the graph with initial data
    # effectively "priming" it for the first run.
    initial_state = {
        "task": request.query,
        "plan": [],
        "current_step_index": 0,
        "documents": [],
        "bg_investigation": []
    }
    
    graph.update_state(config, initial_state)
    
    return {"thread_id": thread_id, "status": "created"}

@app.get("/research/{thread_id}/stream")
async def stream_research(thread_id: str):
    """
    Stream updates from the agent workflow.
    Automatically resumes from current checkpoint.
    """
    
    async def event_generator():
        config = {"configurable": {"thread_id": thread_id}}
        
        try:
            # astream(None) resumes from the current state/checkpoint
            # stream_mode="updates" gives us the node outputs
            async for event in graph.astream(None, config, stream_mode="updates"):
                # Handle different event structures
                for node_name, node_state in event.items():
                    # Extract Plan
                    current_plan = node_state.get("plan", [])
                    
                    # Extract Messages (if any)
                    messages = []
                    # Depending on your State definition, access messages
                    # ResearchState doesn't usually have 'messages' unless added.
                    # But we can send status updates.
                    
                    # Prepare payload
                    payload = {
                        "node": node_name,
                        "plan": current_plan,
                        # Send the whole state values needed for UI?
                        # Or just deltas.
                        "step_index": node_state.get("current_step_index", 0)
                    }
                    
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            
            # Check status after stream ends (could be interrupt or done)
            snapshot = graph.get_state(config)
            if snapshot.next:
                # Interrupted
                # Send the *current* state so UI can show it for editing
                payload = {
                    "type": "interrupt",
                    "next": snapshot.next,
                    "plan": snapshot.values.get("plan", [])
                }
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            else:
                # Finished
                res = snapshot.values.get("bg_investigation", []) 
                # Or final result?
                yield "data: [DONE]\n\n"
                
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
            # Prevent infinite loops in client if error persists
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/research/{thread_id}/state")
async def get_state(thread_id: str):
    """
    Get current state (useful for fetching plan before approval)
    """
    config = {"configurable": {"thread_id": thread_id}}
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
    """
    Update the plan and resume execution.
    """
    config = {"configurable": {"thread_id": request.thread_id}}
    
    # Update the plan in the state
    graph.update_state(config, {"plan": request.plan})
    
    # The client will reconnect to /stream to resume
    return {"status": "updated", "message": "Plan updated. Reconnect to stream to continue."}

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "DeepInsight API"}

if __name__ == "__main__":
    uvicorn.run("deepinsight.api.server:app", host="0.0.0.0", port=8000, reload=True)
