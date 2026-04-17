"""
增强搜索工具模块

基于Tavily API提供场景化的网络搜索能力。
支持五种预设场景，每种场景都有针对性的参数优化。

核心类：
- SearchConfig：五种场景的配置定义
- EnhancedTavilyWrapper：搜索执行和结果处理

支持的场景：
- social_media: 社交媒体讨论
- academic: 学术研究
- travel: 旅游信息
- lifestyle: 生活方式
- general: 通用搜索
"""

import logging
import json
import os
from typing import List, Dict, Any, Optional
from tavily import TavilyClient
from deepinsight.utils.normalizers import compress_search_results

logger = logging.getLogger(__name__)


class SearchConfig:
    """
    不同场景的搜索配置
    
    每个场景都定义了针对性的搜索参数，包括：
    - 搜索深度（basic/advanced）
    - 包含/排除的域名
    - 是否包含图片
    - 返回的最大结果数
    """
    SCENARIOS = {
        "social_media": {
            # 社交媒体：获取最新讨论和跨平台观点
            "search_depth": "advanced",
            "include_domains": [
                "twitter.com", "reddit.com", "facebook.com", 
                "instagram.com", "tiktok.com"
            ],
            "include_images": True,
            "include_images_descriptions": True,
            "max_results": 10
        },
        "academic": {
            # 学术研究：获取论文和研究数据
            "search_depth": "advanced",
            "include_domains": [
                "scholar.google.com", "arxiv.org", "researchgate.net"
            ],
            "exclude_domains": ["facebook.com", "youtube.com"],
            "include_images": True,
            "include_images_descriptions": True,
            "max_results": 10
        },
        "travel": {
            # 旅游信息：获取旅行指南和目的地信息
            "search_depth": "basic",
            "include_images": True,
            "max_results": 7,
            "exclude_domains": []
        },
        "lifestyle": {
            # 生活方式：获取健康、美学、创意等信息
            "search_depth": "basic",
            "include_images": True,
            "max_results": 8,
            "exclude_domains": []
        },
        "general": {
            # 通用搜索：默认场景，适合所有其他查询
            "search_depth": "basic",
            "include_images": True,
            "max_results": 5
        }
    }


class EnhancedTavilyWrapper:
    """
    增强的 Tavily 搜索包装器
    
    功能：
    1. 支持原生 API 的高级参数
    2. 内置结果清洗和提取管道
    3. 集成日志记录和性能监控
    4. 文本和图片的智能关联呈现
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        初始化搜索包装器
        
        Args:
            api_key: Tavily API 密钥，默认从环境变量读取
        """
        self.api_key = api_key or os.getenv("TAVILY_API_KEY")
        if not self.api_key:
            logger.warning("TAVILY_API_KEY is missing. Search functionality may be limited.")
        self.client = None

    @property
    def tavily_client(self):
        """延迟初始化 Tavily 客户端，避免异常API密钥"""
        if not self.client:
            if not self.api_key:
                raise ValueError(
                    "TAVILY_API_KEY is missing. "
                    "Please set it in environment variables or pass it to __init__."
                )
            self.client = TavilyClient(api_key=self.api_key)
        return self.client

    def search(
        self,
        query: str,
        config_name: str = "general",
        custom_config: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        """
        执行场景化搜索
        
        Args:
            query: 搜索查询语句
            config_name: 场景名称 (social_media/academic/travel/lifestyle/general)
            custom_config: 自定义参数，会覆盖场景默认参数
            
        Returns:
            List[Dict]: 清洗后的搜索结果列表
            
        Example:
            >>> searcher = EnhancedTavilyWrapper()
            >>> results = searcher.search("AI论文", config_name="academic")
            >>> print(len(results))  # 返回的结果数
        """
        # 获取场景配置
        params = SearchConfig.SCENARIOS.get(
            config_name, 
            SearchConfig.SCENARIOS["general"]
        ).copy()
        
        # 应用自定义配置覆盖
        if custom_config:
            params.update(custom_config)

        # 记录搜索日志
        logger.info(f"--- [Search Log] Start ---")
        logger.info(f"Query: {query}")
        logger.info(f"Mode: {config_name}")
        debug_params = {
            k: v for k, v in params.items() 
            if k != "api_key"
        }
        logger.info(f"Parameters: {json.dumps(debug_params, ensure_ascii=False)}")

        try:
            # 执行搜索
            response = self.tavily_client.search(
                query=query,
                search_depth=params.get("search_depth", "basic"),
                include_domains=params.get("include_domains", None),
                exclude_domains=params.get("exclude_domains", None),
                include_images=params.get("include_images", False),
                include_images_descriptions=params.get(
                    "include_images_descriptions", False
                ),
                max_results=params.get("max_results", 5)
            )
            
            # 处理和清洗结果
            cleaned_results = self._process_results(
                response, 
                include_images=params.get("include_images", False)
            )

            cleaned_results = compress_search_results(
                cleaned_results,
                max_per_item=1500,
                min_length=30,
                min_score=0.0
            )
            
            logger.info(
                f"--- [Search Log] Success: "
                f"Processed {len(cleaned_results)} items ---"
            )
            return cleaned_results
            
        except Exception as e:
            logger.error(f"--- [Search Log] Error: {e} ---")
            return []

    def _process_results(
        self, 
        raw_response: Dict[str, Any],
        include_images: bool
    ) -> List[Dict[str, Any]]:
        """
        处理原始搜索结果：清洗、融合、关联
        
        将文本和图片智能关联，生成结构化输出。
        
        Args:
            raw_response: Tavily API 的原始响应
            include_images: 是否包含图片
            
        Returns:
            List[Dict]: 结构化的结果列表
        """
        process_data = []

        # 第1步：收集所有图片用于关联
        all_images = raw_response.get("images", [])
        processed_images = []

        if include_images and all_images:
            unique_image_urls = set()
            
            for img in all_images:
                # 支持字符串格式和字典格式的图片
                if isinstance(img, str):
                    url = img
                    desc = "Image result"
                elif isinstance(img, dict):
                    url = img.get("url")
                    desc = img.get("description") or "Image result"
                else:
                    continue

                # 验证URL
                if not url or not url.startswith("http"):
                    continue
                if url in unique_image_urls:
                    continue

                unique_image_urls.add(url)
                processed_images.append({
                    "url": url,
                    "description": desc
                })

        # 第2步：处理文本结果并关联图片
        results = raw_response.get("results", [])
        for idx, res in enumerate(results):
            content = res.get("content", "").strip()
            title = res.get("title", "No Title").strip()
            url = res.get("url", "")

            # 过滤低质量结果
            if not content or len(content) < 50:
                logger.debug(f"跳过内容为空或过短的结果: {title}")
                continue

            # 为每个文本关联2-3张图片（循环分配策略）
            related_images = []
            if include_images and processed_images:
                start_idx = (idx * 2) % len(processed_images)
                for i in range(2):
                    img_idx = (start_idx + i) % len(processed_images)
                    related_images.append(processed_images[img_idx])

            item = {
                "type": "text",
                "title": title,
                "url": url,
                "content": content,
                "score": res.get("score", 0.0),
                "related_images": related_images
            }
            process_data.append(item)

        # 第3步：添加独立的图片项
        for img in processed_images:
            process_data.append({
                "type": "image",
                "url": img["url"],
                "description": img["description"]
            })

        return process_data


# 全局实例（模块级单例）
search_provider = EnhancedTavilyWrapper()
