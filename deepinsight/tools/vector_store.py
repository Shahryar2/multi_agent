import os
from typing import List, Dict, Any
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

load_dotenv()

class VectorStore:
    def __init__(self, collection: str = "research_docs", persist_directory: str = "./chroma_data"):
        self.collection = collection
        self.persist_directory = persist_directory

        embedding_model = os.getenv("Embedding_model", "text-embedding-3-small")
        embedding_api_key = os.getenv("Embedding_API_KEY")
        embedding_api_base = os.getenv("Embedding_API_BASE")
        self.embedding_model = OpenAIEmbeddings(
            model=embedding_model, 
            chunk_size=1000,
            openai_api_key=embedding_api_key,
            openai_api_base=embedding_api_base
        )
        # 文本分割器
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000, 
            chunk_overlap=200
        )
        self.vector_store = Chroma(
            collection_name=self.collection,
            persist_directory=self.persist_directory,
            embedding_function=self.embedding_model
        )

    def _load_vector_store(self):
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
        """添加文档到向量存储"""
        docs = []
        for item in data_list:
            if isinstance(item, Document):
                docs.append(item)
                continue
            meta_data = {
                "source": item.get("source", "web"),
                "url": item.get("url", ""),
                "title": item.get("title", ""),
                "original_id": item.get("id", "")
            }
            doc = Document(
                page_content=item.get("text", ""),
                metadata=meta_data
            )
            docs.append(doc)

        if not docs:
            logger.warning("[Vector]没有有效文档可添加到向量存储")
            return
        try:
            split_docs = self.text_splitter.split_documents(docs)
            if split_docs:
                self.vector_store.add_documents(split_docs)
                print(f"[Vector]已添加 {len(split_docs)} 条文档到向量存储")
        except Exception as e:
            logger.error(f"[Vector]添加文档失败: {e}")

    def similarity_search(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        """语义检索"""
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
    
    def clear(self):
        """清空向量存储"""
        try:
            ids = self.vector_store.get().get('ids')
            if ids:
                self.vector_store.delete(ids)
                logger.info(f"[Vector]已清空，共删除 {len(ids)} 条记录")
            else:
                logger.info("[Vector]数据库为空，无需清空")
        except Exception as e:
            logger.error(f"[Vector]清空向量存储时出错: {e}")

vector_store = VectorStore()

# ...existing code...

if __name__ == "__main__":
    try:
        # 1. 打印配置信息 (脱敏)
        vs = VectorStore()
        api_key = os.getenv("Embedding_API_KEY", "")
        masked_key = api_key[:8] + "****" + api_key[-4:] if api_key else "未配置"
        print(f"API Base: {os.getenv('Embedding_API_BASE')}")
        print(f"Model: {os.getenv('Embedding_model')}")
        print(f"API Key: {masked_key}")

        # 2. 测试 Embedding 生成
        test_text = "这是一个测试句子，用于验证向量接口是否通畅。"
        print(f"\n正在尝试 Embed 文本: '{test_text}' ...")
        
        # 直接调用底层 embedding 方法
        embedding = vs.embedding_model.embed_query(test_text)
        
        print(f"✅ 连接成功！")
        print(f"生成的向量维度: {len(embedding)}")
        print(f"向量前5位: {embedding[:5]}")

        # 3. 测试 Chroma 写入与检索
        print("\n正在测试 ChromaDB 写入与检索...")
        test_doc = Document(page_content=test_text, metadata={"source": "test"})
        vs.vector_store.add_documents([test_doc])
        print("写入成功。正在检索...")
        
        results = vs.similarity_search("测试验证", k=1)
        if results:
            print(f"✅ 检索成功！命中内容: {results[0]['text']}")
        else:
            print("❌ 检索返回为空")

    except Exception as e:
        print(f"\n❌ 连接失败！错误详情:")
        print(e)
        print("\n建议检查：")
        print("1. Embedding_API_KEY 是否过期或余额不足")
        print("2. Embedding_API_BASE 是否正确 (有些中转商需要加 /v1，有些不需要)")
        print("3. 网络是否能访问该 API 地址")