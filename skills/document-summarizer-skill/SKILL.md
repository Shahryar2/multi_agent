---
name: document-summarizer-skill
description: >-
  文档摘要Skill，提供单个文档摘要和批量文档摘要解决方案。
  支持并行处理，采用LLM进行智能摘要。当需要快速浓缩文档内容、处理大量文本或保留关键信息时使用。
---

# Document Summarizer Skill

## 目标用途

提供高效的文档摘要功能，从冗长的文本中提取核心信息。该Skill负责：

- 单个文档的智能摘要
- 批量文档的并行处理
- 自动内容质量验证和过滤
- 摘要元数据记录

## 核心API

### 1. `summarize_single_doc()` - 单个文档摘要

对单个文档进行智能摘要。

**参数**：
```python
summarize_single_doc(
    doc: Dict[str, Any],
    model_tag: str = "basic"  # 使用的LLM模型
) -> Dict[str, Any]
```

**文档格式**：
```python
{
    "text": "长篇文档内容...",
    "query": "查询上下文（可选）",
    "title": "文档标题",
    "url": "文档来源URL"
}
```

**返回格式**：
```python
{
    "text": "摘要后的内容...",
    "query": "查询上下文",
    "title": "文档标题",
    "url": "文档来源URL",
    "is_summary": True  # 标记为已摘要
}
```

**特性**：
- 短文本自动保留（<200字）
- 使用LLM进行语义浓缩
- 保留原始字段（title, url, query等）
- 自动标记摘要状态

**示例**：
```python
from modules.document_summarizer import summarize_single_doc

doc = {
    "text": "这是一篇很长的文章...",
    "title": "AI的应用",
    "url": "https://example.com/article",
    "query": "AI应用"
}

summary = summarize_single_doc(doc, model_tag="smart")
print(summary["text"])  # 摘要后的内容
print(summary["is_summary"])  # True
```

---

### 2. `map_summarize_documents()` - 批量摘要

并行处理多个文档进行摘要。

**参数**：
```python
map_summarize_documents(
    documents: List[Dict[str, Any]],
    max_workers: int = 2,
    model_tag: str = "basic"
) -> List[Dict[str, Any]]
```

**性能参数**：
- `max_workers`: 并发线程数，默认2个（避免API限流）
- 实际并发受限于API速率限制

**返回值**：
与输入格式相同，但所有文档都包含 `is_summary` 字段

**示例**：
```python
from modules.document_summarizer import map_summarize_documents

documents = [
    {"text": "长文档1...", "title": "标题1"},
    {"text": "长文档2...", "title": "标题2"},
    {"text": "长文档3...", "title": "标题3"},
]

summaries = map_summarize_documents(
    documents,
    max_workers=3,
    model_tag="basic"
)

print(f"处理了 {len(summaries)} 个文档")
```

---

## 工作流程

```
输入文档列表
    ↓
检查文本长度
    ├─ < 200字 → 直接保留（短文本）
    └─ ≥ 200字 ↓
        ↓
    调用 LLM 进行摘要
        ↓
    添加元数据
        ├─ is_summary: True
        ├─ 保留原始字段
        └─ 异常时保留原文
        ↓
    返回摘要结果
```

---

## 最佳实践

### 1. 模型选择

| 场景 | 推荐模型 | 说明 |
|------|--------|------|
| 批量快速摘要 | basic | 成本低，速度快 |
| 高质量摘要 | smart | 理解能力强 |
| 复杂逻辑 | thinking | 准确性最高 |

### 2. 并发控制

```python
# ✓ 推荐：保守的并发数
summaries = map_summarize_documents(docs, max_workers=2)

# ⚠️ 小心：过大的并发可能触发API限流
summaries = map_summarize_documents(docs, max_workers=10)
```

### 3. 批量处理建议

```python
from modules.document_summarizer import map_summarize_documents

# 大批量分批处理
def batch_summarize(all_docs, batch_size=50):
    results = []
    for i in range(0, len(all_docs), batch_size):
        batch = all_docs[i:i+batch_size]
        summaries = map_summarize_documents(batch, max_workers=2)
        results.extend(summaries)
    return results
```

---

## 错误处理

### 摘要失败

当LLM调用失败时，原文会被保留：

```python
{
    "text": "原始未摘要的文本...",
    "title": "标题",
    "is_summary": False  # 标记为失败
}
```

**常见原因**：
- API 超时
- LLM 模型不可用
- 无效的环境配置

### 日志记录

```
[摘要中]正在处理文档:文章标题...
[摘要失败]: Connection timeout
```

---

## 集成指南

### 在 Agents 中的使用

```python
from modules.document_summarizer import map_summarize_documents

def research_node(state: ResearchState):
    # 获取搜索到的原始文档
    documents = state.get("documents", [])
    
    # 如果文档过多，进行摘要
    if len(documents) > 10:
        documents = map_summarize_documents(
            documents,
            max_workers=2,
            model_tag="basic"
        )
    
    state["documents"] = documents
    return state
```

---

## 性能特性

| 指标 | 值 |
|------|-----|
| 单文档处理 | 0.5-2秒（含API调用） |
| 批量处理 | (文档数/max_workers) × 单文档时间 |
| 短文本跳过 | <20ms（直接返回） |
| 内存占用 | O(文档数) |

---

## 输出格式说明

### 摘要后文档

```python
{
    "text": "摘要后的内容，大约100-200字",
    "title": "原始标题",
    "url": "原始URL",
    "query": "原始查询",
    "is_summary": True  # ✓ 已摘要
}
```

### 原始文档（短或失败）

```python
{
    "text": "完整或原始文本",
    "title": "原始标题",
    "url": "原始URL",
    "is_summary": False  # ✗ 未摘要
}
```

---

## 与其他Skill的关系

- **依赖**：`llm-factory-skill` (需要LLM实例)
- **被依赖**：由workflow节点在处理大量文档时使用
- **配合使用**：在 vector-storage-skill 之前进行摘要，提高存储效率
