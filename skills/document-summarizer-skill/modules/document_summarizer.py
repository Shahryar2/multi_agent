"""
文档摘要模块

提供单个文档摘要和批量文档摘要功能，采用LLM进行智能浓缩。

核心函数：
- summarize_single_doc()：单个文档摘要
- map_summarize_documents()：批量并行摘要

特点：
- 智能长度检测（短文本直接保留）
- 并行处理优化
- 详细的错误处理和日志记录
"""

import logging
import time
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# 这里假设llm_factory和prompt_demo来自相应的Skills
# 实际集成时需要调整导入路径
try:
    from deepinsight.core.llm import get_llm
    from deepinsight.prompts.prompt_demo import SUMMARIZE_PROMPT
except ImportError:
    # 如果Skills已独立，可这样导入
    from skills.llm_factory_skill.modules.llm_factory import get_llm
    SUMMARIZE_PROMPT = """请对以下文本进行简洁的摘要，保留核心信息。\n内容：{text}"""

logger = logging.getLogger(__name__)


def summarize_single_doc(
    doc: Dict[str, Any], 
    model_tag: str = "basic"
) -> Dict[str, Any]:
    """
    对单个文档进行摘要
    
    Args:
        doc: 包含以下字段的文档字典：
            - text: 文档内容（必需）
            - query: 查询上下文（可选）
            - title: 文档标题（可选）
            - url: 文档来源URL（可选）
        model_tag: 使用的LLM模型标签
        
    Returns:
        Dict[str, Any]: 摘要后的文档，包含 is_summary 标记
        
    Example:
        >>> doc = {
        ...     "text": "长篇文章内容...",
        ...     "title": "原标题",
        ...     "query": "查询"
        ... }
        >>> summary = summarize_single_doc(doc)
        >>> print(summary["is_summary"])  # True
    """
    llm = get_llm(model_tag=model_tag)
    query = doc.get("query", "通用研究")
    text = doc.get("text", "")

    # 短文本直接保留，不进行摘要
    if len(text) < 200:
        result = doc.copy()
        result["is_summary"] = False
        return result

    # 构建摘要提示
    prompt = ChatPromptTemplate.from_messages([
        ("system", "你是一个精通信息提取的助手。"),
        ("user", SUMMARIZE_PROMPT)
    ])
    
    chain = prompt | llm | StrOutputParser()

    try:
        time.sleep(0.5)  # 避免请求过快
        title = doc.get("title", "无标题")[:20]
        logger.info(f"[摘要中] 正在处理文档: {title}...")
        print(f"[摘要中] 正在处理文档: {title}...")
        
        # 执行摘要
        summary = chain.invoke({"query": query, "text": text})
        
        # 返回摘要结果
        result = doc.copy()
        result["text"] = summary
        result["is_summary"] = True
        
        return result
        
    except Exception as e:
        logger.error(f"[摘要失败]: {e}")
        print(f"[摘要失败]: {e}")
        
        # 摘要失败时保留原文
        result = doc.copy()
        result["is_summary"] = False
        return result


def map_summarize_documents(
    documents: List[Dict[str, Any]],
    max_workers: int = 2,
    model_tag: str = "basic"
) -> List[Dict[str, Any]]:
    """
    并行对文档列表进行摘要
    
    使用线程池并行处理多个文档，在不阻塞主线程的情况下提高吞吐量。
    
    Args:
        documents: 文档列表
        max_workers: 并发线程数，默认2个
        model_tag: 使用的LLM模型标签，默认"basic"
        
    Returns:
        List[Dict[str, Any]]: 摘要后的文档列表
        
    Example:
        >>> docs = [
        ...     {"text": "长文本1...", "title": "标题1"},
        ...     {"text": "长文本2...", "title": "标题2"},
        ... ]
        >>> summaries = map_summarize_documents(docs, max_workers=2)
        >>> print(len(summaries))  # 2
    """
    if not documents:
        return []

    logger.info(f"开始对 {len(documents)} 个文档进行摘要处理...")
    print(f"开始对 {len(documents)} 个文档进行摘要处理...")

    # 使用线程池并行处理
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 为每个文档提交摘要任务
        futures = [
            executor.submit(summarize_single_doc, doc, model_tag=model_tag)
            for doc in documents
        ]
        
        # 等待所有任务完成并收集结果
        summarized_docs = [future.result() for future in futures]

    logger.info("文档摘要处理完成。")
    print("文档摘要处理完成。")
    
    return summarized_docs


# 测试代码
if __name__ == "__main__":
    print("=" * 60)
    print("文档摘要 Skill 演示")
    print("=" * 60)

    # 演示数据
    test_docs = [
        {
            "text": "这是一篇关于人工智能发展的长文章。" * 50,
            "title": "AI发展趋势",
            "url": "https://example.com/ai",
            "query": "AI应用"
        },
        {
            "text": "这是一篇关于机器学习的文章。" * 50,
            "title": "机器学习基础",
            "url": "https://example.com/ml",
            "query": "ML算法"
        },
        {
            "text": "这是一篇很短的文章。",  # 应该不被摘要
            "title": "短文章",
            "url": "https://example.com/short"
        }
    ]

    print("\n[演示1] 单个文档摘要")
    print("-" * 60)
    
    try:
        single_summary = summarize_single_doc(test_docs[0])
        print(f"原文长度: {len(test_docs[0]['text'])} 字")
        print(f"摘要长度: {len(single_summary['text'])} 字")
        print(f"摘要状态: {'已摘要' if single_summary.get('is_summary') else '未摘要'}")
    except Exception as e:
        print(f"演示失败: {e}")

    print("\n[演示2] 批量并行摘要")
    print("-" * 60)
    
    try:
        batch_summaries = map_summarize_documents(test_docs, max_workers=2)
        for i, doc in enumerate(batch_summaries):
            print(f"文档 {i+1}: {doc['title']}")
            print(f"  是否摘要: {doc.get('is_summary', False)}")
            print(f"  长度: {len(doc['text'])} 字")
    except Exception as e:
        print(f"演示失败: {e}")

    print("\n" + "=" * 60)
    print("演示完成")
    print("=" * 60)
