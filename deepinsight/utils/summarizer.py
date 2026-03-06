import logging
import time
from typing import List, Dict, Any, Optional
from difflib import SequenceMatcher
from concurrent.futures import ThreadPoolExecutor
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from deepinsight.core.llm import get_llm
from deepinsight.graph.state import DraftState
from deepinsight.prompts.prompt_demo import SUMMARIZE_PROMPT

logger = logging.getLogger(__name__)

def summarize_single_doc(doc:Dict[str,Any], model_tag: str = "basic") -> Dict[str,Any]:
    """
    对单个文档进行摘要
    """
    llm = get_llm(model_tag=model_tag)
    query = doc.get("query","通用研究")
    text = doc.get("text","")

    if len(text)<200:
        return doc

    prompt = ChatPromptTemplate.from_messages([
        ("system", '你是一个精通信息提取的助手。'),
        ("user", SUMMARIZE_PROMPT)
    ])
    chain = prompt | llm | StrOutputParser()
    
    try:
        time.sleep(0.5)  # 避免请求过快
        print(f"[摘要中]正在处理文档:{doc.get('title','无标题')[:20]}...")
        summary = chain.invoke({'query': query, 'text': text})
        new_doc = doc.copy()
        new_doc['text'] = summary
        new_doc['is_summary'] = True
        return new_doc
    except Exception as e:
        print(f"[摘要失败]: {e}")
        logger.error(f"Summarization failed for doc {e}")
        return doc
    
def map_summarize_documents(
    documents: List[Dict[str,Any]],
    max_workers: int = 2,
    model_tag: str = "basic"
) -> List[Dict[str,Any]]:
    """
    并行对文档列表进行摘要
    """
    if not documents:
        return []
    print(f"开始对 {len(documents)} 个文档进行摘要处理...")
    logger.info(f"开始对 {len(documents)} 个文档进行摘要处理...")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        summarized_docs = list(executor.map(lambda d: summarize_single_doc(d, model_tag=model_tag), documents))

    logger.info("文档摘要处理完成。")
    return summarized_docs


def find_matching_section(
        step_desc: str,
        existing_sections: Dict[str,DraftState],
        threshold:float = 0.5
    )-> Optional[DraftState]:
    """
    基于语义相似度查找可复用章节
    """
    best_match = None
    best_ratio = 0.0

    for title, section in existing_sections.items():
        ratio = SequenceMatcher(None,step_desc,title).ratio()
        if ratio >= best_ratio and ratio >= threshold:
            best_ratio = ratio
            best_match = section

    return best_match
