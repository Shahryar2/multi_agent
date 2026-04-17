---
name: scene-mode-manager-skill
description: >-
  场景模式管理Skill，定义和管理四种操作模式（Research/Chat/Comparison/Follow-up）的完整配置。
  当需要获取模式配置、切换工作流模式、或查询可用模式时使用。
---

# Scene Mode Manager Skill

## 目标用途

统一管理项目中的四种操作模式及其配置参数。该Skill负责：

- 四种模式的完整配置定义（Research/Chat/Comparison/Follow-up）
- 模式配置的动态读取和获取
- 模式的前端展示信息（使用`get_all_modes()`）
- 模式配置的灵活扩展和维护

## 四种核心模式

### 📊 Research 模式（深度研究）

**配置参数**：
- `max_search_depth`: "advanced" - 高级搜索
- `max_documents`: 30 - 最多获取30个文档
- `research_rounds`: 1 - 单轮搜索
- `output_format`: "full_report" - 完整报告输出
- `cost_budget`: "high" - 高成本预算
- `enable_revision`: True - 启用审核修改
- `auto_plan_approval`: False - 需要手动批准计划

**使用场景**：
- 需要详细的深度分析和研究报告
- 学术研究或商业决策支持
- 对输出质量要求高

---

### 💬 Chat 模式（轻量随聊）

**配置参数**：
- `max_search_depth`: "none" - 无搜索
- `max_documents`: 0
- `research_rounds`: 0 - 不进行搜索
- `output_format`: "plain_text" - 纯文本输出
- `cost_budget`: "minimal" - 最小成本
- `enable_revision`: False - 不启用审核
- `auto_plan_approval`: True - 自动批准
- `context_injection`: "last_draft" - 注入前一轮报告

**使用场景**：
- 基于已有资料的快速对话
- 追问和知识库对话
- 轻量级的信息检索

---

### 📝 Comparison 模式（快速对比）

**配置参数**：
- `max_search_depth`: "basic" - 基础搜索
- `max_documents`: 15 - 最多15个文档
- `research_rounds`: 1 - 单轮搜索
- `output_format`: "comparison_table" - 对比表格输出
- `cost_budget`: "medium" - 中等成本
- `enable_revision`: False
- `auto_plan_approval`: True - 自动批准
- `context_injection`: None

**使用场景**：
- 快速对比两个或多个对象
- 生成对比表格和对比分析
- 快速决策支持

---

### 🔍 Follow-up 模式（追问前文）

**配置参数**：
- `max_search_depth`: "none" - 无搜索
- `max_documents`: 0
- `research_rounds`: 0
- `output_format`: "contextual_response" - 上下文响应
- `cost_budget`: "minimal"
- `enable_revision`: False
- `auto_plan_approval`: True
- `context_injection`: "full_context" - 注入完整上下文

**使用场景**：
- 基于前一轮对话继续讨论
- 无需新搜索的追问
- 保持会话上下文的连贯性

---

## 核心API

### 1. `get_mode_config(mode)` - 获取模式配置

获取指定模式的完整配置字典。

**参数**：
- `mode` (str): 模式名 ("research", "chat", "comparison", "follow_up")

**返回值**：
- Dict[str, Any]: 该模式的完整配置

**示例**：
```python
from modules.scene_mode_manager import get_mode_config

# 获取研究模式配置
config = get_mode_config("research")
print(config)
# {
#     "name": "📊 深度研究报告",
#     "max_search_depth": "advanced",
#     "max_documents": 30,
#     ...
# }
```

### 2. `get_all_modes()` - 获取所有模式摘要

获取所有模式的基本信息（用于前端展示）。

**返回值**：
- Dict[str, Dict[str, str]]: 包含name、description、emoji的简化信息

**示例**：
```python
from modules.scene_mode_manager import get_all_modes

modes_list = get_all_modes()
# {
#     "research": {
#         "name": "📊 深度研究报告",
#         "description": "完整的任务拆解和深度分析...",
#         "emoji": "📊"
#     },
#     "chat": {...},
#     ...
# }
```

---

## 工作流集成

### 在 Router 节点中的使用

```python
from modules.scene_mode_manager import get_mode_config

def router_node(state: ResearchState):
    mode = state.get("mode", "research")
    mode_config = get_mode_config(mode)  # ✅ 获取配置
    
    # 根据模式决定工作流
    if mode in ["chat", "follow_up"]:
        return {"next": "chat", "mode_config": mode_config}
    else:
        return {"next": "planner", "mode_config": mode_config}
```

### 在状态管理中的使用

```python
class ResearchState(TypedDict):
    mode: str  # 当前模式
    mode_config: Dict[str, Any]  # 该模式的配置
    # ... other fields ...
```

---

## 配置参数说明

### search_depth 参数

| 值 | 原始搜索深度 | 说明 |
|-----|------------|------|
| "advanced" | 高级 | 更复杂的查询、更多结果 |
| "basic" | 基础 | 简单快速的搜索 |
| "none" | 无 | 不执行网络搜索 |

### output_format 参数

| 值 | 说明 | 适用模式 |
|-----|------|--------|
| "full_report" | 完整报告 | Research |
| "plain_text" | 纯文本 | Chat |
| "comparison_table" | 对比表格 | Comparison |
| "contextual_response" | 上下文响应 | Follow-up |

### cost_budget 参数

| 值 | 含义 | API调用情况 |
|-----|------|-----------|
| "high" | 高预算 | 允许多轮搜索、调用较强模型 |
| "medium" | 中等预算 | 1-2轮搜索、平衡模型选择 |
| "minimal" | 最小预算 | 零搜索、调用基础模型 |

---

## 动态配置扩展

### 添加新的模式

若需添加新的操作模式，只需在 `MODE_CONFIGS` 字典中添加条目：

```python
MODE_CONFIGS = {
    "research": {...},
    "chat": {...},
    # ... existing modes ...
    
    "your_new_mode": {
        "name": "🆕 新模式",
        "description": "新模式的描述",
        "emoji": "🆕",
        "max_search_depth": "basic",
        "max_documents": 10,
        # ... other config fields ...
    }
}
```

修改后，`get_mode_config()` 和 `get_all_modes()` 会自动识别新模式。

---

## 前端集成

### 模式选择器 UI

前端可以通过 `get_all_modes()` 获取所有可用模式的展示信息：

```javascript
// 前端获取模式列表
const response = await fetch('/api/modes');
const modes = await response.json();

// 显示模式选择器
modes.forEach(mode => {
  console.log(`${mode.emoji} ${mode.name}: ${mode.description}`);
});
```

### 模式切换 API

```javascript
// 用户选择模式后，切换模式
const selectedMode = "comparison";
const config = await fetch(`/api/mode/${selectedMode}`).then(r => r.json());
console.log(`成本预算: ${config.cost_budget}`);
```

---

## 最佳实践

1. **模式选择**：根据任务复杂度和时间预算选择合适的模式
   - 一句话问题 → Chat 模式
   - 需要对比 → Comparison 模式
   - 深度分析 → Research 模式
   - 后续追问 → Follow-up 模式

2. **性能优化**：充分利用 cost_budget 参数
   - 避免不必要的高预算模式使用
   - 在 minimal 预算下完成的任务无需用 high 预算

3. **用户教育**：在前端清晰展示每种模式的差异
   - emoji 图标快速识别
   - description 简洁说明用途
   - 时间/成本预期提前告知

---

## 错误处理

### 未知模式

当请求未知模式时，`get_mode_config()` 会：
- 输出警告信息
- 返回 "research" 模式作为默认值

```python
config = get_mode_config("unknown_mode")
# ⚠️ 警告: Unknown mode: unknown_mode, using 'research' as default
# 返回研究模式配置
```

---

## 与其他Skill的关系

- **依赖**：无（独立模块）
- **被依赖**：由 `agents.py` 中的 router_node 使用
- **配合使用**：与 `llm-factory-skill` 配合，实现模式感知的模型选择

