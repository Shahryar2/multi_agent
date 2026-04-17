import hashlib
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
    

def remap_citations(text:str, old_citations: List[Dict],new_citations: List[Dict]) -> str:
    """
    重审更新引用列表
    """
    if not text or not old_citations or not new_citations:
        return text
    
    id_to_new_index = {
        c['id']: c['index'] 
        for c in new_citations 
        if 'id' in c
    }
    old_index_to_id = {
        c['index']: c['id'] 
        for c in old_citations
        if 'id' in c
    }
    def replace_match(match):
        old_index = int(match.group(1))
        if old_index in old_index_to_id:
            doc_id = old_index_to_id[old_index]
            if doc_id in id_to_new_index:
                return f"[{id_to_new_index[doc_id]}]"
        return match.group(0)
    
    return re.sub(r'\[(\d+)\]', replace_match, text)

def smart_truncate_draft(draft: str, max_length: int = 15000) -> str:
    """
    智能截断长文(保护引用列表)
    """
    if len(draft) <= max_length:
        return draft
    
    citation_marker = '## 引用列表'
    parts = draft.split(citation_marker)
    if len(parts) < 2:
        return draft[:max_length] + "\n...(truncated)..."
    
    body = parts[0]
    citations = citation_marker + parts[1]
    if len(citations) >= max_length * 0.5:
        return draft[:max_length]
    
    available_length = max_length - len(citations) - 100
    if available_length <= 0:
        return draft[:max_length]
    
    truncated_body = body[:available_length]
    last_newline = truncated_body.rfind('\n\n')
    if last_newline != -1:
        truncated_body = truncated_body[:last_newline]

    return f"{truncated_body}\n\n...(中间内容已省略以适应Token限制)...\n\n{citations}"

def smart_truncate(text: str, max_length: int, add_ellipsis: bool = True) -> str:
    """
    智能截断文本：
    1. 限制最大长度
    2. 尽量在句子结束符（。！？. ! ?）处截断，避免切断语义
    3. 如果找不到合适的句子结束符，则在最后退化为硬截断
    """
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    
    # 初步硬截断
    truncated = text[:max_length]
    
    # 寻找最后一个句子结束符的位置
    last_end = max(
        truncated.rfind('。'),
        truncated.rfind('！'),
        truncated.rfind('？'),
        truncated.rfind('.'),
        truncated.rfind('!'),
        truncated.rfind('?')
    )
    
    # 如果结束符在文本的后半部分（保留了足够多的信息），则在此截断
    if last_end > max_length * 0.5:
        return truncated[:last_end + 1]
    
    # 否则，退而求其次寻找逗号或换行
    last_comma = max(
        truncated.rfind('，'),
        truncated.rfind(','),
        truncated.rfind('\n')
    )
    
    if last_comma > max_length * 0.7:
        result = truncated[:last_comma]
    else:
        result = truncated.rstrip()
        
    return result + ("..." if add_ellipsis else "")


class ContentCompressor:
    """
    轻量级内容压缩器
    """
    NOTISE_PATTERNS = [
        r'点击.*?查看.*?更多',
        r'关注.*?获取.*?最新',
        r'(扫码|扫描).*?(关注|下载)',
        r'版权所有.*?保留.*?权利',
        r'Copyright.*?All Rights Reserved',
        r'本文(来源|转载|作者)[:：].*?(?=\n|$)',
        r'(阅读|浏览).*?\d+.*?(次|人)',
        r'(分享|收藏|点赞).*?(?=\s|$)',
        r'广告|推广|赞助',
        r'免责声明.*?(?=\n|$)',
        r'\[.*?(图片|视频|广告).*?\]',
    ]

    VALUE_SIGNALS = [
        # 数据类
        r'\d+%', r'\d+亿', r'\d+万', r'¥\d+', r'\$\d+',
        # 结论类
        r'总结|结论|建议|推荐|注意|重要|关键|核心',
        # 因果类
        r'因为|所以|导致|原因|结果|影响',
        # 对比类
        r'相比|对比|优于|不如|区别|差异',
        # 时间类
        r'最新|最近|目前|预计|未来',
    ]
    def __init__(
            self,
            max_content_length: int = 500,
            min_content_length: int = 30,
            min_score_threshold: float = 0.0,
            remove_duplicates: bool = True
        ):
        """
        Args:
            max_content_length (int): 最大内容长度，超过则压缩
            min_content_length (int): 最小内容长度，低于则丢弃
            min_score_threshold (float): 最小评分阈值，低于则丢弃
            remove_duplicates (bool): 是否去重
        """
        self.max_content_length = max_content_length
        self.min_content_length = min_content_length
        self.min_score_threshold = min_score_threshold
        self.remove_duplicates = remove_duplicates
        
        self._noise_regex = [re.compile(p,re.IGNORECASE) for p in self.NOTISE_PATTERNS]
        self._value_regex = [re.compile(p) for p in self.VALUE_SIGNALS]

    def compress(self, segments: List[Dict[str,Any]]) -> List[Dict[str,Any]]:
        """
        压缩文档列表的主入口

        处理流程：
        1. 深度清洗(移除噪音)
        2. 去重
        3. 质量评分
        4. 按分数排序
        5. 智能截断
        """
        if not segments:
            return []
        
        original_count = len(segments)

        # 深度清洗
        segments = [self._deep_clean(seg) for seg in segments]
        # 过滤过短内容
        segments = [
            s for s in segments
            if len(s.get("text", "") or s.get("content", "")) >= self.min_content_length
        ]
        # 去重
        if self.remove_duplicates:
            segments = self._advanced_deduplicate(segments)
        # 质量评分
        segments = [self._score_segment(seg) for seg in segments]
        # 分数过滤
        if self.min_score_threshold > 0:
            segments = [
                s for s in segments
                if s.get("quality_score",0) >= self.min_score_threshold
            ]
        # 按分数排序
        segments.sort(key=lambda x: x.get("quality_score",0), reverse=True)
        # 智能截断
        for seg in segments:
            original_text = seg.get("text","") or seg.get("content","")
            seg["text"] = smart_truncate(original_text, self.max_content_length)
            if "content" in seg:
                seg["content"] = seg["text"]
        logger.info(
            f"[Compressor] {original_count} -> {len(segments)} 条，压缩率 {(1 - len(segments)/max(original_count,1))*100:.1f}%"
        )

        return segments

    
    def _deep_clean(self, segment: Dict[str,Any]) -> Dict[str,Any]:
        """深度清洗，移除噪音内容"""
        segment = segment.copy()
        text = segment.get("text","") or segment.get("content","")
        # 简单清洗
        text = clean_text(text)
        
        # 移除噪音
        for pattern in self._noise_regex:
            text = pattern.sub("", text)
        
        # 清理多余空白
        text = re.sub(r'\s+', ' ', text).strip()
        segment["text"] = text
        if "content" in segment:
            segment["content"] = text

        return segment
    

    def _advanced_deduplicate(self, segments: List[Dict[str,Any]]) -> List[Dict[str,Any]]:
        """
        高级去重:基于内容指纹
        """
        seen_fingerprints = set()
        seen_urls = set()
        unique = []
        
        for seg in segments:
            url = seg.get("url","")
            text = seg.get("text","") or seg.get("content","")

            if url and url in seen_urls:
                continue

            fingerprint = self._get_fingerprint(text)
            if fingerprint in seen_fingerprints:
                continue
            seen_fingerprints.add(fingerprint)
            if url:
                seen_urls.add(url)
            unique.append(seg)

        return unique

    def _get_fingerprint(self, text: str) -> str:
        """
        简单内容指纹生成
        """
        noramlized = re.sub(r'\s+', '', text[:300].lower())
        return hashlib.md5(noramlized.encode()).hexdigest()[:16]
    

    def _score_segment(self, segment: Dict[str,Any]) -> Dict[str,Any]:
        """
        简单质量评分
        """
        segment = segment.copy()
        text = segment.get("text","") or segment.get("content","")

        if not text:
            segment["quality_score"] = 0.0
            return segment
        
        score = 0.5
        # 长度分
        length = len(text)
        if 100 <= length <= 800:
            score += 0.15
        elif length > 800:
            score += 0.1
        elif length < 50:
            score -= 0.2
        # 价值信号分
        value_matches = sum(
            1 for pattern in self._value_regex 
            if pattern.search(text)
        )
        score += min(value_matches * 0.05, 0.2)
        
        # 数据密度分
        digits = len(re.findall(r'\d', text))
        digit_radio = digits / (max(len(text),1))
        if 0.02 <digit_radio <= 0.15:
            score += 0.1

        # 结构分
        punctuation = len(re.findall(r'[，。！？；,.!?;]', text))
        if punctuation >= 3:
            score += 0.05

        # 原始分数
        original_score = segment.get("score", 0)
        if original_score > 0:
            score = score * 0.7 + original_score * 0.3
        segment["quality_score"] = min(max(score, 0), 1)

        return segment
    
    

class CitationSelector:
    """
    引用选择器
    根据章节主题智能选择最相关的引用
    """
    def __init__(
            self,
            max_citations: int = 3,
            max_snippet_length: int = 150
        ):
        self.max_citations = max_citations
        self.max_snippet_length = max_snippet_length
        
    def select_for_section(
            self,
            citations: List[Dict[str,Any]],
            section_topic: str,
            section_result: str = "",
            priority_ids: List[str] = None,
        ) -> List[Dict[str,Any]]:
        """
        为章节选择最相关的引用。

        优先级策略：
        - priority_ids 内的文献（研究员专门为该步骤搜到的）优先入选
        - 剩余名额再从非优先文献里按相关性补充
        这保证每个章节优先引用自己的研究成果，同时不同章节的引用自然分散
        """
        if not citations:
            return []
        
        priority_ids_set = set(priority_ids or [])

        # 提取关键词
        topic_keywords = self._extract_keywords(section_topic + " " + section_result)
        
        priority_group = []
        non_priority_group = []
        
        for citation in citations:
            c = citation.copy()
            title = c.get("title","")
            snippet = c.get("snippet",c.get("text",""))[:500]
            citation_keywords = self._extract_keywords(title + " " + snippet)

            overlap = len(topic_keywords & citation_keywords)
            relevance = overlap / max(len(citation_keywords),1)
            original_score = c.get("quality_score", c.get("score", 0.5))
            c["relevance_score"] = relevance * 0.6 + original_score * 0.4

            if c.get("id") in priority_ids_set:
                priority_group.append(c)
            else:
                non_priority_group.append(c)

        # 两组内各自按相关性排序
        priority_group.sort(key=lambda x: x.get("relevance_score",0), reverse=True)
        non_priority_group.sort(key=lambda x: x.get("relevance_score",0), reverse=True)

        # 优先组底大占 max_citations 的 2/3（至少保留一个内容）
        max_priority = max(1, self.max_citations * 2 // 3)
        selected_priority = priority_group[:max_priority]
        remaining_slots = self.max_citations - len(selected_priority)
        selected = selected_priority + non_priority_group[:remaining_slots]

        for c in selected:
            snippet = c.get("snippet",c.get("text",""))
            if len(snippet) > self.max_snippet_length:
                c["snippet"] = smart_truncate(snippet, self.max_snippet_length)

        return selected


    def _extract_keywords(self, text: str) -> List[str]:
        """
        简单关键词提取
        """
        if not text:
            return set()
        # 移除特殊字符
        text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9\s]', '', text)
        keywords = set()
        words = text.lower().split()
        # 英文单词
        keywords.update(
            w for w in words if len(w) >= 3
        )
        chinese = ''.join(re.findall(r'[\u4e00-\u9fa5]+', text))
        for i in range(len(chinese)-1):
            keywords.add(chinese[i:i+2])

        return keywords

    
    def format_citations_text(self, citations: List[Dict[str,Any]]) -> str:
        """
        格式化引用文本列表为字符串（含全局编号，供LLM在写作时知道该引用哪个数字）
        """
        if not citations:
            return "无可用参考资料"
        
        lines = []
        for c in citations:
            index = c.get("index", "?")
            title = c.get("title","无标题")
            url = c.get("url","")
            snippet = c.get("snippet",c.get("text",""))[:self.max_snippet_length]
            lines.append(f"[{index}] {title} ({url}): {snippet}")
        
        return "\n".join(lines)

def compress_search_results(
    results: List[Dict[str,Any]],
    max_per_item: int = 500,
    min_length: int = 30,
    min_score: float = 0.0
) -> List[Dict[str,Any]]:
    """
    压缩搜索结果便捷函数

    Args:
        results: 原始搜索结果列表
        max_per_item: 每条结果的最大内容长度
        min_length: 最小内容长度，低于则丢弃
        min_score: 最小质量分数，低于则丢弃

    Returns:
        List[Dict[str,Any]]: 压缩后的搜索结果列表
    """
    compressor = ContentCompressor(
        max_content_length=max_per_item,
        min_content_length=min_length,
        min_score_threshold=min_score,
    )
    return compressor.compress(results)

def select_citations_for_section(
    citations: List[Dict[str,Any]],
    section_topic: str,
    section_result: str = "",
    max_citations: int = 3,
    max_snippet_length: int = 150,
    priority_ids: List[str] = None,
) -> str:
    """
    为章节选择引用便捷函数

    Args:
        citations: 原始引用列表
        section_topic: 章节主题
        section_result: 章节结果摘要
        max_citations: 最大引用数量
        max_snippet_length: 引用摘要最大长度
        priority_ids: 研究员为该步骤专门搜到的文档ID列表，这些ID对应的引用优先入选

    Returns:
        str: 格式化后的引用文本
    """
    selector = CitationSelector(
        max_citations=max_citations,
        max_snippet_length=max_snippet_length
    )
    selected = selector.select_for_section(citations, section_topic, section_result, priority_ids=priority_ids)
    return selector.format_citations_text(selected)

# 全局实例
default_compressor = ContentCompressor(
    max_content_length=500,
    min_content_length=30,
    min_score_threshold=0.0,
)
default_selector = CitationSelector(
    max_citations=3,
    max_snippet_length=150
)