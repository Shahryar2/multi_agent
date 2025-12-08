from langchain_core.tools import tool
from langchain_core.utils.function_calling import convert_to_openai_function
# from duckduckgo_search import DuckDuck
from langchain_community.tools import DuckDuckGoSearchRun
# 定义一个简单的工具
@tool
def search_weather(city: str):
    """
    模板
    查询指定城市的天气情况。
    """
    # 这里模拟一个API调用，实际项目中可以替换为真实API
    print(f"--- [工具调用] 正在查询 {city} 的天气 ---")
    if "北京" in city:
        return "北京今天晴天，气温 25 度，微风。"
    elif "上海" in city:
        return "上海今天小雨，气温 22 度，出门请带伞。"
    else:
        return f"{city} 的天气数据暂时无法获取，建议查询北京或上海。"
@tool
def web_search(query: str):
    """
    使用网络搜索引擎查询信息。
    """
    # 这里模拟一个API调用，实际项目中可以替换为真实API
    print(f"--- [工具调用] 正在进行网络搜索：{query} ---")
    search = DuckDuckGoSearchRun()
    return search.invoke(query)
# 导出工具列表，方便 Agent 加载
def get_tools():
    return [search_weather, web_search]