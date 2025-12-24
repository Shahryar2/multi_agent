- 构建对应的合适的提示词

  (参考鹿流)

---
#### 一、接下来要实现的功能（优先级）
- 1) 内容溯源（Citations）与文档结构化（必须）-ing
  - 1) 短期为解决token限制问题先快速截断；
       关于截断的处理由两部分1.针对文档 2.针对对话
  - 2) Map-Reduce摘要（√）
  - 3) 后期补充实现向量库+检索增强
- 2) Reviewer（审稿/自检）节点：实现打回-重搜循环（高优先）√
- 3) 文档聚合(Map-Reduce 摘要√)与去重(√) + 向量检索缓存（中优先）
- 4) 并行 Researcher（并发抓取）与速率限制（中优先） √
- 5) API：Human-in-loop 的 HTTP 接口（获取状态、更新计划、继续执行）（高优先）
- 6) 持久化 Checkpointer 从内存换成 SQLite/Postgres（高优先）
- 7) Prompt 管理与版本化（将来便于迭代）（低-中优先）
- 8) 前端（Streamlit/React）用于交互展示（可视化 agent 思考流）（后期）
- 9) 监控、配额、安全（token/secret 管理、审计日志）（上线前）

---

#### 二、每一项的为什么/怎么做/验证（详细）
2) Reviewer（审稿人）节点：实现打回-重搜循环（高优先）
- 为什么：保证质量并避免 hallucination；实现闭环、展示架构能力。
- 怎么做：
  - 在 `workflow` 中在 `writer` 之后插入 `reviewer` 节点：`writer -> reviewer`，若 reviewer 返回 `"pass"` 则 `END`，若 `"fail"` 则 `planner` 或 `researcher`（带上 reviewer 指出的缺失点）。
  - `reviewer_node` 的 prompt：检查 draft 是否覆盖 planner 的子问题，并返回 `{"status":"pass"}` 或 `{"status":"fail","missing":["需求1","需求2"]}`。
- 验证：
  - 故意让 Planner 产生不完整的 plan，观察 reviewer 是否打回并触发额外 search。

3) 文档聚合（Map-Reduce 摘要）与去重 + 向量检索缓存（中优先）
- 为什么：当搜索到大量文档时必须降维以避免 token 溢出，同时保留事实。
- 怎么做：
  - 把 `documents` 切成片段（chunk），对每个 chunk 调用 LLM 做短摘要（map），然后对这些摘要做合并摘要（reduce）。
  - 同时把原始片段加入向量数据库（Chroma/FAISS）以支持后续检索与去重。
- 关键实现点：
  - 新建 `utils/summarizer.py`：`summarize_chunk(text)->summary`、`reduce_summaries(list)->merged_summary`。
  - 在 `research_node` 中：把每个 result 的 `text` 切片后并行摘要，再合并入 `state["documents"]` 为 summary-level 文档，同时保存原片段到向量库并记录 `source_id`。
- 验证：
  - 当 `plan` 很长（10+）时，`writer` 仍能在合理 token 下产生合乎逻辑的报告。
  - 检查向量库能检索到原始片段并返回对应 URL。

4) 并行 Researcher（并发抓取）与速率限制（中优先）
- 为什么：提升效率，处理多个子查询并发执行。
- 怎么做：
  - 使用 Python 的 `concurrent.futures.ThreadPoolExecutor` 或 `asyncio.gather`（取决于 tavily 客户端是否 async）。
  - 在 `research_node` 中改为并发调用：对 `plan` 创建任务池并收集结果。
  - 加入 per-tool 速率限制（Semaphore 或第三方限速器）以防 API 限流。
- 验证：
  - 对比串行与并行的耗时和稳定性；观察是否触发 API 限制并实现重试策略。

5) API：Human-in-loop 的 HTTP 接口（获取状态、更新计划、继续执行）（高优先）
- 为什么：目前只能通过测试脚本交互，生产化需要 HTTP 接口便于前端或自动化调用。
- 怎么做：
  - 在 `api/server.py` 添加接口：
    - `POST /task/start` -> 启动新会话（返回 `thread_id`）
    - `GET /task/{thread_id}/state` -> 返回当前 state（plan、next 等）
    - `POST /task/{thread_id}/update` -> 更新 state（如替换 plan）
    - `POST /task/{thread_id}/continue` -> 命令系统继续执行
  - 使用现有 `app.get_state(config)`、`app.update_state(config, ...)` 接口实现后端逻辑。
- 验证：
  - 用 `curl` 或 Postman 模拟整个流程：start -> get_state -> update -> continue -> get final draft。

6) 持久化 Checkpointer（内存 → SQLite/Postgres）（高优先）
- 为什么：内存 saver 丢失重启；需要会话恢复与审计。
- 怎么做：
  - 使用 `langgraph.checkpoint.sqlite.SqliteSaver` 或 `pgsql` 持久化。
  - 修改 `workflow.create_graph()`：`memory = SqliteSaver(db_path="db/checkpoints.sqlite")` 并传入 `compile(checkpointer=memory, ...)`。
- 验证：
  - 启动任务并中断，重启服务后 `get_state`能返回之前的会话进度。

7) Prompt 管理与版本化（低-中优先）
- 为什么：方便 A/B 测试不同 prompt 和快速迭代。
- 怎么做：
  - 把 prompts 存到 `core/prompts.py`（你已经有），再支持从 JSON/YAML 加载不同版本；在 `api` 提供切换参数。
- 验证：
  - 能在 UI 或 API 上切换 planner/writer prompt 并看到输出差异。

8) 前端（Streamlit/React）（后期）
- 为什么：展示 agent 思考流、用户确认、报告导出（PDF/MD/PPT）。
- 怎么做（MVP）：
  - 用 Streamlit 快速实现：输入框 -> Start -> 展示 plan -> 确认/修改 -> 显示 streaming 输出（SSE）。
- 验证：
  - 端到端用户交互：能在浏览器上完成一次完整流程。

9) 监控、配额、审计（上线前）
- 为什么：防止滥用、方便调优、法律合规。
- 怎么做：
  - 记录每次调用 LLM/搜索工具的日志（时间、耗时、token、cost）。
  - 限制每个 thread 的并发与每天请求量。
- 验证：
  - 查看日志、成本统计、报警测试。

---

三、短期（72小时）实操清单（最优先）
1. 把 `research_node` 返回的 `documents` 改成结构化字典（包含 `url,title,text`）。（立即）
2. 在 `writer_node` 的 prompt 中强制基于 `documents` 给出脚注引用示例。（当天）
3. 添加 `reviewer_node`，并在 `workflow` 中串入 `writer->reviewer->(END|planner)` 的条件边。（48小时内）
4. 在 `workflow` 中把 `MemorySaver()` 换成 `SqliteSaver` 做持久化（48小时内）。
5. 增加 API 接口：`/task/start`、`/task/{id}/state`、`/task/{id}/update`、`/task/{id}/continue`（72小时内）。

我可以帮你把第1项和第2项的代码补丁写好并提交到 `graph/agents.py` 与 `graph/workflow.py`（如果你同意我来改代码的话）。完成第1～3步后，你将能证明：系统能并行检索带来源、生成带引用的报告，并由 reviewer 来保证质量 —— 这是面试中最吸睛的 Demo。

---

四、如何验证与 demo 脚本（快速验收）
- 新建 `deepinsight/tests/demo_end_to_end.py`：
  - start task -> 调用 `app.stream` 直到 planner 完成 -> 使用 `app.get_state` 查看 plan -> 用 `app.update_state` 修改（模拟用户） -> continue -> 等待 writer + reviewer 输出 -> 检查 draft 是否包含 `[1]` 引用并底部列出 url。
- 准备 3 个 demo 主题：`市场分析`、`产品调研`、`短事实查询`，分别验证三种路由。

---

五、时间线建议（你个人节奏）
- Week 1 (完成)：实现 citations + reviewer + sqlite checkpointer + simple API endpoints。
- Week 2：并行 researcher + map-reduce summarizer +向量库引入。
- Week 3：前端 minimal（Streamlit） + 用户可视化（流式展示 + 中断确认）。
- Week 4：性能优化、日志、监控、整理 README 与 demo 视频（面试材料）。
