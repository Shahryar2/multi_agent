from deepinsight.utils.skill_loader import load_skill_module

_skill = load_skill_module(
    "llm-factory-skill",
    "modules/llm_factory.py",
    "skills_llm_factory",
)

get_llm = _skill.get_llm
_get_base_llm = getattr(_skill, "_get_base_llm", None)

__all__ = ["get_llm", "_get_base_llm"]


if __name__ == "__main__":
    try:
        model = get_llm("smart")
        response = model.invoke("你好，请介绍一下你自己。")
        print(f"模型连接成功！\n回复: {response.content}")
    except Exception as e:
        print(f"模型连接失败: {e}")

    # try:
    #     print("正在测试 'thinking' 模型...")
    #     model = get_llm("thinking")
        
    #     # 换一个适合触发推理的问题
    #     question = "如果我有3个苹果，吃掉了1个，又买了2个，现在我有几个？请一步步思考。"
    #     response = model.invoke(question)
        
    #     print("\n=== 模型回复 Content ===")
    #     print(response.content)
        
    #     print("\n=== 元数据 ===")
    #     print(response.response_metadata)
    #     print("\n=== 额外信息 (可能包含思维链) ===")
    #     # 很多推理模型会把推理过程放在 additional_kwargs 中
    #     if response.additional_kwargs:
    #         print(response.additional_kwargs)
        
    #     # 检查 content 中是否包含常见的思维链标签
    #     if "<think>" in response.content:
    #         print("\n[通过 Content 检测到显式思维链标签]")
    #     elif "reasoning_content" in response.additional_kwargs:
    #          print("\n[通过 additional_kwargs 检测到推理内容]")

    # except Exception as e:
    #     print(f"模型连接失败: {e}")