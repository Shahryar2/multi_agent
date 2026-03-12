# DeepInsight: 基于多智能体协作的深度研报生成系统 (Autonomous Deep Research Agent System)

![Python Version](https://img.shields.io/badge/Python-3.11+-blue.svg)
![Framework](https://img.shields.io/badge/Framework-LangGraph-orange.svg)
![Frontend](https://img.shields.io/badge/Frontend-React%20%7C%20Tailwind-61DAFB.svg)

## 📖 项目简介
**DeepInsight** 是一个聚焦于解决复杂上下文调研痛点、对标 ***GPT-Researcher*** 与字节跳动***鹿流***深度研究模式的多智能体系统。

普通的 RAG 系统通常只能回答短文本查询（如“某公司去年的营收是多少”），而本项目旨在解决宏观、深度的长文类需求，例如：“*请帮我写一份关于2025年东南亚电动车市场的深度分析报告，包含竞争对手分析、政策风险和未来趋势预测*”。

通过引入多智能体协同机制，系统具备：**复杂任务拆解 -> 自主聚合搜索 -> 网页/文档阅读 -> 去噪过滤 -> 交叉验证 -> 逻辑编排文章 -> 自我反思修改** 的全流程能力。所有输出强制带有事实溯源与引用标准（Citations），最大程度限制 LLM 幻觉。

---

## ✨ 核心特性与亮点 (Highlights)

- **🤖 复合多智能体协同 (Multi-Agent Collab)**
  基于 `LangGraph` 构建了基于状态机（State Graph）的 Agent 工作流，彻底摆脱单体 LLM 的逻辑局限与上下文遗忘困境。主要编排包含四个核心角色：
  1. **规划者 (Planner Agent)：** 思维链任务拆解，基于模糊指令输出细粒度搜索子策略。
  2. **研究员 (Researcher Agent)：** 执行递归搜索、网页读取、噪音清洗并提取关键 Fact。
  3. **审稿人 (Reviewer/Critic Agent)：** 对比 Researcher 返回的证据与用户原始需求，执行自我反思（Self-Reflection），决定是否打回重搜。
  4. **撰稿人 (Writer Agent)：** 长文本生成，事实拼接与自动编排，融合严格的 Markdown 格式及学术级引用脚注。

- **🧑‍💻 人机协同干预 (Human-in-the-Loop)**
  不再是“盲盒式生成”。智能体在关键节点（如 Planner 完成初步调研大纲时），系统允许暂停并向前端发送询问，等待用户进行“审查、干预补充或驳回”操作，确保研究大方向可控。

- **📝 严格的幻觉控制与引用机制**
  系统底层采用了 Map-Reduce 信息压缩策略和基于本地 SQLite/Chroma 暂存交叉验证方案，确保输出内容的每一条关键论点、每一段内容均具备可查来源的出处，避免“凭空捏造”。

- **🔌 底层设施**
  使用 `Tavily` 和 `DuckDuckGo API` 作为网络感知触角，内置 `ChromaDB` 作为动态知识切片及防重向量库，基于 `FastAPI` 构建异步非阻塞服务。

---

## 🛠️ 技术栈 (Tech Stack)

### **后端 (Backend)**
- **开发语言**: Python >= 3.11
- **Agent 框架**: [LangGraph](https://langchain-ai.github.io/langgraph/) + LangChain
- **Web 框架**: FastAPI + Uvicorn
- **搜索引擎**: Tavily-Python / DuckDuckGo-Search
- **持久化与检索**: ChromaDB, LangGraph-checkpoint-sqlite
- **数据校验**: Pydantic

### **前端 (Frontend)**
- **框架**: React 18 + Vite
- **UI & 样式**: Tailwind CSS
- **图标部件**: Lucide React
- **动态交互**: 实现 Agent 思考状态流式回显、审批流 (Approval Modal)、用户面板与历史记录查看

---

## 🚀 快速开始 (Getting Started)

### 1. 基础配置
克隆代码库后，在项目根目录创建并配置 `.env` 文件。
需要自行申请相关大模型（OpenAI API 等）和搜索工具（Tavily）的密钥：
```bash
OPENAI_API_KEY=your_openai_api_key
TAVILY_API_KEY=your_tavily_api_key
```

### 2. 启动后端 (Python 环境)

推荐使用虚拟环境管理依赖：
```bash
# 创建并激活虚拟环境
python -m venv .venv
source .venv/Scripts/activate  # Windows: .venv\Scripts\Activate.ps1

# 安装依赖
pip install -e .
# 或者直接 pip install -r pyproject.toml 中的对应库

# 启动 FastAPI 服务 (默认跑在 localhost:8000)
uvicorn deepinsight.api.server:app --reload
```

### 3. 启动前端 (Node.js 环境)

进入到 frontend 文件夹，安装并启动前端 UI 服务：
```bash
cd frontend
npm install
npm run dev
```
启动成功后，浏览器访问 http://localhost:5173 即可与系统进行对话及深度报告生成。

## 🛣️ 未来规划 (Roadmap)
- 支持更多文档源解析 (PDF / PPT / 内部离线知识库直接融合检索)
- 场景化定制面板 (添加一键“防迷惑”、“场景适配参数”与“用户偏好定制”配置区)
- 完善的文件上传感知能力 (支持用户挂载本地报告让智能体作为背景参照)
- 多模态图文编排 (允许 Writer Agent 检索并结合图表进行可视化呈现)