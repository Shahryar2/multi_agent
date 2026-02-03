- 构建对应的合适的提示词

  (参考鹿流)

---
#### 一、接下来要实现的功能（优先级）
- 1) 内容溯源（Citations）与文档结构化（必须）-ing
  - 1) 短期为解决token限制问题先快速截断；
       关于截断的处理由两部分
       1.针对文档 √
       2.针对对话
  - 3) 后期补充实现向量库 √ +检索增强  
- 3) 向量检索缓存（中优先）
- 4) 并行 Researcher（并发抓取）与速率限制（中优先） √
- 5) API：Human-in-loop 的 HTTP 接口（获取状态、更新计划、继续执行）（高优先）
- 6) 持久化 Checkpointer 从内存换成 SQLite/Postgres（高优先）√
- 7) Prompt 管理与版本化（将来便于迭代）（低-中优先）
- 8) 前端（Streamlit/React）用于交互展示（可视化 agent 思考流）（后期）
- 9) 监控、配额、安全（token/secret 管理、审计日志）（上线前）

---

### 3. 项目未实现的具体功能是？（功能缺口）

3.  **人机交互接口 (Human-in-the-loop API)**：
    *   *现状*：目前只能通过 `test_human_loop.py` 在控制台交互。
    *   *目标*：在 `api/server.py` 中完善 HTTP 接口，支持前端（如 Streamlit/React）暂停任务、修改计划、批准继续。

4.  **多模态支持**：
    *   *现状*：只处理文本。
    *   *目标*：支持读取 PDF 研报、解析图表数据（这是研报系统的杀手锏）。

---

### 4. 项目需要继续优化的地方是？（代码与逻辑优化）

即使不加新功能，现有代码也有很大优化空间：

1.  **Researcher 的“去噪”能力**：
    *   *问题*：`normalize_data` 只是简单的正则清洗。网页上的导航栏、广告、版权声明依然会占用大量 Token。
    *   *优化*：引入专门的 HTML 解析库（如 `trafilatura`）或使用 LLM 进行二次清洗（Extraction）。




### 一、 待实现的核心功能及代码细节

目前项目已具备“骨架”，但要达到“产品级”，以下三个功能是优先级最高的：

#### 1. 人机协同 (Human-in-the-loop) 的 API 完善
**目标**：目前中断逻辑只在本地测试有效。需要通过 API 让前端能获取当前计划、修改计划并点击“继续”。

**实现步骤**：
1.  **状态获取接口**：读取当前 `thread_id` 的 `snapshot`。
2.  **状态更新接口**：允许用户修改 `plan`。
3.  **恢复执行接口**：发送 `None` 输入触发图继续运行。

**代码细节 (server.py)**：
```python
@app.get("/task/{thread_id}/state")
async def get_task_state(thread_id: str):
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = graph.get_state(config)
    return {
        "next_node": snapshot.next,
        "values": snapshot.values, # 包含当前的 plan
        "created_at": snapshot.created_at
    }

@app.post("/task/{thread_id}/approve")
async def approve_task(thread_id: str, modified_plan: list = None):
    config = {"configurable": {"thread_id": thread_id}}
    # 如果用户修改了计划，先更新状态
    if modified_plan:
        graph.update_state(config, {"plan": modified_plan})
    
    # 触发继续执行 (resume)
    # 注意：这里需要异步处理，或者通过流式接口返回
    async def stream_resume():
        async for event in graph.astream(None, config=config):
            yield f"data: {json.dumps(event)}\n\n"
            
    return StreamingResponse(stream_resume(), media_type="text/event-stream")
```

#### 2. 多场景策略模式 (Multi-Scenario Strategy)
**目标**：让系统不仅能写“研报”，还能做“竞品对比”、“技术溯源”等。

**实现步骤**：
1.  在 `ResearchState` 中增加 `category` 字段。
2.  修改 `router_node` 识别细分场景。
3.  在 `planner` 和 `writer` 中根据 `category` 切换 Prompt。

**代码细节 (agents.py)**：
```python
# 在 planner_node 中增加分支
def planner_node(state: ResearchState):
    category = state.get("category", "general_report")
    
    # 策略映射
    prompts = {
        "comparison": "你是一个对比分析专家，请按维度（性能、价格、口碑）拆解任务...",
        "timeline": "你是一个历史学家，请按时间线（起因、发展、现状）拆解任务...",
        "general_report": PLANNER_PROMPT
    }
    
    system_prompt = prompts.get(category, PLANNER_PROMPT).format(...)
    # ... 后续逻辑 ...
```

### 二、 代码薄弱功能自查 (Self-Audit)

通过对你现有代码的分析，以下几点存在潜在风险，建议优化：

#### 1. 状态膨胀 (State Bloat)
*   **问题**：`ResearchState` 中的 `documents` 是一个 `Annotated[List, operator.add]`。
*   **风险**：如果一个任务搜索了 50 个网页，`documents` 列表会非常大。由于 LangGraph 每次经过节点都会序列化状态存入 SQLite，这会导致 **数据库读写变慢**，甚至超过消息长度限制。
*   **优化**：`documents` 应该只存储 **元数据和摘要**，完整的原文应该只存在向量库（ChromaDB）中。

#### 2. 并行研究的速率限制 (Rate Limiting)
*   **问题**：`ThreadPoolExecutor(max_workers=5)`。
*   **风险**：如果 5 个线程同时调用 `Tavily` 和 `LLM`，极易触发 API 的 **429 (Too Many Requests)** 错误。
*   **优化**：引入 `asyncio.Semaphore(3)` 或在线程池执行函数中加入随机抖动（`time.sleep(random.uniform(0.5, 2))`）。

#### 3. 向量库 ID 碰撞与去重
*   **问题**：目前的 `normalizers.py` 使用 `uuid4` 或简单的 `hash`。
*   **风险**：如果用户多次运行同一个任务，向量库会存入大量重复内容，导致检索结果全是“车轱辘话”。
*   **优化**：使用 `URL + 标题` 的 MD5 作为 ID。

#### 4. Writer 的“精准召回”逻辑缺陷
*   **问题**：在 `writer_node` 中，你使用了 `doc_map = {doc.get("id"): doc for doc in documents}`。
*   **风险**：如果 `documents` 因为 Token 限制被清理了，或者 Researcher 存入向量库后没把完整 doc 放回 state，这里就拿不到原文。
*   **优化**：增加一个从向量库根据 ID 直接取回文档的方法：`vector_store.get_by_ids(step_ids)`。

#### 5. 错误恢复能力
*   **问题**：如果某个子任务 `failed`，目前只是打印了日志。
*   **风险**：Writer 可能会因为缺少关键环节的数据而写出错误的结论。
*   **优化**：在 `orchestrator` 中增加逻辑：如果发现有 `failed` 的任务，尝试重试一次，或者提示用户手动干预。

### 下一步行动建议
1.  **修复 `doc_data` 作用域 Bug**（你上次提到的那个）。
2.  **实现 API 的 `approve` 逻辑**，这是打通前后端交互的关键。
3.  **优化 `ResearchState`**，减少在 State 中传递大文本，多利用向量库。


### 问题
3. 没有查看历史研究的按钮和布局设计
4. 主页应该设置侧边栏或合适的位置用于查看登录用户信息，包括历史对话、收藏信息等
5. 研究过程中可以不要系统的对话框的头像，直接输出，美观就好
7. 研究过程中的右侧展示栏还是有点丑
9. 研究页面输出思考、研究，展示的搜索到的页面内容和图片以及最终的研究文档几个部分要做一点点区别
    比如背景、字体颜色、框选的设计区别
12. 想要的是将后端系统进行的转化为用户可看的md形式的，类似于看得到系统思考的过程，而不是等最后把东西直接放在前端页面，是要动起来(有所更改但是只能作为半成品)

13. 关于出现不相关的搜索链接的问题(优化，现在这种情况好像变少了)：
    1. 开始搜索或计划前对问题的细化提问
    2. 创建计划或其他必要节点前，判断当前信息对于问题来说是否全面 
    3. 对研究任务的进一步细分，涵盖不同的任务和方面
    4. 设置相关性评判函数，对搜索到的文本或网页或文档进行强相关性评分过滤
    5. 提示词方面的设置，细化提示词对于搜索的要求

14. 是否考虑加入其他搜索引擎混合使用，并且能直接访问的稍微多一点？但是会不会影响到质量？
15. 刷新一次后右边侧边栏的 资料库和日志信息没有恢复刷新前状态，这是正常的吗，我觉得日志信息可以不恢复但是资料库应该恢复刷新前状态

18. 批准计划框中的计划修改点击更改按钮可以增加更改成功提示;
    批准计划框的拒绝按钮点击无反应，无法拒绝并返回
19. 重审的问题，是否应该出现区分 或是说优化重审功能
    举例说明，就是前端显示，文档写好了但是突然又出现批准计划的选择框，然后又重新书写，
    是否应该区分最终生成的文档和书写过程中的背景效果，作区分，如 问题9.
    重审的原因也可以呈现在前端
    重审时批准计划框内并没有具体的计划内容
    重审后可能会出现最后一次书写的内容还不如第一次或第二次的内容质量好


17. 关于报告修改功能![1769500563234](image/todo/1769500563234.png)