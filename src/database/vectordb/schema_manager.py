"""
Milvus 数据库 Schema 管理模块
负责集中管理所有 Milvus 集合的 schema 和索引参数
"""
import logging
import re
from typing import Tuple, Dict, Any
from pymilvus import MilvusClient, DataType

logger = logging.getLogger(__name__)

class MilvusSchemaManager:
    """Milvus Schema 管理器"""
    
    @staticmethod
    def get_deepresearch_schema():
        """
        获取深度研究集合的 schema 定义，支持不同场景
        
        Args:
            scenario: 场景名称，如 'ai' 等
            
        Returns:
            tuple: (schema, index_params) - schema 和索引参数
        """
        try:
            # 创建模式
            schema = MilvusClient.create_schema(
                auto_id=False,
                enable_dynamic_field=True,
            )
            schema.add_field("id", DataType.VARCHAR, is_primary=True, max_length=36)
            schema.add_field("url", DataType.VARCHAR, max_length=500)
            schema.add_field("title", DataType.VARCHAR, max_length=500)
            schema.add_field("content", DataType.VARCHAR, max_length=65535)
            schema.add_field("create_time", DataType.INT64)
            schema.add_field("content_emb", DataType.FLOAT_VECTOR, dim=1024)
            
            # 创建索引参数
            index_params = MilvusClient.prepare_index_params()
            index_params.add_index(
                field_name="content_emb", 
                index_type="HNSW",
                index_name="idx_content_emb",
                metric_type="COSINE",
                params={"M": 8, "efConstruction": 200}
            )
            return schema, index_params
        except Exception as e:
            logger.error(f"创建深度研究集合 schema 失败: {str(e)}")
            raise e
