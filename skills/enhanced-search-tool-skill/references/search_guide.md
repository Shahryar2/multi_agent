# 搜索场景参考指南

## 快速场景选择

使用以下决策树快速选择合适的搜索场景：

```
    是否需要学术资料？
    ├─ 是 → academic（学术）
    └─ 否 ↓
    
    是否关于旅游/美食？
    ├─ 是 → travel（旅游）
    └─ 否 ↓
    
    是否关于生活/健康/创意？
    ├─ 是 → lifestyle（生活）
    └─ 否 ↓
    
    是否涉及社交媒体讨论？
    ├─ 是 → social_media（社交）
    └─ 否 → general（通用）
```

## 场景详细对比

### 搜索深度对比

| 深度 | 特征 | 搜索时间 | 结果质量 | 成本 |
|-----|------|--------|--------|------|
| advanced | 复杂查询、更多结果 | 3-5秒 | 高 | 高 |
| basic | 简单快速、精准结果 | 1-2秒 | 中 | 低 |

### 结果数量

- **social_media/academic**: 10条 - 适合详细研究
- **lifestyle**: 8条 - 平衡场景
- **travel**: 7条 - 信息型场景
- **general**: 5条 - 快速查询

## 查询优化建议

### Academic 场景

**适合的查询**：
- "最新的 deep learning 论文"
- "CVPR 2024 会议摘要"
- "neural network 算法研究"

**优化技巧**：
- 使用学术术语而不是日常用语
- 包含年份获取最新信息
- 提及具体的研究领域

### Social Media 场景

**适合的查询**：
- "AI 伦理讨论最新观点"
- "产品发布反馈"
- "技术社区热门话题"

**优化技巧**：
- 使用目标平台特有的用语
- 包含热门话题标签（如果适用）
- 寻求多个平台的观点

### Travel 场景

**适合的查询**：
- "巴黎春季旅游攻略"
- "日本京都美食推荐"
- "欧洲自由行预算规划"

**优化技巧**：
- 明确目的地和季节
- 包含活动类型（美食、景点、etc）
- 提及预算或旅行风格

### Lifestyle 场景

**适合的查询**：
- "居家瑜伽入门指南"
- "装修风格灵感"
- "健身计划制定"

**优化技巧**：
- 具体说明兴趣领域
- 包含级别信息（入门、进阶等）
- 提及个人偏好（if relevant）

### General 场景

**适合的查询**：
- "什么是 X？"
- "如何做 Y？"
- "X 最新消息"

**优化技巧**：
- 简洁明了的表述
- 避免过于复杂的逻辑
- 一个查询关注一个核心问题

## 网站域名参考

### 学术网站
- scholar.google.com - Google Scholar
- arxiv.org - 论文预印本库
- researchgate.net - 研究者社交平台
- ieee.org - IEEE 出版物
- acm.org - ACM 数字图书馆

### 社交媒体
- twitter.com / x.com - 实时讨论
- reddit.com - 社区讨论和 AMA
- facebook.com - 群组讨论
- instagram.com - 视觉内容
- tiktok.com - 短视频趋势

### 旅游信息
- tripadvisor.com - 旅游评分和评论
- booking.com - 住宿搜索
- agoda.com - 亚洲住宿
- airbnb.com - 民宿预订

### 生活方式
- medium.com - 长文章博客
- gq.com - 生活风格杂志
- healthline.com - 健康信息

## 结果解释

### 文本结果字段

```python
{
    "type": "text",
    "title": "文章标题",
    "url": "https://example.com/article",
    "content": "内容摘要...",
    "score": 0.95,  # 相关性评分（0-1）
    "related_images": [
        {
            "url": "https://...",
            "description": "图片描述"
        }
    ]
}
```

- **score**: 越接近1表示与查询越相关
- **related_images**: 自动关联的相关图片

### 性能指标

接收以下日志输出可了解搜索性能：

```
[Search Log] Start
Query: 用户查询
Mode: 使用的场景
Parameters: {...}
[Search Log] Success: Processed 8 items
```

- **Processed items**: 清洗后保留的结果数

## 高级用法

### 自定义配置

覆盖默认参数以满足特定需求：

```python
from modules.enhanced_search_tool import search_provider

# 场景：需要更多结果的学术搜索
results = search_provider.search(
    query="transformer 模型最新进展",
    config_name="academic",
    custom_config={
        "max_results": 20,  # 覆盖默认的10
        "include_images": False  # 不包含图片
    }
)
```

### 结果后处理

获取结果后的常见处理方式：

```python
# 按相关性排序
sorted_results = sorted(
    [r for r in results if r["type"] == "text"],
    key=lambda x: x["score"],
    reverse=True
)

# 按内容长度过滤
long_results = [
    r for r in results 
    if r.get("content", "") and len(r["content"]) > 200
]

# 合并图片
all_images = []
for result in results:
    if result["type"] == "text":
        all_images.extend(result.get("related_images", []))
    elif result["type"] == "image":
        all_images.append(result)
```

## 故障排查

### 问题：返回空列表

**原因可能**：
1. API 密钥无效
2. 查询语句存在问题
3. 网络连接问题

**解决方案**：
```python
import logging
logging.basicConfig(level=logging.DEBUG)

# 查看详细日志
results = search_provider.search("测试查询")
```

### 问题：图片没有关联

**原因**：
- 搜索结果中没有图片
- `include_images` 设为 False

**解决方案**：
```python
results = search_provider.search(
    query="...",
    config_name="general",
    custom_config={"include_images": True}
)
```

### 问题：结果太多/太少

**调整方法**：
```python
# 想要更多结果
results = search_provider.search(
    query="...",
    custom_config={"max_results": 20}
)

# 想要更快的结果
results = search_provider.search(
    query="...",
    custom_config={"search_depth": "basic"}
)
```

## 成本和性能

### 预期响应时间

- basic 搜索: 1-2 秒
- advanced 搜索: 3-5 秒
- 结果处理: 0.5-1 秒
- **总计**: 1-6 秒

### API 配额

每个 Tavily 账户有每日搜索限制。建议：
- 监控每日搜索数量
- 对相同查询进行缓存
- 在非高峰时段执行批量搜索
