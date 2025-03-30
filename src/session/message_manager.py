"""
MySQL消息管理模块
"""

import os
import logging
from typing import Dict, List, Optional
from src.database.mysql.mysql_base import MySQLBase
from src.session.session_manager import session_manager
from src.database.mysql.schemas.chat_schema import CHAT_SCHEMA

logger = logging.getLogger(__name__)

class MessageManager(MySQLBase):
    """MySQL消息管理类，提供消息的存储和查询"""
    
    def __init__(self):
        """初始化MySQL连接并确保消息相关表存在"""
        super().__init__()
        self._init_message_tables()
        self.session_manager = session_manager
    
    def _init_message_tables(self):
        """初始化消息相关的数据表"""
        try:
            with self.connection.cursor() as cursor:
                # 从chat_schema中查找并创建消息相关表
                for table_name, create_sql in CHAT_SCHEMA.items():
                    if table_name in ['messages', 'message_attachments']:
                        cursor.execute(create_sql)
                        logger.debug(f"创建或确认表存在: {table_name}")
        except Exception as e:
            logger.error(f"消息相关表初始化失败: {str(e)}")
            raise
    
    def add_message(self, session_id: str, role: str, content: str) -> Optional[str]:
        """
        添加消息到会话
        
        Args:
            session_id: 会话ID
            role: 角色，'user'或'assistant'
            content: 消息内容
            
        Returns:
            Optional[str]: 消息ID，如果添加失败则返回None
        """
        try:
            # 检查会话是否存在
            session = self.session_manager.get_session(session_id)
            if not session:
                # 如果会话不存在，创建会话
                self.session_manager.create_session(session_id)
            
            # 生成消息ID
            message_id = os.urandom(16).hex()
            
            # 添加消息
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO messages (id, session_id, role, content) VALUES (%s, %s, %s, %s)",
                    (message_id, session_id, role, content)
                )
                
                # 更新会话的更新时间
                cursor.execute(
                    "UPDATE sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                    (session_id,)
                )
            
            return message_id
        except Exception as e:
            logger.error(f"添加消息失败: {str(e)}")
            return None
    
    def get_messages(self, session_id: str, limit: int = 100) -> List[Dict]:
        """
        获取会话的消息历史
        
        Args:
            session_id: 会话ID
            limit: 返回的消息数量限制
            
        Returns:
            List[Dict]: 消息列表，按时间正序排列
        """
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id, role, content, created_at FROM messages WHERE session_id = %s ORDER BY created_at ASC LIMIT %s",
                    (session_id, limit)
                )
                messages = cursor.fetchall()
                
                # 转换为格式化的消息列表
                result = []
                for msg in messages:
                    result.append({
                        "id": msg["id"],
                        "role": msg["role"],
                        "content": msg["content"],
                        "timestamp": msg["created_at"].isoformat() if msg["created_at"] else None
                    })
                
                return result
        except Exception as e:
            logger.error(f"获取消息历史失败: {str(e)}")
            return []
    
    def delete_message(self, message_id: str) -> bool:
        """
        删除消息
        
        Args:
            message_id: 消息ID
            
        Returns:
            bool: 是否删除成功
        """
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("DELETE FROM messages WHERE id = %s", (message_id,))
            return True
        except Exception as e:
            logger.error(f"删除消息失败: {str(e)}")
            return False
    
    def clear_session_messages(self, session_id: str) -> bool:
        """
        清空会话消息
        
        Args:
            session_id: 会话ID
            
        Returns:
            bool: 是否清空成功
        """
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("DELETE FROM messages WHERE session_id = %s", (session_id,))
            return True
        except Exception as e:
            logger.error(f"清空会话消息失败: {str(e)}")
            return False
