import json
import re
from urllib.parse import urlparse
from typing import Any, Dict, List, TypedDict
import logging
import uuid

logger = logging.getLogger(__name__)

def make_segment(query: str, url: str, title: str, text: str, source: str, extra: Dict[str, Any] = None) -> Dict[str, Any]:
    """生成标准化的 segment dict"""
    clean_texted = clean_text(text)

    # 简单验证 URL
    valid_url = ""
    if url and isinstance(url, str):
        url = url.strip()
        try:
            parsed = urlparse(url)
            # 必须包含 scheme (http/https) 和 netloc
            if parsed.scheme in ('http', 'https') and parsed.netloc:
                valid_url = url
        except Exception:
            pass

    return {
        "id": str(uuid.uuid4())[:8],
        "source": source,
        "query": query,
        "url": valid_url,
        "title": title or "",
        "text": clean_texted,
        "metadata": extra or {}
    }

def clean_text(text: str) -> str:
    """
    深度清洗:
    1. 去除多余空白和换行
    2. 统一编码
    """
    if not text:
        return ""
    # 1. 去除 HTML 标签
    text = re.sub(r'<[^>]+>', '', text)
    # 2. 去除 Markdown 图片/链接语法但保留文字 [text](url) -> text
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
    text = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', text)
    # 3. 去除长串 URL
    text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)
    # 4. 合并多余空白和换行
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def deupdate_segment(segment: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # 去重
    seen = set()
    out = []
    for seg in segment:
        if len(seg.get("text","")) < 10:
            continue

        key = seg.get("url") or seg.get("title") or seg.get("text")[:200]
        if key and key not in seen:
            seen.add(key)
            out.append(seg)
    return out

def normalize_data(results: Any,query: str,source: str = "tavily") -> List[Dict[str, Any]]:
    """
    输入数据标准化。
    """
    segments = []
    try:
        if isinstance(results,tuple):
            segments = results[0]

        if isinstance(results,str):
            try:
                parse = json.loads(results)
                return normalize_data(parse,query,source)
            except json.JSONDecodeError:
                logger.error(f"Failed to parse Tavily response as JSON: {results}")
                segments.append(make_segment(query, "", "", results, source))
                return segments
            
        if isinstance(results,list):
            for item in results:
                if isinstance(item,dict):
                    url = item.get("url") or item.get("link") or ""
                    title = item.get("title") or item.get("headline") or (url[:30] if url else "参考资料")
                    # content(全文/较长片段)，snippet(短摘要)
                    text = item.get("content") or item.get("snippet") or item.get("text") or ""
                    segments.append(make_segment(query, url, title, text, source,extra=item))
                else:
                    segments.append(make_segment(query, "", "", str(item), source))
            return deupdate_segment(segments)
    
        if isinstance(results,dict):
            if "error" in results:
                logger.error(f"Error in results: {results['error']}")
                return []
            url = results.get("url") or ""
            title = results.get("title") or "Untitled"
            text = results.get("content") or results.get("snippet") or json.dumps(results, ensure_ascii=False)
            segments.append(make_segment(query, url, title, text, source,extra=results))
            return segments
    
        segments.append(make_segment(query, "", "", str(results), source))
        return segments
            
    except Exception as e:
        logger.error(f"Normalization failed for query '{query}': {e}")
        return []