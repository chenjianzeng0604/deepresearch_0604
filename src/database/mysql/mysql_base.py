"""
MySQL数据库基础连接模块
"""

import os
import logging
import pymysql
from pymysql.cursors import DictCursor

logger = logging.getLogger(__name__)

class MySQLBase:
    """MySQL数据库基础连接类"""
    
    def __init__(self):
        """初始化MySQL连接"""
        self.host = os.getenv("MYSQL_HOST", "localhost")
        self.port = int(os.getenv("MYSQL_PORT", "3306"))
        self.user = os.getenv("MYSQL_USER", "root")
        self.password = os.getenv("MYSQL_PASSWORD", "")
        self.db_name = os.getenv("MYSQL_DB_NAME", "deepresearch")
        self.connection = None
        self._connect()
    
    def _connect(self):
        """建立MySQL连接"""
        try:
            self.connection = pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.db_name,
                charset='utf8mb4',
                cursorclass=DictCursor,
                autocommit=True
            )
        except Exception as e:
            logger.error(f"MySQL连接失败: {str(e)}")
            raise
    
    def close(self):
        """关闭MySQL连接"""
        if self.connection:
            self.connection.close()
            logger.info("MySQL连接已关闭")
