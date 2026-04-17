---
name: llm-factory-skill
description: >-
  统一的LLM工厂函数，支持三种模型标签（smart、thinking、basic）的初始化和配置。
  当需要获取LLM实例、多模型支持、环境配置管理、或集成监控上下文时使用。
---

# LLM Factory Skill

## 目标用途

提供标准化的LLM工厂函数，作为项目的基础依赖层。该Skill负责：

- 多模型标签管理（smart/thinking/basic）
- 环境变量配置读取和缓存
- LLM实例的工厂创建
- Langsmith监控上下文集成（thread_id, user_id, mode）

## 核心功能

### 1. `get_llm()` - 工厂函数 (主入口)

获取配置好的LLM实例，支持监控上下文集成。

**使用场景**：
- 初始化不同用途的模型实例
- 需要绑定用户/线程/模式上下文的场景
- 需要统一模型管理的工作流

**参数示例**：
```python
from modules.llm_factory import get_llm

# 场景1：基础使用
model = get_llm(model_tag="smart", temperature=0.7)

# 场景2：带上下文的使用（推荐用于生产环境）
model = get_llm(
    model_tag="smart",
    temperature=0.7,
    thread_id="user_123_session_456",
    user_id="user_123",
    mode="research"
)
```

### 2. 模型标签说明

详见 `references/model_config.md`

- **smart**: 高性能模型，基于 Gemini API
- **thinking**: 推理模型，支持深度思考链
- **basic**: 基础模型，OpenAI API

## 工作流程

1. **配置读取**：从环境变量获取API密钥和模型名称
2. **缓存机制**：通过 `@lru_cache` 避免重复初始化相同配置
3. **上下文绑定**：可选地绑定 Langsmith 监控元数据
4. **异常处理**：缺少API密钥时抛出明确的错误

## 环境变量要求

详见 `references/model_config.md` 和项目 `.env` 文件

## 集成指南

### 导入方式

```python
# 方式1：直接导入工厂函数
from skills.llm_factory_skill.modules.llm_factory import get_llm

# 方式2：保持向后兼容（代理导入）
from deepinsight.core.llm import get_llm
```

### 迁移步骤

1. 现有代码无需修改（通过代理导入保持兼容）
2. 新代码优先使用 Skill 中的导入路径
3. 建议逐步重构现有导入指向 Skill 模块

## 错误处理

- **缺失API密钥**：明确指出是哪个模型标签的密钥缺失
- **模型初始化失败**：详细的异常信息便于调试
- **缓存异常**：自动忽略异常继续创建新实例

## 性能特性

- **缓存高效**：相同参数的LLM实例复用，避免重复初始化
- **线程安全**：`lru_cache` 和 `with_config` 都是线程安全的
- **轻量级**：只在调用时才初始化模型，不在导入时加载

---

# 使用示例

## 基础使用

```python
from modules.llm_factory import get_llm

model = get_llm("smart")
response = model.invoke("你好，请自我介绍")
print(response.content)
```

## 生产环境使用

```python
from modules.llm_factory import get_llm

# 在API处理函数中
def handle_request(user_id, thread_id, task_content):
    # 根据复杂度选择模型
    model = get_llm(
        model_tag="thinking" if len(task_content) > 1000 else "smart",
        temperature=0.3,  # 降低随机性提高稳定性
        thread_id=thread_id,
        user_id=user_id,
        mode="research"
    )
    
    return model.invoke(task_content)
```

## 多模型切换

```python
from modules.llm_factory import get_llm

models = {
    "analysis": get_llm("smart", temperature=0.3),
    "creative": get_llm("smart", temperature=0.9),
    "reasoning": get_llm("thinking", temperature=0.5)
}

analysis_result = models["analysis"].invoke("分析这个数据...")
creative_result = models["creative"].invoke("编写一个故事...")
reasoning_result = models["reasoning"].invoke("推理这个问题...")
```
