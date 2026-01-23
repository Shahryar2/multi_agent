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
        改进版：文本和图片关联呈现
        Output Format:
        [
            {
                "type": "text", 
                "title": "...",
                "url": "...", 
                "content": "...",
                "score": 0.0,
                "related_images": [  # 新增
                    {"url": "...", "description": "..."},
                ]
            },
            {
                "type": "image",
                "url": "...",
                "description": "..."
            }
        ]
        """
        process_data = []
        
        # 1. 先收集所有图片（用于关联）
        all_images = raw_response.get("images", [])
        processed_images = []
        
        if include_images and all_images:
            unique_image_urls = set()
            for img in all_images:
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
                processed_images.append({
                    "url": url,
                    "description": desc
                })
        
        # 2. 处理文本内容（关联相关图片）
        results = raw_response.get("results", [])
        for idx, res in enumerate(results):
            content = res.get("content", "").strip()
            if len(content) < 30:
                continue
            
            # 为每个文本关联 2-3 张图片（简单策略：循环分配）
            related_images = []
            if include_images and processed_images:
                # 每个文本分配 2-3 张图片
                start_idx = (idx * 2) % len(processed_images)
                for i in range(2):
                    img_idx = (start_idx + i) % len(processed_images)
                    related_images.append(processed_images[img_idx])
            
            item = {
                "type": "text",
                "title": res.get("title", "No Title"),
                "url": res.get("url", ""),
                "content": content,
                "score": res.get("score", 0.0),
                "related_images": related_images  # 新增字段
            }
            process_data.append(item)
        
        # 3. 单独的图片项（用于纯图片展示）
        for img in processed_images:
            process_data.append({
                "type": "image",
                "url": img["url"],
                "description": img["description"]
            })
        
        return process_data

# 全局实例
search_provider = EnhancedTavilyWrapper()