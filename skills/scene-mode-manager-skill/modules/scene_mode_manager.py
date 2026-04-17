"""
场景模式管理模块

定义和管理四种操作场景（Research, Chat, Comparison, Follow-up）
以及每种模式的完整配置参数。

核心函数：
- get_mode_config()：获取指定模式的完整配置
- get_all_modes()：获取所有模式的摘要信息（前端展示用）

支持的模式：
- research: 深度研究报告模式
- chat: 轻量随聊模式
- comparison: 快速对比模式
- follow_up: 追问前文模式
"""

from typing import Dict, Any


# 完整配置字典
MODE_CONFIGS = {
    "research": {
        "name": "📊 深度研究报告",
        "description": "完整的任务拆解和深度分析，适合需要详细报告的场景",
        "emoji": "📊",
        "max_search_depth": "advanced",  # 搜索深度：advanced | basic | none
        "max_documents": 30,  # 最多获取文档数
        "research_rounds": 1,  # 搜索轮次（0 = 不搜索，1 = 一轮，n = n 轮）
        "output_format": "full_report",  # 输出格式：full_report | plain_text | comparison_table
        "cost_budget": "high",  # 成本预算：high | medium | minimal
        "enable_revision": True,  # 是否启用审核和修正
        "auto_plan_approval": False,  # 是否自动批准计划（False = 需用户批准）
        "context_injection": None,  # 是否注入历史上下文
    },
    "chat": {
        "name": "💬 轻量随聊",
        "description": "基于已有资料快速回答，适合追问和知识库对话",
        "emoji": "💬",
        "max_search_depth": "none",
        "max_documents": 0,
        "research_rounds": 0,
        "output_format": "plain_text",
        "cost_budget": "minimal",
        "enable_revision": False,
        "auto_plan_approval": True,
        "context_injection": "last_draft",  # 注入前一轮的报告
    },
    "comparison": {
        "name": "📝 快速对比",
        "description": "生成对比表格，适合快速对比两个或多个对象",
        "emoji": "📝",
        "max_search_depth": "basic",
        "max_documents": 15,
        "research_rounds": 1,
        "output_format": "comparison_table",
        "cost_budget": "medium",
        "enable_revision": False,
        "auto_plan_approval": True,
        "context_injection": None,
    },
    "follow_up": {
        "name": "🔍 追问前文",
        "description": "基于前一轮对话继续讨论，无需新搜索",
        "emoji": "🔍",
        "max_search_depth": "none",
        "max_documents": 0,
        "research_rounds": 0,
        "output_format": "contextual_response",
        "cost_budget": "minimal",
        "enable_revision": False,
        "auto_plan_approval": True,
        "context_injection": "full_context",  # 注入完整上下文
    },
}


def get_mode_config(mode: str) -> Dict[str, Any]:
    """
    获取指定模式的完整配置
    
    如果模式名称未知，返回 "research" 模式作为默认值。
    
    Args:
        mode: 模式名称 ("research", "chat", "comparison", "follow_up")
    
    Returns:
        Dict[str, Any]: 该模式的完整配置字典，包含所有参数
        
    Example:
        >>> config = get_mode_config("research")
        >>> print(config["max_documents"])  # 30
        >>> print(config["cost_budget"])    # "high"
    """
    if mode not in MODE_CONFIGS:
        print(f"⚠️  未知模式: {mode}，使用 'research' 作为默认模式")
        return MODE_CONFIGS["research"].copy()
    return MODE_CONFIGS[mode].copy()


def get_all_modes() -> Dict[str, Dict[str, str]]:
    """
    获取所有可用模式的摘要信息（前端展示用）
    
    只返回模式的基本信息（name、description、emoji），
    而不返回所有的技术配置参数。
    
    Returns:
        Dict[str, Dict[str, str]]: 所有模式的摘要，格式如下：
        {
            "research": {
                "name": "📊 深度研究报告",
                "description": "完整的任务拆解和深度分析...",
                "emoji": "📊"
            },
            "chat": {...},
            ...
        }
        
    Example:
        >>> modes = get_all_modes()
        >>> for mode_key, info in modes.items():
        ...     print(f"{info['emoji']} {info['name']}")
        📊 深度研究报告
        💬 轻量随聊
        📝 快速对比
        🔍 追问前文
    """
    return {
        key: {
            "name": config["name"],
            "description": config["description"],
            "emoji": config["emoji"],
        }
        for key, config in MODE_CONFIGS.items()
    }


# 测试和演示代码
if __name__ == "__main__":
    print("=" * 60)
    print("场景模式管理 Skill 演示")
    print("=" * 60)

    # 演示1：获取单个模式配置
    print("\n[演示1] 获取单个模式配置")
    print("-" * 60)
    
    research_config = get_mode_config("research")
    print(f"研究模式配置:")
    print(f"  名称: {research_config['name']}")
    print(f"  搜索深度: {research_config['max_search_depth']}")
    print(f"  最大文档数: {research_config['max_documents']}")
    print(f"  成本预算: {research_config['cost_budget']}")
    print(f"  启用审核: {research_config['enable_revision']}")

    # 演示2：获取所有模式摘要
    print("\n[演示2] 获取所有模式摘要（前端展示）")
    print("-" * 60)
    
    all_modes = get_all_modes()
    for mode_key, info in all_modes.items():
        print(f"{info['emoji']} {info['name']}")
        print(f"   {info['description']}")

    # 演示3：模式特性对比
    print("\n[演示3] 模式特性对比")
    print("-" * 60)
    print(f"{'模式':<12} {'搜索深度':<12} {'文档数':<8} {'成本':<8} {'时间':<10}")
    print("-" * 60)
    
    for mode_key in ["research", "chat", "comparison", "follow_up"]:
        config = get_mode_config(mode_key)
        time_estimate = {
            "research": "5-10分钟",
            "chat": "<1分钟",
            "comparison": "2-3分钟",
            "follow_up": "<1分钟"
        }[mode_key]
        
        print(f"{mode_key:<12} {config['max_search_depth']:<12} "
              f"{config['max_documents']:<8} {config['cost_budget']:<8} "
              f"{time_estimate:<10}")

    # 演示4：错误处理（未知模式）
    print("\n[演示4] 错误处理 - 未知模式")
    print("-" * 60)
    
    unknown_config = get_mode_config("unknown_mode")
    print(f"获得的模式: 研究模式（默认）")
    print(f"成本预算: {unknown_config['cost_budget']}")

    print("\n" + "=" * 60)
    print("演示完成！✓")
    print("=" * 60)
