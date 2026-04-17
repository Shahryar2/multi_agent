---
name: enhanced-search-tool-skill
description: >-
  增强的搜索工具Skill，基于Tavily API提供场景化搜索能力。
  支持五种预设场景（社交媒体/学术/旅游/生活/通用），每种场景有各自的搜索参数优化。
  当需要执行网络搜索、按场景优化搜索参数、或获取关联图片时使用。
---

# Enhanced Search Tool Skill

## 目标用途

提供统一、高效的网络搜索接口，自动针对不同场景优化搜索参数。该Skill负责：

- 场景化搜索（五种预设场景）
- 搜索结果清洗和融合
- 文本和图片的关联呈现
- 详细的日志记录和性能监控

## 五种核心场景配置

### 1. 🔗 Social Media（社交媒体）

**用途**：获取社交平台上的最新信息和跨平台讨论

**配置参数**：
- `search_depth`: "advanced" - 高级搜索
- `include_domains`: [twitter.com, reddit.com, facebook.com, instagram.com, tiktok.com]
- `max_results`: 10 - 返回10条结果
- `include_images`: True

**推荐查询例子**：
- "最新的技术行业讨论"
- "产品发布评论"
- "热门话题分析"

---

### 2. 🎓 Academic（学术研究）

**用途**：获取学术论文、研究数据和专业知识

**配置参数**：
- `search_depth`: "advanced"
- `include_domains`: [scholar.google.com, arxiv.org, researchgate.net]
- `exclude_domains`: [facebook.com, youtube.com]
- `max_results`: 10
- `include_images`: True

**推荐查询例子**：
- "最新的机器学习论文"
- "深度学习算法研究"
- "学术会议信息"

---

### 3. ✈️ Travel（旅游信息）

**用途**：获取旅行地点、攻略和旅游信息

**配置参数**：
- `search_depth`: "basic" - 基础搜索
- `max_results`: 7
- `include_images`: True

**推荐查询例子**：
- "北京旅游攻略"
- "巴黎美食推荐"
- "东京自由行计划"

---

### 4. 🎨 Lifestyle（生活方式）

**用途**：获取生活、健康、美学等方面的信息

**配置参数**：
- `search_depth`: "basic"
- `max_results`: 8
- `include_images`: True

**推荐查询例子**：
- "健身计划"
- "家居装修灵感"
- "文艺创意分享"

---

### 5. 📰 General（通用搜索）

**用途**：通用网络搜索，适合所有不属于以上四类的查询

**配置参数**：
- `search_depth`: "basic"
- `max_results`: 5
- `include_images`: True

**推荐查询例子**：
- "天气预报"
- "新闻资讯"
- "常规信息查询"

---

## 核心API

### `search()` - 执行搜索

执行搜索并返回清洗后的结果。

**参数**：
```python
search(
    query: str,              # 搜索查询语句
    config_name: str = "general",  # 场景名称
    custom_config: Dict = None     # 自定义参数（覆盖默认）
) -> List[Dict[str, Any]]
```

**返回值**：
清洗后的搜索结果列表，每项格式如下：

```python
{
    "type": "text" | "image",
    "title": "文章标题",           # 仅文本结果有
    "url": "https://example.com",
    "content": "文章内容摘要",      # 仅文本结果有
    "score": 0.85,                 # 相关性评分，仅文本有
    "related_images": [            # 关联的图片列表
        {
            "url": "https://image.url",
            "description": "图片描述"
        },
        ...
    ],
    "description": "图片描述"      # 仅图片结果有
}
```

**使用示例**：
```python
from modules.enhanced_search_tool import EnhancedTavilyWrapper

searcher = EnhancedTavilyWrapper()

# 场景1：学术搜索
results = searcher.search(
    query="最新的大语言模型研究",
    config_name="academic"
)

# 场景2：社交媒体讨论
results = searcher.search(
    query="AI 伦理问题讨论",
    config_name="social_media"
)

# 场景3：自定义参数
results = searcher.search(
    query="深圳美食",
    config_name="general",
    custom_config={"max_results": 15}  # 覆盖默认的5条
)
```

---

## 结果处理流程

```
原始 Tavily 响应
    ↓
_process_results() 处理
    ├─ 提取文本内容 (title, url, content)
    ├─ 提取图片       (url, description)
    └─ 建立文本-图片关联
    ↓
compress_search_results() 清洗
    ├─ 去重
    ├─ 按长度过滤
    └─ 按分数过滤
    ↓
返回清洗后的结果列表
```

---

## 日志和监控

所有搜索操作都记录详细日志，包括：

```
[Search Log] Start
Query: 用户查询
Mode: 使用的场景
Parameters: 具体参数
[Search Log] Success: Processed X items
```

日志级别：
- **INFO**：正常搜索启动和完成
- **DEBUG**：跳过的低质量结果
- **ERROR**：搜索失败和异常

---

## 错误处理

### 缺失 API 密钥

**症状**：
```
Warning: TAVILY_API_KEY is missing
ValueError: TAVILY_API_KEY is missing
```

**解决方案**：
1. 在 `.env` 文件中设置 `TAVILY_API_KEY`
2. 确保 `.env` 已被加载
3. 验证密钥值正确（不为空）

### 搜索失败

**症状**：返回空列表 `[]`

**常见原因**：
- 网络连接问题
- 查询语句过于特殊或不符合格式
- Tavily API 配额已用完
- API 服务暂时不可用

---

## 性能特性

- **场景化优化**：每个场景都有针对性的参数调优
- **内容清洗**：自动过滤高质量结果（最少30字）
- **图片关联**：为文本结果关联相关图片，提升表现力
- **日志详尽**：完整的执行日志便于调试和监控

---

## 集成指南

### 在 Agents 中的使用

```python
from modules.enhanced_search_tool import search_provider

def research_node(state: ResearchState):
    # 根据任务特点选择场景
    config_name = determine_config(state["task"])
    
    # 执行搜索
    results = search_provider.search(
        query=state["task"],
        config_name=config_name
    )
    
    # 处理结果
    state["documents"].extend(results)
    return state
```

### 场景自动选择逻辑

```python
def determine_config(query: str) -> str:
    """根据查询内容自动选择场景"""
    keywords = {
        "academic": ["论文", "研究", "学术", "arxiv"],
        "social_media": ["推特", "reddit", "讨论", "话题"],
        "travel": ["旅游", "攻略", "目的地", "酒店"],
        "lifestyle": ["生活", "健康", "美食", "装修"]
    }
    
    for scene, kws in keywords.items():
        if any(kw in query for kw in kws):
            return scene
    
    return "general"
```

---

## 最佳实践

1. **选择合适的场景**：
   - 不要所有查询都用 "general"
   - 学术内容用 "academic"
   - 社交讨论用 "social_media"

2. **控制结果数量**：
   - 避免一次性获取太多结果
   - 必要时用 `custom_config` 调整 `max_results`

3. **处理图片关联**：
   - 文本结果已自动关联图片
   - 可直接使用 `related_images` 进行展示

4. **监控日志**：
   - 定期检查搜索日志
   - 识别和优化低质量查询

---

## 场景对比

| 特性 | 社交媒体 | 学术 | 旅游 | 生活 | 通用 |
|------|--------|------|------|------|------|
| 搜索深度 | 高级 | 高级 | 基础 | 基础 | 基础 |
| 最大结果数 | 10 | 10 | 7 | 8 | 5 |
| 包含图片 | ✓ | ✓ | ✓ | ✓ | ✓ |
| 目标网站 | 社交平台 | 学术网站 | 任意 | 任意 | 任意 |
| 速度 | 中等 | 中等 | 快 | 快 | 快 |

