# LLM 模型配置参考

## 环境变量配置

### 模型标签：`smart` (高性能模型)

**用途**: 通用场景，平衡性能和成本

**所需环保量变量**:
```bash
Gemini_api_key=<YOUR_GEMINI_API_KEY>
fangzhou_api_base=<API_BASE_URL>
Gemini_model=<MODEL_NAME>  # 默认: gpt-3.5-turbo
```

**推荐使用场景**:
- 常规信息检索和总结
- 文本生成（报告、总结、翻译）
- API开发中的默认模型选择

---

### 模型标签：`thinking` (推理模型)

**用途**: 需要深度推理的复杂问题

**所需环境变量**:
```bash
Gemini_thinking_api_key=<YOUR_THINKING_API_KEY>
fangzhou_api_base=<API_BASE_URL>
Gemini_thinking_model=<MODEL_NAME>  # 默认: gpt-3.5-turbo
```

**推荐使用场景**:
- 逻辑分析和推理问题
- 代码审查和优化建议
- 复杂决策支持
- 需要逐步推导的任务

**性能特征**:
- 响应时间较长（包含推理过程）
- 输出质量更高
- 成本相对较高

---

### 模型标签：`basic` (基础模型)

**用途**: 备用方案，或成本敏感型场景

**所需环境变量**：
```bash
OPENAI_API_KEY=<YOUR_OPENAI_KEY>
OPENAI_API_BASE=<OPENAI_BASE_URL>
OPENAI_MODEL=<MODEL_NAME>  # 默认: gpt-3.5-turbo
```

**推荐使用场景**:
- 低优先级任务
- 成本受限的场景
- 实时性要求强但质量容差大的任务
- 快速原型设计

---

## Temperature 参数说明

`temperature` 参数控制模型的创意程度（采样温度）

| 值范围 | 特性 | 推荐用途 |
|--------|------|---------|
| 0.0-0.3 | 确定性强，输出稳定 | 数据提取、事实查询、代码生成 |
| 0.3-0.7 | 平衡（默认0.7）| 摘要、翻译、一般问答 |
| 0.7-1.0 | 创意强，输出多样 | 创意写作、头脑风暴 |

**性能建议**：
- **稳定任务**（分析、提取）: temperature=0.3
- **通用任务**（理解、总结）: temperature=0.7（默认）
- **创意任务**（写作、创意）: temperature=0.9

---

## 完整的 .env 示例

```bash
# Smart 模型配置
Gemini_api_key=sk-xxx...
fangzhou_api_base=https://api.example.com/v1
Gemini_model=gpt-4

# Thinking 模型配置
Gemini_thinking_api_key=sk-thinking-xxx...
Gemini_thinking_model=gpt-4-turbo

# Basic 模型配置
OPENAI_API_KEY=sk-openai-xxx...
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_MODEL=gpt-3.5-turbo

# Embedding 配置（向量存储使用）
OPENAI_Embedding_MODEL=text-embedding-3-small

# Tavily 搜索配置
TAVILY_API_KEY=tvly-xxx...
```

---

## 模型选择决策树

```
任务来临
  ├─ 是否需要深度推理？
  │  ├─ 是 → thinking 模型
  │  └─ 否 → 下一步
  ├─ 成本受限吗？
  │  ├─ 是 → basic 模型
  │  └─ 否 → smart 模型
  └─ 默认选择 → smart 模型
```

---

## 缓存和性能

### LRU 缓存机制

工厂函数使用 `@lru_cache(maxsize=4)` 缓存最近4个不同配置的模型实例。

- **缓存键**：(model_tag, temperature) 元组
- **最大缓存**：4个模型实例
- **优势**：避免重复初始化相同配置的模型，提升性能

### 缓存策略建议

为了充分利用缓存，建议限制 temperature 个数：

```python
# ✓ 好的做法 - 固定几个预设
models = {
    "analysis": get_llm("smart", temperature=0.3),      # 分析模型
    "general": get_llm("smart", temperature=0.7),       # 通用模型
    "creative": get_llm("smart", temperature=0.9),      # 创意模型
}

# ✗ 不好的做法 - 每次都用不同temperature，缓存无效
for temp in [0.1, 0.2, 0.3, 0.4, 0.5]:
    model = get_llm("smart", temperature=temp)  # 缓存失效
```

---

## 错误排查

### 问题 1：API 密钥不存在

**错误消息**：
```
ValueError: API密钥未配置。缺失的环境变量...
```

**解决方案**：
1. 检查 `.env` 文件中对应的密钥是否存在
2. 确认环境变量已被加载（`load_dotenv()` 已调用）
3. 验证密钥值是否正确（不为空，格式有效）

### 问题 2：模型名称错误

**症状**：API 返回 "Model not found" 错误

**解决方案**：
1. 检查 `.env` 中的模型名称是否与API支持的名称一致
2. 常见有效的模型名称：
   - `gpt-4`, `gpt-4-turbo`, `gpt-4o`
   - `gpt-3.5-turbo`
   - 使用 API 的官方文档查看最新可用模型列表

### 问题 3：API Base URL 错误

**症状**：连接超时或 SSL 错误

**解决方案**：
1. 验证 `OPENAI_API_BASE` 或 `fangzhou_api_base` URL 是否正确
2. 确保 URL 以 `/v1` 结尾（如需要）
3. 测试 URL 连接：`ping <base_url>`

---

## 扩展和自定义

### 添加新的模型标签

如需支持新的模型标签，在 `_get_base_llm()` 函数中添加新的分支：

```python
@lru_cache(maxsize=4)
def _get_base_llm(model_tag: str, temperature: float = 0.7):
    # ... existing code ...
    elif model_tag == "my_custom_model":
        api_key = os.getenv("MY_CUSTOM_MODEL_API_KEY")
        base_url = os.getenv("MY_CUSTOM_MODEL_BASE")
        model_name = os.getenv("MY_CUSTOM_MODEL_NAME", "gpt-3.5-turbo")
    # ... rest of function ...
```

---

## 成本优化建议

1. **分级使用模型**：不是所有任务都需要最强模型
   - 常规任务用 basic
   - 通用任务用 smart
   - 只在必要时用 thinking

2. **批量操作时缩小 temperature 范围**
   - 避免因频繁改变 temperature 导致缓存失效
   - 预设几个常用的 temperature 值

3. **监控 API 调用频率**
   - 使用 Langsmith 集成（thread_id, user_id, mode）
   - 定期审查调用日志，识别优化机会
