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
    获取大模型实例的工厂函数。
    使用 lru_cache 确保在相同参数下只创建一个实例（单例优化）。
    """
    if model_tag == "smart":
        api_key = os.getenv("fangzhou_api_key")
        base_url = os.getenv("fangzhou_api_base")
        model_name = os.getenv("Gemini_model", "gpt-3.5-turbo")
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
        # 关键：支持流式输出，这对用户体验至关重要
        streaming=True 
    )
    
    return llm

# 简单的测试代码，仅在直接运行此文件时执行
if __name__ == "__main__":
    try:
        model = get_llm()
        response = model.invoke("你好，请介绍一下你自己。")
        print(f"模型连接成功！\n回复: {response.content}")
    except Exception as e:
        print(f"模型连接失败: {e}")