import logging
from typing import List, Dict, Any
import os
from pymilvus import MilvusClient
from pymilvus.model.hybrid import BGEM3EmbeddingFunction
from huggingface_hub import snapshot_download

logger = logging.getLogger(__name__)

class MilvusDao:
    """
    MilvusDao - 用于与Milvus进行交互的DAO
    """
    def __init__(self, collection_name: str):
        """初始化MilvusDao"""
        self.collection_name = collection_name
        self.embedding_model = None

        # 禁用所有代理设置
        os.environ["HTTP_PROXY"] = ""
        os.environ["HTTPS_PROXY"] = ""
        os.environ["http_proxy"] = ""
        os.environ["https_proxy"] = ""
        os.environ["NO_PROXY"] = "*"
        
        # 配置HuggingFace缓存目录
        cache_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "local_models")
        os.makedirs(cache_dir, exist_ok=True)
        os.environ["HF_HOME"] = cache_dir
        # 设置HF_ENDPOINT环境变量为镜像站点
        os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
        # 禁用进度条以减少噪音
        os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
        
        # 初始化Milvus客户端
        self.milvus_client = MilvusClient(uri="http://localhost:19530")
        
        # 初始化时就尝试下载模型
        self._init_embedding_model()
        
    def _init_embedding_model(self):
        """初始化并下载嵌入模型"""
        try:
            # 设置模型名称和本地缓存路径
            model_name = "BAAI/bge-m3"
            cache_dir = os.environ.get("HF_HOME")
            
            logger.info(f"开始下载模型 {model_name} 到 {cache_dir}")
            
            # 尝试下载模型快照
            try:
                model_path = snapshot_download(
                    repo_id=model_name,
                    cache_dir=cache_dir,
                    local_files_only=True,
                    token=os.environ.get('HF_TOKEN')
                )
                logger.info(f"模型已下载到: {model_path}")
            except Exception as e:
                logger.warning(f"下载模型快照失败: {str(e)}")
                model_path = model_name
            
            # 初始化模型
            self.embedding_model = BGEM3EmbeddingFunction(
                model_name=model_path,
                device="cpu",
                use_fp16=False
            )
            logger.info("成功加载BGE-M3模型")
        except Exception as e:
            logger.error(f"初始化嵌入模型失败: {str(e)}")
            self.embedding_model = None

    def _generate_embeddings(self, texts: List[str]) -> List[float]:
        """生成文本嵌入向量"""
        if self.embedding_model is None:
            self._init_embedding_model()
        
        try:
            if not texts:
                return [0.0] * 1024
            
            docs_embeddings = self.embedding_model._encode(texts)
            return docs_embeddings['dense']
        except Exception as e:
            logger.error(f"生成嵌入向量失败: {str(e)}")
            return [0.0] * 1024

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

    def _search(self, collection_name: str, data: List[Dict[str, Any]], filter: str, output_fields: List[str], limit: int = 100) -> List[Dict[str, Any]]:
        """
        Search Milvus for embeddings
        
        Args:
            collection_name: Collection name
            data: List of embeddings and content
            filter: Filter string
            output_fields: List of output fields
            
        Returns:
            List[Dict[str, Any]]: List of embeddings and content
        """
        if collection_name not in self.milvus_client.list_collections():
            return []
        
        results = self.milvus_client.search(
            collection_name=collection_name,
            data=data,
            filter=filter,
            output_fields=output_fields,
            limit=limit
        )
        return results
