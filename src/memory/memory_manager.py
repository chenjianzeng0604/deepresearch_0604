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
from datetime import datetime
import uuid

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
        self.memory_expiry = int(os.getenv("REDIS_MEMORY_EXPIRY", "3600"))
    
    def _init_memory_tables(self):
        """初始化记忆相关的数据表"""
        try:
            with self.connection.cursor() as cursor:
                # 从chat_schema中查找并创建记忆相关表
                for table_name, create_sql in CHAT_SCHEMA.items():
                    if table_name in ['memories', 'messages']:
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
    
    def save_chat_history(self, session_id: str, messages: List[Dict]) -> bool:
        """
        保存会话历史到短期记忆(Redis)和长期存储(MySQL)
        
        Args:
            session_id: 会话ID
            messages: 消息列表
            
        Returns:
            bool: 是否保存成功
        """
        success = True
        
        # 1. 保存到Redis缓存
        if self.redis_client:
            try:
                # 构造redis键名
                redis_key = f"chat_history:{session_id}"
                
                # 将消息列表序列化为JSON并保存
                value = json.dumps(messages, ensure_ascii=False)
                self.redis_client.set(redis_key, value, ex=self.memory_expiry)
            except Exception as e:
                logger.error(f"保存会话历史到Redis失败: {str(e)}")
                success = False
        else:
            logger.warning("Redis未连接，会话历史将只保存到MySQL")
        
        # 2. 同步保存到MySQL数据库
        if messages:
            try:
                # 检查会话是否存在
                session = self.session_manager.get_session(session_id)
                if not session:
                    # 如果会话不存在，创建会话
                    self.session_manager.create_session(session_id)
                
                # 找出最后保存的消息ID，以避免重复保存
                last_message_id = None
                try:
                    with self.connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT id FROM messages WHERE session_id = %s ORDER BY created_at DESC LIMIT 1",
                            (session_id,)
                        )
                        result = cursor.fetchone()
                        if result:
                            last_message_id = result.get('id')
                except Exception as e:
                    logger.warning(f"获取最后消息ID失败: {str(e)}")
                
                # 遍历所有消息并保存到MySQL
                # 只保存还未保存过的新消息(通常是最新的消息)
                new_messages = []
                for message in messages:
                    # 检查是否已经存在相同内容的消息来避免重复
                    message_id = message.get('id')
                    
                    # 如果消息ID已经存在于数据库中，则跳过
                    if message_id and message_id == last_message_id:
                        continue
                    
                    role = message.get('role', 'unknown')
                    content = message.get('content', '')
                    
                    # 不传递id值，让MySQL自动生成自增ID
                    new_messages.append((session_id, role, content))
                
                # 批量插入新消息
                if new_messages:
                    with self.connection.cursor() as cursor:
                        cursor.executemany(
                            "INSERT INTO messages (session_id, role, content) VALUES (%s, %s, %s)",
                            new_messages
                        )
                    self.connection.commit()
                
                # 更新会话最后修改时间
                self.session_manager.update_session(session_id)
            except Exception as e:
                logger.error(f"保存会话历史到MySQL失败: {str(e)}", exc_info=True)
                success = False
                
        return success
    
    def get_chat_history(self, session_id: str) -> List[Dict]:
        """
        获取会话历史，优先从Redis获取，如果Redis不可用则从MySQL获取
        
        Args:
            session_id: 会话ID
            
        Returns:
            List[Dict]: 消息列表
        """
        # 1. 首先尝试从Redis获取
        if self.redis_client:
            try:
                # 构造redis键名
                redis_key = f"chat_history:{session_id}"
                
                # 从redis获取并反序列化
                value = self.redis_client.get(redis_key)
                if value:
                    return json.loads(value)
            except Exception as e:
                logger.error(f"从Redis获取会话历史失败: {str(e)}")
        
        # 2. 如果Redis获取失败或无数据，从MySQL获取
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id, role, content, created_at FROM messages WHERE session_id = %s ORDER BY created_at ASC",
                    (session_id,)
                )
                messages = cursor.fetchall()
                
                # 转换为适合LLM使用的格式
                result = []
                for message in messages:
                    result.append({
                        "id": str(message["id"]),  # 转换为字符串确保与之前的UUID格式兼容
                        "role": message["role"],
                        "content": message["content"],
                        "timestamp": message["created_at"].isoformat() if message["created_at"] else None
                    })
                
                # 如果从MySQL获取到数据，同步缓存到Redis
                if result and self.redis_client:
                    self._sync_to_redis(session_id, "chat_history", result)
                
                return result
        except Exception as e:
            logger.error(f"从MySQL获取会话历史失败: {str(e)}")
            return []
    
    def _sync_to_redis(self, session_id: str, key_type: str, data: Any) -> bool:
        """
        将数据同步到Redis缓存
        
        Args:
            session_id: 会话ID
            key_type: 键类型，如'chat_history'
            data: 要同步的数据
            
        Returns:
            bool: 是否同步成功
        """
        # 参数验证
        if not session_id or not isinstance(session_id, str):
            logger.error("同步到Redis失败: 无效的会话ID")
            return False
            
        if not key_type or not isinstance(key_type, str):
            logger.error(f"同步到Redis失败: 无效的键类型: {key_type}")
            return False
            
        if data is None:
            logger.warning(f"同步到Redis失败: 数据为None: {session_id}, {key_type}")
            return False
            
        # Redis客户端检查
        if not self.redis_client:
            logger.warning("Redis客户端未初始化，跳过同步")
            return False
            
        try:
            # 构造redis键名
            redis_key = f"{key_type}:{session_id}"
            
            # 序列化数据
            try:
                if isinstance(data, str):
                    value = data
                else:
                    value = json.dumps(data, ensure_ascii=False)
            except (TypeError, OverflowError) as je:
                logger.error(f"Redis数据序列化失败: {je}", exc_info=True)
                return False
                
            # 设置过期时间
            expiry_time = self.memory_expiry
            
            # 保存数据到Redis并设置过期时间
            self.redis_client.set(redis_key, value, ex=expiry_time)
            logger.debug(f"数据已同步到Redis: {redis_key}, 过期时间: {expiry_time}秒")
            return True
        except redis.RedisError as re:
            logger.error(f"Redis操作失败: {re}", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"同步数据到Redis失败: {str(e)}", exc_info=True)
            return False

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
