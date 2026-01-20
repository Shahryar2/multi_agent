import sys
import os
import logging
from dotenv import load_dotenv

load_dotenv()

# 将项目根目录加入 python path，确保能导入 deepinsight 模块
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deepinsight.tools.search_provider import search_provider, SearchConfig

# 配置日志查看输出
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_social_search():
    print("\n=== 测试场景 1: 社交媒体搜索 (Social Media) ===")
    query = "Tesla Cybertruck latest reviews"
    
    # 使用 social_media 模式
    results = search_provider.search(query, config_name="social_media")
    
    # 验证逻辑
    images = [r for r in results if r['type'] == 'image']
    texts = [r for r in results if r['type'] == 'text']
    
    print(f"搜索词: {query}")
    print(f"返回结果总数: {len(results)}")
    print(f"文本条目数: {len(texts)}")
    print(f"图片条目数: {len(images)}")
    
    if images:
        print("\n[成功] 捕获到图片数据:")
        print(f"示例图片: {images[0]}")
    else:
        print("\n[警告] 未捕获到图片 (可能是 API Key 权限问题或该关键词无图)")

    if any("twitter.com" in r['url'] or "reddit.com" in r['url'] for r in results):
         print("[成功] 包含社媒来源域名")
    else:
         print("[提示] 本次结果未包含 twitter/reddit，可能是随机性或国内网络问题")

def test_academic_search():
    print("\n=== 测试场景 2: 学术严谨搜索 (Academic) ===")
    query = "Transformer architecture attention mechanism"
    
    results = search_provider.search(query, config_name="academic")
    
    images = [r for r in results if r['type'] == 'image']
    
    print(f"图片条目数: {len(images)} (预期为 0)")
    
    if len(images) == 0:
        print("[成功] 学术模式下正确过滤了图片")
    else:
        print("[失败] 学术模式下不应返回图片")

if __name__ == "__main__":
    # 确保 API KEY 存在
    if not os.getenv("TAVILY_API_KEY"):
        print("错误: 请先在 .env 文件中配置 TAVILY_API_KEY")
    else:
        test_social_search()
        test_academic_search()