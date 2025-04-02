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
        
        # 短期记忆的过期时间，默认1小时
        self.memory_expiry = int(os.getenv("REDIS_MEMORY_EXPIRY", "3600"))
    
    def _init_memory_tables(self):
        """初始化记忆相关的数据表"""
        try:
            with self.connection.cursor() as cursor:
                # 从chat_schema中查找并创建记忆相关表
                for table_name, create_sql in CHAT_SCHEMA.items():
                    if table_name in ['memories', 'memory_tags', 'memory_references', 'chat_messages']:
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
                            "SELECT id FROM chat_messages WHERE session_id = %s ORDER BY created_at DESC LIMIT 1",
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
                    # 检查消息是否有ID，如果没有则生成一个
                    message_id = message.get('id')
                    if not message_id:
                        message_id = str(uuid.uuid4())
                        message['id'] = message_id
                    
                    # 如果消息ID已经存在于数据库中，则跳过
                    if message_id == last_message_id:
                        continue
                    
                    role = message.get('role', 'unknown')
                    content = message.get('content', '')
                    
                    new_messages.append((message_id, session_id, role, content))
                
                # 批量插入新消息
                if new_messages:
                    with self.connection.cursor() as cursor:
                        cursor.executemany(
                            "INSERT INTO chat_messages (id, session_id, role, content) VALUES (%s, %s, %s, %s)",
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
                    "SELECT role, content, created_at FROM chat_messages WHERE session_id = %s ORDER BY created_at ASC",
                    (session_id,)
                )
                messages = cursor.fetchall()
                
                # 转换为适合LLM使用的格式
                result = []
                for message in messages:
                    result.append({
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
            key_type: 键类型，如'chat_history'、'memory'或'user_features'
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
                
            # 设置过期时间，不同类型的数据可以有不同的过期时间
            expiry_time = {
                'chat_history': self.memory_expiry,             # 短期记忆默认过期时间
                'memory': self.memory_expiry * 2,               # 长期记忆保留时间更长
                'user_features': self.memory_expiry * 3         # 用户特征保留时间最长
            }.get(key_type, self.memory_expiry)
            
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
    
    def save_memory(self, session_id: str, content: str, user_features: Dict = None) -> bool:
        """
        保存长期记忆并提取用户特征
        
        Args:
            session_id: 会话ID
            content: 记忆内容
            user_features: 用户特征字典，可选
            
        Returns:
            bool: 是否保存成功
        """
        # 参数验证
        if not session_id or not isinstance(session_id, str):
            logger.error("保存记忆失败: 无效的会话ID")
            return False
            
        if not content or not isinstance(content, str) or len(content.strip()) < 5:
            logger.error(f"保存记忆失败: 无效的记忆内容: '{content}'")
            return False
            
        if user_features is not None and not isinstance(user_features, dict):
            logger.error(f"保存记忆失败: 无效的用户特征类型: {type(user_features)}")
            return False
            
        try:
            # 检查会话是否存在
            session = self.session_manager.get_session(session_id)
            if not session:
                # 如果会话不存在，创建会话
                self.session_manager.create_session(session_id)
                logger.info(f"为长期记忆创建新会话: {session_id}")
                
            # 处理用户特征数据
            features_json = None
            if user_features:
                try:
                    # 过滤无效特征数据
                    filtered_features = {k: v for k, v in user_features.items() if v}
                    if filtered_features:
                        features_json = json.dumps(filtered_features, ensure_ascii=False)
                except Exception as je:
                    logger.warning(f"用户特征序列化失败，但将继续保存记忆: {je}")
            
            # 生成记忆ID
            memory_id = os.urandom(16).hex()
            
            # 数据库事务
            try:
                with self.connection.cursor() as cursor:
                    if features_json:
                        # 保存记忆和用户特征
                        cursor.execute(
                            "INSERT INTO memories (id, session_id, content, user_features) VALUES (%s, %s, %s, %s)",
                            (memory_id, session_id, content, features_json)
                        )
                    else:
                        # 只保存记忆
                        cursor.execute(
                            "INSERT INTO memories (id, session_id, content) VALUES (%s, %s, %s)",
                            (memory_id, session_id, content)
                        )
                self.connection.commit()
                logger.info(f"长期记忆保存到MySQL成功: {session_id}")
            except Exception as db_error:
                self.connection.rollback()
                logger.error(f"保存长期记忆到MySQL失败: {db_error}", exc_info=True)
                return False
            
            # 同步到Redis缓存
            sync_result = self._sync_to_redis(session_id, "memory", content)
            
            # 如果有用户特征，也同步到Redis
            if user_features:
                user_features_sync = self._sync_to_redis(session_id, "user_features", user_features)
                if not user_features_sync:
                    logger.warning(f"用户特征同步到Redis失败，但已保存到MySQL: {session_id}")
            
            if not sync_result:
                logger.warning(f"记忆同步到Redis失败，但已保存到MySQL: {session_id}")
                
            return True
        except Exception as e:
            logger.error(f"保存长期记忆失败: {str(e)}", exc_info=True)
            return False
    
    def get_memory(self, session_id: str) -> Optional[str]:
        """
        获取会话的最新长期记忆内容
        
        Args:
            session_id: 会话ID
            
        Returns:
            Optional[str]: 长期记忆内容
        """
        # 首先尝试从Redis获取
        if self.redis_client:
            try:
                redis_key = f"memory:{session_id}"
                value = self.redis_client.get(redis_key)
                if value:
                    try:
                        memory_data = json.loads(value)
                        if isinstance(memory_data, dict) and "content" in memory_data:
                            return memory_data["content"]
                    except json.JSONDecodeError:
                        # 如果不是JSON格式，直接返回
                        return value
            except Exception as e:
                logger.error(f"从Redis获取记忆失败: {str(e)}")
        
        # 如果Redis获取失败，从MySQL获取
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "SELECT content FROM memories WHERE session_id = %s ORDER BY created_at DESC LIMIT 1",
                    (session_id,)
                )
                memory = cursor.fetchone()
                if memory:
                    # 同步到Redis
                    self._sync_to_redis(session_id, "memory", memory["content"])
                    return memory["content"]
                return None
        except Exception as e:
            logger.error(f"获取长期记忆内容失败: {str(e)}")
            return None
    
    def get_user_features(self, session_id: str) -> Dict:
        """
        获取用户特征
        
        Args:
            session_id: 会话ID
            
        Returns:
            Dict: 用户特征字典
        """
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "SELECT user_features FROM memories WHERE session_id = %s AND user_features IS NOT NULL ORDER BY created_at DESC LIMIT 1",
                    (session_id,)
                )
                result = cursor.fetchone()
                if result and result["user_features"]:
                    try:
                        return json.loads(result["user_features"])
                    except json.JSONDecodeError:
                        logger.error("用户特征解析失败")
            return {}
        except Exception as e:
            logger.error(f"获取用户特征失败: {str(e)}")
            return {}
    
    def save_user_features(self, session_id: str, features: Dict) -> bool:
        """
        单独保存用户特征
        
        Args:
            session_id: 会话ID
            features: 用户特征字典
            
        Returns:
            bool: 是否保存成功
        """
        # 参数验证
        if not session_id or not isinstance(session_id, str):
            logger.error("保存用户特征失败: 无效的会话ID")
            return False
            
        if not features or not isinstance(features, dict):
            logger.error(f"保存用户特征失败: 无效的特征数据类型: {type(features)}")
            return False
            
        # 过滤空值，避免存储无用数据
        filtered_features = {k: v for k, v in features.items() if v}
        if not filtered_features:
            logger.warning("保存用户特征失败: 过滤空值后无有效特征数据")
            return False
            
        try:
            # 检查会话是否存在
            session = self.session_manager.get_session(session_id)
            if not session:
                # 如果会话不存在，创建会话
                self.session_manager.create_session(session_id)
                logger.info(f"为用户特征创建新会话: {session_id}")
                
            # 序列化特征数据
            try:
                features_json = json.dumps(filtered_features, ensure_ascii=False)
            except (TypeError, OverflowError) as je:
                logger.error(f"特征数据JSON序列化失败: {je}", exc_info=True)
                return False
            
            # 数据库事务
            try:
                # 更新最新的记忆条目
                with self.connection.cursor() as cursor:
                    # 先尝试更新最新的记忆条目
                    cursor.execute(
                        "UPDATE memories SET user_features = %s WHERE session_id = %s ORDER BY created_at DESC LIMIT 1",
                        (features_json, session_id)
                    )
                    if cursor.rowcount == 0:
                        # 如果没有记忆条目，创建一个新的
                        memory_id = os.urandom(16).hex()
                        cursor.execute(
                            "INSERT INTO memories (id, session_id, content, user_features) VALUES (%s, %s, %s, %s)",
                            (memory_id, session_id, "用户特征记忆", features_json)
                        )
                        
                self.connection.commit()
                logger.info(f"用户特征保存到MySQL成功: {session_id}")
            except Exception as db_error:
                self.connection.rollback()
                logger.error(f"保存用户特征到MySQL失败: {db_error}", exc_info=True)
                return False
            
            # 同步到Redis缓存 - 即使失败也不影响整体操作
            try:
                self._sync_to_redis(session_id, "user_features", filtered_features)
                logger.info(f"用户特征同步到Redis成功: {session_id}")
            except Exception as redis_error:
                logger.warning(f"同步用户特征到Redis失败，但已保存到MySQL: {redis_error}")
                # 这里我们不返回False，因为数据已经成功保存到MySQL
            
            return True
        except Exception as e:
            logger.error(f"保存用户特征失败: {str(e)}", exc_info=True)
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
