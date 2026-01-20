import os
from functools import lru_cache
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from typing import Literal

# 加载环境变量
load_dotenv()

model_tag = "smart","basic"
@lru_cache()
def get_llm(model_tag:str, temperature: float = 0.7):
    """
    获取大模型实例的工厂函数
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

    if not api_key:
        raise ValueError("OPENAI_API_KEY not found in environment variables.")
    
    llm = ChatOpenAI(
        model=model_name,
        temperature=temperature,
        api_key=api_key,
        base_url=base_url,
        max_tokens = 4096,
        streaming=True,
    )
    
    return llm


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