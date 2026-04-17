"""
LLM 工厂模块

提供统一的LLM实例获取接口，支持多模型标签、环境配置管理、
以及Langsmith监控上下文集成。

核心函数：
- get_llm()：获取配置好的LLM实例（主入口）
- _get_base_llm()：内部缓存函数，确保相同配置复用同一实例

支持的模型标签：
- smart: 高性能模型（Gemini API）
- thinking: 推理模型（支持深度思考）
- basic: 基础模型（OpenAI API）
"""

import os
from functools import lru_cache
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from typing import Optional

# 加载环境变量
load_dotenv()


@lru_cache(maxsize=4)
def _get_base_llm(model_tag: str, temperature: float = 0.7):
    """
    内部获取大模型基础实例的缓存函数
    
    使用 @lru_cache 确保相同配置的模型实例被复用，
    避免重复初始化和API调用。
    
    Args:
        model_tag: 模型标签 ("smart", "thinking", "basic")
        temperature: 采样温度 (0.0-1.0)，默认0.7
        
    Returns:
        ChatOpenAI: 配置好的大模型实例
        
    Raises:
        ValueError: 当指定模型标签的API密钥缺失时
    """
    if model_tag == "smart":
        api_key = os.getenv("Gemini_api_key")
        base_url = os.getenv("fangzhou_api_base")
        model_name = os.getenv("Gemini_model", "gpt-3.5-turbo")
    elif model_tag == "thinking":
        api_key = os.getenv("Gemini_thinking_api_key")
        base_url = os.getenv("fangzhou_api_base")
        model_name = os.getenv("Gemini_thinking_model", "gpt-3.5-turbo")
    elif model_tag == "basic":
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_API_BASE")
        model_name = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
    else:
        raise ValueError(f"Unknown model tag: {model_tag}")

    if not api_key:
        raise ValueError(
            f"API密钥未配置。缺失的环境变量：\n"
            f"  模型标签: {model_tag}\n"
            f"  请检查 .env 文件并重新加载环境变量。"
        )
    
    return ChatOpenAI(
        model_name=model_name,
        temperature=temperature,
        openai_api_key=api_key,
        openai_api_base=base_url,
    )


def get_llm(
    model_tag: str,
    temperature: float = 0.7,
    thread_id: Optional[str] = None,
    user_id: Optional[str] = None,
    mode: Optional[str] = None
):
    """
    获取大模型实例的工厂函数
    
    这是与LLM交互的统一入口，集成了以下能力：
    - 多模型管理（smart/thinking/basic）
    - 实例缓存复用
    - Langsmith监控上下文绑定
    
    Args:
        model_tag: 模型标签 ("smart", "thinking", "basic")。
                   - smart: 高性能通用模型
                   - thinking: 推理模型
                   - basic: 基础/备用模型
        temperature: 采样温度，范围0.0-1.0，默认0.7
                     (越低越确定性，越高越随机)
        thread_id: 线程ID，用于Langsmith追踪用户会话，格式如"user_123_session_456"
        user_id: 用户ID，用于Langsmith记录用户级别的行为
        mode: 操作模式，用于分类不同的工作流（如"research", "chat", "analysis"）
              
    Returns:
        ChatOpenAI: 配置好的大模型实例，可直接调用 invoke() 等方法
        
    Raises:
        ValueError: 当模型标签未知或API密钥缺失时
        
    Example:
        >>> # 基础使用
        >>> model = get_llm("smart")
        >>> response = model.invoke("你好")
        
        >>> # 生产环境使用（推荐）
        >>> model = get_llm(
        ...     model_tag="smart",
        ...     temperature=0.3,
        ...     thread_id="user_123_session_456",
        ...     user_id="user_123",
        ...     mode="research"
        ... )
        >>> response = model.invoke("请分析这个数据")
    """
    # 获取基础LLM实例（通过缓存复用）
    base_llm = _get_base_llm(model_tag, temperature)

    # 构建Langsmith监控上下文
    tags = []
    metadata = {}

    if mode:
        tags.append(mode)
    if thread_id:
        metadata["thread_id"] = thread_id
    if user_id:
        metadata["user_id"] = user_id

    # 如果有监控上下文信息，通过 with_config 绑定
    if tags or metadata:
        return base_llm.with_config({"tags": tags, "metadata": metadata})
    
    return base_llm


# 测试和演示代码
if __name__ == "__main__":
    try:
        print("测试 LLM Factory Skill...")
        print("-" * 50)
        
        # 测试1：基础使用
        print("测试1：基础使用 - smart 模型")
        model = get_llm("smart")
        response = model.invoke("你好，请介绍一下你自己。")
        print(f"✓ 模型连接成功！")
        print(f"回复: {response.content[:100]}...\n")
        
        # 测试2：带上下文的使用
        print("测试2：带监控上下文使用")
        model_with_context = get_llm(
            model_tag="smart",
            temperature=0.5,
            thread_id="test_session_001",
            user_id="test_user_001",
            mode="research"
        )
        print("✓ 带上下文的模型实例创建成功\n")
        
        # 测试3：缓存验证
        print("测试3：缓存验证（同参数应返回相同实例）")
        model_1 = get_llm("smart", temperature=0.7)
        model_2 = get_llm("smart", temperature=0.7)
        print(f"相同参数实例对比: {id(model_1)} == {id(model_2)}: {id(model_1) == id(model_2)}")
        print("✓ 缓存工作正常\n")
        
        print("-" * 50)
        print("所有测试通过！✓")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
