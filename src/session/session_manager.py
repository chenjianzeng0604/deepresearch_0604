"""
MySQL会话管理模块
"""

import os
import logging
import datetime
from typing import Dict, List, Optional
from src.database.mysql.mysql_base import MySQLBase
from src.database.mysql.schemas.chat_schema import CHAT_SCHEMA

logger = logging.getLogger(__name__)

class SessionManager(MySQLBase):
    """MySQL会话管理类，提供会话的存储和查询"""
    
    def __init__(self):
        """初始化MySQL连接并确保会话相关表存在"""
        super().__init__()
        self._init_session_tables()
    
    def _init_session_tables(self):
        """初始化会话相关的数据表"""
        try:
            with self.connection.cursor() as cursor:
                # 从chat_schema中查找并创建会话相关表
                for table_name, create_sql in CHAT_SCHEMA.items():
                    if table_name in ['sessions', 'session_categories', 'session_tags']:
                        cursor.execute(create_sql)
                        logger.debug(f"创建或确认表存在: {table_name}")
        except Exception as e:
            logger.error(f"会话相关表初始化失败: {str(e)}")
            raise
    
    def create_session(self, session_id: str, user_id: str = None, title: str = None) -> bool:
        """
        创建新会话
        
        Args:
            session_id: 会话ID
            user_id: 用户ID
            title: 会话标题
            
        Returns:
            bool: 是否创建成功
        """
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO sessions (id, user_id, title) VALUES (%s, %s, %s)",
                    (session_id, user_id, title or f"会话 {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                )
            return True
        except Exception as e:
            logger.error(f"创建会话失败: {str(e)}")
            return False
    
    def get_session(self, session_id: str) -> Optional[Dict]:
        """
        获取会话信息
        
        Args:
            session_id: 会话ID
            
        Returns:
            Optional[Dict]: 会话信息
        """
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT * FROM sessions WHERE id = %s", (session_id,))
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"获取会话失败: {str(e)}")
            return None
    
    def list_sessions(self, user_id: Optional[str] = None, limit: int = 10) -> List[Dict]:
        """
        列出会话
        
        Args:
            user_id: 用户ID，如果指定则只返回该用户的会话
            limit: 返回数量限制
            
        Returns:
            List[Dict]: 会话列表
        """
        try:
            with self.connection.cursor() as cursor:
                if user_id:
                    cursor.execute(
                        "SELECT * FROM sessions WHERE user_id = %s ORDER BY updated_at DESC LIMIT %s",
                        (user_id, limit)
                    )
                else:
                    cursor.execute(
                        "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT %s",
                        (limit,)
                    )
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"列出会话失败: {str(e)}")
            return []
    
    def update_session_status(self, session_id: str, status: str) -> bool:
        """
        更新会话状态
        
        Args:
            session_id: 会话ID
            status: 会话状态
            
        Returns:
            bool: 是否更新成功
        """
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE sessions SET status = %s WHERE id = %s",
                    (status, session_id)
                )
            return True
        except Exception as e:
            logger.error(f"更新会话状态失败: {str(e)}")
            return False
    
    def delete_session(self, session_id: str) -> bool:
        """
        删除会话
        
        Args:
            session_id: 会话ID
            
        Returns:
            bool: 是否删除成功
        """
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("DELETE FROM sessions WHERE id = %s", (session_id,))
            return True
        except Exception as e:
            logger.error(f"删除会话失败: {str(e)}")
            return False
            
    def update_session(self, session_id: str, title: str = None) -> bool:
        """
        更新会话信息，包括最后修改时间
        
        Args:
            session_id: 会话ID
            title: 会话标题，如果不指定则不更新
            
        Returns:
            bool: 是否更新成功
        """
        try:
            sql = "UPDATE sessions SET updated_at = CURRENT_TIMESTAMP"
            params = []
            
            if title:
                sql += ", title = %s"
                params.append(title)
                
            sql += " WHERE id = %s"
            params.append(session_id)
            
            with self.connection.cursor() as cursor:
                cursor.execute(sql, tuple(params))
            self.connection.commit()
            return True
        except Exception as e:
            logger.error(f"更新会话信息失败: {str(e)}")
            return False

session_manager = SessionManager()
