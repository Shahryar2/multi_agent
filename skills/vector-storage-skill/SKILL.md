---
name: vector-storage-skill
description: >-
  向量存储Skill，基于Chroma向量数据库提供文档的语义存储和检索能力。
  支持文档添加、相似度搜索、按ID获取等操作。当需要文本相似度检索、建立知识库索引或执行语义搜索时使用。
---

# Vector Storage Skill

## 目标用途

提供高效的向量存储和语义检索功能。该Skill负责：

- 文档向量化和存储
- 相似度检索（Semantic Search）
- 文档按ID获取
- 持久化存储管理

## 核心API

### 1. `add_documents()` - 添加文档

将文档批量添加到向量存储。

**参数**：
```python
add_documents(data_list: List[Dict[str, Any]])
```

**文档格式**：
```python
{
    "text": "文档内容",
    "title": "文档标题",
    "url": "来源URL",
    "id": "唯一ID",
    "source": "来源标记（可选）"
}
```

**自动处理**：
- 智能分割（chunk_size=1000, overlap=200）
- 向量化编码
- 元数据保留

**示例**：
```python
from modules.vector_storage import vector_store

docs = [
    {
        "text": "深度学习是...",
        "title": "深度学习解释",
        "url": "https://example.com/dl",
        "id": "doc_001"
    },
    {
        "text": "机器学习是...",
        "title": "机器学习基础",
        "url": "https://example.com/ml",
        "id": "doc_002"
    }
]

vector_store.add_documents(docs)
```

---

### 2. `similarity_search()` - 相似度检索

根据查询找到最相关的文档。

**参数**：
```python
similarity_search(
    query: str,
    k: int = 5
) -> List[Dict[str, Any]]
```

**返回格式**：
```python
[
    {
        "text": "检索到的相关内容",
        "title": "文档标题",
        "url": "来源URL",
        "id": "文档ID",
        "score": 0.92  # 相关性评分（0-1）
    },
    ...
]
```

**特性**：
- 语义相似度匹配
- 返回相关性评分
- 默认返回5个最相关结果

**示例**：
```python
from modules.vector_storage import vector_store

# 查询相关文档
results = vector_store.similarity_search("什么是神经网络", k=3)

for result in results:
    print(f"{result['title']} (评分: {result['score']:.2f})")
    print(f"相关内容: {result['text'][:100]}...")
```

---

### 3. `get_by_id()` - 按ID获取文档

根据原始ID获取特定文档。

**参数**：
```python
get_by_id(original_ids: List[str]) -> List[Dict[str, Any]]
```

**返回格式**：同 `similarity_search()` (但无score字段)

**特性**：
- 精确ID匹配
- 自动去重
- 支持批量查询

**示例**：
```python
from modules.vector_storage import vector_store

# 获取特定文档
docs = vector_store.get_by_id(["doc_001", "doc_003"])

for doc in docs:
    print(f"{doc['title']}: {doc['text']}")
```

---

### 4. `clear()` - 清空存储

删除所有已存储的文档。

**参数**：无

**返回**：日志信息

**使用场景**：
- 重置知识库
- 清除过期数据

**示例**：
```python
from modules.vector_storage import vector_store

vector_store.clear()  # 删除所有文档
```

---

## 工作流程

```
文档输入
    ↓
文本分割（chunk_size=1000, overlap=200）
    ↓
向量化编码（OpenAI Embeddings）
    ↓
存储到 Chroma
    ├─ 内存存储（会话级）
    └─ 持久化存储（磁盘）
    ↓
支持查询操作
    ├─ 相似度搜索
    ├─ ID查询
    └─ 全量检索
```

---

## 最佳实践

### 1. 文档格式规范

```python
# ✓ 好的格式
doc = {
    "text": "完整的文档内容...",
    "title": "清晰的标题",
    "url": "https://example.com/doc",
    "id": "unique_doc_id",
    "source": "search_engine"
}

# ✗ 避免
doc = {
    "text": "",  # 空文本
    "title": None,  # None值
    "url": "invalid.url"  # 无效URL
}
```

### 2. 分块策略

当前配置：
- **chunk_size**: 1000字符 - 平衡上下文和细粒度
- **chunk_overlap**: 200字符 - 避免信息丢失

**调整建议**：
- 长文档处理：`chunk_size=1500, overlap=300`
- 短段落处理：`chunk_size=500, overlap=100`

### 3. 搜索参数优化

```python
from modules.vector_storage import vector_store

# 查询相关度前10个结果
results = vector_store.similarity_search(query, k=10)

# 使用更宽泛的搜索
results = vector_store.similarity_search(query, k=20)

# 精确搜索（fewer results）
results = vector_store.similarity_search(query, k=1)
```

---

## 集成指南

### 在 Workflow 中的使用

```python
from modules.vector_storage import vector_store

def research_node(state: ResearchState):
    # 存储搜索结果到向量库
    vector_store.add_documents(state["documents"])
    
    # 后续可执行语义检索
    relevant_docs = vector_store.similarity_search(
        state["task"], 
        k=5
    )
    
    state["vector_results"] = relevant_docs
    return state
```

### 知识库初始化

```python
from modules.vector_storage import vector_store

def init_knowledge_base(documents: List[Dict]):
    """初始化向量知识库"""
    print(f"正在初始化知识库，共 {len(documents)} 个文档...")
    vector_store.clear()  # 清除旧数据
    vector_store.add_documents(documents)
    print("✓ 知识库初始化完成")
```

---

## 性能特性

| 指标 | 值 |
|------|-----|
| 单条文档存储 | 100-500ms（含向量化） |
| 批量添加（100条） | 5-15秒 |
| 相似度查询 | 50-200ms |
| ID查询 | 10-50ms |
| 内存占用 | ~100MB/10000条文档 |

---

## 环境变量

```bash
# OpenAI Embedding 模型配置
OPENAI_Embedding_MODEL=text-embedding-3-small
OPENAI_API_KEY=sk-...
OPENAI_API_BASE=https://api.openai.com/v1

# 向量存储路径
# 默认: ./chroma_data
```

---

## 错误处理

### 问题1：内存不足

**症状**：处理大批量文档时OOM

**解决方案**：
```python
# 分批添加
def batch_add_documents(docs, batch_size=100):
    for i in range(0, len(docs), batch_size):
        batch = docs[i:i+batch_size]
        vector_store.add_documents(batch)
```

### 问题2：查询返回结果为空

**常见原因**：
- 向量库为空（未添加文档）
- 查询与文档语义差异过大
- 语言不匹配

**调试方法**：
```python
# 检查向量库是否有数据
all_docs = vector_store.get_by_id([])  # 获取所有
print(f"向量库中有 {len(all_docs)} 条文档")
```

---

## 与其他Skills的关系

- **依赖**：`llm-factory-skill` (OpenAI Embeddings)
- **配合使用**：`enhanced-search-tool-skill` (添加搜索结果)、`document-summarizer-skill` (存储摘要)
- **被依赖**：由workflow中需要语义搜索的节点使用

---

## 高级配置

### 自定义 Embedding 模型

```python
from langchain_openai import OpenAIEmbeddings

# 使用更强大的嵌入模型
embeddings = OpenAIEmbeddings(
    model="text-embedding-3-large",
    chunk_size=1000
)

# 在 VectorStore 中使用
vs = VectorStore(embedding_model=embeddings)
```

### 持久化存储管理

```python
# Chroma 自动持久化到磁盘
# 位置: ./chroma_data（可自定义）

from modules.vector_storage import VectorStore

# 自定义持久化路径
vs = VectorStore(persist_directory="/custom/path/chroma")
```
