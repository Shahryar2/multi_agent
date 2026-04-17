# 场景模式参考文档

## 模式选择决策树

当用户提出新任务时，根据以下决策树选择合适的模式：

```
┌─ 用户是否提供了完全新的、无关的问题？
│  ├─ 是 → 重新开始一个新的 Research 模式任务
│  └─ 否 ↓
└─ 这是否是对上一次回答的后续提问或追问？
   ├─ 是 → Follow-up 模式
   └─ 否 ↓
   ├─ 用户是否要求对比类任务？
   │  ├─ 是 → Comparison 模式
   │  └─ 否 ↓
   └─ 任务复杂性和深度要求如何？
      ├─ 简单 / 单句 → Chat 模式
      └─ 复杂 / 需要深度分析 → Research 模式
```

## 工作流状态迁移

```
           ┌─────────────────────────────────────────┐
           │  用户输入 (task)                         │
           └──────────────┬──────────────────────────┘
                         ↓
           ┌─────────────────────────────────────────┐
           │  Router 节点：决定工作流模式              │
           │  读取 mode_config 参数                   │
           └──────────────┬──────────────────────────┘
                         ↓
            ┌────────┴────────┬────────┬──────────┐
            ↓                 ↓        ↓          ↓
        Research          Chat    Comparison  Follow-up
          流程             流程      流程        流程
```

## 模式配置矩阵

| 属性 | Research | Chat | Comparison | Follow-up |
|------|----------|------|-----------|-----------|
| **功能定位** | 深度分析 | 快速对话 | 快速对比 | 上文追问 |
| **搜索方式** | 高级搜索 | 无 | 基础搜索 | 无 |
| **并发请求** | 中等 | 低 | 中等 | 低 |
| **执行时间** | 5-10分钟 | <1分钟 | 2-3分钟 | <1分钟 |
| **成本水位** | 高 | 最低 | 中等 | 最低 |
| **适合场景** | 报告、学术 | 随聊、追问 | 对比选择 | 深化讨论 |

## 上下文注入策略

### Context Injection 参数说明

- **None**: 不注入任何上下文，完全独立处理
- **"last_draft"**: 注入前一轮的报告内容，用于轻量级追问
- **"full_context"**: 注入完整的会话历史，包括所有documents、citations

### 注入时机

```
Research 任务完成
    ↓ (output: draft, citations, documents)
    ├─→ 用户问题1 (Chat 模式)
    │   context_injection="last_draft" ← 使用Research的draft
    │   ↓
    ├─→ 用户问题2 (Follow-up 模式)
    │   context_injection="full_context" ← 使用完整历史
    │   ↓
    └─→ 用户问题3 (Follow-up 模式)
        context_injection="full_context"
```

## 成本和时间预估

### High 成本预算 (Research)
```
搜索:        3-5 秒
规划:        5-10 秒
检索:        5-10 秒
分析:        15-20 秒
写作:        30-60 秒
审核修改:    30-60 秒
────────────────────
总计:        5-10 分钟
成本:        ~2-5 USD (API调用)
```

### Medium 成本预算 (Comparison)
```
搜索:        2-3 秒
检索:        3-5 秒
对比分析:    10-15 秒
生成表格:    5-10 秒
────────────────────
总计:        2-3 分钟
成本:        ~0.3-0.8 USD
```

### Minimal 成本预算 (Chat / Follow-up)
```
直接响应:    1-3 秒
────────────────────
总计:        <1 分钟
成本:        ~0.02-0.05 USD
```

## 模式转换规则

### 允许的转换

```
Research
   ├→ Chat (在 Research 完成后追问)
   ├→ Follow-up (继续深化讨论)
   └→ Comparison (对比 Research 中的不同观点)

Chat
   ├→ Research (升级为深度研究)
   └→ Follow-up (继续相关提问)

Comparison
   ├→ Research (详细分析对比项)
   └→ Follow-up (继续对比的后续问题)

Follow-up
   ├→ Chat (快速问题)
   ├→ Follow-up (继续同一话题)
   └→ Research (升级为深度研究)
```

### 转换触发条件

| 转换方向 | 触发条件 | 说明 |
|--------|--------|------|
| 任何 → Research | 用户说"详细分析"、"深度研究" | 用户显式要求深化 |
| 任何 → Chat | 用户提简单问题或澄清 | 快速轻量回答 |
| Research → Comparison | 用户在 draft 中比较对象 | 自动识别对比需求 |
| 任何 → Follow-up | 用户说"继续"、"那么..." | 维持会话连贯性 |

## 配置扩展示例

### 添加自定义模式

**场景**：需要"实时新闻"模式，快速获取最新信息

```python
MODE_CONFIGS["news"] = {
    "name": "📰 实时新闻",
    "description": "快速获取最新信息和热点新闻",
    "emoji": "📰",
    "max_search_depth": "advanced",  # 优先最新结果
    "max_documents": 20,
    "research_rounds": 1,
    "output_format": "news_brief",     # 新的输出格式
    "cost_budget": "medium",
    "enable_revision": False,
    "auto_plan_approval": True,
    "context_injection": None,
}
```

## 联动其他配置

### 与 router_node 的协作

```python
def router_node(state: ResearchState):
    mode = state.get("mode", "research")
    mode_config = get_mode_config(mode)
    
    # 根据 cost_budget 选择 LLM 模型
    if mode_config["cost_budget"] == "high":
        model_tag = "smart"
    elif mode_config["cost_budget"] == "medium":
        model_tag = "basic"
    else:
        model_tag = "basic"
    
    # 根据 max_search_depth 设置搜索参数
    search_params = {
        "advanced": {"search_depth": "advanced", "max_results": 10},
        "basic": {"search_depth": "basic", "max_results": 5},
        "none": {"skip_search": True}
    }
```

### 与前端 UI 的协作

```javascript
// 前端根据 mode_config 展示不同的预期
const config = modes[selectedMode];

// 显示预期时间
const timeEstimate = {
    "high": "5-10分钟",
    "medium": "2-3分钟",
    "minimal": "<1分钟"
}[config.cost_budget];

// 显示成本估计
const costEstimate = {
    "high": "约2-5 USD",
    "medium": "约0.3-0.8 USD",
    "minimal": "约0.02 USD"
}[config.cost_budget];

showAlert(`预计耗时: ${timeEstimate}, 成本: ${costEstimate}`);
```

## 监控和分析

### 模式使用统计

建议追踪以下指标：

- 各模式的使用频率
- 各模式的平均执行时间  - 各模式的成功率
- 各模式的用户满意度评分

```python
# 示例：记录模式使用
def log_mode_usage(mode, duration, success=True):
    analytics.track({
        "event": "mode_used",
        "mode": mode,
        "duration_seconds": duration,
        "success": success,
        "timestamp": datetime.now()
    })
```

### 性能优化建议

1. **Research 模式**：优化搜索策略，减少不必要的搜索轮次
2. **Chat 模式**：充分利用缓存，加快响应
3. **Comparison 模式**：预加载对比模板，加快表格生成
4. **Follow-up 模式**：优化上下文注入，避免超出 token 限制
