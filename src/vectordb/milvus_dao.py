import logging
from typing import List, Dict, Any
from pymilvus import MilvusClient
from ..embeddings.model_manager import embedding_manager

logger = logging.getLogger(__name__)

class MilvusDao:
    """
    MilvusDao - 用于与Milvus进行交互的DAO
    """
    def __init__(self, collection_name: str):
        """初始化MilvusDao"""
        self.collection_name = collection_name
        self.milvus_client = MilvusClient(uri="http://localhost:19530")
        
    def _generate_embeddings(self, texts: List[str]) -> List[float]:
        """生成文本嵌入向量"""
        return embedding_manager.generate_embeddings(texts)

    def _store_in_milvus(self, collection_name: str, schema: Any, index_params: Any, data: List[Dict[str, Any]]):
        """存储数据到Milvus"""
        collection_exists = collection_name in self.milvus_client.list_collections()
        
        # 如果集合不存在，创建集合
        if not collection_exists:
            self.milvus_client.create_collection(
                collection_name=collection_name,
                schema=schema,
                index_params=index_params
            )
            logger.info(f"创建新集合: {collection_name}")
        
        # 插入数据    
        if data and len(data) > 0:
            self.milvus_client.insert(
                collection_name=collection_name,
                data=data
            )
            logger.info(f"向集合 {collection_name} 插入 {len(data)} 条数据")
        
        # 加载集合
        try:
            self.milvus_client.load_collection(
                collection_name=collection_name
            )
            logger.info(f"成功加载集合: {collection_name}")
        except Exception as e:
            logger.error(f"加载集合失败: {str(e)}")

    def _query(self, collection_name: str, filter: str, output_fields: List[str]) -> List[Dict[str, Any]]:
        """
        Query Milvus for embeddings
        
        Args:
            collection_name: Collection name
            query: Query string
            
        Returns:
            List[Dict[str, Any]]: List of embeddings and content
        """
        if collection_name not in self.milvus_client.list_collections():
            return []
        
        results = self.milvus_client.query(
            collection_name=collection_name,
            filter=filter,
            output_fields=output_fields,
        )
        return results

    def _search(self, collection_name: str, data: List[Dict[str, Any]], filter: str = None, output_fields: List[str] = None, limit: int = 100, order_by: str = None) -> List[Dict[str, Any]]:
        """
        Search Milvus for embeddings
        
        Args:
            collection_name: Collection name
            data: List of embeddings and content
            filter: Filter string
            output_fields: List of output fields
            limit: Maximum number of results to return
            order_by: Field to order results by, format: "field_name desc/asc"
            
        Returns:
            List[Dict[str, Any]]: List of embeddings and content
        """
        if collection_name not in self.milvus_client.list_collections():
            return []
        
        search_params = {
            "collection_name": collection_name,
            "data": data,
            "limit": limit
        }
        
        # 添加可选参数
        if filter:
            search_params["filter"] = filter
            
        if output_fields:
            search_params["output_fields"] = output_fields
        
        # 添加排序参数（如果提供）
        if order_by:
            search_params["order_by"] = order_by
        
        results = self.milvus_client.search(**search_params)
        return results
