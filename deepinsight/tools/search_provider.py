import logging
import json
import os
from typing import List, Dict, Any,Optional
from langchain_community.tools.tavily_search.tool import TavilySearchResults
from tavily import TavilyClient

logger = logging.getLogger(__name__)

class SearchConfig:
    """
    不同场景的搜索配置
    """
    SCENRIOS = {
        "social_media":{
            # 社媒类
            "search_depth": "advanced", # 高级模式
            "include_domains": ["twitter.com", "reddit.com","facebook.com", "instagram.com","tiktok.com"],
            "include_images": True,
            "include_images_descriptions": True,
            "max_results": 10
        },
        "academic":{
            # 学术类
            "search_depth": "advanced",
            "include_domains": ["scholar.google.com", "arxiv.org", "researchgate.net"],
            "exclude_domains": ["facebook.com", "youtube.com"],
            "include_images": True,
            "include_images_descriptions": True,
            "max_results": 10
        },
        "travel":{
            # 旅游类
            "search_depth": "basic",
            "include_images": True,
            "max_results": 7,
            "exclude_domains": []
        },
        "general":{
            # 通用类
            "search_depth": "basic",
            "include_images": False,
            "max_results": 5
        }
    }


class EnhancedTavilyWrapper:
    """
    增强 Tavily 搜索包装器
    1. 支持原生 API 的高级参数
    2. 内置清洗和提取管道
    3. 集成日志记录
    """
    def __init__(self,api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("TAVILY_API_KEY")
        if not self.api_key:
            logger.warning("TAVILY_API_KEY is missing.")
        self.client = None

    @property
    def tavily_client(self):
        if not self.client:
            if not self.api_key:
                raise ValueError("TAVILY_API_KEY is missing.")
            self.client = TavilyClient(api_key=self.api_key)
        return self.client
    
    def search(
            self,
            query: str,
            config_name: str = "general",
            custom_config: Optional[Dict] = None
    ) -> List[Dict[str,Any]]:
        """
        执行搜索并返回清洗后的结果
        """
        params = SearchConfig.SCENRIOS.get(config_name, SearchConfig.SCENRIOS["general"]).copy()
        if custom_config:
            params.update(custom_config)
        
        logger.info(f"--- [Search Log] Start ---")
        logger.info(f"Query: {query}")
        logger.info(f"Mode: {config_name}")
        debug_params = {k:v for k,v in params.items() if k != "api_key"}
        logger.info(f"Parameters: {json.dumps(debug_params, ensure_ascii=False)}")

        try:
            response = self.tavily_client.search(
                query=query,
                search_depth=params.get("search_depth", "basic"),
                include_domains=params.get("include_domains", None),
                exclude_domains=params.get("exclude_domains", None),
                include_images=params.get("include_images", False),
                include_images_descriptions=params.get("include_images_descriptions", False),
                max_results=params.get("max_results", 5)
            )
            # 数据清洗与融合
            cleaned_results = self._process_results(response, include_images=params.get("include_images", False))
            
            logger.info(f"--- [Search Log] Success: Processed {len(cleaned_results)} items ---")
            return cleaned_results
        except Exception as e:
            logger.error(f"--- [Search Log] Error: {e} ---")
            return []
        

    def _process_results(self, raw_response: Dict[str, Any], include_images: bool) -> List[Dict[str, Any]]:
        """
        管道：清洗结果，分离文本、图片
        Output Fromat:
        [
            {"type": "text", "title": "...","url": "...", "content": "..."},
            {"type": "image", "title": "...", "url": "...", "content":"[图片]"}
        ]
        """
        process_data = []
        # 1. 处理文本内容
        results = raw_response.get("results", [])
        for res in results:
            content = res.get("content", "").strip()
            if len(content) < 30:
                continue  # 跳过过短内容
            
            item = {
                "type": "text",
                "title": res.get("title", "No Title"),
                "url": res.get("url", ""),
                "content": content,
                "score": res.get("score", 0.0)
            }
            process_data.append(item)

        # 2. 处理图片内容
        images = raw_response.get("images", [])
        if include_images and images:
            # 去重
            unique_image_urls = set()
            for img in images:
                if isinstance(img, str):
                    url = img
                    desc = "Image result"
                elif isinstance(img, dict):
                    url = img.get("url")
                    desc = img.get("description") or "Image result"
                else:
                    continue

                if not url or not url.startswith("http"):
                    continue
                if url in unique_image_urls:
                    continue
                unique_image_urls.add(url)

                process_data.append({
                    "type": "image",
                    "title": "Image Result",
                    "url": url,
                    "content": f"[图片] URL: {url} | 描述: {desc}",
                    "score": 0.0
                })

        return process_data

# 全局实例
search_provider = EnhancedTavilyWrapper()