"""
MySQL数据库表结构定义模块
"""

from .chat_schema import CHAT_SCHEMA, init_chat_default_data
from .crawler_schema import CRAWLER_SCHEMA

__all__ = ['CHAT_SCHEMA', 'CRAWLER_SCHEMA', 'init_chat_default_data']
