import logging
import time
from typing import List, Dict, Any, Union, Optional, Callable

from pymilvus import MilvusClient

logger = logging.getLogger(__name__)

class MilvusDao:
    """
    MilvusDao - 通用的Milvus向量数据库交互工具类
    
    提供了与Milvus数据库的基础交互功能，包括：
    - 连接管理和重连机制
    - 集合的创建和管理
    - 数据插入和查询
    - 向量搜索
    
    示例用法:
    ```python
    # 创建 MilvusDao 实例
    milvus_dao = MilvusDao(
        uri="http://localhost:19530",
        user="",
        password="",
        db_name="default"
    )
    
    # 定义集合架构
    schema = {
        "fields": [
            {"name": "id", "type": "VARCHAR", "is_primary": True, "max_length": 100},
            {"name": "content", "type": "VARCHAR", "max_length": 65535},
            {"name": "content_emb", "type": "FLOAT_VECTOR", "dim": 768}
        ]
    }
    
    # 定义索引参数
    index_params = {
        "index_type": "IVF_FLAT",
        "metric_type": "L2",
        "params": {"nlist": 1024}
    }
    
    # 存储数据
    data = [
        {"id": "1", "content": "示例内容1", "content_emb": [0.1, 0.2, ..., 0.768]},
        {"id": "2", "content": "示例内容2", "content_emb": [0.2, 0.3, ..., 0.768]}
    ]
    milvus_dao.store(collection_name="my_collection", schema=schema, 
                    index_params=index_params, data=data)
    
    # 搜索数据
    search_data = [{"content_emb": [0.1, 0.2, ..., 0.768]}]
    results = milvus_dao.search(collection_name="my_collection", 
                               data=search_data, 
                               output_fields=["id", "content"])
    ```
    """
    
    def __init__(self, 
                 uri: str = "http://localhost:19530", 
                 user: str = "", 
                 password: str = "", 
                 db_name: str = "default",
                 token: str = None,
                 reconnect_attempts: int = 3,
                 reconnect_delay: int = 2,
                 embedding_generator: Optional[Callable[[List[str]], List[List[float]]]] = None):
        """
        初始化MilvusDao
        
        Args:
            uri: Milvus服务器URI，默认为"http://localhost:19530"
            user: Milvus用户名，默认为空
            password: Milvus密码，默认为空
            db_name: 数据库名称，默认为"default"
            token: 访问令牌，默认为None
            reconnect_attempts: 重连尝试次数，默认为3
            reconnect_delay: 重连延迟(秒)，默认为2
            embedding_generator: 可选的嵌入向量生成器函数，接收文本列表并返回嵌入向量列表
        """
        self.uri = uri
        self.user = user
        self.password = password
        self.db_name = db_name
        self.token = token
        self.milvus_client = None
        self.reconnect_attempts = reconnect_attempts
        self.reconnect_delay = reconnect_delay
        self.embedding_generator = embedding_generator
        
        # 初始化客户端
        self._init_client()
        
    def _init_client(self) -> bool:
        """
        初始化Milvus客户端，添加重试机制
        
        Returns:
            bool: 连接是否成功
        """
        for attempt in range(self.reconnect_attempts):
            try:
                self.milvus_client = MilvusClient(
                    uri=self.uri,
                    user=self.user,
                    password=self.password,
                    db_name=self.db_name,
                    token=self.token
                )
                # 尝试执行一个简单操作验证连接
                self.milvus_client.list_collections()
                logger.info(f"成功连接到Milvus服务: {self.uri}")
                return True
            except Exception as e:
                if attempt < self.reconnect_attempts - 1:
                    logger.warning(f"连接Milvus服务失败 (尝试 {attempt+1}/{self.reconnect_attempts}): {str(e)}，{self.reconnect_delay}秒后重试")
                    time.sleep(self.reconnect_delay)
                else:
                    logger.error(f"连接Milvus服务失败，已达最大重试次数: {str(e)}")
        return False
                    
    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        生成文本嵌入向量
        
        Args:
            texts: 文本列表
            
        Returns:
            List[List[float]]: 嵌入向量列表
            
        Raises:
            ValueError: 如果未提供embedding_generator且无法找到默认生成器
        """
        if not texts:
            logger.warning("提供的文本列表为空")
            return []
            
        if self.embedding_generator:
            return self.embedding_generator(texts)
        else:
            # 尝试导入项目中的embedding_manager作为后备
            try:
                from ..embeddings.model_manager import embedding_manager
                return embedding_manager.generate_embeddings(texts)
            except ImportError:
                raise ValueError("未提供embedding_generator且无法导入默认的embedding_manager")

    def collection_exists(self, collection_name: str) -> bool:
        """
        检查集合是否存在
        
        Args:
            collection_name: 集合名称
            
        Returns:
            bool: 集合是否存在
        """
        if not self.milvus_client:
            if not self._init_client():
                return False
        
        try:
            return collection_name in self.milvus_client.list_collections()
        except Exception as e:
            logger.error(f"检查集合存在性失败: {str(e)}")
            # 尝试重新连接
            if self._init_client():
                try:
                    return collection_name in self.milvus_client.list_collections()
                except Exception as e:
                    logger.error(f"重新连接后检查集合存在性仍然失败: {str(e)}")
            return False
    
    def create_collection(self, collection_name: str, schema: Dict, index_params: Dict) -> bool:
        """
        创建集合
        
        Args:
            collection_name: 集合名称
            schema: 集合架构
            index_params: 索引参数
            
        Returns:
            bool: 创建是否成功
        """
        if not self.milvus_client:
            if not self._init_client():
                return False
        
        if self.collection_exists(collection_name):
            logger.info(f"集合 {collection_name} 已存在")
            return True
            
        try:
            self.milvus_client.create_collection(
                collection_name=collection_name,
                schema=schema,
                index_params=index_params
            )
            logger.info(f"创建新集合: {collection_name}")
            return True
        except Exception as e:
            logger.error(f"创建集合失败: {str(e)}")
            return False
            
    def drop_collection(self, collection_name: str) -> bool:
        """
        删除集合
        
        Args:
            collection_name: 集合名称
            
        Returns:
            bool: 删除是否成功
        """
        if not self.milvus_client:
            if not self._init_client():
                return False
                
        if not self.collection_exists(collection_name):
            logger.info(f"集合 {collection_name} 不存在")
            return True
            
        try:
            self.milvus_client.drop_collection(collection_name)
            logger.info(f"成功删除集合: {collection_name}")
            return True
        except Exception as e:
            logger.error(f"删除集合失败: {str(e)}")
            return False

    def store(self, collection_name: str, schema: Dict, index_params: Dict, 
             data: List[Dict[str, Any]], validate_fn: Optional[Callable[[Dict], bool]] = None) -> bool:
        """
        存储数据到Milvus
        
        Args:
            collection_name: 集合名称
            schema: 集合架构，创建集合时使用
            index_params: 索引参数，创建集合时使用
            data: 待存储的数据列表
            validate_fn: 可选的数据验证函数，接收数据项并返回是否有效
            
        Returns:
            bool: 存储是否成功
        """
        if not data or len(data) == 0:
            logger.warning("无数据可写入Milvus")
            return False
        
        # 检查客户端连接状态
        if not self.milvus_client:
            logger.warning("Milvus客户端未初始化，尝试重新连接")
            if not self._init_client():
                logger.error("无法连接到Milvus服务，无法写入数据")
                return False
                
        # 确保集合存在
        if not self.collection_exists(collection_name):
            if not self.create_collection(collection_name, schema, index_params):
                return False
        
        # 验证数据
        validated_data = []
        if validate_fn:
            # 使用提供的验证函数
            for item in data:
                if validate_fn(item):
                    validated_data.append(item)
                else:
                    logger.warning(f"数据验证失败，跳过: {item}")
        else:
            # 使用默认验证：确保所有字段都存在
            required_fields = [field["name"] for field in schema["fields"]]
            for item in data:
                if all(field in item for field in required_fields):
                    validated_data.append(item)
                else:
                    missing = [field for field in required_fields if field not in item]
                    logger.warning(f"数据缺少必要字段 {missing}，跳过")
        
        if not validated_data:
            logger.warning("所有数据验证失败，无数据可写入")
            return False
        
        # 插入数据，添加重试机制
        for attempt in range(self.reconnect_attempts):
            try:
                # 插入数据    
                self.milvus_client.insert(
                    collection_name=collection_name,
                    data=validated_data
                )
                logger.info(f"向集合 {collection_name} 插入 {len(validated_data)} 条数据")
                
                # 加载集合以使其可用于搜索
                self.milvus_client.load_collection(collection_name)
                logger.info(f"成功加载集合: {collection_name}")
                return True
            except Exception as e:
                if attempt < self.reconnect_attempts - 1:
                    logger.warning(f"向Milvus插入/加载数据失败 (尝试 {attempt+1}/{self.reconnect_attempts}): {str(e)}，{self.reconnect_delay}秒后重试")
                    time.sleep(self.reconnect_delay)
                    # 尝试重新连接
                    self._init_client()
                else:
                    logger.error(f"向Milvus插入/加载数据失败，已达最大重试次数: {str(e)}")
        return False
                    
    def query(self, collection_name: str, filter: str, output_fields: List[str] = None) -> List[Dict[str, Any]]:
        """
        查询Milvus中的数据
        
        Args:
            collection_name: 集合名称
            filter: 过滤条件，例如 "id in ['1', '2', '3']"
            output_fields: 输出字段列表，为None时返回所有字段
            
        Returns:
            List[Dict[str, Any]]: 查询结果列表
        """
        if not self.milvus_client:
            logger.warning("Milvus客户端未初始化，尝试重新连接")
            if not self._init_client():
                logger.error("无法连接到Milvus服务，无法执行查询")
                return []
        
        # 检查集合是否存在
        if not self.collection_exists(collection_name):
            logger.warning(f"集合 {collection_name} 不存在")
            return []
        
        # 准备查询参数
        query_params = {
            "collection_name": collection_name,
            "filter": filter
        }
        
        if output_fields:
            query_params["output_fields"] = output_fields
        
        # 添加重试机制
        for attempt in range(self.reconnect_attempts):
            try:
                results = self.milvus_client.query(**query_params)
                logger.info(f"成功从 {collection_name} 查询到 {len(results)} 条记录")
                return results
            except Exception as e:
                if attempt < self.reconnect_attempts - 1:
                    logger.warning(f"查询Milvus失败 (尝试 {attempt+1}/{self.reconnect_attempts}): {str(e)}，{self.reconnect_delay}秒后重试")
                    time.sleep(self.reconnect_delay)
                    # 尝试重新连接
                    self._init_client()
                else:
                    logger.error(f"查询Milvus失败，已达最大重试次数: {str(e)}")
        return []
                    
    def search(self, collection_name: str, data: List[Dict[str, Any]], 
              filter: str = None, output_fields: List[str] = None, 
              limit: int = 100, order_by: str = None) -> List[Dict[str, Any]]:
        """
        在Milvus中进行向量搜索
        
        Args:
            collection_name: 集合名称
            data: 搜索向量数据，格式如 [{"vector_field": [0.1, 0.2, ...]}]
            filter: 可选的过滤条件
            output_fields: 可选的输出字段列表
            limit: 返回结果数量限制，默认100
            order_by: 排序字段，格式："field_name desc/asc"
            
        Returns:
            List[Dict[str, Any]]: 搜索结果列表
        """
        if not self.milvus_client:
            logger.warning("Milvus客户端未初始化，尝试重新连接")
            if not self._init_client():
                logger.error("无法连接到Milvus服务，无法执行搜索")
                return []
        
        # 检查集合是否存在
        if not self.collection_exists(collection_name):
            logger.warning(f"集合 {collection_name} 不存在")
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
        
        # 添加排序参数
        if order_by:
            search_params["order_by"] = order_by
        
        # 添加重试机制
        for attempt in range(self.reconnect_attempts):
            try:
                results = self.milvus_client.search(**search_params)
                logger.info(f"成功从 {collection_name} 搜索到 {len(results)} 组结果")
                return results
            except Exception as e:
                if attempt < self.reconnect_attempts - 1:
                    logger.warning(f"搜索Milvus失败 (尝试 {attempt+1}/{self.reconnect_attempts}): {str(e)}，{self.reconnect_delay}秒后重试")
                    time.sleep(self.reconnect_delay)
                    # 尝试重新连接
                    self._init_client()
                else:
                    logger.error(f"搜索Milvus失败，已达最大重试次数: {str(e)}")
        return []
        
    def count(self, collection_name: str, filter: str = None) -> int:
        """
        计算集合中符合条件的记录数
        
        Args:
            collection_name: 集合名称
            filter: 可选的过滤条件
            
        Returns:
            int: 记录数量
        """
        if not self.milvus_client:
            logger.warning("Milvus客户端未初始化，尝试重新连接")
            if not self._init_client():
                logger.error("无法连接到Milvus服务，无法执行计数")
                return 0
                
        # 检查集合是否存在
        if not self.collection_exists(collection_name):
            logger.warning(f"集合 {collection_name} 不存在")
            return 0
            
        count_params = {"collection_name": collection_name}
        if filter:
            count_params["filter"] = filter
            
        # 添加重试机制
        for attempt in range(self.reconnect_attempts):
            try:
                count = self.milvus_client.count(**count_params)
                return count
            except Exception as e:
                if attempt < self.reconnect_attempts - 1:
                    logger.warning(f"计算Milvus记录数失败 (尝试 {attempt+1}/{self.reconnect_attempts}): {str(e)}，{self.reconnect_delay}秒后重试")
                    time.sleep(self.reconnect_delay)
                    # 尝试重新连接
                    self._init_client()
                else:
                    logger.error(f"计算Milvus记录数失败，已达最大重试次数: {str(e)}")
        return 0
    
    def delete(self, collection_name: str, filter: str) -> bool:
        """
        删除集合中符合条件的记录
        
        Args:
            collection_name: 集合名称
            filter: 过滤条件，例如 "id in ['1', '2', '3']"
            
        Returns:
            bool: 删除是否成功
        """
        if not self.milvus_client:
            logger.warning("Milvus客户端未初始化，尝试重新连接")
            if not self._init_client():
                logger.error("无法连接到Milvus服务，无法执行删除")
                return False
                
        # 检查集合是否存在
        if not self.collection_exists(collection_name):
            logger.warning(f"集合 {collection_name} 不存在")
            return False
            
        # 添加重试机制
        for attempt in range(self.reconnect_attempts):
            try:
                self.milvus_client.delete(
                    collection_name=collection_name,
                    filter=filter
                )
                logger.info(f"成功从 {collection_name} 中删除符合条件的记录")
                return True
            except Exception as e:
                if attempt < self.reconnect_attempts - 1:
                    logger.warning(f"删除Milvus记录失败 (尝试 {attempt+1}/{self.reconnect_attempts}): {str(e)}，{self.reconnect_delay}秒后重试")
                    time.sleep(self.reconnect_delay)
                    # 尝试重新连接
                    self._init_client()
                else:
                    logger.error(f"删除Milvus记录失败，已达最大重试次数: {str(e)}")
        return False
    
    def close(self):
        """
        关闭Milvus客户端连接
        """
        if self.milvus_client:
            try:
                # 目前的MilvusClient没有显式的close方法
                # 将引用设为None允许垃圾回收
                self.milvus_client = None
                logger.info("已关闭Milvus客户端连接")
            except Exception as e:
                logger.error(f"关闭Milvus客户端连接时出错: {str(e)}")
