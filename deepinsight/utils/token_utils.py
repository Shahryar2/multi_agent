import os
import tiktoken
import logging
from core.llm import get_llm
import json
from typing import Any, Dict, List, TypedDict

logger = logging.getLogger(__name__)

def get_encoding(model_tag: str | None = None):
    """
    获取模型对应的编码器
    """
    if model_tag == "smart":
        model_name = os.getenv("Gemini_model", "gpt-3.5-turbo")
    elif model_tag == "basic":
        model_name = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
    else:
        model_name = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")

    try:
        return tiktoken.encoding_for_model(model_name) if model_name else tiktoken.get_encoding("cl100k_base")
    except KeyError:
        logger.warning(f"模型 {model_name} 未知，使用默认编码器 cl100k_base")
        return tiktoken.get_encoding("cl100k_base")
    
def count_tokens(text: str, model_tag: str | None = None) -> int:
    """
    计算文本的 token 数量
    """
    if not text:
        return 0
    enc = get_encoding(model_tag)
    return len(enc.encode(text))

def ensure_content_string(content: Any) -> str:
    """
    清洗内容
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content,(list,dict)):
       return json.dumps(content,ensure_ascii=False)
    return str(content) 

def term_document(
    documents: List[Dict[str, Any]],
    max_tokens: int = 20000,
    max_tokens_per_doc: int = 1000,
    model_tag: str | None = None
) -> List[Dict[str, Any]]:
    """
    截断文档
    """
    enc = get_encoding(model_tag)
    trimmed_docs: List[Dict[str, Any]] = []
    current_tokens = 0

    for doc in documents:
        if isinstance(doc,dict):
            raw_text = doc.get("text", doc.get("page_content",""))
            doc_dict = doc.copy()
        else:
            raw_text = getattr(doc, "page_content", "")
            metadata = getattr(doc, "metadata", {})
            doc_dict = {
                "text": raw_text, 
                "title": metadata.get("title", ""),
                "url": metadata.get("source", ""),
                "id": metadata.get("source", ""),
                "type": metadata.get("type", ""),
            }

        text = ensure_content_string(raw_text)
        tokens = enc.encode(text)
        if len(tokens) > max_tokens_per_doc:
            tokens = tokens[:max_tokens_per_doc]
            text = enc.decode(tokens) + "...(truncated)"
        doc_token_count = len(tokens)

        if current_tokens + doc_token_count > max_tokens:
            logger.info(f"文档总 Token 已达上限 ({current_tokens} + {doc_token_count} > {max_tokens})，停止加载更多文档。")
            break

        doc_dict["text"] = text
        trimmed_docs.append(doc_dict)
        current_tokens += doc_token_count
    logger.info(f"完成，保留{len(trimmed_docs)}/{len(documents)}篇，总 Token 数：{current_tokens}")
    return trimmed_docs
