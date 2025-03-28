"""
MySQL数据库表结构定义模块
"""

from .chat_schema import CHAT_SCHEMA
from .crawler_schema import CRAWLER_SCHEMA

__all__ = ['CHAT_SCHEMA', 'CRAWLER_SCHEMA']
