import streamlit as st
import requests
import json
import sseclient
import time

# Configuration
API_BASE = "http://localhost:8000"
st.set_page_config(page_title="DeepInsight Research Agent", layout="wide")

# State Initialization
if "thread_id" not in st.session_state:
    st.session_state.thread_id = None
if "status" not in st.session_state:
    st.session_state.status = "idle"  # idle, running, interrupted, done
if "plan" not in st.session_state:
    st.session_state.plan = []
if "logs" not in st.session_state:
    st.session_state.logs = []

# --- Custom CSS ---
st.markdown("""
<style>
    .stTextArea textarea { font-family: monospace; }
    .status-badge { padding: 4px 8px; border-radius: 4px; font-weight: bold; }
    .status-running { background-color: #e6f3ff; color: #0066cc; }
    .status-interrupted { background-color: #fff0e6; color: #cc6600; }
</style>
""", unsafe_allow_html=True)

# --- Sidebar ---
with st.sidebar:
    st.header("🛠️ 控制面板")
    status_map = {
        "idle": "⚪ 空闲",
        "running": "🔵 运行中",
        "interrupted": "🟠 等待批准",
        "done": "🟢 已完成"
    }
    st.write(f"**状态:** {status_map.get(st.session_state.status, st.session_state.status)}")
    if st.session_state.thread_id:
        st.write("**会话 ID:**")
        st.code(st.session_state.thread_id, language="text")
        if st.button("重置会话"):
            st.session_state.thread_id = None
            st.session_state.status = "idle"
            st.session_state.plan = []
            st.session_state.logs = []
            st.rerun()

# --- Main Interface ---
st.title("🦁 DeepInsight Research Agent")

# 1. Input Section
if st.session_state.status == "idle":
    with st.container():
        st.subheader("开始新的研究任务")
        query = st.text_area("研究主题", height=100, placeholder="例如：比较 Mamba 和 Transformer 的架构异同及其使用场景...")
        if st.button("🚀 开始任务", type="primary"):
            if query:
                with st.spinner("初始化代理中..."):
                    try:
                        resp = requests.post(f"{API_BASE}/research/start", json={"query": query})
                        if resp.status_code == 200:
                            data = resp.json()
                            st.session_state.thread_id = data["thread_id"]
                            st.session_state.status = "running"
                            st.rerun()
                        else:
                            st.error(f"初始化失败: {resp.text}")
                    except Exception as e:
                        st.error(f"连接错误: {e}")

# 2. Live Logs & Stream Handler
log_placeholder = st.empty()
plan_placeholder = st.empty()

# Helper to render logs
def render_logs():
    with log_placeholder.container():
        with st.expander("📜 智能体执行日志", expanded=True):
            for log in st.session_state.logs[-10:]:  # Show last 10
                st.write(log)

# Display Logs (Initial Render)
render_logs()

# Streaming Logic (Only when running)
if st.session_state.status == "running" and st.session_state.thread_id:
    # Use a placeholder for the "Working" status
    status_msg = st.markdown(":blue[**🤖 智能体正在工作...**] (实时工作流)")
    
    try:
        url = f"{API_BASE}/research/{st.session_state.thread_id}/stream"
        # Connect to SSE
        with requests.get(url,stream=True) as response:
            client = sseclient.SSEClient(response)
        
            for msg in client.events():
                if msg.data == "[DONE]":
                    st.session_state.status = "done"
                    st.rerun()
                    break
                    
                try:
                    data = json.loads(msg.data)
                except:
                    continue
                
                # Handle Interrupt (Plan Approval)
                if data.get("type") == "interrupt":
                    st.session_state.status = "interrupted"
                    if "plan" in data:
                        st.session_state.plan = data["plan"]
                    st.rerun()
                    break
                
                # Handle Normal Updates
                node = data.get("node")
                if node:
                    # Update Logs
                    timestamp = time.strftime("%H:%M:%S")
                    node_zh = {
                        "router": "路由分配",
                        "planner": "任务规划",
                        "researcher": "信息搜索",
                        "writer": "报告撰写",
                        "reviewer": "质量审核",
                    }.get(node,node)
                    log_entry = f"`{timestamp}` **[{node_zh}]** 执行完成."
                    st.session_state.logs.append(log_entry)
                    render_logs() # Refresh logs in place
                    
                if "plan" in data:
                    st.session_state.plan = data["plan"]
                
    except Exception as e:
        st.error(f"流连接中断: {e}")
        if st.button("重试连接"):
            st.rerun()

# 3. Plan Approval Interface (Interrupted State)
if st.session_state.status == "interrupted":
    st.divider()
    st.subheader("⚠️ 需要审批：研究计划")
    st.info("规划器已生成以下步骤. 您可以在继续之前 修改任务描述或调整类型.")
    
    # Data Editor
    # We ensure defaults are set for validation
    formatted_plan = st.session_state.plan
    
    edited_plan = st.data_editor(
        formatted_plan,
        column_config={
            "description": st.column_config.TextColumn("任务描述", width="large", required=True),
            "type": st.column_config.SelectboxColumn("类型", options=["research", "analysis", "writing"], required=True),
            "status": st.column_config.SelectboxColumn("状态", options=["pending", "completed", "failed"], disabled=True)
        },
        num_rows="dynamic",
        use_container_width=True,
        key="plan_editor"
    )
    
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("✅ 批准计划", type="primary"):
            try:
                resp = requests.post(f"{API_BASE}/research/approve", json={
                    "thread_id": st.session_state.thread_id,
                    "plan": edited_plan
                })
                if resp.status_code == 200:
                    st.session_state.status = "running"
                    st.session_state.plan = edited_plan
                    st.rerun()
                else:
                    st.error(f"审批失败: {resp.text}")
            except Exception as e:
                st.error(f"请求失败: {e}")

# 4. Final Results
if st.session_state.status == "done":
    # st.balloons()
    st.success("研究任务已执行完毕!")
    st.subheader("最终执行清单")
    st.table(st.session_state.plan)
    
    # Optionally fetch final state to show report
    # ...
