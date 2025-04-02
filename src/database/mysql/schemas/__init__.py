"""
MySQL数据库表结构定义模块
"""

from .chat_schema import CHAT_SCHEMA, init_chat_default_data

# 为保持与原有代码兼容，提供一个空的CRAWLER_SCHEMA字典
CRAWLER_SCHEMA = {
    # 爬虫场景表 - 现在完全由crawler_config.py管理
}

__all__ = ['CHAT_SCHEMA', 'CRAWLER_SCHEMA', 'init_chat_default_data']
