"""
向量存储模块

基于Chroma向量数据库提供文档的语义存储和检索能力。

核心类：
- VectorStore：向量存储和检索的主类

核心方法：
- add_documents()：添加文档
- similarity_search()：相似度检索
- get_by_id()：按ID获取
- clear()：清空存储
"""

import os
from typing import List, Dict, Any, Optional
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

load_dotenv()


class VectorStore:
    """
    向量存储和检索类
    
    基于Chroma向量数据库，支持：
    - 文档向量化存储
    - 相似度语义检索
    - 文档按ID获取
    - 持久化存储管理
    """
    
    def __init__(
        self, 
        collection: str = "research_docs", 
        persist_directory: str = "./chroma_data"
    ):
        """
        初始化向量存储
        
        Args:
            collection: 集合名称（用于分组存储）
            persist_directory: 持久化存储目录
        """
        self.collection = collection
        self.persist_directory = persist_directory

        # 初始化 OpenAI Embeddings
        embedding_model = os.getenv(
            "OPENAI_Embedding_MODEL", 
            "text-embedding-3-small"
        )
        embedding_api_key = os.getenv("OPENAI_API_KEY")
        embedding_api_base = os.getenv("OPENAI_API_BASE")
        
        self.embedding_model = OpenAIEmbeddings(
            model=embedding_model,
            chunk_size=1000,
            openai_api_key=embedding_api_key,
            openai_api_base=embedding_api_base
        )
        
        # 文本分割器配置
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200
        )
        
        # 初始化 Chroma 向量存储
        self.vector_store = Chroma(
            collection_name=self.collection,
            persist_directory=self.persist_directory,
            embedding_function=self.embedding_model
        )

    def _load_vector_store(self):
        """按持久化目录是否存在切换加载方式"""
        if os.path.exists(self.persist_directory) and os.listdir(self.persist_directory):
            self.vector_store = Chroma(
                persist_directory=self.persist_directory,
                embedding_function=self.embedding_model
            )
        else:
            self.vector_store = Chroma(
                embedding_function=self.embedding_model,
                persist_directory=self.persist_directory
            )

    def add_documents(self, data_list: List[Dict[str, Any]]):
        """
        添加文档到向量存储
        
        Args:
            data_list: 文档列表，每个文档包含：
                - text: 文档内容（必需）
                - title: 文档标题（可选）
                - url: 来源URL（可选）
                - id: 唯一ID（可选）
                - source: 来源标记（可选）
        """
        docs = []
        
        for item in data_list:
            if isinstance(item, Document):
                docs.append(item)
                continue
            
            # 提取元数据
            meta_data = {
                "source": item.get("source", "web"),
                "url": item.get("url", ""),
                "title": item.get("title", ""),
                "original_id": item.get("id", "")
            }
            
            # 创建Document对象
            doc = Document(
                page_content=item.get("text", ""),
                metadata=meta_data
            )
            docs.append(doc)

        if not docs:
            logger.warning("[Vector] 没有有效文档可添加到向量存储")
            return

        try:
            # 文本分割
            split_docs = self.text_splitter.split_documents(docs)
            
            if split_docs:
                # 添加到向量存储
                self.vector_store.add_documents(split_docs)
                logger.info(f"[Vector] 已添加 {len(split_docs)} 条文档到向量存储")
                print(f"[Vector] 已添加 {len(split_docs)} 条文档到向量存储")
        except Exception as e:
            logger.error(f"[Vector] 添加文档失败: {e}")

    def similarity_search(
        self, 
        query: str, 
        k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        执行相似度语义检索
        
        Args:
            query: 查询文本
            k: 返回的最大结果数，默认5
            
        Returns:
            List[Dict]: 相关文档列表，包含相关性评分
            
        Example:
            >>> results = vs.similarity_search("什么是AI", k=3)
            >>> print(results[0]["score"])  # 0.92
        """
        results = self.vector_store.similarity_search_with_score(query, k=k)
        
        formatted_results = []
        for doc, score in results:
            formatted_results.append({
                "text": doc.page_content,
                "title": doc.metadata.get("title", ""),
                "url": doc.metadata.get("url", ""),
                "id": doc.metadata.get("original_id", ""),
                "score": score
            })
        
        return formatted_results

    def get_by_id(self, original_ids: List[str]) -> List[Dict[str, Any]]:
        """
        通过原始 ID 获取文档
        
        Args:
            original_ids: 原始ID列表
            
        Returns:
            List[Dict]: 匹配的文档列表
        """
        if not original_ids:
            return []
        
        try:
            results = self.vector_store.get(
                where={"original_id": {"$in": original_ids}}
            )
            
            formatted = []
            seen_ids = set()
            
            if results['documents']:
                for doc, meta in zip(results['documents'], results['metadatas']):
                    oid = meta.get("original_id")
                    if oid and oid not in seen_ids:
                        formatted.append({
                            "text": doc,
                            "title": meta.get("title", ""),
                            "url": meta.get("url", ""),
                            "id": oid
                        })
                        seen_ids.add(oid)
            
            return formatted
            
        except Exception as e:
            logger.error(f"[Vector] 通过ID获取文档失败: {e}")
            return []

    def get_documents_by_ids(self, original_ids: List[str]) -> List[Dict[str, Any]]:
        """
        别名函数，与 get_by_id 兼容
        """
        return self.get_by_id(original_ids)

    def clear(self):
        """清空向量存储中的所有文档"""
        try:
            ids = self.vector_store.get().get('ids')
            if ids:
                self.vector_store.delete(ids)
                logger.info(f"[Vector] 已清空，共删除 {len(ids)} 条记录")
                print(f"[Vector] 已清空，共删除 {len(ids)} 条记录")
            else:
                logger.info("[Vector] 数据库为空，无需清空")
                print("[Vector] 数据库为空，无需清空")
        except Exception as e:
            logger.error(f"[Vector] 清空向量存储时出错: {e}")


# 全局实例
vector_store = VectorStore()


# 测试代码
if __name__ == "__main__":
    print("=" * 60)
    print("向量存储 Skill 演示")
    print("=" * 60)

    # 演示数据
    test_docs = [
        {
            "text": "深度学习是机器学习的一种方法，使用神经网络处理复杂数据。" * 5,
            "title": "深度学习简介",
            "url": "https://example.com/dl",
            "id": "doc_001"
        },
        {
            "text": "机器学习是人工智能的重要分支，让计算机从数据中学习。" * 5,
            "title": "机器学习基础",
            "url": "https://example.com/ml",
            "id": "doc_002"
        },
        {
            "text": "神经网络模仿生物神经的计算结构，是现代AI的基础。" * 5,
            "title": "神经网络原理",
            "url": "https://example.com/nn",
            "id": "doc_003"
        }
    ]

    try:
        print("\n[演示1] 清空并初始化向量库")
        print("-" * 60)
        vector_store.clear()
        print("✓ 向量库已清空")

        print("\n[演示2] 添加文档")
        print("-" * 60)
        vector_store.add_documents(test_docs)
        print(f"✓ 已添加 {len(test_docs)} 个文档")

        print("\n[演示3] 相似度检索")
        print("-" * 60)
        results = vector_store.similarity_search("什么是AI技术", k=2)
        for result in results:
            print(f"标题: {result['title']}")
            print(f"相关性: {result['score']:.3f}")
            print(f"内容: {result['text'][:100]}...")
            print()

        print("\n[演示4] 按ID获取")
        print("-" * 60)
        docs = vector_store.get_by_id(["doc_001", "doc_003"])
        print(f"获取了 {len(docs)} 个文档:")
        for doc in docs:
            print(f"  - {doc['title']}")

    except Exception as e:
        print(f"❌ 演示失败: {e}")

    print("\n" + "=" * 60)
    print("演示完成")
    print("=" * 60)
