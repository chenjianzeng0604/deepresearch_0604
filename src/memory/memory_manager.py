"""
记忆管理模块，提供长期和短期记忆的统一管理
"""

import os
import logging
import json
from typing import Dict, List, Any, Optional, Union
import redis
from src.database.mysql.mysql_base import MySQLBase
from src.session.session_manager import session_manager
from src.database.mysql.schemas.chat_schema import CHAT_SCHEMA

logger = logging.getLogger(__name__)

class MemoryManager(MySQLBase):
    """记忆管理类，提供长期和短期记忆的存储和查询
    
    长期记忆基于MySQL数据库存储，适合持久保存的重要信息
    短期记忆基于Redis数据库存储，适合临时保存的会话上下文信息
    """
    
    def __init__(self):
        """初始化MySQL和Redis连接"""
        super().__init__()
        self._init_memory_tables()
        self.session_manager = session_manager
        
        # 初始化Redis连接
        self.redis_host = os.getenv("REDIS_HOST", "localhost")
        self.redis_port = int(os.getenv("REDIS_PORT", "6379"))
        self.redis_db = int(os.getenv("REDIS_DB", "0"))
        self.redis_password = os.getenv("REDIS_PASSWORD", None)
        self.redis_client = None
        self._connect_redis()
        
        # 短期记忆的过期时间，默认1小时
        self.memory_expiry = int(os.getenv("REDIS_MEMORY_EXPIRY", "3600"))
    
    def _init_memory_tables(self):
        """初始化记忆相关的数据表"""
        try:
            with self.connection.cursor() as cursor:
                # 从chat_schema中查找并创建记忆相关表
                for table_name, create_sql in CHAT_SCHEMA.items():
                    if table_name in ['memories', 'memory_tags', 'memory_references']:
                        cursor.execute(create_sql)
                        logger.debug(f"创建或确认表存在: {table_name}")
        except Exception as e:
            logger.error(f"记忆相关表初始化失败: {str(e)}")
            raise
    
    def _connect_redis(self):
        """建立Redis连接"""
        try:
            self.redis_client = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                db=self.redis_db,
                password=self.redis_password,
                decode_responses=True
            )
        except Exception as e:
            logger.error(f"Redis连接失败: {str(e)}")
            self.redis_client = None
    
    # 长期记忆管理 (MySQL)
    def add_memory(self, session_id: str, content: str) -> Optional[str]:
        """
        添加长期记忆
        
        Args:
            session_id: 会话ID
            content: 记忆内容
            
        Returns:
            Optional[str]: 记忆ID，如果添加失败则返回None
        """
        try:
            # 检查会话是否存在
            session = self.session_manager.get_session(session_id)
            if not session:
                # 如果会话不存在，创建会话
                self.session_manager.create_session(session_id)
            
            # 生成记忆ID
            memory_id = os.urandom(16).hex()
            
            # 添加记忆
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO memories (id, session_id, content) VALUES (%s, %s, %s)",
                    (memory_id, session_id, content)
                )
            
            return memory_id
        except Exception as e:
            logger.error(f"添加长期记忆失败: {str(e)}")
            return None
    
    def get_memories(self, session_id: str, limit: int = 10) -> List[Dict]:
        """
        获取会话的长期记忆
        
        Args:
            session_id: 会话ID
            limit: 返回的记忆数量限制
            
        Returns:
            List[Dict]: 记忆列表，按时间排序
        """
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id, content, created_at FROM memories WHERE session_id = %s ORDER BY created_at DESC LIMIT %s",
                    (session_id, limit)
                )
                memories = cursor.fetchall()
                
                # 转换为格式化的记忆列表
                result = []
                for memory in memories:
                    result.append({
                        "id": memory["id"],
                        "content": memory["content"],
                        "timestamp": memory["created_at"].isoformat() if memory["created_at"] else None
                    })
                
                return result
        except Exception as e:
            logger.error(f"获取长期记忆失败: {str(e)}")
            return []
    
    def get_memory_content(self, session_id: str, limit: int = 10) -> List[str]:
        """
        获取会话的长期记忆内容
        
        Args:
            session_id: 会话ID
            limit: 返回的记忆数量限制
            
        Returns:
            List[str]: 长期记忆内容列表
        """
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "SELECT content FROM memories WHERE session_id = %s ORDER BY created_at DESC LIMIT %s",
                    (session_id, limit)
                )
                memories = cursor.fetchall()
                return [memory["content"] for memory in memories]
        except Exception as e:
            logger.error(f"获取长期记忆内容失败: {str(e)}")
            return []
    
    def delete_memory(self, memory_id: str) -> bool:
        """
        删除长期记忆
        
        Args:
            memory_id: 记忆ID
            
        Returns:
            bool: 是否删除成功
        """
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("DELETE FROM memories WHERE id = %s", (memory_id,))
            return True
        except Exception as e:
            logger.error(f"删除长期记忆失败: {str(e)}")
            return False
    
    def clear_session_memories(self, session_id: str) -> bool:
        """
        清空会话长期记忆
        
        Args:
            session_id: 会话ID
            
        Returns:
            bool: 是否清空成功
        """
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("DELETE FROM memories WHERE session_id = %s", (session_id,))
            return True
        except Exception as e:
            logger.error(f"清空会话长期记忆失败: {str(e)}")
            return False
    
    # 短期记忆管理 (Redis)
    
    def save_short_memory(self, session_id: str, key: str, value: Union[str, Dict, List]) -> bool:
        """
        保存短期记忆
        
        Args:
            session_id: 会话ID
            key: 记忆键
            value: 记忆值，可以是字符串或可JSON序列化的对象
            
        Returns:
            bool: 是否保存成功
        """
        if not self.redis_client:
            logger.warning("Redis未连接，无法保存短期记忆")
            return False
            
        try:
            # 如果value不是字符串，尝试序列化为JSON
            if not isinstance(value, str):
                value = json.dumps(value, ensure_ascii=False)
            
            # 构造redis键名
            redis_key = f"memory:{session_id}:{key}"
            
            # 保存到redis
            self.redis_client.set(redis_key, value, ex=self.memory_expiry)
            return True
        except Exception as e:
            logger.error(f"保存短期记忆失败: {str(e)}")
            return False
    
    def get_short_memory(self, session_id: str, key: str) -> Optional[str]:
        """
        获取短期记忆
        
        Args:
            session_id: 会话ID
            key: 记忆键
            
        Returns:
            Optional[str]: 记忆值
        """
        if not self.redis_client:
            logger.warning("Redis未连接，无法获取短期记忆")
            return None
            
        try:
            # 构造redis键名
            redis_key = f"memory:{session_id}:{key}"
            
            # 从redis获取
            value = self.redis_client.get(redis_key)
            return value
        except Exception as e:
            logger.error(f"获取短期记忆失败: {str(e)}")
            return None
    
    def save_chat_history(self, session_id: str, messages: List[Dict]) -> bool:
        """
        保存会话历史到短期记忆
        
        Args:
            session_id: 会话ID
            messages: 消息列表
            
        Returns:
            bool: 是否保存成功
        """
        if not self.redis_client:
            logger.warning("Redis未连接，无法保存会话历史")
            return False
            
        try:
            # 构造redis键名
            redis_key = f"chat_history:{session_id}"
            
            # 将消息列表序列化为JSON并保存
            value = json.dumps(messages, ensure_ascii=False)
            self.redis_client.set(redis_key, value, ex=self.memory_expiry)
            return True
        except Exception as e:
            logger.error(f"保存会话历史失败: {str(e)}")
            return False
    
    def get_chat_history(self, session_id: str) -> List[Dict]:
        """
        从短期记忆获取会话历史
        
        Args:
            session_id: 会话ID
            
        Returns:
            List[Dict]: 消息列表
        """
        if not self.redis_client:
            logger.warning("Redis未连接，无法获取会话历史")
            return []
            
        try:
            # 构造redis键名
            redis_key = f"chat_history:{session_id}"
            
            # 从redis获取并反序列化
            value = self.redis_client.get(redis_key)
            if value:
                return json.loads(value)
            return []
        except Exception as e:
            logger.error(f"获取会话历史失败: {str(e)}")
            return []
    
    def close(self):
        """关闭数据库连接"""
        # 关闭MySQL连接
        if hasattr(self, 'connection') and self.connection:
            self.connection.close()
            logger.info("MySQL连接已关闭")
        
        # 关闭Redis连接
        if self.redis_client:
            self.redis_client.close()
            logger.info("Redis连接已关闭")

memory_manager = MemoryManager()

